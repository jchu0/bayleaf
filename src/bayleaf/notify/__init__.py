"""Outbound notify port + adapters (ADR-0010 §2).

Stub-first and OFF the deterministic critical path (ADR-0001): turns a *flagged* decision
card into an outbound notification and never sets or overrides a verdict. Public entry
point is :func:`notify_card`; :func:`get_notifier` flips the adapter from the environment
(``BAYLEAF_NOTIFIER=stub|slack|teams|discord``, default stub). Each real adapter's live
send is opt-in via its own ``*_LIVE`` flag (``BAYLEAF_SLACK_LIVE`` / ``BAYLEAF_TEAMS_LIVE``
/ ``BAYLEAF_DISCORD_LIVE``, T-015b / T-035) — unarmed, it degrades to the stub.
"""

from .models import NotifyPayload, NotifyResult, NotifyStatus
from .notifier import (
    DiscordNotifier,
    NotifyPort,
    SlackNotifier,
    StubNotifier,
    TeamsNotifier,
    build_payload,
    get_notifier,
    notify_card,
    should_notify,
)

__all__ = [
    "DiscordNotifier",
    "NotifyPayload",
    "NotifyPort",
    "NotifyResult",
    "NotifyStatus",
    "SlackNotifier",
    "StubNotifier",
    "TeamsNotifier",
    "build_payload",
    "get_notifier",
    "notify_card",
    "should_notify",
]
