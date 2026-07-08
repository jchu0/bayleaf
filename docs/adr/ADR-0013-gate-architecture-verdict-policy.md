# ADR-0013 — Gate architecture and surface-and-decide verdict policy

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md) |

## Context

A single QC gate is too coarse, in two ways. (1) Samples that never really
sequenced — low pass-filter reads plus tiny FASTQs from sample-quality or
barcoding failures — should not consume pipeline processing at all. (2) The tool's
job is to **surface information and let the operator decide**, not to
prescriptively auto-recommend reruns. In practice, reruns mostly stem from
operational/file-system issues, not data quality — a low-coverage sample is a
human judgment call, not an automatic resequence.

## Decision

**Three checkpoints:**
1. **Preflight / intake gate** — before the processing queue. Relies on Illumina
   run/lane sequencing QC (cluster PF / %PF, error rate, run Q30, yield) plus
   per-sample FASTQ sanity (read count, file size). Catches "didn't sequence
   anything", sample-quality dropouts, and barcoding issues before they consume
   the pipeline. Includes a **manual override** for genuinely-sparse samples or
   unanticipated edge cases.
2. **QC gate** — after processing: sequencing / alignment / coverage quality (the
   input-quality check).
3. **Variant gate** — the output: per-variant confidence + annotation
   (caller-aware — see the QC sources reference on caller-dependent `QUAL`).

**Verdict policy — surface and decide, don't prescribe:**
1. The gate surfaces cited information and a recommendation; the human decides and acts.
2. Most findings map to **HOLD** (review) or **ESCALATE** (provenance/identity — chain of custody).
3. **RERUN** is reserved mostly for **operational / file-system failures** —
   network errors, missing files, distributed-FS indexing lag and race conditions
   (file-not-found), pipeline step crashes — not for data-quality shortfalls.
4. **Depth vs coverage are surfaced distinctly:** reads spanning only half the
   expected breadth (a dropout) is a different signal from high-quality reads with
   good breadth but insufficient depth for calling.
5. Every decision and its resolution is recorded to the experience corpora
   (ADR-0009) so the agent learns the lab's actual choices over time (a dedicated
   agent skill later).

## Assumptions

- Preflight can lean on Illumina run QC (InterOp/SAV/demux) to judge "did we sequence".
- Operational failures are distinguishable (log/file signals) from data-quality issues.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Single gate | Too coarse — can't gate intake or separate output-variant confidence |
| Auto-rerun on any QC breach | Prescriptive and wrong; resequencing won't fix most issues, and the human should decide |

## Consequences

| | |
|---|---|
| **Gains** | Cheap early rejection of unsequenceable samples; a conservative, trust-building verdict policy; the corpora capture real human decisions for future guidance |
| **Costs** | Three checkpoints, an override mechanism, and intake-metric wiring to build |
| **Follow-ups** | Preflight + QC + variant metric sets land in `data/qc_metrics.md`; the decision record feeds ADR-0009 |

## Revisit when

- Preflight thresholds or the override/authority policy need tuning, or the
  RERUN vs HOLD boundary proves miscalibrated in practice.
