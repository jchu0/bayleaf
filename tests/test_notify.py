"""Tests for the outbound notify port (offline, stub-first).

These run fully offline (no network, no Slack SDK). They pin the guarantees that make the
seam safe: the stub builds a well-formed payload for a flagged card, the notify policy
skips clean cards, the payload is deterministic, the port NEVER touches the verdict, and
`PIPEGUARD_NOTIFIER=slack` with no creds degrades to the stub instead of raising or
sending. The (deferred) live-send seam is exercised with a fake client — never the wire.
"""

from pathlib import Path

import pytest

from pipeguard import Verdict, load_run, notify_card, run_gate
from pipeguard.notify import (
    NotifyStatus,
    SlackNotifier,
    StubNotifier,
    build_payload,
    get_notifier,
    should_notify,
)
from pipeguard.notify import notifier as notify_mod
from pipeguard.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


@pytest.fixture(scope="module")
def cards():
    # Stub synthesizer keeps the demo scenario deterministic: S4=ESCALATE, S5=HOLD,
    # S1/S2/S3=PROCEED (pinned in test_gate.py).
    return {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}


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
    # Recorded to the outbox rather than sent.
    assert notifier.outbox == [payload]


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
    result = notify_card(cards["S4"])
    assert result.delivered is False
    assert result.adapter == "stub"  # degraded, not sent


def test_slack_channel_is_read_from_env_never_hardcoded(cards, monkeypatch):
    monkeypatch.setenv("PIPEGUARD_SLACK_CHANNEL", "C0EXAMPLE")
    result = SlackNotifier().notify(cards["S4"])
    assert result.payload is not None
    assert result.payload.channel == "C0EXAMPLE"  # resolved from env


def test_slack_live_seam_falls_back_to_stub_on_error(cards, monkeypatch):
    """With the (normally OFF) guard flipped on, any send error still degrades to stub."""
    monkeypatch.setattr(notify_mod, "_LIVE_SEND_ENABLED", True)
    agent = SlackNotifier()

    def _boom():
        raise RuntimeError("simulated Slack client failure")

    monkeypatch.setattr(agent, "_get_client", _boom)
    result = agent.notify(cards["S4"])
    assert result.status is NotifyStatus.PREPARED and result.adapter == "stub"
    assert result.delivered is False  # degraded, never sent


def test_slack_live_seam_missing_client_lib_falls_back_to_stub(cards, monkeypatch):
    """Guard on but slack_sdk absent (it is not a dependency): lazy import → fallback."""
    monkeypatch.setattr(notify_mod, "_LIVE_SEND_ENABLED", True)
    # No monkeypatch of _get_client: the real lazy `import slack_sdk` raises ImportError
    # (slack_sdk is intentionally not installed), which must degrade to the stub.
    result = SlackNotifier().notify(cards["S4"])
    assert result.adapter == "stub" and result.delivered is False


def test_slack_live_seam_posts_via_client_when_explicitly_enabled(cards, monkeypatch):
    """Prove the deferred wiring's SHAPE with a fake client — no real Slack API, no wire.

    This is the one place SENT can occur, and only because the module guard is flipped in
    the test AND a fake client is injected. The default demo/suite never reaches here.
    """
    monkeypatch.setattr(notify_mod, "_LIVE_SEND_ENABLED", True)

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


def test_slack_never_sends_by_default_even_with_creds(cards, monkeypatch):
    """The default guard (_LIVE_SEND_ENABLED=False) suppresses sending even if creds exist."""
    monkeypatch.setenv("PIPEGUARD_SLACK_BOT_TOKEN", "xoxb-not-a-real-token")
    monkeypatch.setenv("PIPEGUARD_SLACK_CHANNEL", "C0EXAMPLE")
    # Guard is NOT flipped here — this asserts the shipped default never delivers.
    result = SlackNotifier().notify(cards["S4"])
    assert result.delivered is False
    assert result.adapter == "stub"
