# Output Contract — bulkchip-motif-enrichment

> Scaffold: intended outputs once the tool-backed body is implemented.

## Output Structure

```
<output>/
├── README.md
├── report.md
├── result.json                        # chained from upstream
├── motif_enrichment_summary.csv       # top known motifs per subset
├── <subset>/                          # one HOMER output dir per peak subset
│   ├── knownResults.txt
│   ├── knownResults.html
│   ├── homerResults.html              # de novo motifs
│   └── homerMotifs.all.motifs
└── reproducibility/
```

## File Contents

### `result.json`

```json
{
  "skill": "bulkchip-motif-enrichment",
  "version": "0.1.0",
  "steps_completed": ["...", "motif_enrichment"],
  "params": { "peak_subset": "consensus", "size": "200", "len": "8,10,12" },
  "motif_enrichment": [
    { "peak_subset": "consensus", "out_dir": "<output>/consensus",
      "known_results": "<output>/consensus/knownResults.txt",
      "denovo_results": "<output>/consensus/homerResults.html",
      "top_motifs": [ { "motif": "CTCF", "pvalue": 1e-50, "pct_targets": 0.0 } ] }
  ],
  "prev_result": "<absolute path to upstream result.json>"
}
```

### `motif_enrichment_summary.csv`

| Column | Type | Meaning |
|---|---|---|
| `peak_subset` | str | `consensus` / `<condition>` / `up` / `down` |
| `motif` | str | known-motif name (HOMER) |
| `pvalue` | float | enrichment p-value |
| `pct_targets` | float | % of target peaks with the motif |
| `pct_background` | float | % of background sequences with the motif |
