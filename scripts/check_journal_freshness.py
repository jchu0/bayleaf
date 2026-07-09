"""Soft pre-push nudge: warn (once/day, never blocking) if code shipped without a journal entry.

Part of the doc-update discipline (the ToC **Doc-update map** + CLAUDE.md "Start here"). This is
a tripwire, not a gate — the real enforcer is the session-end checklist (CLAUDE.md Documentation
rule 5). It **always exits 0**: a hard "must touch a doc" hook is satisfied by an empty stub and
trains ``--no-verify``, and many pushes legitimately need no docs (reverts, perf, test-only).

It fires at most once per calendar day (MST): if the push range touches ``src/|app/|api/|data/``
and today's ``docs/journal/<YYYY-MM-DD>-*.md`` is not added/modified in the range, it prints one
reminder line. A per-day marker under ``.git/`` debounces it so a 72-commit day nudges once, not
72 times.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

_MST = timezone(timedelta(hours=-7))  # the repo's canonical timezone (Arizona)
_CODE_PREFIXES = ("src/", "app/", "api/", "data/")
_REPO = Path(__file__).resolve().parent.parent


def _push_range() -> str:
    """The commit range being pushed — pre-commit's refs if present, else origin/main..HEAD."""
    frm = os.environ.get("PRE_COMMIT_FROM_REF")
    to = os.environ.get("PRE_COMMIT_TO_REF")
    if frm and to:
        return f"{frm}..{to}"
    return "origin/main..HEAD"


def _changed_files(rng: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", rng], capture_output=True, text=True, cwd=_REPO
        )
    except OSError:
        return []
    return [line for line in out.stdout.splitlines() if line]


def main() -> int:
    today = datetime.now(_MST).strftime("%Y-%m-%d")
    marker = _REPO / ".git" / f".journal-nudge-{today}"
    if marker.exists():
        return 0  # already nudged today — no alert-fatigue on a busy day
    files = _changed_files(_push_range())
    touched_code = any(f.startswith(_CODE_PREFIXES) for f in files)
    journal_today = any(f.startswith(f"docs/journal/{today}-") for f in files)
    if touched_code and not journal_today:
        print(
            f"[journal-freshness] This push changes code but has no docs/journal/{today}-*.md "
            "entry. If this was a substantive session, run the Session-end doc checklist "
            "(CHK-1: add a journal entry). Non-blocking; shown once per day."
        )
        with contextlib.suppress(OSError):
            marker.write_text("nudged\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
