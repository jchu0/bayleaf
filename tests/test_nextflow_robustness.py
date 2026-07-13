"""Adversarial robustness tests for the Nextflow compiler (off-golden-path + hostile inputs).

Each case pins one fix from the compiler robustness review — a graph that USED to compile to a
silently-wrong or unparseable bundle now either compiles correctly or fails loud with a
`CompileError`. The germline byte-for-byte drift guard (`test_nextflow_compile.py`) and the
custom-script tests (`test_nextflow_custom_process.py`) stay green: these fixes only touch
off-golden-path/hostile inputs, and the last two tests here re-assert the golden path in-file.

Mapping (review rank → test):
  1. proc-name collision              → test_distinct_tools_sharing_a_process_name_are_rejected
  2. data-kind source + zero-input    → test_file_input_fastq_source_wires_to_reads,
                                        test_novel_kind_source_becomes_a_params_channel,
                                        test_zero_input_custom_omits_meta_and_input_block,
                                        test_zero_input_placeholder_omits_meta_and_input_block
  3. fan-in                           → test_fan_in_into_one_input_port_is_rejected
  4. injection / interpolation        → test_hostile_port_kind_is_rejected,
                                        test_hostile_pipeline_name_is_groovy_escaped
  5. dup-emit kinds                   → test_duplicate_output_kinds_are_deduped_placeholder,
                                        test_duplicate_output_kinds_are_deduped_custom
  6. catalog port-drift               → test_catalogued_node_with_drifted_inputs_is_rejected,
                                        test_catalogued_node_emitting_an_uncatalogued_output_is_rejected
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bayleaf.nextflow import (
    CompileError,
    NfEdge,
    NfGraph,
    NfNode,
    compile_graph,
    germline_graph,
    required_inputs,
)

_REPO = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO / "pipelines" / "germline"


def _fastp() -> NfNode:
    """A catalogued fastp node whose ports match the catalog (used as a valid graph fixture)."""
    return NfNode("fp", "fastp", ins=["fastq"], outs=["fastq", "fastp_json", "fastp_html"])


# ── (1) proc-name collision ──────────────────────────────────────────────────────────────────────
def test_distinct_tools_sharing_a_process_name_are_rejected() -> None:
    """Two DISTINCT tool strings that collapse to the same UPPER_SNAKE process name (`my tool` and
    `my-tool` → MY_TOOL) would clobber one module + emit a duplicate include — a silently-wrong
    bundle. The compiler now rejects it instead of shipping the collision."""
    g = NfGraph(
        name="collide",
        nodes=[
            NfNode("a", "my tool", ins=["bam"], outs=["vcf"]),
            NfNode("b", "my-tool", ins=["bam"], outs=["vcf"]),
        ],
    )
    with pytest.raises(CompileError, match="process name MY_TOOL"):
        compile_graph(g)


def test_custom_node_reusing_a_catalogued_name_is_not_a_collision() -> None:
    """A custom card reusing a catalogued tool name is the SAME tool string, not a distinct-tool
    collision — is_custom wins in the module render, so it must still compile (regression guard for
    the collision fix not being over-eager)."""
    g = NfGraph(
        name="reuse",
        nodes=[
            NfNode(
                "n_call",
                "bcftools call",
                ins=["bam", "reference_fasta", "panel_bed"],
                outs=["vcf"],
            ),
            NfNode(
                "n_norm",
                "bcftools norm",  # a catalogued name, but operator-authored ⇒ renders verbatim
                ins=["vcf"],
                outs=["vcf"],
                script="bcftools annotate -a clinvar.vcf.gz $vcf",
            ),
        ],
        edges=[NfEdge("n_call", 0, "n_norm", 0)],
    )
    module = compile_graph(g).files["modules/bcftools_norm.nf"]
    assert "label 'operator_authored'" in module
    assert "bcftools norm -f" not in module  # the catalogued command did NOT leak in


# ── (2) data-kind source + zero-input placeholder ─────────────────────────────────────────────────
def test_file_input_fastq_source_wires_to_reads_not_a_placeholder() -> None:
    """The shipped generic File-input card (no inputs, emits a DATA kind) used to compile to a
    broken exit-1 placeholder AND drop the input from `required_inputs`. It is now a params-backed
    SOURCE: a wired File-input(fastq)→fastp resolves fastp's input to `ch_reads`, no FILE_INPUT
    process is emitted, and `required_inputs` reports fastq."""
    g = NfGraph(
        name="file-input",
        nodes=[NfNode("src", "File input", ins=[], outs=["fastq"]), _fastp()],
        edges=[NfEdge("src", 0, "fp", 0)],
    )
    bundle = compile_graph(g)
    # The source is not a process — no module, no placeholder anywhere.
    assert "modules/file_input.nf" not in bundle.files
    assert all("PLACEHOLDER" not in c for c in bundle.files.values())
    # fastp draws the reads channel (the same wiring as an unwired fastq input), not a process out.
    assert "FASTP(ch_reads)" in bundle.main_nf
    assert "ch_reads = Channel.fromPath(params.input)" in bundle.main_nf
    # The external input is reported (was empty when File-input compiled as a tool).
    assert required_inputs(g) == {"fastq"}


def test_novel_kind_source_becomes_a_params_channel() -> None:
    """A source emitting a kind that is neither fastq nor a reference routes to a `params.<kind>`
    file channel (not the reads channel, not a broken process), and `required_inputs` reports it."""
    g = NfGraph(
        name="novel-source",
        nodes=[
            NfNode("src", "File input", ins=[], outs=["cram"]),
            # An operator-authored consumer so the novel kind has a real (non-catalogued) sink.
            NfNode("t", "cram-tool", ins=["cram"], outs=["vcf"], script="tool ${cram} > out.vcf"),
        ],
        edges=[NfEdge("src", 0, "t", 0)],
    )
    main = compile_graph(g).main_nf
    assert "ch_cram = Channel.fromPath(params.cram)" in main
    assert "CRAM_TOOL(ch_cram)" in main
    assert required_inputs(g) == {"cram"}


def test_zero_input_placeholder_omits_meta_and_input_block() -> None:
    """A genuinely zero-input placeholder (no inputs, no outputs to make it a source) must omit the
    `input:` block and NOT tag by a `${meta.id}` that no upstream sample provides — otherwise it
    references an undefined variable and fails to parse under -stub-run."""
    g = NfGraph(name="zero", nodes=[NfNode("z", "zero-tool", ins=[], outs=[])])
    module = compile_graph(g).files["modules/zero_tool.nf"]
    assert 'tag "${meta.id}"' not in module  # no meta to tag by
    assert "input:" not in module  # no input block on a zero-input process
    assert "emit: out" in module  # still emits a default output so it parses
    assert "PLACEHOLDER" in module


def test_zero_input_custom_omits_meta_and_input_block() -> None:
    """A zero-input CUSTOM process (e.g. an operator-authored fetch step) likewise omits the input
    block + meta so it parses, while still rendering the operator's body verbatim."""
    g = NfGraph(
        name="fetch",
        nodes=[NfNode("zc", "ref-fetch", ins=[], outs=["ref"], script="wget http://x/ref.fa")],
    )
    module = compile_graph(g).files["modules/ref_fetch.nf"]
    assert 'tag "${meta.id}"' not in module
    assert "input:" not in module
    assert "emit: ref" in module
    assert "wget http://x/ref.fa" in module  # verbatim operator body
    assert "label 'operator_authored'" in module


# ── (3) fan-in ────────────────────────────────────────────────────────────────────────────────────
def test_fan_in_into_one_input_port_is_rejected() -> None:
    """Two edges into the SAME input port would silently drop all but the last (last-write-wins) → a
    wrong pipeline. The compiler now rejects the fan-in loudly."""
    g = NfGraph(
        name="fan-in",
        nodes=[
            NfNode("a", "fastp", ins=["fastq"], outs=["fastq", "fastp_json", "fastp_html"]),
            NfNode("b", "fastp", ins=["fastq"], outs=["fastq", "fastp_json", "fastp_html"]),
            NfNode("c", "bwa-mem2", ins=["fastq", "reference_fasta"], outs=["bam"]),
        ],
        edges=[NfEdge("a", 0, "c", 0), NfEdge("b", 0, "c", 0)],  # both into c's input port 0
    )
    with pytest.raises(CompileError, match="two incoming edges"):
        compile_graph(g)


# ── (4) injection / unescaped interpolation ───────────────────────────────────────────────────────
def test_hostile_port_kind_is_rejected() -> None:
    """A port kind carrying shell/Groovy metacharacters (it becomes a channel name + a bash
    filename) is rejected before any codegen — it never reaches the emitted pipeline."""
    g = NfGraph(
        name="inject",
        nodes=[NfNode("n", "fastp", ins=["fastq"], outs=["vcf; rm -rf /"])],
    )
    with pytest.raises(CompileError, match="characters outside"):
        compile_graph(g)


def test_hostile_tool_name_is_rejected() -> None:
    """A tool name carrying a quote (it lands in an emitted bash `echo '… "<tool>" …'`) is rejected
    rather than allowed to break out of the string."""
    g = NfGraph(name="inject2", nodes=[NfNode("n", "evil'; rm -rf /", ins=["bam"], outs=["vcf"])])
    with pytest.raises(CompileError, match="characters outside"):
        compile_graph(g)


def test_hostile_pipeline_name_is_groovy_escaped() -> None:
    """The pipeline name lands in a Groovy single-quoted manifest string; a name with an apostrophe
    is ESCAPED (not rejected — names legitimately carry punctuation), so the emitted config is still
    valid Groovy and the apostrophe cannot terminate the string early."""
    g = NfGraph(name="eve's pipe", nodes=[_fastp()])
    cfg = compile_graph(g).files["nextflow.config"]
    # The apostrophe is backslash-escaped inside the single-quoted manifest name.
    assert r"name = 'eve\'s pipe'" in cfg
    # A raw, unescaped `eve's pipe'` (string terminated early) must NOT appear.
    assert "name = 'eve's pipe'" not in cfg


# ── (5) duplicate output kinds ────────────────────────────────────────────────────────────────────
def test_duplicate_output_kinds_are_deduped_placeholder() -> None:
    """A placeholder node declaring a repeated output kind must emit ONE `emit:`/`touch` per kind —
    duplicates are a Nextflow parse error."""
    g = NfGraph(name="dup", nodes=[NfNode("n", "dup-tool", ins=["bam"], outs=["vcf", "vcf"])])
    module = compile_graph(g).files["modules/dup_tool.nf"]
    assert module.count("emit: vcf") == 1
    assert module.count("vcf.out") == 2  # once in the output decl, once in the stub touch


def test_duplicate_output_kinds_are_deduped_custom() -> None:
    """A custom node declaring a repeated output kind is likewise deduped to one `emit:`/`touch`."""
    g = NfGraph(
        name="dup-custom",
        nodes=[NfNode("n", "dup-tool2", ins=["bam"], outs=["vcf", "vcf"], script="run")],
    )
    module = compile_graph(g).files["modules/dup_tool2.nf"]
    assert module.count("emit: vcf") == 1
    assert module.count("vcf.stub") == 1


# ── (6) catalog port-drift ────────────────────────────────────────────────────────────────────────
def test_catalogued_node_with_drifted_inputs_is_rejected() -> None:
    """A catalogued node whose INPUT ports diverge from its ProcessSpec would emit a call/module
    arity mismatch — the compiler rejects it (clean fail beats a broken bundle)."""
    g = NfGraph(name="drift-in", nodes=[NfNode("n", "fastp", ins=["bam"], outs=["fastq"])])
    with pytest.raises(CompileError, match="diverge"):
        compile_graph(g)


def test_catalogued_node_emitting_an_uncatalogued_output_is_rejected() -> None:
    """A catalogued node declaring an output the spec never emits would wire a `.out.<kind>` channel
    that doesn't exist — rejected."""
    g = NfGraph(
        name="drift-out",
        nodes=[NfNode("n", "fastp", ins=["fastq"], outs=["fastq", "ghost_out"])],
    )
    with pytest.raises(CompileError, match="never produces"):
        compile_graph(g)


def test_a_reordered_output_subset_still_compiles() -> None:
    """A catalogued node MAY trim/reorder its outputs (an unused catalogued output is harmless and
    the Builder legitimately drops them) — only a genuinely uncatalogued output is rejected."""
    g = NfGraph(
        name="subset",
        nodes=[NfNode("fp", "fastp", ins=["fastq"], outs=["fastp_json", "fastq"])],  # reordered
    )
    bundle = compile_graph(g)  # must not raise
    assert "modules/fastp.nf" in bundle.files


# ── golden-path re-assertion (the fixes are off-path only) ────────────────────────────────────────
def test_germline_still_compiles_byte_for_byte() -> None:
    """The robustness fixes are NO-OPs on the germline chain: it still compiles byte-for-byte to the
    committed reference pipeline (a second guard alongside test_nextflow_compile.py)."""
    assert _REFERENCE.is_dir(), "run scripts/generate_reference_pipeline.py to (re)generate it"
    bundle = compile_graph(germline_graph())
    for rel, content in bundle.files.items():
        committed = _REFERENCE / rel
        assert committed.is_file(), f"missing committed file {rel}"
        assert committed.read_text(encoding="utf-8") == content, f"drift in {rel} — regenerate"


def test_custom_script_node_still_compiles() -> None:
    """An operator-authored custom-script node still renders a real process wired from its edge —
    the identifier/port-drift guards do not touch the custom path (custom nodes skip port-drift)."""
    g = NfGraph(
        name="clinvar-annot",
        nodes=[
            NfNode(
                "n_call",
                "bcftools call",
                ins=["bam", "reference_fasta", "panel_bed"],
                outs=["vcf"],
            ),
            NfNode(
                "n_annot",
                "bcftools annotate",
                ins=["vcf"],
                outs=["vcf"],
                script="bcftools annotate -a clinvar.vcf.gz -c INFO/CLNSIG $vcf",
            ),
        ],
        edges=[NfEdge("n_call", 0, "n_annot", 0)],
    )
    bundle = compile_graph(g)
    module = bundle.files["modules/bcftools_annotate.nf"]
    assert "label 'operator_authored'" in module
    assert "BCFTOOLS_ANNOTATE(BCFTOOLS_CALL.out.vcf)" in bundle.main_nf
