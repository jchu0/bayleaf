# Journal — 2026-07-10 (MST) — provenance download, QC enrichment, builder fixes, demo login (doc sweep)

| Field | Value |
|---|---|
| **Focus** | SWEEP the Doc-update map for nine commits landed on `main` since the last sweep (`fa3b6c3`): Provenance artifact download + full digest + a real QC input (T-077), four UI refinements (T-078), a Grafana dashboard (T-079), a hash-not-sha256 label + monitoring chart fix (T-080), a demo login gate + real admin role (T-081), QC enrichment to a full three-gate readout + a same-day follow-up (T-082), and Pipeline Builder connector/tool-I/O + canvas-navigation fixes (T-083/T-084). Ground every claim against the actual diffs before touching docs. |
| **Participants** | doc-keeper subagent (Claude Code), maintainer (James Hu, prior session) |
| **Outcome** | 13 docs updated (+ this journal); one real behavior-vs-doc drift found and fixed (Admin's gating was documented as "any approver" in three places — architecture.md, functional.md REQ-F-066, and the (previously missing) frontend README — when the code has gated on a separate `isAdmin` capability since T-066/T-081); one stale "not yet built" deferral removed (Provenance artifact download); test census updated (362→363, 41→42 `test_api`); one new risk (RISK-035) + one ADR realized-addendum (no decision altered) recorded. |

## Discussion

### Commits swept (newest → oldest)

1. `07f53af` — Pipeline builder: Fit-to-DAG, trackpad zoom, bigger minimap (T-084).
2. `d8c1625` — Pipeline builder: fix the broken connector lines + the tool I/O (T-083).
3. `a9b06ad` — QC readout: name ungated rows + emit real breadth on the GIAB run (T-082 follow-up).
4. `a8fc73b` — Core: enrich contrived QC to a full three-gate readout (T-082).
5. `0f7e85f` — Frontend: gate the app behind a demo login + a real admin role (T-081).
6. `eb7d016` — Frontend: label the digest "hash" + keep the monitoring chart from distorting (T-080).
7. `f696bc7` — Telemetry: add the auto-provisioned Grafana dashboard (T-079).
8. `e3e1995` — Frontend: paginate/group the review queue, fix runs-card layout, monitoring date + Y-axis, triage table (T-078).
9. `71a06d6` — Provenance: wire artifact download + full digest + give QC a real input (T-077).

For each, read the full `git show <sha>` diff (not just the message) before writing anything.
All nine diffs matched their commit-message descriptions; no behavioral drift between message
and code. Task IDs T-077..T-084 were **free** (no collision) — the commit authors self-assigned
non-colliding ids this time, unlike the previous batch (`2026-07-09-frontend-batch3.md`).

### Grounding method (per claim)

- **QC enrichment (T-082/a9b06ad).** Read `src/bayleaf/models.py`, `parsers.py`,
  `metrics/mapping.py` (the 8-entry `_QCMETRICS_MAP` addition), `runbook.py` (the `required`
  field + 5 new `QCThreshold`s with concrete `gate`/`hard_fail` values), `rules.py`
  (`_evaluate_metric`'s `if not threshold.required: return None` guard), and
  `api/card_readout.py` (`_display_name`, already landed and using
  `default_registry().entry(our_key).display_name`, confirming the follow-up commit's claim).
  Cross-checked the "10 gated / 10 ungated" claim against `src/bayleaf/metrics/metric_registry.yaml`
  (counted 20 `our_key` entries) and `runbook.py`'s `qc_thresholds` list (counted 10 `QCThreshold`s)
  — exact match. Cross-checked which of the 10 "ungated" entries actually have a producer: only
  `preflight.phix_aligned` / `variant.gq` / `variant.titv` appear in `_QCMETRICS_MAP`; the other 7
  (`qc.zero_cov_targets`, `qc.fold_enrichment`, `qc.fold_80`, `identity.ngscheckmate_match`,
  `identity.sex_concordance`, `contamination.freemix`, `variant.allele_balance`) do not — an
  honest, **pre-existing** gap, not introduced by T-082, and I was careful not to imply otherwise
  in `qc_metrics.md`/`metric_registry.md`.
- **Provenance download + stage mapping (T-077).** Read `api/main.py`'s diff directly: the new
  `GET /api/runs/{id}/artifacts/{name}` route, the `RunArtifact.url` field, and the
  `_ARTIFACT_STAGE` dict changing from one `(stage, role)` tuple per kind to a `list[...]`.
  Confirmed `RunArtifact` (the `url`-carrying model) lives in `api/main.py`, **not**
  `src/bayleaf/models.py` — so the 🔴 "models.py/parsers.py/persistence — new field" map row
  does **not** fire (that's `RunArtifacts`, the core intake bundle, a different type); the correct
  row is the 🟠 "api/ endpoint... new/changed capability" one, routing to architecture.md +
  functional.md, which I updated. `QCMetrics` (which DID gain 8 core-model fields, T-082) is a
  genuine `src/bayleaf/models.py` hit, so `schemas.md` got the 🔴 treatment there instead.
- **Builder tool-I/O + connectors (T-083/T-084).** Read the `BuilderShared.tsx`/`BuilderCanvas.tsx`
  diffs directly — confirmed the exact I/O deltas (bcftools call/norm's `panel_bed`, markdup's
  `bai` vs the phantom `samtools_stats`, mosdepth's `mosdepth_thresholds`) and the minimap
  dimension change (168×46 → 210×108) and the `ZMIN`/`ZMAX` 0.6/1.4 clamp against the raw diff
  hunks, not just the commit prose.
- **Test census.** `uv run pytest --collect-only -q` → **363** collected (was 362 at the last
  sweep); `git diff --stat fa3b6c3..HEAD -- tests/` shows only `tests/test_api.py` touched
  (+36/-8); `git diff fa3b6c3..HEAD -- tests/test_api.py | grep '^+def test_'` shows exactly one
  new test, `test_artifact_download_serves_file_and_blocks_traversal`. `uv run pytest -q` →
  **360 passed, 3 skipped** (the Postgres-live suite, unchanged). Updated `evaluation.md`'s
  headline count and the `test_api` per-file number (41→42); no other per-file counts changed
  (no other new test files, no other file's test count moved).
- **Admin gating drift.** While updating the login-gate framing I noticed `architecture.md`
  ("approver-gated governance"), `functional.md` REQ-F-066 ("visible only when the acting
  `RoleContext` is `approver`"), and the (until this session, entirely absent) frontend
  `design/frontend/README.md` all still described Admin's original T-066 gating rule — but
  `0f7e85f` (T-081) changed the actual gate to a separate `isAdmin` boolean
  (`frontend/src/context/RoleContext.tsx`: `isAdmin = session != null && isAdminId(session.id)`,
  read from `frontend/src/auth.ts`'s `ADMIN_IDS`), which is **not** the same predicate as "acting
  role === approver" (an `m.chen`/approver session has `isAdmin === false`; only `s.ops` does).
  Verified directly in `RoleContext.tsx` and `auth.ts` (both quoted above). Fixed all three
  places, citing the correction inline rather than silently rewriting history.
- **A second, smaller drift**: REQ-F-066 said "*(No `tasks.md` row yet at time of writing —
  flagged for the planning sweep.)*" — but `tasks.md` already has a T-066 row (added in an
  earlier session, done). Fixed the citation to point at the real row while I was in that
  paragraph anyway.
- **Grafana dashboard.** Read `git show f696bc7` in full (small, five-file diff) — confirmed no
  new Prometheus series (`_render_prometheus` in `api/main.py` untouched, not part of this
  commit's diff) and no new dependency; the dashboard purely visualizes the four series
  `ops/telemetry-connectors.md` already documents. Updated that doc with one factual paragraph
  and `tasks.md`; deliberately did **not** add a `deploy/telemetry/` mention to `CLAUDE.md`'s code
  map (that map has never tracked `deploy/`, and T-036's original telemetry-bundle addition
  didn't get a CLAUDE.md line either — staying consistent with that established boundary rather
  than expanding the code map's scope unilaterally).

### Doc-update map sweep (row by row)

- 🔴 journal → this file.
- 🔴 task-status changes → `tasks.md` T-077..T-084 added, `Last updated` bumped.
- 🔴 `models.py`/`parsers.py` field change (`QCMetrics` +8 fields, T-082) → `schemas.md` (the
  `QCMetrics` note in the `RunArtifacts` intake-bundle blockquote) — done. `RunArtifact.url`
  (api-layer, not core) does **not** fire this row (see grounding above).
- 🔴 test census → `evaluation.md` — done (363/22/360-pass/3-skip, `test_api` 41→42).
- 🟠 `runbook.py`/`rules.py` threshold/gate-assignment change (T-082's 5 new optional
  `QCThreshold`s + the `required` field) → `qc_metrics.md` — done (new "Implementation status"
  section, the Gate 2/3 rows annotated). *Verdict policy itself is unchanged* (ADR-0013 not
  touched — ADR unaltered, correctly).
- 🟠 `metrics/` registry/mapping change → `metric_registry.md` — done (new "Wiring status"
  section with the verified 10/10/7-unwired breakdown).
- 🟠 `provenance.py`/`engine.py`/EventType/JSONL-ledger change → **waived.** None of the nine
  commits touch `provenance.py`, `engine.py`, or the `EventType` enum — `_ARTIFACT_STAGE` and the
  new download route are purely `api/main.py` (a read/serve projection over already-written
  files), not the ledger. `provenance.md` is unchanged.
- 🟠 new advisory agent / model tier / corpus → **waived.** None of the nine commits touch
  `synthesis/`, `triage/`, `pipeline_repair/`, `feedback_agent.py`, or `archivist.py`.
  `design/agents.md` is unchanged.
- 🟠 `api/` endpoint or `frontend/` screen — new/changed capability → `architecture.md` +
  `requirements/functional.md` (new REQ-F-069/070/071 + REQ-F-064/066 corrections) — done.
  `design/data-platform-and-archivist.md` — **waived**: that doc's artifact-disposition catalog
  (GATE-READ/FLATTEN-INPUT/INDEX-ONLY) and its `MANIFEST.sha256` design-spec content are about
  which files the *gate* reads, not the Provenance screen's UI-facing download/hash-label
  feature it never documented in the first place (grepped for `GET /api/runs/{id}/artifacts`,
  `_ARTIFACT_STAGE`, `demux_stats` — the one hit is an unrelated GATE-READ classification row).
  `/metrics` series count unchanged (Grafana just visualizes the existing four) → no re-verify
  needed there, but I added one factual paragraph to `ops/telemetry-connectors.md` anyway since
  it's the doc that owns the docker-compose demo-sizzle description that was (mildly) stale
  ("Grafana booted connected but empty" was implied, now corrected).
- ⚪ load-bearing decision → **no new decision this session** (T-081's login gate was an
  already-made maintainer call per the commit message, "maintainer chose the demo gate"; I added
  an ADR-0017 **realized addendum**, not a new decision, per the ADR being about identity/RBAC
  and this being additive framing over it — no Decision/Status field altered).
- ⚪ scope/wishlist/"built" change → **waived.** Grepped `scope-and-wishlist.md` for
  `login`/`download`/`Grafana`/`dashboard`: no matching wishlist row exists for any of these
  (they are incremental fixes/enrichments of already-in-scope, already-built features — the
  artifact-download UI was always implicit in the already-built T-037 Provenance canvas, not a
  distinct wishlist line item; Grafana closes wishlist #17's "sizzle" piece, already tracked via
  T-036/T-079 in `tasks.md`, not a distinct wishlist row). `scope-and-wishlist.md` unchanged.
- ⚪ file moved / module added / a map trigger rotted → **waived**, no file moves this batch.
- ⚪ demo-flow/exact-commands/port change → **waived**, no command or port changed.
- ⚪ new tool/dependency → **waived**, confirmed via each commit's own "no new dependency" claim
  and no `pyproject.toml`/`uv.lock` diff in `git diff --stat fa3b6c3..HEAD`.

### Left deliberately untouched (flagged for the maintainer, not fixed)

- **`docs/design/frontend/pipeline-builder-brief.md`** still shows the *original* (buggy) tool
  I/O in its example tables (e.g. `n_markdup` outputs `bam`/`markdup_metrics`/`samtools_stats`;
  `n_norm` carries `panel_bed`) — the same shape T-083 fixed in the live app. This is the
  maintainer's stable design brief (per the ToC: "the stable spec"), analogous to the excluded
  `briefs/`/`handoffs/`/`source/`/`bayleaf.html` deliverables, and prior sessions never edited
  it when correcting implementation drift (they annotate `design/frontend/README.md` with
  "Shipped" notes instead, which is what this session did too). Not edited; noted here so the
  maintainer can decide whether the brief itself should be corrected or left as historical
  design intent.
- **A traversal-hardening pattern is now used by at least two endpoints** (the T-054 pipeline
  dry-run locator resolver and the new T-077 artifact download) with no general NFR entry
  capturing "path-traversal-hardened file-serving endpoints validate the resolved path stays
  inside an allowed root." `requirements/nonfunctional.md` has no such REQ-NF item. Not added —
  the Doc-update map doesn't clearly route this batch's change there (it's a repeated
  *implementation pattern*, not a new requirement per se), but flagging it as a candidate
  REQ-NF for a future security-focused pass.
- **Uncommitted local changes** already present at session start (`docs/design/frontend/
  bayleaf.html`, `README.md`, `source/bayleaf.dc.html`, `source/support.js`, plus untracked
  root `bayleaf.html`/`briefs/`/`handoffs/`/`source/`) were left completely alone — none of the
  nine commits swept this session touch those paths, and they read as the maintainer's own
  in-progress design-package work, explicitly out of scope per the operating contract.

## Decisions

| Decision | Distilled to |
|---|---|
| Admin's gating is `isAdmin` (a frontend-only governance capability), not "any approver" — correct this in every doc that described the old framing, citing the correction inline rather than silently rewriting | [architecture.md](../design/architecture.md), [functional.md](../requirements/functional.md) REQ-F-066, [design/frontend/README.md](../design/frontend/README.md) §11 |
| The now-built artifact-download endpoint closes a previously-recorded "no download URL" deferral — remove the stale deferral rather than let a built feature stay marked not-built | [CLAUDE.md](../../CLAUDE.md), [architecture.md](../design/architecture.md) |
| The demo login gate (T-081) is real enough to warrant its own risk entry (client-side-only, spoofable) rather than being silently subsumed into the existing ADR-0017 dev-shim risk framing | [risks.md](../quality/risks.md) RISK-035 |
| The login gate is additive framing over ADR-0017, not a new decision — record it as a dated realized-addendum, not a new ADR or an edit to the existing Decision/Status | [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) §Realized addendum |
| `pipeline-builder-brief.md`'s stale example tool-I/O is left untouched (maintainer's stable design spec, same category as the excluded briefs/handoffs/source) rather than silently corrected | this journal §"Left deliberately untouched" |

## Open questions & TODO

- Should `pipeline-builder-brief.md`'s example tool-I/O tables be corrected to match the
  now-fixed live Builder, or intentionally left as the original design intent? (See "Left
  deliberately untouched" above.)
- A candidate `REQ-NF` for "traversal-hardened file-serving validates the resolved path stays
  inside its allowed root" — currently an implementation pattern repeated across two endpoints
  (T-054 dry-run, T-077 download) with no requirements-level capture.
- T-069/T-070/T-071 (Builder dry-run/diff wiring, run-selector, decision-card contamination gap)
  are unaffected by this batch and remain open as before — not re-verified line-by-line this
  session (last verified in `2026-07-09-frontend-batch3.md`).

## Distilled into

- [planning/tasks.md](../planning/tasks.md) — T-077 through T-084 added; `Last updated` bumped.
- [CLAUDE.md](../../CLAUDE.md) — Current code map: QC-enrichment optional thresholds, artifact
  download (closing the old deferral), the demo login gate + corrected `isAdmin` framing, the
  Pipeline Builder connector/tool-I/O + canvas-navigation fixes.
- [data/schemas.md](../data/schemas.md) — `QCMetrics`'s 8 additional registered fields.
- [data/metric_registry.md](../data/metric_registry.md) — new "Wiring status (T-082)" section.
- [data/qc_metrics.md](../data/qc_metrics.md) — new "Implementation status (T-082)" section.
- [design/architecture.md](../design/architecture.md) — provenance download/hash-label/QC-input
  paragraph, QC-readout three-gate-enrichment paragraph, a new "Frontend fixes batch 4"
  paragraph, the Admin `isAdmin` correction, the stale deferral removed.
- [requirements/functional.md](../requirements/functional.md) — REQ-F-069/070/071 added;
  REQ-F-064/066 corrected.
- [quality/risks.md](../quality/risks.md) — new RISK-035.
- [quality/evaluation.md](../quality/evaluation.md) — test census (363/22/360-pass/3-skip,
  `test_api` 42).
- [ops/telemetry-connectors.md](../ops/telemetry-connectors.md) — the provisioned Grafana
  dashboard, factually described.
- [design/frontend/README.md](../design/frontend/README.md) — §4 login gate, §5.4/5.5/5.6/5.7/5.8
  "Shipped" notes, §6 Builder connector/tool-I/O/canvas notes, new §11 Admin (previously entirely
  undocumented in this file).
- [adr/ADR-0017-identity-rbac-authoring-lifecycle.md](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)
  — a realized addendum (no Decision/Status altered).
