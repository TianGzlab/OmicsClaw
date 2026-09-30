"""consensus-interpret — LLM-grounded biological interpretation of a
verified typed consensus run (ADR 0012 γ + β).

Thin CLI wrapper. Pipeline: load typed_run -> inline DE -> marker DB ->
candidate ranking -> per-cluster annotation (LLM) -> next-step
synthesis (LLM) -> invariant enforcement -> 5 artifact writes (delegated to
``_artifacts.py``): interpreted_report.md, interpreted_assignments.json,
de_per_cluster.csv, contradiction_regions.csv, audit.json.

Reads from the typed run dir (``--input``, via ``_run_reader.py``): plan.json,
consensus_labels.tsv, member_scores.csv, cross_method_nmi.csv.

Exit codes (continuous with consensus-domains §3/5/6):
    0  success
    2  argparse error
    3  TypedRunInvalid
    4  AdataMismatch
    5  MarkerDBUnavailable
    6  LLMUnavailable
    7  InvariantViolation
    8  CoverageBelowThreshold
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import anndata as ad

from _artifacts import write_artifacts
from _candidates import rank_celltype_candidates
from _de import per_cluster_de
from _errors import (
    ConsensusInterpretError,
    CoverageBelowThresholdError,
    InvariantViolationError,
    LLMUnavailableError,
    MarkerDBUnavailableError,
    TypedRunInvalidError,
)
from _llm import annotate_cluster, synthesize_next_steps
from _marker_db import MarkerDB
from _run_reader import load_typed_run

logger = logging.getLogger("consensus-interpret")

# Skill version. `skill.yaml` was its source until the old skill system was
# deleted; this is now the only place it is declared. Required leaf-skill
# module constants (omicsclaw.skill.protocol.validate_skill_module).
SKILL_NAME = "consensus-interpret"
SKILL_VERSION = "0.1.0"

_BANNER_AI = "[A+I: Interpreted on verified consensus]"
_BANNER_NOLLM = "[I-noLLM: Structural patterns only — biology annotation disabled]"

_DEFAULT_TOP_K_MARKERS = 20
_DEFAULT_TOP_K_NEXT_STEPS = 3
_DEFAULT_COVERAGE_FLOOR = 0.5


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "LLM-grounded biological interpretation of a verified typed "
            "consensus run (ADR 0012). Banner: "
            "[A+I: Interpreted on verified consensus]."
        )
    )
    parser.add_argument("--input", required=True, help="typed consensus run dir")
    parser.add_argument("--output", required=True, help="interpreted output dir")
    parser.add_argument("--tissue", default=None,
                        help="one of brain/immune/kidney/liver — selects bundled marker DB")
    parser.add_argument("--adata", default=None,
                        help="override plan.json:input_path; required for legacy runs without it")
    parser.add_argument("--markers", default=None,
                        help="user-provided marker TSV (overrides --tissue)")
    parser.add_argument("--no-llm", action="store_true",
                        help="structural-only degrade mode; banner [I-noLLM: ...]; no biology annotation")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--top-k-markers", type=int, default=_DEFAULT_TOP_K_MARKERS)
    parser.add_argument("--top-k-next-steps", type=int, default=_DEFAULT_TOP_K_NEXT_STEPS,
                        help="capped at 3 by ADR 0012")
    parser.add_argument("--coverage-floor", type=float, default=_DEFAULT_COVERAGE_FLOOR,
                        help="T2->T1 escalation if interpretable_cluster_frac < floor (default 0.5)")
    return parser


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _build_cluster_ctx(cluster_id: int, bundle, de_df, n_cells: int) -> dict:
    """Render the cluster-context block fed into the annotate.tmpl LLM prompt."""
    sub = de_df[de_df["cluster"] == cluster_id]
    if sub.empty:
        de_rows = "(no DE rows)"
    else:
        de_rows = "\n".join(
            f"{int(row['rank'])}\t{row['gene']}\t{row['score']:.2f}\t{row['pval_adj']:.2e}"
            for _, row in sub.iterrows()
        )

    # NMI neighbors: lowest 2 pair-wise NMI rows that mention any member.
    nmi = bundle.nmi_matrix
    nmi_neighbors_lines: list[str] = []
    if not nmi.empty:
        cols = list(nmi.columns)
        pairs: list[tuple[str, str, float]] = []
        for i, mi in enumerate(cols):
            for mj in cols[i + 1:]:
                try:
                    v = float(nmi.loc[mi, mj])
                except (KeyError, ValueError):
                    continue
                pairs.append((mi, mj, v))
        pairs.sort(key=lambda t: t[2])
        for mi, mj, v in pairs[:2]:
            nmi_neighbors_lines.append(f"  pair ({mi}, {mj}): NMI={v:.3f}")
    nmi_neighbors = "\n".join(nmi_neighbors_lines) if nmi_neighbors_lines else "  (no inter-method NMI matrix available)"

    return {
        "cluster_id": cluster_id,
        "n_cells": n_cells,
        "mean_local_purity": "(not recorded in typed run for this skill)",
        "member_agreement_summary": "(per-member overlap not yet computed; use cross_method_nmi below)",
        "nmi_neighbors": nmi_neighbors,
        "de_top_k_rows": de_rows,
    }


def _coverage(annotations) -> float:
    if not annotations:
        return 0.0
    interpreted = sum(1 for a in annotations if a.cell_type != "Unknown")
    return interpreted / len(annotations)


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #

def _run(args: argparse.Namespace) -> int:
    # 1. T1 preflight — load typed run bundle
    bundle = load_typed_run(args.input, adata_override=args.adata)
    output_dir = Path(args.output)

    # 2. Load full adata (need X for DE; backed='r' was used in Slice 1 just
    # for the cheap obs-index check).
    adata = ad.read_h5ad(bundle.adata_path)

    # 3. Inline DE on the consensus labels (always — Slice 7 writes
    # de_per_cluster.csv even in --no-llm mode)
    de_df, de_status = per_cluster_de(
        adata,
        bundle.consensus_labels,
        consensus_label_column=bundle.consensus_label_column,
        top_k=args.top_k_markers,
    )

    # 4. Degrade path: --no-llm
    if args.no_llm:
        logger.info("--no-llm set; skipping biology annotation; writing structural-only report")
        write_artifacts(
            output_dir=output_dir, bundle=bundle, annotations=[], next_steps=[],
            de_df=de_df, audit={"marker_db_source": None, "llm_model": "disabled (--no-llm)"},
            banner=_BANNER_NOLLM,
        )
        return 0

    # 5. Marker DB (T1)
    marker_db = MarkerDB.load(tissue=args.tissue, override_path=args.markers)

    # 6. Candidate ranking (deterministic, pre-LLM)
    candidates_by_cluster = rank_celltype_candidates(
        de_df, marker_db, top_k=5,
    )

    # 7. Per-cluster LLM annotation (skip clusters with no candidates — they
    # surface as "Unknown" via empty-candidates path in annotate_cluster)
    annotations = []
    cluster_sizes = bundle.consensus_labels[bundle.consensus_label_column].value_counts().to_dict()
    interpretable_clusters = [c for c in sorted(de_status.keys()) if de_status[c] == "ok"]
    for cluster_id in interpretable_clusters:
        candidates = candidates_by_cluster.get(cluster_id, [])
        n_cells = int(cluster_sizes.get(cluster_id, 0))
        cluster_ctx = _build_cluster_ctx(cluster_id, bundle, de_df, n_cells)
        annotation = annotate_cluster(cluster_ctx, candidates)
        annotations.append(annotation)

    # 8. T2 -> T1: coverage check
    coverage = _coverage(annotations)
    if coverage < args.coverage_floor:
        raise CoverageBelowThresholdError(
            f"only {coverage:.0%} of clusters interpretable "
            f"(floor {args.coverage_floor:.0%}); check --tissue match / "
            f"adata expression characteristics."
        )

    # 9. Next-step synthesis (β)
    next_steps = synthesize_next_steps(
        annotations, bundle.nmi_matrix, top_k=args.top_k_next_steps,
    )

    # 10. Write artifacts (T3 invariant enforcement inside)
    audit = {
        "marker_db_source": marker_db.source_label,
        "coverage": coverage,
    }
    write_artifacts(
        output_dir=output_dir, bundle=bundle, annotations=annotations,
        next_steps=next_steps, de_df=de_df, audit=audit, banner=_BANNER_AI,
    )

    print(
        f"[consensus-interpret] OK: {len(annotations)} clusters interpreted; "
        f"{len(next_steps)} next-step recommendations; "
        f"coverage={coverage:.0%}; banner={_BANNER_AI}.",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=os.environ.get("OMICSCLAW_LOG_LEVEL", "INFO"))
    try:
        return _run(args)
    except ConsensusInterpretError as exc:
        print(f"[consensus-interpret] FATAL: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        # Unexpected programming bug — log full trace + exit 1
        logger.exception("unexpected internal error: %s", exc)
        print(f"[consensus-interpret] INTERNAL ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
