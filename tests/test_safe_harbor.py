"""Conservative HIPAA Safe-Harbor-STYLE de-identification (ADR-0018 D3, api/safe_harbor.py).

Pins the conservative default the maintainer chose: direct identifiers dropped, dates generalized to
year, ages capped at 90+, and free-text identifier classes mechanically redacted. These tests also
pin the HONESTY boundary — the module never claims certified de-identification (its id says
"style"), and its free-text redaction is documented as mechanical/incomplete. Off-gate: this is an
egress transform only and never touches a verdict/finding (ADR-0001).
"""

from api.safe_harbor import (
    HIPAA_SAFE_HARBOR_CLASSES,
    SAFE_HARBOR_POLICY_ID,
    cap_age,
    generalize_date,
    redact_free_text,
    redact_record,
)


# ── free-text redaction (the regex-detectable identifier classes) ──────────────────
def test_redact_free_text_scrubs_each_class() -> None:
    text = (
        "Contact jane.doe@lab.org or 415-555-0134, SSN 123-45-6789, "
        "collected 2026-07-10, MRN 100482277, see http://ehr.example/x, host 10.0.0.5, ZIP 94107."
    )
    out = redact_free_text(text)
    # Every identifier is replaced; none of the raw values survive.
    for raw in [
        "jane.doe@lab.org",
        "415-555-0134",
        "123-45-6789",
        "2026-07-10",
        "100482277",
        "http://ehr.example/x",
        "10.0.0.5",
        "94107",
    ]:
        assert raw not in out
    assert "[REDACTED:EMAIL]" in out
    assert "[REDACTED:SSN]" in out
    assert "[REDACTED:PHONE]" in out
    assert "[REDACTED:URL]" in out
    assert "[REDACTED:IP]" in out


def test_redact_free_text_leaves_non_identifiers() -> None:
    # A benign sentence with no identifiers is unchanged.
    text = "Coverage was borderline; re-run recommended before release."
    assert redact_free_text(text) == text


# ── date generalization + age capping ──────────────────────────────────────────────
def test_generalize_date_keeps_year_only() -> None:
    assert generalize_date("2026-07-10") == "2026"
    assert generalize_date("07/10/2026") == "2026"
    assert generalize_date("July 10, 2026") == "2026"
    # No recognizable year → fail-closed to a redaction, never a passthrough.
    assert generalize_date("sometime last spring") == "[REDACTED:DATE]"


def test_cap_age_buckets_over_89() -> None:
    assert cap_age(42) == "42"
    assert cap_age(89) == "89"
    assert cap_age(90) == "90+"
    assert cap_age(105) == "90+"


# ── record-level conservative scrub ─────────────────────────────────────────────────
def test_redact_record_drops_direct_identifiers() -> None:
    row = {
        "run_id": "RUN-2026-07-10-A",
        "verdict": "hold",
        "submitted_by": "j.smith",  # operator name → dropped
        "subject_id": "SUBJ-0007",  # unique subject id → dropped
        "run_date": "2026-07-10",  # date → year
        "note": "call 415-555-0134 re MRN 100482277",  # free text → redacted
    }
    out = redact_record(row, origin="synthetic")
    assert "submitted_by" not in out  # direct identifier removed entirely
    assert "subject_id" not in out
    assert out["run_date"] == "2026"  # generalized to year
    assert "415-555-0134" not in out["note"] and "100482277" not in out["note"]
    assert out["run_id"] == "RUN-2026-07-10-A"  # non-identifier operational field kept
    assert out["verdict"] == "hold"


def test_redact_record_caps_age() -> None:
    out = redact_record({"age": "94"}, origin="synthetic")
    assert out["age"] == "90+"
    # A non-numeric age fails closed to a redaction rather than leaking.
    assert redact_record({"age": "ninety"}, origin="synthetic")["age"] == "[REDACTED:AGE]"


def test_redact_record_never_touches_verdict_or_gate() -> None:
    # Belt-and-suspenders: a verdict/confidence riding along in an egress row is passed through
    # untouched — the scrub shapes identifiers, it does not read or alter a decision (ADR-0001).
    out = redact_record(
        {"verdict": "escalate", "confidence": None, "gate": "variant"}, origin="synthetic"
    )
    assert out == {"verdict": "escalate", "confidence": None, "gate": "variant"}


# ── egress-hardening regressions (audit P2-11 / AS-02, AS-04) ─────────────────────────
def test_guarded_origin_drops_cohort_key_even_when_none() -> None:
    # AS-04: a GATE_BY_ORIGIN cohort key (tissue) on a PHI-guarded origin (real-giab) must be
    # DROPPED even when its value is None — never emitted as {"tissue": null}, which would leak
    # column PRESENCE for a guarded/real run. (The None short-circuit must not precede the drop.)
    out = redact_record({"tissue": None, "sample_id": "S1"}, origin="real-giab")
    assert "tissue" not in out
    # a present value is likewise withheld for a guarded origin
    assert "tissue" not in redact_record({"tissue": "blood"}, origin="real-giab")


def test_card_narration_freetext_is_scrubbed() -> None:
    # AS-02: card narration fields (headline/rationale/next_steps) are free-text scrubbed, not
    # passed through raw — an embedded identifier must not survive an export.
    out = redact_record(
        {"headline": "Escalate: contact jane.doe@lab.org", "rationale": "email ops@lab.org re it"},
        origin="synthetic",
    )
    assert "jane.doe@lab.org" not in out["headline"]
    assert "[REDACTED:EMAIL]" in out["headline"]
    assert "ops@lab.org" not in out["rationale"]


def test_mixed_case_cohort_key_is_not_passed_through_raw() -> None:
    # AS-05: the deid-fallback lookup must be case-insensitive. A differently-cased cohort column
    # (`Tissue`) is a GATE_BY_ORIGIN field — on a NON-guarded origin it must be pseudonymized, not
    # egressed raw as it would be if the lookup only matched the lowercase policy key.
    out = redact_record({"Tissue": "liver"}, origin="synthetic")
    assert out["Tissue"] != "liver"  # not raw
    assert out["Tissue"].startswith("pseudo_")  # origin-gated pseudonym, like lowercase `tissue`
    # And on a guarded origin the mixed-case cohort key must be DROPPED, not leaked as a column.
    assert "Tissue" not in redact_record({"Tissue": "liver"}, origin="real-giab")


def test_mixed_case_direct_identifier_is_dropped() -> None:
    # AS-05 (belt-and-suspenders): a mixed-case operator-PII column (`Submitted_By`) resolves its
    # DROP action case-insensitively and is removed entirely, not exported raw.
    out = redact_record({"Submitted_By": "j.smith", "run_id": "R1"}, origin="synthetic")
    assert "Submitted_By" not in out
    assert out["run_id"] == "R1"


# ── honesty boundary ────────────────────────────────────────────────────────────────
def test_policy_is_labelled_style_not_certified() -> None:
    # The policy id must say "style" — this is Safe-Harbor-STYLE, never an attested de-id claim.
    assert "style" in SAFE_HARBOR_POLICY_ID
    assert "hipaa-compliant" not in SAFE_HARBOR_POLICY_ID.lower()
    # All 18 identifier classes are documented (some as explicit "not present" seams).
    assert len(HIPAA_SAFE_HARBOR_CLASSES) == 18
