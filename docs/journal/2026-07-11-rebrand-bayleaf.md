# 2026-07-11 (MST) — Product rebrand: bayleaf → bayleaf (surface only)

**Branch:** `feat/rebrand-bayleaf` — a git worktree off `main`, isolated from the in-flight
`feat/custom-script-io` WIP (which was left untouched).

## What & why

Renamed the **product** from bayleaf to **bayleaf** (tagline: *"Add subtle flavor to your NGS
project"*) across the user-facing surface, and replaced the logo/favicon with a bay-leaf mark.
Scope was deliberately the **brand surface, not the code**: the Python package stays `bayleaf`
(imports, `BAYLEAF_*` env vars, `src/bayleaf/`), and the `X-Bayleaf-*` wire headers are
unchanged — renaming those is a separate, breaking, coordinated change for a later pass.

## Changed (15 files)

1. **Icons / logos** — new `frontend/src/components/Logo.tsx` (a reusable bay-leaf mark: veined
   blade, tunable `leaf`/`vein` colors) + rewrote `frontend/public/favicon.svg` (green rounded
   tile + white veined leaf). Wired the mark into the Sidebar tile and the Login tile, replacing
   the DNA-helix glyph and the `ShieldCheck` icon (the now-unused `ShieldCheck` import was dropped).
2. **Brand strings** — `bayleaf` in the Sidebar wordmark + link title, Login wordmark, `index.html`
   `<title>` (+ `theme-color`/`description` meta), `frontend/package.json` `name`, Streamlit page
   title / `st.title` / docstring (icon 🧬 → 🌿), FastAPI `title="bayleaf API"`, the FeedbackWidget
   product label, and the rendered in-UI mentions in `RunReport`, `BuilderModals`, `BuilderShared`,
   `Lineage`, `Admin`.
3. **README** — top-level `README.md` rebranded (title `# bayleaf 🌿`, the tagline, and a
   **"Name vs. package"** note stating the importable package is still `bayleaf` so every command
   still works verbatim); `frontend/README.md` given a bayleaf header.

## Deliberately NOT changed (deferred to the package-rename pass)

1. The `bayleaf` Python package/module, all `BAYLEAF_*` env vars, `from bayleaf import …`.
2. The `X-Bayleaf-*` HTTP wire headers (11 refs across `api/` + `frontend/`) — internal protocol,
   invisible to users, breaking to rename in lockstep.
3. Code comments / FastAPI route docstrings mentioning bayleaf (2 left: `RunReport.tsx:180`
   comment, `api/main.py:550` docstring), plus the wider `docs/` tree.

## Verification

1. `tsc -b`: the ONLY error is a pre-existing `InboxContext.tsx(254) assignee` error on `main`
   (unrelated to the rebrand; already fixed in the `feat/custom-script-io` WIP). All 15 rebranded
   files are type-clean.
2. `oxlint` over every rebranded file: clean (exit 0).
3. Live dev server (worktree, :5199): the Sidebar renders the green tile + white leaf + "bayleaf";
   the browser tab title is "bayleaf"; the favicon renders as the green-tile bay-leaf mark.

## Also on this branch: a pre-existing `main` type-error fix (at the maintainer's request)

While verifying the rebrand's `tsc`, we found a **pre-existing** error on `main` (and identically on
`feat/custom-script-io`, committed + WIP — their `InboxContext.tsx`/`types.ts`/`api.ts` are
byte-identical): `frontend/src/context/InboxContext.tsx(254)` reads `t.assignee`, but `refresh()`
(line ~206) projected the `Ticket[]` from `api.listTickets` down to an 8-field object that dropped
`assignee`, and the state's inline type matched that narrow shape. **Fix:** stop the lossy projection
and store the full `Ticket[]` (`setTickets([...open, ...inReview])`) + type the state
`useState<Ticket[]>` (`import type { Ticket }`). This also corrects a **latent runtime bug** — the
derived tickets' `assignee` was always `null` at runtime despite the code's documented intent to fall
back to "the ticket's REAL review-queue assignee." Deliberately applied HERE (not on the shared
`feat/custom-script-io`) to avoid disturbing in-flight work; it flows to `main` whenever this branch
merges. `tsc -b` on the whole frontend now passes with **zero** errors.
