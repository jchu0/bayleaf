# PipeGuard data

Origin labels for everything in this directory. Full strategy:
[docs/data/strategy.md](../docs/data/strategy.md).

Origin labels: `real-giab` (real GIAB HG002 + NIST truth) · `synthetic`
(programmatically perturbed for labeled failure modes) · `contrived`
(hand-authored demo — realistic format, invented values).

| Dataset | Origin | Notes |
|---|---|---|
| `mock_run_01/` | `contrived` | Hand-authored session-1 demo. Realistic Illumina formats, **invented** values — barcodes, QC numbers, and the planted S4 barcode swap + S5 borderline QC. **Not GIAB.** To be superseded/augmented by real + synthetic bundles. |

Do **not** commit raw reads or large artifacts — commit accessions + a fetch
script instead (see `.gitignore` and the data strategy).
