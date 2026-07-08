# Evaluation — what "good" means

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / all |
| **Related** | [risks.md](risks.md), [requirements/nonfunctional.md](../requirements/nonfunctional.md), [data/strategy.md](../data/strategy.md), [demo/demo_plan.md](../demo/demo_plan.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) |

## Overview

How we know PipeGuard is *correct* and *honest*: the properties we check, the tests
that check them, and the limits of what a demo-stage evaluation can claim. The unit
of evaluation is a **case** (`EVAL-NNN`) with a precise definition of good and a named
check. Cases are grouped by type: **Deterministic** (same input → same output),
**Faithfulness** (the AI narrates but never decides), **Failure-mode** (each contrived
fault reaches its intended verdict), and **Real-data** (against GIAB truth — Phase 2).

The offline suite is **65 tests across 5 files** (`test_gate` 24, `test_triage` 16,
`test_persistence` 11, `test_synthetic` 10, `test_api` 4), all runnable with no API
key (`pytest`, `pythonpath=src`).

## What "good" means (principles)

1. **Deterministic before impressive.** A fixed run and pinned runbook must yield
   identical verdicts, findings, and content hashes every time. Reproducibility is the
   headline property, not model quality.
2. **Honest over confident.** We evaluate whether the system *refuses to overclaim* —
   confidence omitted until grounded, no invented pathogenicity, AI degrades to a stub
   — as strictly as whether it gets verdicts right.
3. **Every number traces to a source.** A finding is "good" only if its evidence
   points at a real artifact + field; an untraceable number is a bug regardless of
   whether the verdict is right.
4. **Grounded, not calibrated.** Verdicts are checked against *intended* outcomes on
   contrived/synthetic data; confidence heuristics are **not** claimed to be
   probability-calibrated (that needs the real-data track).

## Deterministic cases

### EVAL-001 — Pinned demo scenario

| Field | Value |
|---|---|
| **Target** | End-to-end gate on `mock_run_01` |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_gate.py` (`test_all_samples_parsed`, `test_s4_barcode_mismatch_is_critical_provenance`, `test_s4_missing_subject_id_flagged`, `test_s5_borderline_qc_only_warnings`, `test_verdict_aggregation_precedence`) |

**Definition of good.** S1–S3 **proceed**, S4 **escalate** (barcode/index swap +
missing `subject_id`, both preflight), S5 **hold** (borderline Q30 + coverage). Verdict
precedence: worst verdict wins.

**Method.** Parse the committed run, run the gate, assert per-sample verdicts and that
S4's barcode finding is a preflight/provenance critical, S5's are QC warnings only.

**Known failure modes.** A parser normalization change (MultiQC `pct_*` vs fastp
fraction) silently shifts a borderline sample across a threshold — caught by the pinned
values, which is the point.

### EVAL-002 — Reproducible projection from the ledger

| Field | Value |
|---|---|
| **Target** | Event ledger → relational projection (`rebuild-db`) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_persistence.py` (`test_rebuild_projects_demo_scenario`, `test_rebuild_is_idempotent`, `test_content_hashes_preserved`, `test_events_round_trip_faithfully`, `test_rebuild_from_different_ledger_drops_stale_rows`) |

**Definition of good.** Replaying a JSONL ledger yields the same runs/samples/findings/
cards/events; a second rebuild is idempotent; content hashes survive the round-trip;
rebuilding from a different ledger drops stale rows (the DB is a pure function of the
log).

**Method.** Build the demo ledger, project to SQLite, assert row-level equality and
hash preservation; rebuild twice and diff; rebuild from ledger B over DB-of-A and assert
no A-rows remain.

**Known failure modes.** A row field sourced from code rather than the event would break
purity — guarded by `schema_version` flowing from the event (a prior review finding).

### EVAL-003 — Live-repo wiring matches offline rebuild

| Field | Value |
|---|---|
| **Target** | In-band projection during a run vs. offline replay |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_persistence.py` (`test_live_repo_wiring_matches_rebuild`, `test_repo_param_persists_without_changing_output`, `test_reset_clears_projection`) |

**Definition of good.** Passing a `repo` to the gate persists the same projection an
offline `rebuild-db` would produce, **without changing the gate's output** when the repo
is omitted (the seam is invisible to the default path).

**Method.** Run with and without a repo; assert identical cards; assert the persisted
rows equal the rebuilt rows.

**Known failure modes.** Persistence side effects leaking into verdicts — explicitly
asserted against.

## Failure-mode cases (synthetic)

### EVAL-010 — Each contrived fault reaches its intended verdict

| Field | Value |
|---|---|
| **Target** | `pipeguard.synthetic` generator across all `FailureMode`s |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_synthetic.py` (`test_each_failure_mode_hits_intended_verdict`, `test_mixed_run_every_sample_matches_intent`, `test_committed_demo_run_verdicts`, `test_committed_demo_run_is_reproducible`, `test_generated_run_parses_with_existing_parsers`) |

**Definition of good.** clean → **proceed**; barcode_swap / absent_from_sheet →
**escalate**; missing_metadata / low_q30 / low_coverage / high_dup → **hold**;
pipeline_failure → **rerun**. Generated runs parse with the *existing* parsers (no
generator-only dialect) and are byte-reproducible.

**Method.** Generate one run per mode into a temp dir, gate it, assert the verdict
equals `INTENDED_VERDICT[mode]`; regenerate and assert identical output; parse the
committed `mock_run_02/03` and assert their pinned verdict vectors.

**Known failure modes.** The generator drifting from real artifact shapes — mitigated by
reusing the production parsers in the assertion (`test_generated_run_parses_with_existing_parsers`).

## Faithfulness cases (AI narrates, never decides)

### EVAL-020 — Triage note never touches the verdict

| Field | Value |
|---|---|
| **Target** | Triage agent (stub **and** claude path) |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_triage.py` (`test_note_never_touches_the_verdict`, `test_note_addresses_the_flagged_findings`, `test_note_cites_corpus_and_findings`, `test_note_content_hash_is_stable_and_deterministic`) |

**Definition of good.** A `TriageNote` addresses the flagged findings and cites both the
corpus and the findings, and it **cannot** carry or alter a verdict/confidence (the type
has no such field). A clean/proceed card yields no note.

**Method.** Run triage on flagged and clean cards; assert citations present, verdict
untouched, and note hash stable/deterministic.

**Known failure modes.** A future schema change adding a decision-bearing field to the
note — structurally prevented today; re-audit if the model is expanded.

### EVAL-021 — Live AI degrades to the deterministic stub

| Field | Value |
|---|---|
| **Target** | `claude` synthesizer / triage path under failure |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_triage.py` (`test_claude_path_prose_is_llm_but_citations_stay_deterministic`, `test_claude_path_falls_back_to_stub_on_refusal`, `test_claude_path_falls_back_to_stub_on_error`); `test_api.py` (`test_triage_endpoint_returns_advisory_note_for_flagged_sample`, `test_triage_endpoint_404s_for_clean_and_unknown_samples`) |

**Definition of good.** With the claude path selected, prose may be model-authored but
**citations and addressed findings stay deterministic**; any error or safety refusal
falls back to the stub (no 500, no broken demo). The API returns an advisory note for a
flagged sample and 404s for clean/unknown ones.

**Method.** Monkeypatch the client to raise / to return a refusal; assert stub fallback
and preserved citations. (This case fixed a real demo bug: a datetime-serialization
error that previously produced a 500 before the fallback could run.)

**Known failure modes.** A new field serialized outside the try-block would resurrect the
500 — the regression test pins the fallback.

## Real-data evaluation (Phase 2 — planned)

### EVAL-030 — Verdicts vs. GIAB HG002 truth

| Field | Value |
|---|---|
| **Target** | Gate + (later) variant-gate against a known-answer sample |
| **Type** | Real-data |
| **Automated?** | **Planned** — depends on the GIAB HG002 subset fetch (tasks T-013 GIAB half / T-017) |

**Definition of good.** On a real, well-characterized sample with a gold-standard truth
VCF + high-confidence BED, the gate's breadth/callability and identity checks behave
correctly, and any variant-level claim is checkable against truth.

**Method.** *(Planned)* Fetch a panel-region HG002 subset (accession + script, no raw
reads committed), run the gate, compare against truth in high-confidence regions.

**Known failure modes.** Truth is only trustworthy inside the high-confidence BED;
outside it, absence of a call is not evidence. Requires the genomics toolchain
(bioconda/containers), kept separate from the app's `uv` toolchain.

## What we do *not* claim

1. **No calibrated probabilities.** Confidence is a heuristic; we do not evaluate it as
   a probability and do not report ROC/Brier-style calibration.
2. **No clinical accuracy claim.** Verdicts are checked against *intended* operational
   outcomes on contrived/synthetic data, not clinical ground truth. PipeGuard is a
   research/demo tool ([constraints.md](../requirements/constraints.md) REQ-C-030).
3. **No performance SLA.** No throughput/latency benchmark is measured at this stage
   (see [risks.md](risks.md), [nonfunctional.md](../requirements/nonfunctional.md)
   REQ-NF-032).

---

*Marker legend:* **Fact** (a named, passing test) · **Assumption** · **Decision** ·
**TODO** (Phase-2 / planned). Test ids are current as of the last-updated date; run
`pytest` for the live count.
