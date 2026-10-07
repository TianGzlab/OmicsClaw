# Guide assignment

Read an upstream barcode/guide table; this skill does not call guides from
FASTQ. `standardize_mapping` resolves common column names. `collapse_assignments`
deduplicates guides per barcode, keeps supplied target genes or infers them
from the guide delimiter, and marks controls using whole tokens. `NT_sg1`
matches NT; WNT3, NTRK1 and NT5E do not. Multi-guide cells are dropped by default.

`attach_assignments` returns a copy restricted to matching barcodes and known
gene-expression features, then applies the single-cell canonicalization
contract. No matching barcode raises a clear error. Statuses in retained cells
are assigned, control or multi_guide. For analysis, use sc-perturb downstream.
