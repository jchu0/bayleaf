"""In-app feedback capture (W12) — product telemetry, OFF the deterministic gate.

Framework boundary + guardrail (CLAUDE.md 1, ADR-0001): this module holds the feedback
data contract + the append-only writer, with **no** FastAPI import and **no** import of the
`pipeguard` core — so the one write path in the app can never touch a verdict, finding,
provenance event, or the EventLedger. It mirrors `api/deid.py`: a self-contained telemetry
seam beside the read-API, not inside the gate wiring.

Config (env, mirroring the existing ``os.environ`` pattern): ``PIPEGUARD_FEEDBACK_PATH``
sets the JSONL sink; default is ``feedback.events.jsonl`` at the repo root (gitignored, next
to ``run.events.jsonl`` by convention). It is an operational path, never a secret. The path
is **server-fixed** — no request value ever contributes to it, so path traversal is
structurally impossible.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# Bump when the stored record shape changes, so an out-of-band reader can branch on it.
FEEDBACK_SCHEMA_VERSION = 1

_ENV_FEEDBACK_PATH = "PIPEGUARD_FEEDBACK_PATH"
# Repo root, beside where run.events.jsonl lives by convention (api/ -> parent -> parent).
_DEFAULT_FEEDBACK_PATH = Path(__file__).resolve().parent.parent / "feedback.events.jsonl"

# Serialize appends within a worker so concurrent requests can't interleave a line. Honest
# seam: multi-worker/multi-process needs a file lock (flock) or a durable sink — not built.
_WRITE_LOCK = threading.Lock()

# A rule id like ``PROV-001`` / ``qc.q30`` — bounded + charset-locked so it can never carry a
# newline (which would forge a second JSONL record) or a control char.
_RuleId = Annotated[str, StringConstraints(max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


class FeedbackContext(BaseModel):
    """Non-PII decision/route keys the client attaches so a reaction is analyzable.

    ``extra="forbid"`` is a *structural* PII guard, not a convention: a smuggled
    ``subject_id``/``email``/``name`` is a hard 422, never a silently-stored field. Every
    string is length-bounded with a strict charset so nothing here can forge a JSONL line or
    escape a path. ``verdict`` is a **snapshot** of the call being rated — analysis-only,
    never re-read by the gate.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    sample_id: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    verdict: Literal["proceed", "hold", "rerun", "escalate"] | None = None
    gate: Literal["preflight", "qc", "variant"] | None = None
    rule_ids: list[_RuleId] = Field(default_factory=list, max_length=64)
    # Pins the reaction to the immutable DecisionCard the client is holding (hex content hash).
    card_content_hash: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9]+$")
    route: str | None = Field(None, max_length=200)  # location.pathname — data only, never a path
    screen: str | None = Field(None, max_length=64)  # human title, e.g. "Decision cards"


class FeedbackIn(BaseModel):
    """The POST body. ``extra="forbid"`` blocks any smuggled identity/server field.

    Two targets, disjoint by construction (see the validator): ``decision`` carries an
    agree/disagree ``signal`` keyed to a specific verdict; ``product`` carries a ``kind`` for
    diffuse product feedback. There is deliberately **no** operator name/email/principal field
    anywhere in the request.
    """

    model_config = ConfigDict(extra="forbid")

    target: Literal["decision", "product"]
    signal: Literal["agree", "disagree"] | None = None
    reason_code: (
        Literal[
            "threshold_too_strict",
            "threshold_too_loose",
            "wrong_root_cause",
            "missing_context",
            "other",
        ]
        | None
    ) = None
    kind: Literal["idea", "problem", "confusing", "praise"] | None = None
    message: str | None = Field(None, max_length=2000)
    context: FeedbackContext = Field(default_factory=FeedbackContext)

    @field_validator("message")
    @classmethod
    def _normalize_message(cls, v: str | None) -> str | None:
        # Strip and coerce empty → None so a whitespace-only note is stored as absent.
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @model_validator(mode="after")
    def _check_target(self) -> FeedbackIn:
        # Keep the two targets disjoint + well-keyed so an out-of-band reader can trust the shape.
        if self.target == "decision":
            if self.signal is None:
                raise ValueError("decision feedback requires a signal (agree/disagree)")
            if self.kind is not None:
                raise ValueError("decision feedback must not carry a product 'kind'")
            ctx = self.context
            if not (ctx.run_id and ctx.sample_id and ctx.verdict):
                raise ValueError(
                    "decision feedback requires context.run_id, sample_id, and verdict"
                )
        else:  # product
            if self.kind is None:
                raise ValueError("product feedback requires a 'kind'")
            if self.signal is not None or self.reason_code is not None:
                raise ValueError("product feedback must not carry a decision signal/reason_code")
        return self


class FeedbackAck(BaseModel):
    """The 201 response. Deliberately minimal — the submitted message is never echoed back
    (no reflection surface), so the API never re-emits operator-typed text."""

    id: str
    received_at: str
    schema_version: int
    status: Literal["recorded"] = "recorded"


def feedback_path() -> Path:
    """The JSONL sink, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_FEEDBACK_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_FEEDBACK_PATH


def append_feedback(record: dict[str, Any]) -> None:
    """Append one record as a single JSONL line (append-only; prior lines are never touched).

    ``json.dumps`` escapes every value, so a message containing ``\\n`` or ``"`` can never forge
    a second line. ``OSError`` propagates so the caller can map a disk failure to a 503 without
    leaking the path.
    """
    line = json.dumps(record, ensure_ascii=False) + "\n"
    path = feedback_path()
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
