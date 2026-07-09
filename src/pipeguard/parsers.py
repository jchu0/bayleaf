"""Parsers that turn on-disk run artifacts into a typed `RunArtifacts` bundle.

Formats are modeled on real Illumina outputs so the demo reads as authentic to
a bioinformatician:

    sample_metadata.csv  - intake sheet (LIMS export style)
    SampleSheet.csv      - Illumina v2 sectioned sample sheet ([BCLConvert_Data])
    demux_stats.csv      - BCL Convert Demultiplex_Stats.csv style
    qc_metrics.csv       - flattened MultiQC-style per-sample metrics
    pipeline.log         - free-text pipeline log

Parsers are intentionally forgiving: a missing column becomes a None field
rather than an exception, because "missing metadata" is itself a signal the
gate is supposed to catch.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from .models import (
    DemuxRecord,
    QCMetrics,
    RunArtifacts,
    Sample,
    SampleSheetEntry,
)

# Canonical intake fields; anything else on the row is preserved in `extra`.
_KNOWN_META_FIELDS = {"sample_id", "subject_id", "tissue", "library_prep", "submitted_by"}


def _clean(value: object) -> str | None:
    """Normalize a cell to a stripped string or None (blank/NaN -> None)."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: object) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text.rstrip("%xX"))
    except ValueError:
        return None


def _to_int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def parse_sample_metadata(path: Path) -> list[Sample]:
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    samples: list[Sample] = []
    for _, row in df.iterrows():
        data = row.to_dict()
        sample_id = _clean(data.get("sample_id"))
        if sample_id is None:
            continue
        extra = {k: _clean(v) for k, v in data.items() if k not in _KNOWN_META_FIELDS}
        samples.append(
            Sample(
                sample_id=sample_id,
                subject_id=_clean(data.get("subject_id")),
                tissue=_clean(data.get("tissue")),
                library_prep=_clean(data.get("library_prep")),
                submitted_by=_clean(data.get("submitted_by")),
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    return samples


class SampleSheetHeader(NamedTuple):
    """The run-level lifecycle context carried in a sample sheet's [Header] block.

    Every field is optional: a sheet may omit any row, and a missing key stays
    `None` rather than being invented — "missing metadata" is itself a signal the
    gate is meant to surface, not a parse error.
    """

    platform: str | None  # InstrumentPlatform, e.g. "NovaSeq"
    run_date: str | None  # Date, kept as the raw ISO string (never coerced to a datetime)
    run_name: str | None  # RunName, e.g. "RUN-2026-07-07-A"


def parse_sample_sheet_header(path: Path) -> SampleSheetHeader:
    """Parse the [Header] block of an Illumina v2 sample sheet.

    Extracts the run-level context the [BCLConvert_Data] rows lack — instrument
    platform, run date, and run name — from Illumina v2 "Key,Value" header rows
    (`InstrumentPlatform,NovaSeq` / `Date,2026-07-07` / `RunName,RUN-2026-07-07-A`).
    The date is preserved as the raw string on purpose: we do NOT fabricate a
    datetime when the field is absent or malformed. Any missing key -> `None`
    (a missing field is a signal, not a crash), mirroring the other parsers here.
    """
    if not path.exists():
        return SampleSheetHeader(None, None, None)
    lines = path.read_text().splitlines()
    header_start: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower().strip("[]") == "header":
            header_start = i + 1
            break
    if header_start is None:
        return SampleSheetHeader(None, None, None)

    # Collect Key->Value pairs until the next [Section] or EOF. Keys are matched
    # case-insensitively so a differently-cased sheet still resolves.
    fields: dict[str, str | None] = {}
    for line in lines[header_start:]:
        if line.strip().startswith("["):
            break
        if not line.strip():
            continue
        # Split on the FIRST comma only, so a value containing a comma survives intact.
        key, _, value = line.partition(",")
        fields[key.strip().lower()] = _clean(value)
    return SampleSheetHeader(
        platform=fields.get("instrumentplatform"),
        run_date=fields.get("date"),
        run_name=fields.get("runname"),
    )


def parse_sample_sheet(path: Path) -> list[SampleSheetEntry]:
    """Parse the [BCLConvert_Data] (or [Data]) section of an Illumina v2 sheet."""
    lines = path.read_text().splitlines()
    data_start: int | None = None
    for i, line in enumerate(lines):
        header = line.strip().lower().strip("[]")
        if header in {"bclconvert_data", "data"}:
            data_start = i + 1
            break
    if data_start is None:
        return []

    # Collect rows until the next [Section] or EOF.
    block: list[str] = []
    for line in lines[data_start:]:
        if line.strip().startswith("["):
            break
        if line.strip():
            block.append(line)
    if not block:
        return []

    header_cols = [c.strip().lower() for c in block[0].split(",")]
    entries: list[SampleSheetEntry] = []
    for raw in block[1:]:
        cells = [c.strip() for c in raw.split(",")]
        # Tolerant zip: a row with fewer/more cells than the header is a data
        # signal handled downstream (missing sample_id -> skip), not a crash.
        record = dict(zip(header_cols, cells, strict=False))
        sample_id = _clean(record.get("sample_id"))
        if sample_id is None:
            continue
        entries.append(
            SampleSheetEntry(
                sample_id=sample_id,
                index=_clean(record.get("index")),
                index2=_clean(record.get("index2")),
            )
        )
    return entries


def parse_demux_stats(path: Path) -> list[DemuxRecord]:
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    # Tolerate the various BCL Convert header spellings.
    col_sample = _first_present(df.columns, ["sampleid", "sample_id", "sample"])
    col_index = _first_present(df.columns, ["index", "barcode"])
    col_reads = _first_present(df.columns, ["# reads", "reads", "read_count"])
    col_pct = _first_present(df.columns, ["% reads", "pct_reads", "% of reads"])
    records: list[DemuxRecord] = []
    for _, row in df.iterrows():
        sample_id = _clean(row.get(col_sample)) if col_sample else None
        if sample_id is None:
            continue
        records.append(
            DemuxRecord(
                sample_id=sample_id,
                index=_clean(row.get(col_index)) if col_index else None,
                reads=_to_int(row.get(col_reads)) if col_reads else None,
                pct_reads=_to_float(row.get(col_pct)) if col_pct else None,
            )
        )
    return records


def parse_qc_metrics(path: Path) -> list[QCMetrics]:
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    metrics: list[QCMetrics] = []
    for _, row in df.iterrows():
        sample_id = _clean(row.get("sample_id"))
        if sample_id is None:
            continue
        metrics.append(
            QCMetrics(
                sample_id=sample_id,
                q30=_to_float(row.get("q30")),
                pct_reads_identified=_to_float(row.get("pct_reads_identified")),
                mean_coverage=_to_float(row.get("mean_coverage")),
                dup_rate=_to_float(row.get("dup_rate")),
                cluster_pf=_to_float(row.get("cluster_pf")),
            )
        )
    return metrics


def parse_log(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line.strip()]


def _first_present(columns: Iterable[str], candidates: list[str]) -> str | None:
    cols = list(columns)
    return next((c for c in candidates if c in cols), None)


def load_run(run_dir: str | Path, run_id: str | None = None) -> RunArtifacts:
    """Load every artifact in a run directory into a single `RunArtifacts`."""
    run_dir = Path(run_dir)
    if run_id is None:
        run_id = run_dir.name

    def _maybe(name: str) -> Path:
        return run_dir / name

    samples = (
        parse_sample_metadata(_maybe("sample_metadata.csv"))
        if _maybe("sample_metadata.csv").exists()
        else []
    )
    sheet_path = _maybe("SampleSheet.csv")
    sheet = parse_sample_sheet(sheet_path) if sheet_path.exists() else []
    # The [Header] block carries run-level lifecycle context (platform/date/name) the
    # per-sample rows lack; parse_sample_sheet_header tolerates an absent sheet itself.
    header = parse_sample_sheet_header(sheet_path)
    demux = (
        parse_demux_stats(_maybe("demux_stats.csv")) if _maybe("demux_stats.csv").exists() else []
    )
    qc = parse_qc_metrics(_maybe("qc_metrics.csv")) if _maybe("qc_metrics.csv").exists() else []
    log = parse_log(_maybe("pipeline.log"))

    return RunArtifacts(
        run_id=run_id,
        samples=samples,
        sample_sheet=sheet,
        demux=demux,
        qc=qc,
        log_lines=log,
        platform=header.platform,
        run_date=header.run_date,
        run_name=header.run_name,
    )
