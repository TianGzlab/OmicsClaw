# Output Contract — bulkchip-preprocessing

> Status: implemented.

## Output Structure

All outputs land directly under `--output` (OmicsClaw per-skill layout).

```
<output>/
├── README.md                          # orientation note
├── report.md                          # markdown summary
├── result.json                        # structured envelope (Step 1)
├── fastq_trimmed/
│   ├── <sample>_R1_trimmed.fastq.gz   # + _R2 for paired-end
│   └── trimmed_summary.csv            # per-sample reads in/out, % passing, tool
├── fastqc/                            # FastQC HTML/zip (unless --no-fastqc)
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## File Contents

### `result.json`

```json
{
  "skill": "bulkchip-preprocessing",
  "version": "0.1.0",
  "steps_completed": ["preprocessing"],
  "params": { "tool": "fastp", "genome": "hg38", "quality": 20, "min_length": 20 },
  "sample_sheet": {
    "layout": "paired-end",
    "genome": "hg38",
    "conditions": ["..."],
    "is_replicated": true,
    "control_map": { "<chip_sample>": "<control_sample>" },
    "samples": [
      { "name": "...", "condition": "...", "replicate": 1, "r1": "...", "r2": "...",
        "is_control": false, "control": "<control_sample>", "antibody": "CTCF",
        "peak_mode": "narrow" }
    ]
  },
  "preprocessing": [
    { "sample": "...", "tool": "fastp", "r1_trimmed": "...", "r2_trimmed": "...",
      "stats": { "reads_in": 0, "reads_out": 0, "pct_passing": 0.0 } }
  ]
}
```

### `fastq_trimmed/trimmed_summary.csv`

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name (ChIP or control) |
| `tool` | str | `fastp` or `trim_galore` |
| `reads_in` | int | raw read/pair count |
| `reads_out` | int | post-trim read/pair count |
| `pct_passing` | float | `reads_out / reads_in` |
| `is_control` | bool | True for input/IgG samples |
