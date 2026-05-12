#!/usr/bin/env python3
"""REPLACE_SKILL_NAME — placeholder runtime for the OmicsClaw v2 skill template.

This is the minimum-viable wrapper that lints clean and runs `--demo` out of
the box.  The demo synthesises a 5x3 CSV in memory so the template stays
domain-agnostic; replace `synthesise_demo` and `load_input` with real I/O
for your data modality (AnnData, VCF, mzML, …) when filling in.

Usage:
    python replace_me.py --demo --output /tmp/out
    python replace_me.py --input data.csv --output results/ --method default
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Bootstrap sys.path so `omicsclaw.common.report` resolves whether this script
# is run from the template directory or after being copied into
# `skills/<domain>/<skill>/`.  Walk up looking for the omicsclaw package.
_HERE = Path(__file__).resolve()
for _candidate in _HERE.parents:
    if (_candidate / "omicsclaw" / "__init__.py").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

from omicsclaw.common.report import (  # noqa: E402
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

SKILL_NAME = "REPLACE_SKILL_NAME"
SKILL_VERSION = "0.1.0"

DEFAULT_METHOD = "default"
ALLOWED_METHODS = ("default",)

logger = logging.getLogger(SKILL_NAME)


def synthesise_demo() -> pd.DataFrame:
    """Built-in synthetic data for `--demo`.

    Replace this with a real demo fixture from `<skill>/data/` when your skill
    needs a richer example (e.g. a small h5ad, a tiny VCF).
    """
    rng = np.random.default_rng(seed=42)
    return pd.DataFrame(
        {
            "feature": [f"feature_{i}" for i in range(5)],
            "value": rng.normal(loc=0.0, scale=1.0, size=5).round(4),
            "rank": np.arange(1, 6),
        }
    )


def load_input(input_path: Path) -> pd.DataFrame:
    """Read real input.  Replace with your modality's reader."""
    if input_path.suffix == ".csv":
        return pd.read_csv(input_path)
    raise ValueError(
        f"replace_me.py loads CSV only — swap this for your modality's "
        f"reader (e.g. anndata.read_h5ad).  Saw: {input_path}"
    )


def run_method(frame: pd.DataFrame, method: str) -> pd.DataFrame:
    """Placeholder transformation — replace with the real algorithm."""
    if method not in ALLOWED_METHODS:
        raise ValueError(
            f"--method {method!r} not in allowed list {ALLOWED_METHODS}"
        )
    out = frame.copy()
    out["method"] = method
    return out


def write_outputs(
    output_dir: Path,
    *,
    frame: pd.DataFrame,
    method: str,
    input_path: Path | None,
) -> None:
    """Write the three baseline artifacts: `tables/replace_me.csv`,
    `report.md`, `result.json`.

    Every path written here MUST also appear in `references/output_contract.md`
    or `scripts/skill_lint.py::_check_output_contract_paths` will fail.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    table_path = tables_dir / "replace_me.csv"
    frame.to_csv(table_path, index=False)

    summary = {
        "method": method,
        "n_rows": int(len(frame)),
        "n_columns": int(frame.shape[1]),
    }

    header = generate_report_header(
        title=f"{SKILL_NAME} Report",
        skill_name=SKILL_NAME,
        input_files=[input_path] if input_path else None,
        extra_metadata={"Method": method},
    )
    body_lines = [
        "## Summary",
        "",
        f"- **Method**: {method}",
        f"- **Rows**: {summary['n_rows']}",
        f"- **Columns**: {summary['n_columns']}",
        "",
        "## Outputs",
        "",
        f"- `tables/replace_me.csv` — {summary['n_rows']} rows",
    ]
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        header + "\n".join(body_lines) + "\n" + footer
    )

    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={
            "method": method,
            "table": str(table_path.relative_to(output_dir)),
        },
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SKILL_NAME,
        description=(
            "Placeholder OmicsClaw v2 skill — replace with real logic."
        ),
    )
    parser.add_argument("--input", type=Path, help="Path to input file.")
    parser.add_argument(
        "--output", type=Path, required=True, help="Output directory."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on built-in synthetic data instead of --input.",
    )
    parser.add_argument(
        "--method",
        default=DEFAULT_METHOD,
        choices=ALLOWED_METHODS,
        help=f"Method backend (default: {DEFAULT_METHOD}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    if not args.demo and args.input is None:
        raise SystemExit("Provide --input <file> or --demo.")

    if args.demo:
        frame = synthesise_demo()
        input_path: Path | None = None
    else:
        input_path = args.input.resolve()
        frame = load_input(input_path)

    result = run_method(frame, args.method)
    write_outputs(
        args.output,
        frame=result,
        method=args.method,
        input_path=input_path,
    )
    logger.info("Wrote outputs to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
