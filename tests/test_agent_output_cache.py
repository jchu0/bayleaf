"""Generic advisory-agent output cache (api/agent_output_cache) — offline.

Covers the reusable helper (generate-once, serve-from-cache, the don't-cache-a-degrade policy) and
that the read endpoints it now backs — node-author proposal, archivist digest, pipeline-repair
proposal — serve the SAME result on a repeat request (cached, not regenerated).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.agent_output_cache import agent_cache_key, cache_through, get_agent_output_cache
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_AGENT_CACHE_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_AGENT_CACHE_PATH", str(tmp_path / "cache.jsonl"))
    # keep every agent on the offline stub
    for env in (
        "BAYLEAF_TRIAGE_AGENT",
        "BAYLEAF_ARCHIVIST_AGENT",
        "BAYLEAF_NODE_AUTHOR_AGENT",
        "BAYLEAF_PIPELINE_REPAIR_AGENT",
    ):
        monkeypatch.delenv(env, raising=False)


class _Out(BaseModel):
    id: str
    generated_by: str
    model: str | None = None


def test_cache_through_generates_once_then_serves() -> None:
    calls = {"n": 0}

    def gen() -> _Out:
        calls["n"] += 1
        return _Out(id=f"out-{calls['n']}", generated_by="stub")

    ki = {"x": 1, "agent": "stub"}
    kw: dict[str, Any] = {
        "namespace": "t",
        "key_inputs": ki,
        "model_cls": _Out,
        "expected_by": "stub",
    }
    a = cache_through(generate=gen, **kw)
    b = cache_through(generate=gen, **kw)
    assert a is not None and b is not None
    assert calls["n"] == 1 and a.id == b.id == "out-1"  # generated once, then served


def test_cache_through_skips_a_degraded_result() -> None:
    """expected_by='claude' but the result is generated_by='stub' (a degrade) → NOT cached."""
    ki = {"x": 2, "agent": "claude"}
    out = cache_through(
        namespace="t",
        key_inputs=ki,
        generate=lambda: _Out(id="degraded", generated_by="stub"),
        model_cls=_Out,
        expected_by="claude",
    )
    assert out is not None and out.generated_by == "stub"  # returned to the caller...
    assert get_agent_output_cache().get(agent_cache_key("t", ki)) is None  # ...but not cached


def test_node_proposal_endpoint_is_cached() -> None:
    a = client.get("/api/builder/node-proposal", params={"request": "fastp"})
    b = client.get("/api/builder/node-proposal", params={"request": "fastp"})
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]  # same proposal — cached, not regenerated


def test_archive_digest_endpoint_is_cached() -> None:
    run = "RUN-2026-06-05-GIAB-A"
    a = client.get(f"/api/runs/{run}/archive-digest")
    b = client.get(f"/api/runs/{run}/archive-digest")
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]  # same digest — cached


def test_repair_endpoint_is_cached() -> None:
    mon = client.get("/api/monitoring").json()
    sigs = mon.get("signatures") or []
    if not sigs:
        pytest.skip("no recurring signatures in the served data")
    sig = sigs[0]["signature"]
    a = client.get(f"/api/monitoring/signatures/{sig}/repair")
    b = client.get(f"/api/monitoring/signatures/{sig}/repair")
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]  # same proposal — cached
