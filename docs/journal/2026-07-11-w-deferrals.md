# Journal — 2026-07-11 (MST) — W3/W4 deferred-slice continuations + doc sweep

| Field | Value |
|---|---|
| **Focus** | Close two named deferrals left open by earlier same-day work: T-128's (W3) "no per-variant evidence table" gap, and T-129's (W4) "a true multi-sample driver run … stays deferred" gap — then sweep every doc the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) obligates. |
| **Participants** | James Hu, Claude Code (doc-keeper subagent for the sweep) |
| **Outcome** | Both commits (`fec0f83`, `9ab7fca`) landed on `main` before this session started; this session is the SWEEP + AUTHOR + CHK pass over them — no code changed here, only docs. Both slices are honestly narrower than their parent tasks' full scope: the per-variant table ships ClinVar-only fields (no gnomAD/inheritance-fit); the multi-sample parse is offline-proven only, the live multi-sample Nextflow run remains unverified. |

## Discussion

### W3 continuation — per-variant Report table (`fec0f83`)

T-128 (earlier the same day) shipped `RunReport.tsx`'s Report tab entirely over data already on
the wire (`detail.cards`/`detail.events`) — deliberately the smallest slice ("option A" in the
audit's `w3.md` panel), explicitly leaving "no per-variant evidence table" as an open item because
no endpoint served `VariantCall` rows at all (confirmed at the time: `api/report.py` did not
exist).

This commit closes that specific gap, narrowly: a new `GET /api/runs/{run_id}/variants`
(`api/main.py`) reuses `pipeguard.parsers.parse_variant_calls` — the SAME parser
`rules._check_route_to_human` (VAR-RTH-001) already calls — so there is no new parsing logic, only
a new read surface over an existing one. Read pattern matches `get_run`/`get_card`: 404 for an
unknown run id, `[]` (not a 404) for a run with no `variants.csv`. No `require_role` — this is a
read, like every other run-detail GET.

Grounded by reading the diff directly (`git show fec0f83`): the endpoint is 15 lines including its
docstring; `RunReport.tsx` adds a `useEffect` fetch + a paginated table (`VariantRow`) rendering
`clinvar_significance` in quotes, explicitly labelled VERBATIM in a code comment
("`// VERBATIM — the cited source's value, rendered unmodified (G3/G4).`"); the empty state reads
"Variant annotation is an externally-produced input PipeGuard READS (ADR-0018), never runs." The
3 new tests (`tests/test_run_variants.py`) assert the CLINVAR-RTH fixture's exact fields verbatim,
an empty list (not 404) for `mock_run_01`, and a 404 for an unknown run id — matching the honesty
framing exactly.

What this is NOT: the full `AnnotatedVariant` model (§1 item 1 of
[variant-interpretation.md](../design/variant-interpretation.md)) with gnomAD population
frequency, inheritance-fit, and a call-quality join. The table is unconditional on the
route-to-human rule firing — any row in `variants.csv` shows, whether or not it is armed against
the policy — which is a genuinely new (if narrow) capability the hero panel above it doesn't have
(the hero shows only a *fired* route-to-human hit).

### W4 continuation — multi-sample driver parse (`9ab7fca`)

T-129 (also earlier the same day) added per-sample fan-out at the **compiler/pipeline level**
(every catalogued Nextflow process carries the nf-core `[meta, files]` map) but explicitly left
the driver's **parse** single-sample: "a true multi-sample driver run (parsing N result dirs into
N run dirs) stays deferred."

This commit closes the PARSE half only, offline: `discover_samples()` finds every sample from its
`${id}.fastp.json`; `_one_for()` (renamed from `_one()`) anchors its glob match with a dot prefix
(`glob.escape(sample) + "."`) so `S1` can never match `S10`'s files; `parse_publish_dir()` parses
each into a `SampleMetrics`; `write_run_dir_multi()` writes ONE run dir with N rows across every
frozen-five CSV — verified by reading `scripts/run_giab_pipeline.py`'s diff directly, and cross-
checked against `data/mock_run_01`'s existing 5-sample flat-CSV shape (same contract, no schema
change). A fan-out of 1 is pinned byte-identical to the pre-fan-out format
(`test_single_sample_run_dir_is_byte_identical_to_pre_fanout_format`).

The commit body is explicit, and the 7 new tests
(`tests/test_run_giab_multisample.py`) prove exactly this and nothing more: partial/empty publish
dirs fail loud (`SystemExit`), N-sample fixture dirs parse to N gated cards via the unchanged
`run_gate_from_dir`, and `S1`/`S10` never cross-capture. All of this is against **hand-built
fixture publish dirs** — no Nextflow, no bioconda tools, no network. The LIVE driver
(`run_nextflow()`) is UNCHANGED by this commit: it still writes a single-row samplesheet
(`f"sample,fastq_1,fastq_2\n{cfg.sample},{cfg.read1},{cfg.read2}\n"`), because only HG002 has real
panel reads on disk in this sandbox. This is the honest deferral the commit message states
verbatim: "the live MULTI-SAMPLE Nextflow run is unverified."

`api/routers/intake.py` gets an additive `IntakeStatus.samples: list[SampleStatus]` (per-sample
`queued|running|complete|failed|lost|skipped`), mirroring run-level transitions onto every
`processed` sample via a new `_mirror_samples()` helper while leaving a `skipped` sample frozen.
Confirmed additive by reading the diff: an older persisted job with no `samples` key still
deserializes (`job.get("samples", [])` → `[]`).

### Doc sweep

Walked the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) against both commits:

1. **🟠 api/ endpoint or frontend/ screen — new/changed capability** fired for the `/variants`
   endpoint and `RunReport.tsx` → updated `design/architecture.md` (Runs read-API bullet + a new
   history bullet), `design/data-platform-and-archivist.md` (§3.2.2 addendum),
   `requirements/functional.md` (new REQ-F-094).
2. **⚪ Load-bearing decision made or realized** — no NEW decision here (both slices are
   continuations of ADR-0018 D2's already-decided boundary and ADR-0003's already-decided Nextflow
   direction, not a new tradeoff), but both ADRs' own **Realized** sections needed a new dated item
   since they name concrete artifacts the reader would otherwise have to reverse-engineer from the
   commit log → `ADR-0018` (new Realized item 5), `ADR-0003` (Realized §3 narrowed + a new Date
   entry).
3. **🔴 Add/remove/rename a test, or define an EVAL case** fired hard — 10 new tests across 2 new
   files → recounted the census with `uv run pytest --collect-only -q` (517 collected) +
   `git ls-files 'tests/*.py' | wc -l` (37) + `uv run pytest -q` (511 passed / 6 skipped, this
   sandbox has no `nextflow`) and updated `quality/evaluation.md`'s hardcoded count, added
   EVAL-009 (multi-sample parse) and EVAL-013 (variants endpoint), and added a fifth "what we do
   not yet verify" item for the live multi-sample run.
4. **🔴 A task changes status or is created** → `planning/tasks.md` T-133 (W3 continuation) +
   T-134 (W4 continuation), both `done` (the commits already landed), depending on T-128/T-129
   respectively.
5. **🔴 `src/pipeguard/models.py`/`parsers.py`/`persistence/`** did NOT fire — `VariantCall` was
   already a full core model (no field added), and the driver/API changes are outside
   `src/pipeguard/` entirely (a script + an `api/routers/` file). `data/schemas.md` was still
   touched, but for a narrower reason: it documents API-level pydantic shapes too (it already
   documented `IntakeStatus`), so the additive `SampleStatus`/`IntakeStatus.samples` field and the
   new `/variants` wire projection both earned a note there, under the existing
   "execution-job bookkeeping is API-layer, not a core record" item and the existing `VariantCall`
   block, respectively — not a new top-level record.
6. **🔴 Doc/status change** → `TABLE_OF_CONTENTS.md` (`design/variant-interpretation.md`'s row —
   "two pieces" → "four pieces," naming the new ones; `design/nextflow-codegen.md`'s row — the
   parse-vs-run distinction).
7. `requirements/nonfunctional.md` — added REQ-NF-045 (multi-sample publish-dir parse fails loud),
   parallel to the existing REQ-NF-041 (tolerant parsing) / REQ-NF-044 (preflight fails loud)
   pattern this repo already uses for "a bad input must fail loud, not silently proceed."

**Waived, with the specific map row named:**

- **`requirements/scope-and-wishlist.md`** (map row: "Scope / wishlist / 'built' changes") —
  checked (`grep -n "T-128\|T-129\|w3.md\|w4.md" requirements/scope-and-wishlist.md`, zero hits):
  neither W3 nor W4 is tracked as its own wishlist row there (they are audit-track deliverables
  feeding `tasks.md` directly, not wishlist items #1–#20); wishlist #11's Pipeline Builder row
  already covers the Nextflow-compiler capability at the right grain. Nothing to correct.
- **`data/qc_metrics.md` / `data/provenance.md` / `data/metric_registry.md`** (map rows for
  `runbook.py`/`rules.py`/`metrics/` changes) — neither commit touches a threshold, a gate
  assignment, the metric registry, or the `EventType` vocabulary; the route-to-human rule and its
  QC-metrics documentation are unchanged by this session.
- **`design/agents.md`** (map row: a new advisory agent) — no new agent; `/variants` is a plain
  read endpoint, not an agent surface.
- **`CLAUDE.md`'s code map** — explicitly caller-owned per the task brief; not touched here.

## Decisions

No new load-bearing decision was made this session — both commits are narrow, planned
continuations of already-decided boundaries (ADR-0018 D2's route-to-human/report scope; ADR-0003's
Nextflow compute-portability direction). Both ADRs' Realized sections were extended with a new
dated item rather than a new Decision row, per the existing pattern this repo uses for "the
decision didn't change, but a new artifact now realizes more of it."

| Decision | Distilled to |
|---|---|
| (none — continuation work under already-accepted ADR-0018/ADR-0003 decisions) | n/a |

## Open questions & TODO

- The live multi-sample Nextflow run (an N-row samplesheet, real second-sample reads, a real
  Nextflow fan-out, the parse above run against Nextflow's REAL published output) is unbuilt and
  unscheduled — it needs a second real GIAB (or synthetic) sample's panel reads on disk, which
  this sandbox does not have.
- The full `AnnotatedVariant` evidence join (gnomAD AF, inheritance-fit, call-quality) stays
  design-only, per [variant-interpretation.md §0](../design/variant-interpretation.md).
- `requirements/scope-and-wishlist.md`, `design/agents.md`, `data/qc_metrics.md`,
  `data/provenance.md`, `data/metric_registry.md` were checked and waived (see above) — no action
  needed unless a future session actually touches those areas.

## Distilled into

- [design/variant-interpretation.md](../design/variant-interpretation.md) — §0 items 4/5
  renumbered + rewritten, §5 phasing item 2 addendum, top metadata.
- [adr/ADR-0018-variant-interpretation-advisory-evidence.md](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) — new Realized item 5, item 6 renumbered, top metadata.
- [design/nextflow-codegen.md](../design/nextflow-codegen.md) — new §Multi-sample driver parse,
  Limitations item 4 narrowed, Tests/verification table + census, top metadata.
- [design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new §3.2.2.
- [adr/ADR-0003-deployment-agnostic-ports.md](../adr/ADR-0003-deployment-agnostic-ports.md) —
  Realized §3 item narrowed, top metadata.
- [requirements/functional.md](../requirements/functional.md) — new REQ-F-094, REQ-F-095;
  REQ-F-090 body + Notes item 9 narrowed.
- [requirements/nonfunctional.md](../requirements/nonfunctional.md) — new REQ-NF-045.
- [data/schemas.md](../data/schemas.md) — `SampleStatus`/`IntakeStatus.samples` addition, the
  `/variants` wire projection noted against the existing `VariantCall` block.
- [design/architecture.md](../design/architecture.md) — Runs read-API bullet, Intake execution
  driver table row, a new history bullet.
- [quality/evaluation.md](../quality/evaluation.md) — census refreshed to 517/37, 511 pass/6 skip;
  new EVAL-009, EVAL-013; a fifth "what we do not yet verify" item.
- [planning/tasks.md](../planning/tasks.md) — new T-133, T-134 rows; top metadata.
- [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — `design/variant-interpretation.md` and
  `design/nextflow-codegen.md` row descriptions; top metadata.
