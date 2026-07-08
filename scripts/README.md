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
