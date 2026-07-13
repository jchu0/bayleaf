"""PHASE 4 — an attached advisory agent's SCOPED READ of a bound node's published outputs.

This is the read mechanism behind the Wave-2 agent-binding model (``frontend/src/types.ts``
``AgentBinding {agent, node, grants:('outputs'|'logs')[]}``, carried CLIENT-SIDE in the Builder
graph envelope ``graph.agent_bindings``). The binding expresses INTENT — an advisory agent (e.g.
QC-triage) should observe ONE graph node's results, a **narrowing** of what agents already see (the
whole analysis-output tree). **Honest scope (WS-08):** the server does NOT persist or enforce that
per-agent binding — there is no server-side ``AgentBinding`` model, and no run records which graph
it executed. So access here is NOT gated by the binding; it is gated by (1) the node SCOPE (outputs
matched to the node's own catalogued output globs — never a sibling's files, enforced below) and
(2) the WIRE ROLE (``outputs``: viewer+; the PII-adjacent ``logs``: reviewer+). Real per-agent
enforcement (load the run's bindings, match the requesting agent, intersect grants) is a documented
deferral: it needs server-side binding persistence **and** a run→executed-graph linkage, neither of
which exists today. The binding is an advisory client-side hint, not an access-control boundary:

  ``GET /api/runs/{run_id}/nodes/{node_id}/observations?grants=outputs[,logs]``

returns the agent's granted VIEW of that node's outputs for the run:

  1. ``grants=outputs`` (default) — the node's PUBLISHED artifact list (name / relpath / kind /
     size), scoped to the node by matching the tool's catalogued output-port globs against the
     run's Nextflow publish dir. Never the whole run — only this node's files.
  2. ``grants=logs`` (opt-in, off by default) — the DE-IDENTIFIED tail of the node's task
     ``.command.log`` / ``.command.err``, routed through :func:`api.deid.scrub_text` (subject ids +
     generic PII redacted). NEVER raw stderr: a tool can echo a subject id into a path or a log
     line, so the raw stream is never emitted.

**Guardrails.** Read-only, post-hoc, OFF the deterministic gate (ADR-0001 — no verdict/confidence
is read or written). Node-scoped data + role-gated access (ADR-0012): outputs are confined to the
node's own output globs; the opt-in ``logs`` grant is de-identified AND restricted to reviewer+
(PII-adjacent even after scrubbing). Least-privilege is by node-scope + wire-role today — NOT by the
(unpersisted, unenforced) binding; per-agent binding enforcement is the deferral noted above.
Compose ≠ execute (it reads already-published artifacts and runs nothing). Traversal-hardened like
the artifact download (``run_id`` must be a bare name; every resolved path is re-checked to be
inside the run's scratch/data dir). Honest-empty: a node/run that produced nothing on disk (a
fixture-only committed run, or an uncatalogued node) returns an empty view with a ``note``, never
fabricated outputs.

**Where a node's outputs live on disk.** The intake driver (``scripts/run_giab_pipeline.py``) runs
the pipeline via ``nextflow run`` into a per-run gitignored scratch dir and publishes each process's
outputs to ``.nf-runs/<run_id>/nf-out/results/`` as ``${meta.id}.<suffix>`` files; the Nextflow work
dir (one task dir per process instance, holding ``.command.log``/``.command.err``/``.command.run``)
lives under ``.nf-runs/<run_id>/work/``. A committed demo run (``data/<run_id>/`` with only the
frozen-five CSVs) has no scratch dir → honest-empty. This module reads what is genuinely there.

**Node → tool resolution.** ``node_id`` is resolved to a catalogued :class:`ProcessSpec` via (1) a
direct catalog tool key (``fastp``, ``bcftools call``) or (2) the seeded ``germline_graph()`` node
id (``n_fastp`` → ``fastp``) — the default pipeline every live intake run compiles + runs. An
authored-pipeline node id absent from the seeded graph doesn't resolve here (the run→authored-graph
linkage isn't tracked yet) — a documented seam; it degrades to honest-empty, never a wrong node's
files.

**Triage-consumption seam.** :func:`gather_node_observations` is the reusable core the QC-triage
agent (``src/pipeguard/triage``) can call to consume a bound node's scoped view when it advises. It
is intentionally NOT wired into the agent in this slice (the agent stays a pure narrator over rule
findings today) — this endpoint + this function are the read mechanism; agent consumption is the
labelled next step.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.auth import Actor, require_role
from api.deid import DEID_POLICY_ID, default_policy, scrub_text
from api.job_store import KIND_INTAKE, get_job_store
from pipeguard.nextflow.catalog import ProcessSpec, catalog_entry
from pipeguard.nextflow.germline import germline_graph

router = APIRouter(prefix="/api", tags=["node_observations"])

_REPO = Path(__file__).resolve().parent.parent.parent
_DATA = _REPO / "data"
_NF_RUNS = _REPO / ".nf-runs"

# The two grants the Wave-2 AgentBinding model defines. ``outputs`` is the default (on); ``logs`` is
# opt-in (off) because a task log can carry subject-id PII (scrubbed before it leaves the machine).
_KNOWN_GRANTS = ("outputs", "logs")
AgentGrant = Literal["outputs", "logs"]

# The grants query param as a module-level singleton (B008: a FastAPI call read from a module var,
# not built in the argument default). Repeated (?grants=outputs&grants=logs) or comma-joined
# (?grants=outputs,logs); absent → the binding model's default-on 'outputs'.
_GRANTS_QUERY = Query(None, description="Repeated or comma-joined: outputs[,logs]")

# Last N lines of a task log to return — a tail, not the whole file (a real log can be large; an
# agent needs the recent context, and a bounded tail keeps the response small + the scrub cheap).
_MAX_LOG_LINES = 200

# Pull each `path("…")` / `path('…')` glob out of a ProcessSpec output port's Nextflow decl so we
# can match published files (a port decl can name more than one path, e.g. paired fastqs).
_PATH_GLOB_RE = re.compile(r"""path\(\s*(['"])(?P<glob>.+?)\1\s*\)""")

# The `.command.run` header Nextflow writes into each task work dir, naming the process instance:
#   # NEXTFLOW TASK: FASTP (HG002)
# We read it to attribute a work dir to THIS node's process (never guess by mtime/order).
_TASK_HEADER_RE = re.compile(r"NEXTFLOW TASK:\s*(?P<proc>[A-Za-z0-9_:]+)")


# ── wire models (advisory, read-only — no verdict/confidence field anywhere, ADR-0001) ──────────


class NodeObservationArtifact(BaseModel):
    """One published output file the bound node produced, scoped to the node."""

    model_config = ConfigDict(frozen=True)
    name: str = Field(..., description="The published file name, e.g. 'HG002.fastp.json'")
    relpath: str = Field(..., description="Path relative to the run's publish dir (results/)")
    kind: str | None = Field(
        None, description="Catalogued artifact-kind of the matched output port (best-effort)"
    )
    size_bytes: int


class NodeLogTail(BaseModel):
    """The DE-IDENTIFIED tail of one of the node's task log streams (opt-in 'logs' grant only)."""

    model_config = ConfigDict(frozen=True)
    stream: Literal["stdout", "stderr"] = Field(
        ..., description="stdout = .command.log; stderr = .command.err"
    )
    relpath: str = Field(..., description="Path relative to the run's Nextflow work dir")
    lines: list[str] = Field(..., description="Scrubbed tail lines (subject ids + PII redacted)")
    truncated: bool = Field(..., description="True when the file had more lines than the tail")
    deid_policy: str = Field(..., description="Id of the de-id policy that scrubbed these lines")


class NodeObservation(BaseModel):
    """An attached agent's granted, node-scoped, read-only view (advisory; off the gate)."""

    model_config = ConfigDict(frozen=True)
    run_id: str
    node_id: str
    tool: str | None = Field(None, description="The catalogued tool the node resolved to (or None)")
    process: str | None = Field(None, description="Nextflow process name (None if unresolved)")
    grants: list[AgentGrant] = Field(..., description="Grants actually applied to this response")
    advisory: Literal[True] = True  # this view never sets/overrides a verdict (ADR-0001)
    source: Literal["nextflow-publish", "none"] = Field(
        ..., description="Where outputs were located ('none' = nothing on disk for this node/run)"
    )
    outputs: list[NodeObservationArtifact] = []
    logs: list[NodeLogTail] = []
    note: str | None = Field(None, description="Honest explanation when the view is empty")


# ── node → spec resolution ─────────────────────────────────────────────────────────────────────


def _resolve_spec(node_id: str) -> tuple[str | None, ProcessSpec | None]:
    """(tool, spec) for a node id. A direct catalog tool key wins; else the seeded germline graph's
    node id → its tool. Returns (None, None) if neither resolves; (tool, None) if the node's tool is
    real but uncatalogued (a placeholder process — known name, no output globs → honest-empty)."""
    key = node_id.strip()
    spec = catalog_entry(key)
    if spec is not None:
        return spec.tool, spec
    for node in germline_graph().nodes:
        if node.id == key:
            return node.tool, catalog_entry(node.tool)
    return None, None


def _output_globs(spec: ProcessSpec) -> list[tuple[str, str]]:
    """(kind, glob) pairs for every ``path(…)`` in the spec's output ports, in port order."""
    pairs: list[tuple[str, str]] = []
    for port in spec.outputs:
        for match in _PATH_GLOB_RE.finditer(port.decl):
            pairs.append((port.kind, match.group("glob")))
    return pairs


# ── outputs ────────────────────────────────────────────────────────────────────────────────────


def _results_dir(run_id: str) -> Path:
    """The Nextflow publish dir for a run (``.nf-runs/<run_id>/nf-out/results``)."""
    return _NF_RUNS / run_id / "nf-out" / "results"


def _scoped_outputs(
    run_id: str, spec: ProcessSpec | None
) -> tuple[list[NodeObservationArtifact], Literal["nextflow-publish", "none"]]:
    """The published files matching this node's output-port globs, scoped to the node.

    Traversal-hardened: every candidate is re-checked to be a real file inside the resolved publish
    dir before it is listed, so a symlink/`..` can never surface a file from outside the run.
    """
    results = _results_dir(run_id)
    if spec is None or not results.is_dir():
        return [], "none"
    root = results.resolve()
    found: dict[str, NodeObservationArtifact] = {}
    for kind, pattern in _output_globs(spec):
        # `Path.glob` confines the pattern to `results`; the resolve()/is_relative_to re-check below
        # is defense-in-depth against a symlinked entry pointing outside the publish dir.
        for path in sorted(results.glob(pattern)):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                continue
            rel = path.relative_to(results).as_posix()
            if rel in found:
                continue
            found[rel] = NodeObservationArtifact(
                name=path.name, relpath=rel, kind=kind, size_bytes=path.stat().st_size
            )
    artifacts = [found[key] for key in sorted(found)]
    return artifacts, ("nextflow-publish" if artifacts else "none")


# ── logs (opt-in, de-identified) ────────────────────────────────────────────────────────────────


def _sensitive_tokens(run_id: str) -> list[str]:
    """The run's KNOWN sensitive literals to pseudonymize in a log tail: subject ids from
    ``sample_metadata.csv`` + the intake ``submitted_by``. Read tolerantly — a missing file/column
    just yields fewer tokens, never a crash."""
    tokens: set[str] = set()
    meta = _DATA / run_id / "sample_metadata.csv"
    if meta.is_file():
        try:
            with meta.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    for col, value in row.items():
                        if col and col.strip().lower() in {"subject_id", "subject"} and value:
                            tokens.add(value.strip())
        except (OSError, csv.Error):
            pass
    job = get_job_store().get(run_id, KIND_INTAKE)
    if job and job.get("submitted_by"):
        tokens.add(str(job["submitted_by"]))
    return [t for t in tokens if t]


def _read_tail(path: Path, max_lines: int) -> tuple[list[str], bool]:
    """Last ``max_lines`` lines of a text file + whether it was truncated. Tolerant of a binary/
    partial line (``errors='replace'``) so a weird log never raises."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], False
    if len(lines) > max_lines:
        return lines[-max_lines:], True
    return lines, False


def _process_matches(header: str, process: str) -> bool:
    """True if a ``.command.run`` header's ``NEXTFLOW TASK: <PROC>`` names this process (nf-core
    processes can be namespaced ``WORKFLOW:PROC`` — a trailing-segment match covers that)."""
    match = _TASK_HEADER_RE.search(header)
    if not match:
        return False
    proc = match.group("proc")
    return proc == process or proc.split(":")[-1] == process


def _node_logs(run_id: str, spec: ProcessSpec | None, sensitive: list[str]) -> list[NodeLogTail]:
    """The de-identified ``.command.log``/``.command.err`` tail(s) for this node's task instances.

    Scans the run's Nextflow work dir, attributing each task dir to a process via its
    ``.command.run`` header, and returns the scrubbed tail of every matching task's log streams.
    Honest-empty when there is no work dir (a fixture-only run) or no matching task.
    """
    if spec is None:
        return []
    work = _NF_RUNS / run_id / "work"
    if not work.is_dir():
        return []
    root = work.resolve()
    policy = default_policy()
    tails: list[NodeLogTail] = []
    for cmd_run in sorted(work.rglob(".command.run")):
        if not cmd_run.resolve().is_relative_to(root):
            continue  # defense-in-depth against a symlinked work entry
        try:
            header = cmd_run.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if not _process_matches(header, spec.process):
            continue
        task_dir = cmd_run.parent
        for stream, fname in (("stdout", ".command.log"), ("stderr", ".command.err")):
            log = task_dir / fname
            if not log.is_file():
                continue
            raw, truncated = _read_tail(log, _MAX_LOG_LINES)
            scrubbed = [scrub_text(line, sensitive=sensitive, policy=policy) for line in raw]
            tails.append(
                NodeLogTail(
                    stream=stream,
                    relpath=log.relative_to(work).as_posix(),
                    lines=scrubbed,
                    truncated=truncated,
                    deid_policy=DEID_POLICY_ID,
                )
            )
    return tails


# ── the reusable core (triage-consumption seam) + the endpoint ──────────────────────────────────


def gather_node_observations(
    run_id: str, node_id: str, grants: list[AgentGrant]
) -> NodeObservation:
    """Build a bound node's scoped, read-only observation view (the QC-triage-consumption seam).

    Pure over what's on disk — no verdict/confidence is read or written (ADR-0001). ``grants``
    decides which parts are populated (``outputs`` always safe; ``logs`` opt-in + de-identified).
    """
    tool, spec = _resolve_spec(node_id)
    outputs: list[NodeObservationArtifact] = []
    source: Literal["nextflow-publish", "none"] = "none"
    if "outputs" in grants:
        outputs, source = _scoped_outputs(run_id, spec)
    logs: list[NodeLogTail] = []
    if "logs" in grants:
        logs = _node_logs(run_id, spec, _sensitive_tokens(run_id))
    note: str | None = None
    if tool is None:
        note = (
            f"node '{node_id}' did not resolve to a catalogued tool/process — "
            "no scoped outputs (an authored-pipeline node id is a documented seam)"
        )
    elif source == "none" and not logs:
        note = "no published outputs on disk for this node/run (fixture-only run, or nothing ran)"
    return NodeObservation(
        run_id=run_id,
        node_id=node_id,
        tool=tool,
        process=spec.process if spec else None,
        grants=grants,
        source=source,
        outputs=outputs,
        logs=logs,
        note=note,
    )


def _guard_run_id(run_id: str) -> None:
    """Reject a traversal-crafted run id BEFORE it is joined into a scratch/data path (the artifact-
    download idiom): it must be a bare path segment with no ``..``."""
    if run_id != Path(run_id).name or run_id in {"", ".", ".."} or ".." in run_id:
        raise HTTPException(status_code=404, detail="Unknown run")


def _parse_grants(raw: list[str]) -> list[AgentGrant]:
    """Flatten repeated + comma-joined grant params into an ordered, de-duped, validated list.

    Supports ``?grants=outputs,logs`` and ``?grants=outputs&grants=logs``. An unknown grant is a
    422 (a typo shouldn't silently under- or over-grant). An empty selection defaults to
    ``['outputs']`` (the binding model's default-on grant)."""
    seen: list[AgentGrant] = []
    for item in raw:
        for token in item.split(","):
            tok = token.strip().lower()
            if not tok:
                continue
            if tok not in _KNOWN_GRANTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"unknown grant '{tok}' (allowed: {', '.join(_KNOWN_GRANTS)})",
                )
            if tok not in seen:
                seen.append(tok)  # type: ignore[arg-type]  # membership guard narrows to AgentGrant
    return seen or ["outputs"]


@router.get("/runs/{run_id}/nodes/{node_id}/observations")
def node_observations(
    run_id: str,
    node_id: str,
    grants: list[str] | None = _GRANTS_QUERY,
    actor: Actor = Depends(require_role("viewer", "reviewer", "approver")),
) -> NodeObservation:
    """A bound advisory agent's SCOPED READ of a node's published outputs for a run (off the gate).

    ``grants=outputs`` (default) lists the node's published artifacts; ``grants=logs`` additionally
    returns the DE-IDENTIFIED tail of the node's task logs (opt-in — a raw log can carry subject-id
    PII). Read-only, node-scoped (ADR-0012), traversal-hardened, honest-empty. Role gate:
    ``outputs`` viewer+; ``logs`` reviewer+ (PII-adjacent even after de-id).
    """
    _guard_run_id(run_id)
    parsed = _parse_grants(grants or [])
    # WS-08: 'logs' returns DE-IDENTIFIED task logs — still PII-adjacent (a tool can echo a
    # subject id into a path/line the scrub's known-literal set misses). Server-enforce a higher bar
    # than plain viewer for it. This is REAL access control (the wire role), unlike the client-side
    # AgentBinding, which the server does not persist or enforce (see the module docstring). Outputs
    # (a published-file listing) stay viewer+.
    if "logs" in parsed and actor.role not in ("reviewer", "approver"):
        raise HTTPException(
            status_code=403,
            detail=(
                "the 'logs' grant returns de-identified task logs and requires reviewer+ — "
                "a viewer may read 'outputs' only"
            ),
        )
    return gather_node_observations(run_id, node_id, parsed)
