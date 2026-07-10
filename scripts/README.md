# scripts/

Operational scripts for PipeGuard. These run *outside* the app's normal flow —
some need the separate genomics toolchain (bioconda/containers), which is kept
apart from the app's `uv` environment on purpose (CLAUDE.md coding standard 4).

## `fetch_giab_hg002.py` — real GIAB HG002 subset fetcher (origin `real-giab`)

Fetches a small, panel-scoped subset of the **real** GIAB HG002 benchmark so the
coverage/faithfulness gates can be validated against NIST truth data — without
ever committing raw bytes to git (CLAUDE.md Data-handling rule 1). The reproducible
record is the committed manifest [`giab_hg002_manifest.json`](giab_hg002_manifest.json);
the bytes land in the **git-ignored** `data/real-giab/`.

### What it fetches (and why a subset)

Grounded in the NIST GIAB **v4.2.1** small-variant benchmark release for
**HG002 / NA24385** on **GRCh38** (see the manifest for exact URLs):

1. `truth-vcf` — `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` (~149M): the
   gold-standard variant "answer key" (chr1–22).
2. `truth-vcf-index` — its `.tbi` (~1.6M): needed for region restriction.
3. `high-conf-bed` — `..._benchmark_noinconsistent.bed` (~11M): the
   high-confidence regions; faithfulness claims are only valid inside these.
4. `reads` **(opt-in, `--with-reads`)** — a **panel-region slice** of the
   2×250 Illumina BAM. The whole BAM is **122G and is never downloaded**;
   `samtools view -M -L <panel.bed> <remote-url>` streams only the reads
   overlapping the panel, producing a small local subset BAM.

Why a subset: whole-genome reads are 100+ GB and pointless for a demo/QC gate.
The truth VCF + BED are the compact, canonical artifacts; a panel-region reads
slice is enough to produce real `mosdepth`/coverage metrics (docs/data/strategy.md).

### Prerequisites

| Step | Needs |
|---|---|
| Truth VCF/BED/`.tbi` download (default) | Just Python 3.10+ and network — stdlib `urllib`/`hashlib`, no extra tools. |
| `--panel-bed` (restrict truth VCF to a panel) | `bcftools` + `tabix` (bioconda). |
| `--with-reads` (panel-region reads slice) | `samtools` (bioconda) built with remote (libcurl) support. |

The genomics tools are **not** in the app's `uv` env. Install via e.g.
`conda install -c bioconda samtools bcftools tabix`, or run the step inside the
project's genomics container. Missing a required tool → the script fails loudly
with an install hint; being offline / a moved accession → a clear connectivity
error naming the URL to re-verify.

### How to run

```bash
# 1. Dry-run: print the exact plan (URLs, destinations, checksum posture); fetch nothing.
python scripts/fetch_giab_hg002.py --dry-run

# 2. Fetch the small truth artifacts into the git-ignored data/real-giab/.
python scripts/fetch_giab_hg002.py

# 3. Also produce a panel-scoped truth VCF (needs bcftools/tabix).
python scripts/fetch_giab_hg002.py --panel-bed scripts/panel_regions.example.bed

# 4. Also slice a panel-region reads BAM (needs samtools; --panel-bed required).
python scripts/fetch_giab_hg002.py --with-reads --panel-bed scripts/panel_regions.example.bed
```

`scripts/panel_regions.example.bed` is **illustrative** (arbitrary chr20 smoke-test
windows, not a clinical panel) — replace it with your real panel BED.

Useful flags: `--target-dir` (override the destination), `--force` (re-download
even if present), `--manifest` (use a different manifest), `-v` (debug logging).

### Behavior guarantees

1. **Idempotent** — an already-present file is verified and skipped, not re-pulled.
2. **Atomic** — downloads write to `*.part` and rename on success, so an
   interrupted run never leaves a truncated file masquerading as complete.
3. **Checksum-verifying** — pinned checksums are enforced (mismatch → hard error).
   GIAB publishes no checksums file for the v4.2.1 truth artifacts, so those are
   unpinned: the script logs the computed sha256 for you to pin in the manifest.
   The reads `.bai` **is** verified against GIAB's real published md5.
4. **No secrets** — GIAB data is fully public; no keys/tokens are used or needed.
5. **Never commits data** — everything lands under the git-ignored `data/real-giab/`.

### Verified offline

The pure logic is unit-tested with **no network and no genomics tools** in
[`tests/test_fetch_giab.py`](../tests/test_fetch_giab.py) (manifest parsing,
target-path construction, checksum verify, the `--dry-run` plan, and the
missing-tool / connectivity error paths — the network seam is an injected
in-memory opener). It is covered by `make check` (ruff + strict mypy + pytest).

Related: [`docs/data/strategy.md`](../docs/data/strategy.md) · task **T-013**
(GIAB half) / **T-017** groundwork · [ADR-0004](../docs/adr/ADR-0004-vcf-first-giab-substrate.md).

## `gate_giab.py` — real GIAB data through the QC gate (T-017)

Once the reads slice is fetched (`--with-reads`), this runs the **real** panel data
through the deterministic gate:

```bash
# needs mosdepth on PATH (bioconda), plus the fetched panel BAM
conda install -n hackathon -c conda-forge -c bioconda mosdepth
PATH=/path/to/env/bin:$PATH python scripts/gate_giab.py
```

It runs `mosdepth --by <panel.bed>` for the real in-panel **mean coverage + breadth**,
writes a git-ignored `data/real-giab/run/` directory carrying that real coverage in the
parsers' on-disk shape, and gates it with a coverage-focused runbook (reusing `run_gate`
and the registry-backed rules unchanged). Honest scope: a BAM yields coverage/breadth, not
the fastq/run metrics (Q30/dup/PF) — so it gates the metric the artifact actually holds.
Validated end-to-end: HG002 panel = **55.8× coverage** (clears the 30× gate), **99% ≥ 20×**.

## `seed_giab_demo.py` — populate the live app with GIAB-themed **synthetic** runs

Seeds ~24 **synthetic** runs (`origin=contrived`) with **GIAB sample names** (HG00x / NA2xxxx)
directly into `data/` so the live operator UI has volume for UI/UX testing — Runs pagination +
status/verdict/platform facets, Monitoring windows, Provenance, Archive, and (with `--tickets`)
the Review queue all populate. Honest: the run data is contrived, only the sample labels are
GIAB-flavored; it never touches the genuinely-fetched `data/RUN-2026-07-08-GIAB-HG002`
(`origin=real-giab`) or the committed `mock_run_0x`. The generated dirs are git-ignored
(`data/RUN-*-GIAB-*/`) — this script is the reproducible record.

```bash
uv run python scripts/seed_giab_demo.py                 # write ~24 RUN-*-GIAB-{A,B} dirs
uv run python scripts/seed_giab_demo.py --tickets        # + POST ~8 Review-queue tickets (API up)
uv run python scripts/seed_giab_demo.py --clean          # regenerate (remove prior seed dirs first)
```

Uses the failure-mode generator so each planted mode round-trips to a real verdict (~1/3 of runs
all-CLEAN → **released**, the rest a hold/rerun/escalate mix → **needs_review**), rotates four
platforms (NovaSeq X / NextSeq 2000 / NovaSeq 6000 / MiSeq), and spreads dates across ~5 weeks so
the Monitoring 7/14/30d windows split. Sample IDs use an anti-substring GIAB pool (never
lane-suffixed) so the `pipeline.log` substring rules don't cross-fire.

## `run_giab_pipeline.py` — real GIAB fastqs through the *outlined* pipeline → dashboard

Where `gate_giab.py` reads the pre-aligned NIST panel BAM, this **actually executes the
Pipeline-Builder germline chain from raw reads** on the real GIAB HG002 panel fastqs, then
lands a **dashboard-discoverable** run so the operator UI shows it exactly like a mock run —
every number derived from real reads:

```bash
# needs the bioconda toolchain on PATH: fastp, bwa-mem2, samtools, mosdepth, bcftools
conda install -n hackathon -c conda-forge -c bioconda fastp bwa-mem2 samtools mosdepth bcftools
# one-time reference prep (git-ignored): chr20 GRCh38 + bwa-mem2 index
#   curl -o data/real-giab/ref/chr20.fa.gz https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr20.fa.gz
#   gunzip data/real-giab/ref/chr20.fa.gz && samtools faidx data/real-giab/ref/chr20.fa && bwa-mem2 index data/real-giab/ref/chr20.fa
PATH=/path/to/env/bin:$PATH uv run python scripts/run_giab_pipeline.py
```

Chain: `fastp` (trim + Q30/dup/PF) → `bwa-mem2 mem` (align to chr20 — the panel is chr20 windows)
→ `samtools fixmate/markdup` → `{mosdepth --by <panel>, bcftools mpileup|call -mv|norm}`. It writes
`data/<run_id>/` with the frozen-five CSVs (real `qc_metrics.csv`) + a narrated `pipeline.log` +
`origin=real-giab`, then runs the *unchanged* `run_gate` with the **default runbook** — the same
recompute the read-API serves, so the run appears in the operator UI. **compose ≠ execute** holds:
this is a standalone driver of the external toolchain, not the app running a tool.

Validated E2E: HG002 panel → **Q30 88.2% · reads-PF 99.3% · 54.2× · dup 0.006% · 553 variants**;
the four measurable metrics clear their gates, and the run gates to **HOLD** on the honest
*cluster-PF-missing* signal (a run-level SAV metric a fastq→BAM path can't produce — flagged, not
fabricated). The run dir is git-ignored (derived from the git-ignored reads).
