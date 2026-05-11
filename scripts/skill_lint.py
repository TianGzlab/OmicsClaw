#!/usr/bin/env python3
"""Lint OmicsClaw v2 skills against the canonical template.

A skill is "v2" iff it has a `parameters.yaml` sidecar.  Lint rules apply only
to v2 skills; legacy skills (frontmatter-only) lint clean by default so the
89-skill migration can proceed one PR at a time without breaking CI.

Usage:
    python scripts/skill_lint.py <skill_dir>          # one skill
    python scripts/skill_lint.py --all                # every skill under skills/
    python scripts/skill_lint.py --all --strict       # treat warnings as errors
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from generate_parameters_md import render_parameters_md  # noqa: E402

REQUIRED_SECTIONS = (
    "## When to use",
    "## Inputs & Outputs",
    "## Flow",
    "## Gotchas",
    "## Key CLI",
    "## See also",
)

REQUIRED_REFERENCES = ("methodology.md", "output_contract.md", "parameters.md")

ALLOWED_FRONTMATTER_KEYS = {
    "name", "description", "version", "author", "license", "tags", "requires",
}

REQUIRED_SIDECAR_KEYS = {
    "domain", "script", "saves_h5ad", "requires_preprocessed",
    "trigger_keywords", "legacy_aliases", "allowed_extra_flags", "param_hints",
}

MAX_BODY_LINES = 200
MAX_DESCRIPTION_WORDS = 50


def _parse_skill_md(skill_dir: Path) -> tuple[dict, str] | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    body = parts[2].lstrip("\n")
    return frontmatter, body


_SKIP_CLAUSES = ("skip when", "skip if", "skip for")


def _check_description(description: str) -> list[str]:
    errors: list[str] = []
    desc = (description or "").strip()
    # Whitespace-normalise so YAML folded scalars (`>-` / `|`) that wrap
    # "Skip when" across lines, or that introduce double spaces, still match.
    normalised = " ".join(desc.lower().split())
    if not normalised.startswith("load when"):
        errors.append("description: must start with 'Load when'")
    if not any(clause in normalised for clause in _SKIP_CLAUSES):
        errors.append(
            "description: must include a 'Skip when' / 'Skip if' / 'Skip for' "
            "clause"
        )
    if len(desc.split()) > MAX_DESCRIPTION_WORDS:
        errors.append(
            f"description: must be <= {MAX_DESCRIPTION_WORDS} words "
            f"(found {len(desc.split())})"
        )
    return errors


def _check_body(body: str) -> list[str]:
    errors: list[str] = []
    line_count = len(body.splitlines())
    if line_count > MAX_BODY_LINES:
        errors.append(
            f"body: exceeds {MAX_BODY_LINES} lines (found {line_count})"
        )
    # Line-anchored match: a heading must start the line (after optional
    # whitespace).  Avoids false positives from HTML comments or prose that
    # quotes a section name inline.
    body_lines = [ln.lstrip() for ln in body.splitlines()]
    for section in REQUIRED_SECTIONS:
        if not any(line.startswith(section) for line in body_lines):
            errors.append(f"body: missing required section '{section}'")
    return errors


def _check_frontmatter_keys(frontmatter: dict) -> list[str]:
    errors: list[str] = []
    extra = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if "metadata" in extra:
        meta = frontmatter.get("metadata") or {}
        if isinstance(meta, dict) and "omicsclaw" in meta:
            errors.append(
                "frontmatter: legacy 'metadata.omicsclaw' block must be removed "
                "from v2 skills (move runtime fields to parameters.yaml)"
            )
        extra.discard("metadata")
    if extra:
        errors.append(
            f"frontmatter: unexpected keys {sorted(extra)} "
            f"(allowed: {sorted(ALLOWED_FRONTMATTER_KEYS)})"
        )
    return errors


def _check_sidecar(sidecar: dict) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_SIDECAR_KEYS - set(sidecar)
    for key in sorted(missing):
        errors.append(f"parameters.yaml: missing required field '{key}'")
    flags = sidecar.get("allowed_extra_flags", []) or []
    for flag in flags:
        if not isinstance(flag, str) or not flag.startswith("--"):
            errors.append(
                f"parameters.yaml: allowed_extra_flags entry {flag!r} "
                f"must be a string starting with '--'"
            )
    if "param_hints" in sidecar and not isinstance(sidecar["param_hints"], dict):
        errors.append("parameters.yaml: param_hints must be a dict")
    return errors


_GOTCHA_FILE_LINE_RE = re.compile(r"`?([\w./-]+\.py):(\d+)(?:-(\d+))?`?")
_GOTCHA_RESULT_JSON_RE = re.compile(r"`?result\.json(?:\[[\"'][^\"']+[\"']\])+`?")
_GOTCHA_RESULT_KEY_RE = re.compile(r"\[[\"']([^\"']+)[\"']\]")
_GOTCHA_TABLE_FIG_RE = re.compile(r"`?(?:tables|figures)/([\w._-]+)`?")
_GOTCHA_BULLET_RE = re.compile(r"^\s*-\s+(.*)$", re.MULTILINE)
_GOTCHA_EMPTY_BULLET_RE = re.compile(
    r"^[-*\s_`]*(no gotchas yet|none yet|no gotchas surfaced)\b",
    re.IGNORECASE,
)


def _check_gotchas_anchors(
    skill_dir: Path, body: str, sidecar: dict
) -> list[str]:
    """Verify every code anchor in the Gotchas section grep-resolves.

    The dominant hallucination pattern from PR #4 review was Gotchas that
    described "the desired script" rather than what the code actually does —
    references to `result.json` keys that didn't exist, table filenames that
    weren't written, file:line anchors past EOF.  This lint catches all
    three by greping the skill's `script` for each anchor before the PR
    leaves the contributor's branch.
    """
    errors: list[str] = []

    section = re.search(
        r"^## Gotchas\b\s*\n(.*?)(?=^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return []  # missing-section error already raised by _check_body
    block = section.group(1)

    # Per-bullet processing.  Skip the empty-template marker bullet only
    # when the bullet's lead matches it (so a real Gotcha that *mentions*
    # the phrase "none yet" inside its prose does not silently bypass the
    # anchor lint).
    real_bullets: list[str] = []
    for bullet in _GOTCHA_BULLET_RE.findall(block):
        if _GOTCHA_EMPTY_BULLET_RE.match(bullet):
            continue
        real_bullets.append(bullet)
    if not real_bullets:
        return []

    script_name = sidecar.get("script") or ""
    script_path = skill_dir / script_name if script_name else None
    if not (script_path and script_path.exists()):
        return []  # script not co-located — skip rather than false-fail
    script_text = script_path.read_text(encoding="utf-8")
    script_line_count = script_text.count("\n") + 1

    real_block = "\n".join(real_bullets)

    # TODO(cross-file): when an anchor references a sibling library file
    # (e.g. `_lib/de.py:485-506`, used in spatial-de Gotchas), the
    # filename's basename will not match `script_name` so the line-bound
    # check is skipped.  A project-wide grep would close the gap, but
    # would require resolving the path relative to the repo root.
    for fname, l1, l2 in _GOTCHA_FILE_LINE_RE.findall(real_block):
        if Path(fname).name != Path(script_name).name:
            continue  # cross-file anchor — see TODO above
        upper = int(l2) if l2 else int(l1)
        if upper > script_line_count:
            anchor = f"{fname}:{l1}" + (f"-{l2}" if l2 else "")
            errors.append(
                f"gotchas: anchor {anchor} exceeds {script_name} length "
                f"({script_line_count} lines)"
            )

    for full in _GOTCHA_RESULT_JSON_RE.findall(real_block):
        keys = _GOTCHA_RESULT_KEY_RE.findall(full)
        if keys and keys[0] not in script_text:
            errors.append(
                f'gotchas: result.json["{keys[0]}"] not referenced in '
                f"{script_name}"
            )

    for fname in _GOTCHA_TABLE_FIG_RE.findall(real_block):
        if fname not in script_text:
            errors.append(
                f"gotchas: '{fname}' not referenced in {script_name}"
            )

    return errors


# --- Check: allowed_extra_flags ⊇ argparse --------------------------------
#
# When the user invokes `omicsclaw.py run <skill> --foo bar`, the runner at
# `omicsclaw/core/skill_runner.py:354-378` filters out any --foo not listed
# in the sidecar's `allowed_extra_flags`.  Empty / partial lists silently
# drop user flags, producing wrong output with default parameters.  This
# regression class was discovered in PR-F (proteomics / metabolomics) and
# affects skills migrated in PR-D / PR-E too.

# Locate each `add_argument(` call so we can scan its body for every
# `--flag` literal — handles short+long pairs like `add_argument("-m",
# "--method")` and multi-line calls.  Requires literal `--` so single-dash
# short flags (e.g. `-m`) are correctly NOT captured.
_ADD_ARGUMENT_OPEN_RE = re.compile(r'add_argument\s*\(')
_FLAG_LITERAL_RE = re.compile(r'["\'](--[\w-]+)["\']')


def _extract_argparse_flags(script_text: str) -> set[str]:
    """Find every `--flag` literal inside an `add_argument(...)` call body.

    Walks the source balancing parens so `default=foo(bar)` and similar
    nested calls don't truncate the body early.
    """
    flags: set[str] = set()
    i = 0
    n = len(script_text)
    while i < n:
        match = _ADD_ARGUMENT_OPEN_RE.search(script_text, i)
        if not match:
            break
        body_start = match.end()
        depth = 1
        j = body_start
        while j < n and depth > 0:
            if script_text[j] == "(":
                depth += 1
            elif script_text[j] == ")":
                depth -= 1
            j += 1
        body = script_text[body_start: j - 1]
        for fm in _FLAG_LITERAL_RE.finditer(body):
            flags.add(fm.group(1))
        i = j
    return flags
_RUNNER_BLOCKED_FLAGS = frozenset({"--input", "--output", "--demo"})


def _check_allowed_extra_flags(skill_dir: Path, sidecar: dict) -> list[str]:
    """Verify `allowed_extra_flags` covers every script argparse flag.

    Excludes the runner-blocked trio (`--input`, `--output`, `--demo`),
    which never need to be listed.
    """
    errors: list[str] = []
    script_name = sidecar.get("script") or ""
    script_path = skill_dir / script_name if script_name else None
    if not (script_path and script_path.exists()):
        return []  # script not co-located — skip rather than false-fail
    script_text = script_path.read_text(encoding="utf-8")
    declared = _extract_argparse_flags(script_text) - _RUNNER_BLOCKED_FLAGS
    allowed = set(sidecar.get("allowed_extra_flags") or [])
    missing = declared - allowed
    extra = allowed - declared
    for flag in sorted(missing):
        errors.append(
            f"parameters.yaml: allowed_extra_flags missing '{flag}' — "
            f"declared in {script_name} via add_argument"
        )
    for flag in sorted(extra):
        errors.append(
            f"parameters.yaml: allowed_extra_flags lists '{flag}' but "
            f"{script_name} does not declare it via add_argument"
        )
    return errors


# --- Check: output_contract.md paths exist in the script ------------------
#
# `references/output_contract.md` is supposed to describe the files the
# script actually writes.  PR-F discovered that migrate_skill.py copies the
# legacy SKILL.md "Output Structure" section verbatim, so output_contract.md
# often lists files the script never touches.  This lint forces every
# `tables/X.csv` / `figures/X.png` / etc. mentioned in the contract to
# appear as a substring in the script (and any sibling `_lib/*.py`).

# Match file-shaped tokens with extension.  Multi-dot extensions like
# `checksums.sha256` and `archive.tar.gz` are listed BEFORE their shorter
# prefixes (regex alternation is leftmost — order matters).
_OUTPUT_CONTRACT_PATH_RE = re.compile(
    r"""
    `?
    (?:[a-z_<>-]+/)?       # optional parent dir
    (
        [a-zA-Z][\w._-]*    # filename stem
        \.
        (?:                 # extension — longest matches first
            tar\.gz | sha256 | h5ad | narrowPeak | broadPeak |
            fasta | fastq | json | jpeg | jpg | html |
            csv | tsv | png | svg | pdf | bed | gmt | sam | bam | vcf | txt |
            md  | sh  | fa
        )
    )
    `?
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Framework-standard files written by the common report helper (NOT by the
# skill script directly) — exempt from the substring check.  Also exempt
# self-referencing doc filenames that the migrate_skill.py header comment
# may accidentally surface.
_FRAMEWORK_FILES = frozenset({
    "report.md", "result.json",
    "commands.sh", "requirements.txt", "checksums.sha256",
    "processed.h5ad", "processed.bam",
    "SKILL.md", "output_contract.md", "parameters.md",
    "methodology.md", "r_visualization.md",
    "manifest.json",
})
# Strip HTML comments — migrate_skill.py prepends a `<!-- Generated ... -->`
# header that contains references to output_contract.md / SKILL.md which
# would otherwise be mis-counted as path claims.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# `from skills.<domain>._lib.<module> import ...` or
# `from .._lib.<module> import ...` — captures <module> only, used to
# scope the cross-file haystack search (avoid falsely-validating filenames
# that live in unrelated _lib siblings).
_LIB_IMPORT_RE = re.compile(
    r"from\s+(?:[\w.]+\._lib\.|\.+_lib\.)(\w+)\s+import"
)


def _check_output_contract_paths(skill_dir: Path, sidecar: dict) -> list[str]:
    """Verify every file path in output_contract.md is referenced in the script.

    Searches the script + any `_lib/*.py` siblings for the basename as a
    substring.  Framework-standard outputs (report.md, result.json,
    processed.h5ad, etc.) are exempt — those are written by the common
    report helper, not by the skill script directly.
    """
    errors: list[str] = []
    contract = skill_dir / "references" / "output_contract.md"
    if not contract.exists():
        return []  # missing-file already flagged by _check_references

    contract_text = _HTML_COMMENT_RE.sub("", contract.read_text(encoding="utf-8"))
    # Strip code-fence content?  No — code fences in output_contract.md are
    # the canonical "Output Structure" tree; the paths there ARE the claims.
    referenced_paths = {
        match.group(0).strip("`")
        for match in _OUTPUT_CONTRACT_PATH_RE.finditer(contract_text)
    }
    if not referenced_paths:
        return []  # nothing to validate

    script_name = sidecar.get("script") or ""
    script_path = skill_dir / script_name if script_name else None
    if not (script_path and script_path.exists()):
        return []  # script not co-located — skip rather than false-fail

    script_text = script_path.read_text(encoding="utf-8")
    haystack = script_text
    # Also scan _lib/<X>.py — but ONLY the modules the script actually
    # imports.  Otherwise spatial-domains' contract gets validated against
    # _lib/communication.py, _lib/cnv.py, etc., and the lint passes for
    # filenames that no spatial-domains output ever writes.  Walk up to the
    # `skills/<domain>/` boundary so two-deep trees (singlecell/scrna/X)
    # find _lib at the domain root.
    imported_lib_names = set(_LIB_IMPORT_RE.findall(script_text))
    for parent in (skill_dir, *skill_dir.parents):
        lib_dir = parent / "_lib"
        if lib_dir.is_dir():
            for lib_py in sorted(lib_dir.glob("*.py")):
                if lib_py.stem in imported_lib_names:
                    haystack += "\n" + lib_py.read_text(encoding="utf-8")
        if parent.name == "skills":
            break

    for path in sorted(referenced_paths):
        basename = path.rsplit("/", 1)[-1]
        if basename in _FRAMEWORK_FILES:
            continue
        if basename not in haystack:
            errors.append(
                f"output_contract.md: '{path}' not referenced in "
                f"{script_name} (or sibling _lib/*.py)"
            )
    return errors


def _check_references(skill_dir: Path, sidecar: dict) -> list[str]:
    errors: list[str] = []
    refs = skill_dir / "references"
    for name in REQUIRED_REFERENCES:
        if not (refs / name).exists():
            errors.append(f"references/{name}: missing")
    params_md = refs / "parameters.md"
    if params_md.exists():
        expected = render_parameters_md(sidecar)
        if params_md.read_text(encoding="utf-8") != expected:
            errors.append(
                "references/parameters.md: stale — regenerate with "
                "scripts/generate_parameters_md.py"
            )
    return errors


def lint_skill(skill_dir: Path) -> list[str]:
    """Return a list of lint errors for one skill directory.

    Empty list = clean.  Legacy skills (no parameters.yaml) always return [].
    """
    parsed = _parse_skill_md(skill_dir)
    if parsed is None:
        return [f"{skill_dir}: SKILL.md missing or unparseable"]
    frontmatter, body = parsed

    sidecar_path = skill_dir / "parameters.yaml"
    if not sidecar_path.exists():
        return []  # legacy skill — defer until migrated

    try:
        sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"parameters.yaml: invalid YAML ({exc})"]

    errors: list[str] = []
    errors.extend(_check_description(frontmatter.get("description", "")))
    errors.extend(_check_body(body))
    errors.extend(_check_frontmatter_keys(frontmatter))
    errors.extend(_check_sidecar(sidecar))
    errors.extend(_check_references(skill_dir, sidecar))
    errors.extend(_check_gotchas_anchors(skill_dir, body, sidecar))
    errors.extend(_check_allowed_extra_flags(skill_dir, sidecar))
    errors.extend(_check_output_contract_paths(skill_dir, sidecar))
    return errors


def discover_skills(skills_root: Path) -> list[Path]:
    """Every directory containing a SKILL.md, recursively."""
    return sorted(p.parent for p in skills_root.rglob("SKILL.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="(reserved — currently same as default)")
    args = parser.parse_args()

    if args.all == bool(args.skill_dir):
        parser.error("provide either <skill_dir> or --all")

    from omicsclaw.core.registry import SKILLS_DIR

    targets = discover_skills(SKILLS_DIR) if args.all else [args.skill_dir]

    total_errors = 0
    for skill_dir in targets:
        errors = lint_skill(skill_dir)
        if errors:
            print(f"FAIL {skill_dir}")
            for err in errors:
                print(f"  - {err}")
            total_errors += len(errors)
        else:
            print(f"ok   {skill_dir}")

    if total_errors:
        print(f"\n{total_errors} error(s) across {len(targets)} skill(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
