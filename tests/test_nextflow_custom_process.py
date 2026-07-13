"""Operator-authored custom-script Nextflow processes (ADR-0020).

A Builder card MAY carry an operator-authored `script:` body: a HUMAN provides a Nextflow process
body that runs on a pipeline output (e.g. `bcftools annotate` over a called VCF). These tests pin
the safety + honesty properties that make that feature trustworthy:

1. A custom node renders a REAL process from the node's OWN verbatim script + typed ins/outs, wired
   from the edges exactly like a catalogued tool, and the tool catalog is NEVER consulted for it —
   even if the custom tool name collides with a catalogued one.
2. An honest header comment + a process `label` mark it operator-authored / not curated.
3. A blank/whitespace custom script is a `CompileError`, never a fabricated command; an
   uncatalogued-AND-no-script node keeps its existing labelled placeholder.
4. A port kind outside the known artifact vocabulary is allowed and wired by name (no crash).
5. Compose ≠ execute: the compiler returns TEXT and spawns no subprocess.
6. The seeded germline chain carries no custom node — its byte-for-byte reference output (the drift
   guard) stays green.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from bayleaf.nextflow import (
    CompileError,
    NextflowBundle,
    NfEdge,
    NfGraph,
    NfNode,
    compile_graph,
    germline_graph,
)

_REPO = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO / "pipelines" / "germline"

# The operator's verbatim body for a ClinVar-annotation custom card — runs on a called VCF.
_ANNOTATE_SCRIPT = "bcftools annotate -a clinvar.vcf.gz -c INFO/CLNSIG $vcf > ${meta.id}.annot.vcf"


def _annotate_graph(*, script: str = _ANNOTATE_SCRIPT, tool: str = "bcftools annotate") -> NfGraph:
    """A minimal graph: a catalogued `bcftools call` (→ vcf) feeding an OPERATOR-AUTHORED custom
    annotation process (vcf in → vcf out). The edge is what the custom node's channel wiring must
    resolve to `BCFTOOLS_CALL.out.vcf`."""
    return NfGraph(
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
                tool,
                ins=["vcf"],
                outs=["vcf"],
                script=script,
                container="quay.io/biocontainers/bcftools:1.20--h8b25389_0",
                conda="bioconda::bcftools=1.20",
            ),
        ],
        edges=[NfEdge("n_call", 0, "n_annot", 0)],
    )


# ── (a) a custom node renders verbatim, wired from the edge, honestly labelled ───────────────────
def test_custom_process_renders_verbatim_wired_and_labelled() -> None:
    files = compile_graph(_annotate_graph()).files
    module = files["modules/bcftools_annotate.nf"]

    # The operator's command body appears VERBATIM (only re-indented, as the catalogued path is).
    assert _ANNOTATE_SCRIPT in module
    # The honest header + label mark it operator-authored / not a curated tool (ADR-0020 pin [ii]).
    assert "operator-authored custom process — runs on the compute host; production needs" in module
    assert "sandboxing/allowlisting" in module
    assert "not a curated/catalogued tool" in module
    assert "label 'operator_authored'" in module
    # It is a REAL process, not the uncatalogued placeholder (no fabricated `exit 1` command).
    assert "process BCFTOOLS_ANNOTATE {" in module
    assert "PLACEHOLDER" not in module and "exit 1" not in module
    # The operator's own packaging is threaded through.
    assert "container 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'" in module
    assert "conda 'bioconda::bcftools=1.20'" in module
    # Ports are meta-threaded + wired by kind so the operator addresses `${vcf}` and downstream can
    # wire `.out.vcf`; the process runs per sample.
    assert "tuple val(meta), path(vcf)" in module
    assert "emit: vcf" in module
    assert 'tag "${meta.id}"' in module

    # The channel wiring comes straight from the typed edge, exactly like a catalogued tool.
    main = files["main.nf"]
    assert "BCFTOOLS_ANNOTATE(BCFTOOLS_CALL.out.vcf)" in main


def test_custom_node_never_consults_the_catalog_even_on_a_name_collision() -> None:
    """A custom card that reuses a CATALOGUED tool name must still render the operator's body, never
    the curated command — the catalog is not consulted for a custom node (ADR-0020, task 2)."""
    # `bcftools norm` IS catalogued (a real `bcftools norm -f …` command); author a custom body over
    # that same name and confirm the curated command does NOT leak in.
    files = compile_graph(_annotate_graph(tool="bcftools norm")).files
    module = files["modules/bcftools_norm.nf"]
    assert _ANNOTATE_SCRIPT in module  # the operator's body
    assert "label 'operator_authored'" in module
    assert "bcftools norm -f" not in module  # the catalogued command was NOT consulted


# ── (b) a blank custom script is rejected, never fabricated ──────────────────────────────────────
@pytest.mark.parametrize("blank", ["", "   ", "\n\t \n"])
def test_empty_custom_script_is_a_compile_error(blank: str) -> None:
    g = NfGraph(
        name="blank-custom",
        nodes=[NfNode("x", "mystery-tool", ins=["vcf"], outs=["vcf"], script=blank)],
    )
    with pytest.raises(CompileError, match="empty script"):
        compile_graph(g)


def test_uncatalogued_no_script_node_keeps_its_placeholder_not_an_error() -> None:
    """An uncatalogued tool with NO script (`script is None`) is unchanged — it still compiles to
    the labelled placeholder, never rejected. Only a declared-but-blank custom card is an error."""
    g = NfGraph(
        name="unknown",
        nodes=[
            NfNode("a", "fastp", ins=["fastq"], outs=["fastq", "fastp_json"]),
            NfNode("b", "deepvariant", ins=["fastq"], outs=["vcf"]),
        ],
        edges=[NfEdge("a", 0, "b", 0)],
    )
    placeholder = compile_graph(g).files["modules/deepvariant.nf"]
    assert "PLACEHOLDER" in placeholder and "exit 1" in placeholder
    assert "operator_authored" not in placeholder  # not mislabelled as a custom process


# ── (c) germline drift stays green — a custom node is purely additive ─────────────────────────────
def test_germline_carries_no_custom_node_and_drift_stays_green() -> None:
    bundle = compile_graph(germline_graph())
    # No germline node is custom, so nothing renders the operator-authored header anywhere.
    for content in bundle.files.values():
        assert "operator-authored custom process" not in content
        assert "operator_authored" not in content
    # And the committed reference pipeline is still byte-for-byte the compiler output (drift guard).
    assert _REFERENCE.is_dir(), "run scripts/generate_reference_pipeline.py to (re)generate it"
    for rel, content in bundle.files.items():
        committed = _REFERENCE / rel
        assert committed.is_file(), f"missing committed file {rel}"
        assert committed.read_text(encoding="utf-8") == content, f"drift in {rel} — regenerate"


# ── (d) compose ≠ execute — the compiler emits text and runs nothing ──────────────────────────────
def test_compile_returns_text_and_spawns_no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: Any, **_k: Any) -> Any:  # pragma: no cover - only fires on a broken invariant
        raise AssertionError("the compiler must never spawn a subprocess (compose ≠ execute)")

    # If the pure codegen ever shelled out, these would fire; instead compile succeeds untouched.
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)

    bundle = compile_graph(_annotate_graph())
    assert isinstance(bundle, NextflowBundle)
    assert all(isinstance(v, str) for v in bundle.files.values())
    assert isinstance(bundle.main_nf, str)


# ── (4) a novel output kind is allowed and wired by name, never a crash ───────────────────────────
def test_custom_process_may_emit_a_kind_outside_the_known_vocabulary() -> None:
    """A custom process may emit a novel artifact kind not in the built-in vocabulary; the compiler
    wires it by its raw name (`emit: <kind>`) and never crashes on an unknown kind (ADR-0020)."""
    g = NfGraph(
        name="novel-kind",
        nodes=[
            NfNode(
                "n",
                "cnv-caller",
                ins=["bam"],
                outs=["cnv_segments"],  # not a built-in artifact kind
                script="my-cnv-tool --in ${bam} --out sample.cnv.bed",
            )
        ],
    )
    module = compile_graph(g).files["modules/cnv_caller.nf"]
    assert "emit: cnv_segments" in module
    assert "my-cnv-tool --in ${bam} --out sample.cnv.bed" in module
