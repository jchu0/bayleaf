"""Tests for the read-only per-variant endpoint (GET /api/runs/{id}/variants) — the W3 slice.

The endpoint serves EVERY annotated candidate variant for a run, parsed from its `variants.csv`
via the same `bayleaf.parsers.parse_variant_calls` the gate uses. It is a read-only projection
of an externally-produced annotation (ADR-0018): bayleaf never runs an annotator and never
authors pathogenicity — the ClinVar significance is preserved VERBATIM (ADR-0004), and no verdict
is set here (ADR-0001).

Offline: a TestClient drives the app in-process (no server, no network).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# The committed contrived fixture carrying an annotated ClinVar variant (a verbatim-cited
# Pathogenic BRCA1 spike HG002 does not actually carry — the fixture's own NOTE.md is explicit).
_CLINVAR_RUN = "RUN-2026-07-11-CLINVAR-RTH"


def test_variants_served_for_clinvar_run() -> None:
    """The CLINVAR-RTH run's single annotated variant is served with every field VERBATIM."""
    resp = client.get(f"/api/runs/{_CLINVAR_RUN}/variants")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list) and len(rows) == 1
    v = rows[0]
    assert v["sample_id"] == "HG002"
    assert v["gene"] == "BRCA1"
    assert v["hgvs"] == "NM_007294.4:c.68_69del"
    # Quoted VERBATIM from variants.csv — never normalized, reclassified, or re-authored (ADR-0004).
    assert v["clinvar_significance"] == "Pathogenic"
    assert v["clinvar_review_status"] == "criteria_provided_multiple_submitters"
    assert v["clinvar_accession"] == "VCV000017661"
    assert v["clinvar_version"] == "2026-01"


def test_variants_empty_for_run_without_variants_csv() -> None:
    """A run with no variants.csv returns an empty list (a missing annotation is a signal,
    not an error) — never a 404 or a fabricated row."""
    resp = client.get("/api/runs/mock_run_01/variants")
    assert resp.status_code == 200
    assert resp.json() == []


def test_variants_unknown_run_is_404() -> None:
    """An unknown run id is a 404, mirroring the other run-detail reads (get_run/get_card)."""
    assert client.get("/api/runs/NOPE/variants").status_code == 404
