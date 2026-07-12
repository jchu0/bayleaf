"""Deterministic conformance harness for authored node metadata (W2 boundaries contract).

:func:`check_conformance` mechanically asserts the capability pins in
``docs/design/agent-authoring-contract.md`` against a candidate proposal — the enforcement that
keeps the boundaries MD non-decorative. It is **pure and deterministic**: it makes no network call,
reads no env, and mutates nothing; it only inspects the candidate's fields and returns the list of
violations (empty ⇒ conformant).

It vets a candidate that is EITHER a validated :class:`NodeProposal` OR a raw ``Mapping`` (an
as-yet-unvalidated dict from an untrusted importer or a future agent). The raw-dict path is the
load-bearing one: a :class:`NodeProposal` already pins ``advisory`` ``Literal[True]`` and has no
verdict/confidence/command field *structurally*, so a validated proposal can barely be
non-conformant — but a raw dict from a doc-drop importer or a not-yet-hardened agent CAN carry a
smuggled ``verdict`` / ``script:`` body / an invented live port, and this harness is the tripwire
that catches it before the metadata is trusted (accepted into the library, wired, rendered).

The pins checked (agent-authoring-contract.md "Capability pins"):

  1. **Advisory** — ``advisory`` is present and ``True`` (ADR-0001 / G1).
  2. **No verdict / no confidence** — neither key appears anywhere in the candidate (G1): an
     authored artifact can never carry or move a gate value.
  3. **Metadata, not commands (compose ≠ execute)** — no ``script`` / ``stub`` command-body key
     appears anywhere (ADR-0003): the runnable body lives solely in the human-curated
     ``ProcessSpec`` catalog, never in an authored proposal.
  4. **Closed vocabulary; unknown → reserved** — every port kind is either in
     :data:`ARTIFACT_KINDS` (a live port) or explicitly listed in ``reserved_kinds`` (an inert,
     labelled slot); a port's ``known`` flag, when present, must equal ``kind in ARTIFACT_KINDS``;
     a ``reserved_kinds`` entry must genuinely be outside the vocabulary.
  5. **Versioned four ways** — ``corpus_version`` + ``schema_version`` + ``platform_version`` are
     pinned, and a *matched* proposal also pins the tool ``version`` (tool + corpus + schema +
     platform).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from .models import ARTIFACT_KINDS, NodeProposal

# Keys that must NEVER appear anywhere in an authored candidate. ``verdict`` / ``confidence`` would
# let authored metadata carry a gate value (G1); ``script`` / ``stub`` would be a runnable command
# body (compose ≠ execute, ADR-0003). We scan for these as KEYS (not values) — ``generated_by`` and
# ``mode`` legitimately hold the *value* ``"stub"``, which is fine; a *key* named ``stub`` is not.
_FORBIDDEN_GATE_KEYS = frozenset({"verdict", "confidence"})
_FORBIDDEN_COMMAND_KEYS = frozenset({"script", "stub"})


class ConformanceViolation(BaseModel):
    """One failed pin: a stable machine ``code`` plus a human-readable ``detail``.

    Frozen so a caller can collect + compare violations without accidental mutation. ``code`` is a
    stable identifier (e.g. ``"verdict_field_present"``) safe to assert on in tests and to branch on
    in a UI; ``detail`` explains the specific failure for a log line or an operator.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    detail: str


def _as_mapping(candidate: NodeProposal | Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a candidate to a plain dict view for inspection.

    A :class:`NodeProposal` is dumped in JSON mode (so nested ports/locators become dicts and the
    computed ``known`` / ``mode`` fields are materialized exactly as they serialize on the wire); a
    raw mapping is shallow-copied so the harness never mutates the caller's object.
    """
    if isinstance(candidate, NodeProposal):
        return candidate.model_dump(mode="json")
    return dict(candidate)


def _find_forbidden_keys(node: Any, forbidden: frozenset[str], found: set[str]) -> None:
    """Recursively collect any dict KEY (at any depth) whose name is in ``forbidden``.

    Recurses through dicts and lists so a command body or gate value smuggled inside a nested port,
    locator, or citation is caught, not just a top-level one. Scans keys only — a legitimate string
    *value* like ``generated_by="stub"`` is never a violation.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and key in forbidden:
                found.add(key)
            _find_forbidden_keys(value, forbidden, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _find_forbidden_keys(item, forbidden, found)


def _check_ports(data: Mapping[str, Any]) -> list[ConformanceViolation]:
    """Port-vocabulary checks (pin 4): live kinds are real, unknown kinds are declared reserved."""
    violations: list[ConformanceViolation] = []
    reserved_kinds = data.get("reserved_kinds") or []
    reserved_set = {str(k) for k in reserved_kinds} if isinstance(reserved_kinds, list) else set()

    # A declared reserved kind that is actually in the vocabulary is a mislabel — it would surface a
    # real, wireable kind as an inert slot (or vice-versa downstream). Flag it.
    for kind in sorted(reserved_set):
        if kind in ARTIFACT_KINDS:
            violations.append(
                ConformanceViolation(
                    code="reserved_kind_actually_known",
                    detail=f"reserved_kinds lists {kind!r}, but it IS a live ARTIFACT_KINDS kind",
                )
            )

    for role in ("inputs", "outputs"):
        ports = data.get(role) or []
        if not isinstance(ports, list):
            continue
        for port in ports:
            if not isinstance(port, Mapping):
                continue
            kind = str(port.get("kind", ""))
            known_actual = kind in ARTIFACT_KINDS
            # A carried ``known`` flag must be the computed truth, never authored.
            if "known" in port and bool(port["known"]) != known_actual:
                violations.append(
                    ConformanceViolation(
                        code="port_known_mismatch",
                        detail=(
                            f"{role} port {kind!r} declares known={port['known']} but "
                            f"kind-in-vocabulary is {known_actual}"
                        ),
                    )
                )
            # An unknown kind that is NOT declared reserved is an invented live wire — the exact
            # thing the closed-vocabulary pin forbids.
            if not known_actual and kind not in reserved_set:
                violations.append(
                    ConformanceViolation(
                        code="port_kind_not_reserved",
                        detail=(
                            f"{role} port kind {kind!r} is outside ARTIFACT_KINDS and is not "
                            "declared in reserved_kinds (an invented live port)"
                        ),
                    )
                )
    return violations


def check_conformance(candidate: NodeProposal | Mapping[str, Any]) -> list[ConformanceViolation]:
    """Return the boundary-contract violations for a candidate proposal (empty ⇒ conformant).

    Pure and deterministic — see the module docstring for the five pins. Accepts a validated
    :class:`NodeProposal` or a raw mapping (the untrusted-importer path). The checks are additive:
    every failed pin contributes one (or more) :class:`ConformanceViolation`, so a caller sees the
    full set at once rather than only the first failure.
    """
    data = _as_mapping(candidate)
    violations: list[ConformanceViolation] = []

    # Pin 1 — advisory is present and True.
    if data.get("advisory") is not True:
        violations.append(
            ConformanceViolation(
                code="not_advisory",
                detail=f"'advisory' must be present and True (got {data.get('advisory')!r})",
            )
        )

    # Pin 2 — no gate value (verdict/confidence) anywhere.
    gate_keys: set[str] = set()
    _find_forbidden_keys(data, _FORBIDDEN_GATE_KEYS, gate_keys)
    for key in sorted(gate_keys):
        violations.append(
            ConformanceViolation(
                code=f"{key}_field_present",
                detail=f"authored metadata must never carry a {key!r} field (G1, ADR-0001)",
            )
        )

    # Pin 3 — no runnable command body (script/stub) anywhere (compose ≠ execute).
    command_keys: set[str] = set()
    _find_forbidden_keys(data, _FORBIDDEN_COMMAND_KEYS, command_keys)
    for key in sorted(command_keys):
        violations.append(
            ConformanceViolation(
                code=f"{key}_body_present",
                detail=(
                    f"authored metadata must never carry a {key!r} command body — the runnable "
                    "body lives only in the human-curated ProcessSpec catalog (compose != execute)"
                ),
            )
        )

    # Pin 4 — closed port vocabulary; unknown → reserved.
    violations.extend(_check_ports(data))

    # Pin 5 — versioned four ways (corpus + schema + platform always; tool version when matched).
    for field in ("corpus_version", "schema_version", "platform_version"):
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            violations.append(
                ConformanceViolation(
                    code=f"missing_{field}",
                    detail=f"a proposal must pin {field!r} (tool+corpus+schema+platform)",
                )
            )
    if data.get("matched") is True:
        version = data.get("version")
        if version is None or (isinstance(version, str) and not version.strip()):
            violations.append(
                ConformanceViolation(
                    code="missing_tool_version",
                    detail="a matched proposal must pin the tool 'version'",
                )
            )

    return violations


def is_conformant(candidate: NodeProposal | Mapping[str, Any]) -> bool:
    """True iff the candidate has no boundary-contract violations (convenience over
    :func:`check_conformance`)."""
    return not check_conformance(candidate)
