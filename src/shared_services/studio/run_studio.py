"""CLI du pipeline Studio (Chap 24) — premier point d'entrée exécutable.

Aucun runner n'existait avant : pipeline.run()/save_manifest() n'étaient
appelés que depuis les tests, jamais pour de vrai (LLM_PROXY_URL toujours
absent -> chemin stub uniquement).

Usage (depuis shared_services/, ou via le Dockerfile de ce dossier) :
    python -m studio.run_studio --project politique-ia \
        --idea "..." --audience "..." --vertical "..." \
        --domain politique-ia.0-hitl.com --out-dir /out

Écrit dans --out-dir :
  - manifests/<project>.yaml   (Creative Manifest, versionné — manifest.py)
  - runs/<run_id>.yaml         (trace immuable — pipeline.py)
  - <project>-config.yaml      (prêt pour `copier copy --data-file`)

Échec des guardrails = arrêt net (exit 1), rien n'est écrit au-delà de la
trace — jamais de déploiement silencieux sur un manifest qui ne les passe
pas (Chap 24 : « l'agent QA valide avant tout déploiement »).
"""

import argparse
import sys
from pathlib import Path

import yaml

from studio.inputs import HarvestPacket
from studio.manifest import save_manifest, to_copier_data
from studio.pipeline import run, save_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--idea", required=True, help="idea_oneliner")
    parser.add_argument("--audience", default="")
    parser.add_argument("--vertical", default="")
    parser.add_argument("--target-lang", default="fr")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--tier", default="t0", choices=["t0", "t1", "t2"])
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    packet = HarvestPacket(
        project=args.project,
        idea_oneliner=args.idea,
        audience=args.audience,
        vertical=args.vertical,
        target_lang=args.target_lang,
        tier=args.tier,
    )

    print(f"Studio : lancement du pipeline pour « {args.project} »...")
    result = run(packet)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_path = save_run(result, args.out_dir)
    print(f"Trace persistée : {run_path}")

    if not result.verdict["pass"]:
        print("ÉCHEC des guardrails — rien de généré, rien à déployer :", file=sys.stderr)
        for f in result.verdict["failures"]:
            print(f"  - {f}", file=sys.stderr)
        return 1

    manifest_path = save_manifest(result.manifest, args.out_dir)
    print(f"Manifest persisté : {manifest_path}")

    config = {
        "project": {"name": args.project, "tier": args.tier, "domain": args.domain},
        "fleet": {"register": True},
        **to_copier_data(result.manifest),
    }
    config_path = args.out_dir / f"{args.project}-config.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"Config copier prête : {config_path}")

    print("\nBrief retenu :")
    print(f"  skin  : {result.manifest.brief.skin}")
    print(f"  ton   : {result.manifest.brief.tone}")
    print(f"  blocs : {[b.type for b in result.manifest.blocks]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
