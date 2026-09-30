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

`SKILL.md` is the **single source of truth** and is hand-written end to end.
There is no `skill.yaml` machine contract and no generator: both belonged to
the retired skill system and were deleted with it.

**The frontmatter.** `omicsclaw/skills/` reads exactly four keys; anything
else you put there is inert.

```markdown
---
name: my-new-skill
description: Load when <the one situation this skill is for>. Skip when <the
  case that belongs elsewhere> (use <other-skill>); <another> (use <other>).
trigger: keyword one, keyword two, keyword three
tags:
- domain
- method
---
```

| Key | Required | What reads it |
|---|---|---|
| `name` | **yes** | The prompt index and the `use_skill` tool. Must be unique across every skill — a duplicate is **skipped**, not merged. |
| `description` | **yes** | The prompt index. This single line is the only thing about your skill the model sees before it decides, so it is the highest-leverage text in the file. |
| `trigger` | no | `/skills <query>` search only. It does **not** auto-fire the skill. Comma-separated, or a YAML block sequence. |
| `tags` | no | `/skills <query>` search only. |

**Write the description as a load/skip pair.** "Load when …" tells the model
when to reach for it; "Skip when … (use `<other-skill>`)" is what stops a
wrong choice, and it is the more valuable half. Name the neighbour you are
deferring to — an unqualified "skip when this is not relevant" helps nobody.
Folded continuation lines are fine; the parser keeps them whole.

**The body** is what `use_skill` returns. Keep it under ~200 lines and give
it these sections:

| Section | What goes in it |
|---|---|
| `## When to use` | 3-6 lines mirroring the load/skip split, naming the closest adjacent skill |
| `## Inputs & Outputs` | What the script reads, and every file it writes, by path |
| `## Flow` | 3-7 numbered present-tense steps, anchored to `<script>.py:LINE` where it helps |
| `## Gotchas` | The highest-leverage section. Each bullet states the trap, anchors to a real code path or output filename, and says **why** it exists. Skip anything a competent reader would get right anyway. |
| `## Key CLI` | The real `python skills/<domain>/<skill>/<script>.py …` invocation. There is no `oc run`, and this is the only place anyone learns your flags. |
| `## Dependencies` | The Python packages your script needs. Nothing installs them; this is so an agent can check before a long run. |
| `## See also` | The `references/*.md` files and the adjacent skills |

Start from `templates/skill/SKILL.md`, which carries this checklist inline.


### Step 3: Implement the script

Your script needs three things: a `main()` CLI entry, demo mode support, and standard output files.

```python
#!/usr/bin/env python3
"""One-line description of the skill."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Put the checkout that provides skills/_sdk on sys.path (the same block in every
# skill script; with no such checkout above the file, PYTHONPATH decides)
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

# Import core analysis functions from _lib (recommended for complex skills)
from skills.<domain>._lib.<module> import core_function

# Import report utilities — skill code imports skills._sdk, never omicsclaw
from skills._sdk.report import generate_report_footer, generate_report_header
from skills._sdk.result import write_result_json


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

**Standard output files** (in `--output` directory; describe yours
exhaustively in `references/output_contract.md`; nothing verifies this
mechanically any more, so it is a review item):

| File | Purpose | Optional? |
|------|---------|---|
| `report.md` | Analysis report with methodology, results, disclaimer | always written |
| `result.json` | Standardised envelope (`summary` + `data`) for programmatic access | always written |
| `tables/<name>.csv` | CSV data tables | per skill |
| `figures/<name>.png` | PNG/SVG visualizations | only if your script uses matplotlib |
| `reproducibility/{commands.sh,requirements.txt,checksums.sha256}` | Replay artifacts | written by common report helper when applicable |
| `processed.h5ad` | Output AnnData | only if your script writes one; say so in `## Inputs & Outputs` |

Use `skills._sdk.result.write_result_json` instead of constructing an
ad-hoc payload. A zero-exit process with a missing, malformed, scaffold, or
contract-incomplete `result.json` is reported as `contract_failure`; its raw
output directory is retained for diagnosis, but runner-owned success guides
are not written.

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
# 1. The loader indexes it, and refuses nothing
python -c "from omicsclaw.skills import load_skills; \
  i = load_skills('skills'); print(len(i), i.skipped)"
make list | grep <skill-name>

# 2. Demo mode works, run the way the agent will run it
python skills/<domain>/<skill-name>/<skill_name>.py --demo --output /tmp/test_output

# 3. Tests pass
python -m pytest skills/<domain>/<skill-name>/tests/ -v

# 4. The domain index picks it up
OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py

# 5. The agent can reach it end to end
oc cli --prompt '<a request your skill should answer, naming it>'
```

Step 1 is the one that catches a malformed header: a `SKILL.md` missing
`name` or `description` is **skipped silently** by design, so a skill that
never appears is far more likely to be a frontmatter typo than a wiring
problem. `i.skipped` names the file and the reason.

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

You don't need to register your skill anywhere. `omicsclaw/skills/` walks
the tree at startup and indexes every `SKILL.md` it can parse:

```
You create files                          System does the rest
─────────────────                         ────────────────────
skills/<domain>/<name>/                 → load_skills() walks the tree recursively
    SKILL.md (frontmatter)              → header parsed; body left on disk
    <name>.py                           → nothing to register; the body names the path
                                          │
                                          ├→ System prompt: one `- name: description` line
                                          ├→ use_skill: the model fetches the body on demand,
                                          │             and gets the skill's directory with it
                                          └→ /skills <query>: matched on name, domain, tags, trigger
```

**Progressive disclosure is why the description matters so much.** The
bodies are ~124k tokens over 94 skills; the index is ~8.4k. Only the index
is in the prompt, so your `description:` is the entire basis on which the
model decides whether to open your skill at all.

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

### Test markers and CI

Plain `pytest` skips tests marked `slow`, `demo` and `eval`, and runs
the ones marked `scripted_eval`. Those are the scripted agent evals in
`tests/evals/dataset/`: the model's replies are written into each case,
so they need no API key and no network and finish in seconds. `eval` is
for tests that call a real model. They need a key, run by hand or
nightly, and never gate a PR.

The `Eval CI` workflow (`.github/workflows/eval.yml`) runs the framework
unit tests, then the scripted evals. A PR is green only when every hard
eval assertion passes; the step summary shows the pass rate and warnings
per category. Tests that already fail are listed in
`tests/ci_known_failures.txt` and run as strict xfail, so a fixed test
fails the run until you delete its entry.

## Supported Domains

For an always-current count, run `make list` — it reports what
`omicsclaw/skills/` actually indexed, and how many files it found and
refused. The routing table in [`OMICSCLAW.md`](OMICSCLAW.md) is maintained by hand.

| Domain | Directory |
|--------|-----------|
| Spatial Transcriptomics | `skills/spatial/` |
| Single-Cell Omics | `skills/singlecell/` |
| Genomics | `skills/genomics/` |
| Proteomics | `skills/proteomics/` |
| Metabolomics | `skills/metabolomics/` |
| Bulk RNA-seq | `skills/bulkrna/` |
| Literature | `skills/literature/` |

### Keeping skill-derived docs in sync

`SKILL.md` is the single source of truth. The generators that used to
write headers, catalogues and routing tables from a `skill.yaml` machine
contract were deleted with the old skill system, along with `skill.yaml`
itself — a generator nobody runs is how the domain indexes silently
rotted, so the one derived document left is guarded by a test instead:

```bash
# Check nothing drifted, and that the tree loads with nothing skipped
pytest tests/skills

# Regenerate skills/<domain>/INDEX.md after adding or editing a skill
OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py
# or: make skill-index
```

The routing table in `OMICSCLAW.md` is updated by hand; verify a count with
`find skills/<domain> -name SKILL.md | wc -l`.

### Keeping `## Dependencies` complete

A skill's `## Dependencies` section should list every Python package its
script needs — including optional backends reached transitively through
`_lib` (e.g. `cellrank` / `palantir` for `spatial-trajectory`).

These used to be a `requires:` frontmatter key, generated and checked by
`scripts/audit_skill_requires.py`. That script, the key and the `skill.yaml`
it read were deleted with the old skill system, so **the list is now
hand-maintained and nothing verifies it**. It is documentation for an agent
about to run your script, not an install manifest — nothing installs from
it, and a gap costs a confusing `ImportError` rather than a failed build.

**When you add an algorithm/backend to a skill:**
1. Register it in `DEPENDENCIES` in `skills/_sdk/deps.py`, keyed by its PyPI
   name as spelled in `## Dependencies`, with a pure-literal value:
   `module` (import name, or R package name), `kind` (`"pip"`, `"git"` or
   `"r"`), `install` (for `pip`, exactly `pip install <key> [<also>…]`) and
   `description`, plus optional `also` (extra PyPI names installed together)
   and `alt_env` (a conda env that also counts as available). It is the
   single source of truth for backend name mapping and is read by AST, so no
   calls or lambdas; see AGENTS.md.
2. Add it to the right `pyproject.toml` extra or `environment.yml` Tier 4.
3. Add it to your `SKILL.md`'s `## Dependencies` line.

### Keeping the prompt index small

Only `name` and `description` reach the system prompt, once per skill, on
every turn — about 8.4k tokens over 94 skills against ~124k for the bodies.
That ratio is the whole point of the design, and a description that grows
into a paragraph spends context on every conversation whether or not your
skill is used.

Keep it to one load/skip sentence pair. `make list` shows the compact
per-domain rendering; `python -c "from omicsclaw.skills import load_skills;
print(len(load_skills('skills').summary()))"` gives the index's exact size
if you want to see what an edit cost.

The old `measure_routing_tokens.py` / `check_routing_budget.py` pair that
pinned a ceiling here was deleted: it measured the retired bot tool registry
and its own helper module was already missing.


## For AI Agents Contributing Skills

AI coding agents should follow the same workflow, plus:

1. For complex repository tasks, read [`README.md`](README.md) for project context and [`CHANGELOG.md`](CHANGELOG.md) for recent decisions
2. Read [`SPEC.md`](SPEC.md) for the repository maintenance and AI development contract
3. Read [`AGENTS.md`](AGENTS.md) for project structure and conventions
4. Read the target skill's `SKILL.md` before modifying code
5. Use a concise plan, root-cause debugging, focused tests, and verification evidence for non-trivial repository changes.
6. Use `make list` to verify skills load correctly, and check `i.skipped` is empty
7. Run `python -m pytest -v` to confirm all tests pass
8. Add an entry at the top of [`CHANGELOG.md`](CHANGELOG.md) if the work introduces an important decision, milestone, or lasting contributor workflow change; change `README.md` only when a user-facing entry point, install step or headline feature changes, and keep its What's New to at most five items of one sentence each

## Skill Ideas We Need

**Spatial Transcriptomics:** 3D tissue reconstruction, multi-slice alignment

**Single-Cell:** Multi-modal integration (RNA + ATAC + protein), rare cell type detection

**Genomics:** Long-read variant calling, population genetics analysis

**Proteomics:** DIA-NN integration, PTM site prediction

**Metabolomics:** Compound identification, flux balance analysis

**Multi-Omics:** Cross-omics integration, multi-view factor analysis

## Questions?

Open an issue on [GitHub](https://github.com/TianGzlab/OmicsClaw/issues) or check the documentation.
