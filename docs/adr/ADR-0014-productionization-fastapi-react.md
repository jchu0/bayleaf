# ADR-0014 — Productionize with FastAPI + React (Streamlit as the fallback)

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [design/frontend/](../design/frontend/) |

## Context

Streamlit was chosen as the dev/MVP view — a thin renderer over the framework-agnostic
core — with a React + FastAPI production port planned for *after* MVP. Mid-build, the
maintainer decided to **pull that port into the hackathon scope** so the demo ships on
the intended production UI (the v2.1 clickable prototype), not the Streamlit stand-in.

This is a delivery-posture tradeoff: the full 8-screen React build competes for the
remaining days (deadline Mon Jul 13) with the other differentiators — the QC-triage
Claude agent and real GIAB data. The pushback and the maintainer's choice of the *full*
port (over a lean hero-flow) are recorded so the tradeoff is deliberate, not drifted-into.

## Decision

1. **FastAPI read-API (`api/`)** wraps the core as the production seam (ADR-0010) — the
   core stays framework-agnostic (no FastAPI/React imports in `src/pipeguard/`).
2. **React + Vite + Tailwind frontend (`frontend/`)** consumes the API, built to the
   v2.1 prototype's design system (IBM Plex, verdict/gate tokens).
3. **Streamlit (`app/`) is kept as the guaranteed-working demo fallback** — never
   deleted, kept green — so a React overrun can never leave us without a demo.
4. **Hero-first sequencing:** run overview → decision cards → triage → provenance, so
   even a partial React app demos the core story. Remaining screens (intake, review
   queue, monitoring, settings) follow and some depend on Phase-2 data.

## Consequences

1. React is the primary UI target; Streamlit is insurance, not a parallel product.
2. Screens needing run-level QC, ticket state, or run history (intake, monitoring,
   review-queue transitions) are thin until Phase 2 supplies the data — build them
   read-only or defer rather than mock.
3. Two thin delivery layers now sit over one core; both must stay in sync via the API
   contract, which is the seam a reader/integrator consumes.

## Alternatives considered

1. **Keep Streamlit only, React post-hackathon** — safest for the deadline and the AI
   story; rejected because the maintainer wants the production UI in the demo.
2. **FastAPI + a lean React hero-flow** — recommended as the de-risked middle; the
   maintainer chose the full port instead, accepting the overrun risk.

## Assumptions

- The core's read shapes (pydantic models) are a stable enough contract for the API.
- The Streamlit fallback is cheap to keep green (it already is — one test-pinned demo).
