"""llm-proxy partagé (Chap 18 §4) — base LiteLLM, jetons par projet, Groq.

Écart constaté en prod (2026-11-21, questions de l'agent de 0-hl) : le
proxy tournait SANS base de données, alors que le Chap 18 prévoit
`general_settings.database_url` + un jeton par projet généré via
`/key/generate` (max_budget / budget_duration). Sans base : aucun jeton
virtuel, aucun budget, aucun /key/info ni /spend/logs — chaque projet
recevait la clé MAÎTRE comme LLM_PROXY_TOKEN (dépense illimitée, droits
d'administration du proxy, aucune attribution de coût par projet).

Ces tests verrouillent la remise en conformité :
- compose + litellm-config.yaml branchent réellement la base ;
- aucun secret littéral dans la config (clés via os.environ/...) ;
- scripts/llm-proxy-keys.sh crée la base/le rôle et émet un jeton par
  projet écrit DIRECTEMENT dans le .env.local du projet, jamais affiché
  (il ne doit transiter ni par un terminal partagé, ni par un chat).
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

SHARED = Path(__file__).resolve().parents[1] / "shared_services"
COMPOSE = SHARED / "docker-compose.yml"
CONFIG = SHARED / "litellm-config.yaml"
ENV_EXAMPLE = SHARED / ".env.example"
SCRIPT = SHARED / "scripts" / "llm-proxy-keys.sh"

BASH = shutil.which("bash") or ""


def _proxy() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["llm-proxy"]


def _config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _env_list(service: dict) -> list[str]:
    return list(service.get("environment", []))


# --- compose / config --------------------------------------------------------


def test_llm_proxy_has_database_url_on_shared_postgres():
    env = _env_list(_proxy())
    db = next(e for e in env if e.startswith("DATABASE_URL="))
    assert db == (
        "DATABASE_URL=postgresql://litellm:${LITELLM_DB_PASSWORD}"
        "@postgres:5432/litellm"
    )


def test_llm_proxy_receives_groq_key_from_env_only():
    assert "GROQ_API_KEY=${GROQ_API_KEY}" in _env_list(_proxy())


def test_config_general_settings_wire_master_key_and_database():
    gs = _config()["general_settings"]
    assert gs["master_key"] == "os.environ/LITELLM_MASTER_KEY"
    assert gs["database_url"] == "os.environ/DATABASE_URL"


def test_config_never_stores_prompts_in_spend_logs():
    # Les spend logs servent à l'attribution des coûts (Chap 18, fleet
    # dashboard), pas à archiver le contenu des prompts des projets.
    assert _config()["general_settings"]["store_prompts_in_spend_logs"] is False


def test_every_model_key_comes_from_environment():
    for entry in _config()["model_list"]:
        key = entry["litellm_params"].get("api_key", "")
        assert key.startswith("os.environ/"), entry["model_name"]


def test_groq_models_use_groq_provider_and_groq_key():
    groq = [m for m in _config()["model_list"] if m["model_name"].startswith("groq-")]
    assert groq, "au moins un modèle Groq exposé"
    for m in groq:
        assert m["litellm_params"]["model"].startswith("groq/"), m["model_name"]
        assert m["litellm_params"]["api_key"] == "os.environ/GROQ_API_KEY"


def test_no_literal_secret_in_config():
    text = CONFIG.read_text(encoding="utf-8")
    for marker in ("sk-", "gsk_", "sk-ant-"):
        assert marker not in text, marker


def test_env_example_declares_new_secrets_empty():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    assert "LITELLM_DB_PASSWORD=" in lines
    assert "GROQ_API_KEY=" in lines


# --- scripts/llm-proxy-keys.sh -----------------------------------------------

pytestmark_script = pytest.mark.skipif(not BASH, reason="bash requis (Git Bash)")

FAKE_KEY = "sk-fakeprojectkey0123456789"


def _write_lf(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _setup(tmp_path: Path, *, key_output: str = FAKE_KEY, env_content: str = "") -> dict:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    _write_lf(shared / ".env", env_content)
    projects = tmp_path / "projects"
    projects.mkdir()
    args_log = tmp_path / "docker-args.log"
    stdin_log = tmp_path / "docker-stdin.log"
    d = fakebin / "docker"
    _write_lf(d, "#!/usr/bin/env bash\n" + textwrap.dedent(f"""\
        echo "$@" >> "{args_log.as_posix()}"
        cat >> "{stdin_log.as_posix()}"
        if [[ "$*" == *"exec -T llm-proxy"* ]]; then
          printf '%s\\n' "{key_output}"
        fi
        exit 0
        """))
    d.chmod(0o755)
    return {
        "fakebin": fakebin, "shared": shared, "projects": projects,
        "args_log": args_log, "stdin_log": stdin_log,
    }


def _run(ctx: dict, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(ctx["fakebin"]) + os.pathsep + env["PATH"]
    env["SHARED_DIR"] = str(ctx["shared"])
    env["PROJECTS_DIR"] = str(ctx["projects"])
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


@pytestmark_script
def test_init_db_generates_password_and_creates_role_and_database(tmp_path):
    ctx = _setup(tmp_path, env_content="POSTGRES_ROOT_PASSWORD=x\n")
    r = _run(ctx, "init-db")
    assert r.returncode == 0, r.stderr
    env_lines = _read(ctx["shared"] / ".env").splitlines()
    pw_line = next(line for line in env_lines if line.startswith("LITELLM_DB_PASSWORD="))
    pw = pw_line.split("=", 1)[1]
    # hex : aucun caractère qui casserait l'URL postgresql://user:pw@host
    assert len(pw) >= 32 and all(c in "0123456789abcdef" for c in pw)
    sql = _read(ctx["stdin_log"])
    assert "CREATE ROLE litellm" in sql
    assert "ALTER ROLE litellm" in sql  # réaligne le mot de passe à chaque passage
    assert "CREATE DATABASE litellm OWNER litellm" in sql
    # Le mot de passe passe par stdin (SQL), jamais par argv (visible dans ps).
    assert pw in sql
    assert pw not in _read(ctx["args_log"])
    assert pw not in r.stdout + r.stderr


@pytestmark_script
def test_init_db_keeps_existing_password(tmp_path):
    ctx = _setup(tmp_path, env_content="LITELLM_DB_PASSWORD=abc123def456abc123def456abc123de\n")
    r = _run(ctx, "init-db")
    assert r.returncode == 0, r.stderr
    env = _read(ctx["shared"] / ".env")
    assert env.count("LITELLM_DB_PASSWORD=") == 1
    assert "LITELLM_DB_PASSWORD=abc123def456abc123def456abc123de" in env


@pytestmark_script
def test_init_db_fills_empty_password_line(tmp_path):
    ctx = _setup(tmp_path, env_content="LITELLM_DB_PASSWORD=\nOTHER=1\n")
    r = _run(ctx, "init-db")
    assert r.returncode == 0, r.stderr
    env = _read(ctx["shared"] / ".env")
    assert env.count("LITELLM_DB_PASSWORD=") == 1
    assert "LITELLM_DB_PASSWORD=\n" not in env
    assert "OTHER=1" in env


@pytestmark_script
def test_create_key_writes_url_and_token_into_project_env_local(tmp_path):
    ctx = _setup(tmp_path)
    proj = ctx["projects"] / "0-hl"
    proj.mkdir()
    _write_lf(proj / ".env.local", "FOO=bar\nLLM_PROXY_TOKEN=sk-oldmasterkey\nBAZ=1\n")
    r = _run(ctx, "create-key", "0-hl", "12", "groq-gpt-oss-120b,groq-gpt-oss-20b")
    assert r.returncode == 0, r.stderr
    lines = _read(proj / ".env.local").splitlines()
    assert "FOO=bar" in lines and "BAZ=1" in lines
    assert f"LLM_PROXY_TOKEN={FAKE_KEY}" in lines
    assert "LLM_PROXY_URL=http://llm-proxy:4000" in lines
    assert sum(1 for line in lines if line.startswith("LLM_PROXY_TOKEN=")) == 1
    assert "sk-oldmasterkey" not in "\n".join(lines)


@pytestmark_script
def test_create_key_never_prints_the_key(tmp_path):
    ctx = _setup(tmp_path)
    (ctx["projects"] / "0-hl").mkdir()
    r = _run(ctx, "create-key", "0-hl", "12", "groq-gpt-oss-120b")
    assert r.returncode == 0, r.stderr
    assert FAKE_KEY not in r.stdout + r.stderr


@pytestmark_script
def test_create_key_passes_budget_alias_and_models_but_never_master_key(tmp_path):
    ctx = _setup(tmp_path, env_content="LITELLM_MASTER_KEY=sk-themasterkey\n")
    (ctx["projects"] / "0-hl").mkdir()
    r = _run(ctx, "create-key", "0-hl", "12", "groq-gpt-oss-120b,groq-gpt-oss-20b")
    assert r.returncode == 0, r.stderr
    args = _read(ctx["args_log"])
    assert "exec -T llm-proxy python - 0-hl 12 1d groq-gpt-oss-120b,groq-gpt-oss-20b" in args
    assert "sk-themasterkey" not in args
    # Le code python lit la clé maître dans l'env DU CONTENEUR.
    code = _read(ctx["stdin_log"])
    assert 'os.environ["LITELLM_MASTER_KEY"]' in code
    assert "/key/generate" in code


@pytestmark_script
def test_create_key_respects_budget_duration_override(tmp_path):
    ctx = _setup(tmp_path)
    (ctx["projects"] / "p").mkdir()
    env = {"BUDGET_DURATION": "30d"}
    os.environ.update(env)
    try:
        r = _run(ctx, "create-key", "p", "20", "claude-haiku-5-5")
    finally:
        os.environ.pop("BUDGET_DURATION")
    assert r.returncode == 0, r.stderr
    assert "python - p 20 30d claude-haiku-5-5" in _read(ctx["args_log"])


@pytestmark_script
def test_create_key_fails_without_project_dir_and_calls_nothing(tmp_path):
    ctx = _setup(tmp_path)
    r = _run(ctx, "create-key", "inexistant", "12", "groq-gpt-oss-120b")
    assert r.returncode != 0
    assert _read(ctx["args_log"]) == ""


@pytestmark_script
@pytest.mark.parametrize("budget", ["abc", "-3", "", "12;rm"])
def test_create_key_rejects_invalid_budget(tmp_path, budget):
    ctx = _setup(tmp_path)
    (ctx["projects"] / "0-hl").mkdir()
    r = _run(ctx, "create-key", "0-hl", budget, "groq-gpt-oss-120b")
    assert r.returncode != 0
    assert _read(ctx["args_log"]) == ""


@pytestmark_script
def test_create_key_requires_at_least_one_model(tmp_path):
    # Un jeton sans liste de modèles aurait accès à TOUT le catalogue
    # (Opus compris) : refusé, l'allowlist est obligatoire.
    ctx = _setup(tmp_path)
    (ctx["projects"] / "0-hl").mkdir()
    r = _run(ctx, "create-key", "0-hl", "12", "")
    assert r.returncode != 0
    assert _read(ctx["args_log"]) == ""


@pytestmark_script
def test_create_key_leaves_env_local_untouched_when_proxy_returns_nothing(tmp_path):
    ctx = _setup(tmp_path, key_output="")
    proj = ctx["projects"] / "0-hl"
    proj.mkdir()
    _write_lf(proj / ".env.local", "LLM_PROXY_TOKEN=sk-previous\n")
    r = _run(ctx, "create-key", "0-hl", "12", "groq-gpt-oss-120b")
    assert r.returncode != 0
    assert _read(proj / ".env.local") == "LLM_PROXY_TOKEN=sk-previous\n"


@pytestmark_script
def test_unknown_command_fails_with_usage(tmp_path):
    ctx = _setup(tmp_path)
    r = _run(ctx, "frobnicate")
    assert r.returncode != 0
    assert "Usage" in r.stderr
