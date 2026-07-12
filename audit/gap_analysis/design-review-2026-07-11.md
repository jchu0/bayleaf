# Design Review & Remediation Plan — QC/Provenance Decision Gate

| Field | Value |
|---|---|
| **Date** | 2026-07-11 (MST) |
| **Type** | Adversarial design review + remediation plan (advisory) |
| **Method** | 6 independent read-only lenses (domain rigor, silent-pass/false-negative, adoption fit, AI value, architecture, scope), each grounded in the actual source — not the self-report. ~35 distinct findings. |
| **Status** | Post-hackathon roadmap. None of these is a correctness bug in the *shipped, tested* core (465+ tests green); they are gaps between what the product **claims** and what the code **wires**. |
| **Related** | `audit/AUDIT_PLAN.md`, `audit/SYNTHESIS.md` (prior release-hardening audit); `docs/adr/ADR-0001` (rules-decide/AI-narrates) |

---

## 0. The through-line (read this first)

Six critics looking at rigor, safety, adoption, AI, and architecture *separately* converged on **one shape**: a confident surface that claims more than the wired code delivers. To the builder's credit, **almost every gap is honestly labeled in the code** — `# NOT COMPUTED`, "never mutates the live runbook," "every reads-based run HOLDs," "no core data source." Nothing was hidden. The blind spot is **the sum**: those honest seams add up to a tool whose *headline capabilities are scaffolded, not connected*.

The same pattern recurs across five different "confident labels":

| Claimed | Actually wired |
|---|---|
| "provenance & QC decision gate" | no working identity/contamination detector; the one provenance rule cross-checks non-independent sources (§2) |
| "all checks passed" (PROCEED prose) | "no *modeled* rule objected"; missing data passes green (§1) |
| "grounded in GIAB truth" | benchmark VCF on disk, **never used** for concordance (§4) |
| "AI-assisted" | six agents, all **off by default**; live path mostly paraphrases (§8) |
| operator-authored thresholds / RBAC | Settings lifecycle reaches no verdict; auth shim enforces nothing (§5) |

**The good news:** the *bones are right* — a deterministic verdict, cited immutable evidence, a clean rules-decide/AI-narrates boundary (ADR-0001). That is the hard part and it holds. What is thin is the **wiring to reality**, and most of the highest-leverage fixes are small relative to what already exists.

**If you do only three things** (details in §9):
1. **Fail closed** — missing QC → HOLD, and one real identity/contamination check wired end-to-end. (Trust.)
2. **Let a real run in** — an nf-core/MultiQC ingest adapter. (Adoption.)
3. **Close or honestly label the config loop.** (Stop the surfaces that silently lie.)

---

## 1. Make the gate fail *closed*, not open  · **P0**

The gate's whole promise is that PROCEED means "examined and clean." Today PROCEED means "no *modeled* rule objected," and the two diverge exactly when data is missing — the case a safety gate must fail closed on.

- **1a · "No findings" is rendered as "all checks passed."** `aggregate_verdict([]) → PROCEED` (`synthesis/base.py:28-32`), then the stub writes "cleared every provenance, metadata, and QC check… No inconsistencies were found" (`synthesis/stub.py:50-56`). That sentence conflates "nothing tripped a rule we wrote" with "verified good."
  - **Fix:** change the empty-findings prose to state *coverage* — "passed the N checks that ran; contamination/identity not examined" — and put a checks-ran/checks-available count on the card instead of "all checks passed."
- **1b · Missing QC artifact evaporates into PROCEED.** `rules.py:453` guards the entire QC block with `if qc is not None:`. A sample on the sheet + intake metadata but with **no QC row at all** skips every threshold — including the `required=True` `cluster_pf` NA→HOLD that's supposed to be the backstop — and emits zero findings → PROCEED. `_check_presence` fires PROV-002 for *QC-without-sheet* but there is **no symmetric rule for sheet-without-QC** (`rules.py:85-130`).
  - **Fix:** a sample with no QC artifact is missing-data → **HOLD**, never PROCEED. Add the symmetric presence rule.
- **1c · `required=False` makes safety-adjacent metrics silently skippable.** Breadth, mapping rate, on-target, variant depth are `required=False` (`runbook.py:129-179`); a *missing* value returns `None` → no finding (`rules.py:194-217`). So a pipeline that simply doesn't emit breadth reads "all clear." The richer the check, the easier it evades the gate. Great mean coverage + terrible uniformity passes the coverage gate cleanly.
  - **Fix:** bind an **expected-metric set** to the named pipeline profile ("for germline-panel, breadth_20x MUST be present"). A missing *expected* metric becomes a finding, not a skip — restoring signal without NA-flagging genuinely lean runs.
- **1d · Absent check categories are invisible in the UI.** `MetricsPanel`/`QCReadout` only render gate groups that have rows (`g.rows.length > 0`), so "contamination: not examined" is inferred from a missing pill, never shown.
  - **Fix:** render a fixed catalog of expected categories with an explicit **"NOT RUN"** cell.

---

## 2. Wire one real identity/provenance check — the "provenance" claim needs a spine · **P0**

> ### On PROV-001 (the barcode check) — intent vs. framing
> **Builder's intent (correct and worth keeping):** PROV-001 is a **data-entry / wetlab-typo consistency check** — catch a human transcription error where two records that *should* agree disagree. It was never meant to detect a molecular index mismatch off reads.
> **What the critique still lands on:**
> 1. **The two sources aren't independent.** It compares `SampleSheet.csv` against `demux_stats.csv`, but the demux manifest is *produced using* the sample sheet — so a typo in the sheet propagates to both and would **not** be caught in a real run. The demo's S4 disagreement only exists because the fixture was hand-authored (`rules.py:43-82`; `data/mock_run_01/`). A consistency check needs two *independently authored* sources.
> 2. **The copy overclaims.** "Chain of custody intact" / "index swap" frames a consistency check as an identity/provenance guarantee.
> **Fix that honors the intent:** cross-check the sample sheet's Sample_ID/index against a **genuinely independent** record — your own accessioning/LIMS intake (`sample_metadata.csv`, the `Accession.tsx` CRM), which the wetlab authors separately. Then a real transcription typo between accessioning and the sheet actually surfaces. Reframe the card language to "sample-sheet ⋈ accessioning consistency," reserve "chain of custody" for a check that establishes identity (below), and make any index comparison reverse-complement-aware per instrument workflow.

- **2a · No contamination or sample-identity QC actually runs.** FREEMIX (VerifyBamID2), NGSCheckMate, and sex-concordance are all registered in the metric vocabulary but **computed by nothing** — 7 of 20 registry keys are `# NOT COMPUTED` (`metric_registry.yaml`), no parser, no rule. These are exactly the checks that catch a real sample swap or contamination — the canonical provenance failures. Your own repair/triage corpora *describe* FREEMIX in detail; the *check* doesn't exist.
  - **Fix:** wire **one** end-to-end on the GIAB path. VerifyBamID2 FREEMIX is a single command on your existing dedup BAM and gives a genuine, non-circular contamination gate to anchor the provenance claim. NGSCheckMate/sex-concordance next.
- **2b · The barcode match proves consistency, not identity.** A tube swap *upstream of library prep* puts the wrong subject's DNA behind the right barcode — barcodes match, PROV-001 is silent, PROCEED. Index hopping is equally invisible: `DemuxRecord.reads`/`pct_reads` are parsed (`parsers.py:193-204`) but **no rule reads them**, so undetermined-read fraction and per-sample yield dropouts are ungated.
  - **Fix:** genotype concordance (2a) is the real identity check. Additionally gate on % Undetermined reads and per-sample read-share from demux — the real signals of an index problem.

---

## 3. Let a real run *in* — the adapter you don't have · **P0/P1**

The promise is "no more reconstructing context from scattered files." Today the operator must reconstruct scattered tool outputs into a bespoke shape *before* the tool sees anything.

- **3a · The run-dir contract is a hand-shaped CSV no pipeline emits.** `parse_qc_metrics` reads a fixed-column `qc_metrics.csv` (`parsers.py:210-237`). Real output is `fastp.json`, `*.mosdepth.summary.txt`, `multiqc_data/multiqc_general_stats.txt`. **No MultiQC/fastp/mosdepth parser exists** — the only thing on earth that writes your format is `scripts/run_giab_pipeline.py`. So gating a real run means a human hand-transcribes scattered outputs into your five CSVs — the exact pain you promise to remove, moved upstream onto them.
  - **Fix:** an nf-core/MultiQC `results/` → `RunArtifacts` adapter is **the single highest-leverage feature you don't have.** Until it exists, the value proposition is unearned.
- **3b · No ingress for a real run.** The live boundary hardcodes `_FIXTURE_SAMPLES = {"HG002"}` (`intake.py:61`); every other sample honestly "skips (no reads on disk)." BaseSpace is a labelled mock. A real NovaSeq run / BaseSpace project / results dir has **no door in**.
  - **Fix:** the adapter (3a) plus a real (even minimal) ingress path for non-fixture reads.
- **3c · The metric registry defends a boundary the code never crosses.** The registry's stated purpose — "stable layer above drifting MultiQC keys," `aliases[]` shielding renames — is dead weight, because ingestion maps *typed `QCMetrics` fields*, not raw tool keys (`rules.py:456`). A real MultiQC rename still breaks you, because you never ingest that key.
  - **Fix:** this resolves *for free* once 3a exists — wire the registry to the real adapter so aliases resolve live keys. Until then, the anti-drift framing overstates what's built.
- **3d · Run discovery is hardcoded to the repo's `data/`; intake metadata the gate checks is partly driver-fabricated at the API boundary.** Two smaller adoption leaks in the same family — you can't point it at real storage, and the "provenance intake" partly grades its own homework.
  - **Fix:** make the run-store root configurable; ensure intake metadata comes from the operator/LIMS, not synthesized by the driver.

---

## 4. Back the "grounded in GIAB truth" claim · **P1**

`data/real-giab/` has the HG002 benchmark VCF + confident-region BED (the answer key), yet **no concordance is ever computed** — no hap.py/vcfeval/rtg, no precision/recall/F1. The variant "gate" just counts records from `bcftools call -mv` (not GATK HaplotypeCaller/DeepVariant, the clinical standard). So the *scientific-validation* claim is the same hollow shape as provenance and "all checks passed."

- **Fix:** run `hap.py`/`rtg vcfeval` against the on-disk truth VCF within the confident regions, surface precision/recall/F1 as real evidence — **or** drop the "grounded in GIAB truth" language until it's computed. This is your credibility with a domain audience; it's worth wiring.

---

## 5. Stop the surfaces that control nothing · **P1/P2**

- **5a · The Settings threshold-authoring stack is a ledger wired to nothing.** Draft→approve, RBAC, monotonic versioning, immutable audit, three DB backends — and `_active_runbook` **only ever returns `DEFAULT_RUNBOOK`** (`api/main.py:233-248`). Approving an override changes zero verdicts, and the payload is schemaless `dict[str, Any]`, so even the "future step" has nothing typed to apply. `settings.py:9-15` admits it.
  - **Fix:** either (a) give the override a **typed schema** and layer the latest `approved` override onto a per-run runbook copy in `_active_runbook` — closing the loop; or (b) label the surface in-product **"authoring only — not applied to runs."** Right now it silently lies.
- **5b · "Ask the agent" chat answers nothing.** `AgentComposer.submit()` appends two hardcoded strings and clears the draft — no `api.*` call, no Q&A endpoint exists, in *either* offline or "live" mode (`AgentComposer.tsx:27-41`). The quick-ask chips are exactly the questions an operator needs ("how sure is this a swap not contamination?") and it structurally can't answer any.
  - **Fix:** wire it to a real grounded Q&A endpoint (findings + corpus + this run's raw artifacts as context, same injection-bounding as the synthesizer), or delete it. A fake diagnostic conversation is worse than none.
- **5c · The assay×tissue Settings table has no core data source.** `SettingsAssayTable.tsx` hardcodes 3 assays × 2 tissues and admits "the assay×tissue matrix has no core data source — /api/config returns a flat runbook." The UI writes checks the core can't cash — this is the frontend of §6a.

---

## 6. Make the core extensible where it will need to flex · **P2**

- **6a · The runbook is single-dimensional.** `Runbook.qc_thresholds` is one flat `list[QCThreshold]` (`runbook.py:76-181`) — no axis for assay / platform / sample type. A real lab is N assays × M sample types with different gates. The moment a second assay is real, you must change the `Runbook` shape, the `evaluate_sample(...)` signature, *and* the runbook-selection seam simultaneously — a synchronized rewrite through the deterministic core, the most expensive place to touch.
  - **Fix:** a `RunbookSet` keyed on `(assay, sample_type, platform)` with a documented resolution/fallback order; resolve the threshold set **per sample** from its metadata. Do it now, while there's one assay.
- **6b · Adding a QC metric is a four-file hardcoded-string change.** Observed values flow through a flat pydantic model (`QCMetrics`, 13 named fields), a hand-maintained mapping tuple (`metrics/mapping.py`), and a hardcoded parser. A YAML-registered metric does nothing until four sites agree — which is *why* 7/20 keys are `NOT COMPUTED`. The "dynamic registry" is defeated at ingestion.
  - **Fix:** drive ingestion from the registry (a `dict[our_key, value]` keyed by the registry, not named fields), so "register a metric" is one edit.
- **6c · `QCThreshold` can't express a whole metric class.** It re-declares semantics the registry already owns and supports only one-sided gates — which is why Ts/Tv and fold-80 are parsed but "can't be scored."
  - **Fix:** add a two-sided / target-band gate type so Ts/Tv (~2.0–2.1 WGS / ~3.0 exome) and uniformity can actually gate.
- **6d · Seven near-identical stores × three backends is copy-paste wearing an abstraction's clothes.** ~1,300 core LOC + five triple-backend API stores for a demo on a pinned SQLite/JSONL fixture (whose own docs concede no multi-worker safety).
  - **Fix:** one generic store abstraction, or defer Postgres until a deployment needs it (see §7).

---

## 7. Right-size the scope (mostly acknowledged — noted for honesty) · **P3**

> **Context (added 2026-07-12): the Pipeline Builder is NOT scope creep.** It was a deliberate, *sanctioned*
> response to the Builder track's own suggested idea — *"a pipeline translator for a bioinformatician's
> collaborators: wraps an existing command-line analysis pipeline in an interface a bench scientist can run
> without touching the terminal"* — and the organizers explicitly allowed deviating from the original concept.
> So "the builder doesn't feed the gate" below is factually true but is **not a criticism**: the builder is a
> distinct, legitimate second feature with its own value proposition (bench-scientist pipeline execution), not
> a distraction from the gate. Read the effort-inversion point as *"invest in the gate too,"* not *"the builder
> shouldn't exist."*

You've explicitly green-lit the breadth ("the rest is gravy"), so this is FYI, not a mandate — but two points are worth internalizing:

- **The builder is a *second product* off the decision path.** Pipeline Builder (~7,500 LOC) + Nextflow codegen (~2,800) is **~4× the core gate**, and the verdict comes from `run_gate()` reading a *run directory* — it never touches the canvas; the intake driver runs a *fixed committed pipeline*, not the drawn graph. The thing with the most code doesn't feed the thing the product promises.
- **Effort inverted.** Last ~60 commits: 132 frontend / 113 docs / 35 api / 27 `src`. `rules.py` (the "trust anchor") and `runbook.py` are ~static while ~15 UI waves reshuffled chrome. Your differentiator got the least investment. The §1–4 work rebalances that.
- Lower-tier: Inbox/kanban is a generic productivity app; two frontend-only governance layers sit on an auth shim that trusts client-supplied role headers (governance *theater* — fine for a demo if labeled); Postgres×6 + HIPAA Safe-Harbor solve problems the demo doesn't have yet; 14 screens / 13 routes for a one-decision tool.

---

## 8. Make the AI earn its place · **P2**

- **8a · The live agent path mostly re-words prose the corpus already contains verbatim.** The stub copies retrieved entries directly (`triage/agent.py:110-113`; same in pipeline_repair/node_author); the live prompt forbids adding anything and the schema restricts output to the same fields — so Claude adds phrasing variance, not knowledge, on Opus tokens (`pipeline_repair` defaults `claude-opus-4-8`).
  - **Fix:** give the LLM materially more input than the corpus row (raw artifacts, cross-sample context) so it *can* say something new — or label these "curated remediation lookup," not "agents."
- **8b · "Retrieval" is a `rule_id→entry` dictionary that collapses on novel failures.** ~1 entry per existing rule, token-overlap scoring (no embeddings), query built from the finding's own `rule_id`/`title` — so it near-deterministically returns the row written for that rule and degrades exactly when a human needs help.
  - **Fix:** real semantic retrieval + a corpus that spans failure modes beyond the demo's fixed set.
- **8c · "AI-assisted," but all six agents default to stub** → the demo shows **zero live Claude** unless env flags are flipped. For a "Built with Claude" context this is worth a deliberate call: default the synthesizer on for the demo, or narrate honestly that the deterministic core is the star and AI is advisory.
- **8d · The triage note is redundant with the finding it explains** and starved of the one input (raw artifacts) that would let it add value.

---

## 9. QC metric correctness (real bugs, small fixes) · **P1**

- **9a · Duplication is effectively never gated.** `mapping.py` fixes `dup_rate` unit as `percent` (÷100). The driver writes fastp's rate ×100, but the committed real HG002 fixture stores `dup_rate=0.0057` (a fraction) → normalizes to 0.000057. The fixed per-field unit can't tell a fraction from a percent.
  - **Fix:** detect/normalize unit per source, or standardize the driver + fixtures on one representation and test it.
- **9b · `mean_coverage` conflates three assay contexts** — a Picard panel metric name (`MEAN_TARGET_COVERAGE`), a WGS 30× threshold, computed by mosdepth over "arbitrary chr20 smoke-test windows." For a real panel, 30× is a hard fail, not PROCEED.
  - **Fix:** bind coverage gates to an explicit assay + target region (via §6a); rename the metric to what's actually computed.
- **9c · "% reads identified" is mislabeled** (a demux concept) and mapped to fastp pass-filter survival; the demo's per-lane values sum to >100%, which is impossible for the labeled meaning.
  - **Fix:** relabel to what it gates (pass-filter rate), and make the demo fixture physically coherent.
- **9d · The gated set is a thin subset of standard QC** — missing insert-size, adapter/GC, per-tile quality, error-rate/PhiX, coverage uniformity (fold-80 registered, not computed), Ts/Tv (parsed, ungated per §6c).
  - **Fix:** ingest the flags MultiQC already emits (comes largely free with §3a) and gate the high-value ones.

---

## 10. Prioritized roadmap

| Priority | Theme | Why | First PR |
|---|---|---|---|
| **P0** | §1 fail-closed | A gate that greenlights missing data is unsafe | missing-QC→HOLD + "N checks ran / M not examined" prose (small, high-trust) |
| **P0** | §2 real identity check | The "provenance" claim needs a spine | VerifyBamID2 FREEMIX end-to-end on the HG002 BAM + a "contamination: not examined" UI state |
| **P0/P1** | §3 ingest adapter | Nothing real can enter today | MultiQC/fastp/mosdepth `results/` → `RunArtifacts` adapter |
| **P1** | §4 GIAB concordance | Backs the science claim | `hap.py`/`vcfeval` vs the on-disk truth VCF → precision/recall on the card |
| **P1** | §9 metric bugs | Cheap correctness | dup-rate scale + `mean_coverage`/`% reads` relabel |
| **P1/P2** | §5 close/label config loop | Stop surfaces that lie | typed override schema + apply in `_active_runbook`, or "authoring only" label |
| **P2** | §6 extensibility | Before a 2nd assay is load-bearing | `RunbookSet(assay, sample_type, platform)` |
| **P2** | §8 AI honesty | Earn the "AI-assisted" name | more input to agents, or relabel as lookup; deliberate demo default |
| **P3** | §7 scope | Sanctioned; rebalance effort toward the core | — |

---

## 11. What to preserve (do not break while fixing)

The review's whole premise is that the *foundation is right* — protect it:
1. **Rules decide, AI narrates** (ADR-0001) — the deterministic verdict, cited immutable `Finding`s, the advisory-only AI boundary. Every fix above keeps the verdict a deterministic function of rule findings.
2. **Cited evidence** — every rule authoring its own `Evidence`. The new checks (FREEMIX, concordance, presence) must cite the same way.
3. **Fail-safe posture** — the fixes push it *further* toward failing closed, never toward the LLM deciding.
4. **Honest labeling** — you already label seams; keep doing it. The remediation is to *close* the seams or *label them in-product*, never to paper over them.

**Bottom line:** the bones are a genuine, tested, defensible decision gate. The work here is wiring the confident surfaces down to reality — mostly small changes with outsized trust payoff, and exactly the stuff that's invisible from inside the build.
