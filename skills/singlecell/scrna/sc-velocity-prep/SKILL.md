---
name: sc-velocity-prep
description: Load when generating spliced / unspliced layers from Cell Ranger BAM, FASTQ, STARsolo output, or velocyto loom — the prerequisite for sc-velocity. Skip when AnnData already has spliced+unspliced layers (go straight to sc-velocity) or for any non-velocity preprocessing (use sc-preprocessing).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- velocity-prep
- velocyto
- starsolo
- spliced-unspliced
- kb-python
requires:
- anndata
- numpy
- pandas
---

# sc-velocity-prep

## When to use

The user has raw Cell Ranger output (BAM + barcodes), STARsolo output,
or paired FASTQs and needs an AnnData with `layers["spliced"]` /
`layers["unspliced"]` (and optional `layers["ambiguous"]`) before
running `sc-velocity`. Two backends:

- `velocyto` (default) — runs `velocyto run` against a Cell Ranger BAM
  using a GTF. Produces a `.loom` and reads it back into AnnData.
- `starsolo` — re-runs alignment from FASTQ via STARsolo with the
  Velocyto solo subworkflow, or loads existing STARsolo Velocyto
  output directly when detected.

`--base-h5ad` lets you merge the velocity layers into an
already-processed AnnData (preserves `obs` / `obsm` / clustering).

For velocity estimation itself use `sc-velocity`. For non-velocity
scRNA preprocessing use `sc-preprocessing`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Cell Ranger run dir / STARsolo dir / FASTQ dir / `.loom` | path | yes (unless `--demo`) |
| GTF | `.gtf` (`--gtf`) | required for BAM-backed velocyto |
| STAR index | dir (`--reference`) | required for FASTQ-backed STARsolo |
| Chemistry | `10xv2` / `10xv3` / `10xv4` (`--chemistry`) | required for FASTQ STARsolo |
| Optional base AnnData | `.h5ad` (`--base-h5ad`) | merge layers into existing object |

| Output | Path | Notes |
|---|---|---|
| Velocity-ready AnnData | `processed.h5ad` | adds `layers["spliced"]`, `layers["unspliced"]`, `layers["ambiguous"]` |
| Layer totals | `tables/velocity_layer_summary.csv` | molecules per layer |
| Top genes | `tables/top_velocity_genes.csv` | highest-abundance velocity genes |
| Figures | `figures/velocity_layer_summary.png`, `figures/velocity_layer_fraction.png`, `figures/velocity_gene_balance.png`, `figures/velocity_top_genes_stacked.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Resolve `--input` (Cell Ranger dir / STARsolo dir / FASTQ / `.loom`).
2. For `velocyto`: locate BAM + barcodes, validate `--gtf` (or auto-pick from `resources/singlecell/references/gtf/`), run `velocyto run`, load `.loom`.
3. For `starsolo`: detect existing STARsolo Velocyto output and load directly, OR re-run STARsolo Velocyto with `--reference` + `--chemistry` + auto-detected `--whitelist`.
4. Optionally merge layers into `--base-h5ad`.
5. Compute layer totals (`tables/velocity_layer_summary.csv`) and top-gene balance.
6. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **BAM-backed velocyto needs a GTF.** `sc_velocity_prep.py:397` raises `ValueError("BAM-backed velocyto preparation requires a GTF file. Pass `--gtf /abs/path/to/genes.gtf`, or keep one under `resources/singlecell/references/gtf/`. ...")`. Auto-detection only fires if a project-local GTF lives at the recommended path.
- **FASTQ-backed STARsolo needs a STAR index AND explicit chemistry.** `sc_velocity_prep.py:437` raises `ValueError("FASTQ-backed STARsolo velocity preparation requires a STAR genome directory. ...")` if `--reference` is missing and nothing's at `resources/singlecell/references/starsolo/`. `sc_velocity_prep.py:444` raises `ValueError("FASTQ-backed STARsolo velocity preparation requires an explicit `--chemistry`.")` when `--chemistry auto` is left as the default — STARsolo cannot infer 10x v2 vs v3 vs v4 from FASTQ alone.
- **STARsolo whitelist is auto-guessed; missing → hard fail.** `sc_velocity_prep.py:458` raises `ValueError("Could not infer a compatible STARsolo whitelist. Pass `--whitelist /abs/path/to/3M-february-2018.txt`, or keep the whitelist under `resources/singlecell/references/whitelists/`. ...")`. The guesser uses the reference path + chemistry; a non-standard reference layout breaks it.
- **STARsolo Velocyto matrix loader has a fallback for index-name quirks.** `sc_velocity_prep.py:100` is documented as "with a local fallback for index-name quirks"; `:112` raises `FileNotFoundError(f"Could not locate STARsolo Velocyto matrices under: {path}")` when nothing matches even with the fallback. Common when STARsolo finished partial / was killed mid-run.
- **`--input` mandatory unless `--demo` (parser.error, exit code 2).** `sc_velocity_prep.py:373` calls `parser.error("--input required when not using --demo")`. Once provided, `:376` raises `FileNotFoundError(f"Input path not found: {input_path}")` for a missing path.
- **`--method` choices are exactly `velocyto` / `starsolo`.** `sc_velocity_prep.py:346` declares the choices via argparse; `kb-python` is mentioned in upstream-prep docstrings but is not a valid `--method` value here. Use the dedicated kb-python tooling outside OmicsClaw if you need that path.

## Key CLI

```bash
# Demo (synthetic loom; does NOT exercise velocyto / STARsolo)
python omicsclaw.py run sc-velocity-prep --demo --output /tmp/sc_velo_prep_demo

# velocyto from a Cell Ranger run (BAM-backed)
python omicsclaw.py run sc-velocity-prep \
  --input /data/cellranger_run/ --output results/ \
  --method velocyto --gtf /refs/Homo_sapiens.GRCh38.gtf

# Load existing STARsolo Velocyto output directly
python omicsclaw.py run sc-velocity-prep \
  --input /data/starsolo_run/ --output results/ \
  --method starsolo

# Re-run STARsolo from FASTQ (chemistry must be explicit)
python omicsclaw.py run sc-velocity-prep \
  --input /data/fastqs/ --output results/ \
  --method starsolo --reference /refs/star_index --chemistry 10xv3

# Merge velocity layers into an existing processed AnnData
python omicsclaw.py run sc-velocity-prep \
  --input /data/cellranger_run/ --output results/ \
  --method velocyto --gtf /refs/Homo_sapiens.GRCh38.gtf \
  --base-h5ad /path/to/clustered.h5ad
```

## See also

- `references/parameters.md` — every CLI flag, per-backend tunables
- `references/methodology.md` — when velocyto vs STARsolo wins; whitelist conventions
- `references/output_contract.md` — `layers["spliced"]` / `layers["unspliced"]` / `layers["ambiguous"]` schema
- Adjacent skills: `sc-count` / `sc-multi-count` (upstream — produce the Cell Ranger / STARsolo output this skill consumes), `sc-velocity` (downstream — consumes `layers["spliced"]` + `layers["unspliced"]`), `sc-clustering` (parallel — pass clustered output as `--base-h5ad` to keep clusters when adding velocity layers)
