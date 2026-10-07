---
name: sc-standardize-input
description: Load when an external single-cell h5ad/h5/loom/mtx needs to be canonicalised onto the OmicsClaw
  AnnData contract before downstream scRNA skills run. Skip when data already came from sc-count (already
  canonical); bulk RNA-seq (use bulkrna-qc); spatial (use spatial-preprocess).
trigger: standardize AnnData, fix scRNA input, canonicalize single-cell input, prepare AnnData, input contract
tags:
- singlecell
- scrna
- input
- standardization
- anndata
---

# sc-standardize-input

## When to use

The user has a single-cell expression file from outside OmicsClaw (a public
`.h5ad`, a 10X mtx directory, a `.loom`, etc.) and needs the canonical
AnnData contract every downstream scRNA skill assumes: raw counts in
`layers["counts"]` and `adata.raw`, harmonised feature names, and a
`uns["omicsclaw_matrix_contract"]` provenance record.  Run this once before
`sc-qc` / `sc-preprocessing` / etc.

## Use from a step

```python
standardizer = load_skill("sc-standardize-input")
adata = standardizer.standardize(read_input("external.h5ad"), species="human")
write_output(adata, "intermediate/adata_standardized.h5ad")
```

`standardize` returns a new AnnData. It does not filter, normalize or
cluster. A runnable PBMC example is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `standardize(adata, *, species: str='auto')`

Return a canonical copy with count-like X, layers['counts'] and raw.

Select counts from layers['counts'], aligned raw or X, in that order;
harmonize feature names and record the matrix and input contracts.

:param adata: AnnData with at least one count-like expression matrix.
:param species: 'auto' uses infer_species; 'human' or 'mouse' overrides it.
:returns: A new AnnData. run_info reports the selected matrix and warnings.
:raises ValueError: The species is invalid or no count-like matrix is present.

### `infer_species(adata) -> str`

Infer human or mouse from feature names, defaulting to human.

:param adata: AnnData whose feature names or gene-symbol metadata are examined.
:returns: The species hint used by standardize(species="auto").

### `run_info(adata, *, keep: bool=True) -> dict`

Read standardization diagnostics stored as JSON in adata.uns.

:param adata: The AnnData returned by standardize.
:param keep: False removes these diagnostics after reading; default True.
:returns: A dictionary, or an empty dictionary before standardize runs.

<!-- api:end -->

## Methods and parameters

`species="auto"` uses the existing gene-name heuristic; use `human` or
`mouse` when the organism is known. `infer_species` exposes that heuristic.
Counts are selected from `layers["counts"]`, aligned `raw`, then `X`.
`run_info` reports the chosen source and any warnings. This method has no
random state or optional backend.

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.h5ad`, `.h5`, `.loom`, `.csv`, `.tsv`

**Outputs**

- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `layers`: `counts`

## Flow

1. Load via the shared multi-format single-cell loader.
2. Pre-flight: validate non-empty input; auto-detect species from gene name case (UPPER → human, Title → mouse).
3. Pick the best count-like matrix among `layers["counts"]`, `adata.raw`, and `adata.X` (orchestrated by `canonicalize_singlecell_adata` in `skills/singlecell/_lib/adata_utils.py`, which calls the `matrix_looks_count_like` heuristic at `_lib/adata_utils.py`).
4. Harmonise feature names (Ensembl ↔ symbol, deduplicate).
5. Persist `uns["omicsclaw_input_contract"]` + `uns["omicsclaw_matrix_contract"]`.
6. Save `processed.h5ad`; emit `report.md` + `result.json`.

## Gotchas

- **`--r-enhanced` is accepted but produces no R plots.** `sc_standardize_input.py` declares the flag for CLI consistency; this skill is input canonicalisation, not visualisation.  Pass it freely, but expect no R Enhanced figures.
- Count-source selection uses a count-like heuristic, not file provenance.
  Check `run_info(adata)["expression_source"]` and `warnings`, or the CLI's
  `result.json["summary"]`, before downstream normalization.
- **Species auto-detect is gene-case-based.** UPPER-case symbols → human, Title-case → mouse.  Non-standard gene-name conventions (Ensembl IDs only, lowercase) silently fall through to the `auto` default.  Pass `--species human` or `--species mouse` explicitly when working with non-symbol matrices.
- **No filtering, no normalisation, no clustering.** Even if `result.json` looks complete, the output is still raw counts in canonical form — run `sc-qc` and `sc-preprocessing` next.

## Key CLI

```bash
# Demo (built-in PBMC3K)
python skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py --demo --output /tmp/sc_std_demo

# Real run with species hint
python skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py \
  --input external.h5ad --output results/ --species mouse
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — count-source heuristic, species detection logic
- `references/output_contract.md` — exact `processed.h5ad` + `result.json` shape
- Adjacent skills: `sc-count` (FASTQ → AnnData; skip standardisation when used), `sc-qc` (next step), `sc-preprocessing` (full normalise+cluster pipeline)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`
