## Summary

The scientific spine is largely sound and honestly labeled: the deterministic gate compares registry-**normalized** values against canonical thresholds (so unit drift can't move a verdict), `DecisionCard.confidence` stays `null`, ClinVar `CLNSIG` is quoted verbatim, route-to-human is disarmed by default, and the compiler is drift-pinned. The problems are on the **presentation and reproducibility edges**: a confirmed 100×-wrong QC number in the hero card's finding text for the four fraction-scaled metrics; a required run-level metric (`cluster_pf`) the reads-based pipeline structurally cannot emit, which pins every live run to HOLD; and reproducibility pins that are build-tags/floors rather than digests with no per-run capture. None are demo-critical for the pinned `mock_run_01` recording, but several are latent scientific-truthfulness risks for any real/Builder-driven run.

No **Blocker** findings. Highest first.

---

### SCI-01 · Fraction-scaled QC metrics render 100× wrong in the DecisionCard finding text
- **Severity:** High · **Confidence:** Confirmed · **Category:** confirmed defect
- **Area / journey:** Operate → Decision cards (`/runs/:id`) — the hero output. Affects `breadth_20x`, `breadth_30x`, `pct_mapped`, `on_target`.
- **Evidence:**
  - `src/pipeguard/rules.py:224` — `disp_gate = reg.denormalize(threshold.our_key, threshold.gate, mv.raw_unit)` (denormalizes the gate to the metric's **raw** unit).
  - `src/pipeguard/rules.py:234` — `f"{threshold.label} for {sid} is {mv.raw_value:g}{threshold.unit}; runbook gate is "` (renders the **raw** value, then appends `threshold.unit`, which is `"%"`).
  - `src/pipeguard/metrics/mapping.py:34-36` — `("breadth_20x", "qc.breadth_20x", "fraction")`, `("pct_mapped", "qc.pct_mapped", "fraction")`, `("on_target", "qc.on_target", "fraction")` (these metrics' `raw_unit` is **fraction**, i.e. 0–1).
  - `src/pipeguard/runbook.py:124-128` — breadth_20x `unit="%"` (display symbol is percent).
  - Contrast the correct sibling surface `api/card_readout.py:222-224` — `if canonical_unit is CanonicalUnit.FRACTION: return value * 100.0, "%"` and it renders `mv.normalized_value` (not `raw_value`).
- **Reproduction (read-only, project venv):** `_evaluate_metric` on a failing `breadth_20x=0.85` / `on_target=0.30` emits:
  - `Breadth ≥20x for S1 is 0.85%; runbook gate is ≥ 0.9% (hard-fail 0.8%).`
  - `On-target rate for S1 is 0.3%; runbook gate is ≥ 0.6% (hard-fail 0.4%).`
  while the same run through `q30=80` (raw_unit percent) correctly reads `Q30 for S1 is 80%; runbook gate is ≥ 85%`.
- **Expected:** `Breadth ≥20x … is 85%; gate ≥ 90% (hard-fail 80%)`.
- **Actual:** value and thresholds are shown ~100× too small (`0.85%`, `≥ 0.9%`) in `Finding.detail` and `Evidence.value`/`expected` — the authoritative on-card scientific claim. The **verdict is still correct** (gating is on `normalized_value`); only the human-readable number is wrong, and it silently **contradicts** the QC-readout side-channel (`card_readout.py`), which renders the same metric as `85%`.
- **Root cause:** `_evaluate_metric` mixes scales — it prints `mv.raw_value` (raw unit) and denormalizes thresholds to `mv.raw_unit`, but appends the `threshold.unit` symbol (`%`). This coincides only when `raw_unit` is already percent/x; for the four `fraction`-raw metrics it is off by 100×.
- **Min fix:** render the observed value and thresholds through the same display conversion `card_readout._to_display` uses — i.e. show `mv.normalized_value` (or a value converted to the display unit implied by `threshold.unit`) instead of raw `mv.raw_value`, and denormalize thresholds to that display unit rather than to `mv.raw_unit`.
- **Demo-critical:** N — no committed fixture fails these four metrics (`breadth` passes at ≥0.96, `on_target` at ≥0.80, `pct_mapped` at ≥0.985; `mock_run_01` omits them entirely), so the recording never triggers it. It fires on any real/Builder run with low breadth/mapping/on-target.
- **Risk of fixing now:** Low, but it changes `Finding.detail`/`Evidence` strings, which flow into `content_hash`/`signature` — regenerate any golden fixtures that assert those strings.
- **Regression test:** assert `_evaluate_metric` for a failing `breadth_20x=0.85` yields `"… is 85%; runbook gate is ≥ 90%"`, and that it agrees with `card_readout.build_qc_readout`'s `observed_display`/`threshold_display` for the same metric.

---

### SCI-02 · Required `cluster_pf` structurally pins every reads-based (real/Builder) run to HOLD
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** scientific-correctness risk
- **Area / journey:** Operate — live intake / Builder Run → Decision cards. Owns the "rules-decide moment."
- **Evidence:**
  - `src/pipeguard/runbook.py:99-106` — `QCThreshold(metric="cluster_pf", our_key="qc.cluster_pf", …)` with `required` defaulting to `True` (`runbook.py:42` `required: bool = True`).
  - `scripts/run_giab_pipeline.py:224` — `# cluster_pf is a run-level SAV/InterOp metric not derivable from reads → left blank (honest).`
  - `scripts/run_giab_pipeline.py:229` — writes an empty `cluster_pf` field: `f"{cfg.sample},{q30:.2f},{reads_pf:.2f},{coverage:.1f},{dup:.4f},,{b20:.4f},{b30:.4f}\n"`.
  - `data/RUN-2026-07-08-GIAB-HG002/qc_metrics.csv` — `HG002,88.22,99.31,54.2,0.0057,,0.9924,0.9707` (empty `cluster_pf`).
  - `src/pipeguard/rules.py:172-191` — a missing **required** metric → `QC-CLUSTER_PF-NA` WARN → `Verdict.HOLD`.
- **Actual:** `cluster_pf` (Cluster PF) is an instrument-level Illumina SAV/InterOp metric that the fastp/bwa/mosdepth chain cannot produce, yet it is a `required=True` gate metric. Every run executed through the real Nextflow path (or the Builder Run path) therefore emits a "cluster_pf missing" HOLD — PROCEED is unreachable on the live path. This conflates "metric absent because this pipeline doesn't produce it" with "quality concern."
- **Expected (as a platform):** a SAV-only metric should be `required=False` (score it when present, don't NA-flag a reads-only run), or the missing-required message should distinguish "not produced by this pipeline" from "expected but absent."
- **Min fix:** set the `cluster_pf` threshold `required=False` (matching the other non-frozen checks), OR gate `required` on whether the run declares a SAV source.
- **Demo-critical:** N — this HOLD is the **intended** demo beat ("HG002 → HOLD on the honest cluster_pf-missing signal"), so any fix changes the recorded narrative. Flagging as a release-soundness tension, not a demo bug.
- **Risk of fixing now:** Medium — flipping `required` changes the HG002 verdict and the demo story; coordinate with demo-readiness.
- **Regression test:** a reads-derived run dir with blank `cluster_pf` but passing frozen-four should not HOLD **solely** on `QC-CLUSTER_PF-NA` once the policy is decided.

---

### SCI-03 · Reproducibility pins are tags/floors and no resolved digest or Nextflow version is captured per run
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** scientific-correctness risk
- **Area / journey:** Builder → Export/Run Nextflow; provenance ledger.
- **Evidence:**
  - `src/pipeguard/nextflow/catalog.py:71` — `container="quay.io/biocontainers/fastp:0.23.4--h5f740d0_0"` (a mutable build **tag**, not `@sha256`); same pattern for every `ProcessSpec` (`catalog.py:96-97,121,143,167,186,203`).
  - `pipelines/germline/nextflow.config:5` — `nextflowVersion = '>=23.04.0'` (a **floor**, not a pin).
  - `src/pipeguard/provenance.py:57-59` — `AnalysisRun` docstring: "Phase 1 captures the **gate provenance** … The **pipeline provenance** (sarek params_hash / execution_trace) is added in Phase 2" — no resolved image digest / Nextflow version field exists on the run record (grep for per-run digest/version capture in `api/`+`src/pipeguard/` returns only this Phase-2 note).
- **Actual:** "deterministic reruns" is true only for the **wiring** (compiler output is byte-pinned by the drift test) and the **gate re-derivation** (same inputs → same verdict). The actual toolchain that produces variant calls is pinned to floating tags + a version floor, and nothing captures the resolved digests/version into the run's ledger — so a rerun months later can silently pull a different image build or a newer Nextflow and produce different variant output with no provenance signal.
- **Expected / min fix:** either pin containers by `@sha256` and set an exact `nextflowVersion`, or (lighter) capture the resolved image digests + `nextflow -version` into `AnalysisRun.gate_provenance` per run so a drift is at least **detectable**. At minimum, label every "deterministic/reproducible" surface as "pinned wiring + versions, not bitwise-identical variant output."
- **Demo-critical:** N (stub/mock path). **Risk of fixing now:** Low if limited to capturing versions; Medium if changing container pins (could break the conda/container resolve on the demo box).
- **Regression test:** assert `AnalysisRun`/ledger for a live run records a non-empty resolved-tool-version map; assert `catalog.py` container strings match an approved digest allow-list.

---

### SCI-04 · No FASTQ pairing / read-count / format validation on the paired-end inputs
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** scientific-correctness risk
- **Area / journey:** Builder Run + live intake → alignment.
- **Evidence:**
  - `pipelines/germline/main.nf:15` — `ch_reads = Channel.value([file(params.read1), file(params.read2)])` — R1/R2 are taken as two independent path params, no pairing/order/length check.
  - `scripts/run_giab_pipeline.py:243-244` — `--read1`/`--read2` are independent CLI args; the driver performs no R1/R2 sync validation.
  - No gate rule validates FASTQ synchronization — `src/pipeguard/rules.py` has provenance/metadata/qc/pipeline/variant families only; none inspects read pairing.
- **Actual:** a swapped, mismatched, or unequal-length R1/R2 pair is not caught at compile/intake; it fails (if at all) only at runtime inside bwa-mem2. There is no "reads look wrong" finding, so a paired-end integrity problem is invisible to the decision gate.
- **Expected / min fix:** accept as a documented seam and label it, OR add a lightweight pre-flight (equal record counts / matching read-name stems) surfaced as a provenance finding. This is upstream of chain-of-custody, so a rule-level check is defensible.
- **Demo-critical:** N. **Risk of fixing now:** Low (additive read-only check).
- **Regression test:** feed mismatched-count R1/R2 and assert a loud failure or a preflight finding, never a silent proceed.

---

### SCI-05 · No reference-build / contig-naming assertion between reads, FASTA, and panel BED
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** scientific-correctness risk
- **Area / journey:** Builder Run + live intake → alignment / coverage / calling.
- **Evidence:**
  - `pipelines/germline/main.nf:17` — `ch_reference = Channel.value([file(params.reference), file("${params.reference}.*")])` — reference + sidecar glob only; no contig/build check.
  - `scripts/panel_regions.example.bed` — `chr20` (UCSC hg38, chr-prefixed) smoke windows; reconciled manually (journal 2026-07-09), with no code asserting the panel BED's contig naming matches the reference FASTA or the reads.
  - No assertion of build/contig compatibility anywhere in `pipelines/germline/` or `scripts/run_giab_pipeline.py`.
- **Actual:** a build mismatch (e.g. a GRCh38 `20` panel BED against a `chr20` UCSC FASTA, or reads aligned to a different assembly) produces empty coverage over the panel or a runtime crash, uncaught by the gate. `mosdepth --by` over a non-matching BED yields silently wrong breadth/coverage numbers rather than an error.
- **Expected / min fix:** a pre-flight contig-name intersection check (reference `.fai` contigs ⊇ panel BED chroms) surfaced as a finding, or an explicit documented assumption.
- **Demo-critical:** N. **Risk of fixing now:** Low.
- **Regression test:** a panel BED with `20` (no `chr`) against a `chr20` reference must produce a loud preflight failure, not a `0%`-breadth "pass."

---

### SCI-06 · The one real-GIAB run does not surface its chr20 / arbitrary-smoke-window framing
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** missing user-facing state
- **Area / journey:** Operate → Decision cards / Provenance for `RUN-2026-07-08-GIAB-HG002`.
- **Evidence:**
  - `data/RUN-2026-07-08-GIAB-HG002/` contains only `SampleSheet.csv, demux_stats.csv, origin, pipeline.log, qc_metrics.csv, sample_metadata.csv` — **no `NOTE.md`** (contrast `data/RUN-2026-07-11-CLINVAR-RTH/NOTE.md`, which exists and frames its fixture).
  - `scripts/panel_regions.example.bed:3-6` — "These are **ARBITRARY smoke-test windows** on chr20 …, **NOT a real clinical gene panel** and **NOT any pathogenicity claim**."
  - `data/RUN-2026-07-08-GIAB-HG002/qc_metrics.csv` — `mean_coverage=54.2`, `breadth_20x=0.9924` presented as real-GIAB metrics; the chr20/panel caveat lives only in `pipeline.log` ("aligning to chr20", "panel coverage") and driver docstrings, not in a run-dir NOTE.
- **Actual:** the sole `origin=real-giab` run reports coverage/breadth over three arbitrary ~50–100 kb chr20 windows, but nothing in the run dir tells a consumer this is a chr20 downsample against smoke-test windows. A viewer can read `99.2% breadth ≥20x` as whole-panel/clinical quality.
- **Expected / min fix:** add a `NOTE.md` (mirroring the CLINVAR-RTH one) to the real run dir stating: chr20-only downsample, arbitrary smoke-test panel, benchmark sample (not a patient), no clinical claim.
- **Demo-critical:** N if the recording stays on `mock_run_01`; becomes Y if the real GIAB card is shown on screen.
- **Regression test:** assert every `origin=real-giab` run dir carries a `NOTE.md` describing its downsample scope.

---

### SCI-07 · `qc.duplication` registry source contract names Picard, but the real driver parses fastp
- **Severity:** Low · **Confidence:** Confirmed · **Category:** design inconsistency
- **Evidence:**
  - `src/pipeguard/metrics/metric_registry.yaml:100-103` — `module: picard_markduplicates`, `source_file: markdup_metrics`, `raw_field: PERCENT_DUPLICATION`.
  - `scripts/run_giab_pipeline.py:183` — `dup = d["duplication"]["rate"] * 100.0` (duplication actually comes from **fastp**, not Picard markdup).
- **Actual:** the registry's declared source contract for `qc.duplication` (Picard `PERCENT_DUPLICATION`, a fraction) does not match the real parser (fastp `duplication.rate`, multiplied to percent). Numerically consistent — the mapping declares `raw_unit="percent"` and the driver emits percent, so the gate is correct — but the source provenance recorded/documented for the metric is wrong, which undermines "standalone-interpretable" `MetricValue` provenance (ADR-0007).
- **Min fix:** either add a fastp-sourced entry/alias for the reads-derived duplication metric, or update the `source` block to reflect the fastp path actually used by the driver.
- **Demo-critical:** N. **Risk of fixing now:** Low.

---

### SCI-08 · The "variant gate" is a DP-only stub; GQ/Ts-Tv/allele-balance are ungated and AF is absent
- **Severity:** Low · **Confidence:** Confirmed · **Category:** scientific-correctness risk (honest-but-overstated label)
- **Evidence:**
  - `src/pipeguard/runbook.py:157-165` — the only variant threshold is `variant.dp`; `variant.gq` and `variant.titv` are registered + mapped (`metric_registry.yaml:306-352`, `mapping.py:38-39`) but carry **no** `QCThreshold`, so they are ungated observations.
  - No `INFO/AF`/gnomAD path (design-only), no caller-specific filters, and `variant.allele_balance` (`metric_registry.yaml:322`) has no parser.
- **Actual:** the variant gate scores only genotype depth (plus the off-by-default ClinVar route-to-human). This is honestly a call-quality stub, but the "variant gate" framing can read as broader coverage than DP.
- **Min fix:** none required for the hackathon; keep the DP-only scope explicit in UI/docs so it isn't read as full variant QC. (Post-hackathon: add GQ/AF thresholds.)
- **Demo-critical:** N.

---

### SCI-09 · Seven registered metrics have no parser — vocabulary-only, never computed
- **Severity:** Low · **Confidence:** Confirmed · **Category:** post-hackathon improvement
- **Evidence:**
  - `metric_registry.yaml` entries `qc.zero_cov_targets:193`, `qc.fold_enrichment:209`, `qc.fold_80:225`, `identity.ngscheckmate_match:241`, `identity.sex_concordance:257`, `contamination.freemix:273`, `variant.allele_balance:322`.
  - grep over `src/pipeguard/models.py`, `parsers.py`, `metrics/mapping.py` returns **0** references for each — no `QCMetrics` field, no parser, no mapping entry; none is in a runbook threshold.
- **Actual:** these are controlled-vocabulary entries only (the registry is intentionally the vocabulary layer). Contamination (verifybamid2 FREEMIX) is therefore **not** computed on the real-GIAB path. This is honest at the data layer, but must never be surfaced as "computed." Cross-check the UI (Truthfulness/Specialist 10) that a registered-but-unparsed metric isn't rendered as an observed value.
- **Min fix:** none needed; ensure any registry-driven UI list marks these as "vocabulary / not computed," not observations.
- **Demo-critical:** N.

---

### SCI-10 · Stale `mapping.py` docstring claims `cluster_pf` is unmapped
- **Severity:** Low · **Confidence:** Confirmed · **Category:** design inconsistency (doc drift)
- **Evidence:**
  - `src/pipeguard/metrics/mapping.py:54` — "Unmapped fields (e.g. `cluster_pf`) are omitted until the registry gains an entry for them."
  - But `mapping.py:27` — `("cluster_pf", "qc.cluster_pf", "percent")` maps it, and `metric_registry.yaml:77` registers `qc.cluster_pf`.
- **Actual:** the docstring example is stale — `cluster_pf` is now mapped and registered. Minor, but misleads a reader about the mapping's completeness.
- **Min fix:** update the example (e.g. cite a genuinely-unmapped field, or drop the parenthetical).
- **Demo-critical:** N.

---

## Honest surfaces (verified correct — clean signal)

- **Gate is on normalized values, not raw** — `src/pipeguard/rules.py:195-196` compares `mv.normalized_value` against the canonical threshold; a source raw-unit change cannot move a verdict. The SCI-01 defect is **display-only**; the decision is correct.
- **`card_readout.py` renders units correctly** — `api/card_readout.py:209-232` converts fraction→percent via `mv.normalized_value` (test `tests/test_card_readout.py:65` asserts `observed_display == "84.1%"`). This is the reference the buggy `rules.py` path should match.
- **G4 honored** — `DecisionCard.confidence` defaults `None` (`models.py:231-233`), documented "omitted until grounded (T-019)"; no heuristic bar.
- **G3 honored** — ClinVar `CLNSIG` quoted verbatim (`rules.py:387` `value=hit.clinvar_significance`, `source_field="CLNSIG"`; `parsers.py:291` "preserved VERBATIM"); route-to-human disarmed by default (`runbook.py:60` `significances: tuple[str, ...] = ()`).
- **Unit registry is fail-closed** — `metrics/registry.py:245-258` rejects a disallowed `raw_unit` and an unlisted conversion pair rather than guessing; `_CONVERSIONS` is percent↔fraction only; value-type guards catch a bool/int handed a nonsense value (`registry.py:236-243`).
- **Frozen-five guard exists** — `tests/test_metrics_mapping.py:72` `test_runbook_thresholds_key_on_registered_metrics` asserts every runbook `our_key` is registered.
- **Origin tagging is complete** — every run dir carries an `origin` marker (29 `contrived`, 1 `real-giab`); contrived-vs-real is honestly separable at the data layer.
- **Compiler drift guard** — `scripts/generate_reference_pipeline.py` + `germline_graph()` make the committed `pipelines/germline/` the compiler's byte-for-byte output, pinned by `test_nextflow_compile.py` (EVAL-006); "deterministic wiring" is accurate.
- **Reproducibility scope is honestly labeled** — `AnalysisRun` docstring (`provenance.py:57-59`) and EVAL-030 (`docs/quality/evaluation.md:499-523`) both scope reproducibility to gate/wiring and mark truth-set comparison as Phase-2 (not yet automated). SCI-03 is the *gap*, not a false claim.
- **CLINVAR-RTH fixture is scrupulously framed** — `data/RUN-2026-07-11-CLINVAR-RTH/NOTE.md` states `origin=contrived`, spike-only, benchmark sample, no pathogenicity authored. This is exactly the framing SCI-06 asks the real-GIAB dir to add.
