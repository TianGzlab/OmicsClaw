"""Harness directive — Meta-Agent prompt for code-level evolution.

Unlike ``directive.py`` (parameter optimization), this builds a prompt
that tells the Meta-Agent it can *modify code* within a bounded editable
surface.  The directive includes:

1. **Role & Goal** — you are a harness engineer evolving skill code.
2. **Editable surface** — which files you may modify and why.
3. **Current source code** — the content of each editable file.
4. **Trace diagnostics** — the RunTrace from the latest trial(s).
5. **Hard gate results** — which gates passed/failed.
6. **Failure history** — prior failed patches to avoid repeating.
7. **Output format** — structured JSON with patch plan + unified diff.
"""

from __future__ import annotations

from typing import Any

from omicsclaw.autoagent.edit_surface import EditSurface
from omicsclaw.autoagent.hard_gates import HardGateVerdict
from omicsclaw.autoagent.trace import RunTrace


def build_harness_directive(
    skill_name: str,
    method: str,
    surface: EditSurface,
    traces: list[RunTrace],
    gate_verdict: HardGateVerdict | None = None,
    failure_history: list[dict[str, Any]] | None = None,
    iteration: int = 0,
    max_iterations: int = 10,
    evolution_goal: str = "",
) -> str:
    """Build the full harness directive for the Meta-Agent.

    Parameters
    ----------
    skill_name:
        The target skill being evolved.
    method:
        The method variant (e.g. "scanpy").
    surface:
        The editable surface defining which files can be modified.
    traces:
        RunTrace objects from recent trial(s). Last is most recent.
    gate_verdict:
        Hard gate results from the most recent trial.
    failure_history:
        Summaries of prior failed patches (from failure_bank.jsonl).
    iteration:
        Current iteration number in the harness loop.
    max_iterations:
        Maximum iterations allowed.
    evolution_goal:
        Optional specific evolution objective (e.g. "upgrade QC to
        data-driven filtering").
    """
    sections = [
        _section_role(skill_name, method, evolution_goal),
        _section_editable_surface(surface),
        _section_source_code(surface),
        _section_trace_diagnostics(traces),
    ]

    method_scope = _section_method_scope(surface)
    if method_scope:
        sections.insert(1, method_scope)

    if gate_verdict is not None:
        sections.append(_section_hard_gates(gate_verdict))

    if failure_history:
        sections.append(_section_failure_history(failure_history))

    sections.append(_section_constraints())
    sections.append(_section_output_format())
    sections.append(_section_budget(iteration, max_iterations))

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Directive sections
# ---------------------------------------------------------------------------


def _section_role(skill_name: str, method: str, goal: str) -> str:
    goal_text = goal or (
        f"Improve the robustness, correctness, and quality of the "
        f"**{skill_name}** skill (method: **{method}**)."
    )
    return f"""## Role

You are a **harness engineer** for OmicsClaw — a multi-omics AI agent.

Unlike a parameter optimizer, you modify **source code** within a bounded
editable surface.  Your changes are tested in a sandbox; if they pass hard
gates and improve quality metrics, they are committed.  If they fail, they
are reverted and recorded in the failure bank.

### Evolution Goal

{goal_text}

### Principles

- **Bounded edits**: Only modify files listed in the editable surface.
- **Baseline-first**: The unmodified code runs first; you improve on it.
- **Minimal diff**: Prefer small, targeted changes over broad rewrites.
- **Simplicity wins**: At equal quality, the smaller patch is preferred.
- **Never break contracts**: Skill output format, CLI interface, and
  import structure must be preserved."""


def _section_editable_surface(surface: EditSurface) -> str:
    return f"""## Editable Surface

You may ONLY modify files within this boundary:

{surface.describe()}

Any file outside this surface is **frozen** — do not reference it in
your patch.  If you need to change frozen infrastructure, explain why
in your reasoning and the system will flag it for human review."""


def _section_method_scope(surface: EditSurface) -> str:
    method_focus = surface.metadata.get("method_focus")
    if not isinstance(method_focus, dict):
        return ""

    focus_method = str(method_focus.get("method", "") or "").strip()
    focus_targets = method_focus.get("focus_targets", {})
    if not focus_method or not isinstance(focus_targets, dict):
        return ""

    lines = [
        "## Method Scope",
        "",
        f"Current target method: **{focus_method}**.",
        "",
        "Keep edits centered on these regions:",
    ]
    for rel_path, targets in focus_targets.items():
        if not targets:
            continue
        lines.append(f"- `{rel_path}`: {', '.join(str(t) for t in targets)}")
    lines.append(
        "- In shared multi-method files, do not modify unrelated algorithm "
        "implementations unless a shared helper directly affects the target method."
    )
    return "\n".join(lines)


def _section_source_code(surface: EditSurface) -> str:
    """Include the current content of each editable file."""
    lines = ["## Current Source Code", ""]

    files = surface.explicit_files
    if not files:
        # Enumerate from levels (less precise, but usable)
        lines.append(
            "(No explicit file list — use level patterns to identify "
            "target files.)"
        )
        return "\n".join(lines)

    for rel_path in files:
        lines.append(f"### `{rel_path}`")
        lines.append("")
        try:
            content = surface.read_prompt_file(rel_path)
            if surface.has_prompt_view(rel_path):
                lines.append(
                    "*Method-focused excerpt for the current target. "
                    "Unrelated sections omitted.*"
                )
            # Truncate very large files to avoid blowing up the prompt
            if len(content) > 15000:
                content = content[:15000] + "\n\n... (truncated at 15000 chars)"
            lines.append(f"```python\n{content}\n```")
        except (FileNotFoundError, PermissionError) as exc:
            lines.append(f"*Could not read: {exc}*")
        lines.append("")

    return "\n".join(lines)


def _section_trace_diagnostics(traces: list[RunTrace]) -> str:
    if not traces:
        return (
            "## Trial Diagnostics\n\n"
            "No trials have been run yet — this will be the baseline."
        )

    lines = ["## Trial Diagnostics", ""]

    # Show the most recent trace in detail, older ones summarized
    for trace in traces[-3:]:  # at most 3 recent traces
        lines.append(trace.to_diagnostic_summary())
        lines.append("---")

    return "\n".join(lines)


def _section_hard_gates(verdict: HardGateVerdict) -> str:
    return f"""## Hard Gate Results

{verdict.to_diagnostic()}

{verdict.summary()}"""


def _section_failure_history(failures: list[dict[str, Any]]) -> str:
    lines = [
        "## Failure History",
        "",
        "These patches were tried before and failed. Do NOT repeat them:",
        "",
    ]

    for i, fail in enumerate(failures[-5:], 1):  # at most 5 recent
        lines.append(f"### Failed Patch #{i}")
        if "reasoning" in fail:
            lines.append(f"Intent: {fail['reasoning']}")
        if "gate_failures" in fail:
            lines.append(f"Gate failures: {', '.join(fail['gate_failures'])}")
        if "error_summary" in fail:
            lines.append(f"Error: {fail['error_summary']}")
        if "diff_summary" in fail:
            lines.append(f"Diff: {fail['diff_summary']}")
        lines.append("")

    return "\n".join(lines)


def _section_constraints() -> str:
    return """## Constraints

1. **Preserve skill CLI interface**: ``--input``, ``--output``, ``--method``,
   ``--demo`` must keep working.
2. **Preserve output contract**: ``processed.h5ad``, ``result.json``,
   ``report.md``, ``figures/`` must still be produced.
3. **No new dependencies**: Do not import packages not already in the
   project's requirements.
4. **Backward compatibility**: Existing parameters must still work.
   New parameters should have sensible defaults.
5. **Logging**: Use ``logger.info()`` / ``logger.warning()`` for
   significant decisions (especially fallbacks).
6. **Type safety**: Add type hints to new code.
7. **Method focus**: When a skill file contains multiple algorithms,
   optimize only the requested method and shared helpers that directly
   affect it."""


def _section_output_format() -> str:
    return """## Output Format

Respond with **only** a JSON object:

```json
{
  "patch_plan": {
    "target_files": ["relative/path/to/file.py"],
    "description": "Brief description of what this patch does.",
    "expected_improvements": ["improvement 1", "improvement 2"],
    "rollback_conditions": ["condition that should trigger revert"]
  },
  "diffs": [
    {
      "file": "relative/path/to/file.py",
      "hunks": [
        {
          "old_code": "exact lines to replace (verbatim from source)",
          "new_code": "replacement lines"
        }
      ]
    }
  ],
  "reasoning": "Why this change should improve quality."
}
```

Or, if you believe the code has converged:

```json
{
  "converged": true,
  "reasoning": "Why further changes are unlikely to help."
}
```

**Critical rules for diffs**:
- ``old_code`` must be an **exact** substring of the current file content.
- Each hunk replaces one contiguous block of code.
- Do not include line numbers — use the exact text.
- Prefer small, targeted hunks over rewriting entire functions."""


def _section_budget(iteration: int, max_iterations: int) -> str:
    remaining = max(0, max_iterations - iteration)
    return (
        f"## Budget\n\n"
        f"Iteration: {iteration} / {max_iterations}.  "
        f"Remaining: {remaining}.  Make each iteration count."
    )
