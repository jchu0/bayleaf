# Journal — 2026-07-11 (MST) — D2 end-to-end, D3 share egress wired, UIC-16 closed

| Field | Value |
|---|---|
| **Focus** | SWEEP the docs owed by four commits already landed on `main`: D2 (route-to-human fires end-to-end against a committed run), D3 backend + frontend (de-identified share egress, `DATA_EXPORTED` event), and UIC-16 (Builder cards get typed four-side ports). Pure doc-keeper work; no product code, tests, or fixtures touched. |
| **Participants** | doc-keeper subagent, invoked in SWEEP mode |
| **Outcome** | Every doc obligated by the Doc-update map for the four commits is updated and grounded directly in the code/tests read. Several pre-existing drifts found in passing and fixed — the class of bug this contract calls the #1 drift: **a built/wired feature still documented as "not yet wired" / "never fires end-to-end."** |

## Discussion

### What landed in code (verified by reading, not the commit messages)

1. **`8ecc2a1` (D2).** `api/main.py` gains `_active_runbook(run_id)`: reads an optional
   `route_to_human` marker file (comma-separated ClinVar significances) from the run dir and, if
   present, arms a copy of `DEFAULT_RUNBOOK`'s `RouteToHumanPolicy` for that run only;
   `_evaluate(run_id)` now calls it instead of the bare `DEFAULT_RUNBOOK`. New fixture
   `data/RUN-2026-07-11-CLINVAR-RTH/` (`origin=contrived`): clean `qc_metrics.csv`, a
   `variants.csv` spiking one verbatim-cited ClinVar Pathogenic BRCA1 candidate (`VCV000017661`)
   HG002 does not actually carry, the `route_to_human` marker (`Pathogenic,Likely_pathogenic`),
   and a `NOTE.md` stating the honesty caveat inline. Read `tests/test_route_to_human.py`'s new
   `test_clinvar_rth_fixture_escalates_via_per_run_arming`: asserts the fixture's runbook is armed,
   the gate ESCALATEs HG002 via `VAR-RTH-001` with a verbatim `CLNSIG=="Pathogenic"` evidence row,
   and a stock committed run (`RUN-2026-07-04-GIAB-A`) stays disarmed. 10 tests in that file now
   (was 9).
2. **`076ecd4` (D3 backend).** `src/bayleaf/provenance.py` gains
   `EventType.DATA_EXPORTED = "data.exported"` — a new entry in the core event vocabulary, with an
   inline comment explaining it's an egress transform, never a gate input. `api/main.py` gains
   `POST /api/runs/{run_id}/share` (`require_role("approver")`): builds one row per decision card
   (sample_id/verdict/headline/rationale/n_findings + intake identity), runs each through
   `api.safe_harbor.redact_record`, sha256-hashes the emitted JSON, and returns a `ShareBundle`
   (`rows` + a `ShareManifest`: policy id, n_rows, origin, the content hash, event id, the 18
   §164.514(b)(2) classes, a disclaimer naming it "NOT certified/attested" + "NOT a compliance
   claim"). The event is recorded via new `api/share_ledger.py` — a **separate**, gitignored,
   append-only JSONL (`BAYLEAF_SHARE_LEDGER`), not the gate's own `EventLedger`. Read the whole
   module: its docstring explains why — the gate ledger is a deterministic re-derivation
   (`@lru_cache`'d `_evaluate`) that must stay cacheable, while a share is a live side effect that
   must survive a restart. `get_run` merges `share_events(run_id)` into `RunDetail.events` live
   (sorted by `created_at`), on a **copy**, never mutating the cached object — confirmed by reading
   the merge code around line 496–504 of `api/main.py`. `.gitignore` gains `share.events.jsonl`.
   Read `tests/test_share_egress.py` in full: 5 tests — approver-required (403 for viewer/reviewer),
   unknown-run 404, direct identifiers dropped + scrub labelled, the recorded event's content hash
   matches the manifest and the actor is `human:<id>`, and the gate's cards are byte-identical
   before/after a share (ADR-0001 pinned).
3. **`263390a` (D3 frontend).** `frontend/src/types.ts`/`api.ts` gain `ShareBundle`/`ShareManifest`
   + `api.shareRun(runId)` (a `write<>` POST, so the RBAC actor header rides). `provenance.ts` joins
   `data.exported` into `EVENT_META` (ShieldCheck icon, "Data shared" label) and a `summarizeEvent`
   case reading `n_rows`/`policy_id`/`origin` from the payload — worded as a scrub *version*, never
   a compliance claim. `Provenance.tsx` gains a `ShareAction` component: `if (!isApprover) return
   null` (absent, not merely disabled, for a non-approver), a `useConfirm()` dialog naming the scrub
   + the "NOT attested" caveat + that it's recorded, then `api.shareRun` → toast the real manifest
   → `onShared()` refetches `api.run(runId)` so the new `data.exported` row appears without a full
   page reload.
4. **`12a9913` (UIC-16).** `frontend/src/components/BuilderShared.tsx` gains `portSide(kind, dir)`,
   `layoutPorts()`, `cardHeight()`, `NODE_W = 232` (was 168/208), `PORT_R`, `CARD_HEADER_H`/
   `CARD_FOOTER_H`. Read `portSide()`: `REF_IN_KINDS` (top) and `METRIC_OUT_KINDS` (bottom) are
   explicit sets; I grepped every kind in those sets against `BTOOLSPEC`'s actual `ins`/`outs`
   arrays and confirmed several (`fastp_html`, `samtools_stats`, `adapter_fasta`, the mosdepth
   `*_dist`/`per_base` family, `vcf_index`, `multiqc_html`) are **not** present in any tool's real
   `ins`/`outs` — so they are anticipated by the placement logic but still absent from
   `ARTIFACT_KINDS`, confirming `builder-cards/README.md` §5 item 4 (registering reserved kinds)
   is still open even though items 1–3 (four-sided ports, larger cards, half-circle visual) are
   now closed. `BuilderCanvas.tsx`'s render and wire-endpoint math both call `layoutPorts()`, so a
   wire can't detach from its port by construction.

### Doc-update map sweep

Walked [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map) against the
four commits. Fired rows and what I did:

1. **🔴 `provenance.py` `EventType` vocabulary changed → `data/schemas.md` + `data/provenance.md`
   (duplicated, update both) + `ADR-0002`.** Added `data.exported` to schemas.md's event-vocab
   list; added a new "A second, separate ledger for share events" section to provenance.md
   explaining why `data.exported` lives outside the gate's `EventLedger`; added a numbered item +
   date bump to ADR-0002's "Realized" section (mirroring its existing precedent for documenting
   what got built after acceptance).
2. **🔴 new tests → `quality/evaluation.md`.** Recounted with `uv run pytest --collect-only -q`
   (406 collected, was 381 — this task's own stated baseline of "403 passed / 3 skipped" confirmed
   the total) + `git ls-files 'tests/*.py' | wc -l` (26, was 24) + a per-file breakdown via
   `pytest --collect-only -q | grep ::test | sed ... | sort | uniq -c`. Updated the headline
   sentence + the per-file list (inserted `test_node_author` (19) and `test_share_egress` (5),
   bumped `test_route_to_human` 9→10). Extended **EVAL-012**'s Automated/Method with the new
   committed-fixture test; added a new **EVAL-051** for the share-egress endpoint (De-identification
   cases section); fixed EVAL-050's stale "not yet exercised end-to-end" closing line to point at
   EVAL-051.
3. **⚪ decision made → an ADR.** D2/D3 firing end-to-end are extensions of an already-accepted
   decision (ADR-0018), not new decisions needing a new ADR — added a "Realized (2026-07-11)"
   section to ADR-0018 itself (same pattern as ADR-0002's), naming exactly what's built vs. still
   narrower than the Decision-6 design, and updated its Status/Date/Related fields.
4. **⚪ scope/wishlist/"built" changes → `scope-and-wishlist.md` (+ functional.md, tasks.md).**
   Fixed wishlist #14's stale "not yet wired to any egress endpoint" line; added
   **REQ-F-084** (the share endpoint) and extended **REQ-F-018** (route-to-human, now end-to-end)
   in `functional.md`; fixed REQ-F-083's UIC-16 sub-bullet (was "partial," now closed inline);
   fixed **REQ-NF-023** in `nonfunctional.md` (same stale "not yet wired" claim); added task rows
   **T-119** (D2 end-to-end), **T-120** (D3 wired), **T-121** (UIC-16 closed) to `tasks.md`, and a
   forward-pointer from T-104's own status line.
5. **🟠 new `api/` endpoint / changed capability → `architecture.md` + `data-platform-and-archivist.md`
   + `functional.md`.** Added a "Wave 11" bullet to architecture.md's Component map (mirroring the
   existing "Wave N" pattern) and fixed its own stale UIC-16 "explicitly deferred" line in the Wave
   10 paragraph immediately above it. Fixed `data-platform-and-archivist.md`'s de-id paragraph
   (line ~152) which explicitly said "not yet wired to any egress endpoint" for `safe_harbor.py` —
   this was the same drift as scope-and-wishlist #14 and nonfunctional REQ-NF-023, all three
   apparently written at the same 2026-07-10 sitting and now all stale together.
6. **🟠 `BuilderCanvas.tsx`/`BuilderShared.tsx` port/geometry change → `design/builder-cards/` +
   `design/ui-conventions.md` UIC-16.** Rewrote builder-cards/README.md §5 (items 1–3 closed,
   grounded in the actual `portSide`/`layoutPorts`/`NODE_W` code; item 4 stays open with the exact
   grep evidence). Flipped `ui-conventions.md`'s UIC-16 row 🟡→✅ and added a dated closure note to
   the doc's top "Implementation" block. Added a UIC-16 paragraph to
   `design/frontend/README.md` §6 (the doc's own "Ports render as half-circles..." line predates
   this and would otherwise silently under-describe the new four-sided geometry).
7. **🔴 doc create/move/rename/status flip → `TABLE_OF_CONTENTS.md`.** No new canonical doc was
   created (only this journal, which the journal/ folder's existing ToC row already covers) and no
   doc's `Status` field flipped — `design/variant-interpretation.md` stays 🚧 (Proposed) since most
   of it is still unbuilt. Refreshed the ToC's one-line description of that doc for accuracy
   (route-to-human "fires against a committed run" / de-id "wired to a narrower egress"), a content
   fix rather than a status-flip trigger, and bumped the ToC's own `Last updated`.

### Drift found in passing (not caused by these four commits, fixed anyway)

Grepping `docs/` for `safe_harbor`/`route_to_human`/`route-to-human` before editing (per the
"ground every claim in code" mandate) surfaced a cluster of stale claims all written on
2026-07-10, all now false, all fixed in this sweep:

1. **`docs/data/qc_metrics.md`** (lines ~144–146, ~196): "off by default in every shipped
   fixture — no committed run carries an armed `route_to_human` policy" and "no committed fixture
   arms it." Both false as of `8ecc2a1`. This file was **not** in the task's explicit "at minimum"
   list — found only by grepping for the topic before writing the D2 section elsewhere. Fixed with
   a dated addendum naming the one armed fixture, keeping every unmarked run correctly described as
   still disarmed.
2. **`scope-and-wishlist.md` #14 / `nonfunctional.md` REQ-NF-023 / `data-platform-and-archivist.md`
   §2.1d** — all three said `safe_harbor.py` was "not yet wired to any egress endpoint." All three
   fixed to describe the real (narrower-than-designed) wiring, each keeping the honest caveat that
   the full Share window (scope/location/security-level) is still unbuilt.

### What I deliberately did not touch

- **`design/agents.md`** — no new advisory agent landed (route-to-human is a rule, not an agent;
  the share endpoint is a plain egress transform, not an agent). Map row "a new advisory agent...
  → design/agents.md" does not fire.
- **`requirements/constraints.md`** — no new dependency added (D3 reuses `api/deid.py`'s salt env
  var pattern, D2 adds no dependency, UIC-16 is pure geometry in existing files).
- **`design/frontend/frontend-design-brief.md` / `pipeline-builder-brief.md`** — these are the
  stable v1/v2 design specs, not build-status trackers; `design/ui-conventions.md` and
  `design/builder-cards/README.md` are the correct build-status owners per the ToC's own framing,
  and both were updated.
- **`Admin.tsx`'s Activity feed** — confirmed by reading `FeedKind` (`'threshold' | 'pipeline' |
  'ticket' | 'access' | 'actas'`) that a share does **not** yet surface there; documented this as
  an honest scope gap everywhere the full Share-window design is referenced, rather than silently
  implying parity with the ADR-0018 §Decision-6 text ("audited `ShareEvent` to the Admin Activity
  feed").

## Decisions

| Decision | Distilled to |
|---|---|
| Document D2/D3's 2026-07-11 build as a "Realized" section appended to ADR-0018 itself (not a new ADR) — these are build increments of an already-accepted decision, not a new load-bearing choice; the pattern mirrors ADR-0002's own "Realized" section. | `docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md` |
| Add REQ-F-084 as a new functional requirement for the share endpoint (rather than folding it silently into REQ-F-018's route-to-human item) — it is a distinct capability (an egress action, RBAC + audit) with its own honest scope-narrowing note, and the repo's convention is one REQ-F per shipped capability (see REQ-F-070 download, REQ-F-077 Inbox, etc.). | `docs/requirements/functional.md` REQ-F-084 |
| UIC-16 flips to ✅ (not left at 🟡) on the strength of the larger-card + four-sided-port ask being closed, even though builder-cards §5 item 4 (registering a handful of still-unused reserved kinds) stays open — that residual item was never part of what UIC-16's own row description asks for; it is documented as an open item under builder-cards/README.md §5, not hidden. | `docs/design/ui-conventions.md` UIC-16 |

## Open questions & TODO

- `builder-cards/README.md` §5 item 4 (registering `fastp_html`/`samtools_stats`/mosdepth
  `*_dist`/`vcf_index`/`multiqc_html` as real `ARTIFACT_KINDS` with a producer) remains open.
- The full ADR-0018 §4 Share window (scope/location/security-level selection, staged destinations,
  an Admin-Activity-feed audit row) remains unbuilt; today's `POST /api/runs/{id}/share` is one
  fixed action layered on top of the same scrub module.
- The interpretation agent, `RunReport`, gnomAD AF / inheritance-fit evidence, and the ClinVar/
  gnomAD fetch scripts remain unbuilt (unchanged from the 2026-07-10 sweep).

## Distilled into

- [docs/adr/ADR-0002-event-driven-core-provenance-ledger.md](../adr/ADR-0002-event-driven-core-provenance-ledger.md) — Realized §3 (`data.exported`)
- [docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) — new Realized §, metadata table
- [docs/data/schemas.md](../data/schemas.md) — event vocabulary
- [docs/data/provenance.md](../data/provenance.md) — event vocabulary + new share-ledger section
- [docs/data/qc_metrics.md](../data/qc_metrics.md) — Status note + Implementation-status addendum (drift fix)
- [docs/design/variant-interpretation.md](../design/variant-interpretation.md) — §0/§2/§4/§5/§6
- [docs/design/builder-cards/README.md](../design/builder-cards/README.md) — §5 rewritten, header
- [docs/design/frontend/README.md](../design/frontend/README.md) — §6 ports/cards note
- [docs/design/ui-conventions.md](../design/ui-conventions.md) — UIC-16 → ✅, top note
- [docs/design/architecture.md](../design/architecture.md) — Component map "Wave 11" + Wave-10 fix
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — de-id paragraph (drift fix)
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-018 extended, REQ-F-083i fixed, new REQ-F-084
- [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) — REQ-NF-023 (drift fix)
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — #14 (drift fix)
- [docs/quality/evaluation.md](../quality/evaluation.md) — census (406/26/403 pass/3 skip), EVAL-012 extended, EVAL-050 fixed, new EVAL-051
- [docs/planning/tasks.md](../planning/tasks.md) — T-119, T-120, T-121 (new), T-104/T-118 pointers
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — variant-interpretation.md row description
- [CLAUDE.md](../../CLAUDE.md) — Current code map items 1/2, new "Wave 11" paragraph
