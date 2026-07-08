# Design Handoff — <Topic> (<YYYY-MM-DD>)

| Field | Value |
|---|---|
| **Status** | Active / Applied / Superseded |
| **Date** | <YYYY-MM-DD> (MST) |
| **From → To** | <reviewer or session> → design |
| **Graded** | <what was reviewed, against which docs> |
| **Related** | [frontend-design-brief.md](../frontend-design-brief.md), <ground-truth docs> |

## Context

One or two lines: what was graded, against which authoritative docs.

## Keep — do not regress

What the current artifact already gets right that a future edit might undo. Include
deliberate omissions that look like gaps (also list them under Traps).

## Change (P1)

Numbered. Each item: the change · "what right looks like" · why it matters.

## Polish (P2)

Numbered, lower-priority refinements.

## Traps

Decisions that look like omissions or mistakes but are deliberate — call them out so the
next iteration does not "fix" them.

## Ground truth

The authoritative docs the design must follow (schema, runbook, metric registry).

## Verify

How to confirm each change actually landed (e.g. open the prototype and click through).
