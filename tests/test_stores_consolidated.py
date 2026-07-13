"""WS-06 Gap 6 — the seven off-gate stores share ONE generic JSONL impl (structural consolidation).

The stores under ``api/`` (feedback / library / review / pipeline-graph / settings / job / share)
were the SAME "indexed columns + full-JSON document, env-selected backend, degrade-to-JSONL" shape
copy-pasted seven times. This module pins the CONSOLIDATION invariant so the boilerplate can't
silently reopen: every concrete ``Jsonl*Store`` subclasses the single ``api.base_store.JsonlStore``
base, the read/append/rewrite loop lives in exactly ONE class (no concrete store re-implements it),
the degrade-to-JSONL selector lives in exactly ONE function, and — the load-bearing guarantee — a
record's JSONL bytes are byte-identical to the pre-refactor serialization.

These are anti-scaffold guards: they can only pass on a REAL shared base (a subclass check + a
``func is base.func`` identity check + a source-level "no bespoke read loop" scan), not on seven
independent classes that merely still behave the same. The five behavioural guarantees (default
JSONL, round-trip, idempotent re-append, degrade-to-JSONL, tolerant corrupt-line read) stay pinned
by the per-store suites (``test_share_store`` / ``test_job_store`` / ``test_library_store`` /
``test_api`` / ``test_pipelines`` / ``test_review_queue`` / ``test_settings``) — kept green too.
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from api.base_store import JsonlStore, select_backend
from api.feedback_store import JsonlFeedbackStore, get_feedback_store
from api.job_store import JsonlJobStore, get_job_store
from api.library_store import JsonlLibraryStore, get_library_store
from api.pipeline_store import JsonlPipelineGraphStore, get_pipeline_store
from api.review_store import JsonlReviewStore, get_review_store
from api.settings_store import JsonlSettingsStore, get_settings_store
from api.share_store import JsonlShareStore, get_share_store
from pipeguard.provenance import EntityRef, EventType, ProvenanceEvent

# The IO primitives that must live in exactly ONE class (the generic base). If any concrete store
# re-implements one of these, the boilerplate has re-forked — the whole point of the consolidation.
_IO_PRIMITIVES = ("_read_all", "_append", "_append_authored", "_rewrite", "_write_line")


@dataclass
class Case:
    """One store's write/read shape, so the same structural + byte checks run over all seven."""

    name: str
    env_store: str  # PIPEGUARD_*_STORE (unset => default JSONL)
    env_path: str  # PIPEGUARD_*_PATH (the JSONL sink)
    jsonl_cls: type[Any]
    get_fn: Callable[[], Any]
    tolerant: bool  # whether a corrupt line is skipped (True) or surfaced (False)
    make: Callable[[], Any]  # the write argument (a dict record or a ProvenanceEvent)
    write: Callable[[Any, Any], None]  # (store, arg) -> persist it
    expected_line: Callable[[Any], str]  # (arg) -> the exact JSONL line (incl. trailing newline)
    read_all: Callable[[Any], list[Any]]  # (store) -> every persisted record, in read order


_T0 = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def _share_event() -> ProvenanceEvent:
    return ProvenanceEvent(
        event_type=EventType.DATA_EXPORTED,
        run_id="RUN-A",
        actor="human:b",
        created_at=_T0,
        outputs=[EntityRef(entity_type="share_bundle", id="h", content_hash="h")],
        payload={"n_rows": 1},
    )


def _feedback_rec() -> dict[str, Any]:
    # A non-ASCII value pins ensure_ascii=False concretely (the ✓ must ride through as UTF-8).
    return {
        "id": "f1",
        "received_at": "2026-07-11T12:00:00+00:00",
        "target": "card",
        "source": "ui",
        "context": {"run_id": "RUN-A"},
        "origin": "user",
        "schema_version": 1,
        "note": "nice ✓",
    }


def _library_rec() -> dict[str, Any]:
    return {
        "id": "lib1",
        "tool": "fastp",
        "version": "1.0.0",
        "status": "draft",
        "submitted_by": "a",
        "created_at": "2026-07-11T12:00:00+00:00",
        "proposal": {"advisory": True},
    }


def _review_rec() -> dict[str, Any]:
    return {
        "id": "t1",
        "created_at": "2026-07-11T12:00:00+00:00",
        "run_id": "RUN-A",
        "sample_id": "HG002",
        "gate": "seq",
        "verdict": "HOLD",
        "rule_id": "R1",
        "status": "open",
        "priority": "high",
        "opened_by": "a",
        "actions": [],
    }


def _pipeline_rec() -> dict[str, Any]:
    return {
        "id": "p1",
        "created_at": "2026-07-11T12:00:00+00:00",
        "name": "wgs",
        "schema_version": "1",
        "profile": "research",
        "graph": {"nodes": []},
    }


def _settings_rec() -> dict[str, Any]:
    return {
        "id": "s1",
        "created_at": "2026-07-11T12:00:00+00:00",
        "name": "wgs",
        "status": "draft",
        "payload": {"q30": 0.9},
    }


def _job_rec() -> dict[str, Any]:
    return {
        "kind": "intake",
        "run_id": "RUN-A",
        "status": "queued",
        "error": None,
        "created_at": "2026-07-11T12:00:00+00:00",
        "updated_at": "2026-07-11T12:00:00+00:00",
    }


def _dumps(rec: dict[str, Any]) -> str:
    return json.dumps(rec, ensure_ascii=False) + "\n"


def _dumps_versioned(rec: dict[str, Any]) -> str:
    # pipeline/settings ``append`` authors ``version`` LAST via ``{**record, "version": v}``.
    return json.dumps({**rec, "version": 1}, ensure_ascii=False) + "\n"


CASES: list[Case] = [
    Case(
        "feedback",
        "PIPEGUARD_FEEDBACK_STORE",
        "PIPEGUARD_FEEDBACK_PATH",
        JsonlFeedbackStore,
        get_feedback_store,
        tolerant=False,
        make=_feedback_rec,
        write=lambda s, r: s.append(r),
        expected_line=_dumps,
        read_all=lambda s: s.read_all(),
    ),
    Case(
        "library",
        "PIPEGUARD_LIBRARY_STORE",
        "PIPEGUARD_LIBRARY_PATH",
        JsonlLibraryStore,
        get_library_store,
        tolerant=True,
        make=_library_rec,
        write=lambda s, r: s.add(r),
        expected_line=_dumps,
        read_all=lambda s: s.list(),
    ),
    Case(
        "review",
        "PIPEGUARD_REVIEW_STORE",
        "PIPEGUARD_REVIEW_PATH",
        JsonlReviewStore,
        get_review_store,
        tolerant=False,
        make=_review_rec,
        write=lambda s, r: s.create(r),
        expected_line=_dumps,
        read_all=lambda s: s.list(),
    ),
    Case(
        "pipeline",
        "PIPEGUARD_PIPELINE_STORE",
        "PIPEGUARD_PIPELINE_PATH",
        JsonlPipelineGraphStore,
        get_pipeline_store,
        tolerant=False,
        make=_pipeline_rec,
        write=lambda s, r: s.append(r),
        expected_line=_dumps_versioned,
        read_all=lambda s: s.list(),
    ),
    Case(
        "settings",
        "PIPEGUARD_SETTINGS_STORE",
        "PIPEGUARD_SETTINGS_PATH",
        JsonlSettingsStore,
        get_settings_store,
        tolerant=False,
        make=_settings_rec,
        write=lambda s, r: s.append(r),
        expected_line=_dumps_versioned,
        read_all=lambda s: s.list(),
    ),
    Case(
        "job",
        "PIPEGUARD_JOB_STORE",
        "PIPEGUARD_JOB_PATH",
        JsonlJobStore,
        get_job_store,
        tolerant=True,
        make=_job_rec,
        write=lambda s, r: s.upsert(r),
        expected_line=_dumps,
        read_all=lambda s: s.list(),
    ),
    Case(
        "share",
        "PIPEGUARD_SHARE_STORE",
        "PIPEGUARD_SHARE_PATH",
        JsonlShareStore,
        get_share_store,
        tolerant=True,
        make=_share_event,
        write=lambda s, e: s.append(e),
        expected_line=lambda e: e.model_dump_json() + "\n",
        read_all=lambda s: s.for_run("RUN-A"),
    ),
]


def _point_at_tmp(monkeypatch: Any, case: Case, tmp: Path) -> None:
    monkeypatch.delenv(case.env_store, raising=False)  # default => JSONL
    monkeypatch.setenv(case.env_path, str(tmp / f"{case.name}.jsonl"))


def test_all_seven_stores_share_one_generic_impl(monkeypatch: Any, tmp_path: Path) -> None:
    """Each of the SEVEN concrete JSONL stores subclasses the ONE base, does not override the shared
    IO primitives, defaults to JSONL, round-trips a record, and writes BYTE-IDENTICAL JSONL."""
    assert len(CASES) == 7, "the consolidation must cover all seven off-gate stores"

    for case in CASES:
        # (1) Structural: it IS a JsonlStore, and it does NOT re-implement any IO primitive — the
        # read/append/rewrite loop is inherited from the single base, not copied per store.
        assert issubclass(case.jsonl_cls, JsonlStore), case.name
        for prim in _IO_PRIMITIVES:
            assert getattr(case.jsonl_cls, prim) is getattr(JsonlStore, prim), (
                f"{case.name}.{prim} is not the shared base primitive — the boilerplate re-forked"
            )
        # The tolerance of a corrupt line is a per-store class attribute (behaviour preserved).
        assert case.jsonl_cls._tolerant is case.tolerant, case.name

        _point_at_tmp(monkeypatch, case, tmp_path)

        # (2) Default is JSONL (no store env set => the offline file backend).
        store = case.get_fn()
        assert isinstance(store, case.jsonl_cls), case.name

        # (3) Byte-identical: the on-disk line equals the exact pre-refactor serialization.
        arg = case.make()
        case.write(store, arg)
        raw = (tmp_path / f"{case.name}.jsonl").read_bytes()
        assert raw == case.expected_line(arg).encode("utf-8"), case.name

        # (4) Round-trip: the record reads back through the store's own accessor.
        assert len(case.read_all(store)) == 1, case.name

    # A concrete non-ASCII pin: ensure_ascii=False survived the refactor (the ✓ rides through as raw
    # UTF-8, NOT as a ``✓`` escape) — catches a serialization change the golden compare might miss.
    fb_line = (tmp_path / "feedback.jsonl").read_bytes()
    assert b"\xe2\x9c\x93" in fb_line and b"\\u2713" not in fb_line


def test_tolerant_stores_skip_a_corrupt_line(monkeypatch: Any, tmp_path: Path) -> None:
    """The tolerant stores skip a wedged partial line; the non-tolerant ones surface it (behaviour
    preserved per store) — the ONE shared read loop honours each store's ``_tolerant`` flag."""
    for case in CASES:
        _point_at_tmp(monkeypatch, case, tmp_path)
        store = case.get_fn()
        case.write(store, case.make())
        path = tmp_path / f"{case.name}.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + '{"partial":\n', encoding="utf-8")
        if case.tolerant:
            assert len(case.read_all(store)) == 1, case.name  # corrupt line skipped, not fatal
        else:
            with pytest.raises(ValueError):
                case.read_all(store)  # non-tolerant stores still surface a corrupt line


def test_no_duplicated_store_boilerplate() -> None:
    """The for_run/append/rewrite/degrade-to-JSONL logic exists in exactly ONE place, and no
    concrete JSONL store carries a bespoke file read/append loop."""
    # The IO primitives are DEFINED on the base (its __dict__), so there is a single copy to own.
    for prim in _IO_PRIMITIVES:
        assert prim in JsonlStore.__dict__, f"{prim} must be defined on the generic base"

    # No concrete JSONL store (nor the dict specialization) re-declares an IO primitive in its own
    # body — they inherit the single copy. A re-declared primitive here = the boilerplate re-forked.
    concrete = [c.jsonl_cls for c in CASES]
    for cls in concrete:
        for prim in _IO_PRIMITIVES:
            assert prim not in cls.__dict__, f"{cls.__name__} re-declares {prim} (bespoke loop)"

    # A source-level guard: a concrete store's body must reference NO file-read/append construct —
    # if someone re-inlines a loop, this trips even if they rename the method. Parse with ``ast`` so
    # a docstring/comment MENTIONING these (e.g. "the base's os.replace swap") never false-fires:
    # only real attribute accesses (``path.read_text`` / ``path.open`` / ``raw.splitlines``) count.
    file_io_attrs = {"read_text", "splitlines", "open"}
    for cls in concrete:
        tree = ast.parse(inspect.getsource(cls))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        leaked = attrs & file_io_attrs
        assert not leaked, f"{cls.__name__} references bespoke file IO {sorted(leaked)}"

    # The degrade-to-JSONL selector lives in exactly ONE function, and every get_*_store delegates
    # to it (rather than each re-implementing the try/except/log ladder).
    assert callable(select_backend)
    for case in CASES:
        src = inspect.getsource(case.get_fn)
        assert "select_backend" in src, f"{case.get_fn.__name__} does not use select_backend"
