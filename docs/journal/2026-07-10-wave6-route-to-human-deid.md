# Journal — 2026-07-10 (MST) — Wave 6 doc sweep: route-to-human (VAR-RTH-001) + conservative de-id (D2/D3)

> **Naming note (2026-07-13, MST):** this dated entry predates the rename **route-to-human → flag-for-review** (`VAR-RTH-001 → VAR-FFR-001`, `RouteToHumanPolicy → FlagForReviewPolicy`, `_check_route_to_human → _check_flag_for_review`, the `route_to_human` field/marker + `route_to_human.json` stage key → `flag_for_review*`, `tests/test_route_to_human.py → tests/test_flag_for_review.py`). The old names below are kept as accurate-at-the-time; current-state docs use the new names. See [2026-07-13-flag-for-review-rename-and-page-naming.md](2026-07-13-flag-for-review-rename-and-page-naming.md).

| Field | Value |
|---|---|
| **Focus** | SWEEP the docs owed by two backend commits that implement ADR-0018's maintainer-decided D2 (route-to-human gate rule) and D3 (conservative Safe-Harbor-style de-id) — the first two build increments of the "Wave 6" variant-interpretation design (T-104). Pure doc-keeper work; no product code touched. |
| **Participants** | doc-keeper subagent, invoked in SWEEP mode |
| **Outcome** | Every doc obligated by the Doc-update map for the two commits (`1882226`, `0101f29`) is updated and grounded in the actual code; one pre-existing drift found and fixed in passing (a "built feature marked deferred" gap in `design/variant-interpretation.md`, plus a missing ToC row for that same doc). CLAUDE.md's code map explicitly waived, with precedent cited. |

## Discussion

### What landed in code (verified by reading, not the commit messages)

1. **`1882226`** — `src/bayleaf/models.py` gains `VariantCall` (sample_id + optional gene/hgvs/
   clinvar_significance/clinvar_review_status/clinvar_accession/clinvar_version — ClinVar fields
   stored VERBATIM, never renormalized) and `RunArtifacts.variant_calls: list[VariantCall]`
   (folded into `sample_ids()`). `src/bayleaf/parsers.py` gains `parse_variant_calls` (tolerant
   `variants.csv` reader, absent file → `[]`, alt column spellings for `clnsig`/`clnrevstat`/
   `clnacc`), wired into `load_run`. `src/bayleaf/runbook.py` gains `RouteToHumanPolicy`
   (`significances: tuple[str, ...] = ()` — empty ⇒ `.armed is False`) + `Runbook.route_to_human`.
   `src/bayleaf/rules.py` gains `_check_route_to_human` → rule id **VAR-RTH-001**
   (`Category.VARIANT` → `Gate.VARIANT` via the existing `_CATEGORY_GATE` map, `Severity.
   CRITICAL`, `suggested_verdict=Verdict.ESCALATE`), wired into `evaluate_sample` after the
   existing pipeline-trace check. Read every line of all four files plus `tests/
   test_route_to_human.py` (9 tests) to confirm: disarmed by default, verbatim ClinVar quoting,
   separator-/case-insensitive *matching* only (never alters the quoted string), a review-status
   floor, and an end-to-end test asserting the armed run's card verdict is ESCALATE while the
   disarmed run's finding set is byte-identical to a run with no variant data at all.
2. **`0101f29`** — new `api/safe_harbor.py` (not `src/bayleaf/`, correctly kept out of the
   framework-agnostic core since it's an egress-path transform, ADR-0001): `redact_free_text`
   (regex classes: email/URL/SSN/phone/IP/date/ZIP/long-numeric-id → `[REDACTED:CLASS]`),
   `generalize_date` (year-only, fail-closed to `[REDACTED:DATE]` on no recognizable year),
   `cap_age` (>89 → `"90+"`), `redact_record` (drops direct identifiers, generalizes dates,
   redacts free text, caps age, defers everything else to `api/deid.py`'s existing policy),
   `HIPAA_SAFE_HARBOR_CLASSES` (18-tuple documenting every §164.514(b)(2) class). Read the full
   module + `tests/test_safe_harbor.py` (8 tests): confirmed the honesty guardrail is itself
   tested (`test_policy_is_labelled_style_not_certified`) and the ADR-0001 boundary is tested
   (`test_redact_record_never_touches_verdict_or_gate`). Grepped `api/` and `src/` for
   `safe_harbor` — only the module and its test import it, confirming it is **not yet wired to
   any egress endpoint** (`GET /api/export` still runs `api/deid.py`).
3. Neither commit introduces a new `EventType` (checked `provenance.py`/`data/provenance.md`):
   a `VAR-RTH-001` finding rides the existing generic `finding.emitted` → `verdict.decided`
   vocabulary, same as every other rule. Neither adds a new metric-registry `our_key` (it is a
   policy-driven `Finding`, not a `QCThreshold`), so `metric_registry.md` needed no change.
   `qc_metrics-sources.md` already documents `CLNSIG`/`CLNREVSTAT` citations (§F) — no new claim
   to ground there.

### Doc-update map sweep

Walked [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map) against the
two commits' diff. Fired rows and what I did:

1. **🔴 models.py new field/type → `data/schemas.md`.** Added a `VariantCall` block (mirroring the
   existing `TraceRecord` block) to the "Intake bundle" section + folded `variant_calls[]` into
   the `RunArtifacts` collection list + a short `RouteToHumanPolicy` pointer to qc_metrics.md.
2. **🟠 runbook.py/rules.py new rule/gate assignment → `data/qc_metrics.md`.** Added a new
   "Route-to-human policy (VAR-RTH-001)" section (parallel to the existing "Pipeline / operational
   rules (PIPE-001, EXEC-001)" section) + annotated the Gate-3 "Flagged variant" row + the
   Implementation-status section. **Did NOT touch ADR-0013** — the verdict this rule suggests
   (ESCALATE) is not a new decision-policy addition; ADR-0013's existing "provenance/identity →
   ESCALATE" policy item already generalizes to this rule's category (variant, review-routing).
   Judgment call, recorded as a waiver below.
3. **🔴 new tests → `quality/evaluation.md`.** Recounted the census with
   `uv run pytest --collect-only -q` (381 collected) + `uv run pytest -q` (378 passed, 3 skipped)
   + `git ls-files 'tests/*.py' | wc -l` (24 files); updated the headline sentence + the
   per-file breakdown (inserted `test_route_to_human` (9) and `test_safe_harbor` (8) in
   size-sorted position) and added two new cases: **EVAL-012** (route-to-human, Failure-mode
   section) and **EVAL-050** (the safe-harbor scrub, a new "De-identification cases" section
   mirroring the existing Notify-port-cases pattern for an off-gate transform).
4. **⚪ wishlist/"built" changes → `requirements/scope-and-wishlist.md` (+ mirror
   `functional.md`, `tasks.md`).** Updated wishlist #14 (de-identification) to record the new
   `api/safe_harbor.py` module, honestly flagging it as built-but-unwired. Added
   **REQ-F-018** (route-to-human) to `functional.md` (precedent: EXEC-001 got REQ-F-017 in the
   same pattern, `fd4772e`) and extended **REQ-NF-023** (de-identification precondition) in
   `nonfunctional.md` to name both de-id modules and their conservatism levels. Added task row
   **T-109** to `tasks.md` (the two commits, chronologically after T-108) and a short pointer
   from T-104 to it.
5. **🟠 `design/data-platform-and-archivist.md`** — this doc's own de-id paragraph (§2.1d) cited
   the old deid.py module as "not the Safe-Harbor / Expert-Determination scrub of the full module
   (still wishlist #14)." Since a Safe-Harbor-*style* module now exists, added a second bullet
   describing it (built, unwired) rather than leaving the old sentence implying nothing beyond
   `deid.py` exists.

### A pre-existing drift found in passing (not caused by these two commits)

While reading `design/variant-interpretation.md` for grounding, found it still said (written
2026-07-10 *before* the maintainer's sign-off) that route-to-human was "an off-by-default,
operator-owned config seam **pending maintainer sign-off**" and listed "the route-to-human config
rule" under "**Deferred / labelled seams (documented, not built)**." Both statements are now false
— the maintainer signed off (ADR-0018 D2) and the rule is built. This is exactly the class of bug
CLAUDE.md's habits call out as the #1 drift to fix: **a built feature still marked deferred**.
Fixed with a new §0 "Build status update" section (naming precisely what's built vs. still
design-only) plus inline corrections in §2/§4/§5/§6, rather than rewriting the whole document
(most of it — the interpretation agent, `RunReport`, the Share window, gnomAD/inheritance
evidence — genuinely remains unbuilt). Also found `design/variant-interpretation.md` was never
added to `TABLE_OF_CONTENTS.md`'s Design table despite being linked from ADR-0018's Related field
and ADR table row — added it (🚧, since two of ~6 pieces are built).

### What I deliberately did NOT touch

- **`ADR-0018` itself** — out of scope per the task; already updated by the prior session
  (Status → Accepted, Maintainer decisions section, D1/D2/D3 recorded).
- **Wave-7 UI docs** — out of scope per the task; these two commits are core-only
  (`git diff --stat` on both shows no `frontend/` files).
- **`ADR-0013`** — see waiver above; no new decision policy, an existing verdict category
  extended to a new rule.
- **`CLAUDE.md`'s "Current code map"** — see the Decisions table below.

## Decisions

| Decision | Distilled to |
|---|---|
| Waive `CLAUDE.md`'s "Current code map" for this sweep, even though the Doc-update map's ⚪ row ("a module added → CLAUDE.md + this map") literally fires for two new modules (`VariantCall`/`RouteToHumanPolicy` in the core, `api/safe_harbor.py`). Precedent: EXEC-001 (a comparably-sized new gate rule + new core model `TraceRecord`, commit `fd4772e`) also did **not** touch `CLAUDE.md` — grepped the current file for `EXEC-001`/`TraceRecord`, zero hits, confirmed even the post-hoc doc-keeper-trial cleanup (`1c14dff`) didn't add it. `CLAUDE.md`'s code map in practice tracks major batches/waves (frontend "Wave N" summaries, T-082-scale core batches), not every individual rule addition — the task instructions for this sweep also didn't name it among the likely-owed docs. | This journal entry (no ADR — a documentation-scope judgment call, not a product decision) |
| Do not add/change `ADR-0013` (gate architecture + verdict policy) for VAR-RTH-001. The rule's `suggested_verdict=ESCALATE` fits ADR-0013's existing "provenance/identity → ESCALATE" verdict-policy item; it is a new **rule**, not a new **decision policy** — no verdict category, gate, or aggregation rule changed. | `data/qc_metrics.md` §Route-to-human policy (documents the rule under the existing Gate 3 / verdict-policy framing, no ADR-0013 edit) |

## Open questions & TODO

- The rest of ADR-0018's phasing (interpretation agent, `RunReport`, the Share window that would
  wire `api/safe_harbor.py` as the default L2 policy, gnomAD AF / inheritance-fit evidence, the
  ClinVar/gnomAD fetch scripts) remains unbuilt — tracked at `design/variant-interpretation.md` §0
  and `tasks.md` T-104.
- No fixture in the repo arms `RouteToHumanPolicy` or ships a `variants.csv` — the rule has never
  fired end-to-end against a committed run. A future demo/eval fixture (contrived, `origin=
  contrived`) would need to be added deliberately to exercise it live, per ADR-0018's "demo
  substrate honesty" note (D2).

## Distilled into

- [docs/data/schemas.md](../data/schemas.md) — `VariantCall`, `RouteToHumanPolicy` pointer, intake-bundle collection list
- [docs/data/qc_metrics.md](../data/qc_metrics.md) — §Route-to-human policy (VAR-RTH-001), Gate-3 table annotation, implementation status
- [docs/quality/evaluation.md](../quality/evaluation.md) — test census (381/24/378 pass/3 skip), EVAL-012, EVAL-050
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-018
- [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) — REQ-NF-023 extended
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — wishlist #14
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — §2.1d de-id paragraph
- [docs/design/variant-interpretation.md](../design/variant-interpretation.md) — §0 build-status update + §2/§4/§5/§6 corrections
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — indexed `design/variant-interpretation.md`
- [docs/planning/tasks.md](../planning/tasks.md) — T-109 (new), T-104 pointer
