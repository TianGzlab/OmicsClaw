---
name: replace-me-skill
description: Load when copying this directory to bootstrap a new OmicsClaw skill. Skip when an existing skill already covers the request.
trigger: scaffold skill, new skill, skill template
tags:
- template
- scaffold
---

<!--
Authoring checklist (delete this comment block before committing):

  1. Copy: `cp -r templates/skill skills/<domain>/<my-new-skill>`, then
     `mv replace_me.py <my_new_skill>.py` and rename the tests/ file.
     The folder name must equal the frontmatter `name`: `load_skill` finds
     skills by folder name.
  2. Write the frontmatter above by hand. It is the ONLY metadata the agent
     sees, and `omicsclaw/skills/` reads exactly four keys:

       name         required, unique across all skills. A duplicate is
                    skipped, not merged. This is what `use_skill` and
                    `load_skill` are called with.
       description  required. The one line the model routes on, and the
                    only thing about this skill in the system prompt. Say
                    when to LOAD it and when to SKIP it, naming the skill
                    to use instead — the skip half is what prevents a
                    wrong choice.
       trigger      optional, comma-separated. Discovery keywords for
                    `/skills <query>`. It does NOT auto-fire the skill.
       tags         optional. Also only `/skills <query>`.

     Anything else is inert: it is neither read nor validated.
  3. Put the computations in `_api.py` (rules in `templates/skill/README.md`),
     then regenerate the `## API` section:
       python skills/_sdk/notebook/run.py api skills/<domain>/<my-new-skill> --write
     A test compares it with `_api.py` on every run.
  4. Write the other sections and the `references/*.md` stubs by hand.
  5. Make `examples/example_step.py` load a registered demo dataset with
     `load_demo`, call the library and assert on the result.
  6. Verify it is indexed, then refresh the domain index:
       python -c "from omicsclaw.skills import load_skills; \
         i = load_skills('skills'); print(len(i), i.skipped)"
       OMICSCLAW_WRITE_SKILL_INDEX=1 pytest \
         tests/skills/test_domain_index_is_current.py
       pytest tests/sdk/notebook/test_skill_api_sections.py

Full usage notes and soft conventions live in `templates/skill/README.md`.
-->

# REPLACE_SKILL_NAME

## When to use

<!--
One short paragraph (3-6 lines). Mirror the frontmatter description's
load/skip split and explicitly call out the closest adjacent skill so the
agent knows when to redirect.
-->

The user has `<input shape>` and wants `<output shape>`.  Pick this skill
when `<distinguishing condition>`.  For `<adjacent capability>` use
`<sibling-skill>` instead.

## Use from a step

```python
library = load_skill("REPLACE_SKILL_NAME")
frame = read_input("data/<input>.csv")
write_output(library.run_method(frame, method="default"), "tables/replace_me.csv")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `run_method(frame: pd.DataFrame, *, method: str='default') -> pd.DataFrame`

Placeholder computation: return a copy of the table with a ``method`` column.

:param frame: The input table.
:param method: The backend to run. Default ``"default"``, the only one so far;
    say here where each default comes from and when to change it.
:returns: A new DataFrame: *frame* plus a ``method`` column.
:raises ValueError: *method* is not one of ``METHODS``.

<!-- api:end -->

## Methods and parameters

<!--
Which method when. For every default: its value and where it comes from
(the method's paper, the library's default, a lab convention). Which values
the user should decide, and how to ask.
-->

- `method="default"`: the only backend so far.

## Gotchas

<!--
The failure modes an agent hits, each with the fix. Anchor each to something
grep-able: a function name, a quoted error message, a column or key.
-->

- _None yet — append as failure modes are reported._

## Inputs and outputs

<!--
What each function reads (columns, obs/obsm/layers keys) and what it writes
or returns.
-->

- `run_method` reads a table and returns a new one with a `method` column.

## CLI

`replace_me.py` runs the same functions outside a project and writes
`tables/replace_me.csv`, `report.md` and `result.json`:
`python <skill directory>/replace_me.py --help`. `--demo` synthesises its input.

## Dependencies

Python packages this skill's script needs. They are not installed for you
— check before a long run.

`<package-a>`, `<package-b>`

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — the WHY behind the algorithm
- `references/output_contract.md` — `tables/X.csv` + `result.json` schema
- Adjacent skills: `<sibling-1>` (upstream), `<sibling-2>` (parallel), `<sibling-3>` (downstream)
