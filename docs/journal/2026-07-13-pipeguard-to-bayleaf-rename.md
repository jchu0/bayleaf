# Journal — 2026-07-13 (MST) — PipeGuard → bayleaf breaking package rename

| Field | Value |
|---|---|
| **Focus** | Execute the deferred, breaking code-identifier rename so the Python package matches the already-user-facing product name (**bayleaf**), and strip the last "PipeGuard" traces from the README. |
| **Participants** | James Hu (maintainer), Claude Code (Opus 4.8) |
| **Outcome** | Repo-wide rename landed atomically (`3c2d533`) — `src/bayleaf/`, `BAYLEAF_*` env vars, `X-Bayleaf-*` wire headers, `name = "bayleaf"`. Full gate green; zero code-identifier residue. |

## Discussion

The product was renamed PipeGuard → **bayleaf** on 2026-07-11, but only on the
user-facing *surface*; the Python package, `PIPEGUARD_*` env vars, and
`X-PipeGuard-*` wire headers were deliberately left as a **deferred breaking pass**
(documented in CLAUDE.md's "Naming" block). The maintainer asked to (1) sweep every
mention of the old name to bayleaf and (2) clean the root README. When the
package-vs-product distinction was surfaced, the maintainer chose the **full breaking
rename** — so this session executed the deferred pass.

**Method — a safe, mechanical, case-preserving sweep.** Recon first established the
rename was *clean*: no CamelCase `PipeGuard` code identifiers exist (only the
standalone product name in prose + the `X-PipeGuard-` header prefix), and
`pipeguardStatus` was the only substring identifier. So four ordered replacements
over every tracked text file (excluding the lockfiles, which were regenerated) were
sufficient — applied **longest/most-specific first** so no rule clobbers another:

1. `X-PipeGuard-` → `X-Bayleaf-` (wire headers)
2. `PIPEGUARD_` → `BAYLEAF_` (env vars)
3. `pipeguard` → `bayleaf` (package / imports / module paths)
4. `PipeGuard` → `bayleaf` (product name in prose)

`src/pipeguard/` was moved with `git mv` (history preserved as renames, `R0xx`), and
the two design-mockup files (`PipeGuard.html`, `PipeGuard.dc.html`) were renamed too.
`pyproject.toml` uses `[tool.setuptools.packages.find] where = ["src"]`, so it
auto-discovered `src/bayleaf/` — only the `name =` line needed the sweep. `uv.lock`
was regenerated (`uv lock` → `bayleaf v0.1.0`) and the editable install rebuilt.

**A tooling footgun worth recording:** the first sweep silently no-op'd because this
is **zsh**, where unquoted `$files` does *not* word-split — `for f in $files` ran once
with the entire newline-joined list as a single "filename" (`File name too long`).
Redone null-safe with `git grep -lzI … | xargs -0 sed -i ''`, which is also the more
robust pattern regardless of shell.

**Known side effect (accepted, per the maintainer's "any mention" instruction):**
archived journals and ADRs that historically said "PipeGuard" now say "bayleaf". This
slightly rewrites the historical record in the docs, but keeps `BAYLEAF_*` / `bayleaf.X`
code references in those docs *accurate to current reality*, which was judged the more
important consistency. One deliberate "PipeGuard" mention was **retained** in CLAUDE.md
to document what the old name was and that git history predates the rename.

## Decisions

| Decision | Distilled to |
|---|---|
| Execute the deferred breaking package rename now (not defer further) | [CLAUDE.md](../../CLAUDE.md) naming block (rewritten: "rename landed 2026-07-13") |
| Commit the rename as ONE atomic change (splitting would leave broken intermediate build states) | commit `3c2d533` |
| Keep one historical "PipeGuard" mention to document the old name | [CLAUDE.md](../../CLAUDE.md) |
| Sweep archived journals/ADRs too (accept historical-prose rewrite for code-ref accuracy) | this entry |

## Open questions & TODO

- Push `rename/pipeguard-to-bayleaf` + open a PR to `main` — pending maintainer's go-ahead.
- No behavioral changes intended; if any external tooling hard-codes `PIPEGUARD_*` env
  vars or `X-PipeGuard-*` headers (e.g. a deployment secret), it must be updated to the
  `BAYLEAF_*` / `X-Bayleaf-*` names. `.env.example` already reflects the new prefix.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) — naming block updated to state the rename landed.
- [README.md](../../README.md) — removed the "Formerly PipeGuard" note + "Name vs. package" callout.
