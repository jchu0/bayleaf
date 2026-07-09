"""Tests for the outbound notify port (offline, stub-first).

These run fully offline (no network, no Slack SDK). They pin the guarantees that make the
seam safe: the stub builds a well-formed payload for a flagged card, the notify policy
skips clean cards, the payload is deterministic, the port NEVER touches the verdict, and
`PIPEGUARD_NOTIFIER=slack` with no creds degrades to the stub instead of raising or
sending. The (deferred) live-send seam is exercised with a fake client — never the wire.
"""

import json
import sys
import urllib.request
from pathlib import Path

import pytest

from pipeguard import Verdict, load_run, notify_card, run_gate
from pipeguard.notify import (
    DiscordNotifier,
    NotifyStatus,
    SlackNotifier,
    StubNotifier,
    TeamsNotifier,
    build_payload,
    get_notifier,
    should_notify,
)
from pipeguard.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


@pytest.fixture(scope="module")
def cards():
    # Stub synthesizer keeps the demo scenario deterministic: S4=ESCALATE, S5=HOLD,
    # S1/S2/S3=PROCEED (pinned in test_gate.py).
    return {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}


@pytest.fixture(autouse=True)
def _disarm_live_send(monkeypatch):
    """Belt-and-suspenders: NO notify test may post to a real workspace/channel — even on a
    machine whose shell or .env has a ``*_LIVE`` flag + real creds set. Every adapter's live
    send is env-armed, so we force ALL of them off for every test; the few tests that
    exercise a live seam re-arm one explicitly (after this autouse fixture runs)."""
    monkeypatch.delenv("PIPEGUARD_SLACK_LIVE", raising=False)
    monkeypatch.delenv("PIPEGUARD_TEAMS_LIVE", raising=False)
    monkeypatch.delenv("PIPEGUARD_DISCORD_LIVE", raising=False)


# --- notify policy ----------------------------------------------------------


def test_notify_policy_notifies_only_actionable_cards(cards):
    """Policy: notify HOLD/RERUN/ESCALATE; skip clean PROCEED. Grounded in is_actionable."""
    assert should_notify(cards["S4"]) is True  # ESCALATE
    assert should_notify(cards["S5"]) is True  # HOLD
    assert should_notify(cards["S1"]) is False  # clean PROCEED
    # One definition of the policy — never diverges from the card's own property.
    for card in cards.values():
        assert should_notify(card) == card.is_actionable


def test_clean_proceed_card_is_skipped_and_not_recorded(cards):
    notifier = StubNotifier()
    result = notifier.notify(cards["S1"])  # clean PROCEED
    assert result.status is NotifyStatus.SKIPPED
    assert result.payload is None
    assert result.delivered is False
    assert notifier.outbox == []  # nothing recorded for a clean card


# --- the stub: a well-formed, recorded payload ------------------------------


def test_stub_builds_wellformed_payload_for_flagged_card(cards):
    s4 = cards["S4"]
    notifier = StubNotifier()
    result = notifier.notify(s4)

    assert result.status is NotifyStatus.PREPARED
    assert result.adapter == "stub"
    assert result.delivered is False
    payload = result.payload
    assert payload is not None
    # Title carries the deterministic verdict + sample.
    assert payload.title.startswith("[ESCALATE] S4")
    assert payload.sample_id == "S4"
    assert payload.verdict is Verdict.ESCALATE
    assert payload.headline == s4.headline
    # Text body is non-empty, lists the findings, and carries the research/demo caveat.
    assert s4.headline in payload.text
    assert "Findings:" in payload.text
    assert "not a clinical decision" in payload.text
    # Blocks are Slack-shaped: a header first, every block a typed dict.
    assert payload.blocks and payload.blocks[0]["type"] == "header"
    assert all("type" in b for b in payload.blocks)
    # Enriched: carries the run id, the category-specific guidance, and the observed-vs-
    # expected evidence numbers an operator needs.
    assert payload.run_id == "mock_run_01"
    assert "mock_run_01" in payload.text
    assert "Provenance / identity risk" in payload.text  # ESCALATE framing
    assert "observed" in payload.text  # evidence numbers surfaced
    # Recorded to the outbox rather than sent.
    assert notifier.outbox == [payload]


def test_payload_is_category_specific_by_verdict(cards):
    """Message content is tailored per verdict category, each with run id + evidence."""
    esc = build_payload(cards["S4"], channel="stub")  # ESCALATE (provenance/identity)
    hold = build_payload(cards["S5"], channel="stub")  # HOLD (borderline QC)
    assert "identity risk" in esc.text.lower()  # provenance/identity framing
    assert "operator judgment" in hold.text.lower()  # borderline-QC framing
    assert esc.text != hold.text  # genuinely different messages per category
    for p in (esc, hold):
        assert p.run_id == "mock_run_01"
        assert "observed" in p.text  # observed-vs-expected evidence


def test_payload_reflects_the_cards_verdict_not_a_new_one(cards):
    """The port copies the gate's verdict; it never computes or overrides one (ADR-0001)."""
    for sid in ("S4", "S5"):
        card = cards[sid]
        before = card.verdict
        payload = build_payload(card, channel="stub")
        assert payload.verdict is card.verdict  # copied, not decided
        assert card.verdict is before  # notifying does not mutate the card
        # The payload has no confidence field to smuggle certainty through.
        assert "confidence" not in payload.model_dump()


def test_payload_is_deterministic(cards):
    """Identical cards yield an identical payload + content_hash (offline reproducibility)."""
    a = StubNotifier().notify(cards["S4"]).payload
    b = StubNotifier().notify(cards["S4"]).payload
    assert a is not None and b is not None
    assert a == b
    assert len(a.content_hash) == 64
    assert a.content_hash == b.content_hash


# --- the factory + public entry point ---------------------------------------


def test_get_notifier_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("PIPEGUARD_NOTIFIER", raising=False)
    assert isinstance(get_notifier(), StubNotifier)


def test_get_notifier_selects_slack_from_env(monkeypatch):
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "slack")
    assert isinstance(get_notifier(), SlackNotifier)


def test_get_notifier_unknown_value_falls_back_to_stub(monkeypatch):
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "carrier-pigeon")
    assert isinstance(get_notifier(), StubNotifier)


def test_notify_card_entry_point_uses_env_notifier_and_injection(cards, monkeypatch):
    monkeypatch.delenv("PIPEGUARD_NOTIFIER", raising=False)
    # Default (env-selected) path: the stub prepares a flagged card.
    result = notify_card(cards["S4"])
    assert result.adapter == "stub" and result.status is NotifyStatus.PREPARED
    # Injected notifier is respected (records to the injected outbox).
    injected = StubNotifier()
    notify_card(cards["S5"], notifier=injected)
    assert len(injected.outbox) == 1 and injected.outbox[0].sample_id == "S5"


# --- the Slack adapter: OFF by default, degrades safely, never sends ---------


def test_slack_with_no_creds_falls_back_to_stub_without_sending(cards, monkeypatch):
    """Slack selected + no creds: degrades to the stub, does not raise, does not send."""
    monkeypatch.delenv("PIPEGUARD_SLACK_CHANNEL", raising=False)
    monkeypatch.delenv("PIPEGUARD_SLACK_BOT_TOKEN", raising=False)
    result = SlackNotifier().notify(cards["S4"])
    assert result.status is NotifyStatus.PREPARED  # payload built...
    assert result.adapter == "stub"  # ...by the stub fallback
    assert result.delivered is False  # never a real send
    assert result.payload is not None
    # Channel stays deterministic when unconfigured.
    assert result.payload.channel == "unconfigured"


def test_slack_env_path_degrades_and_does_not_send(cards, monkeypatch):
    """PIPEGUARD_NOTIFIER=slack end-to-end via the public entry point never delivers."""
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "slack")
    monkeypatch.delenv("PIPEGUARD_SLACK_BOT_TOKEN", raising=False)

    # Spy: with the guard at its shipped default, the client seam must never be reached
    # (proves "no socket", not just "result looks like a stub").
    def _fail_if_called(self):
        raise AssertionError("_get_client must not be called on the default (guard-off) path")

    monkeypatch.setattr(SlackNotifier, "_get_client", _fail_if_called)
    result = notify_card(cards["S4"])
    assert result.delivered is False
    assert result.adapter == "stub"  # degraded, not sent


def test_slack_channel_is_read_from_env_never_hardcoded(cards, monkeypatch):
    monkeypatch.setenv("PIPEGUARD_SLACK_CHANNEL", "C0EXAMPLE")
    result = SlackNotifier().notify(cards["S4"])
    assert result.payload is not None
    assert result.payload.channel == "C0EXAMPLE"  # resolved from env


def test_slack_live_seam_falls_back_to_stub_on_error(cards, monkeypatch):
    """With live send armed, any send error still degrades to stub."""
    monkeypatch.setenv("PIPEGUARD_SLACK_LIVE", "1")
    agent = SlackNotifier()

    def _boom():
        raise RuntimeError("simulated Slack client failure")

    monkeypatch.setattr(agent, "_get_client", _boom)
    result = agent.notify(cards["S4"])
    assert result.status is NotifyStatus.PREPARED and result.adapter == "stub"
    assert result.delivered is False  # degraded, never sent


def test_slack_live_seam_missing_client_lib_falls_back_to_stub(cards, monkeypatch):
    """Live armed but slack_sdk absent: the lazy import raises ImportError → stub fallback."""
    monkeypatch.setenv("PIPEGUARD_SLACK_LIVE", "1")
    # Force `import slack_sdk` to fail regardless of the developer's environment (a None
    # entry in sys.modules makes the import raise ImportError) and drop any token — so this
    # test can NEVER build a real client or touch the wire, even on a machine that happens
    # to have slack_sdk installed with a token in a local .env.
    monkeypatch.setitem(sys.modules, "slack_sdk", None)
    monkeypatch.delenv("PIPEGUARD_SLACK_BOT_TOKEN", raising=False)
    result = SlackNotifier().notify(cards["S4"])
    assert result.adapter == "stub" and result.delivered is False


def test_slack_live_seam_posts_via_client_when_explicitly_enabled(cards, monkeypatch):
    """Prove the deferred wiring's SHAPE with a fake client — no real Slack API, no wire.

    This is the one place SENT can occur, and only because live send is armed in the test
    AND a fake client is injected. The default demo/suite never reaches here.
    """
    monkeypatch.setenv("PIPEGUARD_SLACK_LIVE", "1")

    class _FakeSlackClient:
        def __init__(self):
            self.calls: list[dict] = []

        def chat_postMessage(self, **kwargs):
            self.calls.append(kwargs)
            return {"ok": True}

    fake = _FakeSlackClient()
    agent = SlackNotifier(channel="C0EXAMPLE")
    monkeypatch.setattr(agent, "_get_client", lambda: fake)

    result = agent.notify(cards["S4"])
    assert result.status is NotifyStatus.SENT
    assert result.adapter == "slack" and result.delivered is True
    # The seam passes exactly the payload's channel/text/blocks to the client.
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["channel"] == "C0EXAMPLE"
    assert result.payload is not None
    assert call["text"] == result.payload.text
    assert call["blocks"] == result.payload.blocks


def test_slack_never_sends_when_not_armed_even_with_creds(cards, monkeypatch):
    """With PIPEGUARD_SLACK_LIVE unset, a token + channel alone never trigger a send."""
    monkeypatch.setenv("PIPEGUARD_SLACK_BOT_TOKEN", "xoxb-not-a-real-token")
    monkeypatch.setenv("PIPEGUARD_SLACK_CHANNEL", "C0EXAMPLE")
    # (the autouse fixture already ensures PIPEGUARD_SLACK_LIVE is unset)
    agent = SlackNotifier()

    # Spy: the client seam must never be touched when live send isn't armed, even with
    # creds present — this directly proves "no send", not just a stub-shaped result.
    def _fail_if_called():
        raise AssertionError("_get_client must not be called when live send is not armed")

    monkeypatch.setattr(agent, "_get_client", _fail_if_called)
    # Live send is NOT armed here — this asserts the shipped default never delivers.
    result = agent.notify(cards["S4"])
    assert result.delivered is False
    assert result.adapter == "stub"


# --- the webhook adapters (Teams / Discord): OFF by default, never send unless armed ---


class _RecordingOpener:
    """A fake ``urllib.request.urlopen`` — records each Request and returns a 200-like
    response. Injected as the outbound seam so the webhook live path is exercised WITHOUT
    a socket, and so a test can prove the default path never calls it at all."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request, timeout=None):  # matches urlopen(request, timeout=...)
        self.requests.append(request)
        return self

    # Context-manager + read() so it slots into `with urlopen(...) as r: r.read()`.
    def read(self) -> bytes:
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# (adapter class, its live-arm env var, the vendor's JSON body key) — one row per webhook
# adapter so every guarantee below is asserted identically for Teams and Discord.
_WEBHOOK_ADAPTERS = [
    (TeamsNotifier, "PIPEGUARD_TEAMS_LIVE", "PIPEGUARD_TEAMS_WEBHOOK_URL", "text"),
    (DiscordNotifier, "PIPEGUARD_DISCORD_LIVE", "PIPEGUARD_DISCORD_WEBHOOK_URL", "content"),
]


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_with_no_url_falls_back_to_stub_without_sending(
    cards, monkeypatch, adapter_cls, live_env, url_env, body_key
):
    """Webhook adapter, no URL configured: degrades to the stub, does not raise, no send."""
    monkeypatch.delenv(url_env, raising=False)
    result = adapter_cls().notify(cards["S4"])
    assert result.status is NotifyStatus.PREPARED  # payload built...
    assert result.adapter == "stub"  # ...by the stub fallback
    assert result.delivered is False  # never a real send
    assert result.payload is not None
    # Channel stays a deterministic placeholder when unconfigured (never a secret URL).
    assert result.payload.channel == "unconfigured"


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_never_opens_socket_when_not_armed(
    cards, monkeypatch, adapter_cls, live_env, url_env, body_key
):
    """A URL is configured but the live flag is NOT armed (autouse disarms it): the urlopen
    seam is never touched — this directly proves 'no socket', not just a stub-shaped result."""
    opener = _RecordingOpener()
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    result = adapter_cls(webhook_url="https://example.test/hook").notify(cards["S4"])
    assert opener.requests == []  # the outbound seam was never reached
    assert result.status is NotifyStatus.PREPARED and result.adapter == "stub"
    assert result.delivered is False


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_url_read_from_env_never_hardcoded(
    cards, monkeypatch, adapter_cls, live_env, url_env, body_key
):
    """The webhook URL is resolved from env (used as the payload channel), never hardcoded."""
    monkeypatch.setenv(url_env, "https://env.example.test/hook")
    result = adapter_cls().notify(cards["S4"])  # unarmed → stub, but channel resolved from env
    assert result.payload is not None
    assert result.payload.channel == "https://env.example.test/hook"


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_live_seam_posts_via_fake_opener(
    cards, monkeypatch, adapter_cls, live_env, url_env, body_key
):
    """Prove the live wiring's SHAPE with a fake opener — no real HTTP, no wire.

    This is the one place SENT can occur for a webhook adapter, and only because its live
    flag is armed in the test AND a fake urlopen is injected. The default demo/suite never
    reaches here.
    """
    monkeypatch.setenv(live_env, "1")
    opener = _RecordingOpener()
    monkeypatch.setattr(urllib.request, "urlopen", opener)

    url = "https://example.test/hooks/abc123"
    result = adapter_cls(webhook_url=url).notify(cards["S4"])

    assert result.status is NotifyStatus.SENT
    assert result.adapter == adapter_cls.name and result.delivered is True
    assert result.payload is not None
    # Exactly one POST, to the configured URL, carrying the vendor's JSON envelope.
    assert len(opener.requests) == 1
    req = opener.requests[0]
    assert req.full_url == url
    assert req.get_method() == "POST"
    body = json.loads(req.data)
    assert set(body) == {body_key}  # only the vendor's single body field
    assert body[body_key] == result.payload.text  # the shared body (demo text < 2000)
    # The webhook URL is a secret — it must never appear in the human-readable detail.
    assert url not in result.detail


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_live_seam_degrades_to_stub_on_error(
    cards, monkeypatch, adapter_cls, live_env, url_env, body_key
):
    """With the live flag armed, any POST error still degrades to the stub — never breaks."""
    monkeypatch.setenv(live_env, "1")

    def _boom(request, timeout=None):
        raise RuntimeError("simulated webhook failure")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    result = adapter_cls(webhook_url="https://example.test/hook").notify(cards["S4"])
    assert result.status is NotifyStatus.PREPARED and result.adapter == "stub"
    assert result.delivered is False  # degraded, never sent


@pytest.mark.parametrize("adapter_cls, live_env, url_env, body_key", _WEBHOOK_ADAPTERS)
def test_webhook_clean_card_is_skipped_by_policy(cards, adapter_cls, live_env, url_env, body_key):
    """A clean PROCEED card is skipped by the shared notify policy for webhook adapters too."""
    result = adapter_cls(webhook_url="https://example.test/hook").notify(cards["S1"])
    assert result.status is NotifyStatus.SKIPPED
    assert result.payload is None and result.delivered is False


def test_webhook_payload_is_deterministic_with_url_channel(cards):
    """Identical cards + URL yield an identical payload + content_hash (offline repro)."""
    url = "https://example.test/hook"
    a = build_payload(cards["S4"], channel=url)
    b = build_payload(cards["S4"], channel=url)
    assert a == b
    assert a.content_hash == b.content_hash and len(a.content_hash) == 64
    assert a.channel == url


def test_discord_body_truncates_to_discord_2000_char_limit():
    """Discord caps content at 2000 chars; the adapter truncates so a long card can't 400."""
    body = DiscordNotifier(webhook_url="https://example.test/hook")._format_body("x" * 5000)
    assert set(body) == {"content"}
    assert len(body["content"]) == 2000


def test_teams_body_is_legacy_messagecard_text():
    """Teams gets the lowest-common-denominator MessageCard shape: a bare {"text": ...}."""
    body = TeamsNotifier(webhook_url="https://example.test/hook")._format_body("hello")
    assert body == {"text": "hello"}


def test_get_notifier_selects_teams_from_env(monkeypatch):
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "teams")
    assert isinstance(get_notifier(), TeamsNotifier)


def test_get_notifier_selects_discord_from_env(monkeypatch):
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "discord")
    assert isinstance(get_notifier(), DiscordNotifier)


# --- the `python -m pipeguard.notify` CLI ------------------------------------


def test_notify_cli_gates_and_reports_actionable(monkeypatch, capsys):
    """The CLI gates a run and reports its actionable cards via the env-selected notifier."""
    monkeypatch.setenv("PIPEGUARD_NOTIFIER", "stub")  # never live in tests
    from pipeguard.notify.__main__ import main

    assert main([str(DATA)]) == 0
    out = capsys.readouterr().out
    assert "2 actionable" in out  # mock_run_01: S4 escalate + S5 hold
    assert "notified S4" in out and "notified S5" in out
    assert "Notifier: stub" in out


def test_notify_cli_no_args_returns_usage(capsys):
    from pipeguard.notify.__main__ import main

    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err
