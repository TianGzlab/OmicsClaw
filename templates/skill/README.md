# OmicsClaw Skill Template

This directory is a **human-copy starter** for new OmicsClaw skills. It is not
read by codegen.

The goal: `cp -r` this directory into the right `skills/<domain>/` location,
rename the placeholders, and you should be ~80% of the way to a gold-standard
skill like `skills/singlecell/scrna/sc-de` or `skills/spatial/spatial-de`.

## The layout

A skill is an independent subdirectory holding a `SKILL.md` and whatever it
needs beside it. That is the whole contract:

```
skills/<domain>/<skill>/
├── SKILL.md                  the only metadata there is; hand-written except the ## API section
├── _api.py                   the function library steps load with load_skill("<skill>")
├── <skill>.py                the CLI: a thin shell over _api.py, run directly with python
├── examples/example_step.py  a runnable step on demo data
├── references/               detail the body links to, read on demand
└── tests/
```

**`SKILL.md` is the single source of truth.** Its frontmatter is what the
agent is indexed by and its body is what `use_skill` returns. One part is
generated: the `## API` section between the `api:begin` and `api:end`
markers, rendered from `_api.py`'s signatures and docstrings with

```bash
python skills/_sdk/notebook/run.py api skills/<domain>/<skill> --write   # --check to verify
```

`tests/sdk/notebook/test_skill_api_sections.py` fails when the section and
`_api.py` disagree, so edit the docstring and regenerate rather than editing
the section.

## The function library, `_api.py`

The agent writes analysis steps in a project and calls the skill from them:
`library = load_skill("<skill>")`, then `library.<function>(...)`. Only the
names in `__all__` are reachable, and every call is recorded in the step's
ledger. The leading underscore keeps the file out of the guards that count
main scripts. The rules:

- Compute only. No file reads or writes, no logging configuration, no global
  state: steps read with `read_input` and write with `write_output`, and the
  CLI does its own I/O. A method that needs temporary files for R makes them
  with `tempfile` inside the function.
- The first parameter is the data object (`adata` for single-cell); every
  other parameter is keyword-only, with the CLI's default. A function that
  modifies an AnnData does it in place and returns the same object (say so
  when it returns a new one). Tables are `DataFrame`s, figures matplotlib
  `Figure`s. Random processes take an explicit `random_state`.
- Diagnostics a run produces (what was filtered, which matrix was used, a
  fallback) go into `adata.uns` as a JSON string, read back by a public
  `run_info(adata, *, keep=True)`; the CLI calls it with `keep=False` so
  `processed.h5ad` is unchanged.
- `__all__` lists every public function. Each has a docstring: a first line
  saying what it does; `:param name:` for each parameter with its meaning,
  where the default comes from and when to change it; `:returns:` and
  `:raises:`.
- Import the domain `_lib` and `skills._sdk` only: never `omicsclaw`, never
  another skill.
- The CLI script loads its own library with `load_skill(SKILL_NAME)` inside
  `main()` and keeps argparse, the report, the figure gallery and
  `result.json`. The template's `replace_me.py` finds its library by folder
  name instead, so it also runs from `templates/skill/`.
- When a CLI becomes a thin shell, record its outputs first and compare after
  (`tests/parity/snapshot.py`), so the move changes no result.

Four frontmatter keys are read, and only four:

| Key | Required | Read by |
|---|---|---|
| `name` | yes | the prompt index, `use_skill` |
| `description` | yes | the prompt index — the one line the model routes on |
| `trigger` | no | `/skills <query>` search only; never auto-fires a skill |
| `tags` | no | `/skills <query>` search only |

A header missing `name` or `description` is skipped and never indexed.
Anything else in the header is inert.

## Bootstrap steps

```bash
# 1. Copy and rename
cp -r templates/skill skills/<domain>/<my-new-skill>
cd skills/<domain>/<my-new-skill>
mv replace_me.py <my_new_skill>.py
mv tests/test_replace_me.py tests/test_<my_new_skill>.py

# 2. Edit the placeholders
#    - SKILL.md            frontmatter (name / description / trigger / tags)
#                          AND the body. This is the only metadata.
#    - _api.py             the computations, then regenerate ## API:
#                          python <checkout>/skills/_sdk/notebook/run.py api . --write
#    - <my_new_skill>.py   replace the synthetic-CSV demo with real I/O
#    - examples/example_step.py   a step on a load_demo dataset
#    - references/*.md     fill in methodology / output contract / parameters

# 3. Verify it is indexed, with nothing skipped
python -c "from omicsclaw.skills import load_skills; \
  i = load_skills('skills'); print(len(i), i.skipped)"

# 4. Refresh the domain index and run the suites
OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py
python <my_new_skill>.py --demo --output /tmp/<my-new-skill>_demo
pytest tests/
```

Then add the routing-table row in `OMICSCLAW.md` by hand, and the skill's
`tests/` path to `pyproject.toml`'s `testpaths` if it should run in the
default suite.

## Conventions the lint used to enforce

`scripts/skill_lint.py` was deleted with the rest of the retired toolchain,
so none of the following is checked mechanically any more. They are still
what every gold skill does, and they are still the bar for review:

| Surface | Convention |
|---|---|
| `description` | Says when to LOAD and when to SKIP, naming the skill to use instead. The skip half is what prevents a wrong choice, and it is the half a one-line parser used to drop. |
| `name` | Unique across all skills. A duplicate is skipped by the loader, not merged — check with the `load_skills` one-liner above. |
| `SKILL.md` body | ≤ 200 lines; a skill with `_api.py` contains `## When to use`, `## Use from a step`, `## API`, `## Methods and parameters`, `## Gotchas`, `## Inputs and outputs`, `## CLI`, `## See also`, `## Dependencies`; a CLI-only skill keeps `## Inputs & Outputs`, `## Flow` and `## Key CLI` in place of the step, API and CLI sections |
| `SKILL.md` Gotchas | Each non-empty bullet anchors to a function/constant name or quoted error message in the script, a `result.json["key"]`, or a `tables/`/`figures/` filename the script actually writes — not a line number |
| `SKILL.md` Key CLI | For a CLI-only skill, spells the real `python skills/<domain>/<skill>/<script>.py` invocation. There is no `oc run`; steps call such a skill with `run_cli("<skill>", ...)`. |
| `references/` | Contains `methodology.md`, `output_contract.md`, `parameters.md` |
| `references/output_contract.md` | Every `tables/X.csv` / `figures/X.png` it mentions appears as a substring in the script (or a sibling `_lib/*.py` it imports) |

## Soft conventions (not lint-enforced, but every gold skill does this)

### Shared helpers live in `skills/<domain>/_lib/`

When two skills in the same domain need the same utility (matrix-contract
validation, pseudobulk aggregation, gallery rendering, …), put it under
`skills/<domain>/_lib/` and import via `from skills.<domain>._lib.<module>`.
Do **not** put helpers under the skill's own directory unless they are
genuinely single-use.

The template is domain-agnostic and cannot scaffold this for you — see the
existing `skills/singlecell/_lib/` and `skills/spatial/_lib/` for shape.

### Real demo data lives in `data/`

The template's `replace_me.py` synthesises its demo in memory because that
keeps the template domain-agnostic and avoids committing binary fixtures.
When your skill needs a real demo (e.g. a small h5ad, a tiny VCF), drop it
under `<skill>/data/` and load it from `--demo`. See
`skills/singlecell/scrna/sc-de/data/pbmc3k_processed.h5ad` for shape.

### Optional R Enhanced visualisation layer

OmicsClaw has a three-tier visualisation flow: Python standard figures → R
Enhanced figures → parameter tuning. The R layer is opt-in. **Re-rendering
is currently unavailable**: the `replot` command lived in the retired CLI, so
today the only way to refresh a figure is to re-run the skill. If your skill exports `figure_data/*.csv` payloads and you want a
publication-quality R renderer, add:

```
<skill>/r_visualization/
├── <name>_publication_template.R   # consumes figure_data/, writes figures/r_enhanced/
└── README.md                       # input contract + renderer list
```

See `skills/spatial/spatial-de/r_visualization/` for shape. The template
deliberately does not scaffold this directory — leave
`references/r_visualization.md` as-is until you actually add a renderer.

## Reference skills

When in doubt, read these end-to-end:

- `skills/singlecell/scrna/sc-de/` — multi-method DE, AnnData I/O,
  pseudobulk path, R renderers.
- `skills/spatial/spatial-de/` — same DE problem in the spatial modality,
  illustrates the cross-domain shape.
