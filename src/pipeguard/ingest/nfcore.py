"""nf-core / MultiQC ``results/`` publish dir → registry-keyed ``SampleMetrics`` (WS-03).

WHAT this closes: today the ONLY writer of the gate's metric contract is our own driver
(``scripts/run_giab_pipeline.py`` → a bespoke ``qc_metrics.csv``). A real NovaSeq/nf-core run has no
door in. This adapter reads the artifacts the germline pipeline (``pipelines/germline/main.nf``)
already publishes and turns them into ``SampleMetrics`` — one per sample — so a real ``results/``
dir can be ingested, not just the fixture CSV.

THREE design commitments (each a guardrail the review flagged):
  1. **Declared units, never guessed.** Each extractor emits its value on the tool's TRUE source
     scale and DECLARES ``raw_unit`` (fastp ``q30_rate`` is a fraction 0-1, not a pre-scaled
     percent; mosdepth mean is ``x``). The registry then normalizes — so the same logical metric
     from a fraction source and a percent source lands on the same canonical value (the pct_* trap).
  2. **``resolve_alias`` is the single fold point** (its first real, non-test call site). Every leaf
     key an extractor emits is routed through ``registry.resolve_alias`` → ``our_key``, so a MultiQC
     rename (``percent_q30``, ``20_x_pc``, ``pct_duplication`` …) folds to the stable key instead of
     silently vanishing. An unrecognized key is COLLECTED into ``unmapped`` and skipped — never
     invented, never crash (tolerant boundary; making an absent metric fail closed is WS-01's job).
  3. **Structured tool files are primary; MultiQC general-stats is secondary.** The deterministic
     ``fastp.json`` / ``mosdepth`` files win; MultiQC only fills a key a structured file did not
     provide (its namespaced general-stats headers are where key drift lives, so they are the
     alias-fed fallback and unknowns are reported loudly).

BOUNDARIES: this emits ``SampleMetrics`` only — it NEVER runs a tool and NEVER computes a verdict
(ADR-0001/0003). Lowering ``SampleMetrics`` → canonical ``MetricValue``s is
``metrics.metric_values_for``; flipping ``RunArtifacts.qc`` to hold ``SampleMetrics`` (so a real run
gates end-to-end without the transitional CSV) is WS-06·PR2 (a ``models.py`` change, out of this
scope) — see the module TODO.
"""

from __future__ import annotations

import csv
import glob
import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from ..metrics import MetricRegistry, UnknownMetricError, default_registry
from ..models import RawObservation, SampleMetrics

# --------------------------------------------------------------------------- diagnostics contract


@dataclass(frozen=True)
class UnmappedKey:
    """One honestly-surfaced diagnostic: a source key that did NOT land as a metric.

    ``reason`` distinguishes the cases so a caller (and WS-01's fail-closed gate) can tell them
    apart: ``unknown_key`` (not a registered ``our_key`` or alias), ``undeclared_unit`` (a MultiQC
    column whose scale is not declared, so we refuse to guess it), ``unit_not_allowed`` (a declared
    unit the metric's registry entry forbids), and ``absent_source`` (an expected structured file
    was missing, so the metric is a signalled hole — never a fabricated default).
    """

    sample_id: str
    leaf_key: str
    source_file: str
    reason: str


@dataclass(frozen=True)
class IngestResult:
    """The adapter's output: the per-sample metrics it COULD resolve, plus everything it could not
    (``unmapped``) — so no source key is ever silently dropped."""

    samples: list[SampleMetrics] = field(default_factory=list)
    unmapped: list[UnmappedKey] = field(default_factory=list)


# ----------------------------------------------------------------------------- internal atom


class _Observation(NamedTuple):
    """One extracted value before registry reconciliation. ``leaf_key`` is the tool-native key (an
    ``our_key`` for the deterministic structured files, or a possibly-drifted MultiQC header key);
    ``raw_unit`` is DECLARED by the extractor from the source's known scale."""

    leaf_key: str
    raw_value: float
    raw_unit: str
    source_file: str
    source_field: str | None
    source_locator: str | None


# The published per-sample globs, anchored on the ``{sample}.`` dot-prefix (mirrors
# scripts/run_giab_pipeline.py::_one_for so the two never drift). Kept tolerant here: an absent
# file is a signal (None), not the driver's fail-loud sys.exit — the adapter parses at the edge.
_FASTP_GLOB = "fastp.json"
_MOSDEPTH_SUMMARY_GLOB = "*mosdepth.summary.txt"
_MOSDEPTH_THRESHOLDS_GLOB = "*thresholds.bed.gz"
# OPTIONAL, non-default tools (WS-02 / WS-04) — verifybamid2 and hap.py are not in the germline base
# profile, so an absent output is NOT a hole (see the extract calls below), only a present one is
# scored.
_VERIFYBAMID_GLOB = "*selfSM"
_HAPPY_GLOB = "*summary.csv"


def _one_optional(results: Path, sample: str, pattern: str) -> Path | None:
    """The single published output for ``sample`` matching ``{sample}.{pattern}``, or None.

    The ``{sample}.`` dot-prefix anchors the match so ``S1`` never cross-captures ``S10``;
    ``glob.escape`` neutralizes metachars in a sample id. Absent → None (a missing file is a
    signal, not a crash).
    """
    hits = sorted(results.glob(f"{glob.escape(sample)}.{pattern}"))
    return hits[0] if hits else None


# ================================================================================ extractors


def _extract_fastp(path: Path) -> list[_Observation]:
    """fastp.json → q30 / reads-passing-filter / duplication observations, on their TRUE scales.

    Reads tolerantly: a field the report does not carry is simply not emitted (a missing metric is a
    signal, not a crash). q30_rate and duplication.rate are fractions (0-1) as fastp writes them —
    DECLARED ``fraction``, never the driver's pre-scaled percent — and reads-passing-filter is
    derived as a fraction (passed / total).
    """
    try:
        doc: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(doc, dict):
        return []

    obs: list[_Observation] = []
    src = path.name

    summary = doc.get("summary")
    after = summary.get("after_filtering") if isinstance(summary, dict) else None
    q30 = after.get("q30_rate") if isinstance(after, dict) else None
    if isinstance(q30, (int, float)):
        obs.append(
            _Observation(
                "qc.q30", float(q30), "fraction", src, "summary.after_filtering.q30_rate", None
            )
        )

    before = summary.get("before_filtering") if isinstance(summary, dict) else None
    total = before.get("total_reads") if isinstance(before, dict) else None
    filt = doc.get("filtering_result")
    passed = filt.get("passed_filter_reads") if isinstance(filt, dict) else None
    if isinstance(total, (int, float)) and total and isinstance(passed, (int, float)):
        obs.append(
            _Observation(
                "qc.reads_passing_filter",
                float(passed) / float(total),
                "fraction",
                src,
                "filtering_result.passed_filter_reads/summary.before_filtering.total_reads",
                None,
            )
        )

    dup = doc.get("duplication")
    rate = dup.get("rate") if isinstance(dup, dict) else None
    if isinstance(rate, (int, float)):
        obs.append(
            _Observation("qc.duplication", float(rate), "fraction", src, "duplication.rate", None)
        )
    return obs


def _extract_mosdepth_summary(path: Path) -> list[_Observation]:
    """mosdepth summary → mean panel coverage (the ``total_region`` row mean column, unit ``x``)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        if line.startswith("total_region\t"):
            cols = line.split("\t")
            if len(cols) > 3:
                try:
                    mean = float(cols[3])
                except ValueError:
                    return []
                return [
                    _Observation(
                        "qc.mean_target_coverage", mean, "x", path.name, "total_region.mean", None
                    )
                ]
    return []


def _extract_mosdepth_thresholds(path: Path) -> list[_Observation]:
    """mosdepth thresholds → 20x / 30x breadth as fractions (bases >=Nx / region bases)."""
    total = ge20 = ge30 = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                c = line.rstrip("\n").split("\t")
                if len(c) < 8:
                    continue
                try:
                    total += int(c[2]) - int(c[1])
                    ge20 += int(c[6])
                    ge30 += int(c[7])
                except ValueError:
                    continue
    except (OSError, gzip.BadGzipFile):
        return []
    if not total:
        return []
    return [
        _Observation("qc.breadth_20x", ge20 / total, "fraction", path.name, "ge_20x/region", None),
        _Observation("qc.breadth_30x", ge30 / total, "fraction", path.name, "ge_30x/region", None),
    ]


def _extract_verifybamid(path: Path) -> list[_Observation]:
    """verifybamid2 ``.selfSM`` → estimated contamination fraction (``FREEMIX``), unit ``fraction``.

    The FREEMIX column is located by its HEADER name (case-sensitive, as verifybamid2 writes it),
    NOT a hardcoded index, so a column-order change in a future tool version can't silently read the
    wrong field. verifybamid2 emits exactly one data row (the sample's self-check). FREEMIX is a 0-1
    fraction as written — DECLARED ``fraction``, never guessed. A missing/malformed file yields no
    observation (a signal, not a crash — CLAUDE.md data-handling).
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    header: list[str] | None = None
    for line in lines:
        if not line.strip():
            continue
        cols = line.split("\t")
        if header is None:
            # verifybamid2's header row leads with `#SEQ_ID`; strip the leading `#` off that token.
            header = [c.lstrip("#") for c in cols]
            continue
        try:
            idx = header.index("FREEMIX")
        except ValueError:
            return []  # header present but no FREEMIX column — nothing to extract, don't guess
        if idx >= len(cols):
            continue
        try:
            freemix = float(cols[idx])
        except ValueError:
            return []
        return [
            _Observation("contamination.freemix", freemix, "fraction", path.name, "freemix", None)
        ]
    return []


def _extract_happy(path: Path) -> list[_Observation]:
    """hap.py ``summary.csv`` → SNP concordance F1 (``concordance.snp_f1``), unit ``fraction``.

    hap.py writes one row per ``(Type, Filter)`` combination; concordance is read from the SNP +
    PASS row's ``METRIC.F1_Score`` (the standard "how well did we recover truth after filtering"),
    falling back to SNP + ALL when a PASS row is absent. The row is selected by (Type, Filter), NOT
    by position, so the INDEL rows can never be misread as SNP. F1 is a 0-1 fraction — DECLARED
    ``fraction``. A missing file/column/row yields no observation (a signal, not a crash).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    # csv.DictReader consumes any line iterable; splitlines() drops the trailing newline cleanly.
    snp_rows = [
        r
        for r in csv.DictReader(text.splitlines())
        if (r.get("Type") or "").strip().upper() == "SNP"
    ]

    def _row(filt: str) -> dict[str, str] | None:
        return next((r for r in snp_rows if (r.get("Filter") or "").strip().upper() == filt), None)

    row = _row("PASS")
    locator = "SNP/PASS"
    if row is None:
        row = _row("ALL")
        locator = "SNP/ALL"
    if row is None:
        return []
    raw = row.get("METRIC.F1_Score")
    if raw is None or not raw.strip():
        return []
    try:
        f1 = float(raw)
    except ValueError:
        return []
    return [_Observation("concordance.snp_f1", f1, "fraction", path.name, "snp_f1", locator)]


# MultiQC general-stats scale is read from the column HEADER's declaration (its `suffix`), never
# guessed from the key name — the pct_* trap. A `%` suffix is a percent column; an `X`/`x` suffix is
# fold coverage. A column with no declarative unit hint is reported (`undeclared_unit`) rather than
# risk a silent 100x mis-scale. This maps the declared suffix → the registry raw_unit vocabulary.
def _unit_from_multiqc_header(header: dict[str, Any]) -> str | None:
    suffix = str(header.get("suffix", "")).strip().lower()
    if "%" in suffix:
        return "percent"
    if suffix == "x":
        return "x"
    return None


def _extract_multiqc_general_stats(path: Path | None) -> dict[str, list[_Observation]]:
    """``multiqc_data/multiqc_data.json`` general-stats → per-sample observations (secondary).

    MultiQC's file carries parallel ``report_general_stats_data`` (a list, one sample→{col:value}
    dict per module) and ``report_general_stats_headers`` (the same shape, col→header metadata). We
    strip the MultiQC namespace off each column to its leaf key, and DECLARE the unit from the
    header's ``suffix`` (a column whose scale is undeclared is reported, never guessed).
    Absent/malformed file → an empty map (a signal, not a crash).
    """
    if path is None:
        return {}
    try:
        doc: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(doc, dict):
        return {}

    data = doc.get("report_general_stats_data")
    headers = doc.get("report_general_stats_headers")
    if not isinstance(data, list):
        return {}
    if not isinstance(headers, list):
        headers = []

    out: dict[str, list[_Observation]] = {}
    for idx, module in enumerate(data):
        if not isinstance(module, dict):
            continue
        raw_headers = headers[idx] if idx < len(headers) else None
        module_headers = raw_headers if isinstance(raw_headers, dict) else {}
        for sample_id, cols in module.items():
            if not isinstance(cols, dict):
                continue
            bucket = out.setdefault(str(sample_id), [])
            for col_key, value in cols.items():
                if not isinstance(value, (int, float)):
                    continue
                leaf = _strip_multiqc_namespace(str(col_key))
                header = module_headers.get(col_key)
                unit = _unit_from_multiqc_header(header if isinstance(header, dict) else {})
                # Emit even when the unit is undeclared: carry a sentinel so reconcile can report it
                # (`undeclared_unit`) instead of silently dropping — honest surfacing over guessing.
                bucket.append(
                    _Observation(
                        leaf,
                        float(value),
                        unit or "",
                        "multiqc_data.json",
                        str(col_key),
                        f"report_general_stats_data[{idx}]",
                    )
                )
    return out


def _strip_multiqc_namespace(col_key: str) -> str:
    """MultiQC general-stats column ids are namespaced like
    ``<anchor>-mqc-generalstats-<module>-<key>``; the leaf ``<key>`` is the segment after the last
    hyphen. Hyphen-free keys (``20_x_pc``, ``percent_q30``) are returned unchanged — the split is on
    the namespace separator, NOT on underscores, so a leaf key with underscores survives intact."""
    return col_key.rsplit("-", 1)[-1]


# ================================================================================ reconciliation


def _reconcile(
    sample_id: str, observations: list[_Observation], registry: MetricRegistry
) -> tuple[dict[str, RawObservation], list[UnmappedKey]]:
    """Fold ordered observations into ``{our_key -> RawObservation}`` via ``resolve_alias`` — the
    single anti-drift call site. Earlier observations win (callers pass structured-file observations
    before MultiQC), so the deterministic source is authoritative and MultiQC only fills gaps. Every
    key that does NOT land is surfaced as an ``UnmappedKey`` with a reason — never silently dropped.
    """
    resolved: dict[str, RawObservation] = {}
    unmapped: list[UnmappedKey] = []
    for obs in observations:
        try:
            our_key = registry.resolve_alias(obs.leaf_key)
        except UnknownMetricError:
            unmapped.append(UnmappedKey(sample_id, obs.leaf_key, obs.source_file, "unknown_key"))
            continue
        if our_key in resolved:
            continue  # a higher-precedence (structured) source already provided this metric
        if not obs.raw_unit:
            unmapped.append(
                UnmappedKey(sample_id, obs.leaf_key, obs.source_file, "undeclared_unit")
            )
            continue
        # Never silently mis-scale: a declared unit the entry forbids is reported, not stored.
        entry = registry.entry(our_key)
        if entry.raw_units_allowed and obs.raw_unit not in entry.raw_units_allowed:
            reason = f"unit_not_allowed:{obs.raw_unit}"
            unmapped.append(UnmappedKey(sample_id, obs.leaf_key, obs.source_file, reason))
            continue
        resolved[our_key] = RawObservation(
            raw_value=obs.raw_value,
            raw_unit=obs.raw_unit,
            source_field=obs.source_field,
            source_locator=obs.source_locator,
        )
    return resolved, unmapped


# ================================================================================ public entry


def _multiqc_json_path(results: Path) -> Path | None:
    p = results / "multiqc_data" / "multiqc_data.json"
    return p if p.is_file() else None


def ingest_results_dir(
    results: Path | str, *, registry: MetricRegistry | None = None
) -> IngestResult:
    """Ingest a published nf-core/MultiQC ``results/`` dir into one ``SampleMetrics`` per sample.

    Discovers samples from the union of ``*.fastp.json`` files and MultiQC general-stats entries, so
    a sample carried only by MultiQC (or only by the structured files) is still surfaced. Structured
    tool files are parsed first (authoritative); MultiQC general-stats fills the gaps. An expected
    structured file that is absent for a discovered sample is reported (``absent_source``), and any
    unresolved key is reported (``unknown_key`` / ``undeclared_unit`` / ``unit_not_allowed``) — the
    honest "unmapped" surface. A non-existent / empty dir yields an empty result, never a crash.

    Emits NO verdict (ADR-0001): lower the result via ``metrics.metric_values_for(sample)`` to get
    the canonical ``MetricValue``s the deterministic gate thresholds on.
    """
    results = Path(results)
    reg = registry or default_registry()
    if not results.is_dir():
        return IngestResult()

    multiqc = _extract_multiqc_general_stats(_multiqc_json_path(results))
    fastp_ids = {p.name[: -len(".fastp.json")] for p in results.glob(f"*.{_FASTP_GLOB}")}
    sample_ids = sorted(fastp_ids | set(multiqc))

    samples: list[SampleMetrics] = []
    unmapped: list[UnmappedKey] = []
    for sid in sample_ids:
        observations: list[_Observation] = []
        absent: list[UnmappedKey] = []

        # 1. Structured, deterministic tool files (authoritative) ---------------------------------
        fastp = _one_optional(results, sid, _FASTP_GLOB)
        if fastp is not None:
            observations.extend(_extract_fastp(fastp))

        summary = _one_optional(results, sid, _MOSDEPTH_SUMMARY_GLOB)
        if summary is not None:
            observations.extend(_extract_mosdepth_summary(summary))
        else:
            absent.append(UnmappedKey(sid, "qc.mean_target_coverage", "(absent)", "absent_source"))

        thresholds = _one_optional(results, sid, _MOSDEPTH_THRESHOLDS_GLOB)
        if thresholds is not None:
            observations.extend(_extract_mosdepth_thresholds(thresholds))
        else:
            absent.append(UnmappedKey(sid, "qc.breadth_20x", "(absent)", "absent_source"))
            absent.append(UnmappedKey(sid, "qc.breadth_30x", "(absent)", "absent_source"))

        # OPTIONAL add-on tools (WS-02 / WS-04) — not in the germline base profile, so their absence
        # is NOT a hole: no `absent_source` is recorded (that would flag every lean run). Only a
        # PRESENT output scores, matching the `required=False` runbook thresholds for these metrics.
        selfsm = _one_optional(results, sid, _VERIFYBAMID_GLOB)
        if selfsm is not None:
            observations.extend(_extract_verifybamid(selfsm))

        happy = _one_optional(results, sid, _HAPPY_GLOB)
        if happy is not None:
            observations.extend(_extract_happy(happy))

        # 2. MultiQC general-stats (secondary — fills only what structured files did not) ---------
        observations.extend(multiqc.get(sid, []))

        resolved, um = _reconcile(sid, observations, reg)
        samples.append(SampleMetrics(sample_id=sid, raw=resolved))
        # An "absent" structured metric is only a real hole if nothing else supplied it.
        unmapped.extend(a for a in absent if a.leaf_key not in resolved)
        unmapped.extend(um)

    return IngestResult(samples=samples, unmapped=unmapped)


# TODO (WS-03 follow-ups, deliberately NOT done here to keep this change small + honest):
#   1. LIVE INGRESS + card: a real `nextflow run` producing `results/` is env-gated (needs the
#      `hackathon` conda env + JRE + bioconda) and is NOT exercised by the offline suite — flag for
#      the maintainer's Nextflow pass. Wiring `POST /api/runs/ingest` (api/routers/intake.py) to
#      gate an ingested `results/` end-to-end needs `RunArtifacts.qc` to hold `SampleMetrics`
#      (today it is `list[QCMetrics]`, and `engine.run_gate`/`rules.evaluate_sample` iterate it);
#      that type flip is WS-06·PR2 (a `models.py` + `rules.py` change, out of this workstream's
#      scope). Until then the adapter's `SampleMetrics` is gate-READY (`metric_values_for` yields
#      the same canonical `MetricValue`s the gate thresholds on) but not yet gate-WIRED — do NOT
#      add a throwaway `SampleMetrics -> QCMetrics` inverse here (it would duplicate
#      `metrics.mapping._QCMETRICS_MAP`; keep that table single-sourced).
#   2. RUN-ROOT CONSOLIDATION: `settings.run_store_root()` is the one call-time resolver; the API's
#      remaining import-time `data/` constants (api/main.py, api/routers/files.py,
#      api/routers/pipelines_lifecycle.py) should converge onto it (the review's WS-03d) so
#      `PIPEGUARD_DATA_ROOT` is honored uniformly and no third divergent knob appears.
