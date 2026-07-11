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
    """One Builder card: a tool + its ordered input/output artifact-kinds."""

    id: str
    tool: str
    ins: list[str] = field(default_factory=list)
    outs: list[str] = field(default_factory=list)

    def is_source(self) -> bool:
        """A no-input node emitting only reference kinds — a params-backed source, not a process."""
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


# ── name helpers ──────────────────────────────────────────────────────────────────────────────
def _proc_name(tool: str) -> str:
    """UPPER_SNAKE Nextflow process name for a tool card (catalogued or not)."""
    spec = catalog_entry(tool)
    if spec:
        return spec.process
    return re.sub(r"[^A-Za-z0-9]+", "_", tool).strip("_").upper() or "PROCESS"


def _module_file(proc: str) -> str:
    return f"modules/{proc.lower()}.nf"


# ── the compile ─────────────────────────────────────────────────────────────────────────────────
def compile_graph(graph: NfGraph) -> NextflowBundle:
    """Compile ``graph`` → a :class:`NextflowBundle`; :class:`CompileError` on a bad graph."""
    nodes = {n.id: n for n in graph.nodes}
    if len(nodes) != len(graph.nodes):
        raise CompileError("duplicate node id in graph")

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
    spec = catalog_entry(tool)
    if spec:
        return _render_catalogued(spec)
    # Placeholder for an uncatalogued tool: real wiring, no fabricated command.
    node = next(n for n in nodes.values() if n.tool == tool)
    return _render_placeholder(tool, node)


def _render_catalogued(spec: ProcessSpec) -> str:
    ins = "\n    ".join(p.decl for p in spec.inputs) or "val _unused"
    outs = "\n    ".join(f"{p.decl}, emit: {p.channel}" for p in spec.outputs)
    return (
        f"// {spec.label} — {spec.tool}\n"
        f"process {spec.process} {{\n"
        f'    tag "${{params.sample}}"\n'
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
    in_decls = "\n    ".join(f"path in{i}" for i in range(len(node.ins))) or "val _unused"
    out_lines, touches = [], []
    for kind in node.outs:
        out_lines.append(f'path("{kind}.out"), emit: {kind}')
        touches.append(f"{kind}.out")
    outs = "\n    ".join(out_lines) or 'path("out"), emit: out'
    touch = "touch " + " ".join(touches or ["out"])
    return (
        f'// PLACEHOLDER — no catalogued Nextflow command for "{tool}". The wiring is real; the\n'
        f"// command is not. `-stub-run` validates the DAG; a real run fails here until filled.\n"
        f"process {proc} {{\n"
        f'    tag "${{params.sample}}"\n\n'
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
        src_lines.append("    ch_reads = Channel.value([file(params.read1), file(params.read2)])")
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
        args = []
        for i, kind in enumerate(n.ins):
            args.append(_input_channel(n, i, kind, incoming, nodes, call_name))
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
) -> str:
    """The Nextflow channel expression feeding input port ``idx`` of ``node``."""
    if (node.id, idx) in incoming:
        from_node, from_idx = incoming[(node.id, idx)]
        src = nodes[from_node]
        if src.is_source():
            return f"ch_{REFERENCE_PARAM[src.outs[from_idx]]}"
        return f"{call_name[from_node]}.out.{src.outs[from_idx]}"
    # Unwired input = a pipeline source.
    if kind == "fastq":
        return "ch_reads"
    if kind in REFERENCE_PARAM:
        return f"ch_{REFERENCE_PARAM[kind]}"
    return f"ch_{kind}"


def _render_config(
    name: str, ref_params: set[str], needs_reads: bool, extra_params: set[str]
) -> str:
    params = ["    sample     = 'HG002'"]
    if needs_reads:
        params += ["    read1      = null", "    read2      = null"]
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
        "process {\n    cpus = 2\n}\n\n"
        "profiles {\n"
        "    conda       { conda.enabled = true }\n"
        "    docker      { docker.enabled = true }\n"
        "    singularity { singularity.enabled = true }\n"
        "    stub        { }\n"
        "}\n"
    )


def _render_readme(name: str, order: list[NfNode], call_name: dict[str, str]) -> str:
    steps = "\n".join(f"{i + 1}. `{call_name[n.id]}` — {n.tool}" for i, n in enumerate(order))
    return (
        f"# {name} — generated Nextflow pipeline\n\n"
        f"Generated by PipeGuard from a Pipeline-Builder card graph (ADR-0003). PipeGuard\n"
        f"composed this — it did not run it (compose ≠ execute). Validate with no data/tools:\n\n"
        f"```bash\nnextflow run main.nf -stub-run\n```\n\n"
        f"Run for real (bioconda tools on PATH), e.g.:\n\n"
        f"```bash\nnextflow run main.nf -profile conda \\\n"
        f"  --read1 R1.fastq.gz --read2 R2.fastq.gz \\\n"
        f"  --reference ref.fa --panel_bed panel.bed\n```\n\n"
        f"## Steps (topological order)\n\n{steps}\n"
    )


def _indent(block: str) -> str:
    """Indent a multi-line command body to sit inside a 4-space `script:`/`stub:` triple-quote."""
    return block.replace("\n", "\n    ")
