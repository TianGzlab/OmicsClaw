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
  2. Write the frontmatter above by hand. It is the ONLY metadata the agent
     sees, and `omicsclaw/skills/` reads exactly four keys:

       name         required, unique across all skills. A duplicate is
                    skipped, not merged. This is what `use_skill` is
                    called with; skills are not slash commands.
       description  required. The one line the model routes on, and the
                    only thing about this skill in the system prompt. Say
                    when to LOAD it and when to SKIP it, naming the skill
                    to use instead — the skip half is what prevents a
                    wrong choice.
       trigger      optional, comma-separated. Discovery keywords for
                    `/skills <query>`. It does NOT auto-fire the skill.
       tags         optional. Also only `/skills <query>`.

     Anything else is inert: it is neither read nor validated.
  3. Write the narrative sections below (When to use / Inputs & Outputs /
     Flow / Gotchas / Key CLI / Dependencies / See also) and the
     `references/*.md` stubs. Nothing here is generated — there is no
     generator, and the body is the whole of what `use_skill` returns.
  4. Implement: replace the synthetic-CSV demo in the script with real I/O.
  5. Verify it is indexed, then refresh the domain index:
       python -c "from omicsclaw.skills import load_skills; \
         i = load_skills('skills'); print(len(i), i.skipped)"
       OMICSCLAW_WRITE_SKILL_INDEX=1 pytest \
         tests/skills/test_domain_index_is_current.py
       pytest tests/

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

## Inputs & Outputs

<!--
Hand-written. List the files the script reads and every file it writes,
by the path it writes them to — an agent reporting results to a user
reads this to know what to open.
-->

**Inputs**

- `--input <data.ext>` — `<what it must contain>`
- `--demo` — synthesizes its own input instead

**Outputs**

- `tables/replace_me.csv`
- `report.md`
- `result.json`

## Flow

<!--
3-7 numbered steps, present-tense. Name the function or output file a step
lives in, never a line number: line numbers go stale on the next edit.
Don't recapitulate idiomatic Python.
-->

1. Load input (`--input <file>`) or generate a demo (`--demo`).
2. Validate required columns / `obs[X]` keys; raise `ValueError(...)` early.
3. Run the chosen `--method` backend.
4. Write `tables/<name>.csv` + `report.md` + `result.json`.

## Gotchas

<!--
Empirically the highest-leverage section.  Each bullet should:
  * State the trap in the lead sentence.
  * Anchor to something grep-able: a function or constant name, the quoted
    error message, a `result.json` key, or an output filename.
  * Explain WHY (the reason the trap exists), not just WHAT.

Skip obvious things — Python-101 advice or framework-standard behaviour.
The bar is "would the agent get this wrong without this instruction?".
-->

- _None yet — append as failure modes are reported._

## Key CLI

<!--
There is no `oc run`. A skill script is invoked directly, by a person or
by the agent through `bash`. Spell the real path — the agent learns this
skill's CLI from nowhere else.
-->

```bash
# Demo
python skills/<domain>/REPLACE_SKILL_NAME/replace_me.py \
  --demo --output /tmp/REPLACE_SKILL_NAME_demo

# Real input
python skills/<domain>/REPLACE_SKILL_NAME/replace_me.py \
  --input <data.ext> --output results/ \
  --method <method-name>
```

## Dependencies

Python packages this skill's script needs. They are not installed for you
— check before a long run.

`<package-a>`, `<package-b>`

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — the WHY behind the algorithm
- `references/output_contract.md` — `tables/X.csv` + `result.json` schema
- Adjacent skills: `<sibling-1>` (upstream), `<sibling-2>` (parallel), `<sibling-3>` (downstream)
