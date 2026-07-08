# Risks

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all |
| **Related** | [evaluation.md](evaluation.md), [requirements/constraints.md](../requirements/constraints.md), [data/strategy.md](../data/strategy.md), [demo/demo_plan.md](../demo/demo_plan.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) |

## Overview

What could go wrong, ranked by exposure, with the concrete mitigation already in place
(or the trigger that would make us act). Each entry is `RISK-NNN` with category,
likelihood, and impact. This is a living list; the highest-value ones are the **demo**
and **domain-safety** risks, because they are the failure modes a judge or a downstream
clinician would actually feel.

## Technical

### RISK-001 — Parser normalization drift silently moves a verdict

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Medium |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** MultiQC reports percentages (`pct_*`, ×100) while fastp reports fractions
(0–1). Mixing them shifts a borderline sample across a threshold with no error.

**Mitigation.** A canonical [metric registry](../data/metric_registry.md) normalizes
units at the boundary; the pinned demo scenario ([evaluation.md](evaluation.md) EVAL-001)
locks the borderline S5 values so any drift fails a test.

**Owner / revisit trigger.** Any new parser or metric source — re-pin and add a case.

### RISK-002 — Content-hash instability from non-canonical serialization

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** If findings/cards were hashed over non-canonical JSON (key order, datetime
format), "immutable" hashes would churn and reproducibility (EVAL-002) would break.

**Mitigation.** `content_hash` hashes canonical JSON; `model_dump(mode="json")` is used
consistently. A real datetime-serialization bug here already caused a demo 500 and is now
regression-tested ([evaluation.md](evaluation.md) EVAL-021).

**Owner / revisit trigger.** Any change to a frozen model's fields or the hash input.

### RISK-003 — No measured performance envelope

| Field | Value |
|---|---|
| **Category** | Technical |
| **Likelihood** | Low |
| **Impact** | Low |
| **Status** | Accepted |
| **Added** | 2026-07-08 (MST) |

**Risk.** No throughput/latency benchmark exists; a large real run could be slower than
the interactive demo suggests.

**Mitigation.** Explicitly *not claimed* ([nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-032); demo is mock-scale. Accepted for the hackathon.

**Owner / revisit trigger.** First real-data run at panel/exome scale.

## Data

### RISK-010 — Committing PHI or raw reads

| Field | Value |
|---|---|
| **Category** | Data / Security |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Accidentally committing raw reads, PHI, or a large artifact into the repo.

**Mitigation.** Policy is accessions + fetch script, never raw reads
([strategy.md](../data/strategy.md), [nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-021); demo data is public/synthetic/contrived only; every artifact carries an
origin label (`real-giab` / `synthetic` / `contrived`).

**Owner / revisit trigger.** Adding the GIAB real-data track (T-013/T-017) — verify the
fetch-script pattern holds.

### RISK-011 — Synthetic data diverges from real artifact shapes

| Field | Value |
|---|---|
| **Category** | Data |
| **Likelihood** | Medium |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The synthetic generator could emit a dialect the production parsers accept but
real instruments never produce, making green tests misleading.

**Mitigation.** Generated runs are asserted to parse with the *existing* parsers
([evaluation.md](evaluation.md) EVAL-010); field names mirror nf-core/sarek + MultiQC
conventions ([nf-core-conventions.md](../data/nf-core-conventions.md)). Real GIAB data is
the eventual cross-check (EVAL-030).

**Owner / revisit trigger.** First real-data comparison; any generator feature.

## Product / domain safety

### RISK-020 — Overclaiming clinical or diagnostic capability

| Field | Value |
|---|---|
| **Category** | Product |
| **Likelihood** | Medium |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The tool is read as a clinical decision system, or a verdict/confidence is
taken as a diagnostic or pathogenicity claim.

**Mitigation.** Hard guardrails: no diagnostic/therapeutic/pathogenicity claims;
confidence omitted until grounded and labelled a heuristic; thresholds labelled
illustrative/per-assay; conservative language ([constraints.md](../requirements/constraints.md)
REQ-C-030..034). Rules decide, AI only advises (ADR-0001).

**Owner / revisit trigger.** Any UI/demo copy change; any move toward real deployment.

### RISK-021 — AI narration contradicts or appears to set the verdict

| Field | Value |
|---|---|
| **Category** | Product |
| **Likelihood** | Low |
| **Impact** | High |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** A viewer believes the LLM chose the verdict, eroding the core safety story;
or the model emits a number that looks authoritative.

**Mitigation.** The triage note type has no verdict/confidence field
([evaluation.md](evaluation.md) EVAL-020); the UI badges output `ADVISORY · STUB/CLAUDE`;
citations and addressed findings stay deterministic even on the claude path (EVAL-021).

**Owner / revisit trigger.** Any expansion of the agent's output schema.

## Demo

### RISK-030 — Live-AI path flaky or rate-limited mid-demo

| Field | Value |
|---|---|
| **Category** | Demo |
| **Likelihood** | Medium |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** The "flip AI on live" moment errors, times out, or is safety-refused in front
of judges.

**Mitigation.** Any error/refusal degrades to the stub — same structure, templated prose,
$0 ([demo_plan.md](../demo/demo_plan.md) §Fallbacks, EVAL-021). The default demo never
calls the API.

**Owner / revisit trigger.** Rehearsal; API status on demo day.

### RISK-031 — React/API stack fails on the demo machine

| Field | Value |
|---|---|
| **Category** | Demo |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Node/Vite/port issues (we already hit an :8000 Docker clash → moved to :8010)
break the React UI during setup.

**Mitigation.** Layered fallback: React/API → offline **Streamlit** over the same core
(one process, always green) → recorded walkthrough/screenshots
([demo_plan.md](../demo/demo_plan.md) §Fallbacks; [nonfunctional.md](../requirements/nonfunctional.md)
REQ-NF-042).

**Owner / revisit trigger.** Dry run on the actual demo machine.

### RISK-032 — Budget exhaustion from accidental live-AI usage

| Field | Value |
|---|---|
| **Category** | Demo / Security |
| **Likelihood** | Low |
| **Impact** | Medium |
| **Status** | Mitigating |
| **Added** | 2026-07-08 (MST) |

**Risk.** Live Claude left on during dev burns the fixed **~$200** budget before the demo.

**Mitigation.** AI is off by default; every seam is stub-first and $0; live is opt-in per
env var and flipped on only for the demo moment ([constraints.md](../requirements/constraints.md)
REQ-C-010/011; MEMORY: conserve-API-credits).

**Owner / revisit trigger.** Any session that sets `PIPEGUARD_*=claude`.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. Likelihood/impact
are judgement calls for this sprint, not measured probabilities.
