"""Tests for the Pipeline Builder save/version seam (ADR-0014) — PRODUCT state, off the gate.

Offline: the JSONL store is a tmp file and the SQLite store a tmp DB; the TestClient drives the
app in-process (no server, no network). Mirrors the feedback-store tests' discipline.
"""

from fastapi.testclient import TestClient

from api.main import app
from api.pipeline_store import (
    JsonlPipelineGraphStore,
    SqlitePipelineGraphStore,
    get_pipeline_store,
)

client = TestClient(app)


def _pipeline_body(**over):
    body = {
        "name": "wgs_germline",
        "schema_version": "builder/0.1",
        # An arbitrary builder payload — stored as-is, never validated node-by-node.
        "graph": {
            "nodes": [{"id": "n1", "type": "align"}, {"id": "n2", "type": "variant"}],
            "edges": [{"from": "n1", "to": "n2"}],
            "run_layout": {"zoom": 1.0},
        },
        "profile": "research",
    }
    body.update(over)
    return body


# --- The JSONL store directly (round-trip + per-name versioning) -----------------------------


def test_pipeline_jsonl_store_roundtrip_and_versioning(tmp_path, monkeypatch):
    path = tmp_path / "p.jsonl"
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(path))
    store = JsonlPipelineGraphStore()

    # An adversarial graph payload: a key with a newline + quote must NOT forge a second JSONL
    # record (json.dumps escapes it), and must round-trip byte-for-byte.
    graph = {"nodes": [{"id": "n1"}], "run_layout": {"weird\nkey": 'v"al'}}
    common = {"created_at": "t", "schema_version": "builder/0.1", "profile": None}
    s1 = store.append({"id": "a1", "name": "p", "graph": graph, **common})
    s2 = store.append({"id": "a2", "name": "p", "graph": {}, **common})
    s3 = store.append({"id": "b1", "name": "q", "graph": {}, **common})

    assert (s1["version"], s2["version"], s3["version"]) == (1, 2, 1)  # monotonic PER name
    assert [r["version"] for r in store.get_versions("p")] == [1, 2]
    assert {r["name"] for r in store.list()} == {"p", "q"}
    assert store.list(name="p") == store.get_versions("p")  # name filter == history for that name
    assert store.get_versions("p")[0]["graph"] == graph  # arbitrary payload round-trips exactly
    assert path.read_text(encoding="utf-8").count("\n") == 3  # three records, no forged line


# --- The save/list/versions endpoints --------------------------------------------------------


def test_save_list_and_versions_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(tmp_path / "p.jsonl"))
    a1 = client.post("/api/pipelines", json=_pipeline_body(name="alpha"))
    assert a1.status_code == 201
    ack = a1.json()
    assert ack["version"] == 1 and ack["status"] == "draft" and ack["id"] and ack["created_at"]
    assert ack["name"] == "alpha" and ack["schema_version"] == "builder/0.1"
    assert "graph" not in ack  # the ack never echoes the payload back (no reflection surface)

    a2 = client.post("/api/pipelines", json=_pipeline_body(name="alpha", graph={"v": 2})).json()
    assert a2["version"] == 2 and a2["id"] != ack["id"]  # server authors a fresh id + next version
    client.post("/api/pipelines", json=_pipeline_body(name="beta"))

    # Catalog = the LATEST version of each distinct name, sorted by name.
    catalog = client.get("/api/pipelines").json()
    assert [(p["name"], p["version"]) for p in catalog] == [("alpha", 2), ("beta", 1)]
    assert next(p for p in catalog if p["name"] == "alpha")["graph"] == {"v": 2}  # latest graph

    # Full version history for one name, ascending by version.
    hist = client.get("/api/pipelines/alpha").json()
    assert [p["version"] for p in hist] == [1, 2]
    assert hist[0]["graph"]["nodes"][0]["type"] == "align"  # v1's full payload round-trips

    assert client.get("/api/pipelines/nope").status_code == 404  # unknown name


def test_saved_graph_reserves_draft_lifecycle_and_rbac_fields(tmp_path, monkeypatch):
    # The builder-versioning decision reserves a draft -> save -> approve flow with reviewer/
    # approver RBAC. A save mints a `draft` with the *_by fields null; the client cannot set them
    # (extra="forbid"), so no identity/PII enters through the body, and they round-trip on read.
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(tmp_path / "p.jsonl"))
    assert client.post("/api/pipelines", json=_pipeline_body(name="wgs")).status_code == 201
    stored = client.get("/api/pipelines/wgs").json()[0]
    assert stored["status"] == "draft"
    assert stored["submitted_by"] is None
    assert stored["reviewed_by"] is None
    assert stored["approved_by"] is None
    # A client cannot smuggle the reserved server-authored fields (extra="forbid").
    assert client.post("/api/pipelines", json=_pipeline_body(status="approved")).status_code == 422
    assert client.post("/api/pipelines", json=_pipeline_body(approved_by="me")).status_code == 422


def test_save_pipeline_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(tmp_path / "p.jsonl"))
    # Smuggled server-authored fields are a hard 422 (extra="forbid"), never silently stored.
    assert client.post("/api/pipelines", json=_pipeline_body(id="deadbeef")).status_code == 422
    assert client.post("/api/pipelines", json=_pipeline_body(version=99)).status_code == 422
    # A path-ish name fails the charset pattern (name doubles as a URL path segment).
    assert client.post("/api/pipelines", json=_pipeline_body(name="../etc")).status_code == 422
    # graph is required and must be a JSON object (tolerant of internals, strict on the envelope).
    body = _pipeline_body()
    del body["graph"]
    assert client.post("/api/pipelines", json=body).status_code == 422
    assert client.post("/api/pipelines", json=_pipeline_body(graph=[1, 2])).status_code == 422


def test_save_pipeline_write_failure_returns_503_without_leak(monkeypatch):
    class _Boom:
        def append(self, _record):
            raise OSError("disk full at /secret/path")

    monkeypatch.setattr("api.main.get_pipeline_store", _Boom)
    resp = client.post("/api/pipelines", json=_pipeline_body())
    assert resp.status_code == 503 and "unavailable" in resp.json()["detail"]
    assert "disk full" not in resp.text and "/secret/path" not in resp.text  # no path/DSN leak


def test_pipeline_does_not_touch_decision_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(tmp_path / "p.jsonl"))
    before = client.get("/api/runs/mock_run_01").json()
    assert client.post("/api/pipelines", json=_pipeline_body()).status_code == 201
    assert client.get("/api/runs/mock_run_01").json() == before  # verdicts/provenance unchanged


# --- The SQLite adapter through the endpoint + the factory selection/degradation --------------


def test_pipeline_sqlite_store_roundtrips_through_the_endpoint(tmp_path, monkeypatch):
    # Route the endpoint's saves into a real (offline, zero-dep) SQLite DB, then read them back
    # through the store — proving "pipeline versions in a database" end to end.
    db = tmp_path / "pipeline_graphs.sqlite"
    monkeypatch.setenv("PIPEGUARD_PIPELINE_STORE", "sqlite")
    monkeypatch.setenv("PIPEGUARD_PIPELINE_DB", str(db))
    assert client.post("/api/pipelines", json=_pipeline_body(name="wgs")).json()["version"] == 1
    assert client.post("/api/pipelines", json=_pipeline_body(name="wgs")).json()["version"] == 2
    rows = SqlitePipelineGraphStore(str(db)).get_versions("wgs")
    assert [r["version"] for r in rows] == [1, 2]
    assert rows[0]["graph"]["nodes"][0]["type"] == "align"  # full payload round-trips


def test_pipeline_store_factory_selects_and_degrades(tmp_path, monkeypatch):
    # Keep the SQLite DB out of the repo.
    monkeypatch.setenv("PIPEGUARD_PIPELINE_DB", str(tmp_path / "p.sqlite"))
    monkeypatch.delenv("PIPEGUARD_PIPELINE_STORE", raising=False)
    assert isinstance(get_pipeline_store(), JsonlPipelineGraphStore)  # default
    monkeypatch.setenv("PIPEGUARD_PIPELINE_STORE", "sqlite")
    assert isinstance(get_pipeline_store(), SqlitePipelineGraphStore)
    # postgres selected but no DATABASE_URL here -> degrade to JSONL, never raise.
    monkeypatch.setenv("PIPEGUARD_PIPELINE_STORE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(get_pipeline_store(), JsonlPipelineGraphStore)
