# Journal — 2026-07-11 (MST) — Nextflow becomes executable: card-graph compiler + Nextflow-first intake

| Field | Value |
|---|---|
| **Focus** | SWEEP + AUTHOR the docs owed by 5 already-landed commits (`10f1816`→`e4ba174`, offline suite 423 passed / 4 skipped on a machine with `nextflow` on `PATH`, a machine-gated live `nextflow run -stub-run` test passing; ruff+mypy+tsc+oxlint clean): a new `src/bayleaf/nextflow/` card-graph→Nextflow (DSL2) compiler, `POST /api/pipelines/compile` + a Builder "Export to Nextflow" UI, and a Nextflow-first `scripts/run_giab_pipeline.py` intake driver. This makes ADR-0003's "Nextflow carries compute portability" decision executable, not aspirational, and retires the "not Nextflow" framing every prior doc carried since T-057. Pure doc-keeper work — no product code, tests, or fixtures touched. |
| **Participants** | doc-keeper subagent, invoked in SWEEP + AUTHOR mode |
| **Outcome** | Authored [design/nextflow-codegen.md](../design/nextflow-codegen.md); swept every doc the Doc-update map obligates plus two bonus drift fixes found while reading (`data-platform-and-archivist.md`'s "we run no nextflow" row + intro sentence). Every claim below is grounded by reading the actual code (`src/bayleaf/nextflow/{catalog,compiler,germline}.py`, `api/routers/nextflow.py`, `scripts/run_giab_pipeline.py`, `scripts/generate_reference_pipeline.py`, `pipelines/germline/`, `tests/test_nextflow_{compile,api}.py`) and running the offline suite + a fresh test census in this sandbox. |

## Discussion

### What landed in code (verified by reading, not the task description alone)

1. **`src/bayleaf/nextflow/`** — a pure-text compiler, confirmed to never shell out or import
   `subprocess` anywhere in `catalog.py`/`compiler.py`/`germline.py` (grepped). `catalog.py`'s
   `PROCESS_CATALOG` covers exactly 7 tools (fastp, bwa-mem2, samtools markdup, mosdepth,
   bcftools call, bcftools norm, MultiQC) — read every `ProcessSpec`'s `script:` and confirmed
   each is a verbatim lift of the corresponding command block that used to live directly in
   `scripts/run_giab_pipeline.py` (diffed the `8f9d527` commit, which deletes ~150 lines of direct
   tool invocation from that script in the same change these commands appear in the catalog).
   `compiler.py`'s `compile_graph()` does a Kahn topo-sort (`_topo_order`), builds channel
   expressions via `_input_channel()`, and renders four files. Read all 9 named tests in
   `tests/test_nextflow_compile.py` (offline) plus the 10th, machine-gated
   `test_generated_germline_stub_runs` — confirmed it `pytest.skip()`s (not fails) when `nextflow`
   isn't on `PATH`, verified in this sandbox (`which nextflow` → not found → the test collects but
   skips; `uv run pytest -q` here shows 422 passed / 5 skipped, one more skip than the maintainer's
   423/4 report, exactly accounted for by this one test).
2. **The reference-index staging tuple.** Read `INDEXED_REFERENCE_PARAMS = frozenset({"reference"})`
   and the corresponding branch in `_render_main()`: for that one param, the generated channel is
   `Channel.value([file(params.reference), file("${params.reference}.*")])` — a two-element tuple,
   not a bare file. Confirmed by the test assertion
   `ch_reference = Channel.value([file(params.reference), file("${params.reference}.*")])` in
   `test_germline_channel_wiring_matches_the_typed_ports`. This is the one genuinely subtle piece
   of the compiler — Nextflow stages only what a process explicitly declares, so a bwa-mem2/
   samtools/bcftools process needing a FASTA's `.fai`/`.bwt.2bit.64`/etc. sidecars would silently
   fail to find them without this glob-tuple staging trick.
3. **`POST /api/pipelines/compile`** (`api/routers/nextflow.py`) — read the whole 111-line router.
   Confirmed: stateless (no store import), the `CompileEdge` model aliases `from`→`src` because
   `from` is a Python keyword (`Field(alias="from")`, `populate_by_name=True` so both the wire
   name and the Python name work), a 422 on an empty-node-list graph before even attempting to
   compile, and `format=zip` streams a real in-memory `zipfile.ZipFile`. `api/main.py` registers
   it in a 2-line diff (`git show --stat be69d6b`) — no other endpoint touched.
4. **`scripts/run_giab_pipeline.py`** — read the full file (274 lines, was ~370 before `8f9d527`
   per `git show --stat 8f9d527` showing 237 lines changed with a large net deletion). Confirmed
   `run_nextflow()` is the only thing that touches a subprocess for tool execution — it calls
   `subprocess.run([nextflow, "run", str(_PIPELINE), ...], check=True, ...)` where `_PIPELINE =
   _REPO / "pipelines" / "germline" / "main.nf"` — literally the committed reference pipeline, not
   a copy. The QC-parsing functions (`parse_fastp`, `parse_mosdepth`, `count_variants`) are
   unchanged from before — they read the SAME published file shapes (`*.fastp.json`,
   `*.mosdepth.summary.txt`/`*.thresholds.bed.gz`, `*.norm.vcf.gz`), just now from Nextflow's
   `publishDir` rather than from hand-invoked tools writing to a flat work directory. `write_run_dir`
   (the frozen-five CSV writer) and the final `run_gate_from_dir()` call are byte-identical to
   before — confirmed by re-reading against the pre-change description in
   [journal 2026-07-09-giab-e2e-pipeline.md](2026-07-09-giab-e2e-pipeline.md).
5. **`api/routers/intake.py`** changed by 11 lines (`git show --stat e4ba174`) — read the diff:
   only the module docstring and one small helper's docstring were updated to describe the
   Nextflow-first driver; the endpoint's own contract (job registry, `require_role`, 409-on-dup,
   `HG002`-fixture scope, polling states) is untouched. Confirmed no new query param, no new
   response field.
6. **Frontend.** `git show --stat be69d6b -- frontend/` touched exactly `api.ts` (+15),
   `BuilderModals.tsx` (+147, `NextflowExportModal`), `PipelineBuilder.tsx` (+34, the toolbar
   button + modal wiring), `types.ts` (+16). No other screen touched.
7. **No core contract change.** `git show --stat 10f1816 be69d6b 8f9d527 e4ba174` across all four
   commits touches zero files in `models.py`, `parsers.py`, `persistence/`, `runbook.py`,
   `rules.py`, `metrics/`, or `provenance.py` — confirmed by grepping the combined diff stat for
   those paths (empty). This is why `data/schemas.md`, `data/qc_metrics.md`,
   `data/metric_registry.md`, and `data/provenance.md`'s event vocabulary are **not** owed by this
   change (see "What I deliberately did not touch" below).

### Test census, re-derived in this sandbox

`uv run pytest --collect-only -q` → **427 tests collected** (was 413). `git ls-files 'tests/*.py' |
wc -l` → **29** (was 27; the two new files are `test_nextflow_compile.py` and
`test_nextflow_api.py`). `which nextflow` → not found in this sandbox, so `uv run pytest -q` here
gives **422 passed / 5 skipped** (the live `-stub-run` check is the fifth skip, joining the 4
Postgres-live skips). The task's own report of **423 passed / 4 skipped** describes a run on the
maintainer's `hackathon` conda env where `nextflow` IS on `PATH` — both numbers are honest
descriptions of the same 427-test suite under different environments, and I've recorded both
rather than picking one, per the evaluation doc's own "tie claims to verification" habit.

### Doc-update map sweep

Walked [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map) against the
four commits' actual file diffs (not just the task description):

1. **⚪ decision made/realized → an ADR.** Judged this REALIZES [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)'s
   existing "compute portability is delegated to Nextflow" decision rather than making a new
   load-bearing choice — no new ADR. Added a new "Realized (2026-07-11)" section, bumped the
   Status/Date fields, and marked the 2026-07-09 section's "bioconda-toolchain driver, not
   Nextflow" line as historically-accurate-but-superseded (didn't rewrite it in place — it was
   true when written, mirroring the "journal is the archive, never rewritten" convention applied
   to a dated ADR sub-section).
2. **🟠 `api/` endpoint or `frontend/` screen — new/changed capability → `architecture.md` +
   `data-platform-and-archivist.md` + `functional.md`.** All three updated: architecture.md gets a
   new `nextflow` bullet under Core (item 1), a new dated paragraph in the frontend chronicle
   (item 4), an updated Deployment section + two new Swappable-seams rows. functional.md gets a
   new REQ-F-085 (the compiler + compile endpoint + Builder export) and an addendum to REQ-F-067
   (the intake driver is now Nextflow-first) plus a new Notes/deferred item (9) naming the
   curated-catalog + local-only limitations. data-platform-and-archivist.md's stale "we run no
   nextflow" Appendix-C row and its intro sentence's "standalone bioconda driver" phrasing were
   fixed (found while grounding claims in code, not originally itemized in the task list — see
   "bonus fixes" below).
3. **🔴 new tests → `quality/evaluation.md`.** Recounted per the method above; added **EVAL-006**
   (the compiler's deterministic wiring + drift guard + honest-placeholder + the machine-gated
   live `-stub-run` check) in the Deterministic-cases group (after EVAL-005, before the
   Failure-mode section) since the compiler is a pure function like the metric registry, not a
   failure-mode/faithfulness/notify/de-id case. Rewrote the census paragraph with the per-file
   breakdown for `test_nextflow_compile`/`test_nextflow_api`, and reported both pass/skip
   possibilities honestly (see above) rather than picking one number and hiding the environment
   dependency.
4. **⚪ scope/wishlist changes → `scope-and-wishlist.md`.** Fixed three stale "not a Nextflow
   hand-off" claims: item #4 (pipeline-repair)'s parenthetical, item #9 (no-code runner)'s "one
   hard-coded script, not a schema-driven form-to-any-pipeline path" line, and added a new
   "Export to Nextflow" paragraph to item #11 (visual pipeline builder) documenting the capability
   addition alongside the pre-existing `Emit`/`run_layout.yaml` action.
5. **⚪ `CLAUDE.md` code map (module added / a map trigger needs updating).** New `nextflow`
   bullet under Core (item 1); extended item 4's intake-boundary description with the Nextflow-
   first update + the new compile endpoint; appended a full dated paragraph at the tail of the
   code map (matching every prior "Wave N"/"Batch N" entry's format) summarizing all three pieces,
   the live-run evidence, and the honesty framing, with a docs-swept list + this journal link.
6. **🔴 task status → `tasks.md`.** New row **T-123** (the highest existing id was T-122, from an
   unrelated same-day session — checked via `grep -oE "T-1[0-9]{2}"` before picking a number, since
   guessing T-121 collided with an already-used id from a prior session's UIC-16 closer). Also
   added a small superseded-note to T-063's own historical row (the "standalone bioconda-toolchain
   driver" phrase), matching the same non-rewrite-in-place convention as the ADR fix above.
7. **🔴 doc create/move → `TABLE_OF_CONTENTS.md`.** New row for
   [design/nextflow-codegen.md](../design/nextflow-codegen.md) under the Design table.
8. **🟠 `data/nf-core-conventions.md`.** Not explicitly a map row (no trigger for "a design doc's
   vocabulary now feeds a real generator"), but the task named it directly and it was genuinely
   stale in spirit (its package/module conventions section described someone else's convention,
   not something this repo generates) — added an "Update (2026-07-11)" paragraph under Framing
   plus a Related-field crosslink.

### AUTHOR: `docs/design/nextflow-codegen.md`

Followed `docs/_templates/doc.md`'s metadata-table convention (Status/Last-updated/Audience/
Related), extended with domain-specific sections since a flat template didn't fit a compiler this
detailed — mirrored the shape [node-authoring-agent.md](../design/node-authoring-agent.md) uses
(a built-status header, then component map → mechanism → honesty framing → tests → limitations).
Crosslinked ADR-0001, ADR-0003 (with a direct pointer to its new Realized section),
architecture.md, nf-core-conventions.md, the builder-cards/ per-tool specs, and this journal.
Every claim in it traces to a specific file/test I read (listed in its own "Verified by reading
the code directly" line) or to the live-run evidence the task description supplied, which I
treated as a **Fact** reported by the maintainer rather than independently re-run (no `nextflow`
binary available in this sandbox — see the census section above for how that's handled honestly).

### Bonus fixes found while grounding claims in code (not in the task's explicit list)

- **`data-platform-and-archivist.md` Appendix C row 10** ("Pipeline provenance"): said "**FULL**
  (we run no nextflow; parser reads none)" — directly contradicted by `run_giab_pipeline.py` now
  running `nextflow run` for real. Fixed to explain the more precise (and more interesting) current
  truth: Nextflow now executes, but nothing in the repo requests/parses its `pipeline_info/`
  manifest — the driver still hand-parses each process's own published QC file. This is a
  **better**, not just different, honesty story than either "FULL, we don't run it" or a naive
  "now built" would have been, so it was worth the extra sentence.
- **The same doc's Appendix-C intro sentence** ("...as a standalone bioconda driver outside the
  app") — fixed with an inline "Update (2026-07-11)" note rather than deleting the historical
  framing, since the surrounding sentence is itself a dated correction of an even earlier
  (2026-07-08) claim — preserving that chain of corrections seemed more honest than flattening it.

### What I deliberately did not touch

- **`docs/data/schemas.md` / `docs/data/qc_metrics.md` / `docs/data/metric_registry.md`.** No
  field, `our_key`, threshold, or `schema_version` changed — confirmed by the empty diff-stat
  intersection with `models.py`/`parsers.py`/`runbook.py`/`rules.py`/`metrics/` above. Waiving the
  🔴 "models.py / parsers.py / persistence — new/renamed field" and the 🟠 "runbook.py or
  rules.py — a threshold, a metric" map rows: neither fired.
- **`docs/data/provenance.md`.** No `EventType`, ledger format, or `provenance.py` change (grepped
  the four commits' diff stat for `provenance.py`: no hits). Waiving the 🟠 "`provenance.py` /
  `engine.py`, the `EventType` vocabulary" row.
- **`docs/design/agents.md`.** No agent, model tier, or corpus changed — the compiler is a
  deterministic codegen module, not an advisory-agent seam (it has no LLM path at all, unlike the
  six `stub|claude` agents this row governs). Waiving the 🟠 "a new advisory agent" row.
- **`.env.example` / `pyproject.toml`.** Confirmed via `git show --stat` across all four commits:
  neither file touched. No new documented env var (the test-only `BAYLEAF_NEXTFLOW_BIN` override
  in `test_nextflow_compile.py` is a test convenience, not a documented product knob) and no new
  Python dependency (Nextflow is external tooling on `PATH`, not a `uv` package) — so
  `data/licensing.md` and `requirements/constraints.md` are not owed either.
- **`docs/demo/demo_plan.md` / `docs/demo/run-of-show.md`.** demo_plan.md's existing "Nextflow for
  compute portability" talking point is a forward-looking claim that is now *more* true, not
  contradicted — left as-is rather than expanded, since the task didn't ask for a new demo beat
  and adding one is a product decision for the maintainer, not a doc-drift fix.
- **`docs/design/agents.md`, `docs/quality/risks.md`, `README.md`.** Grepped all three for
  `Nextflow`/`nextflow`/`bioconda`: no hits in risks.md or README.md; agents.md's hits are
  unrelated (agent roster, not pipeline execution). Nothing to fix.

## Decisions

| Decision | Distilled to |
|---|---|
| This landing REALIZES ADR-0003's existing "Nextflow carries compute portability" decision — it does not introduce a new load-bearing choice, so no new ADR is warranted; extend ADR-0003 with a new dated Realized section instead. | [docs/adr/ADR-0003-deployment-agnostic-ports.md](../adr/ADR-0003-deployment-agnostic-ports.md) |
| The reference-FASTA sidecar-index staging (`INDEXED_REFERENCE_PARAMS`, a `[file(x), file("x.*")]` tuple channel) is the one genuinely non-obvious wiring rule in the compiler — document it explicitly rather than leaving it implicit in the code, since a future contributor adding a second indexed-reference kind would need to know the pattern exists. | [docs/design/nextflow-codegen.md](../design/nextflow-codegen.md) §Wiring rules point 4 |
| An uncatalogued tool compiling to a labelled, loudly-failing placeholder (never a fabricated command) is the load-bearing honesty guarantee of this whole subsystem — called out explicitly in every doc that describes the compiler (design doc, ADR-0003, functional.md, CLAUDE.md, tasks.md) rather than left as an implementation detail, so "any card runs" can never be misread as the claim. | [docs/design/nextflow-codegen.md](../design/nextflow-codegen.md), [docs/requirements/functional.md](../requirements/functional.md) REQ-F-085 |

## Open questions & TODO

- The offline suite's pass/skip count is now environment-dependent (`nextflow` on `PATH` or not).
  This is the same pattern the Postgres-live tests already established, so no new documentation
  convention was needed — but it's worth noting for a future session that `evaluation.md`'s census
  paragraph now has to state two numbers, not one, and should keep doing so as more machine-gated
  live checks accrue.
- `docs/quality/evaluation.md`'s "What we do *not* claim" item 4 still cites a stale "362-test
  count" from an even earlier (2026-07-09) session — noticed while reading the file for this
  sweep, left untouched (out of scope for this task; it's a dated historical note about a specific
  prior commit range, not a claim this session's change falsifies).
- Slurm/AWS-Batch/HealthOmics executor config for the generated pipeline remains the one
  genuinely open piece of ADR-0003's original compute-portability decision — tracked explicitly in
  the new design doc's Limitations section and the ADR's "Revisit when" list, not silently implied
  as done.

## Distilled into

- [docs/design/nextflow-codegen.md](../design/nextflow-codegen.md) — new design doc (AUTHOR)
- [docs/adr/ADR-0003-deployment-agnostic-ports.md](../adr/ADR-0003-deployment-agnostic-ports.md) — new Realized (2026-07-11) section, Status/Date/Related bumped, the 2026-07-09 line marked superseded
- [docs/design/architecture.md](../design/architecture.md) — new `nextflow` bullet (Core), a new dated frontend-chronicle paragraph, Deployment section + Swappable-seams table updated, Related field
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — Appendix-C row 10 + intro sentence fixed, Related field
- [docs/data/nf-core-conventions.md](../data/nf-core-conventions.md) — Framing section update, Related field
- [docs/requirements/functional.md](../requirements/functional.md) — new REQ-F-085, REQ-F-067 addendum, new Notes/deferred item 9, Related field
- [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) — REQ-NF-060 addendum, Related field
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — items #4/#9/#11 corrected, Related field
- [docs/quality/evaluation.md](../quality/evaluation.md) — new EVAL-006, census refreshed (427/29, 423 pass/4 skip with nextflow, 422/5 without), Related field
- [docs/planning/tasks.md](../planning/tasks.md) — new T-123, T-063's row annotated superseded
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — new design-doc row
- [CLAUDE.md](../../CLAUDE.md) — new `nextflow` bullet (Core), intake-boundary update, new dated code-map paragraph
