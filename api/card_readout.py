"""Decision-card QC readout — an API-LAYER PROJECTION over an already-decided card.

This module joins two things the deterministic gate *already produced* — a
:class:`~pipeguard.models.DecisionCard`'s ``metric_values`` (registry-normalized QC numbers)
and the :class:`~pipeguard.runbook.Runbook`'s ``qc_thresholds`` — into the gate-grouped,
flagged-first table the design's Decision card wants. It is a **pure re-presentation**:

  * It NEVER sets, moves, or second-guesses a verdict / finding / confidence (ADR-0001);
    the gate is the sole authority and stays byte-for-byte untouched.
  * Its ``status`` is derived to *mirror* the QC rule (`pipeguard.rules`) exactly, so the
    readout can never contradict the finding the gate emitted for the same metric:
    ``pass`` ⟺ the gate passed (no finding), ``fail`` ⟺ a CRITICAL hard-fail finding,
    ``borderline`` ⟺ a WARN finding (whether a near-miss or a clear miss of the gate).
  * Direction (``>=`` / ``<=``) comes from the runbook's ``higher_is_better`` flag — an
    authoritative field, not a guess. A metric with no matching threshold is surfaced as
    ``not_gated`` with ``UNKNOWN`` direction rather than fabricating one.

Everything here is additive and off the deterministic critical path: importing it, calling it,
or wiring the optional :data:`router` changes no gate behavior. It is framework-light on purpose
(the projection functions take only ``card`` + ``runbook`` and touch no I/O), so they are trivially
unit-testable; the optional router is the thin HTTP side-channel over them.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pipeguard import DecisionCard, Runbook, run_gate_from_dir
from pipeguard.metrics import default_registry
from pipeguard.models import CanonicalUnit, Gate, MetricValue, Sample, Verdict
from pipeguard.runbook import DEFAULT_RUNBOOK, QCThreshold


def _display_name(our_key: str) -> str:
    """The registry's human display name for a metric (fallback: the key itself). Used to label an
    ungated row nicely; the registry is loaded once + cached, so this stays free of per-call I/O."""
    try:
        return default_registry().entry(our_key).display_name
    except Exception:
        return our_key


# --- Vocabulary -----------------------------------------------------------------------------


class ReadoutStatus(str, Enum):
    """Per-metric readout status. Deliberately mirrors the QC rule's three outcomes plus a
    fourth honest state for a metric the runbook does not gate (so we never invent a verdict).
    """

    PASS = "pass"  # value satisfied the gate — the rule emits no finding
    BORDERLINE = "borderline"  # value missed the gate but did not hard-fail — a WARN finding
    FAIL = "fail"  # value is past hard_fail — a CRITICAL finding
    NOT_GATED = "not_gated"  # no runbook threshold for this metric — cannot classify


class Direction(str, Enum):
    """Comparison direction for a metric's gate, taken from the runbook (never guessed)."""

    AT_LEAST = ">="  # higher_is_better: value must be >= gate
    AT_MOST = "<="  # lower_is_better: value must be <= gate
    UNKNOWN = "?"  # no threshold → direction is not derivable; surfaced, not fabricated


# Display symbol to fall back to when a metric is ungated (no runbook `unit` to borrow). The
# runbook's `unit` is the authoritative display symbol otherwise (runbook.py units contract).
_CANONICAL_SYMBOL: dict[CanonicalUnit, str] = {
    CanonicalUnit.FRACTION: "",
    CanonicalUnit.PERCENT: "%",
    CanonicalUnit.X: "x",
    CanonicalUnit.RATIO: "",
    CanonicalUnit.PHRED: "",
    CanonicalUnit.COUNT: "",
    CanonicalUnit.BOOL: "",
}

# Flagged-first ordering within a gate group: failures first, then borderline, then clean
# passes, and ungated (uninterpretable) rows last so attention lands where it is needed.
_STATUS_ORDER: dict[ReadoutStatus, int] = {
    ReadoutStatus.FAIL: 0,
    ReadoutStatus.BORDERLINE: 1,
    ReadoutStatus.PASS: 2,
    ReadoutStatus.NOT_GATED: 3,
}

_GATE_ORDER: tuple[Gate, ...] = (Gate.PREFLIGHT, Gate.QC, Gate.VARIANT)

# Gate DEPENDENCY chain (maintainer's two-tier model): sequencing-tier QC (preflight — PhiX, reads
# PF, cluster PF) gates sample PROCESSING, and sample-tier QC (coverage/depth/breadth) gates
# DOWNSTREAM analysis (variant). So each gate depends on every gate before it: if an upstream gate
# is not clear, the downstream one is "blocked — clear <upstream> first" rather than "all clear".
_GATE_DEP_ORDER: tuple[Gate, ...] = (Gate.PREFLIGHT, Gate.QC, Gate.VARIANT)


def _blocking_gate(gate: Gate, unclear: set[Gate]) -> Gate | None:
    """The nearest UPSTREAM gate that is not clear (so it gates ``gate`` downstream), else None."""
    if gate not in _GATE_DEP_ORDER:
        return None
    idx = _GATE_DEP_ORDER.index(gate)
    for up in reversed(_GATE_DEP_ORDER[:idx]):  # nearest upstream wins
        if up in unclear:
            return up
    return None


# --- Projection models ----------------------------------------------------------------------


class MetricReadout(BaseModel):
    """One metric's row in the readout: what was observed vs. what the runbook expects.

    ``observed_value`` is the card's canonical ``normalized_value`` (lossless); ``observed_display``
    renders it back into the operator-facing unit (e.g. ``89.9%``). The threshold strings are the
    gate boundary (``threshold_display``, e.g. ``>= 30x``) and the hard-fail boundary
    (``hard_fail_display``) so an operator sees both the target and the critical line.
    """

    metric: str = Field(..., description="Registry `our_key` — the join key card↔runbook")
    label: str = Field(..., description="Human label from the runbook (or the key if ungated)")
    gate: Gate = Field(..., description="Pipeline gate this metric belongs to (from the card)")
    status: ReadoutStatus
    direction: Direction

    observed_value: float = Field(..., description="Canonical normalized_value (lossless)")
    canonical_unit: CanonicalUnit
    observed_unit: str = Field(..., description="Operator-facing display symbol (e.g. %, x)")
    observed_display: str = Field(..., description="Rendered observed value, e.g. '89.9%'")

    threshold_display: str | None = Field(
        None, description="Gate boundary in display terms, e.g. '>= 30x' (None if ungated)"
    )
    hard_fail_display: str | None = Field(
        None, description="Hard-fail boundary in display terms, e.g. '< 75%' (None if ungated)"
    )
    within_borderline_band: bool = Field(
        False,
        description="True when the value is a near-miss inside the runbook's relative band of "
        "the gate (refines BORDERLINE into 'just past the gate' vs a clear miss).",
    )
    flagged: bool = Field(..., description="status in {fail, borderline} — drives flagged-first")


class GateReadout(BaseModel):
    """All readout rows for one pipeline gate, flagged-first."""

    gate: Gate
    rows: list[MetricReadout]
    flagged_count: int = Field(..., description="Number of fail/borderline rows in this gate")
    blocked_by: Gate | None = Field(
        None,
        description="An UPSTREAM gate that is not clear, which gates this one downstream — the "
        "reason this gate reads 'blocked, clear <upstream> first' rather than proceeding. None "
        "when nothing upstream blocks it. A pure re-presentation: the sample's verdict already "
        "reflects the upstream finding; this only stops downstream from reading as 'all clear'.",
    )


class QcReadout(BaseModel):
    """The full gate-grouped QC readout for one decision card (a pure projection)."""

    sample_id: str
    gates: list[GateReadout] = Field(default_factory=list)
    flagged_count: int = Field(0, description="Total fail/borderline rows across all gates")


class CardHeader(BaseModel):
    """Small header context for a decision card. Anything not resolvable from the inputs is
    left ``None`` and named in ``not_captured`` — never fabricated (CLAUDE.md data-handling).
    ``origin`` and ``sample`` are resolvable server-side but are NOT on the card, so the caller
    injects them; absent them, they are honestly reported as not-captured.
    """

    sample_id: str
    run_id: str | None = None
    verdict: Verdict
    generated_by: str = Field(..., description="Narration provenance: 'stub' or 'claude'")
    sample_type: str | None = Field(None, description="Sample tissue/type from intake metadata")
    library_prep: str | None = None
    origin: str | None = Field(None, description="real-giab | synthetic | contrived | unknown")
    not_captured: list[str] = Field(
        default_factory=list, description="Header fields that could not be resolved from inputs"
    )


class QcReportLink(BaseModel):
    """A link to a QC HTML report artifact found on disk for the run (WS-07 Q1).

    The AI-off default fabricates no advice; instead the readout points the operator at the REAL
    QC reports (``fastp.html`` / ``multiqc_report.html``) the run published, when present. ``url``
    targets the existing read-only inline artifact-serve endpoint (``GET /api/runs/{id}/artifacts/
    {name}``) — this model *discovers* the file, it never serves or fabricates one. A run with no
    HTML report (e.g. the synthetic mock_run_01, CSVs only) yields an empty list — honest absence,
    not boilerplate.
    """

    name: str = Field(..., description="Bare artifact filename, e.g. 'multiqc_report.html'")
    label: str = Field(..., description="Human label, e.g. 'MultiQC report'")
    url: str = Field(..., description="Inline artifact-serve link (GET /api/runs/{id}/artifacts/…)")
    scope: str = Field(..., description="'sample' (per-sample report) or 'run' (run-level report)")


class CardReadout(BaseModel):
    """Side-channel view attached to a decision card: its header + its QC readout + QC-report links.

    Purely additive and OFF the deterministic gate (ADR-0001). It re-presents metrics the gate
    already emitted and points at the QC report artifacts on disk; it carries no verdict-setting
    power. ``qc_reports`` is the AI-off suggestion surface: the real reports + this metric readout,
    never fabricated next_steps (WS-07 Q1). Empty when the run published no HTML report.
    """

    header: CardHeader
    readout: QcReadout
    qc_reports: list[QcReportLink] = Field(default_factory=list)


# --- Display helpers ------------------------------------------------------------------------


def _fmt(value: float) -> str:
    """Format a number like the rule messages do (``:g`` trims trailing zeros)."""
    return f"{value:g}"


def _to_display(
    value: float, canonical_unit: CanonicalUnit, display_unit: str
) -> tuple[float, str]:
    """Render a canonical value into the operator-facing (display) unit.

    WHY this lives here rather than calling the metric registry: ``build_qc_readout``'s contract
    is ``(card, runbook)`` only, so display is derived from the two objects in hand. The runbook's
    ``unit`` is the display symbol the canonical value renders back into (runbook.py units
    contract); this is the minimal, conservative fraction↔percent (and ``x``/ratio passthrough)
    mapping that contract implies. Anything it cannot confidently convert falls back to the
    canonical value with the canonical unit's own symbol — never a fabricated number.
    """
    symbol = display_unit.strip()
    if symbol == "%":
        if canonical_unit is CanonicalUnit.FRACTION:
            return value * 100.0, "%"
        if canonical_unit is CanonicalUnit.PERCENT:
            return value, "%"
        # A "%" display on a non-rate canonical unit would be nonsense — fall through and use
        # the canonical symbol instead of guessing a conversion.
    elif symbol:
        # x / ratio and friends: the canonical value is already on the display scale.
        return value, symbol
    return value, _CANONICAL_SYMBOL.get(canonical_unit, "")


# --- Core projection ------------------------------------------------------------------------


def _classify(value: float, threshold: QCThreshold) -> tuple[ReadoutStatus, bool]:
    """Return (status, within_borderline_band), mirroring the QC rule exactly.

    The rule (`pipeguard.rules`) decides: passes ⟺ value satisfies the gate; else a hard-fail
    (past ``hard_fail``) is CRITICAL, otherwise a WARN. We reproduce that boundary logic so the
    readout status can never disagree with the finding the gate emitted for the same metric.
    ``within_borderline_band`` reproduces the rule's relative-band test (``gate * (1 ± band)``)
    to distinguish a near-miss from a clear miss — both are BORDERLINE, but the frontend can
    surface the nuance.
    """
    hib = threshold.higher_is_better
    passes = value >= threshold.gate if hib else value <= threshold.gate
    if passes:
        return ReadoutStatus.PASS, False

    hard = value < threshold.hard_fail if hib else value > threshold.hard_fail
    if hard:
        return ReadoutStatus.FAIL, False

    # Not passing, not hard-failing → a WARN in the rule. Relative band, so it is scale-invariant.
    if hib:
        edge = threshold.gate * (1 - threshold.borderline_band)
        within = value >= edge
    else:
        edge = threshold.gate * (1 + threshold.borderline_band)
        within = value <= edge
    return ReadoutStatus.BORDERLINE, within


def _row_for(mv: MetricValue, threshold: QCThreshold | None) -> MetricReadout:
    """Build one readout row by joining a metric value to its runbook threshold (or None)."""
    if threshold is None:
        # No gate for this metric: surface the observation honestly, classify nothing. Use the
        # registry's display name so an ungated row reads "Genotype quality (GQ)", not "variant.gq".
        obs_num, obs_sym = _to_display(mv.normalized_value, mv.canonical_unit, "")
        return MetricReadout(
            metric=mv.metric_key,
            label=_display_name(mv.metric_key),
            gate=mv.gate,
            status=ReadoutStatus.NOT_GATED,
            direction=Direction.UNKNOWN,
            observed_value=mv.normalized_value,
            canonical_unit=mv.canonical_unit,
            observed_unit=obs_sym,
            observed_display=f"{_fmt(obs_num)}{obs_sym}",
            threshold_display=None,
            hard_fail_display=None,
            within_borderline_band=False,
            flagged=False,
        )

    status, within = _classify(mv.normalized_value, threshold)
    direction = Direction.AT_LEAST if threshold.higher_is_better else Direction.AT_MOST

    obs_num, obs_sym = _to_display(mv.normalized_value, mv.canonical_unit, threshold.unit)
    gate_num, _ = _to_display(threshold.gate, mv.canonical_unit, threshold.unit)
    hard_num, _ = _to_display(threshold.hard_fail, mv.canonical_unit, threshold.unit)
    # The hard-fail boundary points the OPPOSITE way from the gate (you fail by going past it).
    hard_dir = "<" if threshold.higher_is_better else ">"

    flagged = status in (ReadoutStatus.FAIL, ReadoutStatus.BORDERLINE)
    return MetricReadout(
        metric=mv.metric_key,
        label=threshold.label,
        gate=mv.gate,
        status=status,
        direction=direction,
        observed_value=mv.normalized_value,
        canonical_unit=mv.canonical_unit,
        observed_unit=obs_sym,
        observed_display=f"{_fmt(obs_num)}{obs_sym}",
        threshold_display=f"{direction.value} {_fmt(gate_num)}{obs_sym}",
        hard_fail_display=f"{hard_dir} {_fmt(hard_num)}{obs_sym}",
        within_borderline_band=within,
        flagged=flagged,
    )


def build_qc_readout(card: DecisionCard, runbook: Runbook | None = None) -> QcReadout:
    """Project a decided card's ``metric_values`` into a gate-grouped, flagged-first QC readout.

    Pure: no I/O, no mutation, no verdict logic. Joins each ``MetricValue`` to its runbook
    ``QCThreshold`` by ``metric_key == our_key``; a value with no matching threshold is surfaced
    as ``not_gated`` rather than dropped or guessed. Rows are grouped by their pipeline gate
    (preflight → qc → variant) and, within a gate, ordered flagged-first.
    """
    book = runbook if runbook is not None else DEFAULT_RUNBOOK
    # Index thresholds by the registry key the card's metrics carry (metric_key == our_key).
    by_key: dict[str, QCThreshold] = {t.our_key: t for t in book.qc_thresholds}

    # Gates that are NOT clear (the deterministic gate already emitted a non-proceed result for
    # them) — an upstream one of these blocks its downstream gates. A gate only gets a gate_result
    # when it has findings, so "has a gate_result" ⟺ "not clear".
    unclear: set[Gate] = {gr.gate for gr in card.gate_results if gr.verdict is not Verdict.PROCEED}

    buckets: dict[Gate, list[MetricReadout]] = {}
    for mv in card.metric_values:
        row = _row_for(mv, by_key.get(mv.metric_key))
        buckets.setdefault(row.gate, []).append(row)

    gates: list[GateReadout] = []
    total_flagged = 0
    for gate in _GATE_ORDER:
        rows = buckets.get(gate)
        if not rows:
            continue
        # Stable flagged-first sort preserves the card's metric order within a status tier.
        rows.sort(key=lambda r: _STATUS_ORDER[r.status])
        flagged = sum(1 for r in rows if r.flagged)
        total_flagged += flagged
        gates.append(
            GateReadout(
                gate=gate,
                rows=rows,
                flagged_count=flagged,
                blocked_by=_blocking_gate(gate, unclear),
            )
        )

    # Any gate not in the canonical order (defensive) still gets surfaced, appended after.
    for gate, rows in buckets.items():
        if gate in _GATE_ORDER:
            continue
        rows.sort(key=lambda r: _STATUS_ORDER[r.status])
        flagged = sum(1 for r in rows if r.flagged)
        total_flagged += flagged
        gates.append(
            GateReadout(
                gate=gate,
                rows=rows,
                flagged_count=flagged,
                blocked_by=_blocking_gate(gate, unclear),
            )
        )

    return QcReadout(sample_id=card.sample_id, gates=gates, flagged_count=total_flagged)


def build_card_header(
    card: DecisionCard,
    *,
    origin: str | None = None,
    sample: Sample | None = None,
) -> CardHeader:
    """Surface sample-type + origin for the card header, honestly marking what is not captured.

    ``origin`` (real-giab / synthetic / contrived) and sample-type live *server-side*, not on the
    card, so the caller injects them (see the module docstring / integration notes). Whatever is
    absent is left ``None`` and listed in ``not_captured`` — this function never fabricates a value.
    """
    sample_type = sample.tissue if sample is not None else None
    library_prep = sample.library_prep if sample is not None else None

    not_captured: list[str] = []
    if card.run_id is None:
        not_captured.append("run_id")
    if not origin:
        not_captured.append("origin")
    if not sample_type:
        not_captured.append("sample_type")
    if not library_prep:
        not_captured.append("library_prep")

    return CardHeader(
        sample_id=card.sample_id,
        run_id=card.run_id,
        verdict=card.verdict,
        generated_by=card.generated_by,
        sample_type=sample_type,
        library_prep=library_prep,
        origin=origin or None,
        not_captured=not_captured,
    )


# --- Optional HTTP side-channel (additive; the orchestrator mounts it in main.py) -----------
#
# WHY a separate router: the card-serving endpoints return the core `DecisionCard` model, which
# must not change (ADR-0001 / guardrails). This router is the additive, zero-risk way to expose
# the readout without touching those endpoints — mount it with `app.include_router(router)`.
# It is self-contained (does not import main.py) so it unit-tests in isolation.

router = APIRouter(prefix="/api", tags=["qc-readout"])

# Default data root (mirrors main.py's). The gate owns all writes; this is read-only.
_DEFAULT_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


def _data_root() -> Path:
    """The run-data root, resolved at call-time from ``PIPEGUARD_DATA_ROOT`` (else the default).

    Resolved per call — not captured at import — so a test/deploy can repoint it with an env var
    without depending on main.py (the same monkeypatch-friendly pattern as api/feedback_store.py).
    """
    raw = os.environ.get("PIPEGUARD_DATA_ROOT", "").strip()
    return Path(raw) if raw else _DEFAULT_DATA_ROOT


def _origin_marker(run_dir: Path) -> str | None:
    """Read the run's optional single-line `origin` marker (real-giab/synthetic/contrived).

    Returns None when there is no marker, so the header reports origin as not-captured rather
    than fabricating one (mirrors main.py's `_run_origin`, but None instead of the "unknown"
    string so 'not captured' and a genuine 'unknown' tag stay distinguishable).
    """
    marker = run_dir / "origin"
    if marker.exists():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


# QC HTML reports the germline pipeline publishes: per-sample `${id}.fastp.html` and the run-level
# `multiqc_report.html`. A file is a QC report when its stem carries one of these tool tokens; the
# label is derived from the token (never guessed). Extend this map as new report-emitting tools are
# cataloged — an unknown `.html` is left unsurfaced rather than mislabelled.
_QC_REPORT_TOKENS: dict[str, str] = {"fastp": "fastp report", "multiqc": "MultiQC report"}


def _report_scope(name: str, sample_id: str, all_ids: list[str]) -> str | None:
    """Classify a QC-report file for one card: 'sample' (this sample's report), 'run' (run-level),
    or None (a DIFFERENT sample's per-sample report — excluded so it can't leak onto this card).

    The germline convention is ``${id}.<tool>.html``, so a per-sample report's filename STARTS with
    its sample id + '.'. A run-level report (``multiqc_report.html``) starts with no sample id.
    """
    if name.startswith(f"{sample_id}."):
        return "sample"
    for other in all_ids:
        if other != sample_id and name.startswith(f"{other}."):
            return None  # belongs to another sample — not this card's report
    return "run"


def _scan_qc_reports(
    run_dir: Path, run_id: str, sample_id: str, all_ids: list[str]
) -> list[QcReportLink]:
    """Discover the QC HTML reports on disk for ``sample_id``'s card (WS-07 Q1).

    Read-only directory scan (no tool runs): every ``*.html`` file in the run dir whose stem carries
    a known QC-report tool token, scoped so a sibling sample's per-sample report never leaks onto
    this card. Each link targets the existing inline artifact-serve endpoint. Empty ⇒ the run
    published no report (honest absence), and the caller falls back to the metric readout alone.
    """
    reports: list[QcReportLink] = []
    for p in sorted(run_dir.glob("*.html")):
        if not p.is_file():
            continue
        stem = p.name.lower()
        label = next((lbl for tok, lbl in _QC_REPORT_TOKENS.items() if tok in stem), None)
        if label is None:
            continue  # an unrelated .html — not a QC report; leave it unsurfaced, never mislabelled
        scope = _report_scope(p.name, sample_id, all_ids)
        if scope is None:
            continue
        reports.append(
            QcReportLink(
                name=p.name,
                label=label,
                url=f"/api/runs/{run_id}/artifacts/{p.name}",
                scope=scope,
            )
        )
    return reports


@router.get("/runs/{run_id}/cards/{sample_id}/qc-readout")
def get_card_readout(run_id: str, sample_id: str) -> CardReadout:
    """The QC readout + header + QC-report links for one decision card (additive side-channel).

    Re-derives the run's cards deterministically (`run_gate_from_dir`), projects the requested
    sample's card, and scans the run dir for the real QC HTML reports (WS-07 Q1). Read-only: it
    sets no verdict and writes nothing.
    """
    run_dir = _data_root() / run_id
    if not (run_dir / "SampleSheet.csv").exists():
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")

    artifacts, cards = run_gate_from_dir(run_dir)
    card = next((c for c in cards if c.sample_id == sample_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Unknown sample '{sample_id}'")

    sample = next((s for s in artifacts.samples if s.sample_id == sample_id), None)
    header = build_card_header(card, origin=_origin_marker(run_dir), sample=sample)
    reports = _scan_qc_reports(run_dir, run_id, sample_id, artifacts.sample_ids())
    return CardReadout(
        header=header,
        readout=build_qc_readout(card, DEFAULT_RUNBOOK),
        qc_reports=reports,
    )
