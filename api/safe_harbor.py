"""Conservative HIPAA Safe-Harbor-STYLE de-identification for the share/report egress (ADR-0018 D3).

**HONESTY GUARDRAIL — read this first.** This module implements the 45 CFR §164.514(b)(2)
Safe-Harbor identifier removal *mechanically*, as the **most-conservative default** for whatever
leaves the machine through a share/report egress. It is **NOT** a certified or attested
de-identification: no Expert Determination, no formal audit, no BAA/DUA, no legal review. It makes
**no compliance claim** (CLAUDE.md life-science guardrail 1). Everything it emits is labelled
*"conservative Safe-Harbor-style scrub,"* never *"HIPAA-compliant"* or *"de-identified per HIPAA."*
Free-text redaction is regex-mechanical and will miss identifiers a human/NLP model would catch
(esp. names inside prose). **Real patient data would require a real, audited de-identification
program before any external share.** The maintainer chose this conservative default explicitly
("HIPAA compliance is so key here") — the strictest option we can honestly offer, not a substitute.

Why it lives in ``api/`` (not the core): de-identification is an **egress-path data transform
only**. It never reads, sets, or overrides a verdict, finding, confidence, or gate input — the
deterministic gate in ``src/pipeguard/`` is untouched (ADR-0001). Rules decide; this only shapes
what the read-API lets out. Structured pseudonymization reuses ``api.deid`` (salted, non-
reversible); this module adds the Safe-Harbor pieces the export policy left as seams: date
generalization to year, age capping at 90+, and mechanical free-text redaction of identifiers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .deid import DeidAction, _pseudonymize, default_policy

# Bump when the classes/behaviour below change so a consumer can tell which scrub shaped a file.
# NOT a compliance attestation — see the module docstring.
SAFE_HARBOR_POLICY_ID = "safe-harbor-style-v1"

# The 18 §164.514(b)(2) identifier classes, for reference + the manifest/UI. Each maps to how this
# module handles it: structured fields are dropped/hashed by name; free-text and dates are scrubbed
# by pattern. This table documents the intent; it is not the enforcement (that is the code below).
#
# HONEST-LABELING NOTE (audit AS-08). This list documents the classes the scrub *considers* — its
# coverage INTENT — NOT 18 independently running detectors. Read the per-class text below for the
# real status of each: only a subset have an active mechanical detector (email/phone/SSN/date/URL/
# IP/ZIP/long-id via `_FREETEXT_PATTERNS`, plus the by-name structured drops/hashes); several are
# **documented seams with NO detector** because the class does not appear in this data model —
# `vehicle`, `device`, `biometric`, `photo` (each labelled "not present … documented seam"); and
# `names` in free text is only weakly regex-adjacent (no NLP name model). So the manifest's
# `safe_harbor_classes` array is "classes considered," not "18 classes actively scrubbed." The
# prominent `_SHARE_DISCLAIMER` at the egress endpoint already states the scrub is uncertified and
# will miss prose identifiers; this note keeps the class list itself from reading as over-claiming.
HIPAA_SAFE_HARBOR_CLASSES: tuple[tuple[str, str], ...] = (
    (
        "names",
        "Names — dropped as structured fields; redacted in free text only mechanically (weak).",
    ),
    (
        "geo",
        "Geographic subdivisions smaller than a state — ZIP redacted; free-text addresses partial.",
    ),
    (
        "dates",
        "All date elements finer than year (and ages > 89) — generalized to year / capped at 90+.",
    ),
    ("phone", "Telephone numbers — regex-redacted."),
    ("fax", "Fax numbers — regex-redacted (same pattern as phone)."),
    ("email", "Email addresses — regex-redacted."),
    ("ssn", "Social Security numbers — regex-redacted."),
    ("mrn", "Medical record numbers — long numeric ids regex-redacted; named id fields dropped."),
    ("health_plan", "Health-plan beneficiary numbers — named id fields dropped."),
    ("account", "Account numbers — named id fields dropped; long numerics redacted."),
    ("license", "Certificate/license numbers — named id fields dropped."),
    ("vehicle", "Vehicle identifiers/plates — not present in this data model (documented seam)."),
    ("device", "Device identifiers/serials — not present in this data model (documented seam)."),
    ("url", "Web URLs — regex-redacted."),
    ("ip", "IP addresses — regex-redacted."),
    ("biometric", "Biometric identifiers — not present in this data model (documented seam)."),
    (
        "photo",
        "Full-face photos / comparable images — not present in this data model (documented seam).",
    ),
    (
        "other",
        "Any other unique identifying number/characteristic — long numerics redacted; free text.",
    ),
)

# Field names (matched case-insensitively) that are dropped outright as direct identifiers — the
# conservative choice for the columns this data model actually carries. `subject_id` is a unique
# subject key (Safe-Harbor class "other"); `submitted_by` is an operator name.
_DROP_FIELDS: frozenset[str] = frozenset(
    {"submitted_by", "subject_id", "patient_id", "mrn", "name", "email", "phone"}
)
# Field names whose value is generalized from a full date to year-only (Safe-Harbor "dates").
_DATE_FIELDS: frozenset[str] = frozenset(
    {"run_date", "date", "collection_date", "dob", "birth_date"}
)
# Free-text fields scrubbed for embedded identifiers rather than dropped (they may carry signal).
# The card-narration fields (`headline`/`rationale`/`next_steps`) are included: on the LIVE
# synthesizer path they are model-authored prose that could echo an identifier from the context, so
# they get the same mechanical scrub as any other free text rather than passing through raw.
_FREETEXT_FIELDS: frozenset[str] = frozenset(
    {
        "note",
        "notes",
        "comment",
        "comments",
        "narration",
        "detail",
        "headline",
        "rationale",
        "next_steps",
    }
)

# ── free-text redaction ─────────────────────────────────────────────────────────────────────────
# Mechanical regexes for the identifier classes that appear in prose. Ordered so more specific
# patterns (email, SSN) run before the generic long-number pattern that would otherwise eat them.
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL_RE = re.compile(r"\bhttps?://\S+\b", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
# A long bare number (>= 6 digits) — an MRN / account / other unique id. Runs last.
_LONGNUM_RE = re.compile(r"\b\d{6,}\b")

# (compiled pattern, class label) in application order. Email/URL/SSN/phone/date/IP before the
# generic ZIP + long-number sweeps so a specific class wins the label.
_FREETEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_EMAIL_RE, "EMAIL"),
    (_URL_RE, "URL"),
    (_SSN_RE, "SSN"),
    (_PHONE_RE, "PHONE"),
    (_IP_RE, "IP"),
    (_DATE_RE, "DATE"),
    (_ZIP_RE, "ZIP"),
    (_LONGNUM_RE, "ID"),
)


def redact_free_text(text: str) -> str:
    """Mechanically redact the regex-detectable Safe-Harbor identifier classes from ``text``.

    Each match becomes ``[REDACTED:CLASS]``. This is deliberately conservative but **mechanical** —
    it catches emails/phones/SSNs/dates/URLs/IPs/ZIPs/long-ids, and will MISS free-text names and
    other prose identifiers an NLP redactor would catch (documented limitation, module docstring).
    """
    out = text
    for pattern, label in _FREETEXT_PATTERNS:
        out = pattern.sub(f"[REDACTED:{label}]", out)
    return out


def generalize_date(value: str) -> str:
    """Reduce a date to year only (Safe-Harbor removes all date elements finer than year).

    ``2026-07-10`` → ``2026``; ``07/10/2026`` → ``2026``. A value with no recognizable 4-digit year
    is redacted wholesale (fail-closed / conservative) rather than passed through.
    """
    m = re.search(r"(19|20)\d{2}", value)
    return m.group(0) if m else "[REDACTED:DATE]"


def cap_age(age: int) -> str:
    """Cap ages over 89 into a single ``90+`` bucket (Safe-Harbor aggregation of ages > 89)."""
    return "90+" if age > 89 else str(age)


def redact_record(row: Mapping[str, Any], origin: str) -> dict[str, Any]:
    """Apply the conservative Safe-Harbor-style scrub to one egress ``row`` → a NEW dict.

    Pure transform over egress data only — never a verdict/finding/gate input (ADR-0001). Direct-
    identifier fields are dropped; date fields are generalized to year; free-text fields are
    regex-redacted; an ``age`` is capped at 90+. Every other field first passes through the shared
    ``api.deid`` structured policy (so operator PII stays dropped and cohort keys stay origin-gated,
    pseudonymized), then survives as-is. Fail-closed: an unrecognized field is kept only if the deid
    policy passed it through, so adding a new identifier column defaults to the deid policy's rule.
    """
    base = default_policy()
    guarded = origin in base.guarded_origins
    out: dict[str, Any] = {}
    for key, value in row.items():
        lkey = key.strip().lower()
        if lkey in _DROP_FIELDS:
            continue  # direct identifier — removed entirely
        # Resolve the shared structured export policy UP FRONT so a DROP / guarded-origin drop runs
        # BEFORE the `None` branch — otherwise an absent gated field (e.g. `tissue` on a guarded
        # `real-giab` run whose sample has no metadata) would emit `null` and leak that the column
        # exists (mirrors the correct ordering in `api.deid.redact`).
        # Look up with the case-folded key (audit AS-05): the field-name sets above match on `lkey`,
        # so a differently-cased identifier column (`Tissue`) must resolve its GATE_BY_ORIGIN/DROP
        # action here too rather than falling through to PASSTHROUGH and egressing raw.
        # (`action_for` also case-folds defensively; passing `lkey` keeps the intent explicit here.)
        action = base.action_for(lkey)
        if action is DeidAction.DROP:
            continue
        if action is DeidAction.GATE_BY_ORIGIN and guarded:
            continue  # cohort key withheld for PHI-guarded / real origins, even when None
        if value is None:
            out[key] = None
            continue
        if lkey in _DATE_FIELDS:
            out[key] = generalize_date(str(value))
            continue
        if lkey == "age":
            try:
                out[key] = cap_age(int(float(str(value))))
            except (TypeError, ValueError):
                out[key] = "[REDACTED:AGE]"
            continue
        if lkey in _FREETEXT_FIELDS:
            out[key] = redact_free_text(str(value))
            continue
        # Everything else defers to the structured export policy resolved above (passthrough/hash,
        # or a GATE_BY_ORIGIN that survived the origin gate).
        if action is DeidAction.PASSTHROUGH:
            out[key] = value
        else:  # HASH, or a GATE_BY_ORIGIN that survived the origin gate → pseudonymize
            out[key] = _pseudonymize(str(value), base.salt)
    return out
