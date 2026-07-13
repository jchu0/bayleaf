"""Tests for wiring the outbound notify port into `run_gate` (offline, stub-first).

The notify hook is OPTIONAL and off by default (mirrors the `repo` seam): passing a
:class:`~bayleaf.notify.StubNotifier` to `run_gate` notifies the actionable cards and
emits an auditable `notification.emitted` event per notification (ADR-0002/ADR-0010),
while passing NO notifier leaves the card list and the 16-event demo trail byte-for-byte
unchanged. These run fully offline — the stub records to an in-memory outbox and never
opens a socket, so nothing is ever sent. The new EventType is also exercised through the
persistence round-trip (project -> rebuild) so a rebuilt DB mirrors the ledger.
"""

from pathlib import Path

import pytest

from bayleaf import (
    EventLedger,
    EventType,
    SqliteRepository,
    Verdict,
    load_run,
    rebuild_db,
    run_gate,
)
from bayleaf.notify import NotifyStatus, StubNotifier
from bayleaf.persistence import read_ledger
from bayleaf.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"

# The pinned demo scenario (mirrors test_gate.py / test_persistence.py): 5 samples,
# S4 escalate + S5 hold are the two actionable cards; S1-S3 clean proceed.
_ACTIONABLE = {"S4", "S5"}
_BASELINE_EVENT_COUNT = 16  # 1 started + 5 registered + 4 findings + 5 verdicts + 1 completed


def _run(ledger=None, notifier=None, repo=None):
    """Run the gate over the pinned demo with the deterministic stub synthesizer."""
    return run_gate(
        load_run(DATA),
        synthesizer=StubSynthesizer(),
        ledger=ledger,
        notifier=notifier,
        repo=repo,
    )


# --- the notify hook fires only for actionable cards ------------------------


def test_notifier_notifies_actionable_cards_and_records_outbox():
    """A stub notifier queues exactly the actionable cards (policy skips clean PROCEED)."""
    notifier = StubNotifier()
    cards = _run(notifier=notifier)

    # Cards are unchanged in count/content; the notifier only consumed them.
    assert {c.sample_id for c in cards} == {"S1", "S2", "S3", "S4", "S5"}
    # The outbox holds one recorded payload per actionable card — nothing sent.
    assert {p.sample_id for p in notifier.outbox} == _ACTIONABLE
    assert {c.sample_id for c in cards if c.is_actionable} == _ACTIONABLE
    # Every queued payload is a recorded-not-sent stub payload.
    assert all(p.verdict in (Verdict.ESCALATE, Verdict.HOLD) for p in notifier.outbox)


def test_notifier_emits_one_notification_event_per_actionable_card():
    """Each real notification lands as an auditable `notification.emitted` event."""
    ledger = EventLedger()
    _run(ledger=ledger, notifier=StubNotifier())

    notify_events = ledger.by_type(EventType.NOTIFICATION_EMITTED)
    assert len(notify_events) == len(_ACTIONABLE)
    assert {e.sample_id for e in notify_events} == _ACTIONABLE
    # Total trail = baseline 16 + one event per actionable notification.
    assert len(ledger.events) == _BASELINE_EVENT_COUNT + len(_ACTIONABLE)
    # The completed event still brackets the decisioning; notifications follow it.
    completed_idx = next(
        i for i, e in enumerate(ledger.events) if e.event_type is EventType.ANALYSIS_RUN_COMPLETED
    )
    assert all(ledger.events.index(e) > completed_idx for e in notify_events), (
        "notifications are a post-decision dispatch, recorded after the run completes"
    )


def test_notification_event_payload_records_result_and_no_secret():
    """The event payload carries the NotifyResult facts (adapter/status) — never a token."""
    ledger = EventLedger()
    _run(ledger=ledger, notifier=StubNotifier())
    evt = ledger.by_type(EventType.NOTIFICATION_EMITTED)[0]

    assert evt.payload["adapter"] == "stub"
    assert evt.payload["status"] == NotifyStatus.PREPARED.value
    assert evt.payload["delivered"] is False  # the offline default never sends
    assert evt.payload["verdict"] in {"escalate", "hold"}
    # Guardrail: no credential-shaped keys/values ever leak into the ledger.
    blob = f"{evt.payload}".lower()
    assert not any(term in blob for term in ("token", "secret", "xoxb", "bearer"))
    # The event references the finished card in, and the built notification out.
    assert evt.inputs and evt.inputs[0].entity_type == "card"
    assert evt.outputs and evt.outputs[0].entity_type == "notification"
    assert evt.outputs[0].content_hash and len(evt.outputs[0].content_hash) == 64


# --- default flow (no notifier) is byte-for-byte unchanged ------------------


def test_no_notifier_emits_zero_notify_events_and_preserves_trail():
    """Omitting the notifier leaves the pinned 16-event demo trail exactly as before."""
    ledger = EventLedger()
    cards = _run(ledger=ledger)  # no notifier

    assert ledger.by_type(EventType.NOTIFICATION_EMITTED) == []
    assert len(ledger.events) == _BASELINE_EVENT_COUNT
    assert ledger.events[-1].event_type is EventType.ANALYSIS_RUN_COMPLETED
    # The pinned verdicts are intact.
    verdicts = {c.sample_id: c.verdict for c in cards}
    assert verdicts["S4"] is Verdict.ESCALATE
    assert verdicts["S5"] is Verdict.HOLD


def test_notifier_does_not_change_the_cards():
    """Notifying is a downstream side effect: cards are identical with/without a notifier."""
    without = _run()
    with_notifier = _run(notifier=StubNotifier())
    assert [(c.sample_id, c.verdict, c.content_hash) for c in without] == [
        (c.sample_id, c.verdict, c.content_hash) for c in with_notifier
    ]


# --- persistence round-trip handles the new EventType -----------------------


def test_notify_events_survive_persistence_round_trip(tmp_path: Path):
    """project -> rebuild carries `notification.emitted` verbatim; rebuilt DB = the ledger."""
    path = tmp_path / "run.events.jsonl"
    ledger = EventLedger(path=path)
    _run(ledger=ledger, notifier=StubNotifier())

    repo = SqliteRepository(":memory:")
    rebuild_db(path, repo)

    events = repo.list_events()
    # Full-fidelity round-trip on EVERY event (including the new notify events), in order.
    assert [e.model_dump(mode="json") for e in events] == [
        e.model_dump(mode="json") for e in read_ledger(path)
    ]
    notify_rows = [e for e in events if e.event_type is EventType.NOTIFICATION_EMITTED]
    assert len(notify_rows) == len(_ACTIONABLE)
    # The new type is a reserved-vocabulary event: recorded verbatim, but it upserts NO
    # projected row — so findings/cards/samples still mirror the demo scenario.
    assert len(repo.list_findings()) == 4
    assert len(repo.list_decision_cards()) == 5
    assert len(repo.list_samples()) == 5
    repo.close()


def test_live_repo_wiring_records_notify_events(tmp_path: Path):
    """run_gate(notifier=..., repo=...) persists the notify events through the projector."""
    path = tmp_path / "run.events.jsonl"
    ledger = EventLedger(path=path)
    repo = SqliteRepository(":memory:")
    _run(ledger=ledger, notifier=StubNotifier(), repo=repo)

    live_notify = [e for e in repo.list_events() if e.event_type is EventType.NOTIFICATION_EMITTED]
    assert len(live_notify) == len(_ACTIONABLE)
    assert len(repo.list_events()) == _BASELINE_EVENT_COUNT + len(_ACTIONABLE)
    repo.close()


@pytest.mark.parametrize("sample_id", sorted(_ACTIONABLE))
def test_each_actionable_notification_anchors_to_its_card(sample_id: str):
    """Every notify event's out-ref hash matches the built payload for that card."""
    notifier = StubNotifier()
    ledger = EventLedger()
    _run(ledger=ledger, notifier=notifier)

    evt = next(
        e for e in ledger.by_type(EventType.NOTIFICATION_EMITTED) if e.sample_id == sample_id
    )
    payload = next(p for p in notifier.outbox if p.sample_id == sample_id)
    assert evt.outputs[0].content_hash == payload.content_hash
