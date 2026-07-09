# Journal — 2026-07-09 (MST) — Pipeline Builder (#11) + live Postgres test

| Field | Value |
|---|---|
| **Focus** | Two parallel workstreams: build the Pipeline Builder from the maintainer's refreshed design handoff, and run the ADR-0016 live-Postgres integration test. |
| **Participants** | James Hu, Claude Code (+ a background subagent for the Postgres test). |
| **Outcome** | Pipeline Builder MVP (#11 / W11) shipped + verified against the prototype; the Postgres adapters validated against a real Postgres 16 (parity + idempotent replay + feedback round-trip, no bug). |

## Discussion

**Parallelized.** The two asks are independent (frontend screen vs. backend integration
test), so the Postgres test ran as a background subagent (isolated to `tests/` + `src/`)
while I built the Pipeline Builder (frontend). No file overlap.

**Live Postgres test — the port is real.** Docker was available, so this went beyond a
skip-gated stub: the subagent brought up the compose Postgres, installed the `[postgres]`
extra, and ran `tests/test_persistence_postgres_live.py` against a live Postgres 16. The
load-bearing test rebuilds ONE authoritative ledger into both a SQLite and a Postgres
repository and asserts **byte-identical projections across all five tables** — which proves
the two adversarial-review fixes hold against a real server: TIMESTAMPTZ reads normalize to
UTC (pydantic renders them with a trailing `Z`; a non-UTC read would render an offset and
break the equality), and `seq`-BIGSERIAL reads preserve ledger insertion order. Plus
idempotent replay (`reset=False`, upserts only) and a `PostgresFeedbackStore` JSONB
round-trip. **All passed; no adapter bug.** The test is safe offline by construction
(`importorskip` + a probe-and-skip fixture, mirroring `test_artifacts_s3.py`) — 225 passed +
3 skipped with no server. A host-port clash (native pg on 5432) was handled with an
ephemeral compose override on 5442 via `DATABASE_URL` — exactly the override path the test
is built for. The committed compose file + venv were left unchanged.

**Pipeline Builder — the editable superset of the Provenance canvas.** The maintainer
refreshed the handoff (`design/frontend/README.md` → Pipeline Builder + a regenerated
prototype); I committed it, then built `PipelineBuilder.tsx` from its data contract
(`source/PipeGuard.dc.html` — the 7 seeded tool nodes with params/locators/IO, the edge
paths, the three `run_layout.yaml` profiles). It reuses the app shell + tokens verbatim and
adds the net-new surfaces: the sub-header toolbar (Edit/View, profile switcher,
Tidy/Validate/Emit), a three-pane workspace (palette · dot-grid H-scroll canvas · node
inspector) that breaks the max-width cap, and a validate/emit console with a live YAML
preview that swaps with the profile.

The **load-bearing product invariants are rendered as visible UI guarantees**, not just
copy: the QC-triage agent is a dashed port-less pill (an agent→gate data edge is
unrepresentable), the Decision gate is a terminal locked node with no verdict control and no
data-edge input (it reads the frozen five `run/` CSVs via the deterministic-ingest band),
and every emitted locator's `origin` is `unknown` (config locates, it never relabels
provenance). The primary action is **Emit**, never Run — composes, never executes.

Verified 1:1 against the prototype: toolbar, palette, the seeded DAG (pg-status badges,
typed ports, reference hollow rings, orthogonal edges, ingest band, terminal gate, agent
pill), node selection → the schema-driven inspector, profile switch → the YAML swaps
(giab_panel/default/sarek), Emit → the console, and Edit⇄View (View lights node tints
ok/warn/blocked, fills I/O, shows the gate's `proceed 3 · hold 1 · escalate 1`).

MVP scope per the handoff: configure the pre-seeded chain + Validate/Emit + link-out View.
Phase-2 seams (free composition, drag-authoring, dry-run, in-app run, RNA-seq, the
config loader) are designed, not built.

## Decisions

| Decision | Distilled to |
|---|---|
| Run the two asks in parallel (Postgres test as a background subagent, builder inline) | this journal |
| Build the Pipeline Builder from the prototype's data contract verbatim; reuse the shell/tokens; MVP = configure-a-known-pipeline, not free composition | [tasks.md](../planning/tasks.md) T-044; [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) #11 |
| Keep the live Postgres test skip-safe offline (importorskip + probe-and-skip), gated on a reachable DSN | [tasks.md](../planning/tasks.md) T-043 |

## Open questions & TODO

- Pipeline Builder Phase-2 (from the handoff): free composition + edge-drawing, Tidy
  auto-layout, dry-run (locator resolution vs a real run dir), the `PIPEGUARD_RUN_LAYOUT`
  loader so the running system consumes an emitted layout, in-app Run hand-off, RNA-seq.
- Copy/Download on the emit console are stubbed (no clipboard/file write yet).
- The live Postgres test needs docker + the `[postgres]` extra to actually run (skips
  otherwise) — it is not part of the default CI green path, by design.

## Distilled into

- [docs/adr/ADR-0016-postgres-port.md](../adr/ADR-0016-postgres-port.md) — the live-Postgres test (this session's 2nd workstream) is the ADR-0016 follow-up; see also [2026-07-09-postgres-port.md](2026-07-09-postgres-port.md)
- [docs/planning/tasks.md](../planning/tasks.md) — T-044 (builder), T-043 (live pg test note)
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — #11 built, #12/#19 updated
