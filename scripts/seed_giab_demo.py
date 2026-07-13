"""Seed a rich set of GIAB-themed **synthetic** runs into ``data/`` for UI/UX testing.

The live app reads everything from the FastAPI read-API, which discovers a run as any DIRECT
child of ``data/`` with a ``SampleSheet.csv``. Runs, Decision cards, Provenance, Monitoring, and
the Archive index are all *derived* from those run dirs, so dropping ~24 more populates every
screen at once (pagination + status/verdict/platform facets + Monitoring windows all engage).

These are **synthetic** (``origin=contrived``, stamped by the generator) with **GIAB sample
names** (HG00x / NA2xxxx) — honest: the run data is contrived, only the sample labels are
GIAB-flavored. They never touch the genuinely-fetched ``data/RUN-2026-07-08-GIAB-HG002``
(``origin=real-giab``) or the committed ``mock_run_0x``. The generated dirs are git-ignored
(``data/RUN-*-GIAB-*/``); this script is the reproducible record — regenerate with:

    uv run python scripts/seed_giab_demo.py                 # write the run dirs
    uv run python scripts/seed_giab_demo.py --tickets       # + POST a few Review-queue tickets
                                                            #   (needs the API up on :8010)

Review-queue tickets are product state (not derived), so ``--tickets`` POSTs a handful to the
running API, referencing the real flagged samples the gate produces for the seeded runs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from bayleaf.synthetic import FailureMode as FM
from bayleaf.synthetic import RunSpec, SampleSpec, generate_run

_REPO = Path(__file__).resolve().parent.parent
_DATA = _REPO / "data"
_API = "http://localhost:8010"

# Anti-substring GIAB pool: no ID may be a substring of another (the pipeline.log rules match
# sample IDs by substring). HG00x are all 5 chars + distinct; NA2xxxx all 7 chars + distinct.
_POOL = [
    "HG001", "HG002", "HG003", "HG004", "HG005", "HG006", "HG007",
    "NA12878", "NA24385", "NA24149", "NA24143", "NA24631",
]  # fmt: skip

# One failure mode per slot → the real gate round-trips each to a known verdict, so the seeded
# runs show a realistic proceed-dominant mix with holds / reruns / escalates.
_MODES = [
    FM.CLEAN, FM.CLEAN, FM.CLEAN, FM.LOW_Q30, FM.HIGH_DUP, FM.BARCODE_SWAP,
    FM.MISSING_METADATA, FM.LOW_COVERAGE, FM.ABSENT_FROM_SHEET, FM.PIPELINE_FAILURE,
]  # fmt: skip

# Spread across ~5 weeks so Monitoring's 7/14/30d windows split (host clock is ~2026-07).
_DATES = [
    "2026-06-05", "2026-06-09", "2026-06-14", "2026-06-20", "2026-06-25", "2026-06-29",
    "2026-07-02", "2026-07-04", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09",
]  # fmt: skip

_PLATFORMS = ["NovaSeq X", "NextSeq 2000", "NovaSeq 6000", "MiSeq"]

# mode → (gate, verdict, rule_id, title) for honest ticket seeding (matches the core rule IDs).
_TICKET_FOR: dict[FM, tuple[str, str, str, str]] = {
    FM.BARCODE_SWAP: ("preflight", "escalate", "PROV-001", "Barcode mismatch vs sample sheet"),
    FM.ABSENT_FROM_SHEET: ("preflight", "escalate", "PROV-002", "Sample absent from sample sheet"),
    FM.MISSING_METADATA: ("preflight", "hold", "META-001", "Required intake metadata missing"),
    FM.LOW_Q30: ("qc", "hold", "QC-Q30", "Q30 below runbook threshold"),
    FM.LOW_COVERAGE: ("qc", "hold", "QC-MEAN_COVERAGE", "Mean coverage below threshold"),
    FM.HIGH_DUP: ("qc", "hold", "QC-DUP_RATE", "Duplication rate above threshold"),
    FM.PIPELINE_FAILURE: ("preflight", "rerun", "PIPE-001", "A pipeline step failed"),
}


def _specs() -> list[RunSpec]:
    specs: list[RunSpec] = []
    for k, date in enumerate(_DATES):
        for li, letter in enumerate(("A", "B")):  # 2 flow cells/day → 24 runs
            i0 = (k + li) % len(_POOL)
            n = 4 + (k % 4)  # 4..7 GIAB samples per run
            ids = [_POOL[(i0 + j) % len(_POOL)] for j in range(n)]
            run_idx = k * 2 + li
            # Make ~1/3 of runs all-CLEAN so they gate to 'released' — the rest carry the mode
            # mix (→ needs_review), giving the status facet a realistic released/needs-review split.
            all_clean = run_idx % 3 == 0
            samples = [
                SampleSpec(
                    sample_id=s,
                    mode=FM.CLEAN if all_clean else _MODES[(run_idx + j) % len(_MODES)],
                    subject_id=s,
                )
                for j, s in enumerate(ids)
            ]
            rid = f"RUN-{date}-GIAB-{letter}"
            specs.append(
                RunSpec(
                    run_id=rid,
                    run_name=rid,
                    date=date,
                    subject_base=5000 + k * 100,
                    platform=_PLATFORMS[(k + li) % len(_PLATFORMS)],
                    samples=samples,
                )
            )
    return specs


def _post(path: str, body: dict[str, object]) -> dict[str, object] | None:
    req = urllib.request.Request(
        f"{_API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data: dict[str, object] = json.loads(resp.read())
            return data
    except urllib.error.URLError as e:
        print(f"  ! ticket POST failed ({path}): {e} — is the API up on :8010?")
        return None


def seed_tickets(specs: list[RunSpec]) -> None:
    """POST ~8 Review-queue tickets for real flagged samples across open/in_review/resolved."""
    print("Seeding Review-queue tickets (needs the API on :8010)...")
    made = 0
    for spec in specs:
        if made >= 8:
            break
        for sample in spec.samples:
            tk = _TICKET_FOR.get(sample.mode)
            if not tk or made >= 8:
                continue
            gate, verdict, rule_id, title = tk
            ack = _post(
                "/api/review/tickets",
                {
                    "run_id": spec.run_id,
                    "sample_id": sample.sample_id,
                    "gate": gate,
                    "verdict": verdict,
                    "rule_id": rule_id,
                    "title": title,
                    "priority": "high" if verdict == "escalate" else "medium",
                },
            )
            if not ack:
                return
            # Spread across statuses: acknowledge some, resolve a hold.
            if made % 3 == 1:
                _post(f"/api/review/tickets/{ack['id']}/action", {"action": "acknowledge"})
            elif made % 3 == 2 and verdict in ("hold", "rerun"):
                _post(f"/api/review/tickets/{ack['id']}/action", {"action": "resolve"})
            made += 1
            break
    print(f"  seeded {made} tickets")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tickets", action="store_true", help="also POST Review-queue tickets (API up)"
    )
    ap.add_argument(
        "--clean", action="store_true", help="remove previously-seeded GIAB run dirs first"
    )
    args = ap.parse_args()

    specs = _specs()
    if args.clean:
        for spec in specs:
            shutil.rmtree(_DATA / spec.run_id, ignore_errors=True)

    for spec in specs:
        generate_run(spec, _DATA)
    print(f"Seeded {len(specs)} synthetic GIAB runs into {_DATA} (origin=contrived, git-ignored).")

    if args.tickets:
        seed_tickets(specs)
    else:
        print("Tip: re-run with --tickets (API up) to populate the Review queue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
