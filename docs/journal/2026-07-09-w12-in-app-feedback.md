# Journal — 2026-07-09 (MST) — W12: in-app feedback (the first write endpoint)

| Field | Value |
|---|---|
| **Focus** | Build the wishlist W12 / T-042 in-app feedback capture — product telemetry, off the deterministic gate — using a design panel + an adversarial review. |
| **Participants** | James Hu, Claude Code (+ a design-panel workflow and a review workflow of subagents). |
| **Outcome** | Shipped POST /api/feedback (the app's first write) + a per-decision thumbs footer and a global product FAB; 9 new API tests; 216 pytest green; adversarially reviewed (security/correctness/guardrails clean). |

## Discussion

**Design panel first.** W12 had real open questions — the *most valuable* feedback for a
decision gate isn't a generic box, it's signal keyed to a specific verdict — and it is the
app's **first write endpoint** (the read-API was GET-only). Ran a 3-angle design panel
(global widget · per-decision signal · hybrid), judged on product value for a decision gate,
guardrail fit, simplicity, and design fidelity. Winner: a **scoped hybrid** —
- **Surface A (primary):** a per-decision "does this verdict match your call?" thumbs footer
  in the expanded decision card, keyed to `verdict + gate + rule_ids + card_content_hash`.
  This is the highest-resolution telemetry a gate can collect (agreement-rate per verdict /
  gate / rule → a prioritized runbook-tuning backlog), and it stays advisory (ADR-0001).
- **Surface B (secondary):** one global product FAB, mounted in `Layout.tsx` as a sibling of
  `<Outlet/>` so **every migrated screen renders byte-identical** — the FAB rides all screens
  but lives outside them (rejected the raw-hybrid's TopBar mount for exactly this reason).
- One endpoint + one JSONL store, discriminated by a `target` field; explicit-submit only
  (dropped the raw proposal's fragile debounced auto-post).

**First write endpoint, handled honestly.** The read-API docstring's "read-only for now" was
reframed to **read-only over the DECISION domain**: no endpoint mutates a verdict/finding/
provenance event/EventLedger, and the one write (`POST /api/feedback`) is append-only product
telemetry that is structurally off the gate — a separate module (`api/feedback.py`) that never
imports the `bayleaf` core. Security posture baked in: `extra="forbid"` on both request
models is a *structural* PII guard (a smuggled `email`/`subject_id`/server field is a hard
422); the store path is server-fixed (no request value touches it → no traversal); records go
through `json.dumps` (one escaped line each → no log-forging); a write `OSError` maps to a
generic 503 that leaks neither the path nor the message; `origin` is resolved server-side via
`_run_origin` (the trust anchor), never trusted from the client; CORS gains exactly `POST`
with origins still pinned. The one honest residual is free-text PII the operator might type —
minimized (placeholder warning, gitignored local sink, never echoed in the ack, never logged),
not NLP-scrubbed (that's wishlist #14).

**Adversarial review.** Ran a 4-lens review (correctness / security / guardrails /
simplification) with an independent skeptic verifying each finding. **Security, correctness,
and guardrail lenses surfaced nothing real** — a strong signal the core is sound. Two
low-severity simplification nits survived: (1) a write-only `'form'` phase in `DecisionFeedback`
whose guard was redundant with `signal !== null` → **applied** (removed the phase, gated the
reveal on `signal`); (2) ~12 lines of duplicated presentational fragments across the two
feedback components → **skipped** (the verifier itself rated it low-confidence, noted the Send
button actually differs, and called extraction "low-value for an MVP" — coupling two otherwise
independent surfaces wasn't a clear win).

**Verification.** 216 pytest green (9 new: both targets, cross-field + enum/bounds validation,
the `extra=forbid` PII guard, one-JSONL-line escaping, 503 no-leak, CORS scope,
decision-domain-untouched); ruff/mypy/tsc/oxlint clean; browser E2E of both surfaces (201s,
records land in the gitignored JSONL with the right keys + server-resolved origin).

**Aside — external design churn noticed.** The working tree carried uncommitted changes to
`docs/design/frontend/` (README rewritten to "bayleaf **Pipeline Builder** → React",
regenerated `bayleaf.html`/`.dc.html`/`support.js`) — the maintainer's separate "Claude
design" Pipeline-Builder (wishlist #11) work. Left entirely untouched; W12 committed only its
own 11 files.

## Decisions

| Decision | Distilled to |
|---|---|
| W12 = scoped hybrid — per-decision thumbs (primary) + global product FAB (in Layout), one endpoint/store via a `target` discriminator | [tasks.md](../planning/tasks.md) T-042; this journal |
| Add the app's **first write endpoint** (`POST /api/feedback`), scoped as off-gate telemetry; reframe the read-API as "read-only over the DECISION domain" | [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md); [functional.md](../requirements/functional.md) REQ-F-044 |
| `extra="forbid"` as a structural PII guard + server-fixed path + server-resolved origin + json.dumps line integrity | this journal (security posture) |
| Apply the review's write-only-`'form'`-phase simplification; skip the micro-fragment extraction (low-value for MVP) | this journal |

## Open questions & TODO

- **Free-text PII is minimized, not scrubbed** — an email/name-blanking regex or NLP scrub is
  wishlist #14 territory, deferred.
- **Single-worker durability** — the in-process `threading.Lock` serializes appends within one
  uvicorn worker; multi-worker/multi-process needs a file lock or a durable sink (documented,
  not built).
- **No auth / rate-limit** on the endpoint (offline demo); field caps bound per-record size.
  Auth + rate-limiting are the first hardening step if this leaves the demo.
- Reading feedback is out-of-band (tail the JSONL / load into pandas) — there is deliberately
  no read-back GET endpoint.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-042 done
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-044 (feedback)
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — W12 done
- [docs/adr/ADR-0010-ticketing-notify-read-api.md](../adr/ADR-0010-ticketing-notify-read-api.md) — the off-gate write exception
