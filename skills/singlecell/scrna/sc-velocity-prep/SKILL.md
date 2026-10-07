---
name: sc-velocity-prep
description: Load when generating spliced / unspliced layers from Cell Ranger BAM, FASTQ, STARsolo output,
  or velocyto loom — the prerequisite for sc-velocity. Skip when AnnData already has spliced+unspliced
  layers (use sc-velocity); any non-velocity preprocessing (use sc-preprocessing).
trigger: RNA velocity prep, prepare spliced unspliced layers, velocyto, starsolo velocyto, velocity-ready AnnData
tags:
- singlecell
- scrna
- velocity-prep
- velocyto
- starsolo
- spliced-unspliced
---

# sc-velocity-prep

## Use from a step

This is CLI_ONLY: it runs external preparation tools or imports their files.

```python
from skills._sdk.notebook import run_cli

run_cli("sc-velocity-prep", "--input", "data/velocity.loom",
        "--base-h5ad", "data/clustered.h5ad",
        inputs=["data/velocity.loom", "data/clustered.h5ad"])
```

The demo splits PBMC3k counts into fixed 82% spliced, 14% unspliced and
4% ambiguous layers. It checks packaging, not velocity biology or external
tool installation. There is no `_api.py` for this skill.

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

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.loom`, `.fastq`, `.fq`
- FASTQ structure: valid first record; `paired` layout
- Directory layouts (any): `paired-fastq`, `cellranger-output`, `starsolo-velocity`

**Outputs**

- `tables/top_velocity_genes.csv`
- `tables/velocity_layer_summary.csv`
- `figures/velocity_gene_balance.png`
- `figures/velocity_layer_fraction.png`
- `figures/velocity_layer_summary.png`
- `figures/velocity_top_genes_stacked.png`
- `processed.h5ad`
- `velocity_input.h5ad`
- `figures/manifest.json`, `figure_data/manifest.json`, plot-data CSV files
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`
- Conditional backend artifacts under `artifacts/`; imported loom/STARsolo inputs do not create new BAM files.
- `report.md`
- `result.json`
- Processed AnnData — `spliced`, `unspliced` layers; `ambiguous` only when supplied by the source

## Flow

1. Resolve `--input` (Cell Ranger dir / STARsolo dir / FASTQ / `.loom`).
2. For `velocyto`: locate BAM + barcodes, validate `--gtf` (or auto-pick from `resources/singlecell/references/gtf/`), run `velocyto run`, load `.loom`.
3. For `starsolo`: detect existing STARsolo Velocyto output and load directly, OR re-run STARsolo Velocyto with `--reference` + `--chemistry` + auto-detected `--whitelist`.
4. Optionally merge layers into `--base-h5ad`.
5. Compute layer totals (`tables/velocity_layer_summary.csv`) and top-gene balance.
6. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **BAM-backed velocyto needs a GTF.** `sc_velocity_prep.py` raises `ValueError("BAM-backed velocyto preparation requires a GTF file. Pass `--gtf /abs/path/to/genes.gtf`, or keep one under `resources/singlecell/references/gtf/`. ...")`. Auto-detection only fires if a project-local GTF lives at the recommended path.
- **FASTQ-backed STARsolo needs a STAR index AND explicit chemistry.** `sc_velocity_prep.py` raises `ValueError("FASTQ-backed STARsolo velocity preparation requires a STAR genome directory. ...")` if `--reference` is missing and nothing's at `resources/singlecell/references/starsolo/`. `sc_velocity_prep.py` raises `ValueError("FASTQ-backed STARsolo velocity preparation requires an explicit `--chemistry`.")` when `--chemistry auto` is left as the default — STARsolo cannot infer 10x v2 vs v3 vs v4 from FASTQ alone.
- **STARsolo whitelist is auto-guessed; missing → hard fail.** `sc_velocity_prep.py` raises `ValueError("Could not infer a compatible STARsolo whitelist. Pass `--whitelist /abs/path/to/3M-february-2018.txt`, or keep the whitelist under `resources/singlecell/references/whitelists/`. ...")`. The guesser uses the reference path + chemistry; a non-standard reference layout breaks it.
- **STARsolo Velocyto matrix loader has a fallback for index-name quirks.** `sc_velocity_prep.py` is documented as "with a local fallback for index-name quirks"; `_load_starsolo_velocyto_dir_safe` raises `FileNotFoundError(f"Could not locate STARsolo Velocyto matrices under: {path}")` when nothing matches even with the fallback. Common when STARsolo finished partial / was killed mid-run.
- **`--input` mandatory unless `--demo` (parser.error, exit code 2).** `sc_velocity_prep.py` calls `parser.error("--input required when not using --demo")`. Once provided, `main` raises `FileNotFoundError(f"Input path not found: {input_path}")` for a missing path.
- **`--method` choices are exactly `velocyto` / `starsolo`.** `sc_velocity_prep.py` declares the choices via argparse; `kb-python` is mentioned in upstream-prep docstrings but is not a valid `--method` value here. Use the dedicated kb-python tooling outside OmicsClaw if you need that path.
- `sc_velocity_prep.py:main` defaults to eight threads. Reference directories named in error messages are suggestions, not shipped assets. Verify the `velocyto` command can import before a long BAM run; migration preflight found `undefined symbol: __log10_finite` in the installed copy despite its presence on PATH.
- `sc_velocity_prep.py:main` writes a new `.raw` snapshot and records `.X` as raw counts even when `--base-h5ad` contains normalized `.X`. `_lib/upstream.py:merge_velocity_layers` also replaces `layers["counts"]` with the velocity input's counts (the sum of its available splicing layers for imported data). Inspect this existing contract mismatch before treating the merged object's `.X` or `.raw` as counts; the spliced/unspliced layers remain separate.

## Key CLI

```bash
# Demo (proportional PBMC3k layers; no velocyto / STARsolo)
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py --demo --output /tmp/sc_velo_prep_demo

# velocyto from a Cell Ranger run (BAM-backed)
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py \
  --input /data/cellranger_run/ --output results/ \
  --method velocyto --gtf /refs/Homo_sapiens.GRCh38.gtf

# Load existing STARsolo Velocyto output directly
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py \
  --input /data/starsolo_run/ --output results/ \
  --method starsolo

# Re-run STARsolo from FASTQ (chemistry must be explicit)
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py \
  --input /data/fastqs/ --output results/ \
  --method starsolo --reference /refs/star_index --chemistry 10xv3

# Merge velocity layers into an existing processed AnnData
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py \
  --input /data/cellranger_run/ --output results/ \
  --method velocyto --gtf /refs/Homo_sapiens.GRCh38.gtf \
  --base-h5ad /path/to/clustered.h5ad
```

## See also

- `references/parameters.md` — every CLI flag, per-backend tunables
- `references/methodology.md` — when velocyto vs STARsolo wins; whitelist conventions
- `references/output_contract.md` — `layers["spliced"]` / `layers["unspliced"]` / `layers["ambiguous"]` schema
- Adjacent skills: `sc-count` / `sc-multi-count` (upstream — produce the Cell Ranger / STARsolo output this skill consumes), `sc-velocity` (downstream — consumes `layers["spliced"]` + `layers["unspliced"]`), `sc-clustering` (parallel — pass clustered output as `--base-h5ad` to keep clusters when adding velocity layers)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
