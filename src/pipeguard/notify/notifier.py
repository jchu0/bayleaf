"""The outbound notify port + its adapters (ADR-0010 §2).

Turns a *flagged* :class:`~pipeguard.models.DecisionCard` into an outbound
notification. It follows the same stub-first, env-flippable shape as the synthesizer
(`get_synthesizer`) and triage-agent (`get_triage_agent`) seams so it is safe and cheap
to flip on, and never on the deterministic critical path (ADR-0001):

  * :class:`StubNotifier` is the zero-cost default — it builds the payload and records
    it to an in-memory outbox. It never opens a socket, so the whole app notifies offline.
  * :class:`SlackNotifier` is OFF by default, lazy-imports its client, and degrades to the
    stub on ANY error (mirroring `ClaudeTriageAgent`).

Notify policy
-------------
Only *actionable* cards notify — anything whose verdict is not ``PROCEED`` (HOLD, RERUN,
ESCALATE). A clean PROCEED card is :attr:`NotifyStatus.SKIPPED` with no payload: an
operator inbox should carry signal (cards that need a human), not an all-clear for every
passing sample. The check is :func:`should_notify`, grounded in the card's existing
:attr:`~pipeguard.models.DecisionCard.is_actionable`.

Live send is OUT OF SCOPE (T-015b)
----------------------------------
This task builds payload construction, the adapter shape, the lazy import, and the
fallback — but does **not** wire a live Slack post. Posting to a real workspace is
outward-facing and needs maintainer sign-off, so ``_LIVE_SEND_ENABLED`` is ``False`` and
the default demo/tests never send. See :class:`SlackNotifier` for the guarded seam + TODO.

Env knobs (mirror the synthesizer/triage seams; nothing hardcoded — see .env.example):
  PIPEGUARD_NOTIFIER        "stub" (default, offline, $0) | "slack" (adapter; live-send off)
  PIPEGUARD_SLACK_CHANNEL   target channel id/name for the (disabled) Slack path
  PIPEGUARD_SLACK_BOT_TOKEN bot token for the (disabled) Slack path — unused until sign-off
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from ..models import DecisionCard, Finding
from .models import NotifyPayload, NotifyResult, NotifyStatus

# Env var names, in one place so the factory and .env.example never drift.
_ENV_NOTIFIER = "PIPEGUARD_NOTIFIER"
_ENV_SLACK_CHANNEL = "PIPEGUARD_SLACK_CHANNEL"
# The NAME of the env var holding the token — not a secret value itself.
_ENV_SLACK_TOKEN = "PIPEGUARD_SLACK_BOT_TOKEN"

# Placeholder channels so a payload stays deterministic when nothing is configured.
_STUB_CHANNEL = "stub"
_UNCONFIGURED_CHANNEL = "unconfigured"

# The single, documented safety switch for the live Slack post. Kept a plain `bool`
# (NOT typing.Final/Literal) on purpose: as a Literal[False] mypy would prove the send
# branch unreachable and `warn_unreachable` (strict) would then flag it. Flipping this on
# is a deliberate, maintainer-gated act — see SlackNotifier.notify.
_LIVE_SEND_ENABLED: bool = False

# A conservative disclaimer on every notification: this is a research/demo QC aid, and the
# verdict was decided deterministically — the message only formats it (CLAUDE.md guardrails).
_DISCLAIMER = (
    "Research/demo QC aid — not a clinical decision. The verdict is a deterministic "
    "function of the rule findings; this notification only formats it."
)


def should_notify(card: DecisionCard) -> bool:
    """The notify policy: notify only for actionable (non-PROCEED) cards.

    An operator's notification channel should carry cards that need a human — HOLD,
    RERUN, ESCALATE — not an all-clear for every passing sample. Grounded in the card's
    own ``is_actionable`` so the policy has one definition, not two.
    """
    return card.is_actionable


def _finding_line(f: Finding) -> str:
    """One compact, human-readable line for a finding (severity + rule + title)."""
    return f"[{f.severity.value}] {f.rule_id}: {f.title}"


def _plain_text(card: DecisionCard) -> str:
    """A deterministic plain-text body — the Slack `text` fallback and the stub's record.

    No timestamps or ids are interpolated, so identical cards yield identical text (the
    determinism the tests pin). Findings/steps come straight off the card in their stable
    order; the port adds nothing the gate did not already decide.
    """
    lines = [
        f"Sample {card.sample_id} — verdict {card.verdict.value.upper()}",
        card.headline,
    ]
    if card.findings:
        lines.append("")
        lines.append("Findings:")
        lines.extend(f"  - {_finding_line(f)}" for f in card.findings)
    if card.next_steps:
        lines.append("")
        lines.append("Next steps:")
        lines.extend(f"  - {step}" for step in card.next_steps)
    lines.extend(["", _DISCLAIMER])
    return "\n".join(lines)


def _blocks(card: DecisionCard, title: str, text: str) -> list[dict[str, Any]]:
    """Slack Block Kit blocks, as plain dicts (no Slack SDK needed to build them).

    Kept structurally simple and deterministic: a header, a summary section, an optional
    findings section, and a context disclaimer. The header is truncated to Slack's 150-char
    plain_text limit so a long headline can never make the (future) post 400.
    """
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{card.verdict.value.upper()}* — {card.headline}\nSample `{card.sample_id}`"
                ),
            },
        },
    ]
    if card.findings:
        finding_md = "\n".join(f"• {_finding_line(f)}" for f in card.findings)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": finding_md}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _DISCLAIMER}]})
    return blocks


def build_payload(card: DecisionCard, *, channel: str) -> NotifyPayload:
    """Build the channel-ready notification for a card (shared by every adapter).

    Centralised (like triage's ``_assemble_note``) so the payload shape — and its
    provenance/determinism — is identical no matter which adapter sends it. It reads only
    the card's already-decided fields; it never computes or alters a verdict (ADR-0001).
    """
    title = f"[{card.verdict.value.upper()}] {card.sample_id} — {card.headline}"
    text = _plain_text(card)
    return NotifyPayload(
        channel=channel,
        title=title,
        text=text,
        blocks=_blocks(card, title, text),
        sample_id=card.sample_id,
        verdict=card.verdict,
        headline=card.headline,
    )


def _skipped_result(adapter: str) -> NotifyResult:
    """The result for a clean card the notify policy chose not to notify."""
    return NotifyResult(
        status=NotifyStatus.SKIPPED,
        adapter=adapter,
        payload=None,
        detail="skipped by policy: clean PROCEED card — nothing to notify",
    )


class NotifyPort(Protocol):
    """Turns a flagged DecisionCard into an outbound notification.

    The single seam the API/dashboard call; adapters are injected at the edge. An adapter
    MUST return a :class:`NotifyResult` and must never raise for an expected failure
    (missing creds, absent client lib) — it degrades instead, so a notification problem
    can never break the gate.
    """

    name: str

    def notify(self, card: DecisionCard) -> NotifyResult: ...


class StubNotifier:
    """Deterministic, zero-cost notifier: build the payload and record it (no network).

    The default adapter so the whole flow notifies offline, and the fallback the live
    :class:`SlackNotifier` degrades to. Recorded payloads land in :attr:`outbox` so a
    test (or a dashboard) can inspect exactly what *would* be sent.
    """

    name = "stub"

    def __init__(self, channel: str = _STUB_CHANNEL) -> None:
        # Injectable so the Slack fallback can record against the intended channel.
        self._channel = channel
        self._outbox: list[NotifyPayload] = []

    def notify(self, card: DecisionCard) -> NotifyResult:
        if not should_notify(card):
            return _skipped_result(self.name)
        payload = build_payload(card, channel=self._channel)
        # Record rather than send: the offline default still gives an inspectable trail.
        self._outbox.append(payload)
        return NotifyResult(
            status=NotifyStatus.PREPARED,
            adapter=self.name,
            payload=payload,
            detail="stub: payload recorded to the in-memory outbox, not sent (offline, $0)",
        )

    @property
    def outbox(self) -> list[NotifyPayload]:
        """A copy of the payloads this notifier has recorded (never sent)."""
        return list(self._outbox)


class SlackNotifier:
    """Slack notify adapter — OFF by default, live send deferred (T-015b, ADR-0010 §2).

    Design guarantees mirror `ClaudeTriageAgent` so the seam is safe to flip on later:
      * ``slack_sdk`` is imported lazily (it is deliberately NOT a dependency), so the
        package installs and runs without it.
      * Any error — an absent ``slack_sdk``, a missing token, an API failure — degrades to
        the offline stub. A notification problem can never break the gate or the demo.

    Live send is intentionally guarded OFF (``_LIVE_SEND_ENABLED``): posting to a real
    workspace is outward-facing and needs maintainer sign-off. With the guard off, every
    call delegates to the stub (payload built + recorded, no socket opened).
    """

    name = "slack"

    def __init__(self, channel: str | None = None) -> None:
        # Never hardcode the channel — resolve from env, else a clearly-unconfigured
        # placeholder so the payload stays deterministic.
        self._channel = channel or os.environ.get(_ENV_SLACK_CHANNEL) or _UNCONFIGURED_CHANNEL
        self._fallback = StubNotifier(channel=self._channel)
        self._client: Any = None  # slack_sdk WebClient, created lazily on first use

    def _get_client(self) -> Any:
        """Lazily construct the Slack client (import + token resolution).

        Kept separate so the live path is a single, testable seam. Raises when
        ``slack_sdk`` is absent or the token is unset — both of which
        :meth:`notify` catches and degrades on. Constructing a ``WebClient`` does NOT
        touch the network; only a post would.
        """
        if self._client is None:
            from slack_sdk import WebClient  # lazy: slack_sdk is intentionally not a dep

            # Best-effort local .env load (python-dotenv ships with the [claude] extra;
            # plain environment variables still work without it).
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass

            token = os.environ.get(_ENV_SLACK_TOKEN)
            if not token:
                raise RuntimeError(f"{_ENV_SLACK_TOKEN} is not set")
            self._client = WebClient(token=token)
        return self._client

    def notify(self, card: DecisionCard) -> NotifyResult:
        if not should_notify(card):
            return _skipped_result(self.name)

        if not _LIVE_SEND_ENABLED:
            # PRIMARY GUARD: live Slack posting is out of scope (ADR-0010 §2, T-015b).
            # Delegate to the offline stub — it builds + records the same payload and
            # never opens a socket, so the default demo and the test suite never send.
            # TODO(T-015b live-send): enable only behind an explicit maintainer-approved
            # opt-in (e.g. a PIPEGUARD_SLACK_LIVE flag) AND a resolved bot token.
            return self._fallback.notify(card)

        # --- guarded live-send seam (unreached until _LIVE_SEND_ENABLED flips) --------
        payload = build_payload(card, channel=self._channel)
        try:
            client = self._get_client()  # lazy slack_sdk import + token resolution
            # The one outward-facing call. Present so the wiring shape is reviewable, but
            # only reached when a maintainer has flipped the guard above.
            client.chat_postMessage(
                channel=payload.channel, text=payload.text, blocks=payload.blocks
            )
            return NotifyResult(
                status=NotifyStatus.SENT,
                adapter=self.name,
                payload=payload,
                detail=f"slack: posted to {payload.channel}",
            )
        except Exception:
            # ANY failure degrades to the offline stub — never break the gate over a
            # notification (missing slack_sdk, missing token, or an API error).
            return self._fallback.notify(card)


def get_notifier() -> NotifyPort:
    """Select the notifier from the environment (default: the zero-cost stub).

    Set ``PIPEGUARD_NOTIFIER=slack`` to use the Slack adapter (live send still guarded
    off; it degrades to the stub). This is the single line that flips the notify seam.
    """
    choice = os.environ.get(_ENV_NOTIFIER, "stub").strip().lower()
    if choice == "slack":
        return SlackNotifier()
    return StubNotifier()


def notify_card(card: DecisionCard, notifier: NotifyPort | None = None) -> NotifyResult:
    """Notify for one decision card via the env-selected notifier (or an injected one).

    The public entry point (mirrors `triage_card`): picks the env-selected notifier
    unless one is injected, applies the notify policy, and returns a
    :class:`NotifyResult`. It only formats + routes what the card already decided — it
    never sets or alters a verdict or confidence (ADR-0001).
    """
    notifier = notifier or get_notifier()
    return notifier.notify(card)


# Static type check: both adapters satisfy the NotifyPort protocol.
_STUB: NotifyPort = StubNotifier()
_SLACK: NotifyPort = SlackNotifier()
