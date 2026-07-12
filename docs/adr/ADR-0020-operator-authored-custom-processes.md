# ADR-0020 — Operator-authored custom-script Nextflow processes

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-11 (MST) |
| **Deciders** | bayleaf maintainers |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises — a custom script sets no verdict) · [ADR-0003](ADR-0003-deployment-agnostic-ports.md) (deployment-agnostic ports; compose ≠ execute) · [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC + draft→approve lifecycle — the approval gate a custom process runs behind) · [ADR-0019](ADR-0019-pipeline-versioning-run-pinning-edit-lock.md) (pipeline versioning + run pinning) · [design/nextflow-codegen.md](../design/nextflow-codegen.md) (the compile path) · [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) (agents author metadata, a human authors the script) · [requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (#11 the Pipeline Builder) |

## Context

The Nextflow codegen path (`src/pipeguard/nextflow/`, [design/nextflow-codegen.md](../design/nextflow-codegen.md))
compiles a Builder card graph into a runnable pipeline from a **curated catalog**
(`catalog.py`): each catalogued tool card maps to a human-vetted `ProcessSpec` with a real
`script:`. A card outside the catalog compiles to a labelled placeholder that fails loudly on a
real run — never a fabricated command.

That is deliberately safe, but it is also a wall: to run *anything not in the seven-tool germline
catalog* — a `bcftools annotate` step to overlay ClinVar on a called VCF, a lab's in-house
filtering one-liner, a tool no `ProcessSpec` exists for yet — an operator has no in-product path.
Their only options were "wait for a maintainer to add a `ProcessSpec`" or "hand-edit the exported
`main.nf` outside bayleaf." Both defeat the Builder's purpose (compose a runnable pipeline in
the product).

The node-authoring agent ([design/node-authoring-agent.md](../design/node-authoring-agent.md),
[agent-authoring-contract.md](../design/agent-authoring-contract.md)) does **not** close this gap
by design: its **one load-bearing invariant** is that an authoring agent emits *metadata, never a
runnable command* — it fills typed port/version/locator shapes; the `script:`/`stub:` body "lives
solely in the human-curated `ProcessSpec` catalog," and "a human authors the runnable body before
anything compiles." The contract explicitly *assumes a human-authoring surface exists* for the
command body. Until now, that surface did not exist inside the product.

We need a way for a **human operator** to supply a Nextflow process body that runs on a pipeline
output — without (a) letting an agent author executable commands, (b) softening the compose ≠
execute trust seam, or (c) letting an un-reviewed command reach a compute host.

## Decision

Add an **operator-authored custom-script process**: a Builder card on which a **human** provides a
verbatim Nextflow `script:` body (plus optional `container`/`conda` packaging). Concretely:

1. **Model.** `NfNode` (`src/pipeguard/nextflow/compiler.py`) gains three optional fields —
   `script: str | None`, `container: str | None`, `conda: str | None`. A node with a **non-empty**
   `script` is a **custom process** (`NfNode.is_custom()`). The fields are absent on every ordinary
   card, so the change is purely additive.
2. **Compile.** `compile_graph` renders a custom node into a **real** Nextflow process from the
   node's OWN `script` + typed `ins`/`outs`, with channels wired from the graph edges *exactly like
   a catalogued tool* (the same meta-threaded per-sample wiring). **The catalog is never consulted
   for a custom node** — even if its tool name collides with a catalogued one, the operator's body
   wins. The body is emitted byte-for-byte (only re-indented into the `script:` block, as the
   catalogued path already does) — bayleaf never rewrites or fabricates it.
3. **Compile API.** `POST /api/pipelines/compile` (`api/routers/nextflow.py`) accepts the three
   optional fields on a posted node (additively; the existing shape is unchanged), so the Builder
   can post a custom-script card and get real Nextflow back.

A custom card is a first-class runnable process — it does not degrade to the uncatalogued
placeholder — precisely *because* a human authored a real command for it.

## The four-way safety (why this is safe to add)

This ADR exists to record the safety envelope explicitly. A feature that turns operator text into a
command on a compute host is only acceptable because **four independent guardrails** hold at once:

1. **[i] Can't run un-reviewed — an approval gate stands between authoring and execution.** Authoring
   a custom script does not run it. A pipeline only *executes* through `POST /api/pipelines/run`
   (`api/routers/pipeline_run.py`, the W1 gate), which `require_role("reviewer","approver")`, **names
   a saved pipeline** (never a raw posted graph — `extra="forbid"` 422s a smuggled `graph`), and
   resolves + compiles that pipeline's **approver-blessed (`emitted`) snapshot** from the
   `PipelineGraphStore` (which round-trips the graph JSON exactly, so a saved custom node's `script`
   survives; `pipeline_run._to_graph` threads it into the compiled `NfNode`). A name with no approved
   version is a **409, not a silent bypass** (ADR-0017, ADR-0019). So a custom script reaches a
   compute host **only** inside a SAVED, APPROVED pipeline — an approver must bless the exact graph
   (custom body and all) first, and only then is the operator's body actually run. The stateless
   `POST /api/pipelines/compile` path emits text only; it runs nothing.
2. **[ii] Honest label — on the card and in the emitted process.** The compiler emits an honest
   header comment + a `label 'operator_authored'` process directive on every custom process:
   *"operator-authored custom process — runs on the compute host; production needs
   sandboxing/allowlisting; not a curated/catalogued tool. bayleaf transcribed this operator body
   verbatim (compose ≠ execute) — it did not author or vet the command."* The Builder card carries
   the matching honesty (a custom card is visibly not a curated tool). No reader — human or
   downstream tool — can mistake an operator body for a bayleaf-vetted one.
3. **[iii] Agents stay metadata-only; the human authors the script.** This card is the
   **human-authoring surface** the [agent-authoring-contract](../design/agent-authoring-contract.md)
   already assumes. An authoring agent proposes ports/version/locators/prose and **never** a
   `script:`/`stub:` body — the shapes it writes to (`NodeProposal`/`PortSpec`) have no command
   field. The runnable command comes from a human, through *this* card, or from a maintainer adding a
   `ProcessSpec` to the curated catalog. The compose ≠ execute trust seam that keeps agent-authored
   metadata from becoming arbitrary code execution is unchanged — this feature adds the *human* path
   the contract presupposed, not an agent one.
4. **[iv] The core never executes.** `src/pipeguard/` (including `src/pipeguard/nextflow/`) emits
   TEXT and runs nothing — `compile_graph` returns a string bundle and spawns no subprocess (pinned
   by a test). Only the out-of-core drivers (`scripts/run_giab_pipeline.py` + `api/routers/`) ever
   shell out to `nextflow run`, exactly as before this change (ADR-0001, ADR-0003). No new execution
   boundary is crossed; the core stays pure.

A fifth, narrower guard supports these: **never fabricate a command.** A custom card whose body is
blank/whitespace is a `CompileError` (a 422 at the API), never an invented command; an
uncatalogued-*and*-no-script node keeps its existing labelled placeholder. bayleaf emits an
operator's real body or a loud gap — never a guess.

## Assumptions

1. The **approval gate is the security boundary**, not the compiler. The compiler will faithfully
   emit whatever body an operator wrote (that is its job); safety comes from an approver reviewing
   the saved graph before `POST /api/pipelines/run` executes it, plus deployment-side
   sandboxing/allowlisting the emitted comment calls for.
2. An operator authoring a custom card is a trusted, RBAC-gated user (reviewer/approver to run),
   not an anonymous one. This is a research/biotech operations tool, not a public code-execution
   service.
3. Production deployments will sandbox/allowlist the compute host (containers, restricted images,
   no ambient credentials). bayleaf emits the honest warning; it does not itself sandbox.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| **Catalog-only forever** (a maintainer must add every `ProcessSpec`) | The safe status quo, but a hard wall: no in-product path to run anything off the curated chain; every new step is a code change + release. Defeats the Builder. |
| **Let the node-authoring agent emit the `script:`** | Directly violates the agent-authoring contract's one load-bearing invariant (agents author metadata, never commands) — it would turn agent-proposed metadata into a route to arbitrary command execution. Rejected outright. |
| **Free-form command box that bayleaf "wraps"/rewrites into a process** | Any rewriting risks silently changing the operator's intent (a fabricated or mangled command). We emit the body **verbatim** instead, so what runs is exactly what a human wrote and an approver reviewed. |
| **Run custom scripts straight from the stateless `/compile` or a draft graph** | Would let an un-reviewed command reach a compute host. Rejected — execution stays behind the W1 approval gate (safety [i]); compile stays text-only. |

## Consequences

| | |
|---|---|
| **Gains** | An operator can run a real step off the curated catalog (e.g. `bcftools annotate` over a VCF) entirely in-product; the node-author contract's presupposed human-authoring surface now exists; the Builder → runnable-Nextflow story is complete for human-authored steps, not just the seven catalogued tools. |
| **Costs** | The compiler can now emit an arbitrary operator command — so the honest label, the blank-script rejection, and (above all) the W1 approval gate before any run are load-bearing, not optional. (The compiler was robustness-hardened alongside this: `_groovy_escape` on interpolated values incl. operator `conda`/`container` strings, kind/tool/id identifier validation, a File-input source fix, and duplicate-node / fan-in-clobber / proc-name-collision / port-drift guards — `src/pipeguard/nextflow/compiler.py` — so a graph can't smuggle Groovy or silently mis-wire; these harden every process, not just custom ones.) Output filenames aren't known from the typed model, so a custom process declares `path("*")` (captures the work dir); the operator's script is responsible for producing its declared artifacts. A custom process is meta-threaded per-sample, so it expects a per-sample input carrying `meta` (the common "runs on a pipeline output" case); a custom node with only reference/no per-sample inputs is an edge case not specially handled. |
| **Follow-ups** | The Builder's custom-script card UI (authoring surface, the honest label, review affordances) — frontend, built separately. The backend compile + compile-API + run-gate threading are done; the store already round-trips the `script` field, so no persistence change was needed. Optional: let the operator declare output globs (tighter than `path("*")`); a per-deployment allowlist/sandbox profile for the emitted process. |

## Revisit when

1. An operator needs a custom process that is **not** per-sample (a cross-sample aggregator, or a
   no-input source step) — the current always-meta-threaded rendering would need a per-node
   aggregator/source flag, mirroring `ProcessSpec.per_sample`.
2. Custom scripts become common enough that `path("*")` output capture causes real
   input-re-emission or artifact-collision problems — then add operator-declared output globs to the
   card model.
3. The threat model changes (e.g. less-trusted authors, a multi-tenant deployment) — the approval
   gate + deployment sandboxing assumptions above would need to be re-examined and hardened.
