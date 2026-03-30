# OmicsClaw Skill Optimization Template

> **Status**: Detailed reusable summary for skill-by-skill optimization
> **Last Updated**: 2026-03-30
> **Applies To**: `skills/spatial/*` first, then other domains under `skills/`

## 1. This Document Is For

This document is the **detailed optimization summary** distilled from the recent
OmicsClaw skill upgrades. Its purpose is not to replace
[`templates/SKILL-TEMPLATE.md`](../templates/SKILL-TEMPLATE.md), but to provide
a **practical upgrade template** for taking an existing skill and turning it
into a cleaner, more accurate, more explainable, and more extensible OmicsClaw
skill.

In other words:

- `templates/SKILL-TEMPLATE.md` is the **new-skill scaffold**
- this document is the **existing-skill optimization playbook**

It is designed to be reused for:

- `skills/spatial/*`
- later `skills/singlecell/*`
- later `skills/genomics/*`
- later `skills/proteomics/*`
- later `skills/metabolomics/*`
- later `skills/bulkrna/*`

The core idea is to treat each skill as a **small but complete contract**, not
just a Python script.

## 2. What This Template Is Trying To Solve

The recent optimization work exposed the same recurring problems across many
skills:

- `SKILL.md` described methods too generically
- different methods inside one skill were given the same loose parameter story
- `allowed_extra_flags` was sometimes too broad or too blunt
- parameter hints were not always method-specific
- the wrapper code and `_lib` implementation could drift apart
- output folders were technically complete but not user-friendly
- conversational execution and `oc run` execution did not always produce the
  same level of reproducibility
- knowledge documents mixed together too many responsibilities
- adding a new method risked touching too many places in inconsistent ways

The optimization template is meant to standardize all of that.

Its goals are:

1. make the skill more understandable to users
2. make the method and parameter story more scientifically honest
3. make outputs easier to inspect and reproduce
4. make LLM guidance better aligned with the real wrapper
5. make future method expansion less painful

## 3. The Core Model: Six-Layer Optimization

The most useful way to understand the current optimization approach is as a
**six-layer model**. A skill is only "well optimized" when these six layers are
aligned.

### Layer 1: `SKILL.md` Metadata And User Contract

This is the public contract of the skill.

It should define:

- what the skill does
- which methods it supports
- which methods are first-class methods versus wrapper fallbacks
- what inputs it expects
- what outputs it writes
- what CLI flags are allowed
- what the important method-specific parameters are
- what the current wrapper does today, including limitations

This is where users, orchestrators, and the LLM all get the first stable
description of the skill.

### Layer 2: Wrapper Script Contract

Usually:

- `skills/<domain>/<skill>/<skill>.py`

This layer should own:

- CLI argument parsing
- mapping public flags into backend method arguments
- loading inputs
- saving outputs
- generating reports
- generating the reproducibility bundle
- generating the notebook for normal CLI / bot / chat runs

This layer is where user-facing experience lives.

### Layer 3: Backend `_lib` Implementation Contract

Usually:

- `skills/<domain>/_lib/<module>.py`

This layer should own:

- actual method execution
- method dispatch
- centralized defaults
- method-specific validation
- dependency checks
- stable result fields written back into AnnData or exported tables
- method-aware errors and warnings

This is where the science and the real execution logic live.

### Layer 4: Output Contract

This layer answers:

- what files always exist after a successful run
- what users should inspect first
- what fields in `adata.obs`, `adata.obsm`, `adata.uns`, or `tables/` can be
  depended on downstream
- whether figures are generated from persisted results or only from transient
  runtime variables
- whether normal runs produce a notebook or only a `commands.sh`

This layer matters because user experience is not only about "whether the
analysis ran", but whether the output folder is **readable, inspectable, and
re-runnable**.

### Layer 5: Knowledge Contract

This is where the recent optimization pattern became much clearer:

- short injected **guardrails**
- longer implementation-aware **skill guides**

These should now be treated as two distinct knowledge products:

- `knowledge_base/knowhows/KH-<skill>-guardrails.md`
- `knowledge_base/skill-guides/<domain>/<skill>.md`

The first is for concise run-time guidance.
The second is for longer method-selection and tuning reasoning.

### Layer 6: Testing And Framework Wiring Contract

This includes:

- skill tests
- lazy metadata tests
- keyword routing tests
- knowhow loading tests
- registry / alias / routing updates

Without this layer, a skill may look optimized in isolation but still drift out
of sync with the framework.

## 4. The Most Important Public-Facing Rule

The most important design rule in the current template is this:

> **Common wrapper parameters stay unprefixed; method-specific parameters must
> be method-prefixed.**

This one rule keeps multi-method skills understandable.

### 4.1 What Should Usually Be Common Parameters

Typical common wrapper parameters are things like:

- `method`
- `n_top_*`
- `fdr_threshold`
- `cluster_key`
- `root_cell`
- `root_cell_type`
- `species`
- `layer`

These have skill-level meaning and are not tied to only one backend.

### 4.2 What Should Usually Be Prefixed

If a parameter only affects one method, it should usually be prefixed.

Examples:

- `morans_n_neighs`
- `morans_coord_type`
- `spatialde_min_counts`
- `sparkx_num_cores`
- `flashs_bandwidth`
- `cellrank_n_states`
- `palantir_num_waypoints`
- `harmony_theta`

This keeps the public interface scalable as more methods are added.

### 4.3 Why This Matters

When a skill supports many methods, generic parameter names create ambiguity.

For example:

- `n_components` means different things in different methods
- `bandwidth` might be statistical, graphical, or wrapper-specific
- `option` is almost meaningless without a method context

Prefixing method-specific parameters solves this cleanly and makes future
expansion safer.

## 5. Only Expose Truly Core Parameters

Another core rule from the recent optimization work:

> **`allowed_extra_flags` should not be a dump of upstream arguments.**

Only expose parameters that are:

1. truly important to scientific behavior or runtime behavior
2. likely to be adjusted by users
3. already implemented in the current wrapper
4. stable enough to support long-term

Do not expose parameters just because they exist upstream.

Bad pattern:

- expose 20 knobs because the paper or library has them

Preferred pattern:

- expose 3 to 6 knobs that really matter for first-pass tuning

This is especially important because OmicsClaw is not only a code wrapper; it is
also a user-facing analysis interface. Too many weakly justified parameters hurt
both user experience and LLM behavior.

## 6. `param_hints` Must Be Method-Specific

This is one of the strongest parts of the new template.

For a multi-method skill, `param_hints` should be organized **per method**, not
as one generic blob.

Recommended shape:

```yaml
param_hints:
  method_name:
    priority: "first_param -> second_param -> third_param"
    params: ["first_param", "second_param", "third_param"]
    defaults: {first_param: 1, second_param: 20}
    requires: ["obsm.spatial", "layers.counts", "Rscript"]
    tips:
      - "--first-param: Main tuning knob."
      - "--second-param: Secondary control."
```

This structure is useful because it captures five things at once:

- the tuning order
- the exposed parameters
- the actual defaults
- the method prerequisites
- the short user-facing explanation

### 6.1 The `priority` Field Matters

The `priority` string should reflect the **real order of tuning**.

That means:

- first knob users should think about
- second knob that refines behavior
- third knob for runtime or granularity

This is far more useful than just listing parameters alphabetically.

### 6.2 `defaults` Must Match Real Wrapper Defaults

Do not fill `defaults` with paper defaults if the wrapper behaves differently.

The current OmicsClaw philosophy should be:

- document what the wrapper actually uses now
- if that differs from the paper, state that honestly

### 6.3 `requires` Should Be Concrete

Good `requires` entries:

- `obsm.spatial`
- `layers.counts`
- `uns.neighbors`
- `X_pca`
- `Rscript`

Bad `requires` entries:

- `preprocessed data`
- `good quality data`
- vague prose without technical meaning

## 7. Parameter Provenance Must Be Real

Another core rule:

> **Do not invent parameter stories that sound plausible.**

Every exposed parameter should be grounded in one of these:

1. upstream official docs
2. actual callable API signatures
3. wrapper-level logic you intentionally implemented in OmicsClaw

This is especially important because many methods have different parameter
surfaces, and those surfaces do not always match each other.

That means when optimizing a skill:

- do not assume all methods need the same `param_hints`
- do not assume all methods share the same "important knobs"
- do not write generic hints just because the skill category is similar

For example, two methods in the same skill may differ on:

- input matrix assumptions
- graph assumptions
- dependency requirements
- scalability controls
- significance semantics

The documentation and exposed interface need to reflect that.

## 8. Wrapper-Level Controls Are Allowed, But Must Be Labeled Honestly

Some useful OmicsClaw knobs are not official upstream public parameters.

Examples:

- runtime gene caps
- wrapper-side sketch sizes
- wrapper-side bandwidth estimation overrides
- output visualization toggles
- guardrails around computational scale

These are valid to expose, but they must be described as:

- **wrapper-level controls**
- not guaranteed upstream API parameters

This makes the interface honest and avoids misleading users into thinking these
controls are part of the canonical upstream method specification.

## 9. Internal Code Pattern: One Source Of Truth For Defaults

A strong recurring pattern from the recent optimizations is:

> **Defaults should be centralized in code, not scattered.**

Recommended backend pattern:

```python
METHOD_PARAM_DEFAULTS = {
    "method_a": {...},
    "method_b": {...},
}
```

This should become the single source of truth for:

- runtime defaults
- `effective_params`
- report summaries
- test expectations
- synchronization with `SKILL.md`

If defaults are spread across parser definitions, wrapper helpers, and backend
functions independently, drift becomes almost guaranteed.

## 10. `effective_params` Should Be A First-Class Output

The user should be able to answer this question after every run:

> **What exactly did OmicsClaw run?**

That means every skill should make `effective_params` explicit.

Recommended pattern:

1. start from centralized defaults
2. merge user overrides
3. record the final effective values
4. expose them in:
   - `result.json`
   - `report.md`
   - notebook metadata when applicable

This makes bot conversations, CLI reruns, and debugging much easier.

## 11. Two Hard Behavioral Rules

Two rules should be treated as non-negotiable.

### 11.1 Never Silently Fabricate Biological Structure

Do not silently create fake biological metadata just to make a method run.

Examples of things that should not be silently invented:

- clusters
- root cells
- batch labels
- pseudotime anchors
- missing raw count layers

Allowed behavior:

- fail clearly
- or use a documented fallback with an explicit warning

Not allowed:

- hidden fabrication that makes the result look more complete than it really is

### 11.2 Never Pretend One Method Ran When Another Did

If the user asked for method `A`, do not silently run method `B` and report it
as method `A`.

Allowed behavior:

- fail with a good message
- suggest an alternative method

Not allowed:

- silent substitution
- implicit downgrade without explanation

These rules are essential for scientific honesty.

## 12. Output Contract: The Skill Must Be Easy To Inspect

The current optimization direction is clearly pushing toward a more readable
output contract.

Recommended baseline output layout:

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
├── tables/
├── figure_data/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

Possible optional additions:

- `r_visualization/`
- `reproducibility/r_visualization.sh`
- method-specific extra tables
- extra figure manifests

### 12.1 Why The Output Contract Matters

Historically, a skill could be "technically reproducible" while still being hard
for users to understand because the output folder did not clearly show:

- what happened
- which method ran
- where the main result is
- how to rerun it

The optimized template therefore treats the output folder as part of the user
experience contract, not just as a dump of artifacts.

### 12.2 Notebook-First Reproducibility

This became an especially important rule:

> **Notebook output should not be limited to multi-agent `/research` mode.**

If a normal `oc run`, bot conversation, or standard interactive execution
successfully runs a skill, it should also be able to emit a readable
`analysis_notebook.ipynb`.

This makes normal mode and research mode feel much more consistent.

### 12.3 `README.md` Is Not Optional In Spirit

The top-level `README.md` inside the output should act as the user's first guide
to the result folder.

It should answer:

- what method ran
- where the key result is
- which figure to open first
- where the tables are
- where the reproducibility artifacts are

That single file significantly improves usability.

## 13. Figure Generation Must Read Persisted Results

One practical lesson from the recent skill upgrades:

> **`generate_figures(...)` should operate on persisted analysis results, not on
> transient local variables that only existed during method execution.**

If figures depend on:

- embeddings
- cluster labels
- integration results
- pseudotime
- probabilities
- scores

those should first be written into:

- `adata.obs`
- `adata.obsm`
- `adata.uns`
- or stable tables under `tables/`

before figure generation happens.

This prevents subtle bugs where the analysis step "works" but the figure step
fails because the needed objects were never saved back into the data object.

## 14. Knowledge Layer: Guardrails And Skill Guides Must Be Separated

This is one of the most important conceptual clarifications from the recent
work.

### 14.1 Guardrails

Path pattern:

```text
knowledge_base/knowhows/KH-<skill>-guardrails.md
```

Guardrails should be:

- short
- high-value
- safe to inject into prompts
- focused on what the model must remember during analysis

Typical guardrail content:

- inspect the data first
- choose the method intentionally
- explain the method and key parameters before running
- use method-correct interpretation language
- avoid common conceptual mistakes

Guardrails should **not** become long tuning manuals.

### 14.2 Skill Guides

Path pattern:

```text
knowledge_base/skill-guides/<domain>/<skill>.md
```

Skill guides should be:

- longer
- implementation-aware
- tuning-oriented
- method-comparative

Typical skill-guide content:

1. what the skill is for
2. what data must be inspected first
3. how to choose between methods
4. what parameter summary to show before running
5. method-specific tuning order
6. post-run interpretation guidance
7. visualization/output explanation
8. troubleshooting patterns

### 14.3 The Boundary

The clean boundary should be:

- **guardrails** = short injected operational rules
- **skill guide** = longer reference for method choice and tuning

This boundary matters because if the guardrail grows too large, it becomes a
poor prompt injection artifact. If the skill guide is too short, it stops being
useful as a reference document.

## 15. Validated Workflows Should Stay Separate

Another important architectural point:

- validated workflows in `knowledge_base/` are long-lived, trusted procedures
- skill guides are evolving implementation-aligned documents derived from the
  current OmicsClaw wrapper

These two things should not be collapsed into one category.

That means for new tuning-oriented documents:

- do not force them into the validated workflow collection
- keep them in `skill-guides/` if they are wrapper-aligned and still evolving

This avoids confusing "current implementation guidance" with "verified canonical
workflow".

## 16. Framework Wiring Still Matters

After optimizing a skill, the work is not done until the framework-level wiring
is updated.

Typical places that may need updates:

- `omicsclaw/core/registry.py`
- `omicsclaw/knowledge/knowhow.py`
- `knowledge_base/INDEX.md`
- routing tests
- lazy metadata tests
- knowhow tests

Current practical note:

- the active knowhow behavior still relies on explicit wiring logic
- therefore each new guardrail document should be wired deliberately
- do not assume it will automatically become active just because the file exists

## 17. Standard Test Matrix For An Optimized Skill

Every optimized skill should ideally get four categories of testing.

### 17.1 Skill-Specific Tests

These should test:

- method dispatch
- parser behavior
- stable output keys
- default propagation
- major edge cases

### 17.2 Lazy Metadata Tests

These ensure:

- registry metadata stays loadable
- `SKILL.md` frontmatter is still valid
- the skill remains discoverable by the framework

### 17.3 Keyword Routing Tests

These ensure:

- trigger keywords still route correctly
- aliases remain stable
- new method language does not break routing expectations

### 17.4 Knowhow Tests

These ensure:

- the guardrail doc is loaded where expected
- the mapping is correct
- future refactors do not silently disable the guardrail

## 18. Standard Upgrade Sequence For Any Existing Skill

When optimizing an existing skill, the most reliable sequence is:

### Step 1: Inventory The Current Skill

Read:

- `SKILL.md`
- wrapper script
- relevant `_lib` modules
- current tests

Figure out:

- how many methods actually exist
- whether they are truly first-class methods
- which outputs are already stable
- which parameters are already exposed
- where the code and docs are currently drifting

### Step 2: Verify The Real Method Interfaces

For each method:

- inspect upstream docs or API signatures
- confirm which parameters are genuinely important
- confirm what the input requirements are
- confirm which dependencies are required
- separate upstream parameters from wrapper-side controls

This is the step that prevents generic, ungrounded `param_hints`.

### Step 3: Redesign The Public Contract

Rewrite `SKILL.md` so it includes:

- a clearer description
- method-aware `allowed_extra_flags`
- method-aware `param_hints`
- true input requirements
- true output contract
- wrapper-specific caveats

At this stage, the main question should be:

> "If a user only reads this `SKILL.md`, will they understand what OmicsClaw
> really does?"

### Step 4: Align Wrapper And Backend Code

Refactor so that:

- defaults are centralized
- public flags map cleanly into backend parameters
- stable results are written back into AnnData or tables
- `effective_params` is explicit
- figure generation reads persisted outputs
- method-specific failures become clearer

### Step 5: Add Knowledge Documents

Create:

- `KH-<skill>-guardrails.md`
- `skill-guides/<domain>/<skill>.md`

Make sure:

- the guardrail stays short
- the skill guide carries the longer tuning logic
- neither one tries to become a duplicate of validated workflows

### Step 6: Update Framework Wiring

Update:

- registry metadata if needed
- knowhow mapping
- index pages if needed
- routing tests
- lazy metadata tests
- knowhow tests

### Step 7: Validate End To End

At minimum:

- `py_compile` changed Python files
- run targeted `pytest`
- if practical, do at least one smoke run on demo or real testable data

## 19. Method Addition Recipe

Once a skill has been optimized in this style, adding a new method later should
be mechanical.

For every newly added method, check all of these:

1. add method-specific `allowed_extra_flags`
2. add method-specific `param_hints`
3. add parser arguments
4. add centralized defaults in `METHOD_PARAM_DEFAULTS`
5. add backend dispatch logic
6. define stable result keys in `adata` and/or tables
7. update `result.json` / report text / notebook metadata
8. update guardrails if method choice logic changes
9. update the skill guide method section
10. add or extend tests

If one of these is skipped, the skill will drift.

## 20. Common Anti-Patterns To Avoid

These anti-patterns repeatedly caused weak or inconsistent skill contracts:

- exposing the same vague parameter pattern for every method
- documenting the paper rather than the current wrapper
- filling `allowed_extra_flags` with upstream parameters that are not actually
  meaningful for OmicsClaw users
- writing generic `param_hints` without method verification
- calling wrapper-only controls "official method parameters"
- silently inventing missing metadata
- silently changing methods under the hood
- letting figure generation depend on transient runtime variables
- making bot / CLI / interactive outputs differ too much
- treating guardrails and skill guides as the same thing

## 21. Definition Of A Good Optimized Skill

After the recent rounds of work, a skill can be considered "well optimized"
when all of the following are true:

- `SKILL.md` is implementation-aligned
- different methods have different, justified parameter hints
- the wrapper and `_lib` share a single coherent default model
- the output directory is readable
- normal runs produce notebook-grade reproducibility, not only `commands.sh`
- guardrail and skill-guide documents both exist and have clear boundaries
- framework wiring is updated
- targeted tests pass

## 22. A Compact Working Rule To Reuse Later

When optimizing any future skill, the most useful question is not:

> "How do I make this one file nicer?"

The more useful question is:

> "What is the smallest complete contract that makes this skill accurate,
> explainable, reproducible, and easy to extend?"

That question is the essence of the OmicsClaw optimization template.
