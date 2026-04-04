#!/usr/bin/env python3
"""Single-cell metacell construction."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_output_readme, write_result_json
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.metacell import make_demo_metacell_adata, run_kmeans_metacells, run_seacells_metacells

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-metacell"
SKILL_VERSION = "0.1.0"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell metacell construction")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="seacells", choices=["seacells", "kmeans"])
    p.add_argument("--use-rep", type=str, default="X_pca")
    p.add_argument("--n-metacells", type=int, default=30)
    p.add_argument("--celltype-key", type=str, default="leiden")
    p.add_argument("--min-iter", type=int, default=10)
    p.add_argument("--max-iter", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Metacell Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(summary.get("method", "NA")),
            "Embedding": str(params.get("use_rep", "X_pca")),
            "Requested metacells": str(params.get("n_metacells", 0)),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Executed method: `{summary.get('method')}`",
        f"- Metacells produced: `{summary.get('n_metacells', 'NA')}`",
        f"- Mean cells per metacell: `{summary.get('mean_cells_per_metacell', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- Metacells compress noisy single-cell profiles into more stable neighborhood summaries.",
        "- Use SEACells-style results when you need structure-aware aggregation; use the k-means fallback only as a lightweight compression baseline.",
    ]
    (output_dir / "report.md").write_text(header + "\n" + "\n".join(body) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)

    if args.demo:
        adata = make_demo_metacell_adata(seed=args.seed)
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    if args.method == "seacells":
        madata, labels, _model = run_seacells_metacells(
            adata,
            use_rep=args.use_rep,
            n_metacells=args.n_metacells,
            min_iter=args.min_iter,
            max_iter=args.max_iter,
            celltype_key=args.celltype_key,
        )
        executed = "seacells"
    else:
        madata, labels = run_kmeans_metacells(
            adata,
            use_rep=args.use_rep,
            n_metacells=args.n_metacells,
            seed=args.seed,
        )
        executed = "kmeans"

    adata.obs["metacell"] = labels.reindex(adata.obs_names).astype(str)
    madata.write_h5ad(output_dir / "metacells.h5ad")
    madata.obs.to_csv(tables_dir / "metacell_summary.csv")
    pd.DataFrame({"cell": adata.obs_names, "metacell": adata.obs["metacell"].astype(str)}).to_csv(
        tables_dir / "cell_to_metacell.csv", index=False
    )

    if args.use_rep in adata.obsm:
        emb = pd.DataFrame(adata.obsm[args.use_rep], index=adata.obs_names)
        centers = emb.join(adata.obs[["metacell"]]).groupby("metacell").mean(numeric_only=True)
        if centers.shape[1] >= 2:
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.scatter(emb.iloc[:, 0], emb.iloc[:, 1], s=5, alpha=0.15, color="#bdbdbd")
            ax.scatter(centers.iloc[:, 0], centers.iloc[:, 1], s=35, color="#d95f0e")
            ax.set_title("Metacell centroids")
            fig.tight_layout()
            fig.savefig(figures_dir / "metacell_centroids.png", dpi=200)
            plt.close(fig)

    summary = {
        "method": executed,
        "n_metacells": int(madata.n_obs),
        "mean_cells_per_metacell": float(adata.obs["metacell"].value_counts().mean()),
    }
    params = {
        "method": args.method,
        "use_rep": args.use_rep,
        "n_metacells": args.n_metacells,
        "celltype_key": args.celltype_key,
        "min_iter": args.min_iter,
        "max_iter": args.max_iter,
        "seed": args.seed,
    }
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        {
            "params": params,
            "outputs": {
                "metacell_h5ad": str(output_dir / "metacells.h5ad"),
                "cell_to_metacell": str(tables_dir / "cell_to_metacell.csv"),
                "metacell_summary": str(tables_dir / "metacell_summary.csv"),
            },
        },
        input_checksum=input_checksum,
    )
    _write_report(output_dir, summary, params, input_path)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Metacell construction and compression for scRNA-seq.",
        preferred_method=args.method,
    )
    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
