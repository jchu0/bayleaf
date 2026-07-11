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


# ── honesty boundary ────────────────────────────────────────────────────────────────
def test_policy_is_labelled_style_not_certified() -> None:
    # The policy id must say "style" — this is Safe-Harbor-STYLE, never an attested de-id claim.
    assert "style" in SAFE_HARBOR_POLICY_ID
    assert "hipaa-compliant" not in SAFE_HARBOR_POLICY_ID.lower()
    # All 18 identifier classes are documented (some as explicit "not present" seams).
    assert len(HIPAA_SAFE_HARBOR_CLASSES) == 18
