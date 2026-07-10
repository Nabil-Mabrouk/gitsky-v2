"""Task register_fleet (Phase 4, dette — branchement fleet API).

Vérifie le POST vers /api/fleet/projects/register (via httpx MockTransport) et le
skip gracieux sans FLEET_URL.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

TASKS = Path(__file__).resolve().parents[1] / "generator" / "tasks"
sys.path.insert(0, str(TASKS))

import register_fleet as rf  # noqa: E402


def _run_in_tmp(func):
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            func()
            return json.loads((Path(tmp) / ".gitsky" / "fleet.json").read_text("utf-8"))
        finally:
            os.chdir(cwd)


def test_skips_without_fleet_url():
    marker = _run_in_tmp(
        lambda: rf.register("p", "t0", "p.mystudio.com", "1.0.0", fleet_url="")
    )
    assert marker["registered"] == "skipped_no_fleet_url"


def test_posts_to_fleet_register_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    marker = _run_in_tmp(
        lambda: rf.register(
            "pain-scraper",
            "t0",
            "pain-scraper.mystudio.com",
            "1.0.0",
            fleet_url="http://fleet:8000",
            client=client,
        )
    )

    assert marker["registered"] == "ok"
    assert captured["url"].endswith("/api/fleet/projects/register")
    assert captured["payload"] == {
        "name": "pain-scraper",
        "tier": "t0",
        "domain": "pain-scraper.mystudio.com",
        "template_version": "1.0.0",
    }
