# Output Contract — bulkchip-DA

> Scaffold: intended outputs once the tool-backed body is implemented.

## Output Structure

```
<output>/
├── README.md
├── report.md
├── result.json                        # chained from Step 3
├── differential_binding.csv           # peak, baseMean, log2FC, lfcSE, pvalue, padj
├── volcano.png
├── up_peaks.bed                        # gained peaks (log2FC > +lfc, padj < cutoff)
├── down_peaks.bed                      # lost peaks (log2FC < -lfc, padj < cutoff)
└── reproducibility/
```

## File Contents

### `result.json`

```json
{
  "skill": "bulkchip-DA",
  "version": "0.1.0",
  "steps_completed": ["...", "differential_binding"],
  "params": { "treat": "treated", "control": "control", "padj": 0.05, "lfc": 1.0 },
  "differential_binding": {
    "contrast": "treated_vs_control",
    "results_csv": "<output>/differential_binding.csv",
    "volcano_png": "<output>/volcano.png",
    "up_bed": "<output>/up_peaks.bed",
    "down_bed": "<output>/down_peaks.bed",
    "n_up": 0,
    "n_down": 0
  },
  "consensus": { /* carried forward */ },
  "prev_result": "<absolute path to Step 3 result.json>"
}
```

### `differential_binding.csv`

| Column | Type | Meaning |
|---|---|---|
| `peak` | str | consensus peak id (`peak_<N>`) |
| `baseMean` | float | mean normalized count across samples |
| `log2FoldChange` | float | shrunk log2 fold-change (treat / control) |
| `lfcSE` | float | standard error of the LFC |
| `pvalue` | float | Wald test p-value |
| `padj` | float | BH-adjusted p-value |
