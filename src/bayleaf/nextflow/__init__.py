"""Compile a Pipeline-Builder card graph into a runnable nf-core-style Nextflow (DSL2) pipeline.

This is the module that makes ADR-0003's "Nextflow carries compute portability" claim **executable**
rather than aspirational: the Builder composes a typed-port DAG of tool cards, and this package
turns that DAG into a real `main.nf` + `modules/*.nf` + `nextflow.config` a user can `nextflow run`.

Framework-agnostic and PURE (CLAUDE.md architecture guardrail 1): it emits TEXT — it never invokes
Nextflow or any tool, so **compose ≠ execute** (ADR-0003) holds at the core exactly as it does for
the rest of `src/bayleaf/`. The API layer adapts a stored `PipelineGraph` JSON to `NfGraph` and
serves/uses the result; only that outer layer ever shells out to `nextflow run`.
"""

from __future__ import annotations

from .catalog import PROCESS_CATALOG, ProcessSpec, catalog_entry
from .compiler import (
    CompileError,
    NextflowBundle,
    NfEdge,
    NfGraph,
    NfNode,
    compile_graph,
    required_inputs,
)
from .germline import germline_graph

__all__ = [
    "PROCESS_CATALOG",
    "CompileError",
    "NextflowBundle",
    "NfEdge",
    "NfGraph",
    "NfNode",
    "ProcessSpec",
    "catalog_entry",
    "compile_graph",
    "germline_graph",
    "required_inputs",
]
