---
name: bulkatac-DA
description: Load when running differential accessibility analysis on bulk ATAC-seq consensus peak counts via pyDESeq2 — two-condition contrast, volcano plot, and IGV-ready BED tracks of up/down peaks. Skip for scATAC (use scatac-de), bulk RNA (use bulkrna-de), or before peaks are called (run bulkatac-peak-calling first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- differential-accessibility
- pydeseq2
- deseq2
- volcano
- contrast
- bed-tracks
requires:
- pandas
- numpy
---

## When to use

The user has a consensus peak count matrix from `bulkatac-peak-calling` (`peak_counts.txt` plus a sample sheet with ≥ 2 conditions) and wants pyDESeq2-driven differential accessibility for one two-group contrast: up / down peak counts at user-set padj and log2FC thresholds, a volcano plot, and per-peak BED tracks colour-coded for direct loading into IGV / WashU / UCSC. Skip for scATAC (`scatac-de`), bulk RNA (`bulkrna-de`), or to start from BAMs / FASTQs — run the preprocessing → mapping → peak-calling chain first.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/peak_calling/result.json` from `bulkatac-peak-calling` | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| Count matrix | featureCounts TSV pointed to by `consensus.count_matrix` in the upstream JSON | Auto-resolved from Step 3 |
| Annotation TSV | `<step3>/annotation/qvalue<q>/annotated_peaks.tsv` (joins gene name + feature category into DA results) | Auto-resolved; missing → results emit without annotation columns + a warning |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Contrast name, n_tested / n_up / n_down, thresholds, IGV browser-loading instructions |
| Result envelope | `<output>/result.json` | `da` block with contrast + counts + BED + volcano paths |
| Full results | `<output>/DA/<contrast>/<param_tag>/da_results_<contrast>.tsv` | Per-peak TSV — baseMean, log2FoldChange, lfcSE, stat, pvalue, padj, plus annotation columns when available |
| Summary | `<output>/DA/<contrast>/<param_tag>/da_summary_<contrast>.csv` | One-row summary (n_tested, n_up, n_down, thresholds) |
| Up-peak BED | `<output>/DA/<contrast>/<param_tag>/da_peaks_up_<contrast>.bed` | Track header + RGB red (255,0,0) — direct IGV / UCSC load |
| Down-peak BED | `<output>/DA/<contrast>/<param_tag>/da_peaks_down_<contrast>.bed` | RGB blue (0,0,255) |
| All-DA BED | `<output>/DA/<contrast>/<param_tag>/da_peaks_all_<contrast>.bed` | Colour-coded by direction |
| Volcano | `<output>/plots/<contrast>/<param_tag>/volcano_<contrast>.{pdf,png,tsv}` | PDF + PNG + underlying TSV (point data) |
| Reproducibility | `<output>/reproducibility/commands.sh` | Re-run command |

`<contrast>` = `<treat>_vs_<control>`; `<param_tag>` = `q<peak_qvalue>_padj<padj>_lfc<lfc>`.

## Flow

1. Locate the upstream Step-3 `result.json`: use `--prev-result` if passed, otherwise the sibling `<project>/peak_calling/result.json` (`--wd`'s parent); hard-fail if neither resolves (`bulkatac-DA.py:297-306`).
2. Reconstruct the count matrix path, sample names, condition labels, and the Step-3 `qvalue` from the upstream envelope (`bulkatac-DA.py:315-332`).
3. Locate the Step-3 annotation TSV at `annotation/qvalue<q>/annotated_peaks.tsv`; fall back to a glob under `annotation/`; emit a warning and continue without annotation if not found (`bulkatac-DA.py:96-110`).
4. Resolve the contrast: use `--treat`/`--control` explicitly, or auto-pick the two alphabetically-first unique conditions; hard-fail if fewer than two conditions exist (`bulkatac-DA.py:329-342`).
5. Build the `<contrast>` and `<param_tag>` directory tokens (`bulkatac-DA.py:344-345`).
6. Run pyDESeq2 via `_lib.DA.run_differential_accessibility` — emits the results TSV + summary CSV + three colour-coded BED tracks (`bulkatac-DA.py:355-363`).
7. Render the volcano via `_lib.DA.plot_volcano` (PDF + PNG + underlying TSV) (`bulkatac-DA.py:365-368`).
8. Write `report.md`, `result.json`, `reproducibility/`, `README.md`, then stdout summary (`bulkatac-DA.py:370-394`).

## Gotchas

- **No `--demo` flag.** `bulkatac-DA.py:293` jumps straight to argparse + Step-3 loading. Smoke-test by running the full Step 1 → 2 → 3 chain (`bulkatac-preprocessing --demo`, then `bulkatac-mapping`, then `bulkatac-peak-calling`) and passing the same `--wd`.
- **Chains via `--prev-result` (also accepts `--input` as an alias).** `bulkatac-DA.py:239-243` reads `peak_calling/result.json`. `--wd` is aliased to `--output` (`bulkatac-DA.py:244`) so the OmicsClaw runner's `--output <path>` + `--input <result.json>` injection works; if only `--output` is passed, sibling-detection finds `peak_calling/result.json` next to it (`<output>/../peak_calling/result.json`).
- **Auto-contrast picks alphabetically.** When `--treat` / `--control` are both omitted, `bulkatac-DA.py:340-342` sorts the unique condition labels and assigns `control = first`, `treat = second`. For three+ conditions only the first two are tested. Pass both flags explicitly to control which contrast runs.
- **DA results nest under a `DA/` subdir of `--output`.** `bulkatac-DA.py:309` uses `--output` as the skill root; `:357` then writes the contrast tree to `<output>/DA/<contrast>/<param_tag>/` and the volcano to `<output>/plots/<contrast>/<param_tag>/`. The `DA/` here is the contrast-results folder, not a step namespace — join the full path rather than expecting `<output>/<contrast>/`.
- **Re-running with different thresholds writes parallel trees, not overwrites.** `bulkatac-DA.py:345` bakes `q<qvalue>_padj<padj>_lfc<lfc>` into the directory name. Repeated runs with different `--padj` / `--lfc` accumulate alongside each other; clean up manually if disk pressure is a concern.
- **Annotation join is silent on miss.** `bulkatac-DA.py:96-110` warns to the logger and sets `annotation_tsv = None`; the results TSV is still emitted but its `gene_name` / `feature_category` columns are missing. Inspect `result.json["da"]["annotation_source"]` to confirm whether annotation was joined.
- **Hard-fails with fewer than two conditions.** `bulkatac-DA.py:335-339` exits via `parser.error` if `len(set(conditions)) < 2`. If your sample sheet only labels one condition (e.g. a pilot run), DA is not applicable — add a comparator first or skip this skill.

## Key CLI

End-to-end run after `bulkatac-peak-calling` (auto-detects Step-3 result + contrast):

```bash
python skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py \
    --wd ./atac_run
```

Explicit contrast + stricter thresholds:

```bash
python skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py \
    --wd ./atac_run \
    --treat T15 --control T0 \
    --padj 0.01 --lfc 1.5
```

Skip annotation join (faster, no GTF dependency):

```bash
python skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py \
    --prev-result /tmp/atac/peak_calling/result.json \
    --wd /tmp/atac \
    --treat T15 --control T0 \
    --skip-annotation
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — pyDESeq2 GLM details (negative binomial + Wald test), padj method (Benjamini–Hochberg), BED track colouring scheme, contrast naming convention.
- `references/output_contract.md` — full output tree, `da_results_<contrast>.tsv` column schema, `da_summary_<contrast>.csv` schema, `result.json["da"]` keys.
- Adjacent skills:
  - Upstream — `bulkatac-peak-calling` (must run first to produce `peak_calling/result.json` + `consensus_peaks.saf` + `peak_counts.txt`).
  - Parallel — `bulkrna-de` (same DESeq2 engine, gene-level for bulk RNA); `scatac-de` (single-cell ATAC; sparse-aware methods).
  - Downstream — `bulkatac-motif-enrichment` (HOMER motif enrichment in up / down peak sets).
