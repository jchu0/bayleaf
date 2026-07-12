"""Compile a typed-port card graph → a runnable nf-core-style Nextflow (DSL2) bundle.

Pure text codegen (no Nextflow invoked here — compose ≠ execute, ADR-0003). The input is an
:class:`NfGraph` (nodes carry a tool name + ordered input/output artifact-kinds; edges connect a
specific output PORT of one node to a specific input PORT of another — the same
``{from:{node,idx}, to:{node,idx}}`` shape the Builder saves). The output is a
:class:`NextflowBundle`: ``main.nf`` (channel-wired workflow) + one ``modules/*.nf`` per distinct
tool + ``nextflow.config``.

Wiring rule: an input port fed by an edge draws ``<UPSTREAM_CALL>.out.<kind>``; an UNWIRED input is
a pipeline source — ``fastq`` → the reads channel, a reference kind → its ``params`` channel. A
source node (no inputs, emits only reference kinds) is not a process; it maps to that params
channel too. An uncatalogued tool still gets wired, but its module is a labelled placeholder whose
real command fails loudly (a real run surfaces the gap; ``-stub-run`` still validates the DAG).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import INDEXED_REFERENCE_PARAMS, REFERENCE_PARAM, ProcessSpec, catalog_entry


class CompileError(ValueError):
    """The graph can't be compiled (a cycle, or an edge referencing a missing node/port)."""


@dataclass
class NfNode:
    """One Builder card: a tool + its ordered input/output artifact-kinds.

    A card MAY also carry an operator-authored custom Nextflow process body. When a HUMAN operator
    supplies a non-empty ``script`` (via the Builder's custom-script card), this node is a CUSTOM
    PROCESS: the compiler renders that body VERBATIM, wired from this node's own ``ins``/``outs``
    exactly like a catalogued tool, and NEVER consults the tool catalog for it (ADR-0020). The
    optional ``container``/``conda`` are the operator's own packaging for that body. These fields
    are absent (``None``) for every ordinary catalogued/uncatalogued card, so the change is purely
    additive — the seeded germline chain carries none and its compiled output is byte-identical.
    """

    id: str
    tool: str
    ins: list[str] = field(default_factory=list)
    outs: list[str] = field(default_factory=list)
    # Operator-authored custom process (optional). A non-empty `script` ⇒ a CUSTOM PROCESS.
    script: str | None = None  # verbatim Nextflow `script:` body; never rewritten/fabricated
    container: str | None = None  # operator's container image for the custom body (else omitted)
    conda: str | None = None  # operator's conda spec for the custom body (else omitted)

    def is_custom(self) -> bool:
        """True when the operator supplied a NON-EMPTY custom Nextflow body — this node renders
        verbatim from its own ``script``/``ins``/``outs`` and the tool catalog is NOT consulted for
        it (ADR-0020). A blank/whitespace-only ``script`` is deliberately NOT custom here: it is a
        misauthored card the compiler rejects (see ``compile_graph``), never a fabricated
        command."""
        return bool(self.script and self.script.strip())

    def is_source(self) -> bool:
        """A no-input node emitting only reference kinds — a params-backed source, not a process.
        A custom process is never a source: it carries a real command and always renders as a
        process, even if it happens to have no inputs (e.g. an operator-authored fetch step)."""
        if self.is_custom():
            return False
        return not self.ins and bool(self.outs) and all(o in REFERENCE_PARAM for o in self.outs)


@dataclass
class NfEdge:
    """An output PORT (`from_idx` into the source node's `outs`) → an input PORT (`to_idx`)."""

    from_node: str
    from_idx: int
    to_node: str
    to_idx: int


@dataclass
class NfGraph:
    """A named DAG of cards. `name` becomes the pipeline dir/manifest name."""

    name: str
    nodes: list[NfNode] = field(default_factory=list)
    edges: list[NfEdge] = field(default_factory=list)


@dataclass
class NextflowBundle:
    """The generated pipeline: a map of relative path → file content."""

    name: str
    files: dict[str, str]

    @property
    def main_nf(self) -> str:
        return self.files["main.nf"]


def required_inputs(graph: NfGraph) -> set[str]:
    """The artifact-kinds a compiled pipeline needs as EXTERNAL inputs — every tool input port that
    is unwired or fed by a reference source node (i.e. becomes a ``params`` channel, not an upstream
    process output). A runner uses this to require exactly the operator inputs the graph consumes
    (e.g. ``{"fastq", "reference_fasta", "panel_bed"}`` for the germline chain)."""
    nodes = {n.id: n for n in graph.nodes}
    incoming = {(e.to_node, e.to_idx): (e.from_node, e.from_idx) for e in graph.edges}
    kinds: set[str] = set()
    for n in graph.nodes:
        if n.is_source():
            continue
        for i, kind in enumerate(n.ins):
            src = incoming.get((n.id, i))
            if src is None or nodes[src[0]].is_source():
                kinds.add(kind)
    return kinds


# ── name helpers ──────────────────────────────────────────────────────────────────────────────
def _proc_name(tool: str) -> str:
    """UPPER_SNAKE Nextflow process name for a tool card (catalogued or not)."""
    spec = catalog_entry(tool)
    if spec:
        return spec.process
    return re.sub(r"[^A-Za-z0-9]+", "_", tool).strip("_").upper() or "PROCESS"


def _with_meta(decl: str) -> str:
    """Thread the nf-core ``[meta, files]`` map onto a per-sample port decl. ``tuple path(a),
    path(b)`` → ``tuple val(meta), path(a), path(b)``; ``path(x)`` → ``tuple val(meta), path(x)``.
    Reference/value ports keep their bare decl (they are shared value channels, not per-sample)."""
    if decl.startswith("tuple "):
        return "tuple val(meta), " + decl[len("tuple ") :]
    return "tuple val(meta), " + decl


def _is_aggregator(tool: str) -> bool:
    """A catalogued cross-sample AGGREGATOR (per_sample=False, e.g. MultiQC): it drops meta and
    collects every sample's inputs into one run. Uncatalogued tools default to per-sample."""
    spec = catalog_entry(tool)
    return spec is not None and not spec.per_sample


def _module_file(proc: str) -> str:
    return f"modules/{proc.lower()}.nf"


# ── the compile ─────────────────────────────────────────────────────────────────────────────────
def compile_graph(graph: NfGraph) -> NextflowBundle:
    """Compile ``graph`` → a :class:`NextflowBundle`; :class:`CompileError` on a bad graph."""
    nodes = {n.id: n for n in graph.nodes}
    if len(nodes) != len(graph.nodes):
        raise CompileError("duplicate node id in graph")

    # A custom-script card whose body is blank: NEVER fabricate a command — fail loud so a reviewer
    # must supply a real operator-authored body (ADR-0020 safety pin [b]). `script is not None` is
    # the "operator declared a custom card" signal; a non-blank body renders verbatim (is_custom),
    # a blank one is a misauthored card. This is distinct from an uncatalogued-AND-no-script node
    # (`script is None`), which stays the existing labelled placeholder — never rejected.
    for n in graph.nodes:
        if n.script is not None and not n.script.strip():
            raise CompileError(
                f"custom node '{n.id}' ({n.tool}) declares an empty script — a custom process "
                "needs an operator-authored body; PipeGuard never fabricates a command"
            )

    # Validate every edge references real nodes/ports (a missing endpoint is a bug, not a drop).
    incoming: dict[tuple[str, int], tuple[str, int]] = {}
    for e in graph.edges:
        if e.from_node not in nodes or e.to_node not in nodes:
            raise CompileError(f"edge references unknown node ({e.from_node}→{e.to_node})")
        src, dst = nodes[e.from_node], nodes[e.to_node]
        if not (0 <= e.from_idx < len(src.outs)):
            raise CompileError(f"edge from {e.from_node} port {e.from_idx} out of range")
        if not (0 <= e.to_idx < len(dst.ins)):
            raise CompileError(f"edge into {e.to_node} port {e.to_idx} out of range")
        incoming[(e.to_node, e.to_idx)] = (e.from_node, e.from_idx)

    tool_nodes = [n for n in graph.nodes if not n.is_source()]
    order = _topo_order(tool_nodes, incoming, nodes)

    # Alias any tool used by >1 node (Nextflow requires a distinct name per invocation).
    counts: dict[str, int] = {}
    for n in tool_nodes:
        counts[n.tool] = counts.get(n.tool, 0) + 1
    seen: dict[str, int] = {}
    call_name: dict[str, str] = {}
    for n in order:
        base = _proc_name(n.tool)
        if counts[n.tool] == 1:
            call_name[n.id] = base
        else:
            seen[n.tool] = seen.get(n.tool, 0) + 1
            call_name[n.id] = f"{base}_{seen[n.tool]}"

    # Which pipeline-source channels the workflow needs (reads + referenced params).
    needs_reads = False
    ref_params: set[str] = set()
    extra_params: set[str] = set()
    for n in tool_nodes:
        for i, kind in enumerate(n.ins):
            if (n.id, i) in incoming:
                src_id = incoming[(n.id, i)][0]
                if nodes[src_id].is_source():
                    ref_params.add(REFERENCE_PARAM[nodes[src_id].outs[incoming[(n.id, i)][1]]])
                continue
            if kind == "fastq":
                needs_reads = True
            elif kind in REFERENCE_PARAM:
                ref_params.add(REFERENCE_PARAM[kind])
            else:
                extra_params.add(kind)

    files: dict[str, str] = {}
    # One module per DISTINCT tool (aliased calls still share the single process definition).
    for tool in dict.fromkeys(n.tool for n in tool_nodes):  # first-seen order, deduped
        proc = _proc_name(tool)
        files[_module_file(proc)] = _render_module(tool, nodes)

    files["main.nf"] = _render_main(
        graph, order, call_name, incoming, nodes, needs_reads, ref_params, extra_params
    )
    files["nextflow.config"] = _render_config(graph.name, ref_params, needs_reads, extra_params)
    files["README.md"] = _render_readme(graph.name, order, call_name)
    return NextflowBundle(name=graph.name, files=files)


def _topo_order(
    tool_nodes: list[NfNode],
    incoming: dict[tuple[str, int], tuple[str, int]],
    nodes: dict[str, NfNode],
) -> list[NfNode]:
    """Kahn topological sort over tool nodes (source nodes are dependency-free); cycle → error."""
    ids = {n.id for n in tool_nodes}
    deps: dict[str, set[str]] = {n.id: set() for n in tool_nodes}
    for (to_node, _), (from_node, _) in incoming.items():
        if to_node in ids and from_node in ids:  # ignore edges from source nodes
            deps[to_node].add(from_node)
    order: list[NfNode] = []
    ready = [n for n in tool_nodes if not deps[n.id]]  # preserve input order for determinism
    done: set[str] = set()
    while ready:
        n = ready.pop(0)
        order.append(n)
        done.add(n.id)
        for m in tool_nodes:
            if m.id not in done and m.id not in {x.id for x in ready} and deps[m.id] <= done:
                ready.append(m)
    if len(order) != len(tool_nodes):
        raise CompileError("graph has a cycle — a Nextflow DAG must be acyclic")
    return order


# ── renderers ─────────────────────────────────────────────────────────────────────────────────
def _render_module(tool: str, nodes: dict[str, NfNode]) -> str:
    # An operator-authored custom node for this tool WINS over the catalog: its verbatim body is
    # rendered and the catalog is never consulted for it (a HUMAN authored this command, ADR-0020).
    # Checked first so a custom card can even reuse a catalogued tool name without silently
    # inheriting the curated command.
    custom = next((n for n in nodes.values() if n.tool == tool and n.is_custom()), None)
    if custom is not None:
        return _render_custom(custom)
    spec = catalog_entry(tool)
    if spec:
        return _render_catalogued(spec)
    # Placeholder for an uncatalogued tool: real wiring, no fabricated command.
    node = next(n for n in nodes.values() if n.tool == tool)
    return _render_placeholder(tool, node)


def _custom_input_decl(kind: str) -> str:
    """The Nextflow input declaration for one custom-process input port. A reference kind stays a
    shared, meta-free value channel (an indexed FASTA arrives as a ``[file, sidecars]`` tuple,
    matching the compiler's ``ch_<param>`` staging); any other kind is a per-sample artifact whose
    meta rides alongside the operator's named path variable. The variable is named after the port
    KIND (``path(vcf)``, referenced as ``${vcf}``) so an operator's script can address its inputs by
    a predictable name — the same vocabulary the edges wire by, so nothing has to be renamed."""
    if kind in REFERENCE_PARAM:
        if REFERENCE_PARAM[kind] in INDEXED_REFERENCE_PARAMS:
            return f"tuple path({kind}), path({kind}_idx)"
        return f"path {kind}"
    return _with_meta(f"path({kind})")


def _render_custom(node: NfNode) -> str:
    """Render an OPERATOR-AUTHORED custom process from the node's OWN verbatim ``script`` + typed
    ``ins``/``outs`` — the tool catalog is NEVER consulted (ADR-0020).

    WHY the honest header + ``label``: a custom body runs whatever the operator wrote on the compute
    host; it is not a curated, allowlisted, or PipeGuard-vetted command. The emitted process
    self-documents that (a) it is operator-authored, (b) production needs sandboxing/allowlisting,
    (c) PipeGuard only transcribed the text (compose ≠ execute — nothing runs here). The command
    body is emitted byte-for-byte (only re-indented into the triple-quote block, as the catalogued
    path does); PipeGuard never rewrites or fabricates it. Ports are meta-threaded and wired exactly
    like a catalogued per-sample process, so a custom card drops into a fan-out graph unchanged. An
    output kind outside the known artifact vocabulary is still allowed and wired by its raw name
    (``emit: <kind>``), matching the edge wiring — the compiler never crashes on a novel kind."""
    proc = _proc_name(node.tool)
    in_decls = "\n    ".join(_custom_input_decl(k) for k in node.ins) or "val _unused"
    # We cannot know the operator's output filenames from the typed model, so each declared output
    # captures the process work dir permissively (`path("*")`); the operator's script is responsible
    # for producing the artifacts. meta rides so a downstream per-sample process stays wired.
    out_lines = [_with_meta('path("*")') + f", emit: {kind}" for kind in node.outs]
    out_decls = "\n    ".join(out_lines) or (_with_meta('path("*")') + ", emit: out")
    touches = " ".join(f"{kind}.stub" for kind in node.outs) or "out.stub"
    conda_line = f"    conda '{node.conda}'\n" if node.conda else ""
    container_line = f"    container '{node.container}'\n" if node.container else ""
    body = _indent((node.script or "").strip())  # is_custom() guarantees a non-empty body
    return (
        "// operator-authored custom process — runs on the compute host; production needs\n"
        "// sandboxing/allowlisting; not a curated/catalogued tool. PipeGuard transcribed this\n"
        "// operator body verbatim (compose ≠ execute) — it did not author or vet the command\n"
        "// (ADR-0020).\n"
        f"process {proc} {{\n"
        f'    tag "${{meta.id}}"\n'
        f"    label 'operator_authored'\n"
        f"{conda_line}"
        f"{container_line}"
        f"    publishDir \"${{params.outdir}}/custom\", mode: 'copy'\n\n"
        f"    input:\n    {in_decls}\n\n"
        f"    output:\n    {out_decls}\n\n"
        f'    script:\n    """\n    {body}\n    """\n\n'
        f'    stub:\n    """\n    touch {touches}\n    """\n'
        f"}}\n"
    )


def _render_catalogued(spec: ProcessSpec) -> str:
    if spec.per_sample:
        # Per-sample: thread `[meta, files]` onto every non-reference input + every output, and tag
        # by sample. Reference/value inputs (reference_fasta / panel_bed) stay meta-free — they are
        # shared value channels broadcast to each sample.
        in_decls = [
            p.decl if p.kind in REFERENCE_PARAM else _with_meta(p.decl) for p in spec.inputs
        ]
        out_decls = [f"{_with_meta(p.decl)}, emit: {p.channel}" for p in spec.outputs]
        tag = '    tag "${meta.id}"\n'
    else:
        # Aggregator (MultiQC): no meta anywhere; it collects across samples into one report.
        in_decls = [p.decl for p in spec.inputs]
        out_decls = [f"{p.decl}, emit: {p.channel}" for p in spec.outputs]
        tag = ""
    ins = "\n    ".join(in_decls) or "val _unused"
    outs = "\n    ".join(out_decls)
    return (
        f"// {spec.label} — {spec.tool}\n"
        f"process {spec.process} {{\n"
        f"{tag}"
        f"    conda '{spec.conda}'\n"
        f"    container '{spec.container}'\n"
        f"    publishDir \"${{params.outdir}}/{spec.publish}\", mode: 'copy'\n\n"
        f"    input:\n    {ins}\n\n"
        f"    output:\n    {outs}\n\n"
        f'    script:\n    """\n    {_indent(spec.script)}\n    """\n\n'
        f'    stub:\n    """\n    {_indent(spec.stub)}\n    """\n'
        f"}}\n"
    )


def _render_placeholder(tool: str, node: NfNode) -> str:
    proc = _proc_name(tool)
    # Meta-thread inputs/outputs like a catalogued per-sample process, so an uncatalogued card still
    # wires into a fan-out graph (reference inputs stay meta-free value channels).
    in_lines = [
        f"path in{i}" if kind in REFERENCE_PARAM else _with_meta(f"path in{i}")
        for i, kind in enumerate(node.ins)
    ]
    in_decls = "\n    ".join(in_lines) or "val _unused"
    out_lines, touches = [], []
    for kind in node.outs:
        out_lines.append(_with_meta(f'path("{kind}.out")') + f", emit: {kind}")
        touches.append(f"{kind}.out")
    outs = "\n    ".join(out_lines) or _with_meta('path("out")') + ", emit: out"
    touch = "touch " + " ".join(touches or ["out"])
    return (
        f'// PLACEHOLDER — no catalogued Nextflow command for "{tool}". The wiring is real; the\n'
        f"// command is not. `-stub-run` validates the DAG; a real run fails here until filled.\n"
        f"process {proc} {{\n"
        f'    tag "${{meta.id}}"\n\n'
        f"    input:\n    {in_decls}\n\n"
        f"    output:\n    {outs}\n\n"
        f'    script:\n    """\n'
        f"    echo 'PipeGuard: no catalogued Nextflow command for \"{tool}\".' >&2\n"
        f"    exit 1\n"
        f'    """\n\n'
        f'    stub:\n    """\n    {touch}\n    """\n'
        f"}}\n"
    )


def _render_main(
    graph: NfGraph,
    order: list[NfNode],
    call_name: dict[str, str],
    incoming: dict[tuple[str, int], tuple[str, int]],
    nodes: dict[str, NfNode],
    needs_reads: bool,
    ref_params: set[str],
    extra_params: set[str],
) -> str:
    includes = []
    for tool in dict.fromkeys(n.tool for n in order):
        proc = _proc_name(tool)
        aliases = [call_name[n.id] for n in order if n.tool == tool]
        if aliases == [proc]:
            includes.append(f"include {{ {proc} }} from './{_module_file(proc)}'")
        else:
            spec = ", ".join(f"{proc} as {a}" for a in aliases)
            includes.append(f"include {{ {spec} }} from './{_module_file(proc)}'")

    src_lines = []
    if needs_reads:
        # Per-sample fan-out (W4): a samplesheet (sample,fastq_1,fastq_2) → a QUEUE channel of one
        # `[meta, r1, r2]` per row, so each sample's chain runs independently. A single-row sheet is
        # a degenerate fan-out of 1 (the live HG002 intake path is preserved). References stay value
        # channels below, broadcast to every sample.
        src_lines.append("    ch_reads = Channel.fromPath(params.input)")
        src_lines.append("        .splitCsv(header: true)")
        src_lines.append(
            "        .map { row -> tuple([id: row.sample], file(row.fastq_1), file(row.fastq_2)) }"
        )
    for param in sorted(ref_params):
        if param in INDEXED_REFERENCE_PARAMS:
            # Stage the file + every `<file>.*` sidecar index (a bwa-mem2/samtools-indexed FASTA)
            # as a tuple so the index lands next to it in the process work dir.
            idx = f'file("${{params.{param}}}.*")'
            src_lines.append(f"    ch_{param} = Channel.value([file(params.{param}), {idx}])")
        else:
            src_lines.append(f"    ch_{param} = Channel.value(file(params.{param}))")
    for kind in sorted(extra_params):
        src_lines.append(f"    ch_{kind} = Channel.fromPath(params.{kind})")

    calls = []
    for n in order:
        agg = _is_aggregator(n.tool)
        args = []
        for i, kind in enumerate(n.ins):
            args.append(_input_channel(n, i, kind, incoming, nodes, call_name, agg))
        calls.append(f"    {call_name[n.id]}({', '.join(args)})")

    body = "\n".join([*src_lines, "", *calls]) if src_lines else "\n".join(calls)
    return (
        "#!/usr/bin/env nextflow\n"
        "// Generated by PipeGuard from a Pipeline-Builder card graph "
        "(ADR-0003 — compose ≠ execute:\n"
        "// PipeGuard emitted this text; it never ran a tool). Edit params in nextflow.config.\n"
        "nextflow.enable.dsl = 2\n\n" + "\n".join(includes) + "\n\nworkflow {\n" + body + "\n}\n"
    )


def _input_channel(
    node: NfNode,
    idx: int,
    kind: str,
    incoming: dict[tuple[str, int], tuple[str, int]],
    nodes: dict[str, NfNode],
    call_name: dict[str, str],
    aggregator: bool = False,
) -> str:
    """The Nextflow channel expression feeding input port ``idx`` of ``node``. For an AGGREGATOR
    (MultiQC), a per-sample upstream stream is meta-stripped and pooled across samples
    (``.map { it[1] }.collect()``) so the aggregator runs once over every sample's files."""
    if (node.id, idx) in incoming:
        from_node, from_idx = incoming[(node.id, idx)]
        src = nodes[from_node]
        if src.is_source():
            return f"ch_{REFERENCE_PARAM[src.outs[from_idx]]}"
        chan = f"{call_name[from_node]}.out.{src.outs[from_idx]}"
        return f"{chan}.map {{ it[1] }}.collect()" if aggregator else chan
    # Unwired input = a pipeline source.
    if kind == "fastq":
        return "ch_reads.map { it[1] }.collect()" if aggregator else "ch_reads"
    if kind in REFERENCE_PARAM:
        return f"ch_{REFERENCE_PARAM[kind]}"
    return f"ch_{kind}"


def _render_config(
    name: str, ref_params: set[str], needs_reads: bool, extra_params: set[str]
) -> str:
    params = []
    if needs_reads:
        params.append("    input      = null")  # samplesheet: sample,fastq_1,fastq_2 (W4 fan-out)
    for p in sorted(ref_params):
        params.append(f"    {p:<10} = null")
    for p in sorted(extra_params):
        params.append(f"    {p:<10} = null")
    params.append("    outdir     = 'results'")
    return (
        f"// nextflow.config — generated by PipeGuard for pipeline '{name}'.\n"
        f"manifest {{\n"
        f"    name = '{name}'\n"
        f"    description = 'Generated from a PipeGuard Pipeline-Builder card graph'\n"
        f"    nextflowVersion = '>=23.04.0'\n"
        f"}}\n\n"
        f"params {{\n" + "\n".join(params) + "\n}\n\n"
        "process {\n    cpus = 2\n}\n\n" + _PROFILES_BLOCK
    )


# Executor profiles (W4, ADR-0003 — same graph, executor chosen by profile). The DRIVER picks one
# at the run boundary (compose ≠ execute): `sbatch` on PATH → `slurm`, else `standard`. This text is
# CONFIG-VERIFIED, not cluster-verified — the demo env has no sbatch; the emission + the driver's
# branch are tested, a real cluster run is not. SLURM knobs are env-driven (PIPEGUARD_SLURM_*), so
# the profile SHAPE is self-describing while its values stay site-tunable without a recompile.
_PROFILES_BLOCK = """profiles {
    // Local single-thread-serial fallback (the demo default): one sample at a time, one fork,
    // one CPU. 'standard' is Nextflow's implicit default, so a plain `nextflow run` runs serially.
    standard {
        executor.queueSize = 1
        process.maxForks   = 1
        process.cpus       = 1
    }
    // Cluster execution: one sbatch job per process instance, so samples run in parallel. Queue,
    // clusterOptions (e.g. '-A account') and the in-flight cap are env-driven, never baked guesses.
    slurm {
        process.executor       = 'slurm'
        process.queue          = System.getenv('PIPEGUARD_SLURM_QUEUE') ?: 'normal'
        process.clusterOptions = System.getenv('PIPEGUARD_SLURM_CLUSTER_OPTIONS') ?: ''
        executor.queueSize     = (System.getenv('PIPEGUARD_SLURM_QUEUE_SIZE') ?: '50').toInteger()
    }
    conda       { conda.enabled = true }
    docker      { docker.enabled = true }
    singularity { singularity.enabled = true }
    stub        { }
}
"""


def _render_readme(name: str, order: list[NfNode], call_name: dict[str, str]) -> str:
    steps = "\n".join(f"{i + 1}. `{call_name[n.id]}` — {n.tool}" for i, n in enumerate(order))
    return (
        f"# {name} — generated Nextflow pipeline\n\n"
        f"Generated by PipeGuard from a Pipeline-Builder card graph (ADR-0003). PipeGuard\n"
        f"composed this — it did not run it (compose ≠ execute). Validate with no data/tools:\n\n"
        f"```bash\nnextflow run main.nf -stub-run\n```\n\n"
        f"Run for real (bioconda tools on PATH). `--input` is a samplesheet with a header row\n"
        f"`sample,fastq_1,fastq_2` and one row per sample (fans out per sample); pick an executor\n"
        f"profile — `standard` (local, one sample at a time) or `slurm` (one job per sample):\n\n"
        f"```bash\nnextflow run main.nf -profile conda,standard \\\n"
        f"  --input samplesheet.csv --reference ref.fa --panel_bed panel.bed\n```\n\n"
        f"## Steps (topological order)\n\n{steps}\n"
    )


def _indent(block: str) -> str:
    """Indent a multi-line command body to sit inside a 4-space `script:`/`stub:` triple-quote."""
    return block.replace("\n", "\n    ")
