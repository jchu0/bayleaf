"""The doc-drop importer (node-author W2 "bring your own tools") — deterministic, offline.

``import_from_nextflow_schema`` parses an nf-core ``nextflow_schema.json`` into an advisory
:class:`NodeProposal` for a tool that need NOT be in the 11-card corpus — the deferred "bring your
own tools" slice, scoped this pass to the structured (lowest-injection-risk) schema input. These
tests pin the guardrails: file-path params map to typed ports, a kind outside the real vocabulary
is surfaced RESERVED (never invented as a live wire), no outputs/command body are fabricated, and
the result passes the conformance harness by construction.
"""

from __future__ import annotations

import json

from pipeguard.node_author import (
    ARTIFACT_KINDS,
    check_conformance,
    import_from_nextflow_schema,
    propose_node,
)

# An nf-core-style schema: a title, an I/O group with file-path params (some map to real kinds, one
# — cram — does not), a directory-path `outdir` (not a typed artifact), and a scalar param.
_SCHEMA = {
    "$id": "https://raw.githubusercontent.com/nf-core/demo/master/nextflow_schema.json",
    "title": "nf-core/demo pipeline parameters",
    "type": "object",
    "definitions": {
        "input_output_options": {
            "title": "Input/output options",
            "required": ["reads", "fasta"],
            "properties": {
                "reads": {"format": "file-path", "pattern": r"^\S+\.fastq\.gz$"},
                "fasta": {"format": "file-path", "pattern": r"^\S+\.fasta$"},
                "targets": {"format": "file-path", "pattern": r"^\S+\.bed$"},
                "known_sites": {"format": "file-path", "pattern": r"^\S+\.vcf\.gz$"},
                "cram": {"format": "file-path", "pattern": r"^\S+\.cram$"},
                "outdir": {"format": "directory-path"},
                "multiqc_title": {"type": "string"},
            },
        }
    },
}


def test_imports_a_new_tool_not_in_the_corpus() -> None:
    proposal = import_from_nextflow_schema(_SCHEMA)
    assert proposal.advisory is True
    assert proposal.matched is True
    assert proposal.tool == "demo"  # derived from the nf-core title, boilerplate stripped
    assert proposal.version == "unknown"  # a params schema rarely declares a version — honest
    assert proposal.generated_by == "stub"  # deterministic import, $0
    # This is a tool the curated corpus does not have — proving "bring your own tools".
    assert propose_node("demo").matched is False


def test_file_path_params_become_typed_ports_scalars_and_dirs_skipped() -> None:
    proposal = import_from_nextflow_schema(_SCHEMA)
    kinds = {p.kind for p in proposal.inputs}
    # 5 file-path params → 5 input ports; outdir (directory-path) + multiqc_title (scalar) skipped.
    assert len(proposal.inputs) == 5
    assert {"fastq", "reference_fasta", "panel_bed", "vcf", "cram"} == kinds
    # A params schema declares no typed outputs, so none are fabricated.
    assert proposal.outputs == []
    assert proposal.locators == []


def test_unknown_kind_is_reserved_never_invented_as_a_live_wire() -> None:
    proposal = import_from_nextflow_schema(_SCHEMA)
    live = {p.kind for p in proposal.inputs if p.known}
    reserved = {p.kind for p in proposal.inputs if not p.known}
    assert live == {"fastq", "reference_fasta", "panel_bed", "vcf"}
    assert live <= ARTIFACT_KINDS  # every live kind is a real vocabulary kind
    assert reserved == {"cram"}  # cram is outside the vocabulary → reserved, not invented
    assert proposal.reserved_kinds == ["cram"]


def test_required_flag_tracks_the_schema_required_list() -> None:
    ports = {p.kind: p for p in import_from_nextflow_schema(_SCHEMA).inputs}
    assert ports["fastq"].required is True  # 'reads' is in the group's required list
    assert ports["reference_fasta"].required is True  # 'fasta' is required
    assert ports["cram"].required is False  # not required


def test_imported_proposal_passes_conformance_and_carries_no_verdict_or_command() -> None:
    proposal = import_from_nextflow_schema(_SCHEMA)
    assert check_conformance(proposal) == []
    dumped = proposal.model_dump()
    assert "verdict" not in dumped and "confidence" not in dumped
    assert "script" not in dumped and "stub" not in dumped  # compose != execute
    # Citations anchor the proposal to the dropped doc + the tool — no fabricated corpus hit.
    source_kinds = {c.source_kind for c in proposal.citations}
    assert source_kinds == {"card_doc", "tool"}


def test_tool_and_version_overrides_win() -> None:
    proposal = import_from_nextflow_schema(_SCHEMA, tool="myaligner", version="2.1.0")
    assert proposal.tool == "myaligner"
    assert proposal.version == "2.1.0"


def test_accepts_json_text_and_the_newer_defs_key() -> None:
    # JSON text is parsed tolerantly; the newer "$defs" grouping key is handled like "definitions".
    schema_defs = {
        "title": "nf-core/variantcall pipeline parameters",
        "$defs": {"io": {"properties": {"bam": {"format": "file-path", "pattern": r"^\S+\.bam$"}}}},
    }
    proposal = import_from_nextflow_schema(json.dumps(schema_defs))
    assert proposal.tool == "variantcall"
    assert [p.kind for p in proposal.inputs] == ["bam"]


def test_garbage_input_degrades_to_an_empty_conformant_proposal() -> None:
    # Malformed JSON / an empty schema must not crash — a tolerant, empty, conformant proposal.
    proposal = import_from_nextflow_schema("{not valid json")
    assert proposal.tool == "imported_tool"
    assert proposal.inputs == []
    assert check_conformance(proposal) == []
