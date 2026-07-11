"""Route-to-human (VAR-RTH-001) — the OFF-BY-DEFAULT gate rule that escalates a ClinVar-significant
candidate to MANDATORY human review (ADR-0018 decision D2).

The guardrail this suite pins: PipeGuard authors NO pathogenicity. The rule is disarmed by
default (so the pinned demo scenario is byte-for-byte unchanged), and when armed it merely QUOTES
ClinVar verbatim as cited evidence and routes to a human (ESCALATE) — it never renders a clinical
determination. Fully offline; ClinVar significance is a contrived spiked fixture
(`origin=contrived`), never implying a real individual (the only real substrate is GIAB HG002).
"""

from pathlib import Path

from pipeguard.engine import run_gate
from pipeguard.models import RunArtifacts, Verdict
from pipeguard.parsers import parse_variant_calls
from pipeguard.rules import _check_route_to_human, evaluate_sample
from pipeguard.runbook import DEFAULT_RUNBOOK, RouteToHumanPolicy, Runbook

# A contrived annotated-variant table: one clearly Pathogenic candidate (would route when armed),
# one Benign (never routes). Verbatim ClinVar strings, incl. the underscore ClinVar actually uses.
_VARIANTS_CSV = (
    "sample_id,gene,hgvs,clinvar_significance,clinvar_review_status,clinvar_accession,clinvar_version\n"
    "HG002,BRCA1,NM_007294.4:c.68_69del,Pathogenic,criteria_provided_multiple_submitters,VCV000017661,2026-01\n"
    "HG002,TTN,NM_001267550.2:c.1A>G,Benign,criteria_provided_single_submitter,VCV000048110,2026-01\n"
)


def _armed(*significances: str, review_statuses: tuple[str, ...] = ()) -> Runbook:
    """DEFAULT_RUNBOOK with ONLY the route-to-human policy armed (qc thresholds untouched)."""
    return DEFAULT_RUNBOOK.model_copy(
        update={
            "route_to_human": RouteToHumanPolicy(
                significances=significances, review_statuses=review_statuses
            )
        }
    )


def _write(tmp_path: Path, body: str) -> list:
    p = tmp_path / "variants.csv"
    p.write_text(body)
    return parse_variant_calls(p)


# ── parser ──────────────────────────────────────────────────────────────────────
def test_parse_variant_calls_reads_verbatim(tmp_path: Path) -> None:
    calls = _write(tmp_path, _VARIANTS_CSV)
    assert [c.gene for c in calls] == ["BRCA1", "TTN"]
    # Significance is preserved VERBATIM — the parser never normalizes or reclassifies (ADR-0004).
    assert calls[0].clinvar_significance == "Pathogenic"
    assert calls[0].clinvar_accession == "VCV000017661"
    assert calls[1].clinvar_significance == "Benign"


def test_parse_variant_calls_is_tolerant(tmp_path: Path) -> None:
    assert parse_variant_calls(tmp_path / "absent.csv") == []  # absent -> [] (a signal, not crash)
    # Tolerant of alternate column spellings (clnsig / clnrevstat / clnacc).
    alt = "sample,symbol,variant,clnsig\nHG002,BRCA1,c.68_69del,Pathogenic\n"
    calls = _write(tmp_path, alt)
    assert calls[0].sample_id == "HG002" and calls[0].clinvar_significance == "Pathogenic"


# ── rule: OFF by default ─────────────────────────────────────────────────────────
def test_route_to_human_is_off_by_default(tmp_path: Path) -> None:
    calls = _write(tmp_path, _VARIANTS_CSV)
    # Stock (disarmed) runbook: even a Pathogenic candidate produces NO routing finding.
    assert DEFAULT_RUNBOOK.route_to_human.armed is False
    assert _check_route_to_human("HG002", calls, DEFAULT_RUNBOOK) is None


# ── rule: armed ──────────────────────────────────────────────────────────────────
def test_armed_pathogenic_routes_to_human(tmp_path: Path) -> None:
    calls = _write(tmp_path, _VARIANTS_CSV)
    f = _check_route_to_human("HG002", calls, _armed("Pathogenic", "Likely_pathogenic"))
    assert f is not None and f.rule_id == "VAR-RTH-001"
    assert f.suggested_verdict is Verdict.ESCALATE  # route to a human — the conservative action
    assert f.gate.value == "variant"  # lands on the variant gate, not the QC gate
    # The finding QUOTES ClinVar verbatim and cites the accession — it authors no significance.
    clnsig_ev = next(e for e in f.evidence if e.source_field == "CLNSIG")
    assert clnsig_ev.value == "Pathogenic"  # verbatim, not PipeGuard's determination
    assert "VCV000017661" in (clnsig_ev.locator or "")
    assert "ClinVar" in clnsig_ev.source
    # The prose never claims PipeGuard decided pathogenicity — it defers to a human.
    assert "makes no pathogenicity determination" in f.detail


def test_armed_benign_does_not_route(tmp_path: Path) -> None:
    # A run whose only candidate is Benign never routes, even with the policy armed.
    body = "sample_id,gene,clinvar_significance\nHG002,TTN,Benign\n"
    calls = parse_variant_calls_from(tmp_path, body)
    assert _check_route_to_human("HG002", calls, _armed("Pathogenic", "Likely_pathogenic")) is None


def test_significance_match_is_separator_insensitive(tmp_path: Path) -> None:
    # ClinVar's "Likely_pathogenic" matches a config that writes "Likely pathogenic" (match-only
    # folding; the quoted value stays verbatim).
    calls = parse_variant_calls_from(
        tmp_path, "sample_id,gene,clinvar_significance\nHG002,BRCA2,Likely_pathogenic\n"
    )
    f = _check_route_to_human("HG002", calls, _armed("Likely pathogenic"))
    assert f is not None
    assert next(e for e in f.evidence if e.source_field == "CLNSIG").value == "Likely_pathogenic"


def test_review_status_floor_gates_routing(tmp_path: Path) -> None:
    # With a review-status allow-list, a single-submitter Pathogenic call does NOT route unless its
    # status is on the list — a stricter arming (star-rating floor).
    body = (
        "sample_id,gene,clinvar_significance,clinvar_review_status\n"
        "HG002,BRCA1,Pathogenic,criteria_provided_single_submitter\n"
    )
    calls = parse_variant_calls_from(tmp_path, body)
    strict = _armed("Pathogenic", review_statuses=("criteria_provided_multiple_submitters",))
    assert _check_route_to_human("HG002", calls, strict) is None
    lenient = _armed("Pathogenic", review_statuses=("criteria_provided_single_submitter",))
    assert _check_route_to_human("HG002", calls, lenient) is not None


# ── end-to-end: the rule drives the card verdict (rules decide) ─────────────────
def test_end_to_end_armed_run_escalates_the_card(tmp_path: Path) -> None:
    calls = _write(tmp_path, _VARIANTS_CSV)
    artifacts = RunArtifacts(run_id="RUN-CONTRIVED-RTH", variant_calls=calls)
    cards = run_gate(artifacts, runbook=_armed("Pathogenic"))
    card = next(c for c in cards if c.sample_id == "HG002")
    # A deterministic rule routed the sample; the card verdict is ESCALATE (rules decide, ADR-0001).
    assert card.verdict is Verdict.ESCALATE
    assert any(f.rule_id == "VAR-RTH-001" for f in card.findings)
    # The same run through a DISARMED runbook does not escalate on this basis.
    proceed_cards = run_gate(artifacts, runbook=DEFAULT_RUNBOOK)
    proceed = next(c for c in proceed_cards if c.sample_id == "HG002")
    assert not any(f.rule_id == "VAR-RTH-001" for f in proceed.findings)


def test_disarmed_run_matches_stock_evaluation(tmp_path: Path) -> None:
    # Belt-and-suspenders: a sample with variant_calls but a disarmed runbook yields exactly the
    # findings it would without any variant data (the new rule is a no-op).
    calls = _write(tmp_path, _VARIANTS_CSV)
    with_variants = RunArtifacts(run_id="R", variant_calls=calls)
    without = RunArtifacts(run_id="R")
    assert [f.rule_id for f in evaluate_sample("HG002", with_variants, DEFAULT_RUNBOOK)] == [
        f.rule_id for f in evaluate_sample("HG002", without, DEFAULT_RUNBOOK)
    ]


def parse_variant_calls_from(tmp_path: Path, body: str) -> list:
    """Small helper: write `body` to a variants.csv under tmp_path and parse it."""
    p = tmp_path / "variants.csv"
    p.write_text(body)
    return parse_variant_calls(p)
