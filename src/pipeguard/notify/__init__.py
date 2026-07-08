"""Outbound notify port + adapters (ADR-0010 §2).

Stub-first and OFF the deterministic critical path (ADR-0001): turns a *flagged* decision
card into an outbound notification and never sets or overrides a verdict. Public entry
point is :func:`notify_card`; :func:`get_notifier` flips the adapter from the environment
(``PIPEGUARD_NOTIFIER=stub|slack``, default stub). The Slack adapter's live send is
deferred (out of scope, T-015b) — it degrades to the stub until maintainer sign-off.
"""

from .models import NotifyPayload, NotifyResult, NotifyStatus
from .notifier import (
    NotifyPort,
    SlackNotifier,
    StubNotifier,
    build_payload,
    get_notifier,
    notify_card,
    should_notify,
)

__all__ = [
    "NotifyPayload",
    "NotifyPort",
    "NotifyResult",
    "NotifyStatus",
    "SlackNotifier",
    "StubNotifier",
    "build_payload",
    "get_notifier",
    "notify_card",
    "should_notify",
]
