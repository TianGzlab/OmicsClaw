#!/usr/bin/env python3
"""CLI wrapper for creating OmicsClaw skill scaffolds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.core.skill_scaffolder import create_skill_scaffold

SKILL_NAME = "omics-skill-builder"
SKILL_VERSION = "0.1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an OmicsClaw skill scaffold.")
    parser.add_argument("--output", required=True, help="Directory for the scaffold report.")
    parser.add_argument("--request", help="Original user request describing the desired skill.")
    parser.add_argument("--skill-name", default="", help="Preferred hyphenated skill alias.")
    parser.add_argument(
        "--domain",
        default="orchestrator",
        choices=[
            "spatial",
            "singlecell",
            "genomics",
            "proteomics",
            "metabolomics",
            "bulkrna",
            "orchestrator",
        ],
        help="Target OmicsClaw domain.",
    )
    parser.add_argument("--summary", default="", help="One-line skill summary.")
    parser.add_argument("--source-analysis-dir", default="", help="Promote a successful autonomous analysis output directory into the new skill.")
    parser.add_argument("--promote-from-latest", action="store_true", help="Promote the most recent autonomous analysis output.")
    parser.add_argument("--trigger-keyword", dest="trigger_keywords", action="append", default=[])
    parser.add_argument("--method", dest="methods", action="append", default=[])
    parser.add_argument("--input-format", dest="input_formats", action="append", default=[])
    parser.add_argument("--output-item", dest="primary_outputs", action="append", default=[])
    parser.add_argument("--no-tests", action="store_true", help="Do not generate a test stub.")
    parser.add_argument("--demo", action="store_true", help="Run a built-in scaffold example.")
    return parser.parse_args()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.demo:
        request = (
            "Create a reusable OmicsClaw skill for CellCharter-based spatial "
            "domain analysis on AnnData inputs."
        )
        skill_name = args.skill_name or "spatial-cellcharter-domains"
        domain = args.domain or "spatial"
        summary = args.summary or (
            "Spatial domain identification scaffold for CellCharter-based workflows."
        )
        trigger_keywords = args.trigger_keywords or ["cellcharter domains", "cellcharter spatial"]
        methods = args.methods or ["cellcharter"]
        input_formats = args.input_formats or ["AnnData with spatial coordinates"]
        primary_outputs = args.primary_outputs or ["processed.h5ad", "figures/domain_map.png"]
    else:
        if not args.request:
            raise SystemExit("--request is required unless --demo is used.")
        request = args.request
        skill_name = args.skill_name
        domain = args.domain
        summary = args.summary
        source_analysis_dir = args.source_analysis_dir
        promote_from_latest = args.promote_from_latest
        trigger_keywords = args.trigger_keywords
        methods = args.methods
        input_formats = args.input_formats
        primary_outputs = args.primary_outputs
    if args.demo:
        source_analysis_dir = args.source_analysis_dir
        promote_from_latest = args.promote_from_latest

    result = create_skill_scaffold(
        request=request,
        domain=domain,
        skill_name=skill_name,
        summary=summary,
        source_analysis_dir=source_analysis_dir,
        promote_from_latest=promote_from_latest,
        input_formats=input_formats,
        primary_outputs=primary_outputs,
        methods=methods,
        trigger_keywords=trigger_keywords,
        create_tests=not args.no_tests,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    readme = f"""# Omics Skill Builder

Created a new scaffolded OmicsClaw skill.

- Skill: `{result.skill_name}`
- Domain: `{result.domain}`
- Skill directory: `{result.skill_dir}`
- Registry refreshed: `{result.registry_refreshed}`
"""

    report = """# Scaffold Report

The scaffold was created successfully.

Next steps:
1. Replace placeholder logic in the generated Python entrypoint.
2. Expand the generated test into real scientific validation.
3. Refine trigger keywords and parameter hints in the generated SKILL.md.
"""

    _write_text(output_dir / "README.md", readme)
    _write_text(output_dir / "report.md", report)
    _write_text(
        output_dir / "reproducibility" / "commands.sh",
        (
            f"oc run omics-skill-builder --output {output_dir} "
            f"--request {json.dumps(request)} --domain {result.domain} "
            f"--skill-name {result.skill_name}\n"
        ),
    )
    (output_dir / "result.json").write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Created OmicsClaw skill scaffold at {result.skill_dir}")
    print(f"Summary written to {output_dir / 'result.json'}")


if __name__ == "__main__":
    main()
