---
name: consensus-domains
description: Load when you want a verified multi-method consensus over spatial tissue domains on a preprocessed
  spatial AnnData — fanning out N domain methods, ranking base clusterings, and emitting a typed consensus
  with cross-method disagreement. Skip when one method suffices (use spatial-domains); the data is single-cell
  (use sc-consensus-clustering).
trigger: consensus domains, consensus tissue regions, multi-method spatial domains, robust spatial clustering, expert in the loop spatial, bc ranking, saccelerator-like consensus
tags:
- spatial
- consensus
- typed-consensus
- expert-in-the-loop
- saccelerator
- bc-ranking
- kmode
- lca
- weighted
---

# consensus-domains

## When to use

The user has a preprocessed spatial AnnData (typically already QC'd via
`spatial-preprocess`) and wants a **more trustworthy** tissue-domain
assignment than any single method can produce — because the user knows
single-method results disagree on cancer / non-standard tissues, or
because the analysis is going to drive a downstream decision (cell-type
deconvolution, region-specific DE, paper figure).

This skill fans out `spatial-domains` over N method choices, computes a
typed statistical consensus, and surfaces the **cross-method
disagreement** explicitly. It does NOT replace `spatial-domains`; it
wraps it.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `consensus_labels.tsv`
- `member_scores.csv`
- `member_intrinsic_panel.csv`
- `cross_method_nmi.csv`
- `plan.json`
- `report.md`
- `result.json`

## Flow

1. **Plan** — `runtime/consensus/plan.propose_members` reads
   `spatial-domains`' documented parameter defaults,
   queries the evaluation-chair LLM (or falls back deterministically),
   produces N PlannedMember entries.
2. **Fan out** — `runtime/consensus/team.run_team` invokes
   `omicsclaw.skill.runner.run_skill("spatial-domains", ...)` per
   member with `max_parallel = min(N, cpu_count//2, 4)` and a 600 s
   per-member timeout. `cancel_event` is propagated through.
3. **Score** — `runtime/consensus/scoring.score_all_members` ranks
   survivors by composite `alpha * cross_NMI + beta * mean_local_purity`
   with the `max_class_frac > 0.8` hard filter.
4. **BC pick** — on the CLI surface in interactive mode, prompt the
   user with the top-K-by-score default; on Desktop/Channel surfaces
   (or `--non-interactive`), accept the default.
5. **Consensus** — invoke the chosen operator
   (`kmode` / `weighted` / `lca`) on the selected base clusterings.
6. **Report** — write `report.md` starting with the mandatory
   banner; persist `plan.json` for audit; ready for graph-memory
   storage under `analysis://typed/<run_id>`.

## Gotchas

- **A path is allowed to fail loudly.** If fewer than 2 members survive
  the fan-out, this skill raises `InsufficientSurvivorsError` and does
  NOT silently downgrade to narrative consensus. Re-run with
  `--members` adjusted.
- **Banner is non-configurable.** The `[A: Verified consensus]` header
  is enforced by `runtime/consensus/dispatch.output_banner`. Do not
  edit `report.md` to strip it before distribution.
- **Member intrinsic quality is a multi-metric panel.** Spatial-domain
  members are scored on a normalized panel of three unsupervised metrics —
  `chaos` (1-hop coherence), `pas` (anomaly rate), `mlami` (multi-scale
  spatial-graph AMI) — combined into one `[0,1]` intrinsic for the β term of the
  BC composite score. The per-member breakdown is written to
  `member_intrinsic_panel.csv`. Pass `--no-spatial-panel` to score on the single
  `mean_local_purity` signal instead.
- **`--n-clusters` is reserved — accepted but not consumed.** The operator
  returns however many clusters the math yields (bounded at the max member k);
  passing `--n-clusters` changes nothing.
- **LCA requires R + diceR.** When unavailable, the skill prints an
  installation hint and exits non-zero rather than silently switching
  operators. Pass `--operator kmode` to bypass.
- **`requires_preprocessed: true`** — the underlying spatial-domains
  members expect `obsm["X_pca"]` and `obsm["spatial"]` populated. Run
  `spatial-preprocess` first.

## Key CLI

```bash
# Minimal interactive run (CLI surface) — LLM picks 5, you confirm BCs
python skills/spatial/consensus-domains/consensus_domains.py --input preprocessed.h5ad --output out/

# Non-interactive (server / scripted)
python skills/spatial/consensus-domains/consensus_domains.py --input preprocessed.h5ad --output out/ \
  --non-interactive

# Explicit members + weighted operator
python skills/spatial/consensus-domains/consensus_domains.py --input preprocessed.h5ad --output out/ \
  --members banksy,graphst,sedr,leiden,spagcn \
  --operator weighted

# SACCELERATOR-style benchmark (run ALL eligible methods)
python skills/spatial/consensus-domains/consensus_domains.py --input preprocessed.h5ad --output out/ --all
```

## See also

- `references/methodology.md` — the consensus scoring + operator rationale
- `references/output_contract.md` — `consensus_labels.tsv` / `member_scores.csv` / `plan.json` schema
- `references/parameters.md` — every CLI flag, per-method tunables
- Adjacent skills: `spatial-preprocess` (upstream — produces the input), `spatial-domains` (the per-member method this wraps), `consensus-interpret` (downstream — narrates the consensus result), `sc-consensus-clustering` (parallel — the single-cell analogue)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `numpy`, `pandas`, `PyYAML`, `scanpy`, `scikit-learn`, `scipy`
