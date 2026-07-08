"""CLI: gate a run directory and dispatch notifications via the env-selected notifier.

    uv run python -m pipeguard.notify data/mock_run_01

Loads ``.env`` (so ``PIPEGUARD_*`` are in the environment *before* the notifier resolves
its channel/token), runs the gate, and notifies each actionable card through the notifier
chosen by ``PIPEGUARD_NOTIFIER`` (``stub`` by default — $0, offline, nothing leaves the
machine). Live Slack posting additionally needs ``PIPEGUARD_SLACK_LIVE=1`` + a bot
token/channel (see ``.env.example``). Safe by default: with no env set, this only prints.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ..engine import run_gate_from_dir
from ..models import DecisionCard
from .notifier import get_notifier, should_notify


def main(argv: Sequence[str] | None = None) -> int:
    """Gate ``argv[0]`` and notify its actionable cards; return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m pipeguard.notify <run_dir>", file=sys.stderr)
        return 2
    run_dir = args[0]

    # Load .env before constructing the notifier so a Slack channel/token in .env is
    # visible when SlackNotifier resolves them in __init__ (dotenv ships with the
    # slack/claude extras; plain env vars work without it).
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    notifier = get_notifier()
    _, cards = run_gate_from_dir(run_dir, notifier=notifier)
    actionable: list[DecisionCard] = [c for c in cards if should_notify(c)]

    print(f"Gated {run_dir}: {len(cards)} sample(s), {len(actionable)} actionable.")
    print(f"Notifier: {notifier.name}  (live send armed only via PIPEGUARD_SLACK_LIVE)")
    for card in actionable:
        print(f"  notified {card.sample_id} [{card.verdict.value}] — {card.headline}")
    if not actionable:
        print("  nothing to notify — every sample cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
