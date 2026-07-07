# Documentation Habits

- **Status:** active
- **Last updated:** 2026-07-07 (MST)
- **Audience:** all (contributors and Claude Code)

How this repository documents engineering work. The aim is narrow and practical:
keep the project easy to understand, review, demo, and safely extend — and fight
the knowledge siloing that makes bioinformatics work so painful to hand off.

## Why we document

A genomics pipeline accumulates decisions, thresholds, file conventions, and
hard-won fixes that live in one person's head until they leave. This project
treats that knowledge as a first-class output. Documentation here exists to make
the *why* recoverable, the *inputs and outputs* traceable, and the *next step*
obvious — for a teammate, a judge, a future maintainer, or a fresh Claude session.

## Core principles

1. **Explain why before what.** The reasoning behind a choice outlasts the code
   that implements it. Lead with intent; the mechanism is secondary.
2. **Keep decisions visible.** Every load-bearing choice becomes an ADR
   (`docs/design/decisions/`) — one decision per file, with the alternatives we
   rejected and why.
3. **Document assumptions and boundaries.** State what we assume to be true and
   where a component's responsibility ends. Silent assumptions are future bugs.
4. **Keep docs close to the code.** Docs live in the repo, move with it, and are
   updated in the same change as the behavior they describe.
5. **Small and current beats large and stale.** A focused, correct doc is worth
   more than an exhaustive one nobody trusts. Split before a doc sprawls.
6. **Update docs when behavior changes.** A behavior change with no doc change is
   an incomplete change.
7. **Tie claims to verification.** When a doc asserts something works, say how it
   was checked.
8. **Track shortcuts, risks, and limits.** Name what we deferred or simplified,
   in the open. A recorded limitation is a feature of an honest project.
9. **Make setup and demo reproducible.** Anyone should be able to run and demo the
   project from the docs alone.
10. **Preserve operational knowledge as it accrues.** Recurring failures, fixes,
    and thresholds get written down so the answer isn't re-derived every time.

## Necessary documentation stack

We keep a robust set, not a minimal one — anti-siloing is worth the pages. Each
doc owns one question.

| Doc | Owns the question |
|---|---|
| `README.md` | what is this, who is it for, how do I run and demo it, where are the deeper docs |
| `docs/TABLE_OF_CONTENTS.md` | what docs exist and which code they map to (**start here**) |
| `docs/reference/domain-primer.md` | the rare-disease / GIAB / gnomAD / ClinVar background |
| `docs/reference/glossary.md` | terms and acronyms across bioinformatics, software, and clinical |
| `docs/design/architecture.md` | system shape, components, data flow, external services, tradeoffs |
| `docs/design/configuration.md` | the config layer and deployment/agent profiles |
| `docs/design/structure.md` | repo + data layout, and the doc-to-code map |
| `docs/design/decisions/` | important decisions, alternatives, consequences (one per file) |
| `docs/data/schemas.md` | artifact contracts: required/optional fields, types, missing-semantics |
| `docs/data/qc_metrics.md` | the QC metric set and gate thresholds |
| `docs/data/provenance.md` | the I/O lineage model and ledger format |
| `docs/data/licensing.md` | per-tool licenses in the stack, for transparency |
| `docs/quality/evaluation.md` | what "good" means, how outputs are checked, failure modes |
| `docs/quality/risks.md` | technical / product / data / demo risks and mitigations |
| `docs/demo/demo_plan.md` | the demo flow, expected I/O, and the fallback path |

## Style

- Plain language. Short sections. Tables and checklists where they earn their place.
- No filler. If a sentence doesn't change what a reader would do, cut it.
- Mark unknowns explicitly, and distinguish **Fact**, **Assumption**, **Decision**,
  and **TODO** where confusion is likely.
- Examples small and real (a single sample bundle, not a synthetic wall of JSON).
- Don't over-document features that don't exist yet — a wishlist line is enough.

## Templates and consistency

Consistency is what keeps a new session from drifting. Before creating a doc:

1. Look in `docs/_templates/` for a matching template and follow it.
2. If no template fits, **create the template first**, then the doc.

This is also a CLAUDE.md rule, so it holds across sessions.

## Dating and timestamps

Every doc carries a `Last updated: YYYY-MM-DD (MST)` line; append-only entries
(ADRs, journal, ledgers) are dated per entry. We standardize on **MST (UTC-7,
Arizona)** so dates are unambiguous regardless of who or what wrote them.

## Journal → canonical flow

Working sessions are captured raw in `docs/journal/YYYY-MM-DD-<topic>.md` — the
full reasoning, including paths not taken. At the end of a session, the durable
parts are **distilled** into canonical docs (the *why* → an ADR; a behavior
change → the relevant doc). The journal entry then stays as the dated archive; it
is never the source of truth. This gives us traceability (the raw thought process
is preserved) without maintaining two competing "current" versions.

## When to update docs

Update on any of: setup change · interface/API change · architecture change · new
dependency · behavior change · demo-flow change · evaluation-criteria change ·
security or privacy assumption change · a newly discovered limitation · a major
bug or failure worth remembering.

## Claude documentation behavior

- **Write original prose.** Do not copy from other repositories, old templates, or
  prior generated material. Write for this project's actual needs.
- **Scan, don't slurp.** At session start, read `docs/TABLE_OF_CONTENTS.md` and
  load only the files relevant to the task — not the whole repo.
- **Prefer updating over duplicating.** Extend an existing doc before adding a new one.
- **Keep docs proportional to the project's stage.**
- **Update docs in the same change as the code**, and include verification steps
  when a claim needs them.
- **Document assumptions instead of inventing certainty.**
- **Summarize** files created or changed at the end of a documentation task.

## Delivery posture (MVP-first, production-ready seams)

This is a hackathon build with genuine production intent. Prioritize a working,
understandable core flow — but build it behind seams (ports, interfaces, config)
so the path to production isn't foreclosed. During the sprint, prioritize the
README, architecture, demo plan, evaluation, and risks; skip heavyweight process
docs. Keep everything useful to judges, collaborators, and future cleanup, and
**preserve known limitations rather than hiding them.**

## Non-goals

This guide is not an SDLC framework, a compliance system, a substitute for
engineering judgment, a home for boilerplate, or a reason to slow shipping.
