"""The outbound notify port + its adapters (ADR-0010 §2).

Turns a *flagged* :class:`~bayleaf.models.DecisionCard` into an outbound
notification. It follows the same stub-first, env-flippable shape as the synthesizer
(`get_synthesizer`) and triage-agent (`get_triage_agent`) seams so it is safe and cheap
to flip on, and never on the deterministic critical path (ADR-0001):

  * :class:`StubNotifier` is the zero-cost default — it builds the payload and records
    it to an in-memory outbox. It never opens a socket, so the whole app notifies offline.
  * :class:`SlackNotifier` is OFF by default, lazy-imports its client, and degrades to the
    stub on ANY error (mirroring `ClaudeTriageAgent`).
  * :class:`TeamsNotifier` / :class:`DiscordNotifier` are OFF by default too — incoming-
    webhook adapters that POST the shared body with the stdlib (``urllib.request``, no
    SDK, no new dependency) and share :class:`_WebhookNotifier`. Each has its OWN live-arm
    flag, so arming one channel never arms another.

Notify policy
-------------
Only *actionable* cards notify — anything whose verdict is not ``PROCEED`` (HOLD, RERUN,
ESCALATE). A clean PROCEED card is :attr:`NotifyStatus.SKIPPED` with no payload: an
operator inbox should carry signal (cards that need a human), not an all-clear for every
passing sample. The check is :func:`should_notify`, grounded in the card's existing
:attr:`~bayleaf.models.DecisionCard.is_actionable`.

Live send is OPT-IN, per adapter (T-015b / T-035)
-------------------------------------------------
Payload construction, the adapter shape, and the fallback are always built; the actual
outward-facing post is armed only by exporting that adapter's OWN ``*_LIVE`` flag
(see :func:`_flag_enabled`). Off by default and off from creds alone, so the default
demo/tests never send. Each adapter guards independently — arming Slack does not arm
Teams or Discord, and vice-versa.

Env knobs (mirror the synthesizer/triage seams; nothing hardcoded — see .env.example):
  BAYLEAF_NOTIFIER            "stub" (default, $0) | "slack" | "teams" | "discord"
  BAYLEAF_SLACK_LIVE          unset (default; never sends) | "1" to arm the Slack post
  BAYLEAF_SLACK_CHANNEL       target channel id/name for the Slack path (when armed)
  BAYLEAF_SLACK_BOT_TOKEN     bot token (xoxb-…, chat:write) — only used when armed
  BAYLEAF_TEAMS_LIVE          unset (default) | "1" to arm the Teams webhook POST
  BAYLEAF_TEAMS_WEBHOOK_URL   Teams incoming-webhook URL (secret) — only used when armed
  BAYLEAF_DISCORD_LIVE        unset (default) | "1" to arm the Discord webhook POST
  BAYLEAF_DISCORD_WEBHOOK_URL Discord webhook URL (secret) — only used when armed
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Protocol

from ..models import DecisionCard, Finding, Verdict
from .models import NotifyPayload, NotifyResult, NotifyStatus

# Env var names, in one place so the factory and .env.example never drift.
_ENV_NOTIFIER = "BAYLEAF_NOTIFIER"
_ENV_SLACK_CHANNEL = "BAYLEAF_SLACK_CHANNEL"
# The NAME of the env var holding the token — not a secret value itself.
_ENV_SLACK_TOKEN = "BAYLEAF_SLACK_BOT_TOKEN"
# Explicit opt-in for the outward-facing live post (see _live_send_enabled).
_ENV_SLACK_LIVE = "BAYLEAF_SLACK_LIVE"

# Webhook adapters (Teams / Discord). The URL is a SECRET (it embeds an auth token) —
# resolved from env only, never hardcoded or logged. Each has its own live-arm flag so
# arming one channel never arms another (mirrors BAYLEAF_SLACK_LIVE per-adapter).
_ENV_TEAMS_WEBHOOK = "BAYLEAF_TEAMS_WEBHOOK_URL"
_ENV_TEAMS_LIVE = "BAYLEAF_TEAMS_LIVE"
_ENV_DISCORD_WEBHOOK = "BAYLEAF_DISCORD_WEBHOOK_URL"
_ENV_DISCORD_LIVE = "BAYLEAF_DISCORD_LIVE"

# Placeholder channels so a payload stays deterministic when nothing is configured.
_STUB_CHANNEL = "stub"
_UNCONFIGURED_CHANNEL = "unconfigured"

# Discord caps a message's content at 2000 chars; truncate the shared body to fit so a
# long card can't 400 the webhook. (Slack/Teams have far higher limits.)
_DISCORD_CONTENT_LIMIT = 2000
# A conservative timeout on the one outward-facing POST so a hung webhook can't wedge a
# run; any timeout is an error that degrades to the offline stub (never breaks the gate).
_WEBHOOK_TIMEOUT_S = 10

_TRUTHY = {"1", "true", "yes", "on"}


def _flag_enabled(env_name: str) -> bool:
    """Whether an outward-facing live-send flag is armed (the per-adapter safety switch).

    Off unless the named env var is explicitly truthy. Read from ``os.environ`` (not a
    module constant) so it is opt-in per process and can't be silently baked in — the one
    place every adapter's arm-check is defined, so they can't drift.
    """
    return os.environ.get(env_name, "").strip().lower() in _TRUTHY


def _live_send_enabled() -> bool:
    """Whether the live Slack post is armed — the single safety switch.

    Off unless ``BAYLEAF_SLACK_LIVE`` is explicitly truthy in the environment.
    Posting to a real workspace is outward-facing, so it never turns on by default,
    by accident, or from the presence of a token alone: the demo and the test suite
    stay offline until a maintainer deliberately exports this flag *and* supplies a
    token + channel.
    """
    return _flag_enabled(_ENV_SLACK_LIVE)


def _post_webhook(url: str, body: dict[str, Any]) -> None:
    """POST a JSON body to an incoming webhook via the stdlib (the one outbound seam).

    Shared by every webhook adapter (Teams, Discord) so there is a single, patchable
    ``urllib.request.urlopen`` seam — a test spies on it to prove the default path opens
    no socket, and injects a fake opener to exercise the live shape without the wire. No
    Teams/Discord SDK and no new dependency: an incoming webhook is just an HTTP POST.
    Raises on any transport/HTTP error; the caller degrades to the stub so a webhook
    problem can never break the gate (ADR-0001).
    """
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    # Read the response so the request completes; the body is discarded (webhooks return
    # an empty 200/204). urlopen is the seam tests patch — never reached unless armed.
    with urllib.request.urlopen(request, timeout=_WEBHOOK_TIMEOUT_S) as response:
        response.read()


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


# Category-specific framing keyed on the verdict — turns a bare finding list into an
# actionable message: what *kind* of problem this is and what to do about it. The verdict
# is the gate's; this only explains it, and never sets one (ADR-0001).
_VERDICT_GUIDANCE: dict[Verdict, tuple[str, str]] = {
    Verdict.ESCALATE: (
        "🔴 Provenance / identity risk",
        "Chain-of-custody issue — do NOT use this sample downstream until its identity is "
        "verified. This is not a fixable data-quality problem.",
    ),
    Verdict.RERUN: (
        "🟠 Operational / pipeline failure",
        "The pipeline failed for this sample — re-run it. An operational failure, not a "
        "borderline metric.",
    ),
    Verdict.HOLD: (
        "🟡 Borderline QC — needs operator judgment",
        "A metric missed a gate but cleared the hard floor. A human decides proceed vs. "
        "rerun; this is not an automatic fail.",
    ),
    Verdict.PROCEED: ("🟢 Clean", "No action needed."),  # never notified; here for totality
}


def _evidence_detail(f: Finding) -> str:
    """The numbers behind a finding: observed vs. expected, pulled from its evidence.

    This turns "Q30 borderline" into "Q30: observed 84.1, expected 85" — the QC metric
    values an operator actually needs. Read straight off the immutable evidence; the port
    computes nothing.
    """
    parts: list[str] = []
    for e in f.evidence:
        if e.value is None:
            continue
        label = e.source_field or e.locator or e.source
        expected = e.expected or e.threshold
        if expected is not None:
            parts.append(f"{label}: observed {e.value}, expected {expected}")
        else:
            parts.append(f"{label}: {e.value}")
    return "; ".join(parts)


def _finding_line(f: Finding) -> str:
    """One line for a finding: severity + rule + title, enriched with observed-vs-expected."""
    base = f"[{f.severity.value}] {f.rule_id}: {f.title}"
    detail = _evidence_detail(f)
    return f"{base} — {detail}" if detail else base


def _plain_text(card: DecisionCard) -> str:
    """A deterministic plain-text body — the Slack `text` fallback and the stub's record.

    No timestamps or ids are interpolated, so identical cards yield identical text (the
    determinism the tests pin). Content is tailored per verdict (see _VERDICT_GUIDANCE);
    findings/steps come straight off the card in their stable order.
    """
    kind, action = _VERDICT_GUIDANCE.get(card.verdict, ("", ""))
    run = card.run_id or "unknown-run"
    lines = [
        f"[{card.verdict.value.upper()}] sample {card.sample_id} @ run {run}",
        card.headline,
        "",
        kind,
        action,
    ]
    if card.findings:
        lines += ["", "Findings:"]
        lines += [f"  - {_finding_line(f)}" for f in card.findings]
    if card.next_steps:
        lines += ["", "Next steps:"]
        lines += [f"  - {step}" for step in card.next_steps]
    lines += ["", _DISCLAIMER]
    return "\n".join(lines)


def _section(text: str) -> dict[str, Any]:
    """A Slack Block Kit mrkdwn section block."""
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _blocks(card: DecisionCard, title: str) -> list[dict[str, Any]]:
    """Slack Block Kit blocks, as plain dicts (no Slack SDK needed to build them).

    Header → summary with sample + run fields → the verdict-specific guidance → findings
    (with observed-vs-expected evidence) → next steps → the research/demo disclaimer. The
    header is truncated to Slack's 150-char plain_text limit so a long headline can't 400.
    """
    run = card.run_id or "unknown-run"
    summary = f"*{card.verdict.value.upper()}* — {card.headline}"
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
            "fields": [
                {"type": "mrkdwn", "text": f"*Sample*\n`{card.sample_id}`"},
                {"type": "mrkdwn", "text": f"*Run*\n`{run}`"},
            ],
        },
    ]
    kind, action = _VERDICT_GUIDANCE.get(card.verdict, ("", ""))
    if kind:
        blocks.append(_section(f"{kind}\n{action}"))
    if card.findings:
        finding_md = "\n".join(f"• {_finding_line(f)}" for f in card.findings)
        blocks.append(_section(f"*Findings*\n{finding_md}"))
    if card.next_steps:
        steps_md = "\n".join(f"• {step}" for step in card.next_steps)
        blocks.append(_section(f"*Next steps*\n{steps_md}"))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _DISCLAIMER}]})
    return blocks


def build_payload(card: DecisionCard, *, channel: str) -> NotifyPayload:
    """Build the channel-ready notification for a card (shared by every adapter).

    Centralised (like triage's ``_assemble_note``) so the payload shape — and its
    provenance/determinism — is identical no matter which adapter sends it. It reads only
    the card's already-decided fields; it never computes or alters a verdict (ADR-0001).
    """
    run = card.run_id or "unknown-run"
    title = f"[{card.verdict.value.upper()}] {card.sample_id} @ {run} — {card.headline}"
    return NotifyPayload(
        channel=channel,
        title=title,
        text=_plain_text(card),
        blocks=_blocks(card, title),
        sample_id=card.sample_id,
        run_id=card.run_id,
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
    """Slack notify adapter — OFF by default, live send opt-in (T-015b, ADR-0010 §2).

    Design guarantees mirror `ClaudeTriageAgent` so the seam is safe to flip on later:
      * ``slack_sdk`` is imported lazily (it is deliberately NOT a dependency), so the
        package installs and runs without it.
      * Any error — an absent ``slack_sdk``, a missing token, an API failure — degrades to
        the offline stub. A notification problem can never break the gate or the demo.

    Live send is opt-in via ``BAYLEAF_SLACK_LIVE`` (:func:`_live_send_enabled`): posting
    to a real workspace is outward-facing, so unless it is armed every call delegates to
    the stub (payload built + recorded, no socket opened) — a configured token/channel
    alone never sends.
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

        if not _live_send_enabled():
            # PRIMARY GUARD: live Slack posting is opt-in only (ADR-0010 §2, T-015b).
            # Without BAYLEAF_SLACK_LIVE set, delegate to the offline stub — it builds +
            # records the same payload and never opens a socket, so the default demo and
            # the test suite never send even when a token/channel are configured.
            return self._fallback.notify(card)

        # --- live-send seam (reached only when BAYLEAF_SLACK_LIVE is armed) ----------
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


class _WebhookNotifier:
    """Shared base for incoming-webhook notify adapters — Teams and Discord (ADR-0010 §2).

    Mirrors :class:`SlackNotifier`'s safety shape — OFF by default, live send opt-in *per
    adapter*, degrade-to-stub on ANY error — but delivers with a stdlib
    ``urllib.request`` POST to an incoming-webhook URL instead of an SDK client. An
    incoming webhook is just an HTTP POST, so no per-vendor SDK and no new dependency are
    needed. Subclasses supply only the vendor specifics: the adapter :attr:`name`, the env
    vars for the webhook URL + the per-adapter live flag, and :meth:`_format_body` (the
    vendor's JSON envelope around the shared payload text).

    The webhook URL is a secret (it embeds an auth token): it is resolved from env, used as
    the payload's ``channel`` for traceability, and never written to a log or the SENT
    ``detail``. Like every notifier it only formats the already-decided card — it never
    sets or overrides a verdict or confidence (ADR-0001).
    """

    # Subclasses MUST set these three; the base is never instantiated directly.
    name: str
    _webhook_env: str
    _live_env: str

    def __init__(self, webhook_url: str | None = None) -> None:
        # Never hardcode the URL — resolve from env, else a clearly-unconfigured
        # placeholder so the payload stays deterministic and no socket is attempted.
        self._webhook_url = (
            webhook_url or os.environ.get(self._webhook_env) or _UNCONFIGURED_CHANNEL
        )
        self._fallback = StubNotifier(channel=self._webhook_url)

    def _format_body(self, text: str) -> dict[str, Any]:
        """Wrap the shared plain-text body in the vendor's minimal JSON envelope."""
        raise NotImplementedError

    def notify(self, card: DecisionCard) -> NotifyResult:
        if not should_notify(card):
            return _skipped_result(self.name)

        if not _flag_enabled(self._live_env) or self._webhook_url == _UNCONFIGURED_CHANNEL:
            # PRIMARY GUARD: the live POST is opt-in per adapter (its own *_LIVE flag) and
            # needs a configured URL. Unarmed OR misconfigured, delegate to the offline
            # stub — it builds + records the same payload and never opens a socket, so the
            # default demo and the test suite never send even when a URL is configured.
            return self._fallback.notify(card)

        # --- live-send seam (reached only when this adapter's *_LIVE flag is armed) ------
        payload = build_payload(card, channel=self._webhook_url)
        try:
            # The one outward-facing call, via the shared stdlib POST seam.
            _post_webhook(self._webhook_url, self._format_body(payload.text))
            return NotifyResult(
                status=NotifyStatus.SENT,
                adapter=self.name,
                payload=payload,
                # No URL in the detail — the webhook URL is a secret and is never logged.
                detail=f"{self.name}: posted via incoming webhook",
            )
        except Exception:
            # ANY failure degrades to the offline stub — never break the gate over a
            # notification (bad URL, network error, non-2xx, timeout).
            return self._fallback.notify(card)


class TeamsNotifier(_WebhookNotifier):
    """Microsoft Teams notify adapter — OFF by default, live send opt-in (ADR-0010 §2).

    Posts to a Teams *incoming webhook* (``BAYLEAF_TEAMS_WEBHOOK_URL``) as a legacy
    MessageCard ``{"text": ...}`` — the minimal shape every Teams connector renders. Live
    send is armed only by ``BAYLEAF_TEAMS_LIVE``; unarmed or unconfigured, it degrades to
    the offline stub. Slack Block Kit ``blocks`` stay Slack-specific — the shared
    plain-text body carries the same verdict/findings/evidence to every channel.
    """

    name = "teams"
    _webhook_env = _ENV_TEAMS_WEBHOOK
    _live_env = _ENV_TEAMS_LIVE

    def _format_body(self, text: str) -> dict[str, Any]:
        # Legacy MessageCard: a bare "text" is the lowest-common-denominator payload every
        # Teams incoming-webhook connector accepts without an Adaptive Card schema.
        return {"text": text}


class DiscordNotifier(_WebhookNotifier):
    """Discord notify adapter — OFF by default, live send opt-in (ADR-0010 §2).

    Posts to a Discord *webhook* (``BAYLEAF_DISCORD_WEBHOOK_URL``) as
    ``{"content": text}``, truncated to Discord's 2000-char content limit so a long card
    can't 400 the endpoint. Live send is armed only by ``BAYLEAF_DISCORD_LIVE``; unarmed
    or unconfigured, it degrades to the offline stub.
    """

    name = "discord"
    _webhook_env = _ENV_DISCORD_WEBHOOK
    _live_env = _ENV_DISCORD_LIVE

    def _format_body(self, text: str) -> dict[str, Any]:
        # Discord rejects content over 2000 chars — truncate the shared body to fit.
        return {"content": text[:_DISCORD_CONTENT_LIMIT]}


def get_notifier() -> NotifyPort:
    """Select the notifier from the environment (default: the zero-cost stub).

    Set ``BAYLEAF_NOTIFIER`` to ``slack``, ``teams``, or ``discord`` to use that adapter
    (each adapter's live send stays guarded off behind its own ``*_LIVE`` flag; unarmed it
    degrades to the stub). This is the single line that flips the notify seam.
    """
    choice = os.environ.get(_ENV_NOTIFIER, "stub").strip().lower()
    if choice == "slack":
        return SlackNotifier()
    if choice == "teams":
        return TeamsNotifier()
    if choice == "discord":
        return DiscordNotifier()
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


# Static type check: every adapter satisfies the NotifyPort protocol.
_STUB: NotifyPort = StubNotifier()
_SLACK: NotifyPort = SlackNotifier()
_TEAMS: NotifyPort = TeamsNotifier()
_DISCORD: NotifyPort = DiscordNotifier()
