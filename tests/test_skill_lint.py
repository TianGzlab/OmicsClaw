"""Behavioural tests for scripts/skill_lint.py.

The lint script enforces the v2 skill template — but only on skills that have
opted in (i.e. have a `parameters.yaml` sidecar).  Legacy skills with only a
frontmatter contract must continue to lint clean by default so the migration
can proceed skill-by-skill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import skill_lint  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — fabricate skill directories on disk
# ---------------------------------------------------------------------------

VALID_SIDECAR = {
    "domain": "demo",
    "script": "demo.py",
    "saves_h5ad": False,
    "requires_preprocessed": False,
    "trigger_keywords": [],
    "legacy_aliases": [],
    "allowed_extra_flags": ["--method"],
    "param_hints": {},
}

REQUIRED_SECTIONS = (
    "## When to use",
    "## Inputs & Outputs",
    "## Flow",
    "## Gotchas",
    "## Key CLI",
    "## See also",
)

VALID_BODY = (
    "# Demo Skill\n\n"
    "## When to use\nLoad to demo.\n\n"
    "## Inputs & Outputs\nIn → out.\n\n"
    "## Flow\n1. Step.\n\n"
    "## Gotchas\n- _None yet._\n\n"
    "## Key CLI\n```\noc run demo --demo\n```\n\n"
    "## See also\n- references/methodology.md\n"
)


def _write_v2_skill(
    base: Path,
    *,
    description: str = "Load when demoing the lint. Skip when in production.",
    body: str = VALID_BODY,
    sidecar: dict | None = None,
    skip_references: tuple[str, ...] = (),
    extra_frontmatter: dict | None = None,
    script_text: str | None = None,
) -> Path:
    skill = base
    skill.mkdir(parents=True, exist_ok=True)
    fm = {
        "name": skill.name,
        "description": description,
        "version": "0.1.0",
        "tags": ["demo"],
    }
    if extra_frontmatter:
        fm.update(extra_frontmatter)
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    sc = sidecar or VALID_SIDECAR
    (skill / "parameters.yaml").write_text(
        yaml.safe_dump(sc, sort_keys=False), encoding="utf-8"
    )
    if script_text is not None:
        (skill / sc["script"]).write_text(script_text, encoding="utf-8")
    refs = skill / "references"
    refs.mkdir(exist_ok=True)
    for name in ("methodology.md", "output_contract.md"):
        if name not in skip_references:
            (refs / name).write_text(f"# {name}\n", encoding="utf-8")
    if "parameters.md" not in skip_references:
        from generate_parameters_md import render_parameters_md

        (refs / "parameters.md").write_text(
            render_parameters_md(sc), encoding="utf-8"
        )
    return skill


def _write_legacy_skill(base: Path) -> Path:
    """Legacy form: SKILL.md with metadata.omicsclaw, no sidecar."""
    skill = base
    skill.mkdir(parents=True, exist_ok=True)
    fm = {
        "name": skill.name,
        "description": "Old-style description.",
        "version": "0.1.0",
        "metadata": {
            "omicsclaw": {
                "domain": "demo",
                "script": "demo.py",
                "allowed_extra_flags": [],
                "param_hints": {},
            }
        },
    }
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n# Legacy\n",
        encoding="utf-8",
    )
    return skill


# ---------------------------------------------------------------------------
# Behavioural tests
# ---------------------------------------------------------------------------

def test_valid_v2_skill_lints_clean(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo")
    errors = skill_lint.lint_skill(skill)
    assert errors == [], f"expected clean lint, got {errors}"


def test_legacy_skill_lints_clean_by_default(tmp_path: Path) -> None:
    """Migration is skill-by-skill; un-migrated skills must not block CI."""
    skill = _write_legacy_skill(tmp_path / "old")
    errors = skill_lint.lint_skill(skill)
    assert errors == [], f"legacy skill should pass default lint, got {errors}"


def test_description_must_start_with_load_when(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo", description="Differential expression for X.")
    errors = skill_lint.lint_skill(skill)
    assert any("description" in e and "Load when" in e for e in errors)


def test_description_word_count_capped(tmp_path: Path) -> None:
    long_desc = "Load when " + " ".join([f"word{i}" for i in range(60)])
    skill = _write_v2_skill(tmp_path / "demo", description=long_desc)
    errors = skill_lint.lint_skill(skill)
    assert any("description" in e and "50" in e for e in errors)


def test_description_must_include_skip_clause(tmp_path: Path) -> None:
    """A description that only says when to load is half a routing trigger;
    it must also tell the agent which neighbour to bounce to.  Accepts
    'Skip when' / 'Skip if' / 'Skip for' (all three forms appear in
    production descriptions).
    """
    skill = _write_v2_skill(
        tmp_path / "demo",
        description="Load when demoing the lint without a skip clause.",
    )
    errors = skill_lint.lint_skill(skill)
    assert any(
        "description" in e and "Skip" in e for e in errors
    ), f"expected a Skip-clause error, got {errors}"


@pytest.mark.parametrize("clause", ["Skip when", "Skip if", "Skip for"])
def test_description_skip_clause_variants_accepted(
    tmp_path: Path, clause: str
) -> None:
    """All three Skip variants observed in production descriptions are
    accepted by the lint."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        description=f"Load when X. {clause} Y.",
    )
    errors = skill_lint.lint_skill(skill)
    assert not any(
        "description" in e and "Skip" in e for e in errors
    ), f"expected Skip clause to satisfy lint, got {errors}"


@pytest.mark.parametrize(
    "description",
    [
        "Load when X.\nSkip\nwhen Y.",  # YAML literal block scalar (`|`)
        "Load when X. Skip  when Y.",   # double-space artefact
        "Load when X.\tSkip\twhen Y.",  # tab whitespace
    ],
    ids=["newline-wrapped", "double-space", "tab-separated"],
)
def test_description_skip_clause_normalised_whitespace(
    tmp_path: Path, description: str
) -> None:
    """YAML folded / literal scalars and quoted forms can introduce newlines,
    double spaces, or tabs between 'Skip' and the connective.  The lint
    must whitespace-normalise before matching."""
    skill = _write_v2_skill(tmp_path / "demo", description=description)
    errors = skill_lint.lint_skill(skill)
    assert not any(
        "description" in e and "Skip" in e for e in errors
    ), f"expected normalised Skip clause to satisfy lint, got {errors}"


def test_description_skip_without_connective_rejected(tmp_path: Path) -> None:
    """A bare 'Skip' (no when/if/for) carries no routing semantics — the
    connective is what tells the agent which neighbour to bounce to.
    Locks in that 'Skip otherwise.' / 'Skip in production.' do NOT satisfy
    the rule, so a future contributor relaxing the substring to plain 'skip '
    would see this test fail."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        description="Load when X. Skip otherwise.",
    )
    errors = skill_lint.lint_skill(skill)
    assert any(
        "description" in e and "Skip" in e for e in errors
    ), f"expected bare Skip to be rejected, got {errors}"


def test_missing_required_section_fails(tmp_path: Path) -> None:
    body_no_gotchas = VALID_BODY.replace("## Gotchas\n- _None yet._\n\n", "")
    skill = _write_v2_skill(tmp_path / "demo", body=body_no_gotchas)
    errors = skill_lint.lint_skill(skill)
    assert any("## Gotchas" in e for e in errors)


def test_body_too_long_fails(tmp_path: Path) -> None:
    long_body = VALID_BODY + ("filler\n" * 250)
    skill = _write_v2_skill(tmp_path / "demo", body=long_body)
    errors = skill_lint.lint_skill(skill)
    assert any("body" in e.lower() and "200" in e for e in errors)


def test_missing_reference_file_fails(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo", skip_references=("methodology.md",))
    errors = skill_lint.lint_skill(skill)
    assert any("methodology.md" in e for e in errors)


def test_stale_parameters_md_fails(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo")
    (skill / "references" / "parameters.md").write_text("STALE\n", encoding="utf-8")
    errors = skill_lint.lint_skill(skill)
    assert any("parameters.md" in e and "stale" in e.lower() for e in errors)


def test_legacy_omicsclaw_block_in_v2_skill_fails(tmp_path: Path) -> None:
    """A v2 skill (parameters.yaml present) must NOT keep the legacy
    metadata.omicsclaw block — otherwise we get two sources of truth."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        extra_frontmatter={"metadata": {"omicsclaw": {"domain": "stale"}}},
    )
    errors = skill_lint.lint_skill(skill)
    assert any("metadata.omicsclaw" in e for e in errors)


def test_sidecar_missing_required_field_fails(tmp_path: Path) -> None:
    bad = dict(VALID_SIDECAR)
    del bad["domain"]
    skill = _write_v2_skill(tmp_path / "demo", sidecar=bad)
    errors = skill_lint.lint_skill(skill)
    assert any("domain" in e for e in errors)


def test_section_inside_html_comment_does_not_satisfy_check(tmp_path: Path) -> None:
    """A required section heading inside an HTML comment should NOT count
    as the section being present (substring-only matching is wrong)."""
    body_with_commented_sections = (
        "# Demo Skill\n\n"
        "<!-- ## When to use ## Inputs & Outputs ## Flow ## Gotchas "
        "## Key CLI ## See also -->\n"
        "Real body content but no actual sections.\n"
    )
    skill = _write_v2_skill(tmp_path / "demo", body=body_with_commented_sections)
    errors = skill_lint.lint_skill(skill)
    # Each missing section should be flagged.
    assert any("## When to use" in e for e in errors)
    assert any("## Gotchas" in e for e in errors)


def test_sidecar_flag_must_start_with_double_dash(tmp_path: Path) -> None:
    bad = dict(VALID_SIDECAR)
    bad["allowed_extra_flags"] = ["method"]  # missing --
    skill = _write_v2_skill(tmp_path / "demo", sidecar=bad)
    errors = skill_lint.lint_skill(skill)
    assert any("allowed_extra_flags" in e for e in errors)


# ---------------------------------------------------------------------------
# Gotcha-anchor lint — every code surface mentioned in a Gotcha must
# grep-resolve in the skill's script.  Catches the dominant failure mode
# from PR #4 review (Gotchas describing "the desired script" rather than
# what the code actually does).
# ---------------------------------------------------------------------------


def _gotcha_body(gotchas_block: str) -> str:
    """Minimal v2 body with a custom Gotchas section."""
    return (
        "# Demo Skill\n\n"
        "## When to use\nLoad to demo.\n\n"
        "## Inputs & Outputs\nIn → out.\n\n"
        "## Flow\n1. Step.\n\n"
        f"## Gotchas\n{gotchas_block}\n"
        "## Key CLI\n```\noc run demo --demo\n```\n\n"
        "## See also\n- references/methodology.md\n"
    )


def test_gotchas_template_passes(tmp_path: Path) -> None:
    """The default v2 template's empty-gotchas marker must lint clean."""
    body = _gotcha_body(
        "- _No gotchas yet — append entries as they surface in production._\n"
    )
    skill = _write_v2_skill(tmp_path / "demo", body=body)
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_pure_prose_passes(tmp_path: Path) -> None:
    """Bullets without code anchors are allowed (the lint is anchor-only)."""
    body = _gotcha_body(
        "- LFCs are unshrunk by design — apply shrinkage downstream.\n"
        "- Pre-filter removes low-count genes (total < 10).\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo", body=body, script_text="x = 1\n",
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_result_json_unresolved_fails(tmp_path: Path) -> None:
    """A Gotcha referencing result.json[\"fake_key\"] must fail when the
    script does not mention that key — the PR #4 hallucination pattern."""
    body = _gotcha_body(
        '- Check `result.json["fake_key"]` to verify the run.\n'
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text="summary = {'real_key': 1}\n",
    )
    errors = skill_lint.lint_skill(skill)
    assert any(
        "gotchas" in e.lower() and "fake_key" in e for e in errors
    ), errors


def test_gotchas_result_json_resolved_passes(tmp_path: Path) -> None:
    body = _gotcha_body(
        '- Check `result.json["method_used"]` to confirm the engine ran.\n'
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text='summary["method_used"] = "wilcoxon"\n',
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_result_json_nested_first_key_checked(tmp_path: Path) -> None:
    """For nested keys (result.json[\"summary\"][\"X\"]) the lint checks the
    top-level key — that's the most reliably grep-able."""
    body = _gotcha_body(
        '- Inspect `result.json["summary"]["expression_source"]`.\n'
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text='out = {"summary": {"expression_source": "X"}}\n',
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_file_line_in_bounds_passes(tmp_path: Path) -> None:
    body = _gotcha_body(
        "- Behaviour anchored at `demo.py:5` (the silent fallback branch).\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text="\n".join(f"line_{i}" for i in range(20)),
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_file_line_out_of_bounds_fails(tmp_path: Path) -> None:
    """A file:line pointer past the script's end must fail.  PR #3
    reviewer caught a similar bug (anchor pointed to a report-rendering
    line that didn't exist where claimed)."""
    body = _gotcha_body(
        "- Wrong anchor at `demo.py:9999` — file is much shorter.\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text="\n".join(f"line_{i}" for i in range(10)),
    )
    errors = skill_lint.lint_skill(skill)
    assert any(
        "gotchas" in e.lower() and "9999" in e for e in errors
    ), errors


def test_gotchas_file_line_range_checks_upper_bound(tmp_path: Path) -> None:
    """A range like `demo.py:5-9999` must fail because 9999 exceeds file."""
    body = _gotcha_body(
        "- Range anchor `demo.py:5-9999` straddles past EOF.\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text="\n".join(f"line_{i}" for i in range(20)),
    )
    errors = skill_lint.lint_skill(skill)
    assert any("gotchas" in e.lower() and "9999" in e for e in errors), errors


def test_gotchas_table_filename_unresolved_fails(tmp_path: Path) -> None:
    """A `tables/<file>.csv` reference that the script never writes — PR #4
    hallucination pattern (e.g., 'cell_type_proportions.csv' when the
    actual filename was 'proportions.csv')."""
    body = _gotcha_body(
        "- Output ends up in `tables/fake_results.csv` for the run.\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text='df.to_csv(out / "tables/real.csv")\n',
    )
    errors = skill_lint.lint_skill(skill)
    assert any(
        "gotchas" in e.lower() and "fake_results.csv" in e for e in errors
    ), errors


def test_gotchas_figure_filename_resolved_passes(tmp_path: Path) -> None:
    body = _gotcha_body(
        "- The volcano lives at `figures/volcano_plot.png`.\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text='plt.savefig(out / "figures/volcano_plot.png")\n',
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


def test_gotchas_empty_marker_only_matches_when_lead_of_bullet(
    tmp_path: Path,
) -> None:
    """A real Gotcha bullet that happens to mention 'none yet' as prose
    must NOT bypass the anchor lint.  The empty-template skip applies
    only when a bullet leads with the marker phrase — Reviewer S1 fix."""
    body = _gotcha_body(
        "- A real footgun: with `result.json[\"fake_key\"]` no fix is "
        "available — none yet documented in the codebase.\n"
    )
    skill = _write_v2_skill(
        tmp_path / "demo",
        body=body,
        script_text="summary = {'real_key': 1}\n",
    )
    errors = skill_lint.lint_skill(skill)
    # Anchor lint must still fire for fake_key, despite the prose phrase
    assert any(
        "gotchas" in e.lower() and "fake_key" in e for e in errors
    ), errors


def test_gotchas_anchor_check_skipped_when_script_missing(tmp_path: Path) -> None:
    """If parameters.yaml's `script` doesn't resolve to a real file (e.g.,
    the script lives in a sibling dir), skip the anchor lint gracefully —
    do not block the whole skill."""
    body = _gotcha_body(
        '- Result key `result.json["anything"]` and table `tables/x.csv`.\n'
    )
    skill = _write_v2_skill(tmp_path / "demo", body=body)  # no script_text → no demo.py
    errors = skill_lint.lint_skill(skill)
    assert not any("gotchas" in e.lower() for e in errors), errors


# ---------------------------------------------------------------------------
# Check: allowed_extra_flags ⊇ argparse
# ---------------------------------------------------------------------------

def _flag_script(*flags: str) -> str:
    """Render a minimal Python script with the given argparse flags."""
    lines = [
        "import argparse",
        "p = argparse.ArgumentParser()",
        'p.add_argument("--input")',
        'p.add_argument("--output")',
        'p.add_argument("--demo", action="store_true")',
    ]
    for flag in flags:
        lines.append(f'p.add_argument("{flag}")')
    return "\n".join(lines) + "\n"


def test_allowed_extra_flags_matches_argparse(tmp_path: Path) -> None:
    """yaml.allowed_extra_flags must list exactly the script's argparse flags
    (minus --input / --output / --demo, which the runner blocks)."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": ["--alpha", "--method"]}
    skill = _write_v2_skill(
        tmp_path / "demo",
        sidecar=sidecar,
        script_text=_flag_script("--method", "--alpha"),
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("allowed_extra_flags" in e for e in errors), errors


def test_allowed_extra_flags_missing_declared_flag_fails(tmp_path: Path) -> None:
    """A flag declared in argparse but absent from yaml triggers an error."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": ["--method"]}
    skill = _write_v2_skill(
        tmp_path / "demo",
        sidecar=sidecar,
        script_text=_flag_script("--method", "--alpha"),
    )
    errors = skill_lint.lint_skill(skill)
    assert any("missing '--alpha'" in e for e in errors), errors


def test_allowed_extra_flags_lists_undeclared_flag_fails(tmp_path: Path) -> None:
    """A yaml entry that argparse does not declare triggers an error."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": ["--method", "--missing"]}
    skill = _write_v2_skill(
        tmp_path / "demo",
        sidecar=sidecar,
        script_text=_flag_script("--method"),
    )
    errors = skill_lint.lint_skill(skill)
    assert any("'--missing'" in e and "does not declare" in e for e in errors), errors


def test_allowed_extra_flags_runner_blocked_trio_excluded(tmp_path: Path) -> None:
    """--input / --output / --demo are runner-blocked and must NOT need to
    be listed in allowed_extra_flags."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": ["--method"]}
    skill = _write_v2_skill(
        tmp_path / "demo",
        sidecar=sidecar,
        # Script declares only --input/--output/--demo + --method
        script_text=_flag_script("--method"),
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("--input" in e or "--output" in e or "--demo" in e for e in errors), errors


def test_allowed_extra_flags_check_skipped_when_script_missing(tmp_path: Path) -> None:
    """If the script doesn't resolve, skip the check rather than false-fail."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": ["--method"]}
    skill = _write_v2_skill(tmp_path / "demo", sidecar=sidecar)  # no script
    errors = skill_lint.lint_skill(skill)
    assert not any("allowed_extra_flags missing" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Check: output_contract.md paths exist in the script
# ---------------------------------------------------------------------------

def _write_output_contract(skill: Path, body: str) -> None:
    (skill / "references" / "output_contract.md").write_text(body, encoding="utf-8")


def test_output_contract_paths_must_exist_in_script(tmp_path: Path) -> None:
    """A path in output_contract.md must appear as a substring in the script."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script() + 'open("tables/foo.csv").write(...)\n',
    )
    _write_output_contract(skill, "## Output\n- `tables/foo.csv`\n- `tables/missing.csv`\n")
    errors = skill_lint.lint_skill(skill)
    assert any("'tables/missing.csv'" in e for e in errors), errors
    assert not any("'tables/foo.csv'" in e for e in errors), errors


def test_output_contract_framework_files_exempt(tmp_path: Path) -> None:
    """`report.md`, `result.json`, `processed.h5ad`, `commands.sh`, etc. are
    written by the framework helper, NOT the skill script — exempt them."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script(),  # Script writes nothing custom
    )
    _write_output_contract(
        skill,
        "## Output\n- `report.md`\n- `result.json`\n- `processed.h5ad`\n"
        "- `commands.sh`\n- `requirements.txt`\n- `checksums.sha256`\n",
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("output_contract.md:" in e for e in errors), errors


def test_output_contract_html_comment_paths_ignored(tmp_path: Path) -> None:
    """The migrate_skill.py header `<!-- ... output_contract.md -->` must
    not trigger false positives for `output_contract.md` / `SKILL.md`."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script() + 'open("tables/real.csv").write(...)\n',
    )
    _write_output_contract(
        skill,
        "<!-- Generated by scripts/migrate_skill.py -->\n"
        "<!-- Kind: references/output_contract.md | Source: SKILL.md -->\n\n"
        "## Output\n- `tables/real.csv`\n",
    )
    errors = skill_lint.lint_skill(skill)
    assert not any("output_contract.md:" in e for e in errors), errors


def test_output_contract_multi_dot_extensions_match_correctly(tmp_path: Path) -> None:
    """`checksums.sha256` must NOT be truncated to `checksums.sh` by greedy
    extension alternation."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script(),
    )
    _write_output_contract(
        skill, "## Output\n- `reproducibility/checksums.sha256`\n"
    )
    errors = skill_lint.lint_skill(skill)
    # checksums.sha256 is in _FRAMEWORK_FILES → exempt; if greedy-matched to
    # checksums.sh, the framework-files set would not contain it and the
    # check would emit an error.  No error means the regex is correct.
    assert not any("output_contract.md:" in e for e in errors), errors


def test_output_contract_check_skipped_when_script_missing(tmp_path: Path) -> None:
    """If the script doesn't resolve, skip the check rather than false-fail."""
    skill = _write_v2_skill(tmp_path / "demo")  # no script
    _write_output_contract(skill, "## Output\n- `tables/imaginary.csv`\n")
    errors = skill_lint.lint_skill(skill)
    assert not any("output_contract.md:" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Check: _lib lookup behaviour
# ---------------------------------------------------------------------------

def test_output_contract_scans_imported_lib_at_skill_dir(tmp_path: Path) -> None:
    """A path that lives only in `<skill>/_lib/<X>.py` (which the script
    explicitly imports) must be accepted by the lint."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script() + "from .._lib.helper import process\n",
    )
    lib_dir = skill / "_lib"
    lib_dir.mkdir()
    (lib_dir / "helper.py").write_text('open("tables/from_lib.csv").write(...)\n', encoding="utf-8")
    _write_output_contract(skill, "## Output\n- `tables/from_lib.csv`\n")
    errors = skill_lint.lint_skill(skill)
    assert not any("output_contract.md:" in e for e in errors), errors


def test_output_contract_scans_imported_lib_at_grandparent(tmp_path: Path) -> None:
    """For two-deep skill trees (e.g. singlecell/scrna/X), the lint must
    walk up to find the `_lib` at the domain root."""
    domain = tmp_path / "singlecell" / "scrna"
    skill = _write_v2_skill(
        domain / "demo",
        script_text=(
            _flag_script()
            + "from skills.singlecell._lib.helper import process\n"
        ),
    )
    # _lib lives at skills/singlecell/_lib/, two levels above the skill dir
    lib_dir = tmp_path / "singlecell" / "_lib"
    lib_dir.mkdir()
    (lib_dir / "helper.py").write_text('open("tables/from_lib.csv").write(...)\n', encoding="utf-8")
    # The lint stops walking at a `skills/` directory boundary, so anchor
    # one in tmp so the loop terminates predictably.
    (tmp_path / "skills").mkdir(exist_ok=True)
    _write_output_contract(skill, "## Output\n- `tables/from_lib.csv`\n")
    errors = skill_lint.lint_skill(skill)
    assert not any("output_contract.md:" in e for e in errors), errors


def test_output_contract_does_not_scan_unimported_lib(tmp_path: Path) -> None:
    """A path that lives in `_lib/<X>.py` which the script does NOT import
    must NOT silently validate the contract — that was the spatial-domains
    bug where the contract claimed to write `cellchat_results.csv` because
    it appeared in a sibling _lib file."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        script_text=_flag_script() + "from .._lib.real import wanted\n",
    )
    lib_dir = skill / "_lib"
    lib_dir.mkdir()
    (lib_dir / "real.py").write_text('open("tables/wanted.csv").write(...)\n', encoding="utf-8")
    (lib_dir / "unrelated.py").write_text('open("tables/unrelated.csv").write(...)\n', encoding="utf-8")
    _write_output_contract(
        skill,
        "## Output\n- `tables/wanted.csv`\n- `tables/unrelated.csv`\n",
    )
    errors = skill_lint.lint_skill(skill)
    # `wanted.csv` is in an imported _lib → ok.
    # `unrelated.csv` lives in unimported `_lib/unrelated.py` → must error.
    assert any("'tables/unrelated.csv'" in e for e in errors), errors
    assert not any("'tables/wanted.csv'" in e for e in errors), errors


def test_argparse_short_flag_does_not_satisfy_long_flag_requirement(tmp_path: Path) -> None:
    """`add_argument("-m", "--method")` must register `--method` (not `-m`)
    and require `--method` in `allowed_extra_flags`.  The earlier regex
    `[\\-\\-]` collapsed to `[-]` and would have matched `-m` instead."""
    sidecar = {**VALID_SIDECAR, "allowed_extra_flags": []}
    script = _flag_script() + 'p.add_argument("-m", "--method")\n'
    skill = _write_v2_skill(tmp_path / "demo", sidecar=sidecar, script_text=script)
    errors = skill_lint.lint_skill(skill)
    assert any("missing '--method'" in e for e in errors), errors
    # Must NOT report `-m` as a missing flag (single-dash short flags are
    # never listed in allowed_extra_flags).
    assert not any("missing '-m'" in e for e in errors), errors
