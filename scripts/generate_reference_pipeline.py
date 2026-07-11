"""Regenerate ``pipelines/germline/`` from the seeded germline card graph.

The committed reference pipeline is exactly the compiler's output for the Builder's seeded germline
template (``pipeguard.nextflow.germline_graph``), so there is one source of truth and a drift test
(``tests/test_nextflow_compile.py``) pins it. Run this after changing the catalog or the seeded
graph; the drift test fails until you do.

    uv run python scripts/generate_reference_pipeline.py
"""

from __future__ import annotations

from pathlib import Path

from pipeguard.nextflow import compile_graph, germline_graph

_ROOT = Path(__file__).resolve().parent.parent / "pipelines" / "germline"


def main() -> None:
    bundle = compile_graph(germline_graph())
    generated = set(bundle.files)
    # Remove any stale generated file first (a renamed module must not linger).
    if _ROOT.is_dir():
        for p in _ROOT.rglob("*"):
            if p.is_file() and str(p.relative_to(_ROOT)) not in generated:
                p.unlink()
    for rel, content in bundle.files.items():
        out = _ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
    print(f"wrote {len(bundle.files)} files to {_ROOT}")


if __name__ == "__main__":
    main()
