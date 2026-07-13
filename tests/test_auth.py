"""Tests for the minimal auth/identity primitive (``api/auth.py``) — off the decision gate.

Fully in-isolation per the build contract: each test builds its OWN tiny FastAPI app,
mounts routes that depend on ``current_actor`` / ``require_role``, and drives them with a
TestClient. Nothing here imports ``api/main.py`` — the primitive is exercised on its own so a
failure points at the auth seam, not at unrelated wiring.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import Actor, current_actor, require_role


def _app() -> FastAPI:
    """A throwaway app exposing the auth surface: a whoami route (current_actor) and two
    role-gated routes (require_role) so both the identity read and the authz gate are driven."""
    app = FastAPI()

    @app.get("/whoami")
    def whoami(actor: Actor = Depends(current_actor)) -> dict[str, str]:
        return {"id": actor.id, "role": actor.role}

    @app.get("/reviewer-plus")
    def reviewer_plus(
        actor: Actor = Depends(require_role("reviewer", "approver")),
    ) -> dict[str, str]:
        # The gate ALSO yields the actor, so the handler can capture actor.id into an audit field.
        return {"acted_by": actor.id, "role": actor.role}

    @app.get("/approver-only")
    def approver_only(actor: Actor = Depends(require_role("approver"))) -> dict[str, str]:
        return {"acted_by": actor.id}

    return app


client = TestClient(_app())


# --- current_actor: dev-default (no headers) -------------------------------------------------


def test_default_actor_is_permissive_dev_approver() -> None:
    # No headers -> the offline demo/tests must resolve a principal with no auth wiring, and it
    # must be permissive enough to clear any gate (id="dev", role="approver").
    resp = client.get("/whoami")
    assert resp.status_code == 200
    assert resp.json() == {"id": "dev", "role": "approver"}


# --- current_actor: header-provided principal ------------------------------------------------


def test_header_provided_actor_is_read() -> None:
    resp = client.get(
        "/whoami",
        headers={"X-Bayleaf-Actor": "a.rivera", "X-Bayleaf-Role": "reviewer"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": "a.rivera", "role": "reviewer"}


def test_role_header_is_case_insensitive() -> None:
    # Roles arrive from a header; a stray uppercase must not spuriously 400.
    resp = client.get("/whoami", headers={"X-Bayleaf-Role": "APPROVER"})
    assert resp.json()["role"] == "approver"


# --- AS-03: BAYLEAF_AUTH_STRICT opt-in tightens the header-less default (default UNCHANGED) ----


def test_default_headerless_role_unchanged_without_strict(monkeypatch: Any) -> None:
    # GUARDRAIL: with the env explicitly UNSET the header-less default is the permissive approver,
    # exactly as before AS-03 — the offline demo/tests must be byte-for-byte unaffected.
    monkeypatch.delenv("BAYLEAF_AUTH_STRICT", raising=False)
    assert client.get("/whoami").json() == {"id": "dev", "role": "approver"}
    assert client.get("/approver-only").status_code == 200


def test_strict_mode_defaults_headerless_to_viewer(monkeypatch: Any) -> None:
    # AS-03 opt-in: with BAYLEAF_AUTH_STRICT set, a header-LESS request drops to least-privilege
    # viewer instead of approver, so the approver-only gate now 403s a no-header caller. Off by
    # default, so this changes nothing for the demo unless a deployment explicitly opts in.
    monkeypatch.setenv("BAYLEAF_AUTH_STRICT", "1")
    assert client.get("/whoami").json() == {"id": "dev", "role": "viewer"}
    assert client.get("/approver-only").status_code == 403


def test_strict_mode_still_honors_explicit_role_header(monkeypatch: Any) -> None:
    # Strict mode only lowers the no-header fallback; it does NOT verify the header (a real IdP is
    # the only enforcement fix). An explicit role header is still trusted and read as-is.
    monkeypatch.setenv("BAYLEAF_AUTH_STRICT", "1")
    resp = client.get("/whoami", headers={"X-Bayleaf-Role": "approver"})
    assert resp.json()["role"] == "approver"


def test_partial_headers_default_the_missing_field() -> None:
    # Actor id present, role absent -> id read, role falls back to the dev default (approver).
    resp = client.get("/whoami", headers={"X-Bayleaf-Actor": "b.chen"})
    assert resp.json() == {"id": "b.chen", "role": "approver"}


def test_unknown_role_header_is_400() -> None:
    # An explicit-but-unknown role is a loud 400, never a silent coercion (privilege safety).
    resp = client.get("/whoami", headers={"X-Bayleaf-Role": "superadmin"})
    assert resp.status_code == 400


def test_malformed_actor_id_is_400() -> None:
    # A newline in the id could forge a log/JSONL line downstream -> rejected at the boundary.
    resp = client.get("/whoami", headers={"X-Bayleaf-Actor": "evil\nname"})
    assert resp.status_code == 400


# --- require_role: allow / 403 by role -------------------------------------------------------


def test_require_role_allows_when_role_in_allowed() -> None:
    # reviewer is in {reviewer, approver} -> allowed, and the actor is returned to the handler.
    resp = client.get("/reviewer-plus", headers={"X-Bayleaf-Role": "reviewer"})
    assert resp.status_code == 200
    assert resp.json() == {"acted_by": "dev", "role": "reviewer"}


def test_require_role_allows_default_dev_actor() -> None:
    # The permissive default (approver) clears every gate, so existing endpoints/tests are
    # unaffected when the gate is added with no auth headers wired.
    assert client.get("/reviewer-plus").status_code == 200
    assert client.get("/approver-only").status_code == 200


def test_require_role_403s_when_role_not_allowed() -> None:
    # viewer is not in {reviewer, approver} -> 403 (Forbidden), NOT 401: the request is
    # authenticated (a principal exists), it just lacks the privilege.
    resp = client.get("/reviewer-plus", headers={"X-Bayleaf-Role": "viewer"})
    assert resp.status_code == 403


def test_require_role_403s_reviewer_on_approver_only_route() -> None:
    resp = client.get("/approver-only", headers={"X-Bayleaf-Role": "reviewer"})
    assert resp.status_code == 403
    # The error names the required role (not secret) but must not leak the caller's id.
    assert "b.chen" not in resp.text
    resp2 = client.get(
        "/approver-only",
        headers={"X-Bayleaf-Actor": "b.chen", "X-Bayleaf-Role": "reviewer"},
    )
    assert resp2.status_code == 403
    assert "b.chen" not in resp2.text
