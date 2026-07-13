# Journal — 2026-07-12 (MST) — Gap-analysis implementation: fail-closed gate, metric honesty, log-access hardening

| Field | Value |
|---|---|
| **Focus** | Begin implementing the [gap-analysis remediation](../../audit/gap_analysis/README.md) (closing the review's "confident surface vs. thin wiring" gaps), test-first, on branch `feat/gap-analysis-remediation` off `main` @ `8e9658e`. Autonomous overnight run; not merged/pushed. |
| **Participants** | Claude (Opus 4.8) + `adversarial-reviewer` subagent; maintainer (James Hu) asleep — resume-with-review agreed up front. |
| **Outcome** | Four workstream slices landed as clean test-first commits; **two flagged findings empirically REFUTED** (WS-10 fastp regression; WS-06 Gap-3 dup-rate); offline suite **627→640 passed / 8 skipped**, ruff + mypy clean and pinned-demo/HG002 verdicts byte-identical at every commit. |

## Discussion

Sandbox constraint established first: no `nextflow`/JRE here, so pipeline-level real-run legs can't be
exercised — but fastp/samtools/bcftools (the `hackathon` conda env) + the real 629 MB GIAB data ARE on
disk, so direct-tool real-path checks are possible. Scope chosen with the maintainer: "all waves, verify
what I can." Every commit held the 640-green offline invariant; each was adversarial-lens or evidence-checked
before landing.

### What landed (4 commits)

1. **`efef163` — WS-10: fastp promoted-output regression REFUTED.** The delta review's "urgent" worry —
   fastp's promoted MANDATORY `unpaired_fastq`/`failed_fastq` outputs may be absent → the intake pipeline
   dies at step 1 — was *likely-but-unconfirmed*. Ran the catalog's actual fastp command on real HG002:
   fastp opens the `--unpaired1/2`/`--failed_out` writers eagerly, so the files are ALWAYS created (with
   content on 490 failed reads; an empty 828-byte gzip even at zero failures). No `Port.optional` change
   (it would falsely imply the output can be absent). Instead froze the evidence with two guards the
   compile/stub tests structurally can't give (the stub `touch`es the files): an offline stub/output
   consistency check for every catalogued tool, and a real-path acceptance test (green on real HG002 w/
   `PIPEGUARD_BIOCONDA_BIN`; skips offline). Caveat: verified fastp 1.3.6; the catalog pins 0.23.4 — behavior
   is longstanding across fastp ≥0.20, final confirm is the live-Nextflow pass.

2. **`4d6acbf` — WS-01·PR1: fail-closed gate.** Two seams that leaked PROCEED on missing data. `QC-MISSING`
   (a sheet-declared sample with no QC row now emits WARN/HOLD, guarded on `sheet is not None`) is LIVE
   end-to-end — `aggregate_verdict([])` no longer PROCEEDs on unexamined data. `expected_metrics` +
   `_check_expected_metrics` (a profile-bound metric absent → `QC-EXPECTED-<key>` HOLD) is a MECHANISM only:
   no deployed code populates `expected_metrics` yet (`_active_runbook` never sets it) — the production
   consumer is WS-05's `RunbookSet`. `aggregate_verdict` untouched (ADR-0001); `DEFAULT_RUNBOOK` byte-for-byte
   inert. An **adversarial review** caught (a) that Gap C ships dark unless the commit says so — now stated
   plainly — and (b) an unvalidated `expected_metrics` could HOLD every sample forever on a typo; added a
   construction-time validator against the producible key set (+ de-dupe) and one E2E `run_gate→card` test.
   Out-of-scope items surfaced and routed: the `@lru_cache` pre-QC verdict staleness (→ WS-03 intake state);
   a demux-only "ghost" sample still PROCEEDs (→ WS-02 provenance).

3. **`2033849` — WS-06 metric honesty (Gaps 4 & 5).** The registry claimed `picard_collecthsmetrics` for
   `qc.mean_target_coverage` + `qc.breadth_20x/30x`, but the committed germline driver computes all three
   with **mosdepth** (`parse_mosdepth`: `total_region` mean; bases≥20x/30x over region bases) and never runs
   Picard — repointed source + parser + the stale Picard pct-trap comments. (A standing guard caught the
   breadth pair, which the plan had missed; `on_target`/`fold_*` deliberately stay Picard-sourced — Picard
   genuinely IS their tool, this reads-only pipeline just doesn't compute them.) The `qc.reads_passing_filter`
   runbook label "% reads identified" (a demux concept) → "Reads passing filter" (matches the registry). No
   verdict/hash change (source is provenance metadata; the relabelled metric fires no finding on the pinned
   runs). **Gap 3 (dup-rate) REFUTED, no change:** the plan wanted `0.0057→0.57`, but the driver writes
   percent (`rate*100`) and fastp reports HG002 duplication at 0.00565% — so `0.0057` IS the correct percent;
   dup "not gating" on HG002 is correct (0.0057% ≪ 30%); dup DOES gate on high values. Deliberately did NOT
   bump `metric_registry_version` (a provenance relabel isn't a contract change; keeps 6 version-pinning tests
   valid).

4. **`8c8e2a1` — WS-08 (interim): node-log access hardening + honest labeling.** The observation endpoint
   read `grants` from the query string and gated only on viewer+, so any viewer could pull `?grants=logs`
   (de-identified task logs) on any node — while the docstring claimed "node-scoped least-privilege via the
   AgentBinding." Investigation: `AgentBinding`/`agent_bindings` exist ONLY in the frontend (no server model,
   no persistence, no run→graph linkage), so the server can't enforce the binding at all. Full per-agent
   enforcement is a large multi-part change; the honest interim: (a) `logs` now requires reviewer+ (real,
   wire-role-enforced exposure reduction), `outputs` stays viewer+; (b) the docstrings now state the binding
   is an advisory CLIENT-SIDE hint the server doesn't enforce, access is by node-scope + wire-role, and full
   binding enforcement is a documented deferral. Design invariant honored: close the seam or label it.

### Refutations are a feature, not a miss

Two of the plan's findings dissolved under real evidence (WS-10, WS-06 Gap-3). That is the review process
working as intended — an adversarial finding is a *hypothesis*; running the real tool is how a plausible-but-
wrong one gets retired instead of "fixed" into a false change. Both are documented in-commit with the evidence.

### Deferred / next

WS-09 (authored-pipeline parse coupling + intake input parity) is the highest-value remaining self-contained
fix. Then the deeper thread: WS-06·PR1/2 (ingestion contract → registry-driven parser) → WS-03 (adapter) →
WS-02 (FREEMIX) → WS-05 (RunbookSet, which wires WS-01's `expected_metrics`) → WS-04 (hap.py) → WS-07. A
**Nextflow verification pass with the maintainer** is owed to run the env-gated real-run legs (WS-01 HG002
QC-MISSING check; WS-10 fastp real-path) on a machine with the toolchain. Full status: the
[gap-analysis tracker](../../audit/gap_analysis/README.md#-current-status--next-action-resume-here).

## Related
- [audit/gap_analysis/README.md](../../audit/gap_analysis/README.md) — the living tracker (statuses updated).
- [audit/gap_analysis/delta-review-2026-07-12.md](../../audit/gap_analysis/delta-review-2026-07-12.md) — WS-08/09/10 source.
- ADR-0001 (rules decide / AI narrates), ADR-0012 (least-privilege), ADR-0022 (agent observation binding).

## Distilled into

**Closed 2026-07-12** — the canonical doc sweep for these four commits (and every commit landed
after them on this branch) is in
[2026-07-12-gap-analysis-remediation-verification.md](2026-07-12-gap-analysis-remediation-verification.md):
`CLAUDE.md` code map (items 1a fail-closed additions, 4c WS-08 access-control honesty),
`docs/data/metric_registry.md`/`qc_metrics.md` (WS-06 metric-honesty + gated-count corrections),
`docs/planning/tasks.md` (T-145 WS-01, T-147 WS-10, T-148 WS-08, T-149 WS-06),
`audit/gap_analysis/README.md` (all four workstream statuses updated).
