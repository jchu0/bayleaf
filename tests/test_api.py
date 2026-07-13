"""Tests for the FastAPI read-API — the production seam over the core.

Offline: TestClient drives the app in-process (no server, no network).
"""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from api.deid import DeidAction, DeidPolicy, _pseudonymize, default_policy, export_fields, redact
from api.feedback_agent import StubFeedbackAgent, assess_feedback
from api.feedback_store import JsonlFeedbackStore, SqliteFeedbackStore, get_feedback_store
from api.main import app

client = TestClient(app)


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_runs_returns_mock_run():
    runs = client.get("/api/runs").json()
    mr = next(r for r in runs if r["run_id"] == "mock_run_01")
    assert mr["n_samples"] == 5
    assert mr["n_attention"] == 2
    assert mr["counts"] == {"proceed": 3, "hold": 1, "rerun": 0, "escalate": 1}


def test_run_summary_surfaces_platform_date_and_lifecycle_status():
    """The summary carries the sample sheet's [Header] platform/date and an honest
    lifecycle status. mock_run_01 completes with actionable samples -> needs_review
    (NOT inferred from n_attention alone — a completed run with flags)."""
    mr = next(r for r in client.get("/api/runs").json() if r["run_id"] == "mock_run_01")
    assert mr["platform"] == "NovaSeq"
    assert mr["run_date"] == "2026-07-07"  # raw ISO string from the [Header] block
    # mock_run_01 has n_attention == 2 and a completed gate, so it needs review.
    assert mr["status"] == "needs_review"
    # The same status rides the run-detail summary (single source: _evaluate).
    assert client.get("/api/runs/mock_run_01").json()["summary"]["status"] == "needs_review"


def test_run_status_tri_state_is_honest_about_lifecycle():
    """The lifecycle label is a pure function of (completed, n_attention): a run with no
    ANALYSIS_RUN_COMPLETED event is 'running' even at zero attention — the exact case the
    old n_attention==0 => 'Released' inference mislabeled."""
    from api.main import _run_status

    # Not yet completed: 'running' regardless of the (interim) attention count.
    assert _run_status(completed=False, n_attention=0) == "running"
    assert _run_status(completed=False, n_attention=3) == "running"
    # Completed: attention decides between needs_review and released.
    assert _run_status(completed=True, n_attention=2) == "needs_review"
    assert _run_status(completed=True, n_attention=0) == "released"


def test_run_detail_serializes_cards_events_and_computed_fields():
    d = client.get("/api/runs/mock_run_01").json()
    assert len(d["cards"]) == 5
    assert len(d["events"]) == 16  # the full provenance trail
    s4 = next(c for c in d["cards"] if c["sample_id"] == "S4")
    assert s4["verdict"] == "escalate"
    assert s4["confidence"] is None  # T-019: omitted until grounded
    assert s4["content_hash"]  # computed field serializes
    assert any(g["gate"] == "preflight" for g in s4["gate_results"])  # corrected gate
    # Registry-normalized QC metrics flow through the response model (T-025 step 4).
    s5 = next(c for c in d["cards"] if c["sample_id"] == "S5")
    q30 = next(m for m in s5["metric_values"] if m["metric_key"] == "qc.q30")
    assert q30["normalized_value"] == 0.841 and q30["canonical_unit"] == "fraction"


def test_card_endpoint_and_404s():
    assert client.get("/api/runs/mock_run_01/cards/S4").json()["verdict"] == "escalate"
    assert client.get("/api/runs/mock_run_01/cards/NOPE").status_code == 404
    assert client.get("/api/runs/NOPE").status_code == 404


def test_artifacts_endpoint_maps_stages_with_real_hash_and_origin():
    arts = client.get("/api/runs/mock_run_01/artifacts").json()
    # A file can sit on more than one (stage, role) edge, so index by (name, stage, role).
    edges = {(a["name"], a["stage"], a["role"]) for a in arts}
    by_name = {a["name"]: a for a in arts}
    # The metadata artifacts map to their pipeline stages (SampleSheet is the demux barcode
    # manifest the preflight gate consumes, not an intake input)...
    assert ("SampleSheet.csv", "demux", "input") in edges
    assert ("sample_metadata.csv", "intake", "input") in edges
    assert ("qc_metrics.csv", "qc", "output") in edges
    # demux_stats is demux's OUTPUT and also the QC stage's INPUT (the two-edge case that gives
    # the QC node a real input instead of rendering orphaned).
    assert ("demux_stats.csv", "demux", "output") in edges
    assert ("demux_stats.csv", "qc", "input") in edges
    # ...each carries the run's origin tag, a real (small-file) sha256 + byte size, and a
    # same-origin download url.
    sheet = by_name["SampleSheet.csv"]
    assert sheet["origin"] == "contrived"
    assert len(sheet["sha256"]) == 64 and sheet["size_bytes"] > 0
    assert sheet["url"] == "/api/runs/mock_run_01/artifacts/SampleSheet.csv"
    # The origin marker itself is never surfaced as a data artifact.
    assert "origin" not in by_name
    assert client.get("/api/runs/NOPE/artifacts").status_code == 404


def test_artifact_download_serves_file_and_blocks_traversal():
    # A real artifact serves its bytes INLINE by default (click-to-view), attachment on ?download=1.
    ok = client.get("/api/runs/mock_run_01/artifacts/SampleSheet.csv")
    assert ok.status_code == 200 and len(ok.content) > 0
    assert "inline" in ok.headers.get("content-disposition", "")
    dl = client.get("/api/runs/mock_run_01/artifacts/SampleSheet.csv?download=1")
    assert dl.status_code == 200 and "attachment" in dl.headers.get("content-disposition", "")
    # ...a bogus name / unknown run 404s...
    assert client.get("/api/runs/mock_run_01/artifacts/nope.csv").status_code == 404
    assert client.get("/api/runs/NOPE/artifacts/SampleSheet.csv").status_code == 404
    # ...and a path-traversal name never escapes the run dir (encoded or raw).
    assert client.get("/api/runs/mock_run_01/artifacts/..%2f..%2fpyproject.toml").status_code == 404
    assert client.get("/api/runs/mock_run_01/artifacts/origin").status_code == 404


def test_downstream_artifact_stage_seams():
    """W3 post-variant lineage seams: a filtered/normalized VCF, a flag-for-review routing record,
    and a share manifest each land on their own downstream stage, while the raw caller VCF stays on
    'variant' and the flag-for-review ARMING marker stays config (never a data artifact)."""
    from api.main import _artifact_stage_roles

    # A filtered/normalized VCF is the filter stage's output — matched BEFORE the generic .vcf rule.
    assert _artifact_stage_roles("HG002.filtered.vcf.gz") == [("filter", "output")]
    assert _artifact_stage_roles("HG002.norm.vcf") == [("filter", "output")]
    # ...but the raw caller output still lands on 'variant' (unchanged).
    assert _artifact_stage_roles("HG002.vcf.gz") == [("variant", "output")]
    # Flag-for-review routing record + de-identified share manifest → their own stages.
    assert _artifact_stage_roles("flag_for_review.json") == [("review", "output")]
    assert _artifact_stage_roles("share_manifest.json") == [("share", "output")]
    # The per-run flag_for_review ARMING marker (config, no extension) is NOT a data artifact.
    assert _artifact_stage_roles("flag_for_review") == []


# --- In-app feedback (W12): the one write endpoint, off the deterministic gate -------------


def _decision_body(**over):
    body = {
        "target": "decision",
        "source": "decision-card",
        "signal": "disagree",
        "reason_code": "threshold_too_strict",
        "context": {
            "run_id": "mock_run_01",
            "sample_id": "S4",
            "verdict": "escalate",
            "gate": "qc",
            "rule_ids": ["QC-Q30"],
            "card_content_hash": "abc123def",
            "route": "/runs/mock_run_01",
            "screen": "Decision cards",
        },
    }
    body.update(over)
    return body


def _read_feedback(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_feedback_decision_target_records_and_acks(tmp_path, monkeypatch):
    store = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(store))
    resp = client.post("/api/feedback", json=_decision_body(message="  disagree with this call  "))
    assert resp.status_code == 201
    ack = resp.json()
    assert (
        ack["status"] == "recorded"
        and ack["schema_version"] == 1
        and ack["id"]
        and ack["received_at"]
    )
    # The ack never echoes the submitted message back (no reflection surface).
    assert "message" not in ack
    rows = _read_feedback(store)
    assert len(rows) == 1
    rec = rows[0]
    assert (
        rec["id"] == ack["id"] and rec["schema_version"] == 1 and rec["app_version"] == app.version
    )
    assert rec["origin"] == "contrived"  # server-resolved from mock_run_01's origin marker
    assert rec["target"] == "decision" and rec["signal"] == "disagree"
    assert rec["message"] == "disagree with this call"  # whitespace-stripped
    assert rec["context"]["sample_id"] == "S4" and rec["context"]["verdict"] == "escalate"


def test_feedback_product_target_strips_message_and_defaults_origin_unknown(tmp_path, monkeypatch):
    store = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(store))
    resp = client.post(
        "/api/feedback",
        json={
            "target": "product",
            "source": "product-fab",
            "kind": "confusing",
            "message": "  Provenance DAG unclear  ",
            "context": {"screen": "Provenance"},
        },
    )
    assert resp.status_code == 201
    rec = _read_feedback(store)[0]
    assert rec["message"] == "Provenance DAG unclear" and rec["origin"] == "unknown"
    assert rec["source"] == "product-fab"  # the originating surface is traced


def test_feedback_cross_field_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(tmp_path / "f.jsonl"))
    # decision with no signal
    assert (
        client.post(
            "/api/feedback",
            json={
                "target": "decision",
                "source": "decision-card",
                "context": {"run_id": "mock_run_01", "sample_id": "S4", "verdict": "escalate"},
            },
        ).status_code
        == 422
    )
    # decision missing the verdict snapshot
    assert (
        client.post(
            "/api/feedback",
            json=_decision_body(context={"run_id": "mock_run_01", "sample_id": "S4"}),
        ).status_code
        == 422
    )
    # product with no kind
    assert (
        client.post(
            "/api/feedback", json={"target": "product", "source": "product-fab", "message": "hi"}
        ).status_code
        == 422
    )
    # product carrying a decision signal
    assert (
        client.post(
            "/api/feedback",
            json={"target": "product", "source": "product-fab", "kind": "idea", "signal": "agree"},
        ).status_code
        == 422
    )


def test_feedback_enum_and_bounds_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(tmp_path / "f.jsonl"))
    assert (
        client.post("/api/feedback", json={"target": "bogus", "source": "product-fab"}).status_code
        == 422
    )
    assert (
        client.post("/api/feedback", json=_decision_body(source="nowhere")).status_code == 422
    )  # bad source
    assert client.post("/api/feedback", json=_decision_body(signal="maybe")).status_code == 422
    assert client.post("/api/feedback", json=_decision_body(message="x" * 2001)).status_code == 422
    # a path-ish run_id fails the charset pattern
    assert (
        client.post(
            "/api/feedback",
            json=_decision_body(
                context={"run_id": "../etc", "sample_id": "S4", "verdict": "escalate"}
            ),
        ).status_code
        == 422
    )


def test_feedback_forbids_extra_fields_as_pii_guard(tmp_path, monkeypatch):
    store = tmp_path / "f.jsonl"
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(store))
    assert (
        client.post("/api/feedback", json=_decision_body(email="a@b.com")).status_code == 422
    )  # smuggled identity
    assert (
        client.post("/api/feedback", json=_decision_body(id="deadbeef")).status_code == 422
    )  # client-set server field
    assert (
        client.post(  # extra inside context
            "/api/feedback",
            json=_decision_body(
                context={
                    "run_id": "mock_run_01",
                    "sample_id": "S4",
                    "verdict": "escalate",
                    "subject_id": "P123",
                }
            ),
        ).status_code
        == 422
    )
    assert not store.exists() or _read_feedback(store) == []  # nothing appended on a rejected write


def test_feedback_message_stays_one_jsonl_line(tmp_path, monkeypatch):
    store = tmp_path / "f.jsonl"
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(store))
    nasty = 'line1\nline2 "quoted"\ttab'
    assert client.post("/api/feedback", json=_decision_body(message=nasty)).status_code == 201
    assert store.read_text(encoding="utf-8").count("\n") == 1  # exactly one physical record
    assert _read_feedback(store)[0]["message"] == nasty.strip()  # escaping round-trips


def test_feedback_write_failure_returns_503_without_leak(monkeypatch):
    class _Boom:
        def append(self, _record):
            raise OSError("disk full at /secret/path")

    monkeypatch.setattr("api.main.get_feedback_store", _Boom)
    resp = client.post("/api/feedback", json=_decision_body())
    assert resp.status_code == 503 and "unavailable" in resp.json()["detail"]
    assert "disk full" not in resp.text and "/secret/path" not in resp.text


def test_feedback_cors_allows_post_from_dev_origin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(tmp_path / "f.jsonl"))
    ok = client.options(
        "/api/feedback",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert "POST" in ok.headers.get("access-control-allow-methods", "")
    evil = client.options(
        "/api/feedback",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert evil.headers.get("access-control-allow-origin") != "http://evil.example"


def test_feedback_does_not_touch_decision_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_FEEDBACK_PATH", str(tmp_path / "f.jsonl"))
    before = client.get("/api/runs/mock_run_01").json()
    assert client.post("/api/feedback", json=_decision_body()).status_code == 201
    assert client.get("/api/runs/mock_run_01").json() == before  # verdicts/provenance unchanged


def test_feedback_sqlite_store_roundtrips_through_the_endpoint(tmp_path, monkeypatch):
    # Route the endpoint's telemetry into a real (offline, zero-dep) SQLite DB, then read it
    # back through the store's read_all — proving "feedback in a database" end to end.
    db = tmp_path / "feedback.sqlite"
    monkeypatch.setenv("BAYLEAF_FEEDBACK_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_FEEDBACK_DB", str(db))
    assert (
        client.post("/api/feedback", json=_decision_body(message="into the DB")).status_code == 201
    )
    assert (
        client.post(
            "/api/feedback",
            json={"target": "product", "source": "product-fab", "kind": "idea", "message": "hi DB"},
        ).status_code
        == 201
    )
    rows = SqliteFeedbackStore(str(db)).read_all()
    assert len(rows) == 2
    by_target = {r["target"]: r for r in rows}
    assert by_target["decision"]["message"] == "into the DB"
    assert by_target["decision"]["context"]["sample_id"] == "S4"  # full record round-trips
    assert by_target["product"]["source"] == "product-fab"


def test_feedback_store_factory_selects_and_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_FEEDBACK_DB", str(tmp_path / "f.sqlite"))  # keep it out of the repo
    monkeypatch.delenv("BAYLEAF_FEEDBACK_STORE", raising=False)
    assert isinstance(get_feedback_store(), JsonlFeedbackStore)  # default
    monkeypatch.setenv("BAYLEAF_FEEDBACK_STORE", "sqlite")
    assert isinstance(get_feedback_store(), SqliteFeedbackStore)
    # postgres selected but no psycopg/DATABASE_URL here -> degrade to JSONL, never raise.
    monkeypatch.setenv("BAYLEAF_FEEDBACK_STORE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(get_feedback_store(), JsonlFeedbackStore)


def test_feedback_agent_categorizes_structurally():
    # The advisory feedback agent (#3b): deterministic categorization from the structured fields,
    # off the gate. Two threshold downvotes on the QC gate + a bug + praise.
    recs = [
        {"id": "a", "target": "decision", "source": "decision-card", "signal": "disagree",
         "reason_code": "threshold_too_strict", "context": {"gate": "qc", "verdict": "escalate"}},
        {"id": "b", "target": "decision", "source": "decision-card", "signal": "disagree",
         "reason_code": "threshold_too_strict", "context": {"gate": "qc", "verdict": "hold"}},
        {"id": "c", "target": "product", "source": "product-fab", "kind": "problem",
         "context": {"screen": "Provenance"}},
        {"id": "d", "target": "product", "source": "product-fab", "kind": "praise",
         "context": {"screen": "Runs"}},
    ]  # fmt: skip
    a = assess_feedback(recs, agent=StubFeedbackAgent())
    assert a.advisory is True and a.generated_by == "stub" and a.n_total == 4
    assert a.by_category["threshold_tuning"] == 2 and a.by_category["bug"] == 1
    assert a.by_priority["high"] >= 2  # disagree-on-escalate + the bug
    assert a.by_sentiment["positive"] == 1  # the praise
    assert any("threshold_tuning on qc gate" in t for t in a.themes)  # recurrence surfaced
    # Advisory only — the assessment carries no verdict/priority that could feed a decision.
    assert "verdict" not in a.model_dump()


def test_runbook_endpoint_exposes_thresholds():
    body = client.get("/api/runbook").json()
    # Life-science guardrail: the policy must read as illustrative, never clinical.
    assert "NOT clinical" in body["disclaimer"]
    # Units contract surfaced so an integrator can't render a canonical 0.85 as "0.85%".
    assert "canonical unit" in body["units_note"]
    assert body["run_id_field"] == "run_id"
    assert body["required_metadata_fields"] == [
        "subject_id",
        "tissue",
        "library_prep",
        "submitted_by",
    ]
    # A known threshold flows through with its canonical-unit gate + direction.
    q30 = next(t for t in body["thresholds"] if t["our_key"] == "qc.q30")
    assert q30["metric"] == "q30"
    assert q30["gate"] == 0.85 and q30["hard_fail"] == 0.75
    assert q30["unit"] == "%" and q30["direction"] == "higher_is_better"
    # A lower-is-better metric reports the flipped comparison sense.
    dup = next(t for t in body["thresholds"] if t["our_key"] == "qc.duplication")
    assert dup["direction"] == "lower_is_better"


def test_metric_catalog_lists_registered_metrics_and_gated_flag():
    body = client.get("/api/metrics/registry").json()
    # Life-science guardrail: the catalog reads as illustrative vocabulary, never clinical.
    assert "NOT clinical" in body["disclaimer"]
    assert body["metric_registry_version"] == 1
    # Every registered metric type is listed (the extensibility story lives here).
    assert body["n_registered"] == 21
    assert len(body["entries"]) == 21
    # Thirteen runbook keys are gated: the five required frozen-CSV metrics + eight optional
    # (non-blocking) checks that score a richer run without NA-flagging a lean one — five one-sided
    # plus variant.titv (the first BOTH-TAILS target_band gate, WS-06 Gap 2) plus
    # contamination.freemix (WS-02) plus concordance.snp_f1 (WS-04), both optional ingest-adapter
    # metrics. The rest stay registered-but-ungated vocabulary the gate can still adopt.
    assert body["n_gated"] == 13
    gated = {e["our_key"] for e in body["entries"] if e["gated"]}
    assert gated == {
        # required (frozen-CSV)
        "qc.q30",
        "qc.reads_passing_filter",
        "qc.mean_target_coverage",
        "qc.cluster_pf",
        "qc.duplication",
        # optional (present-but-failing gates; missing is fine)
        "qc.breadth_20x",
        "qc.breadth_30x",
        "qc.pct_mapped",
        "qc.on_target",
        "variant.dp",
        "variant.titv",  # WS-06 Gap 2: both-tails target_band gate
        "contamination.freemix",  # WS-02: optional verifybamid2 contamination gate
        "concordance.snp_f1",  # WS-04: optional hap.py GIAB SNP-F1 concordance gate
    }
    assert sum(1 for e in body["entries"] if not e["gated"]) == 8
    # Each entry carries the flattened vocabulary fields the settings catalog renders.
    q30 = next(e for e in body["entries"] if e["our_key"] == "qc.q30")
    assert q30["gated"] is True and q30["gate"] == "qc"
    assert {
        "our_key",
        "display_name",
        "category",
        "canonical_unit",
        "direction",
        "gate",
        "source_module",
        "aliases",
    } <= q30.keys()
    # A registered-but-ungated entry reports the flag as false (not absent).
    ungated = next(e for e in body["entries"] if not e["gated"])
    assert ungated["gated"] is False


def test_metrics_prometheus_exposition():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = resp.text
    assert body.endswith("\n")
    lines = body.splitlines()  # anchor to whole lines so "... 3" can't match "... 30"
    # Well-formed exposition: every metric family declares HELP + TYPE before its series.
    for name in (
        "bayleaf_runs_total",
        "bayleaf_samples_total",
        "bayleaf_cards_total",
        "bayleaf_gate_flagged_samples_total",
    ):
        assert any(ln.startswith(f"# HELP {name} ") for ln in lines), name
        assert f"# TYPE {name} counter" in lines, name
    # Cross-path consistency instead of magic pins: the exposition must AGREE with the /api/runs
    # summary aggregates — a genuinely separate code path (per-run `_evaluate` vs the
    # `_aggregate_metrics` roll-up). This is fixture-count-independent, so committing a new run
    # (e.g. the scale-30 fixture) can't silently falsify a hardcoded census (Doc map row 130).
    summaries = client.get("/api/runs").json()
    n_runs = len(summaries)
    n_samples = sum(s["n_samples"] for s in summaries)
    assert f"bayleaf_runs_total {n_runs}" in lines
    assert f"bayleaf_samples_total {n_samples}" in lines
    # Per-verdict totals == the summed per-run counts; every verdict series stays present.
    verdicts = {"proceed": 0, "hold": 0, "rerun": 0, "escalate": 0}
    for s in summaries:
        for v in verdicts:
            verdicts[v] += s["counts"].get(v, 0)
    for v, n in verdicts.items():
        assert f'bayleaf_cards_total{{verdict="{v}"}} {n}' in lines
    assert sum(verdicts.values()) == n_samples  # samples == sum of verdicts, whatever the fixtures
    # Per-gate flagged-sample series: present + a non-negative integer, variant always
    # present-and-≥0 for series stability. Exact counts are data-driven — assert the shape.
    for gate in ("preflight", "qc", "variant"):
        prefix = f'bayleaf_gate_flagged_samples_total{{gate="{gate}"}} '
        series = next((ln for ln in lines if ln.startswith(prefix)), None)
        assert series is not None, gate
        assert int(series.rsplit(" ", 1)[1]) >= 0


def test_export_decision_csv():
    resp = client.get(
        "/api/export", params={"format": "csv", "grain": "decision", "run_id": "mock_run_01"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    # Honesty label: a live recompute, not audit provenance (design doc G-EXPORT-SOURCE).
    assert resp.headers["x-bayleaf-export-source"] == "live-recompute"
    rows = _parse_csv(resp.text)
    assert len(rows) == 5  # five samples in mock_run_01
    assert resp.headers["x-bayleaf-row-count"] == "5"
    # Operator PII is never a column (D10); origin always is (D11).
    assert "submitted_by" not in rows[0]
    assert "origin" in rows[0]
    s4 = next(r for r in rows if r["sample_id"] == "S4")
    assert s4["verdict"] == "escalate" and s4["run_id"] == "mock_run_01"


def test_export_feature_jsonl_is_the_ml_corpus():
    resp = client.get(
        "/api/export", params={"format": "jsonl", "grain": "feature", "run_id": "mock_run_01"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    recs = [json.loads(ln) for ln in resp.text.splitlines() if ln]
    assert int(resp.headers["x-bayleaf-row-count"]) == len(recs)
    # ADR-0007 self-containment: canonical_unit + registry version ride each row.
    assert {
        "metric_key",
        "normalized_value",
        "canonical_unit",
        "metric_registry_version",
        "origin",
    } <= recs[0].keys()
    # A known registry-normalized value (S5 Q30 = 0.841 fraction) is present.
    q30 = next(r for r in recs if r["sample_id"] == "S5" and r["metric_key"] == "qc.q30")
    assert q30["normalized_value"] == 0.841 and q30["canonical_unit"] == "fraction"


def test_export_verdict_filter():
    rows = _parse_csv(
        client.get("/api/export", params={"grain": "decision", "verdict": "escalate"}).text
    )
    assert rows  # at least mock_run_01/S4
    assert {r["verdict"] for r in rows} == {"escalate"}


def test_export_validation_and_404():
    assert client.get("/api/export", params={"format": "xml"}).status_code == 400
    assert client.get("/api/export", params={"grain": "bogus"}).status_code == 400
    assert client.get("/api/export", params={"verdict": "maybe"}).status_code == 400
    assert client.get("/api/export", params={"run_id": "NOPE"}).status_code == 404


def test_export_feature_parquet_roundtrips():
    pq = pytest.importorskip("pyarrow.parquet")  # skip if the optional 'parquet' extra is absent
    resp = client.get(
        "/api/export", params={"format": "parquet", "grain": "feature", "run_id": "mock_run_01"}
    )
    assert resp.status_code == 200
    assert "parquet" in resp.headers["content-type"]
    assert resp.headers["content-disposition"].rstrip('"').endswith(".parquet")
    # Round-trip the columnar bytes: schema + row count + a known column survive.
    table = pq.read_table(io.BytesIO(resp.content))
    assert int(resp.headers["x-bayleaf-row-count"]) == table.num_rows
    assert {"metric_key", "normalized_value", "canonical_unit", "origin"} <= set(table.column_names)


# --- De-identification policy at the export seam (T-040 / W14) --------------------------------
# Demo de-id SEAM, NOT HIPAA de-identification: hashing here is salted pseudonymization, a
# non-reversible heuristic — the tests assert the *field-class behavior*, not any compliance.


def test_deid_pseudonymize_is_stable_salted_and_non_reversible():
    # Stable: same (salt, value) → same token, so a cohort key joins across rows/files.
    assert _pseudonymize("SUBJ-1001", "s") == _pseudonymize("SUBJ-1001", "s")
    # Non-reversible + not the raw value: the plaintext never appears in the token.
    tok = _pseudonymize("SUBJ-1001", "s")
    assert tok.startswith("pseudo_") and "SUBJ-1001" not in tok
    # Salted: a different salt yields a different pseudonym for the same value.
    assert _pseudonymize("SUBJ-1001", "s") != _pseudonymize("SUBJ-1001", "other-salt")
    # Distinct values yield distinct tokens (no accidental collapse).
    assert _pseudonymize("SUBJ-1001", "s") != _pseudonymize("SUBJ-1002", "s")


def test_deid_redact_field_classes():
    policy = DeidPolicy(
        field_actions={
            "submitted_by": DeidAction.DROP,
            "subject_id": DeidAction.GATE_BY_ORIGIN,
            "tissue": DeidAction.GATE_BY_ORIGIN,
        },
        salt="test-salt",
    )
    row = {"run_id": "r", "subject_id": "SUBJ-1001", "tissue": "blood", "submitted_by": "a.rivera"}

    # DROP removes operator PII entirely (the key is gone, not blanked).
    non_real = redact(row, "synthetic", policy)
    assert "submitted_by" not in non_real
    # PASSTHROUGH leaves operational fields untouched.
    assert non_real["run_id"] == "r"
    # GATE_BY_ORIGIN on a non-real origin emits a hashed cohort key (never raw).
    assert non_real["subject_id"] == _pseudonymize("SUBJ-1001", "test-salt")
    assert non_real["subject_id"] != "SUBJ-1001" and non_real["tissue"] != "blood"

    # GATE_BY_ORIGIN on a PHI-guarded origin drops the cohort keys outright.
    real = redact(row, "real-giab", policy)
    assert "subject_id" not in real and "tissue" not in real
    assert "submitted_by" not in real  # still dropped
    # Untagged `unknown` is guarded conservatively — cohort keys withheld there too.
    assert "subject_id" not in redact(row, "unknown", policy)


def test_deid_default_policy_and_export_fields():
    policy = default_policy()
    assert policy.action_for("submitted_by") is DeidAction.DROP
    assert policy.action_for("subject_id") is DeidAction.GATE_BY_ORIGIN
    assert policy.action_for("origin") is DeidAction.PASSTHROUGH  # unnamed → passthrough
    # The identity header carries the gated cohort keys but never the DROP'd operator PII.
    fields = export_fields(["run_id", "origin"], ["subject_id", "tissue", "submitted_by"], policy)
    assert fields == ["run_id", "origin", "subject_id", "tissue"]


def test_export_default_omits_all_identity_columns():
    # Without include=identity the export is unchanged: no cohort keys, no operator PII.
    resp = client.get("/api/export", params={"grain": "decision", "run_id": "mock_run_01"})
    assert resp.status_code == 200
    assert resp.headers["x-bayleaf-deid-policy"] == "demo-deid-v1"
    rows = _parse_csv(resp.text)
    for col in ("submitted_by", "subject_id", "tissue"):
        assert col not in rows[0]


def test_export_identity_mode_gates_and_hashes_cohort_keys():
    # mock_run_01 origin = contrived (non-real) → cohort keys are exported, but hashed.
    resp = client.get(
        "/api/export",
        params={"grain": "decision", "run_id": "mock_run_01", "include": "identity"},
    )
    assert resp.status_code == 200
    rows = _parse_csv(resp.text)
    # Cohort-key columns are present; operator PII is still never a column (DROP).
    assert "subject_id" in rows[0] and "tissue" in rows[0]
    assert "submitted_by" not in rows[0]
    salt = default_policy().salt
    s1 = next(r for r in rows if r["sample_id"] == "S1")
    # S1 subject SUBJ-1001 → pseudonymized, never raw; tissue likewise.
    assert s1["subject_id"] == _pseudonymize("SUBJ-1001", salt)
    assert "SUBJ-1001" not in resp.text and "a.rivera" not in resp.text
    assert s1["tissue"] == _pseudonymize("blood", salt)
    # Missing metadata stays a signal, not a crash: S4 has no subject_id → empty cell.
    s4 = next(r for r in rows if r["sample_id"] == "S4")
    assert s4["subject_id"] == ""
    # Rules decide, de-id only shapes export: the verdict is byte-for-byte untouched.
    assert s4["verdict"] == "escalate"


def test_export_identity_mode_feature_grain_and_validation():
    # Identity join also rides the feature (ML-corpus) grain, hashed + origin-gated.
    resp = client.get(
        "/api/export",
        params={
            "format": "jsonl",
            "grain": "feature",
            "run_id": "mock_run_01",
            "include": "identity",
        },
    )
    assert resp.status_code == 200
    recs = [json.loads(ln) for ln in resp.text.splitlines() if ln]
    assert "subject_id" in recs[0] and "submitted_by" not in recs[0]
    assert "SUBJ-1001" not in resp.text
    # An unknown include mode is a 400 (closed vocabulary).
    assert client.get("/api/export", params={"include": "everything"}).status_code == 400


# --- Run-list filter / sort / paginate (the run-overview + monitoring screens) ----------------


# These tests anchor on the known per-run fixtures (mock_run_01/02/03) and use relative /
# internal-consistency checks for fleet totals, so they stay green whether or not extra run
# fixtures (e.g. a scale run) are present in data/ — mirroring test_list_runs_returns_mock_run.


def test_list_runs_no_params_is_backward_compatible():
    # The byte-identical contract: no params → every run in run_id (sorted) order, unpaginated.
    resp = client.get("/api/runs")
    runs = resp.json()
    ids = [r["run_id"] for r in runs]
    assert ids == sorted(ids)  # same order _run_ids() has always returned
    assert {"mock_run_01", "mock_run_02", "mock_run_03"} <= set(ids)
    # The pre-pagination total rides a header so the body stays a plain list; the page/limit
    # headers appear only when paginating.
    assert resp.headers["x-bayleaf-total-count"] == str(len(runs))
    assert "x-bayleaf-page" not in resp.headers and "x-bayleaf-limit" not in resp.headers


def test_list_runs_q_and_verdict_filters_mirror_export_idiom():
    # q = run_id substring (same idiom as /api/export).
    only01 = client.get("/api/runs", params={"q": "run_01"}).json()
    assert [r["run_id"] for r in only01] == ["mock_run_01"]
    # verdict = runs that contain a sample with that verdict (mock_run_01 has S4 escalate).
    esc = client.get("/api/runs", params={"verdict": "escalate"}).json()
    assert "mock_run_01" in {r["run_id"] for r in esc}
    assert all(r["counts"]["escalate"] > 0 for r in esc)
    # A run with zero of that verdict is filtered out (rerun is absent from mock_run_01).
    rerun_ids = {r["run_id"] for r in client.get("/api/runs", params={"verdict": "rerun"}).json()}
    assert "mock_run_01" not in rerun_ids
    # Unknown verdict is a 400 (closed vocabulary, same as /api/export).
    assert client.get("/api/runs", params={"verdict": "maybe"}).status_code == 400


def test_list_runs_sort_vocabulary_and_default_order():
    # Default order (no sort) is run_id ascending — unchanged from before.
    default_ids = [r["run_id"] for r in client.get("/api/runs").json()]
    assert default_ids == sorted(default_ids)
    # -run_date sorts descending by [Header] date (every fixture is dated).
    dates = [r["run_date"] for r in client.get("/api/runs", params={"sort": "-run_date"}).json()]
    assert dates == sorted(dates, reverse=True)
    # -n_attention ranks the most-flagged runs first.
    ranked = client.get("/api/runs", params={"sort": "-n_attention"}).json()
    atts = [r["n_attention"] for r in ranked]
    assert atts == sorted(atts, reverse=True)
    # An unknown sort token is a 400, never a silent default.
    assert client.get("/api/runs", params={"sort": "bogus"}).status_code == 400


def test_list_runs_pagination_slices_and_reports_total():
    # Pagination is a plain slice over the (unpaginated) run list; the header carries the total.
    full = [r["run_id"] for r in client.get("/api/runs").json()]
    total = len(full)
    resp1 = client.get("/api/runs", params={"limit": 2, "page": 1})
    assert [r["run_id"] for r in resp1.json()] == full[0:2]
    assert resp1.headers["x-bayleaf-total-count"] == str(total)  # total is pre-slice
    assert resp1.headers["x-bayleaf-limit"] == "2" and resp1.headers["x-bayleaf-page"] == "1"
    p2 = client.get("/api/runs", params={"limit": 2, "page": 2}).json()
    assert [r["run_id"] for r in p2] == full[2:4]
    # A page past the end is an empty slice, not an error.
    assert client.get("/api/runs", params={"limit": 2, "page": 999}).json() == []
    # The limit/page floors are enforced by the query constraint (422, not a crash).
    assert client.get("/api/runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/runs", params={"page": 0}).status_code == 422


# --- Monitoring dashboard (pre-aggregated; the §7 screen) -------------------------------------


def test_in_window_is_pure_and_tolerant():
    # The date predicate is a pure, now-injected function so its boundary is clock-independent.
    from datetime import date

    from api.main import _in_window

    now = date(2026, 7, 9)
    assert _in_window("2026-07-08", "7d", now=now) is True
    assert _in_window("2026-07-02", "7d", now=now) is True  # cutoff (now - 7d) is inclusive
    assert _in_window("2026-07-01", "7d", now=now) is False  # just outside the window
    assert _in_window("2026-06-20", "30d", now=now) is True
    assert _in_window(None, "7d", now=now) is None  # undated → can't be placed on the axis
    assert _in_window("not-a-date", "30d", now=now) is None  # tolerant parse, not a crash
    assert _in_window(None, "all", now=now) is True  # "all" admits undated runs
    assert _in_window("2020-01-01", "all", now=now) is True  # "all" ignores the date entirely


def test_monitoring_default_window_is_internally_consistent():
    body = client.get("/api/monitoring").json()
    assert body["window"] == "all" and body["n_runs_excluded_no_date"] == 0
    over = body["overall"]
    rows = body["runs"]
    verdicts = over["verdict_counts"]
    # The overall roll-up is internally consistent with the per-run rows + verdict split.
    assert over["n_runs"] == len(rows)
    assert over["n_samples"] == sum(r["n_samples"] for r in rows) == sum(verdicts.values())
    assert set(verdicts) == {"proceed", "hold", "rerun", "escalate"}
    assert over["n_attention"] == verdicts["hold"] + verdicts["rerun"] + verdicts["escalate"]
    assert abs(over["auto_proceed_pct"] - 100.0 * verdicts["proceed"] / over["n_samples"]) < 1e-9
    # Per-gate rows carry flagged/total for the pass-rate bars; total == the sample count.
    gates = {g["gate"]: g for g in body["gates"]}
    assert set(gates) == {"preflight", "qc", "variant"}
    for g in gates.values():
        assert g["total"] == over["n_samples"] and 0 <= g["flagged"] <= g["total"]
    # Rows are chronological (dates non-decreasing); the known mock_run_01 row is exact.
    dates = [r["run_date"] for r in rows]
    assert dates == sorted(dates)
    r01 = next(r for r in rows if r["run_id"] == "mock_run_01")
    assert r01["run_date"] == "2026-07-07" and r01["n_samples"] == 5
    assert r01["counts"] == {"proceed": 3, "hold": 1, "rerun": 0, "escalate": 1}
    # Recurring signatures are ranked count-desc and fully described.
    sigs = body["signatures"]
    assert body["n_signatures_total"] == len(sigs)  # uncapped by default
    assert [s["count"] for s in sigs] == sorted((s["count"] for s in sigs), reverse=True)
    assert all(s["count"] >= 1 for s in sigs)
    # Fully described, incl. the additive first/last-seen + trend + affected-run deep-link fields.
    assert {
        "signature",
        "rule_id",
        "title",
        "gate",
        "count",
        "first_seen",
        "last_seen",
        "trend",
        "affected_run_ids",
    } == set(sigs[0])


def test_monitoring_signature_cap_reports_full_total():
    uncapped = client.get("/api/monitoring").json()
    total = uncapped["n_signatures_total"]
    assert total == len(uncapped["signatures"]) and total > 3  # fixtures have several signatures
    capped = client.get("/api/monitoring", params={"signatures_limit": 3}).json()
    assert len(capped["signatures"]) == 3  # the ranked list is capped ...
    assert capped["n_signatures_total"] == total  # ... but the full distinct count is reported
    # The highest-count signature survives the cap (ranking is applied before the slice).
    assert capped["signatures"][0]["count"] == uncapped["signatures"][0]["count"]
    # signatures_limit floor is enforced by the query constraint.
    assert client.get("/api/monitoring", params={"signatures_limit": 0}).status_code == 422


def test_monitoring_runs_pagination_slices_and_reports_total():
    # The per-run throughput array is server-paginated (T-072/F-INT-09); it mirrors GET /api/runs
    # exactly (same params, same headers). Only `runs[]` slices — the whole-window aggregates
    # (overall / gates / signatures) are computed before the slice, so a page can't distort them.
    full = client.get("/api/monitoring").json()
    all_runs = [r["run_id"] for r in full["runs"]]
    total = len(all_runs)
    assert total >= 4  # fixtures carry many dated runs, enough to page

    resp1 = client.get("/api/monitoring", params={"limit": 2, "page": 1})
    body1 = resp1.json()
    assert [r["run_id"] for r in body1["runs"]] == all_runs[0:2]  # sliced to the page
    assert resp1.headers["x-bayleaf-total-count"] == str(total)  # total is pre-slice
    assert resp1.headers["x-bayleaf-limit"] == "2" and resp1.headers["x-bayleaf-page"] == "1"
    # The aggregates ignore the page: overall.n_runs counts the WHOLE window, not the 2-run slice.
    assert body1["overall"]["n_runs"] == total
    assert body1["n_signatures_total"] == full["n_signatures_total"]
    assert body1["gates"] == full["gates"]

    p2 = client.get("/api/monitoring", params={"limit": 2, "page": 2}).json()["runs"]
    assert [r["run_id"] for r in p2] == all_runs[2:4]
    # A page past the end is an empty run slice, not an error (aggregates still whole-window).
    past = client.get("/api/monitoring", params={"limit": 2, "page": 999}).json()
    assert past["runs"] == [] and past["overall"]["n_runs"] == total
    # With no limit the runs are unpaginated + no page/limit headers (backward-compatible); the
    # total-count header is still emitted so a client can decide whether to page.
    resp_default = client.get("/api/monitoring")
    assert "x-bayleaf-page" not in resp_default.headers
    assert "x-bayleaf-limit" not in resp_default.headers
    assert resp_default.headers["x-bayleaf-total-count"] == str(total)
    # The limit/page floors are enforced by the query constraint (422, not a crash), as /api/runs.
    assert client.get("/api/monitoring", params={"limit": 0}).status_code == 422
    assert client.get("/api/monitoring", params={"page": 0}).status_code == 422


def test_monitoring_window_validation_and_invariants():
    assert client.get("/api/monitoring", params={"window": "bogus"}).status_code == 400
    body = client.get("/api/monitoring", params={"window": "7d"}).json()
    assert body["window"] == "7d"
    # Every mock run is dated, so none are ever set aside for lacking a date — a clock-independent
    # invariant regardless of which runs the window admits.
    assert body["n_runs_excluded_no_date"] == 0
    over = body["overall"]
    # Internal consistency holds for whatever subset the window admits at test time.
    assert over["n_runs"] == len(body["runs"])
    assert over["n_samples"] == sum(r["n_samples"] for r in body["runs"])
    for g in body["gates"]:
        assert g["total"] == over["n_samples"] and 0 <= g["flagged"] <= g["total"]
    if over["n_samples"]:
        assert 0.0 <= over["auto_proceed_pct"] <= 100.0
    else:
        assert over["auto_proceed_pct"] is None
