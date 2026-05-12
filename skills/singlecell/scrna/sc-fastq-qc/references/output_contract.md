## Output Structure

```
output_directory/
├── report.md
├── result.json
├── 3M-february-2018.txt
├── 737K-august-2016.txt
├── Aligned.sortedByCoord.out.bam
├── commands.sh
├── manifest.json
├── multiqc_report.html
├── possorted_genome_bam.bam
├── web_summary.html
├── tables/
│   ├── Summary.csv
│   ├── barcodes.tsv
│   ├── fastq_per_base_quality.csv
│   ├── fastq_per_file_summary.csv
│   ├── fastq_per_sample_summary.csv
│   ├── features.tsv
│   ├── genes.tsv
│   └── metrics_summary.csv
└── figures/
    ├── fastq_file_quality.png
    ├── fastq_q30_summary.png
    ├── fastq_read_structure.png
    └── per_base_quality.png
```

## File contents

- `tables/Summary.csv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/barcodes.tsv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/fastq_per_base_quality.csv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/fastq_per_file_summary.csv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/fastq_per_sample_summary.csv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/features.tsv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/genes.tsv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `tables/metrics_summary.csv` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `figures/fastq_file_quality.png` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `figures/fastq_q30_summary.png` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `figures/fastq_read_structure.png` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `figures/per_base_quality.png` — written by `sc_fastq_qc.py` (or its imported `_lib/` helpers).
- `3M-february-2018.txt` — written by `sc_fastq_qc.py`.
- `737K-august-2016.txt` — written by `sc_fastq_qc.py`.
- `Aligned.sortedByCoord.out.bam` — written by `sc_fastq_qc.py`.
- `commands.sh` — written by `sc_fastq_qc.py`.
- `manifest.json` — written by `sc_fastq_qc.py`.
- `multiqc_report.html` — written by `sc_fastq_qc.py`.
- `possorted_genome_bam.bam` — written by `sc_fastq_qc.py`.
- `web_summary.html` — written by `sc_fastq_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_fastq_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
