# Singlecell User Experience Rules

The core principle: **any data a user throws at a skill should either produce correct results or produce clear, actionable guidance to fix it**. Never produce wrong/empty results silently.

This document codifies the UX patterns every scRNA skill must implement. The baseline user is a **beginner who does not know which parameters to set, which reference to download, or why the result looks wrong**.

## 1. Input Compatibility Detection

Every skill that depends on specific features in the input data (marker genes, gene sets, reference labels, splicing layers, etc.) must **detect and report compatibility before running the analysis**.

### Required checks

| Check | When | Example |
|-------|------|---------|
| **Feature overlap** | Skill uses a built-in or default gene/feature list | markers method: check how many marker genes exist in `adata.var_names` |
| **Species/organism hint** | Skill uses species-specific defaults | Detect UPPER (human) vs Title-case (mouse) gene naming |
| **Reference availability** | Skill requires an external reference file | popv/knnpredict: check file exists before running |
| **Layer availability** | Skill requires specific AnnData layers | velocity: check spliced/unspliced layers exist |
| **Metadata availability** | Skill requires specific `.obs` columns | DE: check groupby column exists with >1 group |

### Implementation pattern

```python
# 1. Check overlap BEFORE running the analysis
all_required = set(expected_features)
available = all_required & set(adata.var_names)
overlap_rate = len(available) / len(all_required)

# 2. Warn at graduated levels
if overlap_rate == 0:
    logger.warning("NONE of the expected features found. <actionable guidance>")
elif overlap_rate < 0.3:
    logger.warning("Only %.0f%% of expected features found. <guidance>", overlap_rate * 100)
else:
    logger.info("Feature overlap: %.0f%%. Proceeding.", overlap_rate * 100)
```

### Species auto-detection pattern

When a skill uses species-specific defaults (human gene names, mouse gene names), detect the naming convention and attempt automatic adaptation:

```python
def _detect_species_hint(var_names) -> str:
    """Human=UPPER (CD3D), Mouse=Title (Cd3d)."""
    sample = list(var_names[:500])
    upper_ratio = sum(1 for g in sample if g == g.upper()) / len(sample)
    if upper_ratio > 0.7:
        return "human"
    title_ratio = sum(1 for g in sample if g != g.upper() and g[0].isupper()) / len(sample)
    if title_ratio > 0.5:
        return "mouse"
    return "unknown"
```

When species mismatch is detected, attempt **case-insensitive rescue** before giving up.

## 2. Failure Detection and Actionable Guidance

Every skill must detect when its output is degenerate (all Unknown, all NaN, empty results, single cluster, etc.) and provide **specific, actionable guidance** — not just "annotation failed".

### The three-layer guidance rule

Every failure must be reported at **all three layers** that a user might see:

| Layer | Who sees it | What to include |
|-------|-------------|-----------------|
| **stdout (print)** | Direct CLI user | Full step-by-step fix instructions with example commands |
| **report.md** | User reading the output folder | Troubleshooting section with causes + solutions + example commands |
| **result.json** | Bot/agent/downstream code | Machine-readable diagnostic fields + suggested_actions list |

### stdout pattern (for CLI users who don't read logs)

```python
# BAD - user has no idea what to do:
print(f"Annotation complete: {n_types} cell types identified")

# GOOD - user knows exactly what went wrong and how to fix it:
if all_failed:
    print()
    print("  *** ALL cells were labeled 'Unknown' — annotation did not work. ***")
    print("  This usually means ...")
    print()
    print("  How to fix:")
    print("    Option 1 — ...")
    print("      Example command: ...")
    print("    Option 2 — ...")
```

Key rules for stdout guidance:
- Use `***` to visually highlight the problem — users skim terminal output
- State **why** it failed in one plain sentence
- List **numbered options** from easiest to hardest
- Include **copy-pasteable example commands** for each option
- Mention the **exact flag name** (`--marker-file`, `--reference`, `--model`)

### report.md pattern

```python
if all_failed:
    body_lines.extend([
        "",
        "## Troubleshooting: <Problem Description>\n",
        "### Cause 1: <most common cause>",
        "<explanation + example command>",
        "### Cause 2: <second cause>",
        "<explanation + example command>",
        "### Alternative methods",
        "<list methods that don't have this problem>",
    ])
```

### result.json diagnostic pattern

```python
result_data["annotation_diagnostics"] = {
    "all_unknown": True,           # machine-readable failure flag
    "unknown_count": 10,
    "total_count": 10,
    "suggested_actions": [         # bot can present these to user
        "Provide custom markers via --marker-file markers.json",
        "Switch to CellTypist: --method celltypist --model <model>.pkl",
    ],
}
```

The `suggested_actions` list lets the bot/agent **automatically detect and relay guidance** without parsing log text.

## 3. Reference Data Guidance

Any skill that depends on external reference data (reference H5AD, pretrained models, gene set databases, R packages) must tell the user **exactly where to get it and how to use it**.

### Required information

| Item | Must provide |
|------|-------------|
| **What is needed** | File format, required columns/fields, size estimate |
| **Where to download** | Specific URL(s), not just "download a reference" |
| **How to choose** | Which reference/model for which tissue/organism |
| **Example command** | Copy-pasteable command using the downloaded file |
| **Alternatives** | Methods that don't need this reference |

### Where to provide this guidance

1. **SKILL.md** — "Reference Data Guide" section (always present)
2. **Error messages** — when reference file is missing or incompatible
3. **stdout** — when analysis fails due to missing/wrong reference
4. **knowledge_base skill-guide** — troubleshooting section

### Error message pattern for missing references

```python
# BAD:
raise FileNotFoundError(f"Reference file {path} does not exist.")

# GOOD:
raise FileNotFoundError(
    f"Reference file '{path}' does not exist.\n"
    "This method requires a labeled reference H5AD with a 'cell_type' column.\n"
    "\n"
    "How to get a reference:\n"
    "  1. CZ CELLxGENE: https://cellxgene.cziscience.com/\n"
    "  2. Human Cell Atlas: https://www.humancellatlas.org/\n"
    "  3. Mouse: Tabula Muris https://tabula-muris.ds.czbiohub.org/\n"
    "\n"
    "Then: --method <method> --reference /path/to/ref.h5ad\n"
    "\n"
    "Alternatives that don't need a reference:\n"
    "  --method markers --marker-file my_markers.json\n"
    "  --method celltypist --model <model>.pkl"
)
```

## 4. Default Behavior Design

### Principle: defaults should work for the most common case

- If a skill has a default value (e.g., default marker set, default model), it should be **broad enough to cover common cases**, not narrow to one specific tissue type
- If the default cannot be broad (e.g., gene sets are inherently tissue-specific), the skill must **detect failure early and guide the user to provide custom input**

### Principle: never fail silently

- If a default doesn't match the data, the skill must **warn or error**, never silently produce empty/wrong results
- "Silent skip" (`continue` without logging) is forbidden when it can cause the entire analysis to produce no results

### Principle: provide escape hatches

Every skill with defaults must provide a way for users to override them:
- `--marker-file` for custom marker genes
- `--reference` for custom reference datasets
- `--model` for custom pretrained models
- `--gene-sets` for custom gene set files

## 5. Fallback Transparency

When a skill falls back from one method to another (e.g., CellTypist → markers), it must:

1. **Log the fallback** at WARNING level with the reason
2. **Record it in the summary** (`used_fallback`, `fallback_reason`)
3. **Show it in stdout** so the user knows what actually ran
4. **Include it in report.md** with guidance on how to fix the original method
5. **Propagate quality checks** — if the fallback method also fails (e.g., markers returns all Unknown after CellTypist failed), that failure must still be detected and reported

## 6. Method Selection Guidance

For multi-method skills, help users choose the right method:

### In SKILL.md

Include a decision table:

```markdown
| Scenario | Recommended method | Example |
|----------|-------------------|---------|
| Have PBMC/immune data (human) | markers or celltypist | --method markers |
| Have specialized tissue | celltypist with tissue model | --method celltypist --model Human_Lung_Atlas.pkl |
| Have mouse data | celltypist with mouse model | --method celltypist --model Mouse_Isocortex_Hippocampus.pkl |
| Have labeled reference | knnpredict | --method knnpredict --reference ref.h5ad |
```

### In knowledge_base skill-guide

Include a troubleshooting section for the most common failure mode.

## 7. Checklist (add to SC-DEVELOPMENT-CHECKLIST.md)

```
# User Experience
- [ ] skill detects feature/gene overlap with defaults before running
- [ ] skill detects species/organism mismatch when using species-specific defaults
- [ ] skill detects degenerate output (all Unknown, all NaN, empty) and reports at stdout + report.md + result.json
- [ ] stdout failure message includes numbered fix options with example commands
- [ ] report.md includes Troubleshooting section when output is degenerate
- [ ] result.json includes diagnostic fields (e.g., all_unknown, suggested_actions) for bot/agent
- [ ] error messages for missing references include download URLs and alternatives
- [ ] SKILL.md includes Reference Data Guide (or equivalent) when external data is needed
- [ ] knowledge_base skill-guide includes troubleshooting for the most common failure
- [ ] users can override all defaults via CLI flags (--marker-file, --reference, --model, etc.)
- [ ] fallbacks are transparent: logged, recorded in summary, shown in stdout
```
