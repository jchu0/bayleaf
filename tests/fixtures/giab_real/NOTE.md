# Real GIAB tool outputs — committed fixtures

| Field | Value |
|---|---|
| **Origin** | `real-giab` — genuine tool output from the 2026-07-13 live verification pass (`data/real-giab/T7_RUN_STATUS.md`, gitignored). |
| **Sample** | HG002 (NA24385), GIAB Ashkenazim son — a public benchmark cell line, **not a patient**. |
| **Why committed** | These are TINY derived metric files (bytes/KB), so they ride in git as a permanent, CI-runnable proof that the ingest parsers handle real tool output. The heavy inputs (the 122 GB 2×250 BAM, the reference, the query VCF) stay on the external SSD — never committed (CLAUDE.md data-handling). |

## Files

1. **`HG002.wgs.genomewide.selfSM`** — VerifyBamID2 2.0.3, run **genome-wide** on the full HG002
   GRCh38 2×250 BAM. **FREEMIX = 0.000220096** (~0.02%, HG002 clean). **CALIBRATED**: passed the
   marker sanity check *natively* (no `--DisableSanityCheck`), unlike the chr20-capped heuristic —
   100k markers spread across all chromosomes clears the check that two chromosomes did not.
2. **`HG002.subset.happy.summary.csv`** — hap.py (GA4GH, engine `xcmp`) of the real germline
   pipeline's calls (chr20/21/22, 300,175 variants) vs the GIAB v4.2.1 truth. **SNP/PASS
   F1 = 0.989276** (Recall 0.9941, Precision 0.9845); INDEL F1 0.94145. rtg vcfeval cross-check:
   F 0.9828.

Consumed by `tests/test_real_giab_calibrated.py`.
