"""Tests for the FastAPI read-API — the production seam over the core.

Offline: TestClient drives the app in-process (no server, no network).
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_runs_returns_mock_run():
    runs = client.get("/api/runs").json()
    mr = next(r for r in runs if r["run_id"] == "mock_run_01")
    assert mr["n_samples"] == 5
    assert mr["n_attention"] == 2
    assert mr["counts"] == {"proceed": 3, "hold": 1, "rerun": 0, "escalate": 1}


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


def test_runbook_endpoint_exposes_thresholds():
    body = client.get("/api/runbook").json()
    # Life-science guardrail: the policy must read as illustrative, never clinical.
    assert "NOT clinical" in body["disclaimer"]
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


def test_metrics_prometheus_exposition():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = resp.text
    assert body.endswith("\n")
    # Well-formed exposition: HELP/TYPE headers present for a labelled metric.
    assert "# HELP pipeguard_cards_total" in body
    assert "# TYPE pipeguard_cards_total counter" in body
    # Aggregate scalars across the 3 committed mock runs (17 total cards).
    assert "pipeguard_runs_total 3" in body
    assert "pipeguard_samples_total 17" in body
    # Per-verdict counts (mock_run_01: S4 escalate, S5 hold, S1-S3 proceed; +02/+03).
    assert 'pipeguard_cards_total{verdict="proceed"} 7' in body
    assert 'pipeguard_cards_total{verdict="hold"} 5' in body
    assert 'pipeguard_cards_total{verdict="rerun"} 2' in body
    assert 'pipeguard_cards_total{verdict="escalate"} 3' in body
    # Per-gate flagged-sample counts; variant gate is present-and-zero for series stability.
    assert 'pipeguard_gate_flagged_samples_total{gate="preflight"} 6' in body
    assert 'pipeguard_gate_flagged_samples_total{gate="qc"} 4' in body
    assert 'pipeguard_gate_flagged_samples_total{gate="variant"} 0' in body
