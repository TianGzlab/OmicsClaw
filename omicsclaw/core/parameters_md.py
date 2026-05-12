"""Render `references/parameters.md` from a v2 skill's `parameters.yaml` dict.

Lives in the package so that both consumers — `scripts/skill_lint.py` (which
diffs the rendered output against the on-disk reference) and
`omicsclaw/core/skill_scaffolder.py` (which writes the rendered output for
freshly-scaffolded skills) — can import it directly, without mutating
`sys.path` to reach into `scripts/`.

`scripts/generate_parameters_md.py` re-exports `render_parameters_md` and
owns the CLI wrapper.  The function below is the single source of truth.
"""

from __future__ import annotations


AUTOGEN_HEADER = (
    "<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->\n"
    "<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->\n\n"
)


def render_parameters_md(sidecar: dict) -> str:
    """Render a parameters.yaml dict to the canonical markdown layout.

    Empty / missing fields render as informative one-liners so a reader
    always knows whether the absence is intentional.
    """
    lines: list[str] = [AUTOGEN_HEADER, "# Parameters\n"]

    flags = sidecar.get("allowed_extra_flags", []) or []
    lines.append("## Allowed extra CLI flags\n")
    if flags:
        for flag in flags:
            lines.append(f"- `{flag}`")
    else:
        lines.append("_No extra flags beyond the standard `--input` / `--output` / `--demo` set._")
    lines.append("")

    lines.append("## Per-method parameter hints\n")
    hints: dict = sidecar.get("param_hints", {}) or {}
    if not hints:
        lines.append("_No method-specific tuning hints._\n")
        return "\n".join(lines).rstrip() + "\n"

    for method in sorted(hints):
        info = hints[method] or {}
        lines.append(f"### `{method}`\n")

        priority = info.get("priority")
        if priority:
            lines.append(f"**Tuning priority:** {priority}\n")

        for label, key in (("Core parameters", "params"), ("Advanced parameters", "advanced_params")):
            params = info.get(key) or []
            if params:
                lines.append(f"**{label}:**")
                lines.append("")
                lines.append("| name | default |")
                lines.append("|---|---|")
                defaults = info.get("defaults", {}) or {}
                for p in params:
                    dval = defaults.get(p, "—")
                    lines.append(f"| `{p}` | `{dval}` |")
                lines.append("")

        requires = info.get("requires") or []
        if requires:
            lines.append("**Requires:**")
            for r in requires:
                lines.append(f"- `{r}`")
            lines.append("")

        tips = info.get("tips") or []
        if tips:
            lines.append("**Tips:**")
            for t in tips:
                lines.append(f"- {t}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
