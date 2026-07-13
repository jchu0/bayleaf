"""Package CLI: ``python -m bayleaf.synthetic`` — regenerate demo data, at scale.

Subcommands:

* ``demo`` (the default when none is given) — regenerate every committed run (the two
  demo stories *and* the ~30-sample scale run) into ``data/``. Byte-reproducible.
* ``scale`` — generate one large N-sample run (default: the committed 30-sample run).
* ``bulk`` — generate many runs into a git-ignored directory (``data/synthetic_bulk``),
  the on-demand volume the frontend's scale affordances test against. Never committed.

Kept as a thin module distinct from ``generator`` so ``runpy`` does not re-import a
module the package ``__init__`` already loaded — the same reason the older
``python -m bayleaf.synthetic.generator`` form emits a ``RuntimeWarning``. All
rendering and the mode/verdict contract live in ``generator`` + ``scale``; this file is
only argument plumbing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .generator import _default_data_dir, generate_run
from .scale import (
    BULK_DIR_NAME,
    COMMITTED_SCALE_RUN_ID,
    COMMITTED_SCALE_SEED,
    build_scale_spec,
    generate_bulk,
    generate_committed,
)


def _cmd_demo(args: argparse.Namespace) -> None:
    """Regenerate the committed runs (demo stories + scale run) into the target dir."""
    out_dir: Path = args.out or _default_data_dir()
    for run_dir in generate_committed(out_dir):
        print(f"wrote {run_dir}")


def _cmd_scale(args: argparse.Namespace) -> None:
    """Generate one large N-sample run (defaults to the committed scale run)."""
    out_dir: Path = args.out or _default_data_dir()
    spec = build_scale_spec(
        args.samples,
        run_id=args.run_id,
        run_name=args.run_name,
        date=args.date,
        seed=args.seed,
    )
    run_dir = generate_run(spec, out_dir)
    print(f"wrote {run_dir} ({len(spec.samples)} samples)")


def _cmd_bulk(args: argparse.Namespace) -> None:
    """Generate ``--count`` runs into a git-ignored dir (regenerable, not committed)."""
    out_dir: Path = args.out or (_default_data_dir() / BULK_DIR_NAME)
    run_dirs = generate_bulk(out_dir, args.count, samples_per_run=args.samples, seed=args.seed)
    print(f"wrote {len(run_dirs)} runs under {out_dir} ({args.samples} samples each)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bayleaf.synthetic",
        description="Generate contrived NovaSeq demo runs (single, at scale, or in bulk).",
    )
    sub = parser.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="Regenerate every committed run into data/ (the default).")
    demo.add_argument("--out", type=Path, default=None, help="Output dir (default: repo data/).")
    demo.set_defaults(func=_cmd_demo)

    scale = sub.add_parser("scale", help="Generate one large N-sample run.")
    scale.add_argument("--samples", type=int, default=30, help="Sample count (default: 30).")
    scale.add_argument("--out", type=Path, default=None, help="Output dir (default: repo data/).")
    scale.add_argument("--run-id", default=COMMITTED_SCALE_RUN_ID, help="Run directory name.")
    scale.add_argument("--run-name", default="RUN-2026-07-09-SCALE", help="Illumina RunName.")
    scale.add_argument("--date", default="2026-07-09", help="ISO run date (YYYY-MM-DD).")
    scale.add_argument(
        "--seed", type=int, default=COMMITTED_SCALE_SEED, help="Failure-spread seed."
    )
    scale.set_defaults(func=_cmd_scale)

    bulk = sub.add_parser(
        "bulk", help=f"Generate many runs into a git-ignored dir (data/{BULK_DIR_NAME})."
    )
    bulk.add_argument("--count", type=int, default=24, help="Number of runs (default: 24).")
    bulk.add_argument("--samples", type=int, default=12, help="Samples per run (default: 12).")
    bulk.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output dir (default: data/{BULK_DIR_NAME}, git-ignored).",
    )
    bulk.add_argument("--seed", type=int, default=0, help="Base seed (each run uses seed+i).")
    bulk.set_defaults(func=_cmd_bulk)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point. No subcommand behaves like ``demo`` for backward compatibility."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        # Bare ``python -m bayleaf.synthetic`` -> regenerate the committed runs, the
        # behavior documented in data/README.md before scale subcommands existed.
        _cmd_demo(argparse.Namespace(out=None))
        return
    args.func(args)


if __name__ == "__main__":
    main()
