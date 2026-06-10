---
doc_id: bulkatac-motif-enrichment-guardrails
title: Bulk ATAC Motif Enrichment Guardrails
doc_type: knowhow
critical_rule: MUST verify --prev-result points at a bulkatac-DA result.json (not a peak-calling one), explain the per-peak-set background strategy and HOMER parameters before running, and never claim TF binding occupancy — enrichment only surfaces candidate motifs
domains: [epigenomics]
related_skills: [bulkatac-motif-enrichment]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ATAC motif enrichment, HOMER findMotifsGenome, de novo motif discovery, transcription factor motifs, GC-matched background, 基序富集]
priority: 1.0
---

# Bulk ATAC Motif Enrichment Guardrails

- **Inspect first**: confirm `findMotifsGenome.pl` (HOMER) is on `PATH` and that `--prev-result` (alias `--input`) is a `bulkatac-DA` result.json — the run hard-fails on `prev_skill != "bulkatac-DA"` (or a missing `da` key). There is no `--demo` flag.
- **Do not overclaim scope**: this skill reports motif over-representation + de novo discovery only — it does NOT confirm in-vivo TF binding / occupancy (`bulkatac-footprinting`) and does not integrate TF expression.
- **Explain the run before execution**: state the resolved `--genome` / `--genome-fasta`, `--size` (int window in bp or the literal `given`), `--threads`, `--denovo-length`, and `--n-motifs`; note `--mask` is a no-op default-on flag — `--no-mask` is the real toggle (use it for non-mammalian genomes).
- **Use wrapper-correct language**: background strategy differs per peak set — `all_peaks` uses HOMER's GC-matched genomic background ("enriched in open chromatin?"), while `da_up`/`da_down` use the consensus peaks as background (`-bg -chopify`, "what drives condition-specific accessibility?"); HOMER per-genome data must be installed separately unless `--genome-fasta` is passed.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `top_motif_summary.tsv`, per-peak-set dirs `{all_peaks,da_up,da_down}/` (HOMER-native `knownResults.txt/.html`, `homerResults.html`, `homerMotifs.all.motifs`), and `plots/`.
- **Interpret outputs correctly**: DA up/down peak sets are silently skipped when their BEDs are absent — check the length of `result.json["motif_enrichment"]`; an empty peak set yields a `NOTE_no_peaks.txt` sentinel rather than a HOMER failure.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkatac-motif-enrichment.md`.
