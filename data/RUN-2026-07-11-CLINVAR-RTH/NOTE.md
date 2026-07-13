# RUN-2026-07-11-CLINVAR-RTH — contrived flag-for-review demo

`origin=contrived`. This run **demonstrates the flag-for-review gate rule (VAR-FFR-001, ADR-0018 D2)**
end-to-end. It is NOT real data and implies nothing about a real individual:

- The sample is GIAB **HG002** (a publicly-consented benchmark, not a patient).
- `variants.csv` **spikes** a single clearly-contrived candidate — a real, verbatim-cited ClinVar
  **Pathogenic** BRCA1 classification (`VCV000017661`) that HG002 does **not** actually carry. The
  spike exists only to exercise the "quote ClinVar → flag for review" path.
- `flag_for_review` is the per-run arming marker (`api/main._active_runbook`) that arms
  `FlagForReviewPolicy` with `Pathogenic,Likely_pathogenic` **for this run only** — every other run
  stays disarmed (flag-for-review is off by default in the core).
- QC is deliberately clean, so the sample's **only** escalation is the flag-for-review hold — the rule
  flags it for a qualified reviewer; bayleaf authors no pathogenicity of its own (ADR-0004).
