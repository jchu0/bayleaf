"""Records for the outbound notify port (ADR-0010 §2).

Two record shapes live here:

  * :class:`NotifyPayload` — the fully-formed, channel-ready notification built from a
    *flagged* decision card: a title, a plain-text fallback body, and Slack Block Kit
    ``blocks`` (plain JSON dicts — no Slack SDK needed to construct them). It carries the
    card's ``verdict`` + ``headline`` for traceability but is **display only**: it copies
    what the deterministic gate decided and can never set or change a verdict (ADR-0001).
  * :class:`NotifyResult` — the outcome of a :meth:`~pipeguard.notify.NotifyPort.notify`
    call. Its :class:`NotifyStatus` distinguishes *skipped by policy* (a clean card),
    *prepared* (payload built + recorded but not sent — the stub, or the Slack adapter when
    live send is not armed), and *sent* (a real post — the Slack adapter with
    ``PIPEGUARD_SLACK_LIVE`` armed).

Both reuse the shared content-hash helper so a payload has the same stable, deterministic
identity every other record does — which is also what makes the payload testably
reproducible.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..identifiers import content_hash as _content_hash
from ..models import Verdict


class NotifyStatus(str, Enum):
    """What happened when a card was handed to a notifier.

    The three states keep the two orthogonal facts explicit — *did policy want a
    notification* and *was it actually delivered* — so the demo/tests can assert the
    guarded send path never fires without inspecting adapter internals.
    """

    SKIPPED = "skipped"  # notify policy said no (a clean PROCEED card) — no payload built
    PREPARED = "prepared"  # payload built + recorded, but NOT sent (stub, or unarmed Slack)
    SENT = "sent"  # a real outbound post (Slack with PIPEGUARD_SLACK_LIVE armed)


class NotifyPayload(BaseModel):
    """A channel-ready notification built from a flagged decision card.

    Frozen and content-hashed like every other record: identical inputs yield an
    identical payload (and identical ``content_hash``), which is the property the tests
    pin. ``blocks`` are Slack Block Kit structures kept as plain ``dict``s so the core
    stays framework-agnostic — building them needs no Slack SDK; only a live send would.
    """

    model_config = ConfigDict(frozen=True)

    channel: str = Field(
        ..., description="Target channel/destination id (Slack channel; env-driven)"
    )
    title: str = Field(..., description="Short subject line, e.g. '[ESCALATE] S4 — ...'")
    text: str = Field(..., description="Plain-text fallback body (Slack `text`)")
    blocks: list[dict[str, Any]] = Field(
        default_factory=list, description="Slack Block Kit blocks (plain JSON dicts)"
    )
    sample_id: str
    run_id: str | None = Field(
        None, description="Human run id the card belongs to (e.g. mock_run_01), for traceability"
    )
    # Copied from the card for traceability. The notify port NEVER decides a verdict
    # (ADR-0001); this mirrors what the deterministic gate already set.
    verdict: Verdict
    headline: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity of this payload — the same inputs always hash the same."""
        return _content_hash(
            {
                "channel": self.channel,
                "title": self.title,
                "text": self.text,
                "blocks": self.blocks,
                "sample_id": self.sample_id,
                "run_id": self.run_id,
                "verdict": self.verdict.value,
                "headline": self.headline,
            }
        )


class NotifyResult(BaseModel):
    """The outcome of one ``notify(card)`` call.

    Carries the built ``payload`` (``None`` only when skipped by policy), which adapter
    handled it, and a human-readable ``detail`` explaining *why* the status is what it is
    (e.g. "recorded, not sent"). ``delivered`` is the single question a caller usually
    asks — and it is ``False`` for everything the offline default produces.
    """

    model_config = ConfigDict(frozen=True)

    status: NotifyStatus
    adapter: str = Field(
        ..., description="Name of the adapter that handled the card ('stub'|'slack')"
    )
    payload: NotifyPayload | None = Field(
        None, description="The built notification; None when skipped by policy"
    )
    detail: str = Field(..., description="Human-readable reason for this status")

    @property
    def delivered(self) -> bool:
        """True only for a real outbound send (Slack with live send armed)."""
        return self.status is NotifyStatus.SENT
