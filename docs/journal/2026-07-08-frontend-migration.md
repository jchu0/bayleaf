# Journal — 2026-07-08 (MST) — Frontend fidelity pass: 1:1 design migration

| Field | Value |
|---|---|
| **Focus** | Re-skin every React screen to match the maintainer-added design handoff (`docs/design/frontend/`) 1:1 — actual UI/UX, not features — on the light content tokens. |
| **Participants** | James Hu, Claude Code |
| **Outcome** | All eight design screens (§1–§8) migrated faithfully to the light theme + verified against the live prototype; a real-data provenance canvas (§5) and a new Agent-triage screen (§6) added; legacy dark tokens removed. |

## Discussion

**Why this pass.** The first React build used *guessed* tokens (dark `#0d1117` sidebar,
emoji logo, hand-rolled icons). The maintainer then added a self-sufficient handoff
(`README.md` spec + `source/bayleaf.dc.html` + `support.js`) with exact tokens, and
asked for "a 1:1 representation … actual UI/UX." So this session was fidelity, not
scope: rebuild each screen against the handoff, comparing screenshots to the prototype
served on :8090.

**Method.** One screen at a time: read the §N spec + the prototype rendering →
rebuild on the light tokens (`bg-page`/`bg-card`/`text-text`/`border-line`/gate accents)
→ screenshot the live app → diff against the prototype → lint + commit. The app shell
(236px dark sidebar + 56px top bar) and the §3 hero were already done and eyeballed;
this pass finished the other six.

**Screens.** §8 Settings + §7 Monitoring + §4 Review queue + §2 Intake (the four
"quick" ones), then §5 Provenance + §6 Agent triage (the two bigger ones).
- **§4 Review queue** — cards-as-tickets with RBAC (reviewer resolves holds/reruns;
  escalations show a locked "Approver sign-off"), status-filter chips fed by an ephemeral
  acknowledge/resolve, and cross-run recurring-issue detection. Keyed recurrence on the
  **issue class (`rule_id`)**, not the content `signature` — observation-specific
  signatures never dedupe (each barcode value differs), so they'd never trip the "seen N×"
  banner the §4 repair-agent escalation hangs off.
- **§2 Intake + §6 Agent triage** — **run-scoped routes** (`/runs/:runId/intake`,
  `/runs/:runId/agent`), following the existing Provenance pattern so the top-bar run
  switcher drives them. Each is one flow cell / one flagged sample.

**Data honesty was the recurring tension.** The prototype shows an aspirational
full-instrument pipeline; our backend starts from FASTQ and is decision-centric. Rather
than fabricate InterOp tiles or DeepVariant runs, each screen states its boundary:
- **§2** rolls up real per-sample `metric_values` (Q30/Cluster PF/% identified/coverage/
  dup) and says the instrument InterOp tiles (PhiX, cluster density, error rate) and raw
  demux read counts aren't captured in this build.
- **§5** marks alignment/variant-calling "not run in this build" (no artifacts) instead
  of inventing a caller run.

**§5 provenance — real artifacts, not the W10 swimlane.** The held W10 branch built a
*decision-event* swimlane (run→samples→findings→verdict) and explicitly deferred the
*compute* DAG. The §5 spec wants the compute DAG (intake→demux→qc→align→variant→gate)
with a data-I/O drill-in (name · sha256 · size · origin). To ground that honestly I added
a small read-API endpoint, `GET /api/runs/{id}/artifacts`, that lists a run's real files
mapped to stages with a **streamed sha256, on-disk byte size, and the run's origin tag** —
size-capped at 8 MiB so it never slurps a raw-reads file to hash it. SampleSheet lands on
demux (the barcode manifest the preflight gate consumes vs `demux_stats`). This
supersedes the T-037 swimlane approach.

**§6 agent triage — real TriageNote.** Backed by the existing
`/cards/{sample}/triage` endpoint: advisory framing, offline/live badge (stub → offline),
likely cause + suggested action, citations split into findings vs knowledge/experience
(with relevance scores), and an "Ask the agent" thread that appends an honest offline stub
reply (live Q&A is env-armed, not fabricated).

**Cleanup.** With every screen migrated, removed the temporary legacy dark tokens from
`index.css` and migrated the one straggler (the unwired `MetricsPanel`). Full suite green
(207 py tests incl. the new artifacts test; oxlint + tsc clean; project mypy clean).

## Decisions

| Decision | Distilled to |
|---|---|
| §5 provenance canvas = fixed **compute DAG** (intake→demux→qc→align→variant→gate) with a real-artifact I/O drill-in, **superseding** the W10 event-swimlane approach | [tasks.md](../planning/tasks.md) T-037 |
| Add `GET /api/runs/{id}/artifacts` (real sha256 + size + origin; 8 MiB hash cap; SampleSheet→demux) as the §5 data source | [tasks.md](../planning/tasks.md) T-037; [functional.md](../requirements/functional.md) |
| Run-scope Intake (§2) + Agent triage (§6) routes like Provenance, so the top-bar switcher drives them | this journal (UI routing, no ADR) |
| §4 recurring-issue detection keys on **`rule_id`** (issue class), not the content signature | this journal (folded into T-022 fidelity) |
| Screens state their data boundary (no fabricated InterOp/compute artifacts) rather than mock it | reinforces CLAUDE.md data-handling; no new ADR |

## Open questions & TODO

- **Expose demux read counts** (`# Reads` / `% of run` from `demux_stats.csv`) so §2
  Sample admission shows true per-sample yield instead of the `% reads identified` proxy.
- **Wire `MetricsPanel`** (T-025 canonical/raw QC readout) into the §3 card body — migrated
  to light tokens, currently unused.
- **W12 / T-042 in-app feedback** still todo — the remaining wishlist BUILD item alongside
  containerization (T-041).
- Held worktree branch `worktree-agent-a3c8bf74c8bae9618` (stale-based W10 swimlane) can be
  pruned — its approach is superseded by §5.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-022 (migration done), T-037 (§5 canvas + artifacts endpoint)
- [docs/requirements/functional.md](../requirements/functional.md) — new artifacts endpoint
