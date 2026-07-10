# Journal — 2026-07-09 (MST) — Real GIAB fastqs through the outlined pipeline, end to end

| Field | Value |
|---|---|
| **Focus** | Actually run the real GIAB HG002 panel fastqs through the Pipeline-Builder germline chain (not just the pre-aligned BAM) and land a dashboard-discoverable run, for true end-to-end testing on real data. |
| **Outcome** | New [`scripts/run_giab_pipeline.py`](../../scripts/run_giab_pipeline.py) executes fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call→norm} on the real reads, writes `data/RUN-2026-07-08-GIAB-HG002/` (frozen-five CSVs + narrated pipeline.log + `origin=real-giab`), and runs the unchanged `run_gate`. The run renders in the operator UI with real metrics + an honest HOLD. |
| **Related** | [scripts/README.md](../../scripts/README.md) · [gate_giab.py](../../scripts/gate_giab.py) (BAM-only precedent, T-017) · [fetch_giab_hg002.py](../../scripts/fetch_giab_hg002.py) · ADR-0003 (deployment-agnostic ports) |

## Discussion

**Gap it closes.** `gate_giab.py` gates the *pre-aligned* NIST panel BAM (coverage/breadth only).
The maintainer wanted the raw **fastqs** run through the *outlined* chain end to end and surfaced in
the dashboard. That needed the alignment step the app never runs.

**What was missing locally + how it was resolved.** No aligner was installed and there was no
reference. Installed `bwa-mem2` (bioconda, runs fine under Rosetta) and pulled **chr20 only**
(UCSC hg38, chr-prefixed to match the BAM contigs) — sufficient because the panel is 13 chr20
windows (~250 kb); index build is ~10 s. All git-ignored under `data/real-giab/`.

**The run.** fastp (v1.3.6) → bwa-mem2 (v2.2.1) → samtools fixmate/markdup (70,233 primary mapped)
→ mosdepth (v0.3.14) → bcftools call|norm (v1.23.1). Real metrics: **Q30 88.2% · reads-PF 99.3% ·
54.2× · dup 0.006% · breadth 99.2% ≥20× · 553 normalized panel variants**. The run dir is written
at `data/<run_id>/` (top-level, so the read-API's `DATA_ROOT` discovery finds it) with a proper
`[Header]` (RunName/InstrumentPlatform=HiSeq 2500/Date) so status/platform/date populate.

**Verdict = HOLD (honest).** Under the default runbook the run gates to **HOLD — cluster PF is
missing** (`QC-CLUSTER_PF-NA`). cluster-PF is a run-level SAV/InterOp metric a fastq→BAM path can't
produce, so `qc_metrics.csv` leaves it blank and the gate flags the gap rather than fabricating a
value — the four measurable metrics all clear with margin. This is a *better* E2E demo than a
rubber-stamped PROCEED: it shows the gate catching a real data-completeness gap.

**Verified in the app.** `GET /api/runs` discovers it (`needs_review`, HiSeq 2500, 2026-07-08);
the decision card renders the QC-readout hero with the real numbers (54.2×, 88.2%) + the cluster-PF
finding; no console errors. Live, real reads → operator UI.

**Invariant.** compose ≠ execute intact — the script is a standalone driver of the bioconda
toolchain; the app only ingests the `run/` outputs. Nothing raw is committed (reference + reads +
run dir all git-ignored); the reproducible record is the script + the fetch manifest.
