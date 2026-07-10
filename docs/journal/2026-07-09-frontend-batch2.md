# Journal — 2026-07-09 (MST) — Frontend maintainer-feedback batch (admin, backend wiring, fidelity)

| Field | Value |
|---|---|
| **Focus** | A large maintainer feedback batch on the live React app: admin panel, restore the Analyze nav divider, "new pipeline" option, decision-card styling + missing QC checks, connect the frontend to the backend, mock all prototype data with GIAB, and a fidelity pass; plus push incrementally + merge to main. |
| **Outcome** | All asks delivered across 6 commits on `main` (`e891e62`→`6371128`). App is now populated (29 GIAB runs), the 3 broken write paths are wired, an admin panel + new-pipeline flow shipped, and 6 per-screen fidelity closers landed. tsc/oxlint/ruff/mypy(68)/pytest all green; browser-verified. |
| **Related** | [scope journal](2026-07-09-frontend-design-replication-scope.md) · [tasks.md](../planning/tasks.md) T-062 · [seed_giab_demo.py](../../scripts/seed_giab_demo.py) |

## Discussion

Scoped via a 15-agent read-only workflow (per-screen fidelity re-audit + backend-connection map +
admin design + GIAB mock-data plan + old-files audit → synthesis). Then executed in waves, each
committed + pushed to `main` (the maintainer asked for incremental pushes + main merges):

1. **Wave 0 (`e891e62`)** — the biggest lever: `scripts/seed_giab_demo.py` seeds ~24 synthetic
   (origin `contrived`) GIAB-named runs → 29 discoverable, lighting up every screen (this also fixed
   "decision missing QC checks" — the QC hero was hidden on cards with no `metric_values`). Restored
   the Analyze nav group; FacetChip count → filled pill (the "styling off" fix, shared across 3
   screens); `RunSpec.platform` field; `RoleContext.setActor`; removed dead scaffold assets.
2. **New pipeline (`327c2d2`)** — a "+ New" toolbar button + choice modal; `BuilderCanvas` seeded
   DAG made conditional so a blank graph renders empty. View-default still guards the linked pipeline.
3. **Admin panel (`ce396f7`)** — `/admin`, approver-gated: Users & roles (client-mock + "Act as"),
   Activity log (real audit feed from thresholds/pipelines/tickets), System readout. UserPanel now
   reflects the live actor.
4. **Backend writes (`586f832`)** — fixed 3 broken paths: threshold slug (was `thresholds:<display>`
   → 422), pipeline save→submit→approve chain (approve was 409ing), reviewer resolve/suppress RBAC
   (relaxed the backend to match the design). New Toast surfaces real 403/409/422 instead of silent
   divergence; writes reconcile from the response.
5. **Fidelity closers (`6371128`)** — Decision QC "not measured" rows; Monitoring signature
   first/last-seen + trend + affected-run deep-links (additive backend aggregate); Review-queue
   action footer outside the collapsible; Intake yield target; Settings-dialog polish; Provenance
   note fallback; Agent two-line citations.

**Invariants held throughout:** no confidence meter; origin honest (`contrived`, real HG002 run
untouched); rules decide / AI advises; compose ≠ execute; admin off-gate.

**Deferred (lower priority, flagged):** Builder Dry-run/Diff/Export/Archivist wiring + saved-profiles
(endpoints exist, UI mock); Submit create-run (no backend endpoint — needs a net-new `POST /api/runs`).
