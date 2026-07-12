"""Config-driven de-identification policy for the export seam (T-040, W14).

DEMO SEAM — **NOT HIPAA de-identification.** This module is a small, explicit,
unit-testable field-class policy that shapes what leaves the machine through
`GET /api/export`. Hashing here is *pseudonymization* — a salted SHA-256 digest
truncated to a short token — which is a non-reversible heuristic, **not** the HIPAA
Safe-Harbor / Expert-Determination de-identification of 45 CFR §164.514. It makes no
compliance, diagnostic, or safety claim. The full de-id module (ingest-side 18-identifier
scrub, free-text NLP redaction, date-shift / k-anonymity, DUA/BAA, audit) stays
documented-only (wishlist #14, `docs/design/data-platform-and-archivist.md` §2.1d).

Why it lives in `api/` and not the core: de-identification is an **export-path data
transform only**. It never reads, sets, or overrides a verdict, finding, confidence, or
gate input — the deterministic gate in `src/pipeguard/` is untouched (ADR-0001, CLAUDE.md
architecture guardrail 1). Rules decide; this only shapes what the read-API emits.

Design (four field classes, applied per row against the run's read-only `origin`):

1. ``DROP`` — omit the field entirely. Operator PII (``submitted_by``) has no business
   as an ML feature and never leaves the machine (data-platform G-PII / D10).
2. ``HASH`` — always emit a salted, truncated, non-reversible pseudonym.
3. ``GATE_BY_ORIGIN`` — the origin-gated cohort-key opt-in (G-DEID): withhold the field
   for **PHI-guarded** origins (``real-giab`` and, conservatively, untagged ``unknown``);
   for non-real origins (``synthetic`` / ``contrived`` / public), emit a **hashed**
   pseudonym so the demo can visibly show cohort keys that are both origin-gated *and*
   pseudonymized rather than raw.
4. ``PASSTHROUGH`` — emit as-is (the default for any unnamed operational field).

Provenance non-laundering (design §5e): ``origin`` is read-only from the per-run marker
(``api/main._run_origin``); the guarded-origin set is a fixed classification here, **not**
env-configurable, so config can never relabel a run *up* to ``real-giab`` to launder it.

Config (env, mirroring the existing ``os.environ`` pattern): ``PIPEGUARD_DEID_SALT`` sets
the pseudonymization salt; absent, a documented **non-secret demo default** is used (the
salt is a heuristic, not a secret — see the module note above).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Stable id/version for the manifest header (X-PipeGuard-Deid-Policy). Bumping the field
# classes below bumps this so a consumer can tell which policy shaped a file. NOT a
# compliance attestation — see the module docstring.
DEID_POLICY_ID = "demo-deid-v1"

# Env var for the pseudonymization salt (documented in .env.example).
_ENV_DEID_SALT = "PIPEGUARD_DEID_SALT"

# A documented, non-secret demo default. The salt is a heuristic input to pseudonymization,
# not a credential — hashing here is explicitly NOT HIPAA de-id, so a public default is
# acceptable and keeps the offline demo deterministic. Override via PIPEGUARD_DEID_SALT.
_DEFAULT_SALT = "pipeguard-demo-deid-salt"

# Pseudonym token length (hex chars kept from the digest). 16 hex chars = 64 bits of the
# digest — collision-negligible at demo scale while staying short enough to read in a cell.
_PSEUDONYM_LEN = 16
_PSEUDONYM_PREFIX = "pseudo_"

# Origins treated as PHI-guarded: intake-identity cohort keys are NOT exported for these.
# ``unknown`` is included so an *untagged* run is guarded conservatively and never leaks
# identity by omission-of-a-tag. This set is intentionally NOT env-configurable (§5e): a
# run's origin is read-only from its marker and config must not relabel it up to real-giab.
GUARDED_ORIGINS: frozenset[str] = frozenset({"real-giab", "unknown"})


class DeidAction(str, Enum):
    """How one field is treated at the export seam (see the module docstring)."""

    DROP = "drop"
    HASH = "hash"
    GATE_BY_ORIGIN = "gate_by_origin"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class DeidPolicy:
    """An immutable, config-driven map of field name → :class:`DeidAction`.

    Unnamed fields default to ``PASSTHROUGH`` (the operational columns — ``run_id``,
    ``verdict``, ``origin`` … — flow through untouched), so the policy only needs to name
    the sensitive fields. ``salt`` feeds pseudonymization; ``guarded_origins`` is the fixed
    PHI-guarded classification used by ``GATE_BY_ORIGIN`` (not relabelable — §5e).
    """

    field_actions: Mapping[str, DeidAction]
    salt: str = _DEFAULT_SALT
    guarded_origins: frozenset[str] = GUARDED_ORIGINS
    policy_id: str = DEID_POLICY_ID

    def action_for(self, field_name: str) -> DeidAction:
        """The action for ``field_name`` (``PASSTHROUGH`` if the policy does not name it).

        Matching is **case-insensitive** (audit AS-05): the lookup key is trimmed + lower-cased so
        a differently-cased column (``Tissue``, ``Submitted_By``) still resolves to its policy
        action instead of silently falling through to ``PASSTHROUGH`` and egressing raw. Policy
        keys are authored lowercase (see :func:`default_policy`), so this is a strict tightening —
        a mixed-case identifier now gets dropped/gated rather than leaking.
        """
        return self.field_actions.get(field_name.strip().lower(), DeidAction.PASSTHROUGH)


def _pseudonymize(value: str, salt: str) -> str:
    """Salted, truncated, non-reversible SHA-256 pseudonym for ``value``.

    A NUL separator makes the ``salt``/``value`` boundary unambiguous so distinct
    (salt, value) pairs cannot collide by concatenation. This is pseudonymization, NOT
    HIPAA de-identification — stable for a given (salt, value) but not a secure MAC.
    """
    digest = hashlib.sha256(f"{salt}\x00{value}".encode()).hexdigest()
    return f"{_PSEUDONYM_PREFIX}{digest[:_PSEUDONYM_LEN]}"


def redact(row: Mapping[str, Any], origin: str, policy: DeidPolicy) -> dict[str, Any]:
    """Apply ``policy`` to one export ``row``, returning a NEW dict.

    Pure transform over export data only — it never touches a verdict, finding,
    confidence, or gate input (ADR-0001). ``DROP`` omits the key entirely; ``HASH`` emits
    a pseudonym; ``GATE_BY_ORIGIN`` drops the key for a guarded ``origin`` and otherwise
    emits a pseudonym; ``PASSTHROUGH`` copies the value. A ``None`` value is never hashed
    (nothing to pseudonymize) — but a ``GATE_BY_ORIGIN`` field on a guarded origin is still
    dropped even when ``None``, so the mere presence of the column never leaks that a
    guarded run *had* a subject.
    """
    guarded = origin in policy.guarded_origins
    out: dict[str, Any] = {}
    for key, value in row.items():
        action = policy.action_for(key)
        if action is DeidAction.DROP:
            continue
        if action is DeidAction.GATE_BY_ORIGIN and guarded:
            continue  # cohort key withheld for PHI-guarded / real origins
        if action is DeidAction.PASSTHROUGH or value is None:
            out[key] = value
            continue
        # HASH, or GATE_BY_ORIGIN that survived the origin gate (a non-real origin): emit a
        # pseudonym so a cohort key is exported hashed, never raw.
        out[key] = _pseudonymize(str(value), policy.salt)
    return out


def export_fields(
    base_fields: list[str], identity_fields: list[str], policy: DeidPolicy
) -> list[str]:
    """Column order for an export: ``base_fields`` + any non-``DROP`` ``identity_fields``.

    Keeps the CSV/Parquet header consistent with what :func:`redact` emits — a ``DROP``
    field (e.g. ``submitted_by``) is excluded from the header entirely rather than left as
    an always-empty column. ``GATE_BY_ORIGIN`` fields stay in the header (populated for
    non-real rows, empty for guarded ones).
    """
    fields = list(base_fields)
    fields += [f for f in identity_fields if policy.action_for(f) is not DeidAction.DROP]
    return fields


def default_policy() -> DeidPolicy:
    """The active export de-id policy (reproduces today's base-field behavior exactly).

    Field classes: ``submitted_by`` → ``DROP`` (operator PII, never an ML feature);
    ``subject_id`` / ``tissue`` → ``GATE_BY_ORIGIN`` (intake cohort keys — withheld for
    real/guarded origins, pseudonymized for non-real). Every other export column is unnamed
    and therefore ``PASSTHROUGH``, so a non-identity export is byte-identical to before this
    policy existed. Salt from ``PIPEGUARD_DEID_SALT`` (documented non-secret demo default).

    Note (honest tradeoff): ``tissue`` is a low-cardinality attribute that a *real* policy
    might keep as a coarse feature rather than hash; the demo classes it as a cohort key to
    show origin-gated pseudonymization end to end. A real de-id policy classifies per field.
    """
    salt = os.environ.get(_ENV_DEID_SALT, "").strip() or _DEFAULT_SALT
    return DeidPolicy(
        field_actions={
            "submitted_by": DeidAction.DROP,
            "subject_id": DeidAction.GATE_BY_ORIGIN,
            "tissue": DeidAction.GATE_BY_ORIGIN,
        },
        salt=salt,
    )


# The intake-identity columns the opt-in `include=identity` export mode joins from
# `Sample`, in header order. `submitted_by` is joined so the policy can *demonstrably*
# DROP it (proven by the export tests), not merely omit it.
IDENTITY_FIELDS: list[str] = ["subject_id", "tissue", "submitted_by"]


# --- Free-text scrub (the node-log-observation seam, ADR-0012 least-privilege) ---------------
#
# The structured `redact` above shapes a row of named fields; a tool's `.command.log`/`.command.err`
# is FREE TEXT, so an agent that is granted a bound node's logs needs a text-level scrub before the
# tail leaves the machine. This is the SAME honesty posture as the rest of the module — a demo
# heuristic, explicitly **NOT** HIPAA de-identification or a validated NLP PHI scrubber (which stays
# documented-only, data-platform §2.1d). It does two conservative things:
#
#   1. Replaces every occurrence of a KNOWN sensitive literal (the run's subject ids from
#      `sample_metadata.csv`, the operator `submitted_by`) with a salted pseudonym — so a subject id
#      that a tool echoed into a path or a log line is pseudonymized, never emitted raw.
#   2. Redacts a few generic PII shapes (email addresses; 6+-digit runs that could be an MRN / DOB /
#      SSN / accession) with a fixed marker. The 6-digit floor is deliberately conservative so it
#      does not shred ordinary small metric integers a log legitimately prints.
#
# It never touches a verdict, finding, confidence, or gate input (ADR-0001) — it only shapes text on
# the read-API egress path.

# A generic email address.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# A run of 6+ digits (MRN / DOB-as-digits / SSN / accession-ish). Conservative: a shorter run (a
# coverage depth, a small count) is left alone so a log stays readable.
_LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")
# What a redacted generic-PII match becomes (distinct from a pseudonym so a reader can tell the two
# apart: a KNOWN literal is pseudonymized + stable; an unknown-shape match is opaquely redacted).
_TEXT_REDACTED = "[redacted]"
# Ignore a too-short "sensitive" literal — pseudonymizing a 1-char token would corrupt a log
# wholesale and leak nothing meaningful. A real subject/operator id is well over this floor.
_MIN_SENSITIVE_LEN = 3


def scrub_text(
    text: str, *, sensitive: Iterable[str] = (), policy: DeidPolicy | None = None
) -> str:
    """De-identify one free-text line/blob for the node-log observation grant (see module note).

    ``sensitive`` are KNOWN literals (subject ids, operator handles) to pseudonymize wherever they
    appear; longer literals are replaced first so a shorter substring can't pre-empt a longer id.
    Generic email/long-digit shapes are then redacted with a fixed marker. Pure text→text; a real
    NLP PHI scrubber is a documented seam, not this. ``policy`` supplies the pseudonymization salt
    (defaults to :func:`default_policy`)."""
    active = policy or default_policy()
    out = text
    # Longest-first so "SUBJ-00042" is pseudonymized before a bare "SUBJ" substring could match it.
    for token in sorted(
        {s.strip() for s in sensitive if s and len(s.strip()) >= _MIN_SENSITIVE_LEN},
        key=len,
        reverse=True,
    ):
        out = out.replace(token, _pseudonymize(token, active.salt))
    out = _EMAIL_RE.sub(_TEXT_REDACTED, out)
    out = _LONG_DIGITS_RE.sub(_TEXT_REDACTED, out)
    return out
