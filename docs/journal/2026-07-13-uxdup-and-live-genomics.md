# Journal — 2026-07-13 (MST) — Fable-audit reconciliation, the UX-DUP refactor, and the live-genomics calibrated-data flip

| Field | Value |
|---|---|
| **Focus** | Three arcs on `feat/gap-analysis-remediation`, after the [2026-07-13 audit-fixes-IA journal](2026-07-13-audit-fixes-ia.md): (a) **reconcile** the fable release-hardening audit against HEAD and close the genuinely-open remainder; (b) land the **UX-DUP** faceted-IA / duplicate-data refactor end-to-end; (c) freeze the **live-genomics** calibrated FREEMIX + concordance so WS-02/WS-04 stop saying "not pipeline-produced". Plus two Builder IA fixes surfaced by the maintainer. |
| **Participants** | James Hu + Claude Opus 4.8; a general-purpose background agent (RunsContext + TicketsContext); a compute/data-prep terminal session (the live GIAB pass, `data/real-giab/T7_RUN_STATUS.md`); doc-keeper (this sweep). |
| **Outcome** | 15 commits (`7cef743`…`4ec82ae`). The fable audit's 26 consolidated findings were re-verified against HEAD (21 already fixed by prior hardening); the actionable remainder + **3 findings the audit's own SYNTHESIS silently dropped** (J3/J8/J10) closed. UX-DUP: all 7 migration steps landed, `tsc -b`/oxlint clean, key flows browser-verified (incl. a network-traced proof of the queue→inbox bus). Live-genomics: a **calibrated** genome-wide FREEMIX (`0.000220096`, sanity-check passed natively) + real hap.py SNP-F1 (`0.989276`) committed as tiny fixtures and proven through the public `ingest_results_dir → run_gate` path. Census re-derived to **727 tests / 55 files** (719 pass / 8 skip). |

## Discussion

### Arc A — the fable-audit reconciliation (are the audit's findings actually done?)

The maintainer asked whether the fable **release-hardening audit** ([audit/SYNTHESIS.md](../../audit/SYNTHESIS.md), 60 raw → 26 consolidated: P0-1, P1-1…6, P2-1…12, P3-1…14) had really been addressed — a distinct effort from this session's UI/integration audit (the G1–G8 fixes). A 29-agent reconciliation re-checked every finding against the code at HEAD rather than trusting the audit's original state:

- **21 FIXED / 6 PARTIAL / 1 OPEN.** The P0, all six P1s, and all twelve P2s were already closed by post-audit hardening (chiefly `94c19da` "fix audit P0 + 6 P1s + W1 approval-gate MVP", the durable job store, the P3 backlog waves). **Nothing still-open is on the recorded demo path.**
- The completeness sweep caught what the audit's own SYNTHESIS got wrong: it claims "0 findings dropped", but **J3/J8/J10** (from `journeys.md`, all Confirmed) appear in no P-item — dropped, not refuted. J3 is a real truthfulness defect.

The actionable remainder was then closed (all off-camera, all the "confident surface vs thin wiring" class):

1. **`b03d1fa` — honesty cluster.** WS-01 `CheckCoverage` now flips contamination/identity to "ran" when a FREEMIX/NGSCheckMate metric is actually **examined** (`_examined_metric_categories` in `rules.py`; was hardcoded `False`, so an examined-and-passed FREEMIX read "not examined") — present = examined = ran, mirroring the finding-less clean-gate rule; verdict/hash-neutral, freeze-tested. **J3** (BuilderConsole Emit panel no longer claims it `Wrote` a file it never wrote). **J8** (ReviewQueue rerun-resolution copy — a re-run needs a new run id, not a phantom requeue control). **J10** (Submit button role-gated in the UI, not a post-POST 403). A stale runbook "Ts/Tv ungated" comment corrected.
2. **`7cef743` — audit G8 / WS-09 #1.** Builder-Run (`POST /api/pipelines/run`) now calls `check_parse_contract` before launching the driver — parity with intake, so a non-gate-able authored pipeline is rejected at submit instead of running to completion then dying at parse. Done **test-first**: the minimal test fixtures (a `fastp → bwa` graph that can't produce the frozen-five) were reconciled to the shared `germline_graph_dict()`, and a new red test freezes the gap (proven red-before-impl via stash).

### Arc B — the UX-DUP refactor (one canonical list, faceted views)

The [duplicate-data UX review](../../audit/ux-duplicate-data-review.md) (26 sub-issues, 6 proposed primitives) was landed as its 7-step migration, each an independently-shippable, verdict-palette-preserving slice:

1. **`4fde497` / `ec89619`** — extracted `governingGate`/`VERDICT_ORDER`/`GATE_TAG` into `verdict.ts` (10 copies → 1); a `useApiHealth` module-poller singleton (2 pollers → 1); memoized bell selectors in `InboxContext` (killed an O(n log n) sort in the top bar on every inbox mutation, on every page); the shared `<Pager>` gained ellipsis windowing.
2. **`6802e9b`** — Monitoring "Cleared" is now a facet on the one paginated list, not a second unpaginated section.
3. **`fbc4d5b`** — one `inboxStats` pass (chips/tiles/badge/bell agree) + dropped the Inbox "All" chip (decision A).
4. **`5daf1a9`** — NEW `hooks/useRun.ts` session cache: RunDetail/AgentTriage/Provenance stop re-fetching the heaviest payload 3× per journey.
5. **`8e95341` (= B)** — NEW `components/FacetBar.tsx` collapses RunDetail's *triple* verdict-count display (bar + banner + tab strip) into one clickable bar + an attention header CTA; `5b45ae1` dropped the ReviewQueue "All" tab (search now escapes the status facet).
6. **`67099f6` (= step 7)** — NEW `hooks/useRuns.ts` module-singleton unifies the runs-list fetch across Layout/RunOverview/RunSelector/TopBar (header-borne counts preserved).
7. **`3140527` (= C)** — NEW `ticketsBus.ts` invalidation bus ends the queue↔inbox status drift: a successful queue resolve/assign fires `bumpTickets()`, the always-mounted `InboxContext` re-reads. `f6ffbac` fixed a pre-existing asymmetry the bus made visible — `assign`'s optimistic patch had no rollback-on-rejected-write (unlike `syncAction`).

**Decision A applied only to the *actionable* surfaces** (ReviewQueue, Inbox, RunDetail-via-FacetBar). RunOverview and Admin-activity keep "All" per the review's own decision rule 3 (browse-all is those pages' job — the review explicitly exempts RunOverview). **Deliberately deferred:** the ReviewQueue O(runs) `api.run` fan-out — it needs a backend "flagged-cards" endpoint, so the background agent chose the conservative bus (option b) over moving the invariant-heavy `syncAction`/selection machinery.

Browser-verified the risky runtime flows: the selection invariant survives (checkbox → run-group → bulk bar), the confirm gate fires, and a **network trace proved the sync** — `POST .../action` → then `GET tickets?status=open` + `?status=in_review` (InboxContext re-fetching, triggered by the bus). Demo state was restored after (ticket reopened).

### Arc C — live-genomics: WS-02/WS-04 proven on calibrated tool output

The compute terminal session finished the two-track live pass (`T7_RUN_STATUS.md`): a real Nextflow germline run (chr20/21/22, 300,175 variants) and — the long pole — a **genome-wide VerifyBamID2** on the full HG002 2×250 BAM. The headline: the FREEMIX (`0.000220096`, ~0.02%) **passed the marker sanity check natively** (no `--DisableSanityCheck`), so it is a **calibrated** contamination estimate, not the chr20-capped heuristic.

Per the run plan, the orchestrating session did ingest → gate → freeze (`478d579`): the tiny real tool outputs (294 B `.selfSM`, 893 B hap.py `summary.csv`; the 122 GB BAM stays on the SSD) are committed under `tests/fixtures/giab_real/` with an origin-tagged NOTE, and `tests/test_real_giab_calibrated.py` reads them through the **same public `ingest_results_dir → run_gate`** path the demo uses — asserting contamination clean (0.02% ≪ the 2% gate) and SNP-F1 an honest **borderline WARN** (0.989276, just under the illustrative 0.99 gate, above the 0.95 hard-fail). This upgrades WS-02/WS-04 from "parser-wired, fixture-tested" to **"proven on real, calibrated tool output"** — the last mile the WS-02/WS-04 tests explicitly deferred.

### Arc D — two Builder IA fixes (maintainer-spotted)

`4ec82ae` — **node-authoring is a compose-time *feature*, not an agent tile.** The palette listed "Node-authoring" in the Agents group *and* offered an "Author a tool node" button (two doors to the same modal), miscategorizing it: it neither attaches to a node (unlike QC-triage) nor acts across runs (unlike the system agents Pipeline-repair/Archivist). Removed the agent tile; the single edit-mode "Author a tool node" action is its home (agent-backed, not an attachable agent). This also collapsed the duplicate entry point. (The earlier IA fix — splitting System-agents from per-run Agent-triage — is in the prior journal.)

## Decisions

| Decision | Distilled to |
|---|---|
| **UX-DUP "drop All" (decision A) applies to actionable surfaces only.** ReviewQueue/Inbox/RunDetail drop the catch-all; RunOverview + Admin-activity keep it per the review's decision rule 3 (browse-all is those pages' job). | `docs/design/frontend/README.md`; the review's §3 rules; no new ADR (an application of the review, not a new architectural decision). |
| **TicketsContext = a conservative invalidation bus, not a data-layer merge.** End the queue↔inbox status drift via `ticketsBus`; leave ReviewQueue's O(runs) `api.run` fan-out (needs a backend flagged-cards endpoint). | `frontend/src/ticketsBus.ts`; `docs/design/frontend/README.md`; a labelled deferral, not a new ADR. |
| **Node-authoring is a Builder feature, not an agent.** It's neither node-scoped (QC-triage) nor run/org-scoped (system agents), so it leaves the Agents group and lives as the edit-mode "Author a tool node" action. | `frontend/src/screens/PipelineBuilder.tsx`; `docs/design/frontend/README.md` (agent taxonomy). |
| **WS-02/WS-04 are proven on real calibrated tool output, not merely fixture-format.** Commit the tiny genuine outputs + a real-path test through the public spine. | `CLAUDE.md` item 1a/1g; `docs/data/metric_registry.md`; `tests/fixtures/giab_real/NOTE.md`. |

## Open questions & TODO

1. **The ReviewQueue O(runs) `api.run` fan-out** stays — the biggest single cost, but eliminating it needs a backend "flagged-cards" endpoint (or a lazy-load rearchitecture) rather than a frontend change. Tracked as the deferred tail of UX-DUP step 6.
2. **`gap-analysis → main` PR** — now unblocked (live-genomics in, audit closed, UX-DUP verified). To be opened after this doc sweep lands.
3. Remaining labelled deferrals unchanged: WS-07 full (agent artifact context / retrieval), WS-08 full (server-side binding enforcement), the multi-sample live run + Slurm cluster run (env-gated).
4. **Owed:** `docs/planning/tasks.md` header/row refresh for this session — the doc-keeper sweep stalled before it (the working TaskList tracker is current). Minor; discharge on the next doc pass.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) — WS-02/WS-04 "proven on real calibrated tool output" (item 1a/1g), G8 Builder-Run parse-contract parity (item 4).
- [docs/design/frontend/README.md](../design/frontend/README.md) — FacetBar, `useRun`/`useRuns`, `ticketsBus`, `inboxStats`, the dropped "All" facets, the node-authoring recategorization.
- [docs/data/metric_registry.md](../data/metric_registry.md), [docs/data/qc_metrics.md](../data/qc_metrics.md), [docs/data/schemas.md](../data/schemas.md) — calibrated-data provenance / metric status.
- [docs/quality/evaluation.md](../quality/evaluation.md) — census 727/55, 719 pass / 8 skip.
- This entry.
