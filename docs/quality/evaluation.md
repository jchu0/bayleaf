# Evaluation — what "good" means

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | software / all |
| **Related** | [risks.md](risks.md), [requirements/nonfunctional.md](../requirements/nonfunctional.md), [data/strategy.md](../data/strategy.md), [data/metric_registry.md](../data/metric_registry.md), [data/schemas.md](../data/schemas.md), [demo/demo_plan.md](../demo/demo_plan.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) |

## Overview

How we know PipeGuard is *correct* and *honest*: the properties we check, the tests
that check them, and the limits of what a demo-stage evaluation can claim. The unit
of evaluation is a **case** (`EVAL-NNN`) with a precise definition of good and a named
check. Cases are grouped by type: **Deterministic** (same input → same output),
**Faithfulness** (the AI — and the notify port — narrate but never decide), **Failure-mode**
(each contrived fault reaches its intended verdict; a live side effect degrades to a safe
default), and **Real-data** (against GIAB truth — Phase 2). Two subsystems on or beside the
critical path get their own cases: the **metric registry** (unit normalization) and the
**notify port** (outbound integration).

The offline suite is **320 tests across 19 files** — 317 pass and 3 skip (the Postgres
live-integration checks in `test_persistence_postgres_live`, which need a reachable Postgres
and are off by default). By collected size: `test_api` (41), `test_notify` (36),
`test_synthetic` (32), `test_fetch_giab` (32), `test_gate` (29), `test_persistence` (17),
`test_metrics` (17), `test_triage` (16), `test_settings` (13, config-override authoring),
`test_review_queue` (13, the ticket domain), `test_card_readout` (12, the QC-readout projection),
`test_pipeline_lifecycle` (11, submit/approve/dry-run/diff), `test_auth` (10, the RBAC dev shim),
`test_gate_notify` (9), `test_artifacts_s3` (9), `test_pipelines` (8, the Pipeline Builder
save/version store), `test_artifacts` (7), `test_metrics_mapping` (5),
`test_persistence_postgres_live` (3) — all runnable offline with no API key
(`uv sync --all-extras && uv run pytest`; the `test_api` and `test_triage` suites need the
api/claude extras to import FastAPI).

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

### EVAL-004 — Metric registry normalizes by declared unit and round-trips

| Field | Value |
|---|---|
| **Target** | Metric registry (`pipeguard.metrics`) — `normalize` / `denormalize` / `observe` |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_metrics.py` (`test_percent_to_fraction`, `test_percent_to_fraction_is_exact`, `test_denormalize_is_the_inverse_of_normalize`, `test_x_stays_x`, `test_multiqc_pct_trap`, `test_disallowed_raw_unit_rejected`, `test_unsupported_conversion_rejected`, `test_observe_builds_metric_value`, `test_metric_value_json_round_trip`, `test_unknown_key_rejected`, `test_alias_resolution`) |

**Definition of good.** Normalization keys on the caller-declared `raw_unit`, never the field
name: a `percent` value for a fraction metric becomes an exact decimal (`95.0%` → `0.95`, not
`0.9500…1`), `x` stays `x`, and `denormalize` is the exact inverse (rendering a canonical
threshold back into the operator-facing unit). A `raw_unit` the entry disallows, an
unsupported unit pair, or an unknown `our_key` is **rejected** — a mis-declared unit fails
loud, never a silent 100×. `observe` builds a `MetricValue` that round-trips through
`model_dump(mode="json")` without the registry present.

**Method.** Feed known raw values/units through `normalize`/`denormalize`; assert exact
decimals, identity, and inverse; assert disallowed/unsupported/unknown inputs raise; build a
`MetricValue` via `observe` and JSON round-trip it.

**Known failure modes.** An open (guessing) conversion table would mask a mis-declared unit —
the closed table + explicit raise is the guard. A float-imprecision regression (`/100` vs
`*0.01`) would churn `content_hash` — pinned by `test_percent_to_fraction_is_exact`.

### EVAL-005 — QCMetrics→MetricValue mapping holds the canonical scale on the critical path

| Field | Value |
|---|---|
| **Target** | `metrics.mapping.metric_values_for` + runbook↔registry linkage (QC gate path) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_metrics_mapping.py` (`test_maps_qcmetrics_to_normalized_metric_values`, `test_missing_field_is_skipped_not_defaulted`, `test_cluster_pf_maps_to_its_registry_key`, `test_runbook_thresholds_key_on_registered_metrics`, `test_maps_real_mock_run_01_s5`) |

**Definition of good.** Each parsed `QCMetrics` field maps to its registry `our_key` on the
declared scale (`cluster_pf` → `qc.cluster_pf`); a missing (`None`) field is **skipped, not
defaulted** (a missing metric is a signal); every runbook threshold keys on a **registered**
`our_key`; and mapping the real `mock_run_01` S5 yields the canonical `normalized_value`s the
rules gate on. The end-to-end guard that this normalization did **not** move any verdict is
the pinned S5 outcome in EVAL-001 (verdicts stayed byte-identical).

**Method.** Map a synthetic and the real S5 `QCMetrics`; assert our_keys/units, the
skipped-`None` behavior, the `cluster_pf` key, and that every runbook threshold resolves to a
registered metric.

**Known failure modes.** A new `QCMetrics` field added without a registry entry would be
silently dropped — surfaced the moment a threshold keys on it
(`test_runbook_thresholds_key_on_registered_metrics`).

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
| **Automated?** | Yes — `test_triage.py` (`test_claude_path_prose_is_llm_but_citations_stay_deterministic`, `test_claude_path_falls_back_to_stub_on_refusal`, `test_claude_path_falls_back_to_stub_on_error`, `test_triage_endpoint_returns_advisory_note_for_flagged_sample`, `test_triage_endpoint_404s_for_clean_and_unknown_samples`) |

**Definition of good.** With the claude path selected, prose may be model-authored but
**citations and addressed findings stay deterministic**; any error or safety refusal
falls back to the stub (no 500, no broken demo). The API returns an advisory note for a
flagged sample and 404s for clean/unknown ones.

**Method.** Monkeypatch the client to raise / to return a refusal; assert stub fallback
and preserved citations. (This case fixed a real demo bug: a datetime-serialization
error that previously produced a 500 before the fallback could run.)

**Known failure modes.** A new field serialized outside the try-block would resurrect the
500 — the regression test pins the fallback.

## Notify-port cases (outbound integration seam)

### EVAL-040 — Notify fires only for actionable cards, and each send is one provenance event

| Field | Value |
|---|---|
| **Target** | Notify port policy + `notification.emitted` trail (engine wiring, ADR-0010 / ADR-0002) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_notify.py` (`test_notify_policy_notifies_only_actionable_cards`, `test_clean_proceed_card_is_skipped_and_not_recorded`); `test_gate_notify.py` (`test_notifier_notifies_actionable_cards_and_records_outbox`, `test_notifier_emits_one_notification_event_per_actionable_card`, `test_notification_event_payload_records_result_and_no_secret`, `test_no_notifier_emits_zero_notify_events_and_preserves_trail`, `test_notifier_does_not_change_the_cards`, `test_notify_events_survive_persistence_round_trip`, `test_each_actionable_notification_anchors_to_its_card[S4]`, `[S5]`) |

**Definition of good.** Only *actionable* (non-PROCEED) cards notify — a clean PROCEED card is
skipped and nothing is recorded. Each real notification emits exactly one `notification.emitted`
event anchored to its card (S4, S5 in the demo); the event payload records the result but **no
secret**; the notifier never mutates a card; and the events survive the persistence round-trip.
With **no** notifier wired (the default), zero notify events fire and the trail is byte-for-byte
unchanged.

**Method.** Gate `mock_run_01` with and without a notifier; assert the skip/prepare policy, one
event per actionable card, no-secret payloads, unchanged cards and trail, and event survival
through `rebuild-db`.

**Known failure modes.** A notifier that touched a card would violate the "port consumes
finished cards" contract — asserted against (`test_notifier_does_not_change_the_cards`). An
all-clear notification would spam the channel — the actionable-only policy prevents it.

### EVAL-041 — Live Slack send is opt-in and degrades to the offline stub

| Field | Value |
|---|---|
| **Target** | Slack adapter live-send seam (`PIPEGUARD_SLACK_LIVE`) + `get_notifier` selection |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_notify.py` (`test_get_notifier_defaults_to_stub`, `test_get_notifier_selects_slack_from_env`, `test_get_notifier_unknown_value_falls_back_to_stub`, `test_slack_with_no_creds_falls_back_to_stub_without_sending`, `test_slack_env_path_degrades_and_does_not_send`, `test_slack_live_seam_falls_back_to_stub_on_error`, `test_slack_live_seam_missing_client_lib_falls_back_to_stub`, `test_slack_live_seam_posts_via_client_when_explicitly_enabled`, `test_slack_never_sends_when_not_armed_even_with_creds`, `test_slack_channel_is_read_from_env_never_hardcoded`) |

**Definition of good.** The notifier defaults to the offline `stub` ($0; nothing leaves the
machine). `PIPEGUARD_NOTIFIER=slack` selects the adapter, but a real post fires **only** when
`PIPEGUARD_SLACK_LIVE` is armed *and* a bot token + channel are present. Missing creds, a
missing Slack SDK, or any Slack error degrade to the stub (payload built + recorded, not sent).
The channel is read from env, never hardcoded. With the seam explicitly enabled and a client
present, it posts exactly once.

**Method.** Vary the environment (unset / `slack` / unknown / armed-without-creds /
armed-with-mock-client / error / missing-lib) and assert the resolved adapter and that a send
happens **only** in the armed-and-credentialed case — no send on every other path.

**Known failure modes.** A default that sent, or a send reachable without the explicit flag,
would leak data and burn budget — pinned by `test_slack_never_sends_when_not_armed_even_with_creds`.
See [risks.md](risks.md) RISK-033.

### EVAL-042 — Payload is per-verdict and copies (never sets) the verdict

| Field | Value |
|---|---|
| **Target** | Notify payload builder (`build_payload` / stub adapter) + the `python -m pipeguard.notify` CLI |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_notify.py` (`test_stub_builds_wellformed_payload_for_flagged_card`, `test_payload_is_category_specific_by_verdict`, `test_payload_reflects_the_cards_verdict_not_a_new_one`, `test_payload_is_deterministic`, `test_notify_card_entry_point_uses_env_notifier_and_injection`, `test_notify_cli_gates_and_reports_actionable`, `test_notify_cli_no_args_returns_usage`) |

**Definition of good.** Payload framing is category-specific per verdict (escalate = provenance/
identity risk; rerun = operational failure; hold = borderline QC needing operator judgment); it
cites the card's evidence (observed vs. expected); and it **mirrors** the gate's verdict rather
than deriving a new one — the type copies `verdict`/`headline` and cannot decide (ADR-0001).
Identical cards yield an identical (content-hashed) payload. The CLI gates a run dir and reports
the actionable set (and prints usage on no args).

**Method.** Build payloads for escalate / rerun / hold cards; assert per-verdict framing,
evidence citation, verdict-mirroring, and determinism; exercise the CLI happy path and no-args
usage.

**Known failure modes.** A payload builder that inferred a verdict would break the
rules-decide invariant — structurally prevented (the payload only reads already-decided
fields). Interpolating timestamps/ids into the body would break reproducibility — the builder
interpolates none.

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
