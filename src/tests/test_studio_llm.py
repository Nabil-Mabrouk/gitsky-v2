"""Parsing de la réponse LLM réelle (Chap 24) — client OpenAI-compatible.

Le premier run réel contre l'API Anthropic (via llm-proxy) a montré que le
modèle enveloppe parfois sa réponse dans un bloc markdown ```json malgré
response_format=json_object (Anthropic n'a pas de mode JSON natif comme
OpenAI). `generate()` doit tolérer ça, mais rester fail-closed sur du texte
qui n'est vraiment pas du JSON.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "shared_services"))

from studio.llm import generate  # noqa: E402


class _FakeChat:
    def __init__(self, content):
        completions = SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )
        )
        self.completions = completions


def _install_fake_openai(monkeypatch, content):
    import openai

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = _FakeChat(content)

    monkeypatch.setattr(openai, "OpenAI", FakeClient)


def test_generate_parses_plain_json(monkeypatch):
    monkeypatch.setenv("LLM_PROXY_URL", "http://llm-proxy:4000")
    _install_fake_openai(monkeypatch, '{"ok": true}')
    assert generate("m", "prompt", stub=lambda: {"stub": True}) == {"ok": True}


def test_generate_strips_markdown_json_fence(monkeypatch):
    monkeypatch.setenv("LLM_PROXY_URL", "http://llm-proxy:4000")
    _install_fake_openai(monkeypatch, '```json\n{"ok": true}\n```')
    assert generate("m", "prompt", stub=lambda: {"stub": True}) == {"ok": True}


def test_generate_strips_bare_markdown_fence_without_language_tag(monkeypatch):
    monkeypatch.setenv("LLM_PROXY_URL", "http://llm-proxy:4000")
    _install_fake_openai(monkeypatch, '```\n{"ok": true}\n```')
    assert generate("m", "prompt", stub=lambda: {"stub": True}) == {"ok": True}


def test_generate_raises_clear_error_on_non_json(monkeypatch):
    monkeypatch.setenv("LLM_PROXY_URL", "http://llm-proxy:4000")
    _install_fake_openai(monkeypatch, "Je ne peux pas répondre en JSON.")
    with pytest.raises(RuntimeError, match="non-JSON"):
        generate("m", "prompt", stub=lambda: {"stub": True})
