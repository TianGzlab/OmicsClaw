# Contributing to OmicsClaw

We welcome contributions from anyone working in multi-omics analysis, bioinformatics, computational biology, or related fields.

---

## How to Contribute a Skill

### Overview

OmicsClaw uses **convention-over-configuration** for skill discovery. Place your files in the correct directory with the correct naming, and the system automatically handles registry, CLI, bot routing, and agent integration — no manual wiring needed.

```
skills/<domain>/<skill-name>/
├── SKILL.md              # Required — metadata + documentation
├── <skill_name>.py       # Required — entry script (hyphens → underscores)
└── tests/
    └── test_<skill_name>.py  # Required — at least demo mode test
```

### Step 1: Create the directory

```bash
# Pick your domain: spatial, singlecell, genomics, proteomics, metabolomics, bulkrna
mkdir -p skills/<domain>/<skill-name>/tests
```

**Naming rules:**
- Folder: lowercase, hyphens (`spatial-de`, `bulkrna-enrichment`)
- Script: folder name with hyphens replaced by underscores (`spatial_de.py`, `bulkrna_enrichment.py`)
- The script filename **must** match the folder name — this is how the registry finds it

Subdomain nesting is also supported (e.g., `singlecell/scrna/sc-qc/sc_qc.py`).

### Step 2: Write SKILL.md

Copy and customize the template:

```bash
cp templates/SKILL-TEMPLATE.md skills/<domain>/<skill-name>/SKILL.md
```

**Required YAML frontmatter fields:**

```yaml
---
name: your-skill-name              # Must match folder name
description: >-
  One-line description shown in CLI and skill_search results.
version: 0.1.0
metadata:
  omicsclaw:
    domain: spatial                 # Your domain
    trigger_keywords:               # How users find this skill via NLP
      - preprocess
      - QC
      - normalize
    allowed_extra_flags:            # CLI flags beyond --input/--output/--demo
      - "--method"
      - "--species"
    legacy_aliases: [short-alias]   # Optional short names
    saves_h5ad: false               # Does output include processed.h5ad?
    requires_preprocessed: false    # Needs preprocessed input?
---
```

**Required markdown sections:** Why This Exists, Core Capabilities, Workflow, Input/Output Formats, CLI Reference (with `--demo` example), Dependencies, Safety disclaimer.

### Step 3: Implement the script

Your script needs three things: a `main()` CLI entry, demo mode support, and standard output files.

```python
#!/usr/bin/env python3
"""One-line description of the skill."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root on sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Import core analysis functions from _lib (recommended for complex skills)
from skills.<domain>._lib.<module> import core_function

# Import report utilities
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Create analysis visualizations."""
    ...


def write_report(output_dir: Path, summary: dict, input_file, params: dict) -> None:
    """Generate report.md + result.json."""
    ...


def get_demo_data():
    """Return synthetic demo data."""
    ...


def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    # Add flags declared in SKILL.md allowed_extra_flags
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data = get_demo_data()
    elif args.input_path:
        data = load_data(args.input_path)
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Run analysis → generate output
    summary = core_function(data, ...)
    generate_figures(output_dir, summary)
    write_report(output_dir, summary, args.input_path, vars(args))


if __name__ == "__main__":
    main()
```

**Standard output files** (in `--output` directory):

| File | Purpose |
|------|---------|
| `report.md` | Analysis report with methodology, results, disclaimer |
| `result.json` | Structured results for programmatic access |
| `figures/` | PNG/SVG visualizations |
| `tables/` | CSV/TSV data tables |
| `reproducibility/` | commands.sh, requirements.txt, checksums.sha256 |
| `processed.h5ad` | Output AnnData (if `saves_h5ad: true`) |

### Step 4: (Recommended) Use `_lib` for core logic

For complex skills, put core analysis functions in a shared `_lib/` module:

```
skills/<domain>/_lib/
    ├── __init__.py
    └── your_module.py    # run_analysis(), compute_metrics(), ...
```

Then import at the top level of your script:

```python
from skills.<domain>._lib.your_module import run_analysis
```

**Why this matters:** The `skill_search()` tool (used by the research pipeline's coding-agent) performs AST scanning to discover callable functions. It specifically extracts functions imported from `_lib` and marks them as **core functions** (`▶`), displayed prominently to the coding-agent. Functions defined directly in your script are shown as helpers.

If your domain doesn't have `_lib` yet, that's fine — all functions defined in your script will still be discovered and shown to agents.

### Step 5: Write tests

```python
# tests/test_<skill_name>.py
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "<skill_name>.py"

def test_demo_mode(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--demo", "--output", str(tmp_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "result.json").exists()
```

### Step 6: Verify integration

```bash
# 1. Registry discovers your skill
python omicsclaw.py list | grep <skill-name>

# 2. Demo mode works
python omicsclaw.py run <skill-name> --demo --output /tmp/test_output

# 3. Tests pass
python -m pytest skills/<domain>/<skill-name>/tests/ -v
```

### Step 7: Submit

```bash
git checkout -b add-<skill-name>
git add skills/<domain>/<skill-name>/
git commit -m "feat(<domain>): add <skill-name> skill"
git push -u origin add-<skill-name>
# Open PR on GitHub
```

---

## How Auto-Discovery Works

You don't need to register your skill anywhere. The system discovers it automatically:

```
You create files                          System does the rest
─────────────────                         ────────────────────
skills/<domain>/<name>/                 → registry.load_all() discovers the directory
    SKILL.md (with frontmatter)         → LazySkillMetadata parses trigger_keywords, domain, flags
    <name>.py (with main())             → registry.skills[alias] = {script, domain, description, ...}
                                          │
                                          ├→ CLI: `omicsclaw.py run <name>` works
                                          ├→ Bot: NLP routing via trigger_keywords
                                          ├→ skill_search(): AST extracts functions for coding-agent
                                          └→ load_skill(): dynamic import in notebook kernel
```

---

## Skill Guidelines

1. **Local-first**: All data processing happens locally. No mandatory cloud uploads.
2. **Reproducible**: Generate reports with version info and run commands.
3. **Single responsibility**: Each skill does one analysis task well.
4. **Documented**: SKILL.md with methodology, examples, and safety disclaimer.
5. **Standardized output**: Follow the output structure (report.md, result.json, figures/).
6. **Demo mode**: `--demo` must work without `--input` — essential for testing and user onboarding.

## Code Standards

- Python 3.11+
- Type hints encouraged
- Use `pathlib` for file paths
- No hardcoded absolute paths
- Tests with pytest
- Follow existing skill patterns (read 2-3 skills in the same domain before starting)

## Supported Domains

For an always-current count, see the auto-generated sections in
[`CLAUDE.md`](CLAUDE.md) (between `<!-- ROUTING-TABLE-START -->` markers)
and [`skills/orchestrator/SKILL.md`](skills/orchestrator/SKILL.md).

| Domain | Directory |
|--------|-----------|
| Spatial Transcriptomics | `skills/spatial/` |
| Single-Cell Omics | `skills/singlecell/` |
| Genomics | `skills/genomics/` |
| Proteomics | `skills/proteomics/` |
| Metabolomics | `skills/metabolomics/` |
| Bulk RNA-seq | `skills/bulkrna/` |

### Keeping skill-derived docs in sync

After adding, renaming, or removing a skill (or editing SKILL.md frontmatter
that appears in routing tables), regenerate the derived docs so humans and
LLMs see consistent numbers:

```bash
python scripts/sync_skill_docs.py --apply     # regenerate all four
python scripts/sync_skill_docs.py --check     # CI-style drift check
```

This wraps four generators:
- `generate_routing_table.py` → `CLAUDE.md` routing table (compact 7-domain briefing)
- `generate_orchestrator_counts.py` → `skills/orchestrator/SKILL.md`
- `generate_catalog.py` → `skills/catalog.json`
- `generate_domain_index.py` → `skills/<domain>/INDEX.md` (lazy-load detail)

The `docs-consistency` CI job runs `--check` on every PR and will fail
if any of these files are stale.

### Routing-context token budget

The bot's LLM-facing tool registry ships with every turn. To prevent slow
growth, the repo pins a ceiling per-metric:

```bash
python scripts/measure_routing_tokens.py                 # report sizes
python scripts/measure_routing_tokens.py --save X.json   # snapshot
python scripts/check_routing_budget.py                   # fail if over ceiling
```

CI runs `check_routing_budget.py`. If you add a new bot tool or expand an
existing tool's description, the check may fail — in that case:

1. Run `measure_routing_tokens.py` locally and eyeball the diff vs
   `build/routing-baselines/after_stage4.json`.
2. If the new cost is justified, raise the relevant ceiling in
   `build/routing-baselines/ceiling.json` and explain why in the PR.
3. If the growth is accidental (forgot to trim a description), fix it.

See `docs/` and the Stage 2-4 refactor comments in `omicsclaw/runtime/`
for the 3-layer routing architecture (domain briefing → per-domain index →
chosen-skill prefetch) that keeps this budget achievable.

## For AI Agents Contributing Skills

AI coding agents should follow the same workflow, plus:

1. Read [`README.md`](README.md) first for project context on complex repository tasks
2. Read [`SPEC.md`](SPEC.md) for the repository maintenance and AI development contract
3. Read [`AGENTS.md`](AGENTS.md) for project structure and conventions
4. Read the target skill's `SKILL.md` before modifying code
5. Use the matching workflow playbooks in [`docs/superpowers/playbooks/`](docs/superpowers/playbooks/README.md) when debugging, planning, writing tests, verifying completion, parallelizing work, requesting code review, or finishing a branch
   Treat them as process constraints, not optional tips.
6. Use `python omicsclaw.py list` to verify skills load correctly
7. Run `python -m pytest -v` to confirm all tests pass
8. Update `README.md` if the work introduces an important decision, milestone, or lasting contributor workflow change

## Skill Ideas We Need

**Spatial Transcriptomics:** 3D tissue reconstruction, multi-slice alignment

**Single-Cell:** Multi-modal integration (RNA + ATAC + protein), rare cell type detection

**Genomics:** Long-read variant calling, population genetics analysis

**Proteomics:** DIA-NN integration, PTM site prediction

**Metabolomics:** Compound identification, flux balance analysis

**Multi-Omics:** Cross-omics integration, multi-view factor analysis

## Questions?

Open an issue on [GitHub](https://github.com/TianGzlab/OmicsClaw/issues) or check the documentation.
