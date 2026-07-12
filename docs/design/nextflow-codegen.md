# Nextflow Codegen — compiling a Builder card graph into a runnable pipeline

| Field | Value |
|---|---|
| **Status** | Built (T-123) and extended: executor profiles + per-sample fan-out + full QC port wiring (W4), pre-flight guards + per-run version capture (T-131), N-sample driver parse (W4 continuation — offline-verified vs fixture publish dirs; the live multi-sample run stays unverified, §Multi-sample driver parse), operator-authored custom-script processes (ADR-0020), robustness hardening (injection escaping + collision/fan-in/dup-emit/port-drift guards, §Robustness hardening), the reserved-port honesty model (2026-07-12: every shown port is a real channel or removed — promoted 6 kinds incl. the mosdepth byproducts that had 422'd Export-to-Nextflow, removed 7 non-real, one `adapter_fasta` left reserved; see §The catalog), and operator-gated/authored-pipeline intake (ADR-0021, §Nextflow-first intake). Build chronology in [HISTORY.md](../HISTORY.md). |
| **Last updated** | 2026-07-12 (MST) |
| **Audience** | software / bioinformatics |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide, AI advisory — this module sets no verdict), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (deployment-agnostic ports; this doc REALIZES its "Nextflow carries compute portability" decision), [ADR-0016](../adr/ADR-0016-postgres-port.md) (the durable job store the intake driver's launch now persists into, item 8), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md) (operator-authored custom-script processes — the compile path in §Operator-authored custom-script processes below), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md) (operator-gated/scheduled intake processing of approved authored pipelines — §Nextflow-first intake below), [design/agent-authoring-contract.md](agent-authoring-contract.md) (agents author metadata, a human authors the custom script), [design/architecture.md](architecture.md) (component map), [data/nf-core-conventions.md](../data/nf-core-conventions.md) (the vocabulary this catalog adopts), [design/frontend/pipeline-builder-brief.md](frontend/pipeline-builder-brief.md) (the card graph this compiles), [design/builder-cards/](builder-cards/) (the per-tool port specs the catalog mirrors), [planning/tasks.md](../planning/tasks.md) (T-123, T-129, T-131, T-134), [journal 2026-07-11](../journal/2026-07-11-nextflow-codegen-execution.md), [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md), [journal 2026-07-11 w-deferrals](../journal/2026-07-11-w-deferrals.md) |

## Overview

`src/pipeguard/nextflow/` compiles a Pipeline-Builder card graph — the exact `{nodes, edges}`
shape the Builder saves — into a runnable nf-core-style Nextflow (DSL2) pipeline: `main.nf` +
`modules/*.nf` + `nextflow.config` + a `README.md`. It is **pure text codegen**: the compiler
never invokes `nextflow`, never touches a file outside its own in-memory output, and never sets a
verdict — compose ≠ execute holds at the core (ADR-0001/ADR-0003). Two things consume it: an API
compile endpoint feeding the Builder's "Export to Nextflow" UI, and the intake driver
(`scripts/run_giab_pipeline.py`), which now runs the SAME generated pipeline for real.

This makes ADR-0003's "compute portability is delegated to Nextflow" decision **executable, not
aspirational** — every prior doc that said the intake driver was "a bioconda-toolchain driver, not
Nextflow" is now stale; see the "Realized (2026-07-11)" section of
[ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md).

## The one job

Given a typed card graph (a tool name per node + ordered input/output artifact-kind ports +
edges wiring a specific output port to a specific input port — the Pipeline Builder's own data
model, [pipeline-builder-brief.md](frontend/pipeline-builder-brief.md)), produce a **runnable**
Nextflow DSL2 bundle whose channel wiring matches the graph exactly. Nothing here decides
anything: it is a deterministic function `graph → bundle`, same input always yields the same
text (verified by the drift test below).

## Component map

| Module | Job |
|---|---|
| `catalog.py` | The tool → `ProcessSpec` table: process name, bioconda + biocontainer packaging, typed `Port`s, a real `script:`, a `stub:`. The single source of truth for "how does this Builder card become a Nextflow process." |
| `compiler.py` | `compile_graph(NfGraph) -> NextflowBundle`. Kahn topological sort, channel-wiring rules (below), aliasing, rendering of `main.nf`/`modules/*.nf`/`nextflow.config`/`README.md`. |
| `germline.py` | The seeded germline chain expressed as compiler input (`germline_graph()`) — mirrors the Builder's own seeded template so the two can never silently diverge (see the drift guard below). |
| `pipelines/germline/` (repo root, not under `src/`) | The **committed reference pipeline** — exactly `compile_graph(germline_graph())`'s output, regenerated by `scripts/generate_reference_pipeline.py`. |
| `api/routers/nextflow.py` | `POST /api/pipelines/compile` — a stateless, off-gate HTTP wrapper around `compile_graph()`. |
| `frontend/src/components/BuilderModals.tsx` (`NextflowExportModal`) | The Builder's "Export to Nextflow" UI: compiles the live canvas graph, previews `main.nf` + the step chain, Copy / Download `.zip`. |
| `scripts/run_giab_pipeline.py` | The intake execution driver — now runs `pipelines/germline/main.nf` via `nextflow run` instead of calling tools directly (below). |

**Verified by reading the code directly**: `src/pipeguard/nextflow/catalog.py`,
`src/pipeguard/nextflow/compiler.py`, `src/pipeguard/nextflow/germline.py`,
`api/routers/nextflow.py`, `scripts/run_giab_pipeline.py`, `scripts/generate_reference_pipeline.py`,
`pipelines/germline/{main.nf,modules/*.nf,nextflow.config,README.md}`,
`tests/test_nextflow_compile.py`, `tests/test_nextflow_api.py`.

## The catalog (`catalog.py`)

`ProcessSpec` is one tool card's Nextflow process: identity (`tool`, `process`), packaging
(`conda` — a bioconda spec; `container` — a biocontainer image, the nf-core convention of
carrying both so either profile runs), typed `Port`s for inputs/outputs (keyed by the **same
artifact-kind vocabulary the Pipeline Builder uses**, e.g. `fastq`, `bam`, `mosdepth_summary`, so
the compiler can wire channels straight from the graph's typed edges with no translation layer),
a faithful `script:` block (lifted verbatim from the working bioconda commands
`scripts/run_giab_pipeline.py` used to run directly — see [Nextflow-first intake](#nextflow-first-intake)
below), and a `stub:` block that just `touch`es the declared outputs so `nextflow run -stub-run`
validates the whole DAG's wiring with no tools or data present.

The catalog covers the **germline-panel chain this repo actually runs**: `fastp`, `bwa-mem2`,
`samtools markdup`, `mosdepth`, `bcftools call`, `bcftools norm`, `MultiQC` — 7 processes.
`REFERENCE_PARAM` maps the three no-input reference kinds (`reference_fasta`, `panel_bed`,
`truth_vcf`) to their `nextflow.config` params, and `INDEXED_REFERENCE_PARAMS = {"reference"}`
flags that a reference FASTA's sidecar index (`.fai`, `.bwt.2bit.64`, …) must be staged alongside
it — Nextflow otherwise stages only the single declared file (see below).

**Full QC port wiring — every shown port is a real channel or removed (W4 → reserved-port
promotion, 2026-07-12).** The catalog holds no dangling reserved output: every output a Builder
card shows maps to a real published Nextflow channel, or the port was removed as non-real. `fastp`
publishes `fastp_html` (the report it already writes via `-h`) and — after the promotion pass —
`unpaired_fastq`/`failed_fastq` (the `--unpaired1/2` / `--failed_out` products); `samtools markdup`
runs an added `samtools stats` on the dedup BAM and publishes `samtools_stats`; `bcftools norm`
publishes `vcf_index` (the `.csi` its existing `bcftools index -f` step already writes); `MultiQC`
publishes `multiqc_html` (the report `multiqc .` always writes). `mosdepth` publishes
`mosdepth_summary`/`mosdepth_thresholds` **and** the three remaining byproducts of the same
`mosdepth --by … --thresholds` command — `mosdepth_regions`/`mosdepth_global_dist`/
`mosdepth_region_dist` (added to `catalog.py` 2026-07-12): the frontend Builder card advertised all
five while the catalog declared only two, and that arity gap tripped the compiler's output-drift
guard and **422'd Export-to-Nextflow of the default Builder view** — declaring the three real
byproducts closed it. `MultiQC` (the aggregator) ingests **all 5** available QC streams
(`fastp_json`, `markdup_metrics`, `samtools_stats`, `mosdepth_summary`, `mosdepth_thresholds`),
each `.map { it[1] }.collect()`'d across every sample before it scans them.

**Promoted / removed / left-reserved — the reserved-port honesty model (2026-07-12,
`tests/test_nextflow_promoted_ports.py`, 5 cases).** The rule the pass enforces: **every shown port
is a real channel or it is removed — no superficial slots.** Each catalog change is mirrored in the
frontend's `BuilderShared.tsx` (`BTOOLSPEC`/`CARD_PORTS`/`ARTIFACT_KINDS`) in the same landing, and
`builder-cards/README.md §5` is the frontend-facing authority:

1. **Promoted → real published channels:** `fastp_html`, `samtools_stats`,
   `mosdepth_regions`/`mosdepth_global_dist`/`mosdepth_region_dist`, `fastp` `unpaired_fastq`/
   `failed_fastq`, `bcftools norm` `vcf_index`, `MultiQC` `multiqc_html` — each is a genuine product
   of the tool's existing command (an added flag or an index step it already ran), not a fabricated
   emit. `fastp_html`/`samtools_stats` are additionally in `node_author.models.ARTIFACT_KINDS`
   (T-130) so a proposed node's port for those kinds reads `known`, not `reserved`.
2. **Removed as non-real** (a Builder port wires a file channel, so none of these could ever carry a
   real wire — dropped rather than left as superficial slots): `bwa-mem2` `read_group` (a computed
   `@RG` STRING, not a file artifact), `mosdepth` `per_base` (suppressed by the command's
   `--no-per-base`), `bcftools norm` `panel_bed` (norm is genome-wide — the maintainer's I/O
   correction took it off norm), and `MultiQC` `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/
   `ngscheckmate` (no tool in the catalogued germline chain produces them, and MultiQC's inputs are
   fixed by its `ProcessSpec`, so the input-drift guard would reject them anyway).
3. **Left honestly reserved — one kind, `fastp` `adapter_fasta`:** a real optional `--adapter_fasta`
   file input, but the compiler's input-drift guard is exact + positional, so adding it to the
   catalog would force EVERY fastp node (incl. the seeded golden chain) to wire an adapter source —
   too invasive for this pass, so it stays a non-armable reserved slot with a Connect-mode tooltip.
   It is the only port that renders reserved anywhere now — see
   [builder-cards/README.md §5](builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11).

**Honesty framing — the catalog is curated, not universal.** This is deliberate, not a
shortcut left for later: the module docstring says it plainly — "The catalog is deliberately
small and curated (this pipeline's real germline chain). It is NOT a claim that any card is
runnable." A tool card outside the catalog (any of this repo's other Builder palette entries, or
a future node-authoring-agent proposal) still compiles — the compiler never refuses a graph for
having an uncatalogued node — but its module is a **labelled placeholder**, not a fabricated
command (see [Wiring rules](#wiring-rules) point 5).

## Wiring rules (`compiler.py`)

`compile_graph(NfGraph) -> NextflowBundle` implements these rules, each pinned by a named test in
`tests/test_nextflow_compile.py`:

1. **An input port fed by an edge draws `<UPSTREAM_CALL>.out.<kind>`.** The edge's
   `{from:{node,idx}, to:{node,idx}}` shape (identical to what the Builder saves) resolves to the
   upstream node's Nextflow call name + its output port's `emit:` channel name.
2. **An unwired input is a pipeline source.** `fastq` with no incoming edge becomes the
   `ch_reads` value channel (`params.read1`/`params.read2`); a reference kind (`reference_fasta` →
   `params.reference`, etc.) becomes its own `ch_<param>` channel. This is what lets a Builder
   graph with dangling reference inputs (the normal, expected shape — references are supplied at
   run time, not wired from another tool) still compile.
3. **A source node (no inputs, only reference-kind outputs) is not a process.** It maps straight
   to the same params channel an unwired reference input would use — a "Reference FASTA" card in
   the Builder's References section and a bare unwired `reference_fasta` input compile
   identically.
4. **Reference-index staging.** A FASTA carries a sidecar index a bwa-mem2/samtools/bcftools
   process needs sitting next to it in the process work directory. Nextflow stages only the file
   a process explicitly declares, so for any param in `INDEXED_REFERENCE_PARAMS` the compiler
   builds a **tuple channel**: `[file(params.reference), file("${params.reference}.*")]` — the
   FASTA plus every sibling matching its name-glob, staged together. A BED or VCF reference needs
   no such tuple (no sidecar convention to honor).
5. **An uncatalogued tool still gets wired, never silently dropped and never fabricated.** Its
   module renders as a placeholder process: real `input:`/`output:` declarations (so the DAG
   stays valid and the placeholder's channel wiring is exactly what a real implementation would
   need), a `script:` that `echo`s the gap and `exit 1`s (a real run fails loudly, not silently),
   and a working `stub:` (so `-stub-run` still validates the whole graph including the gap).
6. **A repeated tool is aliased.** Nextflow requires a distinct name per process invocation; two
   graph nodes naming the same tool compile to `TOOL_1`/`TOOL_2` calls sharing one process
   definition (one module file per **distinct** tool, not per node).
7. **A cycle is rejected.** Kahn's algorithm over tool nodes (source nodes are dependency-free)
   raises `CompileError("... a cycle ...")` — a Nextflow DAG must be acyclic, so this fails at
   compile time, not at `nextflow run` time.
8. **A bad edge is rejected.** An edge naming a missing node or an out-of-range port index raises
   `CompileError` immediately — never silently dropped (a dropped edge would be a *worse* bug than
   a loud failure: a graph that looks valid but wires nothing).

### Robustness hardening (`tests/test_nextflow_robustness.py`, 17 cases)

A kind/tool/id/pipeline-name is interpolated raw into generated Groovy + bash, and a graph can now
carry operator-supplied text (custom scripts, packaging strings) — so the compiler validates and
escapes rather than trusting input:

1. **Injection defense.** `_groovy_escape()` escapes backslash + single-quote and turns a raw
   newline/CR into `\n`/`\r` before any value enters a single-quoted Groovy string (the pipeline
   name, and operator-supplied `conda`/`container`); a hostile port `kind`, tool name, or node id
   that fails the identifier pattern is rejected with a `CompileError`, never emitted.
2. **File-input source wires to reads, not a placeholder.** A generic `File input` source emitting
   `fastq` wires to the `ch_reads` value channel exactly like an unwired `fastq` input; a novel-kind
   source becomes its own params channel — neither becomes a labelled placeholder.
3. **Proc-name-collision guard.** `_proc_name` is many-to-one (punctuation/case collapse), so two
   *distinct* tools mapping to the same process name are rejected — a custom node reusing a
   catalogued name is NOT a collision (`is_custom` wins in `_render_module`).
4. **Fan-in guard.** Two edges into one input port are rejected — a real fan-in must be merged by an
   explicit upstream node, not a clobbered channel map.
5. **Duplicate-emit dedup.** Duplicate output kinds on a placeholder/custom node are deduped, so the
   `emit:` block stays valid.
6. **Catalog port-drift guard.** A catalogued (non-custom) node whose declared ports diverge from
   its `ProcessSpec` (drifted inputs, or an uncatalogued output kind) is rejected — a reordered
   output *subset* still compiles.

## Operator-authored custom-script processes (ADR-0020, `compiler.py` / `api/routers/nextflow.py`)

The catalog is curated (wiring rule 5): a card the maintainer hasn't written a `ProcessSpec` for
compiles to a loud placeholder. That leaves no in-product path to run a real step off the germline
chain — say a `bcftools annotate` over a called VCF. An **operator-authored custom-script process**
is that path: a Builder card on which a **human** supplies a verbatim Nextflow `script:` body.

**Model.** `NfNode` carries three optional fields — `script: str | None`, `container: str | None`,
`conda: str | None`. A node with a **non-empty** `script` is a **custom process**
(`NfNode.is_custom()`). Absent on every ordinary card, so the change is purely additive — the seeded
germline chain carries none and its compiled output is byte-identical (the drift guard stays green).

**Compile.** `_render_module` checks for a custom node **first**, before the catalog: a custom node's
verbatim body is rendered by `_render_custom` and **the catalog is never consulted for it** — even if
the custom tool name collides with a catalogued one, the operator's body wins (pinned by
`test_custom_node_never_consults_the_catalog_even_on_a_name_collision`). The body is emitted
byte-for-byte (only re-indented into the `script:` block, exactly as the catalogued path does);
PipeGuard never rewrites or fabricates it. Ports are meta-threaded and wired from the graph edges
**exactly like a catalogued per-sample process** (`_custom_input_decl` reuses `_with_meta` +
`REFERENCE_PARAM`/`INDEXED_REFERENCE_PARAMS`), so a custom card drops into a fan-out graph unchanged —
`ANNOTATE(BCFTOOLS_CALL.out.vcf)` is wired from the edge with zero custom-path wiring code. Each
input variable is named after its port **kind** (`path(vcf)`, referenced as `${vcf}`) so an
operator's script can address its inputs by a predictable name. Outputs declare `path("*")` (the
typed model can't know the operator's filenames, so the process captures its work dir; the operator's
script is responsible for producing the declared artifacts) with `emit: <kind>` — an output kind
**outside the built-in vocabulary is allowed and wired by its raw name**, never a crash
(`test_custom_process_may_emit_a_kind_outside_the_known_vocabulary`).

**Honesty + safety (the whole point, ADR-0020's four-way safety).** The emitted module carries an
honest header comment + a `label 'operator_authored'` directive — *"operator-authored custom process
— runs on the compute host; production needs sandboxing/allowlisting; not a curated/catalogued tool.
PipeGuard transcribed this operator body verbatim (compose ≠ execute) — it did not author or vet the
command."* Two hard rules keep it from becoming a fabrication vector:

1. **Never fabricate a command.** A custom card whose `script` is blank/whitespace is a
   `CompileError` (a **422** at `POST /api/pipelines/compile`), never an invented command; an
   uncatalogued-*and*-no-script node keeps its existing labelled placeholder (distinct paths).
2. **Compose ≠ execute is unchanged.** `_render_custom` emits TEXT; `compile_graph` spawns no
   subprocess (`test_compile_returns_text_and_spawns_no_subprocess`). A custom command reaches a
   compute host **only** inside a SAVED, APPROVED pipeline via the W1 run gate
   (`POST /api/pipelines/run`, ADR-0020 safety [i]); the stateless compile path runs nothing. Agents
   still cannot author a command — this is the *human*-authoring surface the
   [agent-authoring-contract](agent-authoring-contract.md) presupposes (ADR-0020 safety [iii]).

**Compile API.** `POST /api/pipelines/compile` accepts the three optional fields on a posted node
(`CompileNode.script/container/conda`), threaded straight into the `NfNode` — additively, so the
pre-existing wire shape is unchanged. A custom-script card thus compiles to real Nextflow over the
wire (`test_compile_accepts_an_operator_authored_custom_script_node`).

**Honest scope.** A custom process is meta-threaded per-sample, so it expects a per-sample input
carrying `meta` (the common "runs on a pipeline output" case, e.g. a VCF). A custom node with only
reference/no per-sample inputs is an edge case not specially handled (see ADR-0020 §Revisit when).
The Builder's custom-script card UI is built separately (frontend); this doc is the backend compile
path.

## Per-sample fan-out (W4, `catalog.py` / `compiler.py`)

Every catalogued process is now **per-sample by default** (`ProcessSpec.per_sample: bool = True`):
its input/output declarations carry the nf-core `[meta, files]` map, it runs once per samplesheet
row, and it tags/names its outputs by `${meta.id}` — so a multi-sample samplesheet **fans out**
(each sample's chain runs independently through the whole DAG) and a single sample is a fan-out of
one. `MultiQC` is the one catalogued **aggregator** (`per_sample=False`): it drops the meta and
`.collect()`s every sample's QC streams into a single report, since QC aggregation is inherently
cross-sample. The compiler's `_render_catalogued` branches on this flag — a per-sample process
gets `tag "${meta.id}"` + meta-threaded `tuple val(meta), …` ports (`_with_meta`); reference/panel
inputs (`reference_fasta`/`panel_bed`) stay meta-free **shared value channels**, broadcast to every
sample rather than carried per-row. `main.nf`'s reads channel is built from a samplesheet, not a
bare `--read1`/`--read2` pair: `Channel.fromPath(params.input).splitCsv(header: true).map { row ->
tuple([id: row.sample], file(row.fastq_1), file(row.fastq_2)) }`. An **uncatalogued** tool's
placeholder module fans out the same way (`_render_placeholder` meta-threads its inputs/outputs
too), so an unknown card still wires into a fan-out graph rather than breaking it.

**Honest scope.** The seeded germline chain and the live intake driver still hand the pipeline a
**one-row** samplesheet (HG002) — a degenerate fan-out of 1. The emitted output filenames
(`${meta.id}.*` = `HG002.*`) are byte-identical to the pre-fan-out driver. A true **multi-sample**
driver run — submitting an N-row samplesheet to a real Nextflow invocation and parsing N result
directories — remains unverified live (no second real sample's reads on disk in this sandbox); see
[§Multi-sample driver parse](#multi-sample-driver-parse-2026-07-11-w4-continuation) below for what
changed and what did not.

## Multi-sample driver parse (2026-07-11, W4 continuation)

`scripts/run_giab_pipeline.py`'s POST-run parse (the step that turns a Nextflow publish dir into
the gate-able run-dir CSVs) is now genuinely **N-sample capable**, closing the "a true
multi-sample driver run … is not built" gap the paragraph above used to carry — narrowed, not
closed, since the LIVE multi-sample Nextflow run is still unverified (see below).

1. **`discover_samples(results)`** finds every sample the publish dir actually holds, from its
   per-sample `${id}.fastp.json` (the fan-out's canonical first-stage artifact) — sorted, so the
   run-dir row order is stable. An empty publish dir (`glob` finds no `*.fastp.json`) is a loud
   `sys.exit`, never a silent zero-sample run.
2. **`_one_for(results, sample, pattern)`** anchors each sample's file match with a **dot prefix**
   (`glob.escape(sample) + "."`), so a shared-prefix pair like `S1`/`S10` can never cross-capture —
   `S1.*` cannot match `S10.…` because the character after `S1` is `0`, not `.`. A sample present
   in the publish dir but missing one of its required per-sample outputs (`fastp.json` /
   `mosdepth.summary.txt` / `thresholds.bed.gz` / `norm.vcf.gz`) fails loud, naming the sample and
   the missing pattern — never a silently-dropped sample or a fabricated metric.
3. **`parse_publish_dir(results) -> list[SampleMetrics]`** runs `parse_sample` over every
   discovered id, reusing the existing per-file parsers (`parse_fastp`/`parse_mosdepth`/
   `count_variants`) unchanged.
4. **`write_run_dir_multi(cfg, samples)`** writes the **one** run dir the read-API/gate already
   discover (`data/<run_id>/`), with **N rows** across every frozen-five CSV
   (`SampleSheet.csv`/`sample_metadata.csv`/`demux_stats.csv`/`qc_metrics.csv`) — the same "one
   sequencing run → one run dir → N samples" shape `data/mock_run_01` (S1..S5) already uses, so
   `run_gate_from_dir` yields N cards with **zero** read-API or gate change. `demux_stats.csv`'s
   `% Reads` becomes each sample's real share of the run's total reads (100% for a lone sample,
   unchanged for N=1). A **fan-out of 1** (the live HG002 driver) still emits BYTE-IDENTICAL
   output to the pre-fan-out single-sample format — pinned by
   `test_single_sample_run_dir_is_byte_identical_to_pre_fanout_format`. The scalar `write_run_dir`
   wrapper the offline preflight test calls is kept, now delegating to `write_run_dir_multi`.

**Verification — offline only, against fixture publish dirs, not a live Nextflow run.**
`tests/test_run_giab_multisample.py` (7 cases) builds small hand-crafted publish dirs (fastp JSON,
mosdepth summary/thresholds, a norm VCF, per sample) and asserts: an N-sample dir → one run dir
with N gated rows; a fan-out of 1 is byte-identical to the pre-fan-out format; a partial publish
dir (one sample missing one output) and an empty publish dir both fail loud; `S1`/`S10` never
cross-capture; `demux_stats.csv`'s `% Reads` is each sample's real share. No Nextflow, no bioconda
tools, no network — pure functions of on-disk fixtures, so this runs in the default sandboxed dev
environment.

**Honest deferral, stated precisely.** The parse/write/gate LOGIC above is proven against fixture
publish dirs; a genuinely **live** multi-sample Nextflow run is not — this sandbox (and the
maintainer's local verification environment) has no second real sample's panel reads on disk, so
the live driver (`run_nextflow()`) still writes a **single-row** samplesheet (`sample,fastq_1,
fastq_2\nHG002,…`) and every live run to date has been a fan-out of 1. Handing the driver an
N-row samplesheet with real multi-sample reads, and confirming the parse above operates
correctly on Nextflow's REAL published output (not just the fixture shape this test builds), is
the next step, not yet taken.

## Executor profiles: local-serial / Slurm (W4, `nextflow.config` / the intake driver)

The generated `nextflow.config` now bakes in two additional `profiles {}` blocks, alongside the
pre-existing `conda`/`docker`/`singularity`/`stub`:

1. **`standard`** — the demo default (Nextflow's implicit profile, so a plain `nextflow run` takes
   this path). Forces strict local serial execution: `executor.queueSize = 1`, `process.maxForks =
   1`, `process.cpus = 1` — one sample, one process, one CPU at a time. This is deliberately the
   most conservative possible local profile, matching the single-machine demo environment.
2. **`slurm`** — cluster execution: `process.executor = 'slurm'`, with the queue name
   (`PIPEGUARD_SLURM_QUEUE`, default `normal`), any `clusterOptions` string (e.g. `-A
   my-account`, `PIPEGUARD_SLURM_CLUSTER_OPTIONS`), and the in-flight job cap
   (`PIPEGUARD_SLURM_QUEUE_SIZE`, default `50`) all **env-driven, never a baked guess** — a
   deployer supplies their own account/queue/partition via environment, not a hand-edited config
   file. One sbatch job is submitted per process instance, so samples (and independent stages
   within a sample) can run in parallel across the cluster.

`scripts/run_giab_pipeline.py`'s `_detect_profile()` picks between them: `shutil.which("sbatch")`
present → `-profile slurm`; absent → `-profile standard`. The compiled bundle is identical either
way — only the executor selected at the `nextflow run` command line changes (compose ≠ execute:
the compiler never bakes an executor choice into the graph itself).

**Honest limit, stated precisely: CONFIG-verified, not CLUSTER-verified.** This repo's sandbox
(and the maintainer's local verification environment) has no `sbatch` on `PATH`, so every live
run to date — including the "Verified live" HG002 run below — has taken the `standard` local-
serial branch. The `slurm` profile has been read and reasoned through, and its Nextflow syntax is
valid, but it has **never been submitted to, or executed by, a real Slurm cluster.** This is the
same class of limit ADR-0003's own "job-runner/cloud adapters stay wishlist" note already carries
— W4 narrows that gap (a Slurm profile now exists, is auto-selected, and is env-configurable) but
does not close it (no cluster has run it). AWS-Batch/HealthOmics executor config remains entirely
unbuilt.

## The reference-pipeline drift guard

The seeded germline chain (`germline.py`'s `germline_graph()` — the same 7-tool chain the
frontend's `germlineTemplate()` seeds onto a fresh Builder canvas) compiles to
`pipelines/germline/`, which is **committed to the repo verbatim as the compiler's output for that
graph** — not hand-written and not hand-edited afterward. `scripts/generate_reference_pipeline.py`
regenerates it (and deletes any stale file the compiler no longer emits); a test in
`tests/test_nextflow_compile.py` (`test_committed_reference_pipeline_matches_the_compiler`) fails
the suite if the two ever diverge. This is the same "single artifact by construction" pattern the
repo already uses for the Builder's `run_layout.yaml` emission — it means "what the Pipeline
Builder would emit if you exported the seeded template" and "the pipeline the demo actually runs"
are provably one thing, not two things a maintainer has to keep in sync by hand.

## The compile endpoint + Builder export

`POST /api/pipelines/compile` (`api/routers/nextflow.py`) is a stateless, off-gate HTTP wrapper:
it takes the Builder's exact save shape (`{nodes:[{id,name,ins,outs}], edges:[{from:{node,idx},
to:{node,idx}}]}`) and returns the compiled bundle — `format=json` for a preview (files + the
rendered `main.nf` + a topological step list) or `format=zip` for a downloadable archive. An empty
graph, a cycle, or a bad edge is a 422 carrying the compiler's own error string — the same
tolerant-boundary posture (fail loud with the real reason, never silently) as the rest of the
read-API. It never persists anything and never runs Nextflow.

The frontend's `NextflowExportModal` (wired from a new "Nextflow" Pipeline-Builder toolbar
button, `frontend/src/screens/PipelineBuilder.tsx` / `frontend/src/components/BuilderModals.tsx`)
compiles the LIVE canvas graph on open, previews `main.nf` and the step chain, and offers Copy /
Download `.zip` — labelled honestly as "composes, never runs a tool or sets a verdict." This is a
capability addition on top of the Builder's pre-existing `run_layout.yaml` emission
(wishlist #11, [scope-and-wishlist.md](../requirements/scope-and-wishlist.md)): where `Emit`
produces a locator-config YAML naming which files feed which stage, "Export to Nextflow" produces
an actually-executable pipeline for the same graph. (The old `RunHandoffModal` `run_layout.yaml`
preview was later deleted as orphaned once `RunPipelineModal` superseded it; `AuthorToolNodeModal`
is now wired to a real node proposal, [node-authoring-agent.md](node-authoring-agent.md).)

## Nextflow-first intake

`scripts/run_giab_pipeline.py` is the app's execution driver — `POST /api/runs`
(`api/routers/intake.py`) triggers it as a background subprocess. **Before this landing** it
called `fastp`/`bwa-mem2 mem`/`samtools fixmate`/`markdup`/`mosdepth`/`bcftools` directly, in
sequence, as a hand-written bioconda-toolchain script. **Now** it is Nextflow-first: `run_nextflow()`
shells out to `nextflow run pipelines/germline/main.nf` — the exact reference pipeline this
compiler produces — with the real HG002 fastqs/reference/panel BED as params, then parses the
pipeline's **published** QC outputs (`*.fastp.json`, `*.mosdepth.summary.txt`/
`*.thresholds.bed.gz`, `*.norm.vcf.gz`) into the frozen-five run-dir CSV contract the gate
consumes (unchanged — `run_gate` was not touched). Needs `nextflow` + a JRE + the bioconda tools
on `PATH` (e.g. the `hackathon` conda env used to verify this locally — not a repo dependency);
`api/routers/intake.py` injects an env override via `PIPEGUARD_BIOCONDA_BIN`.

**Operator-gated + authored-pipeline processing (ADR-0021).** `POST /api/runs`'s `SubmitRunIn` now
optionally names a `pipeline` (+`pipeline_version`): when present, intake resolves + compiles that
operator-**authored**, approver-blessed pipeline through the *same* approval gate the Builder-Run
path uses (`api/authored_pipeline.py` — a name with no approved version → 409); absent, it runs the
committed `germline-panel` reference as before (byte-preserved, since for that pipeline the compiled
bundle *is* the committed reference). A processing `mode` gates *when* the driver fires — `immediate`
(now), `hold` (register without firing; release later via `POST /api/runs/{id}/release`), or
`schedule` (park with `scheduled_at`; a time-based auto-release is a DEFERRED seam — release is
manual today). Both are execution-boundary concerns, off the deterministic gate; compose ≠ execute
holds (the core still never runs a tool). See
[ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md).

**The `compose ≠ execute` boundary, stated precisely:**

1. `src/pipeguard/` (the core, including `src/pipeguard/nextflow/`) **never runs a tool.** The
   compiler emits text. `run_gate`/`rules`/`synthesis` read a CSV run dir; none of them shell out
   to anything.
2. `scripts/run_giab_pipeline.py` (a driver, outside the core) and `api/routers/intake.py` (the
   API layer, also outside the core) **do** shell out to Nextflow, which orchestrates the real
   toolchain. This was already true before this change (T-057 already had the API layer
   triggering an external subprocess) — what changed is *what that subprocess does internally*,
   not *whether* the API layer executes something. No new boundary was crossed; the existing one
   just got more honest (the driver used to bypass Nextflow entirely despite ADR-0003 naming it as
   the compute-portability layer).

**Verified live** (2026-07-11, on real GIAB HG002 panel reads, via the `hackathon` conda env —
Nextflow 26.04 + a JRE + MultiQC installed locally, `data/real-giab/` gitignored and not committed):
`nextflow run` reported `completed=7 failed=0`; the parsed QC matched the pre-Nextflow numbers
(Q30 88.2%, coverage 54.2×, 553 normalized variants — same real reads, same tools, different
orchestrator); the gate produced HG002 **HOLD** on the honest cluster_pf-missing signal (a
run-level SAV/InterOp metric a fastq→BAM path cannot produce — flagged, not fabricated), matching
the pre-Nextflow expected result. This confirms the Nextflow re-plumbing changed *how* the tools
run, not *what* they compute.

## Pre-flight guards + version capture (2026-07-11, T-131)

Four audit findings (`audit/SYNTHESIS.md` P3-3/P3-4/P3-5/P3-6) hardened
`scripts/run_giab_pipeline.py` around the Nextflow launch above, without touching what Nextflow
itself runs or how the gate scores the result:

1. **FASTQ pairing/format (P3-3).** Before the launch, `_preflight_fastqs()` streams R1/R2 in
   lockstep: each file must exist, be non-empty, and not be the same file; every 4-line record must
   look like FASTQ (`@` header, `+` separator line, equal seq/qual length); and each pair of records
   must share a mate-independent read id (Casava comment + `/1`/`/2` suffix stripped). A pairing
   failure — a swapped file, a truncated file, or a mismatched sample — raises a loud, specific
   `sys.exit` naming the read index and the two ids that didn't match, **before** any tool runs.
2. **Reference↔panel-BED contig naming (P3-4).** `_preflight_contigs()` reads the reference's
   contig set (from its `.fai` if present, else FASTA headers) and asserts every panel-BED contig is
   a member. A naming mismatch (`20` vs `chr20`) does not crash downstream — it silently yields
   ~0% panel breadth (mosdepth finds no overlap) — so this check turns that silent-wrong-result
   failure mode into a loud one, before Nextflow launches.
3. **Reference-index sidecar presence (P3-5).** `_preflight_reference_index()` asserts the sidecars
   the germline chain's reference channel needs (`.fai`, `.0123`, `.amb`, `.ann`, `.bwt.2bit.64`,
   `.pac`) are on disk before launch — without this check the run would launch, run fastp, and only
   then die deep inside bwa-mem2, burning a full launch on a problem detectable in milliseconds.
4. **Per-run resolved-version capture (P3-6).** `capture_versions()` writes `versions.txt` into the
   run dir: a best-effort snapshot of the resolved `nextflow`/`fastp`/`bwa-mem2`/`samtools`/
   `mosdepth`/`bcftools`/`multiqc` versions actually on `PATH` at run time (`shutil.which` + a
   `--version`/`version` probe per tool). **This is provenance capture only — it does NOT pin or
   change any container/conda tag**; the module catalog stays floating tags + a version floor
   deliberately (re-pinning containers was assessed Medium risk and left out of scope). A probe
   failure (tool absent/erroring) is recorded as text (`"<tool>: not found on PATH"`), never fatal —
   capturing provenance must not break a run. **This does not add a `pipeline_info/` round-trip**
   (Limitation 5 below is unchanged) — `versions.txt` is a separate, simpler resolved-version
   snapshot, not Nextflow's own manifest.

A fifth, related finding (P3-9) is a **labeling-only** fix, not a new guard: the driver's
`sample_metadata.csv` was always fixture-authored (HG002, `tissue=blood`, `subject_id=sample_id` —
this build has no LIMS/subject feed), and now carries an explicit `metadata_origin=
fixture-authored-placeholder` column so a downstream reader can never mistake it for accessioned
subject data (an extra column, not a `#`-comment line — the core parser has no `comment=` set and
would misread a leading `#` line as the header row).

Each guard is a pure function of its path args (unit-tested without Nextflow on `PATH`,
`tests/test_run_giab_preflight.py`, 16 cases) and none ever silently proceeds past a bad input —
see [functional.md REQ-F-092/REQ-F-093](../requirements/functional.md) and
[nonfunctional.md REQ-NF-005/REQ-NF-044](../requirements/nonfunctional.md).

## Tests / verification

| Test | What it pins |
|---|---|
| `test_germline_bundle_has_the_expected_files` | The bundle has `main.nf`/`nextflow.config`/7 module files. |
| `test_germline_channel_wiring_matches_the_typed_ports` | Every graph edge appears as an `UPSTREAM.out.<kind>` argument; unwired inputs become source channels; the reference FASTA stages its sidecar-index tuple. |
| `test_a_process_carries_a_real_command_and_a_stub` | A catalogued process has both a real `script:` and a working `stub:`. |
| `test_committed_reference_pipeline_matches_the_compiler` | The drift guard — `pipelines/germline/` byte-for-byte equals `compile_graph(germline_graph())`, no stray or missing files. |
| `test_cycle_is_rejected` / `test_edge_to_unknown_node_is_rejected` | A cycle / a bad edge raises `CompileError`, never silently drops. |
| `test_uncatalogued_tool_becomes_a_labelled_placeholder` | An unknown tool still wires; its module is a labelled, loudly-failing placeholder, never a fabricated command. |
| `test_reference_source_node_maps_to_a_params_channel` | A no-input reference card compiles identically to an unwired reference input. |
| `test_repeated_tool_is_aliased` | Two nodes naming the same tool alias to distinct calls sharing one module. |
| `test_generated_germline_stub_runs` | **Machine-gated, skip-safe** (mirrors the Postgres-live pattern): if `nextflow` is on `PATH`, the generated pipeline must validate end-to-end via `-stub-run` with placeholder inputs; absent Nextflow → skip, never fail. |
| `tests/test_nextflow_api.py` (6 tests) | `POST /api/pipelines/compile` — JSON preview, `.zip` download, a 422 on a cycle/empty graph, **and (ADR-0020) a posted custom-script node → real Nextflow + a blank custom script → 422**. |
| `tests/test_nextflow_custom_process.py` (9 items, NEW, ADR-0020) | Operator-authored custom processes: a custom node renders its verbatim body wired from the edge + honestly labelled; the catalog is never consulted (even on a name collision); a blank script is a `CompileError` (never fabricated) while an uncatalogued-no-script node keeps its placeholder; a novel output kind is wired by name; compose ≠ execute (returns text, spawns no subprocess); the germline drift stays green. Pure-offline, no `nextflow` needed. |
| `tests/test_run_giab_multisample.py` (7 tests, W4 continuation) | Offline, fixture-publish-dir proof of the multi-sample parse: N-sample dir → N gated run-dir rows; fan-out-of-1 byte-identical to the pre-fan-out format; partial/empty publish dir fails loud; `S1`/`S10` prefix anchoring; `demux_stats.csv` `% Reads` share. No `nextflow` involved — see [§Multi-sample driver parse](#multi-sample-driver-parse-2026-07-11-w4-continuation). |
| `tests/test_nextflow_promoted_ports.py` (5 tests, 2026-07-12) | The reserved-port honesty model: the promoted kinds (`fastp` `unpaired_fastq`/`failed_fastq`, `bcftools norm` `vcf_index`, `MultiQC` `multiqc_html`, mosdepth byproducts) each render to a real `emit:` channel + `stub:` touch; the removed kinds no longer appear in any `ProcessSpec`; `adapter_fasta` stays reserved; the germline drift stays green. Pure-offline. |
| `tests/test_nextflow_robustness.py` (17 tests) | The §Robustness hardening guards: Groovy/identifier injection escaping (hostile kind/tool/pipeline-name), the File-input-source-wires-to-reads fix, proc-name-collision / fan-in / duplicate-emit / catalog-port-drift rejection, zero-input meta omission — plus the germline drift + a custom-script node still compiling. Pure-offline. |

Census (verified `uv run pytest --collect-only -q` + `ls tests/test_*.py | wc -l`, updated
2026-07-12): **634 tests collected across 48 test files** (+`test_nextflow_promoted_ports.py` and
`test_node_observations.py` since the prior 620/46 count). The compiler/wiring/drift/placeholder/
robustness/custom-process/multi-sample-parse tests all run **unconditionally offline** — no
`nextflow` binary required. Two machine-gated live checks (`test_nextflow_compile.py`'s `-stub-run`
and `test_e2e_pipeline.py`'s env-gated live-stub) skip when `nextflow` is absent (this sandbox's
default) and run when it is present; that is the only source of the pass-vs-skip variance. The
authoritative pass/skip census is reconciled in [quality/evaluation.md](../quality/evaluation.md).

## Limitations (recorded in the open, not hidden)

1. **The catalog is curated, not general.** Only the 7 germline-chain tools have a real command.
   A future node-authoring-agent proposal or an arbitrary Builder palette card compiles to a
   placeholder, not a runnable process, until someone adds a `ProcessSpec` for it.
2. **Cluster execution is CONFIG-verified, not CLUSTER-verified (narrowed 2026-07-11, W4).**
   `nextflow run pipelines/germline/main.nf -profile conda`/`-profile standard` is what was
   actually verified live. A `slurm` profile now exists (env-driven queue/cluster-options/
   in-flight cap) and is auto-selected when `sbatch` is on `PATH` — but this sandbox has no
   `sbatch`, so it has **never executed against a real cluster**; only its Nextflow syntax has
   been read and reasoned through. AWS-Batch/HealthOmics executor config (the rest of ADR-0003's
   compute-portability decision) remains fully unbuilt.
3. **Container images are named, not pulled/verified.** Each `ProcessSpec.container` names a
   plausible biocontainer image (nf-core convention); none has been pulled or run in this repo —
   only the `conda` profile has been live-verified.
4. **The LIVE intake driver still runs a single-sample fan-out of 1** (narrowed 2026-07-11, W4
   continuation — was "not built," now "built offline, unverified live"; see
   [functional.md REQ-F-067](../requirements/functional.md) for the fixture-scope boundary and
   [functional.md REQ-F-095](../requirements/functional.md) for the parse itself). The compiled
   pipeline fans out per-sample (W4, above): every catalogued process carries the nf-core
   `[meta, files]` map. **The driver's post-run parse is now genuinely N-sample capable**
   (`discover_samples`/`parse_publish_dir`/`write_run_dir_multi`, [§Multi-sample driver
   parse](#multi-sample-driver-parse-2026-07-11-w4-continuation)) and is proven against fixture
   publish dirs (7 offline tests) — but the driver still hands Nextflow a **one-row** samplesheet
   (only HG002 has real reads on disk in this sandbox), so a genuinely live multi-sample run
   (N-row sheet → a real Nextflow fan-out → the parse above run against Nextflow's real output)
   has never been exercised.
5. **No `nextflow_schema.json`/`pipeline_info/` round-trip.** The driver parses each process's
   published QC file directly (fastp.json, mosdepth summary) rather than ingesting Nextflow's own
   `pipeline_info/` provenance manifest (`software_versions.yml`, `execution_trace_*.txt`, …) —
   PipeGuard keeps its own provenance ledger instead (ADR-0002); see
   [nf-core-conventions.md §3](../data/nf-core-conventions.md).

---

*Marker legend:* **Fact** (grounded by reading the cited code/tests or the live-run output above)
· **Assumption** · **Decision** · **TODO**.
