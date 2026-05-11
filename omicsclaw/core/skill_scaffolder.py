"""Helpers for creating OmicsClaw-native skill scaffolds."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import json
import os
import re
import shutil
from pathlib import Path
import textwrap
from typing import Iterable

from omicsclaw.common.manifest import StepRecord
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.verification import (
    COMPLETION_REPORT_FILENAME,
    WORKSPACE_KIND_ANALYSIS_RUN,
    ArtifactRequirement,
    build_completion_report,
    format_completion_summary,
    isolated_workspace,
    update_workspace_manifest,
    write_completion_report,
)
from omicsclaw.version import __version__


def _resolve_omicsclaw_dir() -> Path:
    override = str(os.getenv("OMICSCLAW_DIR", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


OMICSCLAW_DIR = _resolve_omicsclaw_dir()
SKILLS_DIR = OMICSCLAW_DIR / "skills"
OUTPUT_DIR = OMICSCLAW_DIR / "output"
SKILL_TEMPLATE_PATH = OMICSCLAW_DIR / "templates" / "skill" / "SKILL.md"
STAGING_ROOT = OMICSCLAW_DIR / ".omicsclaw-staging" / "skill-scaffolds"
SKILL_SCAFFOLDER_VERSION = __version__

VALID_DOMAINS = (
    "spatial",
    "singlecell",
    "genomics",
    "proteomics",
    "metabolomics",
    "bulkrna",
    "orchestrator",
)

_DOMAIN_PROFILES = {
    "spatial": {
        "title": "Spatial Transcriptomics",
        "emoji": "🧭",
        "input_formats": [
            ("AnnData", ".h5ad", "Spatial coordinates in obsm['spatial']", "data/sample_spatial.h5ad"),
            ("Visium-style directory", "folder", "Filtered matrix + spatial metadata", "data/visium_run/"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Spatial coordinates", "obsm['spatial']", "Needed for neighborhood-aware analyses and plots"),
            ("Expression matrix", "adata.X or layers['counts']", "Needed for feature-level computations"),
            ("Observation metadata", "adata.obs", "Needed for grouping, QC, or annotation exports"),
        ],
    },
    "singlecell": {
        "title": "Single-Cell Omics",
        "emoji": "🧫",
        "input_formats": [
            ("AnnData", ".h5ad", "Cell x gene matrix with obs/var metadata", "data/sample_scrna.h5ad"),
            ("Sparse matrices", ".mtx/.tsv", "Matrix + barcodes + features", "data/filtered_feature_bc_matrix/"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Expression matrix", "adata.X or layers['counts']", "Needed for normalization and downstream analysis"),
            ("Cell metadata", "adata.obs", "Needed for grouping, QC, and annotation"),
            ("Feature metadata", "adata.var", "Needed for gene selection and reporting"),
        ],
    },
    "genomics": {
        "title": "Genomics",
        "emoji": "🧬",
        "input_formats": [
            ("Variants", ".vcf", "Standard VCF header and variant records", "data/sample.vcf"),
            ("Alignments", ".bam/.cram", "Coordinate-sorted reads with index", "data/sample.bam"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Primary genomic file", "VCF/BAM/CRAM/FASTA", "Needed to run the core genomics method"),
            ("Reference metadata", "Reference genome or annotations", "Needed for reproducible interpretation"),
            ("Sample identifiers", "File names or metadata table", "Needed for multi-sample reporting"),
        ],
    },
    "proteomics": {
        "title": "Proteomics",
        "emoji": "🧪",
        "input_formats": [
            ("Mass spectrometry", ".mzML/.mzXML", "Centroided or profile MS data", "data/sample.mzML"),
            ("Quantification table", ".csv/.tsv", "Sample x protein or peptide matrix", "data/protein_matrix.csv"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Primary MS input", "mzML/mzXML or quantified table", "Needed for identification or quantification"),
            ("Feature metadata", "Protein or peptide annotations", "Needed for interpretation and exports"),
            ("Sample labels", "Metadata table or columns", "Needed for comparisons and summaries"),
        ],
    },
    "metabolomics": {
        "title": "Metabolomics",
        "emoji": "🧫",
        "input_formats": [
            ("Mass spectrometry", ".mzML/.cdf", "Raw or preprocessed metabolomics spectra", "data/sample.mzML"),
            ("Feature table", ".csv/.tsv", "Sample x metabolite/feature matrix", "data/metabolite_matrix.csv"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Primary metabolomics input", "Raw spectra or feature matrix", "Needed for peak processing or statistics"),
            ("Feature annotations", "Compound IDs or putative metabolite labels", "Needed for downstream reporting"),
            ("Sample metadata", "Condition or batch columns", "Needed for contrasts and QC"),
        ],
    },
    "bulkrna": {
        "title": "Bulk RNA-seq",
        "emoji": "📚",
        "input_formats": [
            ("Count matrix", ".csv/.tsv", "Genes x samples count table", "data/counts.tsv"),
            ("Reads", ".fastq/.bam", "Aligned or raw sequencing files", "data/sample_R1.fastq.gz"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("Expression counts", "Count matrix or alignment-derived counts", "Needed for DE or enrichment"),
            ("Sample sheet", "Condition and replicate annotations", "Needed for model design"),
            ("Gene identifiers", "Gene symbols or Ensembl IDs", "Needed for interpretation"),
        ],
    },
    "orchestrator": {
        "title": "Orchestrator",
        "emoji": "🛠",
        "input_formats": [
            ("Natural language request", "text", "User goal or pipeline specification", "\"build a routing helper\""),
            ("Optional local file", "path", "Server-side reference file", "data/reference.json"),
            ("Demo", "n/a", "--demo", "Built-in scaffold demo"),
        ],
        "requirements": [
            ("User intent", "Prompt or spec document", "Needed to determine the workflow contract"),
            ("Optional config", "JSON/YAML or CLI flags", "Needed for reusable orchestrator behaviors"),
            ("Output contract", "Markdown/JSON artifacts", "Needed for agent-to-agent handoff"),
        ],
    },
}

_SLUG_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_REQUEST_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_.+]{1,}")
_REQUEST_STOPWORDS = {
    "a",
    "an",
    "analysis",
    "and",
    "build",
    "create",
    "for",
    "from",
    "generate",
    "in",
    "into",
    "new",
    "of",
    "omicsclaw",
    "or",
    "skill",
    "that",
    "the",
    "to",
    "workflow",
}


@dataclass
class SkillScaffoldResult:
    skill_name: str
    domain: str
    skill_dir: str
    script_path: str
    skill_md_path: str
    spec_path: str
    test_path: str = ""
    manifest_path: str = ""
    completion_report_path: str = ""
    completion: dict[str, object] = field(default_factory=dict)
    created_files: list[str] | None = None
    template_path: str = str(SKILL_TEMPLATE_PATH)
    registry_refreshed: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["created_files"] = list(self.created_files or [])
        return data


@dataclass
class AutonomousAnalysisBundle:
    source_dir: str
    notebook_path: str
    analysis_plan: str
    result_summary: str
    web_sources: str
    capability_decision: dict
    python_code: str
    goal: str
    domain: str = ""
    input_file: str = ""
    context: str = ""


def slugify_skill_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = _SLUG_TOKEN_RE.sub("-", text)
    text = text.strip("-")
    return re.sub(r"-{2,}", "-", text)


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def infer_skill_name(request: str, domain: str, preferred_name: str = "") -> str:
    slug = slugify_skill_name(preferred_name)
    if slug:
        return slug

    tokens = [
        token
        for token in _REQUEST_TOKEN_RE.findall((request or "").lower())
        if token not in _REQUEST_STOPWORDS and not token.isdigit()
    ]
    if tokens:
        return slugify_skill_name("-".join(tokens[:5]))

    return f"{domain}-custom-skill"


def _display_title(skill_name: str) -> str:
    return " ".join(part.capitalize() for part in skill_name.replace("_", "-").split("-") if part)


def _yaml_inline_list(items: Iterable[str]) -> str:
    values = [json.dumps(item, ensure_ascii=False) for item in _unique(items)]
    return "[" + ", ".join(values) + "]"


def _yaml_block_list(items: Iterable[str], indent: str = "      ") -> str:
    values = _unique(items)
    if not values:
        return indent + "[]"
    return "\n".join(f"{indent}- {json.dumps(item, ensure_ascii=False)}" for item in values)


def _markdown_bullets(items: Iterable[str], fallback: str) -> str:
    values = _unique(items)
    if not values:
        values = [fallback]
    return "\n".join(f"- {item}" for item in values)


def _input_table_rows(domain: str, extra_inputs: Iterable[str]) -> str:
    profile = _DOMAIN_PROFILES[domain]
    rows = list(profile["input_formats"])
    for item in _unique(extra_inputs):
        rows.insert(
            max(len(rows) - 1, 0),
            ("Additional input", "custom", item, item),
        )
    return "\n".join(
        f"| {label} | `{ext}` | {structure} | `{example}` |"
        for label, ext, structure, example in rows
    )


def _requirement_rows(domain: str) -> str:
    return "\n".join(
        f"| {req} | `{where}` | {why} |"
        for req, where, why in _DOMAIN_PROFILES[domain]["requirements"]
    )


def render_skill_markdown(
    *,
    skill_name: str,
    domain: str,
    summary: str,
    request: str,
    methods: Iterable[str],
    input_formats: Iterable[str],
    primary_outputs: Iterable[str],
    trigger_keywords: Iterable[str],
    source_bundle: AutonomousAnalysisBundle | None = None,
) -> str:
    title = _display_title(skill_name)
    profile = _DOMAIN_PROFILES[domain]
    summary = (summary or "").strip() or f"Autogenerated OmicsClaw scaffold for {title}."
    methods_list = _unique(methods) or ["default"]
    outputs_list = _unique(primary_outputs) or [
        "README.md",
        "report.md",
        "result.json",
        "reproducibility/analysis_notebook.ipynb",
    ]
    keywords = _unique(trigger_keywords) or [
        title.lower(),
        skill_name,
        f"{domain} analysis",
    ]
    script_name = f"{skill_name.replace('-', '_')}.py"
    methodology_sections = "\n".join(
        (
            f"### {method.title()}\n"
            "1. Load and validate the expected input structure.\n"
            "2. Run the method-specific wrapper or external library calls.\n"
            "3. Save stable OmicsClaw outputs and summary artifacts.\n\n"
            "**Key parameters**\n\n"
            "| Parameter | Default | Description |\n"
            "|-----------|---------|-------------|\n"
            f"| `--method` | `{method}` | Selects the backend implementation. |\n"
            "| `--species` | `\"\"` | Optional biological context label for reporting. |\n\n"
            "> Replace this placeholder section with the actual scientific method contract before production use.\n"
        )
        for method in methods_list
    )

    promotion_note = (
        f"Promoted from successful autonomous analysis at `{source_bundle.source_dir}`."
        if source_bundle
        else "Generated from `templates/skill/` by `omics-skill-builder`."
    )

    return f"""---
name: {skill_name}
description: >-
  {summary}
version: 0.1.0
author: OmicsClaw
license: MIT
tags: {_yaml_inline_list([domain, "autogenerated", "skill-scaffold"] + methods_list[:3])}
metadata:
  omicsclaw:
    domain: {domain}
    script: {script_name}
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: {json.dumps(profile["emoji"])}
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: fill-me-in
        bins: []
    trigger_keywords:
{_yaml_block_list(keywords)}
    allowed_extra_flags:
      - "--method"
      - "--species"
    legacy_aliases: []
    saves_h5ad: false
    requires_preprocessed: false
---

# {profile["emoji"]} {title}

{promotion_note}

## Why This Exists

- **Requested workflow**: {request.strip() or summary}
- **Domain fit**: This scaffold targets the **{profile["title"]}** domain inside OmicsClaw.
- **What is included**: a ready-to-edit `SKILL.md`, a runnable Python entrypoint, a minimal test, and a saved scaffold specification.

## Core Capabilities

{_markdown_bullets(methods_list, "Define the primary analysis backend for this skill.")}
- Persist standard OmicsClaw outputs such as `README.md`, `report.md`, `result.json`, and `reproducibility/`.
- Provide a reproducible CLI contract that already accepts `--input`, `--output`, `--demo`, `--method`, and `--species`.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
{_input_table_rows(domain, input_formats)}

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
{_requirement_rows(domain)}

## Workflow

1. Load user input or scaffold demo data.
2. Validate domain-specific prerequisites before running the method.
3. Execute the primary method backend selected by `--method`.
4. Write standard OmicsClaw outputs and any domain-specific tables or plots.
5. Persist figure-ready or machine-readable artifacts for downstream reuse.
6. Document caveats, assumptions, and follow-up implementation tasks.

## CLI Reference

```bash
oc run {skill_name} --input <input_file> --output <report_dir>
oc run {skill_name} --demo --output /tmp/{skill_name}
python skills/{domain}/{skill_name}/{script_name} --input <file> --output <dir> --method {methods_list[0]}
```

## Example Queries

- "Add a reusable OmicsClaw skill called {skill_name}"
- "Create a {profile["title"].lower()} skill for {summary.lower()}"
- "Scaffold a new OmicsClaw workflow around {methods_list[0]}"

## Algorithm / Methodology

{methodology_sections}

## Planned Outputs

{_markdown_bullets(outputs_list, "Define the primary output files for this skill.")}

## Scaffold Checklist

- Replace placeholder dependencies in the frontmatter install block.
- Implement the scientific method in `{script_name}`.
- Expand the generated test into domain-specific validation cases.
- Update trigger keywords and parameter hints to match real behavior.
"""


def render_skill_script(
    *,
    skill_name: str,
    domain: str,
    summary: str,
    methods: Iterable[str],
) -> str:
    methods_list = _unique(methods) or ["default"]
    default_method = methods_list[0]
    title = _display_title(skill_name)
    summary = (summary or "").strip() or f"Autogenerated OmicsClaw scaffold for {title}."
    checklist_rows = [
        ("load_input", "todo"),
        ("validate_requirements", "todo"),
        ("implement_method", "todo"),
        ("write_standard_outputs", "done"),
    ]
    checklist_literal = repr(checklist_rows)

    return f"""#!/usr/bin/env python3
\"\"\"Autogenerated OmicsClaw scaffold for {title}.\"\"\"

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SKILL_NAME = "{skill_name}"
DOMAIN = "{domain}"
SUMMARY = {json.dumps(summary)}
DEFAULT_METHOD = "{default_method}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument("--input", dest="input_path", help="Path to input data")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run the scaffold demo")
    parser.add_argument("--method", default=DEFAULT_METHOD, help="Method backend name")
    parser.add_argument("--species", default="", help="Optional species label")
    return parser.parse_args()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "status"])
        writer.writerows({checklist_literal})


def main() -> None:
    args = parse_args()
    if not args.demo and not args.input_path:
        raise SystemExit("Provide --input or use --demo.")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    readme = f\"\"\"# {{SKILL_NAME}}

This is an autogenerated OmicsClaw skill scaffold.

- Domain: {{DOMAIN}}
- Method: {{args.method}}
- Input: {{args.input_path or "demo"}}
- Species: {{args.species or "not provided"}}

Next step: replace the placeholder implementation in `{{SKILL_NAME.replace("-", "_")}}.py`.
\"\"\"

    report = f\"\"\"# Scaffold Report

The scientific implementation for `{{SKILL_NAME}}` has not been completed yet.
This scaffold exists so the skill can be edited, reviewed, and iterated inside the OmicsClaw repository.

Implementation checklist:
- wire real loaders
- validate domain-specific state
- implement the scientific backend
- expand tests beyond the scaffold smoke test
\"\"\"

    result = {{
        "ok": True,
        "status": "scaffold",
        "skill": SKILL_NAME,
        "domain": DOMAIN,
        "input": args.input_path or "demo",
        "method": args.method,
        "species": args.species,
        "summary": SUMMARY,
    }}

    _write_text(output_dir / "README.md", readme)
    _write_text(output_dir / "report.md", report)
    _write_text(
        output_dir / "reproducibility" / "commands.sh",
        f"oc run {{SKILL_NAME}} --demo --output {{output_dir}}\\n",
    )
    _write_csv(output_dir / "tables" / "scaffold_checklist.csv")
    (output_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Scaffold skill '{{SKILL_NAME}}' completed. Outputs written to {{output_dir}}")


if __name__ == "__main__":
    main()
"""


def render_promoted_skill_script(
    *,
    skill_name: str,
    domain: str,
    summary: str,
    source_bundle: AutonomousAnalysisBundle,
) -> str:
    title = _display_title(skill_name)
    goal = source_bundle.goal or summary
    web_context = source_bundle.web_sources or ""
    analysis_context = source_bundle.context or ""
    default_input = source_bundle.input_file or ""
    requires_input = bool(default_input)
    normalized_code = _normalize_promoted_code(source_bundle.python_code, source_bundle.source_dir)
    indented_code = textwrap.indent(normalized_code.rstrip() + "\n", "    ")

    return f"""#!/usr/bin/env python3
\"\"\"Promoted OmicsClaw skill for {title}.\"\"\"

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_NAME = "{skill_name}"
DOMAIN = "{domain}"
SUMMARY = {json.dumps(summary or goal, ensure_ascii=False)}
ANALYSIS_GOAL = {json.dumps(goal, ensure_ascii=False)}
ANALYSIS_CONTEXT = {json.dumps(analysis_context, ensure_ascii=False)}
WEB_CONTEXT = {json.dumps(web_context, ensure_ascii=False)}
SOURCE_ANALYSIS_DIR = {json.dumps(source_bundle.source_dir, ensure_ascii=False)}
SOURCE_NOTEBOOK = {json.dumps(source_bundle.notebook_path, ensure_ascii=False)}
DEFAULT_INPUT_FILE = {json.dumps(default_input, ensure_ascii=False)}
REQUIRES_INPUT = {str(requires_input)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument("--input", dest="input_path", help="Path to input data")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Reuse the original autonomous-analysis input when available")
    parser.add_argument("--method", default="", help="Optional method backend name")
    parser.add_argument("--species", default="", help="Optional species label")
    return parser.parse_args()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    effective_input = args.input_path or (DEFAULT_INPUT_FILE if args.demo else "")
    if REQUIRES_INPUT and not effective_input:
        raise SystemExit("Provide --input, or use --demo to reuse the original autonomous-analysis input.")

    skill_output_dir = Path(args.output)
    skill_output_dir.mkdir(parents=True, exist_ok=True)

    INPUT_FILE = effective_input
    AUTONOMOUS_OUTPUT_DIR = str(skill_output_dir)
    OUTPUT_PATH = skill_output_dir
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

{indented_code}

    readme = f\"\"\"# {{SKILL_NAME}}

This skill was promoted from a successful `custom_analysis_execute` run.

- Domain: {{DOMAIN}}
- Input: {{effective_input or "none"}}
- Original source notebook: {{SOURCE_NOTEBOOK}}
- Original autonomous analysis directory: {{SOURCE_ANALYSIS_DIR}}

Inspect `report.md` and `references/` for the promotion provenance.
\"\"\"

    report = f\"\"\"# Promoted Skill Report

This skill was generated from a successful autonomous analysis notebook.

## Original Goal

{{ANALYSIS_GOAL}}

## Promotion Notes

- This script started from notebook code that previously ran successfully.
- Review imports, parameter handling, and output paths before considering it production-ready.
- Expand tests and tighten the OmicsClaw output contract in follow-up edits.
\"\"\"

    result = {{
        "ok": True,
        "status": "promoted_from_autonomous_analysis",
        "skill": SKILL_NAME,
        "domain": DOMAIN,
        "input": effective_input,
        "source_analysis_dir": SOURCE_ANALYSIS_DIR,
        "source_notebook": SOURCE_NOTEBOOK,
        "summary": SUMMARY,
    }}

    _write_text(skill_output_dir / "README.md", readme)
    _write_text(skill_output_dir / "report.md", report)
    _write_text(
        skill_output_dir / "reproducibility" / "commands.sh",
        f"oc run {{SKILL_NAME}} --output {{skill_output_dir}}\\n",
    )
    (skill_output_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Promoted skill '{{SKILL_NAME}}' completed. Outputs written to {{skill_output_dir}}")


if __name__ == "__main__":
    main()
"""


def render_skill_test(skill_name: str) -> str:
    script_name = f"{skill_name.replace('-', '_')}.py"
    return f"""from pathlib import Path


def test_scaffold_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "SKILL.md").exists()
    assert (root / "{script_name}").exists()
"""


def _skill_scaffold_requirements(
    *,
    script_name: str,
    create_tests: bool,
    reference_paths: Iterable[str] | None = None,
) -> list[ArtifactRequirement]:
    requirements = [
        ArtifactRequirement(
            name="skill_markdown",
            path="SKILL.md",
            description="Generated skill contract markdown.",
        ),
        ArtifactRequirement(
            name="skill_script",
            path=script_name,
            description="Generated skill entrypoint.",
        ),
        ArtifactRequirement(
            name="scaffold_spec",
            path="scaffold_spec.json",
            description="Structured scaffold specification.",
        ),
        ArtifactRequirement(
            name="workspace_manifest",
            path="manifest.json",
            description="Workspace lineage and verification ledger.",
        ),
    ]
    if create_tests:
        requirements.append(
            ArtifactRequirement(
                name="test_stub",
                path=f"tests/test_{script_name}",
                description="Generated smoke-test stub.",
            )
        )
    for rel_path in _unique(reference_paths or []):
        requirements.append(
            ArtifactRequirement(
                name=Path(rel_path).stem,
                path=rel_path,
                description="Reference artifact copied from the promoted autonomous analysis.",
            )
        )
    return requirements


def _load_completion_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_notebook(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_autonomous_bundle(path: Path) -> AutonomousAnalysisBundle:
    completion_path = path / COMPLETION_REPORT_FILENAME
    if completion_path.exists():
        completion = _load_completion_report(completion_path)
        if not bool(completion.get("completed", False)):
            status = str(completion.get("status", "")).strip() or "incomplete"
            raise ValueError(
                f"Autonomous analysis at {path} is not promotable yet (completion status: {status})."
            )

    notebook_path = path / "reproducibility" / "analysis_notebook.ipynb"
    plan_path = path / "analysis_plan.md"
    summary_path = path / "result_summary.md"
    sources_path = path / "web_sources.md"
    capability_path = path / "capability_decision.json"

    if not notebook_path.exists():
        raise FileNotFoundError(f"Autonomous analysis notebook not found: {notebook_path}")

    notebook = _load_notebook(notebook_path)
    code_cells = []
    goal = ""
    context = ""
    input_file = ""
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        if "AUTONOMOUS_OUTPUT_DIR" in source and "ANALYSIS_GOAL" in source:
            extracted = _extract_setup_literals(source)
            goal = extracted.get("ANALYSIS_GOAL", "")
            context = extracted.get("ANALYSIS_CONTEXT", "")
            input_file = extracted.get("INPUT_FILE", "")
            continue
        code_cells.append(source.rstrip())

    if not code_cells:
        raise ValueError(f"No executable analysis code found in notebook: {notebook_path}")

    capability = {}
    if capability_path.exists():
        capability = json.loads(capability_path.read_text(encoding="utf-8"))

    return AutonomousAnalysisBundle(
        source_dir=str(path),
        notebook_path=str(notebook_path),
        analysis_plan=plan_path.read_text(encoding="utf-8") if plan_path.exists() else "",
        result_summary=summary_path.read_text(encoding="utf-8") if summary_path.exists() else "",
        web_sources=sources_path.read_text(encoding="utf-8") if sources_path.exists() else "",
        capability_decision=capability,
        python_code="\n\n".join(code_cells).strip() + "\n",
        goal=goal,
        domain=str(capability.get("domain", "") or ""),
        input_file=input_file,
        context=context,
    )


def _extract_setup_literals(source: str) -> dict[str, str]:
    values: dict[str, str] = {}
    tree = ast.parse(source)
    wanted = {"ANALYSIS_GOAL", "ANALYSIS_CONTEXT", "WEB_CONTEXT", "INPUT_FILE", "AUTONOMOUS_OUTPUT_DIR"}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in wanted:
            continue
        try:
            values[name] = ast.literal_eval(node.value)
        except Exception:
            continue
    return values


def _normalize_promoted_code(code: str, source_dir: str) -> str:
    normalized = code or ""
    if source_dir:
        normalized = normalized.replace(str(source_dir), "AUTONOMOUS_OUTPUT_DIR")
    return normalized.rstrip() + "\n"


def find_latest_autonomous_analysis(output_root: Path | None = None) -> Path | None:
    root = Path(output_root or OUTPUT_DIR)
    if not root.exists():
        return None

    candidates: list[tuple[float, Path]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        completion_path = child / COMPLETION_REPORT_FILENAME
        if completion_path.exists():
            try:
                completion = _load_completion_report(completion_path)
            except json.JSONDecodeError:
                continue
            if not bool(completion.get("completed", False)):
                continue
        notebook_path = child / "reproducibility" / "analysis_notebook.ipynb"
        plan_path = child / "analysis_plan.md"
        summary_path = child / "result_summary.md"
        if notebook_path.exists() and plan_path.exists() and summary_path.exists():
            latest_ts = max(
                notebook_path.stat().st_mtime,
                plan_path.stat().st_mtime,
                summary_path.stat().st_mtime,
                child.stat().st_mtime,
            )
            candidates.append((latest_ts, child))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])[1]


def refresh_registry() -> bool:
    try:
        from omicsclaw.core.registry import registry

        registry._loaded = False
        registry.skills.clear()
        registry.lazy_skills.clear()
        registry.load_all()
        return True
    except Exception:
        return False


def create_skill_scaffold(
    *,
    request: str,
    domain: str,
    skill_name: str = "",
    summary: str = "",
    input_formats: Iterable[str] | None = None,
    primary_outputs: Iterable[str] | None = None,
    methods: Iterable[str] | None = None,
    trigger_keywords: Iterable[str] | None = None,
    create_tests: bool = True,
    skills_root: Path | None = None,
    source_analysis_dir: Path | str | None = None,
    promote_from_latest: bool = False,
    output_root: Path | None = None,
) -> SkillScaffoldResult:
    hook_runtime = build_default_lifecycle_hook_runtime(OMICSCLAW_DIR)
    source_bundle: AutonomousAnalysisBundle | None = None
    resolved_source_dir: Path | None = None
    if source_analysis_dir:
        resolved_source_dir = Path(source_analysis_dir)
        if not resolved_source_dir.is_absolute():
            resolved_source_dir = (OMICSCLAW_DIR / resolved_source_dir).resolve()
    elif promote_from_latest:
        resolved_source_dir = find_latest_autonomous_analysis(output_root=output_root)
        if resolved_source_dir is None:
            raise FileNotFoundError("No autonomous analysis output was found to promote.")

    if resolved_source_dir is not None:
        source_bundle = _load_autonomous_bundle(resolved_source_dir)

    domain = (domain or source_bundle.domain if source_bundle else domain or "").strip().lower()
    if not domain:
        raise ValueError("A target domain is required when it cannot be inferred from the source analysis.")
    if domain not in VALID_DOMAINS:
        raise ValueError(f"Unsupported domain: {domain}")

    resolved_root = Path(skills_root or SKILLS_DIR)
    if not resolved_root.is_absolute():
        resolved_root = (OMICSCLAW_DIR / resolved_root).resolve()
    target_root = resolved_root / domain
    target_root.mkdir(parents=True, exist_ok=True)

    resolved_skill_name = infer_skill_name(request, domain, preferred_name=skill_name)
    final_skill_dir = target_root / resolved_skill_name
    if final_skill_dir.exists():
        raise FileExistsError(f"Skill directory already exists: {final_skill_dir}")

    script_name = f"{resolved_skill_name.replace('-', '_')}.py"
    spec_payload = {
        "request": request,
        "summary": summary,
        "skill_name": resolved_skill_name,
        "domain": domain,
        "methods": _unique(methods or []),
        "input_formats": _unique(input_formats or []),
        "primary_outputs": _unique(primary_outputs or []),
        "trigger_keywords": _unique(trigger_keywords or []),
        "template_path": str(SKILL_TEMPLATE_PATH),
        "source_analysis_dir": str(resolved_source_dir) if resolved_source_dir else "",
        "promoted_from_autonomous_analysis": bool(source_bundle),
    }
    manifest_metadata = {
        "domain": domain,
        "skill_name": resolved_skill_name,
        "request": request,
        "promoted_from_autonomous_analysis": bool(source_bundle),
        "source_analysis_dir": str(resolved_source_dir) if resolved_source_dir else "",
    }
    relative_created_paths: list[Path] = []
    manifest_path = final_skill_dir / "manifest.json"
    completion_report_path = final_skill_dir / COMPLETION_REPORT_FILENAME

    with isolated_workspace(STAGING_ROOT, prefix="skill-scaffold") as staging_root:
        skill_dir = staging_root / resolved_skill_name
        skill_dir.mkdir(parents=True, exist_ok=False)

        skill_md_path = skill_dir / "SKILL.md"
        script_path = skill_dir / script_name
        spec_path = skill_dir / "scaffold_spec.json"
        test_path = skill_dir / "tests" / f"test_{script_name}"

        skill_md_path.write_text(
            render_skill_markdown(
                skill_name=resolved_skill_name,
                domain=domain,
                summary=summary or (source_bundle.goal if source_bundle else ""),
                request=request or (source_bundle.goal if source_bundle else ""),
                methods=methods or [],
                input_formats=input_formats or [],
                primary_outputs=primary_outputs or [],
                trigger_keywords=trigger_keywords or [],
                source_bundle=source_bundle,
            ),
            encoding="utf-8",
        )
        relative_created_paths.append(Path("SKILL.md"))

        if source_bundle is not None:
            script_path.write_text(
                render_promoted_skill_script(
                    skill_name=resolved_skill_name,
                    domain=domain,
                    summary=summary or source_bundle.goal,
                    source_bundle=source_bundle,
                ),
                encoding="utf-8",
            )
        else:
            script_path.write_text(
                render_skill_script(
                    skill_name=resolved_skill_name,
                    domain=domain,
                    summary=summary,
                    methods=methods or [],
                ),
                encoding="utf-8",
            )
        relative_created_paths.append(Path(script_name))

        if create_tests:
            test_path.parent.mkdir(parents=True, exist_ok=True)
            (test_path.parent / "__init__.py").write_text("", encoding="utf-8")
            test_path.write_text(render_skill_test(resolved_skill_name), encoding="utf-8")
            relative_created_paths.extend(
                [
                    Path("tests") / "__init__.py",
                    Path("tests") / f"test_{script_name}",
                ]
            )

        reference_relative_paths: list[str] = []
        if source_bundle is not None:
            references_dir = skill_dir / "references"
            references_dir.mkdir(parents=True, exist_ok=True)
            reference_targets = {
                "source_analysis_notebook.ipynb": Path(source_bundle.notebook_path),
                "source_result_summary.md": resolved_source_dir / "result_summary.md",
                "source_analysis_plan.md": resolved_source_dir / "analysis_plan.md",
                "source_web_sources.md": resolved_source_dir / "web_sources.md",
                "source_manifest.json": resolved_source_dir / "manifest.json",
                "source_completion_report.json": resolved_source_dir / COMPLETION_REPORT_FILENAME,
            }
            for filename, source_path in reference_targets.items():
                if source_path.exists():
                    dest = references_dir / filename
                    shutil.copy2(source_path, dest)
                    rel_path = Path("references") / filename
                    reference_relative_paths.append(str(rel_path))
                    relative_created_paths.append(rel_path)

        spec_path.write_text(
            json.dumps(spec_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        relative_created_paths.append(Path("scaffold_spec.json"))

        requirements = _skill_scaffold_requirements(
            script_name=script_name,
            create_tests=create_tests,
            reference_paths=reference_relative_paths,
        )
        staged_manifest_path = update_workspace_manifest(
            skill_dir,
            workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
            workspace_purpose=(
                "skill_promotion"
                if source_bundle is not None
                else "skill_scaffold"
            ),
            requirements=requirements,
            step=StepRecord(
                skill="create_omics_skill",
                version=SKILL_SCAFFOLDER_VERSION,
                input_file=str(resolved_source_dir) if resolved_source_dir else request,
                output_file=str(final_skill_dir),
                params={
                    "domain": domain,
                    "skill_name": resolved_skill_name,
                    "create_tests": create_tests,
                    "promoted_from_autonomous_analysis": bool(source_bundle),
                },
            ),
            isolation_mode="staging_copy",
            metadata=manifest_metadata,
        )
        relative_created_paths.append(Path("manifest.json"))

        completion_report = build_completion_report(
            skill_dir,
            workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
            workspace_purpose=(
                "skill_promotion"
                if source_bundle is not None
                else "skill_scaffold"
            ),
            requirements=requirements,
            manifest_path=str(staged_manifest_path),
            metadata=manifest_metadata,
        )
        if not completion_report.completed:
            raise RuntimeError(
                "Skill scaffold verification failed.\n"
                + format_completion_summary(completion_report)
            )
        write_completion_report(
            skill_dir,
            completion_report,
            hook_runtime=hook_runtime,
            hook_context={
                "workspace": str(skill_dir),
                "source": "skill_scaffolder",
            },
        )
        update_workspace_manifest(
            skill_dir,
            workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
            workspace_purpose=(
                "skill_promotion"
                if source_bundle is not None
                else "skill_scaffold"
            ),
            requirements=requirements,
            completion_report=completion_report,
            isolation_mode="staging_copy",
            metadata=manifest_metadata,
            append_step=False,
        )
        relative_created_paths.append(Path(COMPLETION_REPORT_FILENAME))

        shutil.move(str(skill_dir), str(final_skill_dir))

    created_files = [str(final_skill_dir / rel_path) for rel_path in relative_created_paths]

    refreshed = False
    if resolved_root.resolve() == SKILLS_DIR.resolve():
        refreshed = refresh_registry()

    return SkillScaffoldResult(
        skill_name=resolved_skill_name,
        domain=domain,
        skill_dir=str(final_skill_dir),
        script_path=str(final_skill_dir / script_name),
        skill_md_path=str(final_skill_dir / "SKILL.md"),
        test_path=str(final_skill_dir / "tests" / f"test_{script_name}" if create_tests else ""),
        spec_path=str(final_skill_dir / "scaffold_spec.json"),
        manifest_path=str(manifest_path),
        completion_report_path=str(completion_report_path),
        completion=completion_report.to_dict(),
        created_files=created_files,
        registry_refreshed=refreshed,
    )


__all__ = [
    "AutonomousAnalysisBundle",
    "SKILL_TEMPLATE_PATH",
    "SKILLS_DIR",
    "VALID_DOMAINS",
    "SkillScaffoldResult",
    "create_skill_scaffold",
    "find_latest_autonomous_analysis",
    "infer_skill_name",
    "refresh_registry",
    "slugify_skill_name",
]
