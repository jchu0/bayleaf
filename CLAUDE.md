# CLAUDE.md — PipeGuard

AI-assisted provenance & QC decision gate for genomics runs (Built with Claude:
Life Sciences hackathon). This file is the self-contained operating contract for
this repo — do not assume any global rules apply here.

## Start here (every session)

1. **Two top-layer inputs — read both at session start:**
   a. [docs/TABLE_OF_CONTENTS.md](docs/TABLE_OF_CONTENTS.md) — the map of what exists,
      and (its **Doc-update map**) the authority on which docs a given change obligates.
   b. [docs/planning/tasks.md](docs/planning/tasks.md) — development state, timeline,
      and which work is parallel-safe (fan out subagents for non-blocking tasks).
2. **Read lean, write complete.** Load **only** the files relevant to the task for
   context — *unless it genuinely needs broad context*, then bulk-load deliberately.
   Reading and owing are separate: before you finish, sweep the
   [Doc-update map](docs/TABLE_OF_CONTENTS.md#doc-update-map) and update every doc your
   change made stale — a doc you never opened can still be one you now owe. **Not
   loading a doc is fine; leaving one your change made stale is not.** Every working
   session also owes a `docs/journal/YYYY-MM-DD-<topic>.md` entry, whatever it touched.
3. Follow [docs/DOCUMENTATION_HABITS.md](docs/DOCUMENTATION_HABITS.md) for anything
   documentation-related.
4. The `why` behind the architecture lives in the ADRs at [docs/adr/](docs/adr/).

## Commands

```bash
# Setup (uv is the single dependency source: pyproject.toml + uv.lock)
uv sync --all-extras                        # .venv + deps + dev tools, editable install
uv run pre-commit install --install-hooks   # ruff/mypy/secret-scan (commit) + pytest (push)

# Run the dashboard (offline; no API key needed)
uv run streamlit run app/streamlit_app.py   # http://localhost:8501

# Tests (offline — pins the demo scenario)
uv run pytest                               # editable install; no PYTHONPATH shim

# Lint + strict type-check
uv run ruff check && uv run mypy

# Ad-hoc run of the core (no UI)
uv run python -c "from pipeguard import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
```

## Working agreement

**Workflow**
1. Before non-trivial changes, inspect the relevant files and propose a short plan.
2. No broad refactors unless explicitly asked. Prefer small, reviewable diffs.
3. If requirements are ambiguous, make a reasonable assumption, state it, continue.
4. **Parallelize by default.** Batch independent work into as many concurrent processes as
   safely possible: issue independent tool calls in one message, and fan out subagents/
   workflows for non-blocking tasks (audits, per-file/-screen sweeps, research, multi-angle
   design, verification). Scout inline to discover the work-list, then fan out over it.
   Caveats: keep tightly-coupled edits to the *same* file single-author (parallel writers
   collide); serialize steps with a real data dependency; use read-only agents (Explore) for
   audits/reviews. When unsure whether two tasks are independent, they usually are — split them.

**Architecture guardrails**
1. `src/pipeguard/` stays framework-agnostic — no Streamlit/FastAPI imports in the core.
2. Reuse existing utilities, models, and patterns before adding new ones; no duplicate abstractions.
3. Don't move files across `src/`, `app/`, `data/`, `docs/`, `tests/` without explaining why.

**Dependencies**
1. Don't add a dependency unless the stdlib or an existing dep can't do it; justify additions.
2. `pyproject.toml` is the single source of truth (uv). Pin for a reproducible demo.

**Security**
1. Never hardcode keys, tokens, credentials, private URLs, or personal data — use env vars.
2. Update `.env.example` when adding a required env variable.
3. Never print secrets in logs, test output, or errors.

**Life-science / biomedical guardrails**
1. Research/demo tool with production intent — **not** a clinical decision system.
   Make no diagnostic, therapeutic, or safety claims.
2. Confidence values are heuristics, not calibrated probabilities — label them as such.
3. Runbook thresholds are illustrative/configurable, not clinical thresholds.
4. Keep evidence, assumptions, and generated suggestions separate; preserve citations,
   provenance, and confidence. Prefer conservative language; flag uncertainty.
5. Clinical variant claims stay grounded in ClinVar/GIAB truth; never invent pathogenicity.

**Data handling**
1. Never commit raw reads, PHI, credentials, or large artifacts. Commit accessions +
   a fetch script instead. Tag every artifact's origin (`real-giab` / `synthetic` / `contrived`).
2. Parse artifacts tolerantly at boundaries — a missing field is a signal, not a crash.

**Testing & verification**
1. Changes to parsers or rules must keep the offline test suite green and the demo intact.
2. Verification is batch-default (heavy checks on batch pushes); ask when a single change warrants one.

**Delivery posture**
1. MVP-first with production-ready seams. Optimize for a working, understandable core
   flow — but run major tradeoff decisions by the maintainer first. Prefer boring, robust choices.
2. **Do not foreground time/deadline pressure until Fri Jul 10 (MST).** Budget is ample
   (weekly + 5-hour caps well under limit); build steadily, pursue the maintainer's wishlist
   features, and drop deadline hedging. Reassess scope at the **Fri Jul 10** checkpoint
   (Sun Jul 12 is a flex day). This governs framing only — the *guardrails above still hold*.

**Communication**
1. Summarize what changed, list files modified, state how it was verified, and note
   remaining risks/TODOs/assumptions. Be concise. Reference files as clickable paths.
2. Use **numbered or lettered lists**, not plain bullets, for anything referenceable —
   in docs, commit bodies, and chat responses — so items get short stable IDs
   (e.g. "Security 2") for feedback without quoting long text.

## Coding standards

1. **Type hints across the board**, enforced by mypy.
2. **Meaningful docstrings** on public functions and classes.
3. **Comments explain *why*** a method or approach was chosen, not what the line does.
4. **Configuration via env / typed settings** (pydantic-settings); never hardcode config.
   Two toolchains kept separate: `uv` for the app, bioconda/containers for genomics tools.

## Documentation rules

1. Before creating a doc, check [docs/_templates/](docs/_templates/) and follow the
   matching template. If none fits, **create the template first**, then the doc.
2. Update every doc your change obligates, in the **same change**; the [Doc-update map](docs/TABLE_OF_CONTENTS.md#doc-update-map) is the routing authority (touch X → owe doc Y), not the set of files you opened.
3. Date entries ISO-8601 with **MST**. Keep a session journal and distill it into
   canonical docs at session end (journal is the archive, not the source of truth).
4. **Crosslink related sources** — fill each doc's Related field and link inline
   references (docs, ADRs, code) so navigation is one click.
5. Before declaring a **substantive** session/PR done, run the **Session-end doc checklist**
   ([DOCUMENTATION_HABITS.md](docs/DOCUMENTATION_HABITS.md#session-end-doc-checklist))
   and include its CHK-1/CHK-2/CHK-3 results in the wrap-up summary.

## Design invariants (details in docs/design/)

1. **Rules decide; AI narrates/advises** — never let a synthesizer or agent set or
   override a verdict or confidence (ADR-0001).
2. **Agents are advisory and OFF the deterministic critical path** (ADR-0001).
3. **AI is OFF by default** with a deterministic fallback (ADR-0006).
4. **Event-driven core**; every I/O is recorded in the provenance ledger (ADR-0002).
5. **Deployment-agnostic ports & adapters**; Nextflow carries compute portability (ADR-0003).
6. **Config layer + profiles** serve research (lean) and biotech (granular) from one codebase (ADR-0005).

## Current code map (evolving; updated 2026-07-10)

1. **Core (`src/pipeguard/`), framework-agnostic.** `rules` emits cited, immutable
   `Finding`s (each derives its gate + a rule-version-independent signature +
   content_hash); `synthesis/base.py` aggregates the verdict (never the LLM);
   confidence is omitted until grounded (T-019). `models` is the pydantic data
   contract; `identifiers` gives UUIDv7 ids + content hashing; `runbook` holds QC policy
   — `QCThreshold` now carries `required` (default `True`; T-082) so a richer QC report
   (13 metrics: the frozen five + 8 more registered preflight/qc/variant metrics) can gate
   5 additional **optional** thresholds (score a present value, never NA-flag an absent
   one) without penalizing a lean real run; the metric catalog is 10 gated / 10 ungated
   of 20 registered `our_key`s (`data/metric_registry.md`).
2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only
   event trail (analysis_run.started → per-sample findings/verdict → completed) into an
   `EventLedger` (in-memory + JSONL); the event log is authoritative, the DB a
   rebuildable projection via `persistence/` selected by `get_repository()`
   (`PIPEGUARD_REPOSITORY=sqlite|postgres`, default SQLite, degrade-to-SQLite) — SqliteRepository
   *and* PostgresRepository (guarded, off-by-default, ADR-0016); `rebuild-db` targets either (ADR-0003).
3. **Swappable AI, OFF by default.** Synthesizer via `PIPEGUARD_SYNTHESIZER=stub|claude`;
   advisory QC-triage agent (`triage/`, ADR-0009/0012) via `PIPEGUARD_TRIAGE_AGENT=stub|claude`;
   advisory pipeline-repair agent (`src/pipeguard/pipeline_repair/`, ADR-0009/0012) via
   `PIPEGUARD_PIPELINE_REPAIR_AGENT=stub|claude` (recurring signature → cited `RepairProposal`,
   Opus-high default); advisory feedback-categorization agent (`api/feedback_agent.py`, off-gate)
   via `PIPEGUARD_FEEDBACK_AGENT=stub|claude`; advisory archivist (`api/archivist.py`, off-gate)
   via `PIPEGUARD_ARCHIVIST_AGENT=stub|claude` (released runs → organizational `ArchiveDigest`,
   Haiku default) — all five stub-first ($0), import `anthropic` lazily, and fall back to the stub
   on any error (incl. a safety refusal). Models via `PIPEGUARD_*_MODEL`.
4. **Delivery layers (thin, over the core).** `app/` = Streamlit demo (kept as the
   guaranteed-working fallback); `api/` = FastAPI read-API + **off-gate writes**
   (`POST /api/feedback` → `FeedbackStore`; `POST /api/pipelines`, now **auth-gated**
   via `require_role` capturing `submitted_by`, → a pluggable `PipelineGraphStore` — a
   tolerant versioned envelope reserving a draft→approve+RBAC lifecycle, T-049; both
   jsonl/sqlite/postgres) + the artifacts + **windowed-monitoring** endpoints
   (`GET /api/runs/{id}/artifacts`, `GET /api/monitoring`) + a traversal-hardened artifact
   **download** (`GET /api/runs/{id}/artifacts/{name}` → `FileResponse`; `RunArtifact.url` now
   populated, T-077 — the old "no download URL" deferral is closed) + **advisory agent reads** (off-gate,
   read-only: `GET /api/monitoring/signatures/{signature}/repair`, `GET /api/runs/{id}/archive-digest`,
   `GET /api/archive/index`) + runs pagination/search with
   **Tier-0 params** (status filter, platform-aware `q`, sort aliases, facet-count header) +
   honest `RunSummary` status/platform/date (from the SampleSheet `[Header]`) + an **intake
   execution boundary** (`api/routers/intake.py`, T-057): `POST /api/runs` registers a submitted
   samplesheet and triggers `scripts/run_giab_pipeline.py` as a background subprocess
   (in-process job registry; HG002-fixture-scoped, honest-skips the rest; 409 on a dup run id),
   `GET /api/runs/{id}/intake-status` polls `queued|running|complete|failed` — `src/pipeguard/`
   still never runs a tool (compose ≠ execute holds at the core), but the API layer now DOES
   trigger an external driver, closing the old "Submit never runs anything" gap. `GET
   /api/runbook`'s `RunbookThreshold` now also carries `pipeline_gate` (the registry gate)
   distinct from the numeric `gate` value, powering the decision card's honest three-gate
   (preflight/qc/variant) readout with an empty-state note where a gate has no metric table —
   the production seam (ADR-0010/0016). Authz lives in the dev-shim `api/auth.py` (Role viewer|reviewer|approver
   + `Actor` + `current_actor()` from `X-PipeGuard-Actor/-Role` headers, permissive dev-default,
   `require_role`) — the shared authz source for the draft→approve flows and the single swap point
   for real auth; feature-area routers under `api/routers/` (`settings.py` config-override authoring
   T-051, `review_queue.py` ticket domain, `pipelines_lifecycle.py` submit/approve/dry-run/diff)
   fold into `main.py`, backed by two more pluggable stores `api/settings_store.py` +
   `api/review_store.py` (`PIPEGUARD_SETTINGS_STORE`/`PIPEGUARD_REVIEW_STORE`, jsonl/sqlite/postgres,
   degrade-to-jsonl) joining feedback + pipeline stores; `api/card_readout.py` is an API-layer
   QC-readout projection (card `metric_values` ⋈ runbook `QCThreshold` →
   Metric·Observed·Threshold·Status), core card/gate untouched. `frontend/` = React + Vite +
   Tailwind consuming the API — **rebuilt to the refreshed design prototype** (2026-07-09,
   `docs/design/frontend/`, T-062), then extended the same day by a maintainer feedback batch
   (commits `e891e62`→`6371128`, [journal](docs/journal/2026-07-09-frontend-batch2.md)): 10
   operator screens in a three-group nav — Operate (submit samplesheet → runs → intake gate →
   decision cards → review queue), Analyze (provenance → agent triage → monitoring), Configure
   (pipeline builder → settings) — plus an **Admin** group (`/admin`, off the
   deterministic gate: Users & roles client-mock roster + "Act as" wired to the now-full
   `RoleContext.setActor(actor)` [id+role together, not just a role toggle]; Activity log — a
   real audit feed merging thresholds/pipelines/tickets; System — real reads of `GET
   /api/health` + runbook + metric-registry; never a verdict/confidence). **The whole app now
   sits behind a demo login screen** (`frontend/src/auth.ts` + `screens/Login.tsx`, T-081): four
   demo accounts (viewer/reviewer/approver/admin, shared password, every production auth seam
   labelled inline as NOT implemented — OAuth/OIDC, server-side password hashing, httpOnly
   session cookie, real CAPTCHA); `App.tsx`'s `RequireAuth` guard redirects an unauthenticated
   visit to `/login`. Admin gating is now **`isAdmin`** (a frontend-only governance capability
   layered over the wire roles, distinct from "any approver" — an admin is an approver who also
   holds governance), not the earlier any-approver framing. A shared
   `RUN_STATUS_META` (`verdict.ts`) now drives every run-status dot; the top-bar run switcher
   was rebuilt into a searchable, 8-row-capped combobox (search by id/platform, "view all"
   footer) whose dot reads the run's real `status`, not `n_attention` (fixed F17). The Pipeline
   Builder adds free composition, a typed-port Connect mode, and editable
   Locators — "New → From template" now seeds an **editable** germline-chain draft
   (`germlineTemplate()`) rather than the old read-only seeded DAG (only the original linked
   pipeline still renders read-only). Its seeded connector lines are now **computed** from the
   tool/reference card geometry + typed ports (`BuilderCanvas` `SEEDED_WIRES`/`REF_WIRES`, T-083;
   the old hardcoded SVG-path `EDGES` table — which detached from a port whenever a card's port
   count changed — is gone), with the tool I/O corrected to match the real pipeline (bcftools
   call gains `panel_bed`, norm loses it; markdup outputs `bam`·`bai`·`markdup_metrics`, not a
   phantom `samtools_stats`; mosdepth gains `mosdepth_thresholds`); **Fit** now centers/zooms to
   the pipeline (not just a zoom reset), ctrl-wheel/trackpad-pinch zooms the canvas natively, and
   the minimap grew to a 210×108 proportional mirror (T-084). Its Save now chains `savePipeline`→`submitPipeline` and Approve calls
   `approvePipeline` — both **await + reconcile local state from the response** (no longer
   fire-and-forget); Dry-run/Diff now call the REAL endpoints once the graph is Saved (T-096,
   see Batch 6 below), closing the earlier "`dryRunPipeline`/`pipelineDiff` exist but aren't
   called yet" limitation. A
   new `Toast` system (`components/Toast.tsx`) surfaces every off-gate write's real backend
   outcome (403/409/422/503/…) instead of silently diverging; the fix also slugified the
   Settings threshold-override name (spaces/colon 422'd the backend's slug pattern) and
   relaxed review-queue resolve/suppress RBAC from approver-only to reviewer+approver
   (`api/routers/review_queue.py`, matching the design). `GET /api/monitoring`'s
   `MonitoringSignature` additively carries `first_seen`/`last_seen`/`trend`/
   `affected_run_ids`; the Median-review KPI stays a documented, not-yet-built seam. Provenance
   now serves a real artifact **download** + a "show full" 64-char digest toggle (labelled
   "hash," not "sha256," in the UI — defense-in-depth; the wire field is unchanged, T-077/T-080)
   and the QC node reads as fed (`_ARTIFACT_STAGE` maps demux output → QC input too, T-077).
   **Batch 5 (2026-07-10, commits `14c9f3c`→`5774143`, T-085–T-092), all re-presentation/UX —
   no verdict, gate, or ADR-0001 boundary changed.** Builder Tidy is now a flow-preserving
   auto-layout (longest-path column per node over `userEdges`, upstream→downstream reads
   left→right, was one row); a Cancel button (draft-only) discards an in-progress build back to
   the linked pipeline in View; the minimap moved bottom-right→top-right. The palette gained a
   **References** section (Reference FASTA / Panel BED / Truth VCF — no-input source nodes
   emitting their ref artifact, typed-wired so a fasta can't land on a fastq port) and
   collapsible sections with per-section counts (search overrides collapse). `api/card_readout.py`'s
   `GateReadout` gains `blocked_by` — the maintainer's two-tier gate-dependency model
   (sequencing-tier QC gates sample processing, sample-tier QC gates downstream analysis): a gate
   with any non-proceed **upstream** gate now reads "blocked · clear \<upstream\> first" instead
   of "all clear" (pure re-presentation over already-computed `gate_results`; the frontend mirrors
   it for synthesized placeholder gates; part 2, user-clearable HOLD/ESCALATE, is next). The
   decision card's top-strip "Passed" chip is now green (proceed tokens, was neutral grey; "Not
   run" stays grey), and the redundant 3px verdict-colored left spine is dropped (verdict is
   already carried by the badges; the colored rail is reserved for Pipeline-Builder tool cards).
   `GET /api/runs/{id}/artifacts/{name}` now serves **inline by default** (click-to-view) and
   attaches only on `?download=1` — the artifact name views, the Download button downloads;
   Provenance also gained a hover explainer distinguishing `sample_metadata.csv` (intake) from
   `SampleSheet.csv` (demux). A new `frontend/src/context/PrefsContext.tsx` makes the Settings
   dialog's theme (light/dark/system) and density (split/brief/dense) controls real and
   `localStorage`-persisted — a full dark theme now lives in `index.css`
   (`:root[data-theme="dark"]` overriding the `@theme --color-*` vars, so every existing Tailwind
   utility retargets); one density setting now backs both the dialog and `RunDetail`'s own Layout
   control. Admin role edits now **stage into a draft** (a dropdown, not the old 3-way toggle that
   reassigned on every click) behind an explicit Save/Discard bar, and Act-as confirms before
   impersonating (still the client-mock roster; `api/auth.py` unchanged). 364 tests (was 363).
   **Batch 6 (2026-07-10, commits `8a14661`→`4208f0b`, T-093–T-096), also re-presentation/UX —
   no verdict/gate/ADR-0001 boundary changed.** Admin's Activity log now paginates (25/50/100 +
   pager, "Showing X–Y of Z," resets on filter change) and each row expands on click to a
   labelled Detail/Target/Actor/When panel (T-093, no backend change). Admin's System tab gained
   an Artifact-store stat card (`PIPEGUARD_ARTIFACT_STORE` s3 seam) and an Observability section
   linking the read-API's `/metrics` exporter, Prometheus (`:9090`), and the Grafana "PipeGuard —
   QC decision gate" dashboard (`:3000`, T-036/T-079) as off-demo-path links, plus a per-user
   password/email-reset action — a labelled production seam, no live mail, that toasts what
   would happen (T-094). Settings' runbook-threshold table replaced its two side-by-side
   Whole-blood/Saliva columns with a Sample-type dropdown showing one tissue's value column at a
   time (T-095); editing/save/approve and the audit lifecycle are unchanged. **The Builder's
   Dry-run/Diff console tabs now call the REAL endpoints once the graph is Saved** —
   `POST /api/pipelines/{name}/dry-run?run_id=…` (real per-locator matched/ambiguous/missing/
   invalid resolution, via a plain run-id text input, not yet a searchable picker — T-070 stays
   open) and `GET /api/pipelines/{name}/diff` (added/changed/removed vs the approved baseline) —
   falling back to the client-side preview before Save (T-096); compose ≠ execute holds (a
   dry-run globs paths, runs nothing). **T-069 narrows** to the remaining Run-hand-off /
   pipeline-repair / archivist Builder modals (`RunHandoffModal`/`PipelineRepairModal`/
   `ArchivistModal`, still static `phase-2` previews; `api.archiveDigest`/`api.archiveIndex`
   still uncalled) and saved-profiles.
   **Batch 7 (2026-07-10, commits `34bca5d`→`adfd7aa`, T-069/T-070/T-072), closes the last of
   the Builder deferrals — also re-presentation/wiring-only, no verdict/gate/ADR-0001 boundary
   changed.** Monitoring's per-run throughput columns (`data.runs`) now paginate client-side too
   (25/50/100 + pager, independent state from the signatures pager) — **closes T-072's frontend
   half; the backend `GET /api/monitoring` `runs[]` payload stays uncapped server-side, so T-072
   itself stays open** (commit `34bca5d`). A new reusable `RunSelector`
   (`frontend/src/components/RunSelector.tsx`) — a searchable, 8-row-capped combobox sharing the
   top-bar switcher idiom (real `RUN_STATUS_META` status dot, F17, never `n_attention`) —
   replaces the Dry-run tab's plain run-id text box in `BuilderConsole.tsx`; self-fetches
   `api.runs()` lazily, honest "Couldn't load runs" on failure (**closes T-070**, commit
   `3c6455e`). The three remaining static Builder-modal previews are now wired to real data
   (**closes T-069**, commit `adfd7aa`): `PipelineRepairModal` → `GET /api/monitoring` (a
   signature picker) + `GET /api/monitoring/signatures/{sig}/repair` → the real `RepairProposal`
   (summary/rationale/attachTo/scope, cited corpus refs with a **"heuristic" score label, never
   "confidence"**; "Send to review queue" navigates to `/queue`, no fabricated ticket);
   `ArchivistModal` → `GET /api/archive/index` → the real cross-run `ArchiveDigest`
   (archive-ready counts, origins verbatim, proposed action, disclaimer; "Queue archive" stays
   inert, no write endpoint); `RunHandoffModal` now shows the real composed `run_layout.yaml`
   (copy-not-execute, no network call). **Saved-profiles** ships too: a new toolbar "Open" action
   lists `GET /api/pipelines` and hydrates the canvas from a chosen saved graph (approved graphs
   open read-only; re-saving mints a new draft; a foreign envelope with no restorable topology
   loads empty with a labelled toast, never fabricated nodes). Frontend-only for all three
   commits (`git diff --stat a728cb7..adfd7aa -- src/ api/ tests/` empty).
   **Batch 8 (2026-07-10, commits `5763be1`→`f8a6f35`, T-098–T-100), a maintainer UI-feedback
   pass — all frontend-only, no verdict/gate/ADR-0001 boundary changed** (`git diff --stat
   1169e37 f8a6f35 -- src/ api/ tests/` empty). **Theme** (T-098): light mode is now a warm
   japandi sand/greige palette (`index.css` `@theme` neutrals — page/card/insets/lines/text all
   warmed, contrast kept AA+; functional verdict colors + the dark nav + the blue accent
   unchanged), and the Pipeline-Builder canvas dot grid is now theme-aware (`--canvas-dot`,
   warm+subtle in light / much dimmer in dark, was a hardcoded light hex that read as
   distracting on the dark canvas) and now spans the whole scroll surface, not just the content
   plane. **Superseded 2026-07-10 (Wave 7, commit `eab5ff2`)** — painting the grid on BOTH the
   scroll surface and the content plane caused a visible double-grid regression (a static layer
   sliding over a moving one); the scroll-surface grid was removed the same day, so the dots live
   on the content plane only again (see the Wave-7 paragraph below). **UI feedback pass** (T-099): the Pipeline-Builder advisory-agent palette tiles
   (QC-triage/Pipeline-repair/Archivist) are now clickable in **View** mode (an `alwaysEnabled`
   `PaletteItem` flag — they're read-only advisory reads, never a mutation, so consulting one no
   longer forces Edit); Provenance relabels the artifact digest "hash" → "**fingerprint**" (more
   accurate — a content digest, not a process id) with a full-value hover; the Runs verdict bar
   is now capped `max-w-[300px]` with 2px inter-segment gaps so adjacent tones don't bleed
   together; Agent-triage's flagged-samples table now paginates at 10 rows/page. **Monitoring
   rework** (T-100, "Wave 2"): adds **recharts 3.9.2 (MIT)** — the first real charting
   dependency in the frontend, justified per the Dependencies guardrail (the hand-rolled SVG bar
   chart couldn't give hover tooltips + a trend line + a stable frame without reinventing a
   chart library; React-19-compatible, added at the maintainer's request). The "Verdicts over
   time" chart is now a Recharts `ComposedChart` (stacked per-verdict bars + a "Flagged (trend)"
   line + a grounded per-run hover tooltip + dashed gridlines), FROZEN to a ~14-day column frame
   that scrolls sideways beyond it instead of resizing the card on a 7d/14d/30d toggle. **This
   REVERSES, not just narrows, T-072's earlier frontend mitigation**: batch 7's per-run pager
   (`34bca5d`) is removed — the chart now renders every fetched run as a scrolling bar, not a
   paginated table — because a pager made no sense once the chart scrolls. Recurring signatures
   gain a unique stable id (`SIG-<first 8 chars of the signature hash>`) and a REVERSIBLE,
   `localStorage`-persisted clear-from-view/restore (never a DB purge — cleared signatures stay
   searchable in a collapsible "Cleared · N" section).
   **Wave 4 (2026-07-10, commits `f8d9ea0`→`1bb79b8`, T-101), closes two long-standing
   limitations — frontend-only, no verdict/gate/ADR-0001 boundary changed** (`git diff --stat
   e39bb4e 1bb79b8 -- src/ api/ tests/` empty). **API-client error detail** (`f8d9ea0`): every
   failed `get`/`write`/`fetchRunsPage` in `api.ts` used to throw a bare `${status} ${statusText}`;
   a new `httpError()` helper reads FastAPI's real error body — a 4xx `HTTPException`'s `detail`
   string, or a 422's `detail: [{msg}]` array — so every off-gate write's error toast now shows the
   backend's actual reason, app-wide (no wire-contract change). **Submit: real parsing, closes the
   "visual mock" limitation** (`1bb79b8`): the "Upload samplesheet" panel had no `<input
   type=file>` and a hardcoded "Parsed 4 samples" chip; `Submit.tsx` now does real CSV parsing on
   drop/browse, tolerant of both an **Illumina v2 SampleSheet** (`[Header]` + a `[*_Data]` section,
   auto-detecting run name/assay/platform) and a **plain CSV**
   (`Sample_ID,Sample_Type,index,index2,Study`) — a missing/renamed column degrades to an empty
   cell, never a crash. It also adds a **`sample_metadata.csv`** attach (the LIMS/subject sheet,
   the code's own inline label "G2" — previously no path existed for it at all): parses
   `Sample_ID,Subject_ID,Tissue`, merges tissue into the sample-type column, and shows the subject
   id under each sample name — **`subject_id` stays client-side only** (a labelled seam;
   `api/routers/intake.py`'s `SubmitRunIn`/`SampleIn` carry no subject field and `extra="forbid"`
   would reject one, backend unchanged). Sample-table pagination (25/page) and a scale-aware submit
   toast (summarize past 5 names, don't `join()` them) keep a 100+ sample mixed flowcell navigable.
   Honest deferrals: Median-review KPI (no backend field), Submit now hands off to the real
   `POST /api/runs` execution boundary and does real client-side samplesheet + sample_metadata.csv
   parsing, but `subject_id`/`tissue` is parsed + shown, not yet **persisted server-side** (the
   next Submit step — needs the data-platform design's "widen `sample.registered`" slice first,
   gated by its own G-PII/G-DEID guardrails) and there is still no BaseSpace connector (T-057), and
   `GET /api/monitoring`'s per-run `rows[]` stays uncapped server-side — T-072's backend half is
   the one open item, and as of batch 8 there is no longer a frontend render-cap either (the
   maintainer's own call; the scrolling chart degrades more gracefully than an uncapped table
   would at today's volume, but the underlying payload-size risk T-072 tracks is unmitigated in
   either direction until the backend gains `page`/`limit` on `runs[]`, mirroring `GET
   /api/runs`).
   **Audit retrofit (2026-07-10, commit `d65c9c1`, "Wave 3") — frontend-only, no verdict/gate/
   ADR-0001 boundary changed** (`git diff --stat 9733842 d65c9c1 -- src/ api/ tests/` empty).
   Realizes the maintainer's standing rule that no single accidental click may fire a
   cascading/state-changing write: a new reusable `components/ConfirmDialog.tsx`
   (`ConfirmProvider` mounted at the app root, outermost after `ToastProvider`; `useConfirm()`
   returns an async `confirm(opts) → Promise<boolean>`, Escape/click-outside both cancel) gates
   every stakes-y off-gate write. Review queue: Resolve/Escalate/Reopen confirm first (naming
   the effect + that it's audited); Suppress is DANGER-toned (names the cross-run cascade);
   batch Resolve/Suppress confirm the selected count; Acknowledge and un-suppress stay direct
   one-clicks (low-stakes, non-destructive). Admin's Act-as swaps its native `window.confirm`
   (T-092) for the same branded dialog. No new endpoint, no wire change — every confirmed
   action still calls the exact backend write it always did, landing in the Admin Activity
   audit feed unchanged; a reusable primitive for the Settings/variant authoring work ahead.
   **Settings agent table (2026-07-10, commit `7b579bb`, "Wave 5," ST1/ST2) — frontend-only,
   no verdict/gate/ADR-0001 boundary changed** (`git diff --stat c79f62c 7b579bb -- src/ api/
   tests/` empty). `SettingsModelTier.tsx`'s old 3-item model-tiering card (dropdowns applied on
   change) is now a scale-aware TABLE of the full seven-row advisory-agent roster — synthesizer,
   QC-triage, pipeline-repair, archivist, feedback-categorizer, node-author, and a **new
   metrics-expansion agent row** (ST2 — proposes new QC metrics + wiring; labelled `phase-2`; no
   such backend agent or `PIPEGUARD_*` env var exists yet, same non-status as node-author) —
   capped 10 rows/page. Each row shows its real `PIPEGUARD_*_MODEL` env var + model/cost + a
   Stub·$0/Live status, and edits behind a pencil into a staged draft (model + live toggle) with
   explicit Save/Cancel — nothing applies until Save (Cancel discards, verified no leak). A "New
   agent" button links to `/builder` (the node-author agent's home). **Still purely client-side
   state** — Save only updates local React state, no backend call exists — so the T-045 "UI-only,
   not wired to `PIPEGUARD_*_MODEL`" gap stays open; this is a presentation rebuild, not a
   persistence fix. ST2 part 1 (runbook thresholds bound to assay × sample type) was verified
   already correct in `SettingsAssayTable.tsx` — no change needed there.
   **Wave 7 (2026-07-10, commits `52124d3`→`d832553`, T-105–T-108,
   [journal](journal/2026-07-10-frontend-batch7.md)), a maintainer UI-feedback pass — frontend-only,
   no verdict/gate/ADR-0001 boundary changed** (`git diff --stat b4c3672 d832553 -- src/ api/
   tests/` empty; named "Wave 7," not "Batch 7/8," to avoid colliding with those already-used
   labels above). **Theme reverted + nav themeable** (T-105, `52124d3`): light mode reverts from
   the Batch-8 warm japandi trial to a **cool clinical** palette (`--color-page #eef1f5`,
   `--color-card #f9fbfd`, `--canvas-dot #d3dae4`) — the maintainer's call that japandi "didn't
   read clinical" — while staying off the pre-Batch-8 glaring pure-white; separately, the left nav
   gained its own `--color-nav*` var family (light nav in light mode, the original dark nav moved
   into the `:root[data-theme='dark']` override), so `Sidebar.tsx` now themes end-to-end instead
   of staying dark in both modes. **Builder-canvas fix** (T-106, `eab5ff2`, "PB3"): removes the
   double dot-grid the T-098 scroll-surface change caused (a static layer visibly sliding over a
   moving one) — a single grid now lives on the content plane only — and adds a minimap **viewport
   rectangle** that tracks scroll/zoom in real time (`BuilderCanvas.tsx` `updateVp()`, the same
   360/480-margin + zoom convention `fitToDag` uses). **Monitoring + Review queue** (T-107,
   `478129d`, "M7"/"RQ1"): the verdict-over-time chart's X-axis dates slant -35° in DD-MM-YY (was
   flat MM-DD), and the single always-on "Flagged" trend line becomes five toggleable lines
   (proceed/hold/rerun/escalate/flagged) via clickable legend chips (flagged on by default); the
   review-queue Resolve buttons drop their green (proceed-token) styling for a neutral outlined
   button, so "Acknowledge & review" stays the only primary action. **Inbox** (T-108, `d832553`,
   "GA3"), a brand-new off-gate surface: a personal notification/triage workspace replacing the
   dead top-bar bell. `context/InboxContext.tsx` **derives** notifications from the already-off-gate
   open/in-review review-queue tickets and layers a per-operator, `localStorage`-scoped overlay
   (read/flag/priority/kanban-column/due-date/note) plus user-authored self-reminders — re-scoped
   whenever Admin's "Act as" swaps identity, so triage state is per-person, not shared, and never
   lost across a re-fetch or a page change. `screens/Inbox.tsx` (`/inbox`, new Sidebar nav item
   under Operate, badged with the unread count) has four tabs — Inbox stream, Board (4-column
   native drag-and-drop kanban), Calendar (month grid + reminder composer), Notes — and
   `components/NotificationBell.tsx` is a quick-triage dropdown reading the same shared context, so
   the bell and the workspace can never drift apart. Never sets or reads a verdict/confidence; no
   new backend endpoint (`api.listTickets` already existed). Verified live light+dark, tsc+oxlint
   clean, no console errors.
   `src/pipeguard/synthetic/` drives the failure-mode data generator, incl. `scale.py` for
   at-volume runs (`demo/scale/bulk` CLI, T-050).

## Git conventions

Incremental, self-contained commits; short title + descriptive body. End commit
messages made with Claude Code with a `Co-Authored-By: Claude Opus 4.8
<noreply@anthropic.com>` trailer.
