# Journal — 2026-07-12 (MST) — Builder agent hardening: observation bindings, Phase-4 read, reserved-port honesty

| Field | Value |
|---|---|
| **Focus** | Sweep the lean docs (requirements / quality / planning / CLAUDE code map) to reflect a Builder-agent hardening arc merged to `main` (commits `e40784c`→`7c5c073`, base `14307f7`). |
| **Participants** | doc-keeper (Fable-5 subagent), maintainer (James Hu, authored the code) |
| **Outcome** | Requirements, evaluation census + new EVAL claims, tasks, HISTORY, and the CLAUDE code map now describe the agent-observation binding model, the Phase-4 scoped/de-identified node-observation read, reserved-port promotion, the Builder UX/inspector polish, and the `tsc -b` pre-push gate. |

## Discussion

### What landed (5 commits, grounded by reading each diff)

1. **`e40784c` — `tsc -b` pre-push hook + mosdepth 5-output catalog fix + Builder UX + Provenance polish.**
   The root `tsconfig` is references-only, so `tsc --noEmit` was a no-op and nothing ran `tsc -b`
   — that is how a type error reached `main` uncaught. Adds a `frontend-tsc` pre-push hook
   (`.pre-commit-config.yaml`) at the same heavy-check-on-push cadence as pytest. Separately, the
   Builder card advertised **five** mosdepth outputs while `catalog.py` declared only two
   (`mosdepth_summary`, `mosdepth_thresholds`) — that arity gap tripped the compiler's
   output-drift guard and **422'd Export-to-Nextflow on the default Builder view**. The catalog
   now declares all three real byproducts of the *same* `mosdepth --by … --thresholds` command
   (`regions`/`global_dist`/`region_dist`); the seeded `germline_graph()` still trims to
   summary+thresholds and stays a valid subset (drift guard green). Frontend UX: phantom markdup
   `reference_fasta` port removed; reserved ports made honestly non-armable with a Connect-mode
   tooltip; legend fix + dotted advisory-agent edge row; a Hide-that-stays-hidden inspector rail;
   Provenance wider lineage cards + a Stage-X–Y-of-N scroll indicator.

2. **`69a2dab` — the agent-observation binding model (frontend + types only).** Replaces the
   ephemeral `advisoryAttach: Set` with a typed, persisted `AgentBinding { agent, node, grants:
   ('outputs'|'logs')[] }` stored in a `graph.agent_bindings` envelope key **the compiler NEVER
   dereferences**. Proven byte-identical compile with/without bindings **by construction**: the
   frontend compile/run payload is only `{nodes.map(toCompileNode), edges}`, and
   `api/routers/nextflow.py`'s `CompileRequest` is pydantic-default `extra="ignore"`, so an
   `agent_bindings` key cannot reach `compile_graph`. Default grant `outputs`; `logs` opt-in +
   de-identified (subject-id PII guardrail). Taxonomy: **Pipeline-repair + Archivist moved OUT of
   the Builder palette to Agent-triage launchers**; the Builder keeps QC-triage (node-attachable)
   + Node-authoring. ADR-0001-clean (advisory, off the deterministic path).

3. **`4582c7d` — Phase 4: the scoped, de-identified agent-read (backend + tests).** New read-only
   `GET /api/runs/{run_id}/nodes/{node_id}/observations?grants=outputs[,logs]`
   (`api/routers/node_observations.py`, `require_role` viewer+, traversal-hardened, honest-empty).
   `grants=outputs` returns the bound node's PUBLISHED artifact list scoped by matching the tool's
   catalogued output-port globs against the run's Nextflow publish dir (never the whole run).
   `grants=logs` (opt-in) returns a DE-IDENTIFIED tail of `.command.log`/`.command.err` via
   `api/deid.py`'s new `scrub_text()` — pseudonymizes the run's known subject ids (from
   `sample_metadata.csv`) and regex-redacts email + 6+-digit PII. A test plants
   `SUBJ-00042-JohnDoe` / `jane.patient@hospital.org` / MRN `7654321` and asserts all three are
   scrubbed while non-sensitive content survives. `gather_node_observations()` is the
   triage-consumption seam — agent consumption + a UI display are labelled deferred follow-ups;
   an authored-pipeline node→graph linkage isn't tracked (degrades to honest-empty).

4. **`1621e3f` — reserved-port promotion (no superficial ports).** Every shown Builder port now
   maps to a REAL Nextflow channel or was removed. Promoted (real emit + script edit): fastp
   `unpaired_fastq` (`--unpaired1/2`), fastp `failed_fastq` (`--failed_out`), bcftools norm
   `vcf_index` (`.csi` from the existing index step), MultiQC `multiqc_html`. Removed as non-real:
   bwa `read_group` (a string, not a file), mosdepth `per_base` (`--no-per-base` suppresses it),
   bcftools norm `panel_bed` (norm is genome-wide), MultiQC `fastqc_zip`/`bcftools_stats`/
   `picard_hsmetrics`/`ngscheckmate`. Left honestly-reserved: fastp `adapter_fasta` (a real
   optional INPUT; positional promotion deferred). Germline regen + drift green; +5 tests
   (`test_nextflow_promoted_ports.py`).

5. **`7c5c073` — inspector `Save card`→`Save`, grouped with Delete-node in one footer row.**
   Cosmetic/layout only; `onSaveCard`/`onDeleteNode` behavior + edit-vs-view gating unchanged.

### Grounding corrections (Fact)

1. **The compiler injection escaping is NOT part of this arc.** The task brief attributed
   "compiler robustness (injection escaping)" to `e40784c`, but `git diff --stat 14307f7..HEAD --
   src/` shows `compiler.py` untouched in this arc. The escaping (`KIND_PATTERN`,
   `NODE_ID_PATTERN`, `_groovy_escape`, per-node `CompileError`s) landed earlier in `37e54a8`
   (T-140), which is an ancestor of the arc base `14307f7`. It is already documented as
   **REQ-NF-046** and **EVAL-017** — so no new NF REQ was written for it (would duplicate); the
   waiver is recorded in the sweep summary. The File-input `_source_channel` routing and
   `is_source()` widening the brief mentioned also live in `37e54a8`, not this arc.

2. **Census file count: 48, not 46.** The brief said "627/7 across 46 files." Re-derived
   2026-07-12: `uv run pytest --collect-only -q` → **634 collected** (`uv run pytest -q` →
   **627 passed / 7 skipped** offline, `nextflow` absent); `git ls-files 'tests/*.py' | wc -l` →
   **48**. This arc added 2 test files (`test_nextflow_promoted_ports.py`,
   `test_node_observations.py`), 46→48, and +14 tests (620→634). The census in
   `quality/evaluation.md` was updated to **634 / 48** and the milestone appended to HISTORY.

3. **Agent-binding invariant is by-construction, not a dedicated automated test.** `69a2dab`
   touched no backend/tests; the "byte-identical compile" guarantee rests on the frontend payload
   shape + `CompileRequest`'s `extra="ignore"`, pinned indirectly by the germline byte-for-byte
   drift guard (EVAL-006). EVAL-019 records this honestly (Automated? = partly by-construction).

## Decisions

| Decision | Distilled to |
|---|---|
| The agent-observation binding is a persisted graph key the compiler never dereferences (advisory, off the deterministic path). | [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) (authored by a parallel agent this session); REQ-F-101; EVAL-019 (compile-isolation claim). Reinforces [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md). |
| Node-log observation grant must be de-identified before egress (subject-id + generic PII), same honesty posture as the export/share scrubs — a demo heuristic, NOT HIPAA de-id. | REQ-F-101, REQ-NF-028; EVAL-052. Extends [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) least-privilege + REQ-NF-023 de-id posture. |
| Every shown Builder port maps to a real Nextflow channel or is removed — no superficial ports. | REQ-F-102; EVAL-019 (port-promotion claim). |
| `tsc -b` runs on pre-push (the references-only root tsconfig made `tsc --noEmit` a no-op). | REQ-NF-054. |

## Open questions & TODO

1. **Agent consumption of the node-observation read is deferred** — `gather_node_observations()`
   is the seam; the QC-triage agent stays a pure narrator over rule findings for now, and no UI
   surface displays the scoped view yet.
2. **Authored-pipeline node → run-graph linkage isn't tracked** — a node id absent from the
   seeded `germline_graph()` degrades to honest-empty rather than resolving a wrong node's files.
3. **fastp `adapter_fasta` stays honestly-reserved** — a real optional input whose positional
   promotion into the script was deferred.
4. The Slurm executor profile (REQ-F-090/REQ-NF-060) and a genuinely live multi-sample Nextflow
   run (REQ-F-095) remain the standing un-verified seams — unchanged by this arc.

## Distilled into

- [requirements/functional.md](../requirements/functional.md) — REQ-F-101 (agent-observation binding + Phase-4 read), REQ-F-102 (reserved-port promotion), REQ-F-103 (inspector Save/Delete row).
- [requirements/nonfunctional.md](../requirements/nonfunctional.md) — REQ-NF-028 (node-log de-id scrub), REQ-NF-054 (`tsc -b` pre-push gate). REQ-NF-046 (compiler injection) already covers the brief's compiler item — waived, not duplicated.
- [quality/evaluation.md](../quality/evaluation.md) — census → 634 / 48 (627 pass / 7 skip offline); EVAL-019 (reserved-port promotion + agent-binding compile isolation), EVAL-052 (scoped, de-identified node-observation read).
- [planning/tasks.md](../planning/tasks.md) — T-142 (binding model + Phase-4 read), T-143 (reserved-port honesty + Builder UX + `tsc -b`).
- [HISTORY.md](../HISTORY.md) — dated section + census milestone 634 / 48.
- [CLAUDE.md](../../CLAUDE.md) — "Current code map" current-state note (terse).
