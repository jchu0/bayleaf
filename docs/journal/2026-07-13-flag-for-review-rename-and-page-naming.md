# Journal — 2026-07-13 (MST) — flag-for-review rename + operator page-name simplification

| Field | Value |
|---|---|
| **Focus** | Docs-only SWEEP for two coordinated renames the maintainer is executing repo-wide: (1) the variant-gate rule/policy/field **route-to-human → flag-for-review** (incl. `VAR-RTH-001 → VAR-FFR-001`), and (2) the operator **page-name simplification** + a new **System Agents** page. No product code, tests, or design deliverables (`briefs/`, `handoffs/`, `source/`, `bayleaf.html`) touched. |
| **Participants** | doc-keeper subagent (SWEEP + AUDIT), in the `bayleaf-flag-review` worktree |
| **Outcome** | Current-state canonical docs carry the new names; dated journals/HISTORY + tasks.md completed rows keep the historical names with a dated rename note; two code-grounded drifts fixed (agents.md System-Agents `PageId`, agents.md `/agents → /system-agents` route); one cross-link anchor repaired (`nonfunctional.md → ui-conventions UIC-11`). |

## Discussion

### The two renames and how they were routed

1. **Rename convention (given by the maintainer):**
   a. User-facing prose "route to human" / "routed to mandatory human review" / "to a human" →
      **"Flag for review"** (headings/stages/buttons) or **"flagged for review"** (prose).
   b. Identifiers: `VAR-RTH-001 → VAR-FFR-001`; `RouteToHumanPolicy → FlagForReviewPolicy`;
      `_check_route_to_human → _check_flag_for_review`; the `route_to_human` runbook field / dict
      key / arming-marker file and the `route_to_human.json` artifact-stage key → `flag_for_review*`;
      `tests/test_route_to_human.py → tests/test_flag_for_review.py`.
   c. Page names: Sample accessioning → **Sample Metadata**, Submit samplesheet → **Samplesheet**,
      Intake gate → **Intake**, Decision cards → **Decisions**, Agent triage → **Triage**,
      Pipeline builder → **Pipeline**; plus a NEW **System Agents** page (pipeline-repair + archivist
      split off Triage).

2. **Current-state vs dated archive (the honesty rule I applied).** Per
   [DOCUMENTATION_HABITS](../DOCUMENTATION_HABITS.md) and the maintainer's instruction, **current-state
   canonical docs get the new name**; **dated journals + HISTORY + the completed-task rows in
   `tasks.md` keep the historical name** (accurate-at-the-time) with a short dated rename note rather
   than a rewrite. A rename is not a reason to rewrite history.

3. **Mechanical rename, done safely.** I ran a masked string transform over the current-state
   canonical set only, **protecting the journal filename token** `route-to-human-deid` (the file
   `journal/2026-07-10-wave6-route-to-human-deid.md` keeps its name, so inbound links stay valid).
   One bug caught and reverted immediately: `VAR-RTH` is a substring of the **fixture directory**
   `data/RUN-2026-07-11-CLINVAR-RTH/`, so the transform wrongly produced `CLINVAR-FFR`. The fixture
   directory is a real on-disk name **not** in the rename convention — reverted every `CLINVAR-FFR`
   back to `CLINVAR-RTH` (verified 0 remaining). Prose variants ("routes a sample to mandatory human
   review", "route to a human", "A rule decides to ROUTE") were hand-fixed after the mechanical pass.

### Grounding the page names in code (AUDIT)

4. The page-name simplification is **grounded in `frontend/src/access.ts::PAGE_CATALOG`**, which
   already carries the new labels: `Sample Metadata`, `Samplesheet`, `Intake`, `Decisions`,
   `Triage`, `System Agents`, `Pipeline` (verified by reading `access.ts`, `Sidebar.tsx`,
   `App.tsx`). So docs were updated to *match shipped labels*, not to describe a not-yet-shipped
   rename. (The rest of the frontend still mixes old labels in component copy — that is the
   concurrent code session's half.)

5. **Two code-grounded drifts fixed in `design/agents.md`** (invariant: a built feature must not
   read as not-built):
   a. The taxonomy section claimed System Agents and Triage "share one `PageId: 'agent'`" and that
      page-access "cannot distinguish" them. `access.ts:49` now has a **distinct**
      `{ id: 'systemAgents', label: 'System Agents' }` and `App.tsx:78` routes `/system-agents` →
      `RequirePage page="systemAgents"` → a dedicated `SystemAgents.tsx`. Rewrote the section to the
      shipped state (System Agents is its own page/`PageId`; page-access *can* now gate the two
      independently).
   b. The doc named the run-independent route `/agents`; the shipped nav route is **`/system-agents`**
      (`Sidebar.tsx:108`, `App.tsx:78`), with `/agents` kept only as a legacy deep-link to per-run
      Triage. Corrected.

## Decisions

| Decision | Distilled to |
|---|---|
| Current-state docs adopt `flag-for-review`/`VAR-FFR-001`; dated journals/HISTORY/tasks-rows keep the old name + a dated note | [ADR-0018 Naming row](../adr/ADR-0018-variant-interpretation-advisory-evidence.md), [HISTORY.md § ADR-0018](../HISTORY.md), this journal |
| The `data/RUN-2026-07-11-CLINVAR-RTH/` fixture directory is **NOT** renamed (not in the convention; a real on-disk name) | reverted in all current-state docs |
| Page labels follow `frontend/src/access.ts::PAGE_CATALOG` as the single source of truth | [functional.md REQ-F-042](../requirements/functional.md), [design/frontend/README.md §4](../design/frontend/README.md), [usage/*](../usage/README.md) |
| System Agents is a distinct page/`PageId` (corrects agents.md's shared-`PageId` claim) | [design/agents.md § taxonomy](../design/agents.md) |

## Open questions & TODO

- **Page-name follow-ups (not the rename authority — deferred, honest):** inline prose in the large
  `design/frontend/README.md` §5.x walkthroughs, `design/architecture.md`, `demo/demo_plan.md`,
  `demo/run-of-show.md`, and the frontend design deliverables (`briefs/`, `handoffs/`, `source/`,
  `bayleaf.html` — **out of doc-keeper scope**) still use some previous labels. The nav list (§4),
  `access.ts`, `usage/`, `functional.md`, `ui-conventions.md`, and `agents.md` are the authoritative
  current references and are updated.
- **Code side (concurrent session):** the actual `src/`/`api/`/`tests/` rename (class, function,
  field, marker, `test_flag_for_review.py`) and the remaining frontend component-copy page labels are
  owned by the code session; this worktree's code is unchanged, so its docs now *lead* the code until
  the two land together.
- `tasks.md` completed-task rows (T-104/T-109/T-119/T-128/T-130/T-132/T-133) intentionally retain the
  historical names; if the maintainer prefers, they could later be annotated per-row.

## Distilled into

- [docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (new Naming row + body)
- [docs/design/variant-interpretation.md](../design/variant-interpretation.md), [docs/data/qc_metrics.md](../data/qc_metrics.md), [docs/data/schemas.md](../data/schemas.md), [docs/quality/evaluation.md](../quality/evaluation.md) (EVAL-012), [docs/requirements/functional.md](../requirements/functional.md) (REQ-F-018 + REQ-F-042)
- [docs/design/architecture.md](../design/architecture.md), [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md), [docs/design/ui-conventions.md](../design/ui-conventions.md), [docs/design/agents.md](../design/agents.md), [docs/design/frontend/README.md](../design/frontend/README.md)
- [docs/usage/README.md](../usage/README.md), [docs/usage/operator-guide.md](../usage/operator-guide.md)
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md), [docs/planning/tasks.md](../planning/tasks.md), [docs/HISTORY.md](../HISTORY.md), [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) (UIC-11 anchor fix)
- Dated rename notes appended to 9 historical journals (route-to-human mentions)
