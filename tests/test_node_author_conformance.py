"""The node-author conformance harness (W2 boundaries contract) — pure, offline.

``check_conformance`` is the tripwire that keeps ``docs/design/agent-authoring-contract.md``
non-decorative: it mechanically asserts the capability pins against a candidate proposal. These
tests prove (a) a real, corpus-grounded proposal — matched OR the defer-to-human one — passes
clean, and (b) a raw dict smuggling each forbidden thing (a verdict/confidence field, a
``script:``/``stub:`` command body, an invented live port, a mislabelled reserved kind, a missing
version stamp) is caught with the right stable code.
"""

from __future__ import annotations

from typing import Any

from pipeguard.node_author import (
    NodeProposal,
    check_conformance,
    import_from_nextflow_schema,
    is_conformant,
    propose_node,
)

# A minimal, fully-conformant candidate dict — the base each violation test mutates.
_CONFORMANT: dict[str, Any] = {
    "advisory": True,
    "matched": True,
    "tool": "fastp",
    "version": "0.23.4",
    "inputs": [{"kind": "fastq", "known": True}],
    "outputs": [{"kind": "bam", "known": True}],
    "reserved_kinds": [],
    "corpus_version": "1.0.0",
    "schema_version": 1,
    "platform_version": "0.1.0",
}


def _codes(candidate: NodeProposal | dict[str, Any]) -> set[str]:
    return {v.code for v in check_conformance(candidate)}


# --- real proposals pass clean ---------------------------------------------------------------


def test_matched_proposal_is_conformant() -> None:
    proposal = propose_node("fastp")  # matched; reserved ports (adapter_fasta) declared reserved
    assert check_conformance(proposal) == []
    assert is_conformant(proposal) is True


def test_defer_to_human_proposal_is_conformant() -> None:
    # An unmatched proposal (no tool/ports/version) is still conformant — matched=False lifts the
    # tool-version requirement, and it carries no verdict/command/invented port.
    proposal = propose_node("qwerty zxcvb nonsense request")
    assert proposal.matched is False
    assert check_conformance(proposal) == []


def test_imported_proposal_is_conformant() -> None:
    schema = {
        "title": "nf-core/demo pipeline parameters",
        "definitions": {
            "io": {
                "properties": {
                    "input": {"format": "file-path", "pattern": r"^\S+\.fastq\.gz$"},
                    "cram": {"format": "file-path", "pattern": r"^\S+\.cram$"},
                }
            }
        },
    }
    assert check_conformance(import_from_nextflow_schema(schema)) == []


def test_bare_conformant_dict_has_no_violations() -> None:
    assert check_conformance(_CONFORMANT) == []


# --- each forbidden thing is caught ----------------------------------------------------------


def test_missing_or_false_advisory_flag_is_flagged() -> None:
    assert "not_advisory" in _codes({**_CONFORMANT, "advisory": False})
    no_flag = {k: v for k, v in _CONFORMANT.items() if k != "advisory"}
    assert "not_advisory" in _codes(no_flag)


def test_verdict_and_confidence_fields_are_flagged_at_any_depth() -> None:
    assert "verdict_field_present" in _codes({**_CONFORMANT, "verdict": "PROCEED"})
    assert "confidence_field_present" in _codes({**_CONFORMANT, "confidence": 0.9})
    # Nested inside a port, too — the scan is recursive.
    nested = {**_CONFORMANT, "inputs": [{"kind": "fastq", "known": True, "verdict": "HOLD"}]}
    assert "verdict_field_present" in _codes(nested)


def test_script_and_stub_command_bodies_are_flagged() -> None:
    # A command body is forbidden as a KEY anywhere — this is the compose != execute tripwire.
    assert "script_body_present" in _codes({**_CONFORMANT, "script": "bwa mem ..."})
    nested = {**_CONFORMANT, "outputs": [{"kind": "bam", "known": True, "stub": "touch out.bam"}]}
    assert "stub_body_present" in _codes(nested)


def test_generated_by_stub_value_is_not_a_violation() -> None:
    # ``generated_by``/``mode`` legitimately hold the VALUE "stub"; only a KEY named stub is a body.
    ok = {**_CONFORMANT, "generated_by": "stub", "mode": "stub"}
    assert "stub_body_present" not in _codes(ok)
    assert check_conformance(ok) == []


def test_invented_live_port_is_flagged() -> None:
    # A kind outside ARTIFACT_KINDS that is NOT declared reserved is an invented live wire.
    bad = {**_CONFORMANT, "inputs": [{"kind": "made_up_kind", "known": True}]}
    codes = _codes(bad)
    assert "port_kind_not_reserved" in codes
    assert "port_known_mismatch" in codes  # known=True disagrees with kind-in-vocabulary=False


def test_unknown_port_declared_reserved_is_ok() -> None:
    ok = {
        **_CONFORMANT,
        "inputs": [{"kind": "made_up_kind", "known": False}],
        "reserved_kinds": ["made_up_kind"],
    }
    assert check_conformance(ok) == []


def test_reserved_kind_that_is_actually_real_is_flagged() -> None:
    bad = {**_CONFORMANT, "reserved_kinds": ["bam"]}  # bam IS a real vocabulary kind
    assert "reserved_kind_actually_known" in _codes(bad)


def test_missing_version_stamps_are_flagged() -> None:
    for field in ("corpus_version", "schema_version", "platform_version"):
        dropped = {k: v for k, v in _CONFORMANT.items() if k != field}
        assert f"missing_{field}" in _codes(dropped)


def test_matched_proposal_without_a_tool_version_is_flagged() -> None:
    assert "missing_tool_version" in _codes({**_CONFORMANT, "version": None})
    assert "missing_tool_version" in _codes({**_CONFORMANT, "version": "  "})
    # But an UNmatched proposal without a version is fine (nothing to pin).
    unmatched = {**_CONFORMANT, "matched": False, "version": None, "tool": None}
    assert "missing_tool_version" not in _codes(unmatched)
