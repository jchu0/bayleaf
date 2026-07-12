"""Doc-drop importer — propose a *genuinely new* tool from a dropped doc (W2 "bring your tools").

The shipped node-author agent is **corpus-bound**: it can only retrieve one of the 11 curated
tool-cards, so it cannot onboard a tool it has never seen (``node-authoring-agent.md``). This module
is the deferred "bring your own tools" slice: it deterministically parses a **dropped doc** into a
:class:`~pipeguard.node_author.NodeProposal` for a tool that need not be in the corpus.

**Scope this pass:** the structured, lowest-injection-risk input — an nf-core
``nextflow_schema.json`` (:func:`import_from_nextflow_schema`). The free-text inputs the design note
also lists (``--help`` output, a README) are **deferred** — they are the unbounded-input, higher
parse/injection-risk half and want their own spike + safety tests.

**Guardrails, structural (agent-authoring-contract.md):**

  1. **Metadata, not commands (compose ≠ execute).** The importer maps schema params → typed
     *ports* only. It NEVER emits a ``script:``/``stub:`` body — those fields do not exist on any
     shape it writes (a human authors the runnable ``ProcessSpec`` later).
  2. **Closed vocabulary; unknown → reserved, never invented.** A param maps to a real
     :data:`ARTIFACT_KINDS` kind only on a confident, conservative match; anything else becomes a
     ``reserved`` port (a kind structurally outside the vocabulary), surfaced-not-wired. This is
     enforced by :attr:`PortSpec.known` — the importer cannot fabricate a live wire.
  3. **Advisory + no verdict/confidence.** The output is a :class:`NodeProposal` (``advisory``
     pinned ``True``, no gate field); it changes nothing until a human reviews and wires it.
  4. **Deterministic + stub-first ($0).** No network call, no env read: same doc → same proposal.
     A live Claude path would refine only the ``summary``/``rationale`` **prose** (as the agent
     does) — a labelled, not-yet-wired seam here; the structure is 100% deterministic.

The result is designed to pass :func:`~pipeguard.node_author.check_conformance` by construction.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .agent import NODE_AUTHOR_AGENT
from .models import ARTIFACT_KINDS, LocatorSuggestion, NodeCitation, NodeProposal, PortSpec

# Conservative, ordered name/pattern/mimetype hints → a real artifact kind + its card role. Only a
# confident match maps to a live vocabulary kind; everything else falls through to a reserved slot
# (see ``_infer_kind``). Ordered most-specific first so ``reference_vcf`` matches ``vcf`` (a known
# sites file) before the generic ``reference`` → fasta hint. This is an ADVISORY best-effort mapping
# a human reviews — never an authoritative type assignment.
_KIND_HINTS: tuple[tuple[str, str, str], ...] = (
    ("fastq", "fastq", "data"),
    ("truth", "truth_vcf", "reference"),
    ("giab", "truth_vcf", "reference"),
    (".vcf", "vcf", "data"),
    ("vcf", "vcf", "data"),
    (".bam", "bam", "data"),
    ("bam", "bam", "data"),
    ("fasta", "reference_fasta", "reference"),
    (".fa", "reference_fasta", "reference"),
    ("genome", "reference_fasta", "reference"),
    (".bed", "panel_bed", "reference"),
    ("bed", "panel_bed", "reference"),
    ("panel", "panel_bed", "reference"),
    ("interval", "panel_bed", "reference"),
    ("target", "panel_bed", "reference"),
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """A lowercase ``_``-joined slug (for a reserved kind derived from a param name)."""
    return _SLUG_RE.sub("_", text.lower()).strip("_")


def _infer_kind(name: str, param: Mapping[str, Any]) -> tuple[str, str]:
    """Map one schema param → (kind, role). A confident hint → a real kind; else a RESERVED slug.

    The reserved slug is derived from the param name and guaranteed OUTSIDE :data:`ARTIFACT_KINDS`
    (prefixed ``reserved_`` if it would otherwise collide), so :attr:`PortSpec.known` computes
    ``False`` and the port is surfaced as an inert, labelled slot — never an invented live wire.
    """
    haystack = " ".join(str(param.get(k, "")) for k in ("pattern", "mimetype", "description"))
    haystack = f"{name} {haystack}".lower()
    for token, kind, role in _KIND_HINTS:
        if token in haystack:
            return kind, role
    slug = _slug(name) or "param"
    if slug in ARTIFACT_KINDS:  # never let a fallback slug alias a real kind (would mislabel it)
        slug = f"reserved_{slug}"
    return slug, "data"


def _iter_param_groups(schema: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every ``properties`` block in the schema, in a deterministic order.

    nf-core nests params under ``definitions`` (older) or ``$defs`` (newer) groups, each with its
    own ``properties`` + optional ``required`` list; a schema may also carry top-level
    ``properties``. Yields each such block (a dict with ``properties`` + maybe ``required``) so the
    caller walks them in insertion order — groups first, then any top-level properties.
    """
    groups: list[Mapping[str, Any]] = []
    for container_key in ("definitions", "$defs"):
        container = schema.get(container_key)
        if isinstance(container, Mapping):
            for group in container.values():
                if isinstance(group, Mapping) and isinstance(group.get("properties"), Mapping):
                    groups.append(group)
    if isinstance(schema.get("properties"), Mapping):
        groups.append({"properties": schema["properties"], "required": schema.get("required", [])})
    return groups


def _tool_name(schema: Mapping[str, Any], override: str | None) -> str:
    """Derive the tool name from an explicit override, else the schema ``title`` / ``$id``.

    An nf-core ``title`` reads ``"nf-core/<name> pipeline parameters"`` — strip the boilerplate and
    take the last path segment. Falls back to the ``$id`` basename, then a labelled placeholder.
    """
    if override and override.strip():
        return override.strip()
    title = str(schema.get("title", "")).strip()
    if title:
        cleaned = re.sub(r"\bpipeline parameters\b", "", title, flags=re.IGNORECASE).strip()
        cleaned = cleaned.rstrip("/").strip()
        if cleaned:
            return cleaned.split("/")[-1]
    ref = str(schema.get("$id", "")).strip()
    if ref:
        base = ref.rstrip("/").split("/")[-1]
        base = re.sub(r"\.json$", "", base, flags=re.IGNORECASE)
        if base and base != "nextflow_schema":
            return base
    return "imported_tool"


def import_from_nextflow_schema(
    schema: Mapping[str, Any] | str,
    *,
    tool: str | None = None,
    version: str | None = None,
    request: str | None = None,
) -> NodeProposal:
    """Parse an nf-core ``nextflow_schema.json`` into an advisory :class:`NodeProposal`.

    ``schema`` is the parsed schema dict OR its JSON text (parsed tolerantly). ``tool`` /
    ``version`` override the values derived from the schema (a params schema rarely declares a
    version, so it defaults to ``"unknown"`` — honest, not fabricated). Every ``format: file-path``
    param becomes a typed INPUT port; a params schema does not declare typed outputs, so none are
    fabricated (a human adds them when authoring the ``ProcessSpec``). The result is deterministic
    and conformant by construction — it never emits a command body, an invented port, or a verdict.

    Deferred (not built): ``--help`` / README free-text parsing, and a live Claude prose refinement
    of the ``summary``/``rationale`` — both are labelled seams (see the module docstring).
    """
    if isinstance(schema, str):
        try:
            parsed = json.loads(schema)
        except ValueError:
            parsed = {}
        schema = parsed if isinstance(parsed, Mapping) else {}

    name = _tool_name(schema, tool)
    pinned_version = (version or "").strip() or "unknown"

    inputs: list[PortSpec] = []
    seen: set[str] = set()
    for group in _iter_param_groups(schema):
        properties = group.get("properties")
        required_names = set(group.get("required") or []) if isinstance(group, Mapping) else set()
        if not isinstance(properties, Mapping):
            continue
        for param_name, param in properties.items():
            if not isinstance(param, Mapping):
                continue
            # Only typed file artifacts become ports; a directory-path (e.g. `outdir`) or a scalar
            # param is not a typed artifact port, so it is deliberately skipped.
            if param.get("format") != "file-path":
                continue
            if param_name in seen:
                continue  # first declaration wins (deterministic dedupe)
            seen.add(param_name)
            kind, role = _infer_kind(param_name, param)
            note = str(param.get("description", "")).strip() or f"schema param '{param_name}'"
            inputs.append(
                PortSpec(
                    kind=kind,
                    required=param_name in required_names,
                    role=role,  # a PortRole literal ('data'|'reference') from _KIND_HINTS
                    note=note[:280],
                )
            )

    reserved = sorted({p.kind for p in inputs if not p.known})
    source_ref = str(schema.get("$id") or schema.get("title") or "nextflow_schema.json").strip()
    citations = [
        NodeCitation(
            source_kind="card_doc",
            ref=source_ref or "nextflow_schema.json",
            title=str(schema.get("title") or "nextflow_schema.json"),
        ),
        NodeCitation(source_kind="tool", ref=name, title=f"{name} {pinned_version}"),
    ]

    n_live = sum(1 for p in inputs if p.known)
    summary = (
        f"Imported tool node '{name}' ({pinned_version}) from a Nextflow schema: "
        f"{len(inputs)} typed input port(s) ({n_live} live, {len(reserved)} reserved). "
        "Advisory — review the ports and pin a real version before a human authors its ProcessSpec."
    )
    rationale = (
        "Ports were mapped deterministically from the schema's file-path params; kinds outside the "
        "real artifact vocabulary are surfaced as reserved (never wired). A params schema declares "
        "inputs only, so no outputs are fabricated. This is a proposal for human review — it runs "
        "no tool and sets no verdict; the runnable command is authored separately by a human."
    )

    return NodeProposal(
        agent=NODE_AUTHOR_AGENT,
        request=(request or f"import {name} from nextflow_schema.json"),
        matched=True,
        tool=name,
        version=pinned_version,
        stage=None,  # a schema does not name a pipeline stage; a human assigns it on review
        inputs=inputs,
        outputs=[],
        locators=list[LocatorSuggestion](),  # a params schema declares no output locators
        reserved_kinds=reserved,
        summary=summary,
        rationale=rationale,
        citations=citations,
        generated_by="stub",  # deterministic import; a live prose refinement is a labelled seam
        model=None,
    )
