#!/usr/bin/env bash
# Fetch a panel-region slice of GIAB Ashkenazim-trio samples as paired FASTQ (origin: real-giab).
#
# Why this script exists
# ----------------------
# The live driver (scripts/run_giab_pipeline.py) runs a real, multi-sample germline pipeline from
# FASTQ. This produces the panel-scale FASTQ for the samples in its on-disk registry (GIAB_SAMPLE_IDS
# = HG002 + HG003 + HG004). Per CLAUDE.md data-handling, raw reads are NEVER committed — only this
# reproducible fetch script is; the ~7 MB/sample FASTQ land git-ignored under data/real-giab/fastq/.
#
# How it stays small
# ------------------
# The full 2x250 BAM per sample is ~118-130 GB and is NEVER downloaded. samtools (built with
# libcurl) streams ONLY the reads overlapping the panel BED from the remote BAM via HTTP range
# requests (`view -M -L <bed> -X <remote_bam> <local_bai>`), exactly as scripts/fetch_giab_hg002.py
# does for its panel BAM. The only full download is the ~9.4 MB BAM index per sample. The panel slice
# is then collate+fastq'd into properly-paired R1/R2 (singletons dropped) — the shape the driver's
# strict FASTQ preflight (equal counts, matching ids) requires.
#
# Prereqs: the genomics toolchain (samtools >= 1.10 with libcurl) on PATH — e.g. the hackathon
# conda env. Network access to the NIST GIAB FTP.
#
#   scripts/fetch_panel_fastq.sh                 # fetch HG003 + HG004 (HG002 usually already present)
#   scripts/fetch_panel_fastq.sh HG002 HG003 HG004
set -uo pipefail

SAM=${SAMTOOLS:-samtools}
REPO=$(cd "$(dirname "$0")/.." && pwd)
BED=$REPO/scripts/panel_regions.example.bed
BASE=https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/AshkenazimTrio
OUT=$REPO/data/real-giab
FQ=$OUT/fastq
mkdir -p "$FQ"

# The GIAB FTP sub-directory for each trio member (son / father / mother).
dir_for () {
  case "$1" in
    HG002) echo "HG002_NA24385_son" ;;
    HG003) echo "HG003_NA24149_father" ;;
    HG004) echo "HG004_NA24143_mother" ;;
    *) echo "" ;;
  esac
}

fetch_one () {
  local id="$1" dir
  dir=$(dir_for "$id")
  if [ -z "$dir" ]; then echo "$id: not an Ashkenazim-trio id (HG002/HG003/HG004) — skipping"; return 1; fi
  local bam="$BASE/$dir/NIST_Illumina_2x250bps/novoalign_bams/${id}.GRCh38.2x250.bam"
  local bai="$OUT/${id}.GRCh38.2x250.bam.bai"
  local panel="$OUT/${id}.GRCh38.panel.bam"
  echo "=== $id: downloading BAM index (~9.4 MB; the ~120 GB BAM is NEVER downloaded) ==="
  curl -fsS --max-time 180 -o "$bai" "$bam.bai" || { echo "$id: index download FAILED"; return 1; }
  echo "=== $id: streaming panel slice from the remote BAM (range requests only) ==="
  "$SAM" view -b -M -L "$BED" -X -o "$panel" "$bam" "$bai" || { echo "$id: slice FAILED"; return 1; }
  "$SAM" index "$panel"
  echo "=== $id: collate + fastq -> properly-paired R1/R2 (singletons dropped) ==="
  "$SAM" collate -u -O "$panel" "$OUT/tmp.collate.$id" \
    | "$SAM" fastq -1 "$FQ/${id}.R1.fastq.gz" -2 "$FQ/${id}.R2.fastq.gz" \
                   -s "$FQ/${id}.singletons.fastq.gz" -0 /dev/null -n - \
    || { echo "$id: fastq conversion FAILED"; return 1; }
  local r1 r2
  r1=$(($(zcat < "$FQ/${id}.R1.fastq.gz" | wc -l) / 4))
  r2=$(($(zcat < "$FQ/${id}.R2.fastq.gz" | wc -l) / 4))
  echo "=== $id DONE: R1=$r1 R2=$r2 read pairs (must be equal) ==="
}

SAMPLES=("$@")
if [ ${#SAMPLES[@]} -eq 0 ]; then SAMPLES=(HG003 HG004); fi
for s in "${SAMPLES[@]}"; do fetch_one "$s"; echo; done
echo "ALL DONE — reads under $FQ are git-ignored; never commit them."
