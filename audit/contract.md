## Contract auditor — PipeGuard release-hardening (Track A, Fable 5, code-only/headless)

**Scope.** Cross-boundary agreement audit across `frontend/src/types.ts` ↔ `api/main.py` + `api/routers/*` ↔ `src/pipeguard/models.py`; agent output models ↔ their frontend renderers; `catalog.py`/`node_author` port-kind vocab ↔ frontend `ArtifactKind`; `PipelineGraph` envelope ↔ `NfGraph`/`CompileEdge`; store record shapes ↔ readers. Every claim below was re-opened and the quoted string confirmed.

**Headline.** The contract layer is unusually disciplined for a hackathon build: the alias round-trip, the runbook double-shape, `content_hash` exclusions, `confidence`-null, the subject-id `extra="forbid"` seam, the agent `mode`/`generated_by` alias, and every scalar enum (Verdict/Gate/Severity/PipelineStatus/TicketStatus/IntakeStatus) all match across the wire. The **one real drift is the hand-kept `MonitoringSignature` mirror** (comment lies + one served field untyped + `trend` mistyped), which the consuming component silently patches with an `as` cast — defeating TypeScript's drift detection. Two further Low items are latent gaps in the honestly-unwired `node_author` agent. **No Blockers.**

---

### CON-01 · `MonitoringSignature` FE mirror is stale + drops a served field, patched by an unsafe cast
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency
- **Area / journey:** Operate hop 4 — Monitoring (`/monitoring`, `GET /api/monitoring`, §7 signature table).
- **Evidence:**
  - Producer serves four fields, three non-optional-ish: `api/main.py:1255-1258` — `first_seen: str | None = None`, `last_seen: str | None = None`, `trend: Literal["up", "down", "flat"] = "flat"`, `affected_run_ids: list[str] = Field(default_factory=list)`; assembled at `api/main.py:1410-1413`.
  - Consumer type is stale + incomplete: `frontend/src/types.ts:346-347` comment `// first_seen/last_seen/trend are NOT yet served (F2) — kept optional so the row can render`; the type `frontend/src/types.ts:348-357` **omits `affected_run_ids` entirely** and declares `trend?: 'up' | 'down' | 'flat' | null` (optional/nullable vs the backend's required-with-default).
  - The renderer works around the frozen type with a cast: `frontend/src/components/MonitoringSignatureRow.tsx:10` `type SignatureWithRuns = MonitoringSignature & { affected_run_ids?: string[] }` and `:60` `const affectedRuns = (sig as SignatureWithRuns).affected_run_ids ?? []`. Cols 3/5 already render `first_seen`/`last_seen`/`trend` (`:112-128`).
- **Reproduction:** `curl /api/monitoring` → payload carries `affected_run_ids` + populated `first_seen`/`last_seen`/`trend`; grep `affected_run_ids` in `types.ts` → absent; the row reads it only via the `as` cast.
- **Expected:** the hand-kept mirror types every served field, and comments describe reality.
- **Actual:** the shared contract lies ("NOT yet served") and omits `affected_run_ids`, so the one consumer that needs it bypasses the type with `as` — a rename/reshape on the backend would produce **no compile error**, exactly the silent-drift class this audit targets. `trend` mistyping is benign (FE accepts a superset).
- **Root cause:** F2 backfill (`docs/journal/2026-07-09-frontend-design-replication-scope.md:60`) landed on the backend and in the component but the frozen `types.ts` mirror + comment were never updated.
- **Min fix:** in `types.ts:348-357` add `affected_run_ids: string[]`, change `trend` to `trend: 'up' | 'down' | 'flat'`, and delete the "NOT yet served (F2)" comment; drop the `SignatureWithRuns` cast in `MonitoringSignatureRow.tsx:10,60` and read `sig.affected_run_ids` directly.
- **Larger fix:** none warranted (generating `types.ts` from the pydantic schema is post-hackathon).
- **Demo-critical:** N (renders correctly today via the workaround). · **Risk of fixing now:** Low (additive type + cast removal). · **Regression test:** a contract test asserting `set(MonitoringSignature.model_fields) ⊆ typed keys`, or a Vitest that `api.getMonitoring()` returns rows with a typed `affected_run_ids`.

---

### CON-02 · `node_author` core `ARTIFACT_KINDS` mirror has drifted from the frontend builder vocab it claims to track
- **Severity:** Low · **Confidence:** Confirmed · **Category:** design-inconsistency
- **Area / journey:** Builder / Create-a-tool (node-authoring agent, core-only).
- **Evidence:** `src/pipeguard/node_author/models.py:44-46` docstring claims the set is "the union of every BTOOLSPEC in/out kind and every emitted GIAB_LOC locator kind … a periodic sweep keeps the two in sync." The literal at `src/pipeguard/node_author/models.py:47-64` lists 14 kinds and includes only `mosdepth_summary` + `mosdepth_thresholds`. But `frontend/src/components/BuilderShared.tsx:216` gives `mosdepth` five outputs — `mosdepth_summary, mosdepth_thresholds, mosdepth_regions, mosdepth_global_dist, mosdepth_region_dist` — and the runtime union `frontend/src/components/BuilderShared.tsx:860-862` (`ARTIFACT_KINDS`) therefore contains `mosdepth_regions`, `mosdepth_global_dist`, `mosdepth_region_dist`, which the core mirror **omits**.
- **Reproduction:** diff the two sets; the three `mosdepth_*` sub-kinds are present in the FE union, absent in `node_author`.
- **Expected:** `PortSpec.known` (`node_author/models.py:107-109`, computed from `ARTIFACT_KINDS`) treats a real builder kind as known/wireable.
- **Actual:** a proposed node with a `mosdepth_regions`/`_global_dist`/`_region_dist` port would be scored `known=False` → RESERVED (unwired), mislabeling three genuinely-wireable builder kinds. Latent only because the agent is on no wire (see CON-03).
- **Root cause:** the mosdepth multi-output expansion landed in `BuilderShared.tsx` after the core literal was hand-mirrored; the "periodic sweep" never ran.
- **Min fix:** add `mosdepth_regions`, `mosdepth_global_dist`, `mosdepth_region_dist` to the frozenset at `node_author/models.py:47-64`.
- **Larger fix:** a test that fails when the core mirror ≠ the frontend `ARTIFACT_KINDS` union (needs the FE list exported to a shared fixture).
- **Demo-critical:** N. · **Risk of fixing now:** Low. · **Regression test:** `assert {"mosdepth_regions","mosdepth_global_dist","mosdepth_region_dist"} <= ARTIFACT_KINDS`.

---

### CON-03 · `NodeProposal` structured-output contract exists but rides no transport (no API, no FE consumer)
- **Severity:** Low · **Confidence:** Confirmed · **Category:** incomplete-integration
- **Area / journey:** Builder / Create-a-tool.
- **Evidence:** the model is fully specified at `src/pipeguard/node_author/models.py:187` (`class NodeProposal`, with `inputs`/`outputs: list[PortSpec]`, `reserved_kinds`, `:214-216`). Absence proofs: `grep -rn "node_author\|propose_node\|NodeProposal" api/` → **empty**; `grep -rn "propose_node\|NodeProposal" frontend/src/` → **empty** (only unrelated hits: `SettingsModelTier.tsx:53` roster row with `wired: false`, and comments in `BuilderModals.tsx:52`).
- **Expected / disposition:** per the audit mandate, a core-only phase-2 seam is fine **provided nothing claims it is wired** — confirm the label is honest. It is: the Settings roster row is `wired:false, phase2:true`, and `AuthorToolNodeModal` is a static mock (cross-refs journeys/integration auditors).
- **Actual:** a producer-side pydantic contract with no consumer on either boundary — a "contract with no transport." Honest today, but the contract carries no test guaranteeing that if it *is* wired the FE renderer matches it.
- **Root cause:** T-046 shipped the agent core-only; endpoint + modal accept-handler are unbuilt.
- **Min fix (documentation-only for Track A):** none required for the demo; keep as a P2/P3 note that `NodeProposal` has no FE mirror type yet.
- **Demo-critical:** N. · **Risk of fixing now:** N/A (no fix intended pre-hackathon). · **Regression test:** when wired, a round-trip test `NodeProposal.model_dump()` ↔ a new `types.ts` `NodeProposal`.

---

### CON-04 · `IntakeStatus.status` is an unconstrained `str` on the producer but a 4-literal union on the consumer
- **Severity:** Low · **Confidence:** Confirmed · **Category:** post-hackathon-improvement
- **Area / journey:** Operate hops 1-2 — Submit / intake-status poll (`GET /api/runs/{id}/intake-status`).
- **Evidence:** producer types the field open: `api/routers/intake.py:87` `status: str` (the `_Job.status` is also bare `str`, `:47`). Consumer narrows it: `frontend/src/types.ts:711-713` `status: 'queued' | 'running' | 'complete' | 'failed'`, and `Submit.tsx:442,445` branches on `=== 'complete'` / `=== 'failed'`.
- **Actual/expected:** values match **today** — the backend only ever assigns `queued|running|complete|failed` (`intake.py:105,115,118,122,147,165`), so this is honest now. But the contract is enforced only on one side; a future 5th status (e.g. `cancelled`) would silently violate the FE literal with no compile-time signal. (Contrast the sibling `PipelineRunStatus`, `types.ts:201`, which correctly types `status: string`.)
- **Root cause:** the pydantic model uses a plain `str` where a `Literal[...]` would pin the contract.
- **Min fix:** change `api/routers/intake.py:87` (and `_Job.status`) to `Literal["queued","running","complete","failed"]` so producer and consumer are pinned together.
- **Demo-critical:** N. · **Risk of fixing now:** Low (values already conform). · **Regression test:** a test that submits and asserts the polled status ∈ the literal set.

---

### CON-05 · Frontend `TriageNote` type drops the backend's served `addresses_signatures`
- **Severity:** Low · **Confidence:** Confirmed · **Category:** design-inconsistency
- **Area / journey:** Agent triage panel (`/runs/:id/agent`).
- **Evidence:** backend serves it: `src/pipeguard/triage/models.py:98` `addresses_signatures: list[str] = Field(...)` (and it is part of the record's `content_hash`, `triage/models.py:124`). Frontend type omits it: `frontend/src/types.ts:210-221` lists `addresses_rule_ids` but not `addresses_signatures`.
- **Actual/expected:** non-breaking — the FE simply never reads the extra field — but it is an incomplete mirror of a served field on a golden-path agent surface; a future FE feature that groups triage notes by signature would have to re-add or cast it (same class as CON-01, lower stakes).
- **Root cause:** hand-kept `types.ts` mirror trimmed to the fields the current renderer reads.
- **Min fix:** add `addresses_signatures: string[]` to `types.ts:210-221`.
- **Demo-critical:** N. · **Risk of fixing now:** Low (additive). · **Regression test:** field-parity assertion between `TriageNote` pydantic fields and the TS type.

---

## Honest surfaces (verified clean — do not re-litigate)

These checklist items were traced to both boundaries and **confirmed matching**; they are the report's clean signal:

1. **`CompileEdge from→src` alias (checklist #4).** `api/routers/nextflow.py:39-44` `src: CompilePort = Field(alias="from")` + `to: CompilePort` + `populate_by_name=True`, `CompilePort={node:str, idx:int}` (`:34-36`). Consumer `frontend/src/types.ts:170-173` emits `edges: { from:{node,idx}; to:{node,idx} }[]`, assembled at `BuilderModals.tsx:828-829`. **Exact match.**
2. **`subject_id`/`tissue` split (checklist #5).** Core `Sample` carries them (`src/pipeguard/models.py:313-314`) but `SampleIn`/`SubmitRunIn` are `ConfigDict(extra="forbid")` with no subject field (`api/routers/intake.py:58-64,67-75`), and the FE wire type has no subject field (`types.ts:698-703`). No schema implies a subject wire path — a smuggled field would 422. **Honest.**
3. **`DecisionCard.confidence` (checklist #6).** `float | None = Field(None, ...)` (`models.py:231-233`); `grep -rn "confidence=" src/pipeguard api/` → **no assignment anywhere**, so it is uniformly `null` on the wire; `grep confidence` across `frontend/src/screens|components` → no meter/bar renderer. **Honest (G4 upheld).**
4. **`content_hash` exclusions (checklist #7).** `DecisionCard.content_hash` (`models.py:296-306`) hashes an explicit key set (`sample_id/verdict/headline/rationale/next_steps/finding_hashes/generated_by`) — **excludes `run_id` and `metric_values`** exactly as documented; `Finding`/`MetricValue` hashes exclude `id`/`created_at` (`models.py:190-198,392`). **Honest.**
5. **Two runbook shapes (checklist #8).** `RunbookThreshold.gate: float` vs `pipeline_gate: Gate` (`api/main.py:178-182`) is mirrored precisely by `types.ts:412-421` (`gate: number` "NOT the pipeline gate" / `pipeline_gate: Gate`); the separate `QCThreshold` (`runbook.py:13-36`, `GET /api/config`) carries only the numeric `gate`. Gate meaning is **not conflated.**
6. **Status enums (checklist #2).** `PipelineStatus` = `draft|pending_review|approved` (`api/pipeline.py:33` ↔ `types.ts:435`); `TicketStatus` = `open|in_review|resolved` (`review_queue.py:49` ↔ `types.ts:516`); `IntakeStatus` values = `queued|running|complete|failed` (both sides). **All match.** The "README §7 stale alias" hypothesis: the shipped `README.md` does not misstate these; hyphenated `in-review`/`pending` appear only in illustrative design-source mockups (`docs/design/frontend/source/PipeGuard.dc.html`), already dispositioned "treat README §7 TS as illustrative" (`docs/journal/2026-07-09-frontend-design-replication-scope.md:84`).
7. **`ArtifactKind` reserved-port structural honesty (checklist #3).** `PortSpec.known` is a computed property (`node_author/models.py:107-109`) — a port is wired iff its kind ∈ `ARTIFACT_KINDS`, so reserved kinds structurally cannot fabricate a wired port. (The *contents* of that set have drifted — CON-02 — but the structural guarantee holds.) Note the vocabulary is deliberately three-way: the typed `ArtifactKind` union (`types.ts:320-325`, provenance/`LayoutLocator.kind`), the runtime builder union (`BuilderShared.tsx:860`), and the core mirror — they serve different surfaces and only the core mirror is drifted.
8. **Scalar enum parity.** `Verdict` (proceed/hold/rerun/escalate), `Severity` (info/warn/critical), `Gate` (preflight/qc/variant) all match `models.py:31-52` ↔ `types.ts:3-5`.
9. **`RepairProposal` ↔ `AgentProposal` (owned agent-output seam).** Backend exposes a computed `mode` alias for `generated_by` (`pipeline_repair/models.py:196-203`) so the React `AgentProposal` shape (`types.ts:594-611`) maps 1:1 with no rename at the seam; `advisory: Literal[True]` and no verdict/confidence field (G1). **Honest.**
