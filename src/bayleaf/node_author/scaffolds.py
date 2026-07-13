"""Starter scaffolds for onboarding a new tool (P3 §3, design/agent-capabilities.md §3.4).

The node-author proposes METADATA (typed ports, a pinned version, locators). Turning that into a
runnable tool still needs a HUMAN to author three conformant artifacts: a `ProcessSpec` catalog
entry, the Nextflow `process` (`script:`/`stub:`), and — if it emits a QC metric — a metric-registry
entry. This module renders those as **filled-in DRAFT scaffolds** from a proposal so the human edits
a conformant skeleton (ports + names already wired from the corpus) rather than free-composing —
quicker + more reproducible, and the shape conforms by construction.

Hard boundary (ADR-0001/0003): every scaffold is a labelled DRAFT with the runnable command left as
an explicit ``TODO`` — the agent NEVER authors a `script:`/`stub:` body or a real command; it lays
out the skeleton and a human fills the compute. Rendering runs no tool and sets no verdict.
"""

from __future__ import annotations

import re

from .models import NodeProposal, PortSpec


def _process_name(tool: str) -> str:
    """UPPER_SNAKE Nextflow process name from a tool key ('bcftools call' → 'BCFTOOLS_CALL')."""
    return re.sub(r"[^A-Za-z0-9]+", "_", tool).strip("_").upper() or "TOOL"


def _card_ports(ports: tuple[PortSpec, ...] | list[PortSpec], *, output: bool) -> str:
    """Render proposal ports as `Port(...)` literals for the ProcessSpec scaffold (kinds are real;
    the path glob is a labelled TODO — the human names the actual file)."""
    if not ports:
        return "        # (none proposed)"
    lines: list[str] = []
    for p in ports:
        note = f"  # {p.note}" if p.note else ""
        reserved = "" if p.known else "  # RESERVED kind — register in ARTIFACT_KINDS before wiring"
        if output:
            lines.append(
                f"        Port({p.kind!r}, 'path(\"<TODO: *.{p.kind}>\")', emit={p.kind!r}),"
                f"{note}{reserved}"
            )
        else:
            opt = "" if p.required else "  # optional"
            lines.append(f"        Port({p.kind!r}, 'path(\"<TODO>\")'),{note}{reserved}{opt}")
    return "\n".join(lines)


def _nf_ports(ports: tuple[PortSpec, ...] | list[PortSpec], *, output: bool) -> str:
    kw = "output" if output else "input"
    if not ports:
        return f"    {kw}:\n        // (none proposed)"
    decls = [
        f'        path("<TODO>")  // {p.kind}{"" if p.required else " (optional)"}' for p in ports
    ]
    return f"    {kw}:\n" + "\n".join(decls)


def render_scaffolds(proposal: NodeProposal) -> dict[str, str]:
    """Filled DRAFT scaffolds for a matched proposal, keyed by artifact filename. Empty for an
    unmatched (defer-to-human) proposal — there is no tool to scaffold."""
    if not proposal.matched or not proposal.tool:
        return {}
    tool = proposal.tool
    name = _process_name(tool)
    version = proposal.version or "<TODO: pin a version>"
    stage = proposal.stage or ""

    tool_card = f'''# DRAFT ProcessSpec scaffold for "{tool}" ({version}) — add to the catalog.
# The node-author proposed the ports/version below; a HUMAN authors conda/container/script/stub.
# Compose != execute (ADR-0003): the agent never writes the runnable command.
ProcessSpec(
    tool={tool!r},
    process={name!r},
    conda="bioconda::{tool.split()[0]}=<TODO: version>",
    container="<TODO: biocontainer image>",
    label={stage!r},
    inputs=(
{_card_ports(proposal.inputs, output=False)}
    ),
    outputs=(
{_card_ports(proposal.outputs, output=True)}
    ),
    script="""<TODO: the real command; stage inputs, emit the outputs above>""",
    stub="""<TODO: touch each output so -stub-run validates wiring with no tools/data>""",
)'''

    process_nf = f'''// DRAFT Nextflow process scaffold for "{tool}" — a HUMAN fills script/stub.
process {name} {{
    tag "${{meta.id}}"
{_nf_ports(proposal.inputs, output=False)}
{_nf_ports(proposal.outputs, output=True)}

    script:
    """
    <TODO: the real {tool} command>
    """

    stub:
    """
    <TODO: touch the declared outputs>
    """
}}'''

    scaffolds = {"tool_card.py": tool_card, "process.nf": process_nf}

    qc_outputs = [p for p in proposal.outputs if p.role == "qc"]
    if qc_outputs:
        rows = "\n".join(
            f'#   our_key="{p.kind}", category="<TODO>", unit="<TODO>", required=False'
            for p in qc_outputs
        )
        scaffolds["metric_registry_entry.md"] = (
            f"# DRAFT metric-registry entries for {tool} QC outputs (see metric_registry.md).\n"
            "# A registered metric is NOT gated until the runbook adds a threshold (illustrative,\n"
            "# never clinical). A HUMAN registers these:\n" + rows
        )
    return scaffolds
