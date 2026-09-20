"""Output style registry and rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_OUTPUT_STYLE = "default"
SCIENTIFIC_BRIEF_OUTPUT_STYLE = "scientific-brief"
TEACHING_OUTPUT_STYLE = "teaching"
PIPELINE_OPERATOR_OUTPUT_STYLE = "pipeline-operator"
REPORT_REVIEW_OUTPUT_STYLE = "report-review"

_SUPPORTED_SURFACES = frozenset({"interactive", "bot", "pipeline"})
_SURFACE_ALIASES = {
    "cli": "interactive",
    "tui": "interactive",
}
_SURFACE_ADAPTERS = {
    "interactive": (
        "- Optimize for terminal/plain-text readability.\n"
        "- Prefer short sections and flat lists over dense markdown.\n"
        "- Avoid decorative tables, callout boxes, and emoji."
    ),
    "bot": (
        "- Markdown is acceptable when it improves scanability.\n"
        "- Keep replies compact enough for chat clients and notifications.\n"
        "- Use emphasis sparingly; avoid decorative formatting."
    ),
    "pipeline": (
        "- Prioritize operational clarity over narration.\n"
        "- Surface status, artifacts, blockers, approvals, and next actions explicitly.\n"
        "- Keep wording stable enough for logs, transcripts, and hand-offs."
    ),
}


@dataclass(frozen=True, slots=True)
class OutputStyleProfile:
    name: str
    description: str
    instructions: str
    source: str = "builtin"
    aliases: tuple[str, ...] = ()
    supported_surfaces: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports(self, surface: str) -> bool:
        normalized_surface = normalize_output_style_surface(surface)
        if not self.supported_surfaces:
            return normalized_surface in _SUPPORTED_SURFACES
        return normalized_surface in self.supported_surfaces


def normalize_output_style_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    normalized = normalized.replace("_", "-").replace(" ", "-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-")


def normalize_output_style_surface(surface: str | None) -> str:
    normalized = str(surface or "").strip().lower()
    if not normalized:
        return "interactive"
    return _SURFACE_ALIASES.get(normalized, normalized)


_BUILTIN_OUTPUT_STYLE_PROFILES = (
    OutputStyleProfile(
        name=DEFAULT_OUTPUT_STYLE,
        description="Balanced default for concise, precise scientific assistance.",
        instructions=(
            "- Lead with the answer, action, or conclusion.\n"
            "- Keep structure compact with short paragraphs or flat lists.\n"
            "- Preserve exact file paths, warnings, counts, and numerical results.\n"
            "- Avoid decorative flourishes and redundant restatement."
        ),
    ),
    OutputStyleProfile(
        name=SCIENTIFIC_BRIEF_OUTPUT_STYLE,
        description="Terse, evidence-led scientific delivery with minimal narration.",
        instructions=(
            "- Put the core result, confidence, and key limitation first.\n"
            "- Prefer precise technical wording over conversational filler.\n"
            "- Use method names, gene names, and metrics verbatim.\n"
            "- Keep explanations short unless the user asks for depth."
        ),
    ),
    OutputStyleProfile(
        name=TEACHING_OUTPUT_STYLE,
        description="Explanatory mode for users who want rationale and terminology support.",
        instructions=(
            "- Explain the reasoning step by step when it materially helps understanding.\n"
            "- Define specialized jargon the first time it appears.\n"
            "- Use short examples or decision rules when helpful.\n"
            "- End with the immediate next action or takeaway."
        ),
    ),
    OutputStyleProfile(
        name=PIPELINE_OPERATOR_OUTPUT_STYLE,
        description="Operational status mode for multi-step execution and workflow tracking.",
        instructions=(
            "- Start with status, current step, and blocking issues.\n"
            "- Use explicit labels for inputs, outputs, artifacts, and next action.\n"
            "- Prefer checklist-like updates over narrative prose.\n"
            "- Highlight approvals, failures, retries, and ownership clearly."
        ),
    ),
    OutputStyleProfile(
        name=REPORT_REVIEW_OUTPUT_STYLE,
        description="Findings-first review mode for risks, regressions, and validation gaps.",
        instructions=(
            "- Present findings first, ordered by severity.\n"
            "- Include concrete evidence and user-visible impact for each finding.\n"
            "- Mention missing tests, residual risks, or assumptions explicitly.\n"
            "- Keep summaries secondary to findings."
        ),
    ),
)


def get_builtin_output_style_profiles() -> tuple[OutputStyleProfile, ...]:
    return _BUILTIN_OUTPUT_STYLE_PROFILES


def get_output_style_profiles(
    omicsclaw_dir: str | None = None,
) -> tuple[OutputStyleProfile, ...]:
    """Return every output style this deployment offers.

    ``omicsclaw_dir`` used to select extension packs on top of the
    built-ins; ``omicsclaw/extensions/`` was removed with the old stack,
    so the built-ins are now the whole set. The parameter is kept because
    callers pass it positionally and a style source may return.
    """
    return get_builtin_output_style_profiles()


def build_output_style_registry(
    omicsclaw_dir: str | None = None,
) -> dict[str, OutputStyleProfile]:
    registry: dict[str, OutputStyleProfile] = {}
    for profile in get_output_style_profiles(omicsclaw_dir):
        registry.setdefault(profile.name, profile)
        for alias in profile.aliases:
            registry.setdefault(alias, profile)
    return registry


def resolve_output_style_profile(
    style_name: str | None,
    *,
    omicsclaw_dir: str | None = None,
    surface: str | None = None,
) -> OutputStyleProfile:
    registry = build_output_style_registry(omicsclaw_dir)
    normalized_name = normalize_output_style_name(style_name)
    profile = registry.get(normalized_name)
    if profile is None:
        profile = registry[DEFAULT_OUTPUT_STYLE]

    normalized_surface = normalize_output_style_surface(surface)
    if profile.supports(normalized_surface):
        return profile
    return registry[DEFAULT_OUTPUT_STYLE]


def render_output_style_layer(
    *,
    style_name: str | None,
    surface: str | None,
    omicsclaw_dir: str | None = None,
) -> str:
    requested_name = normalize_output_style_name(style_name)
    normalized_surface = normalize_output_style_surface(surface)
    profile = resolve_output_style_profile(
        requested_name,
        omicsclaw_dir=omicsclaw_dir,
        surface=normalized_surface,
    )
    adapter = _SURFACE_ADAPTERS.get(normalized_surface, "")

    lines = [
        "## Output Style Profile",
        "",
        f"Active style: `{profile.name}`",
        f"Description: {profile.description}",
        "- Output style changes presentation only. Do not change scientific constraints, safety boundaries, or exact results.",
        "",
        "### Style Directives",
        profile.instructions.strip(),
    ]

    if adapter:
        lines.extend(
            (
                "",
                f"### Surface Adapter ({normalized_surface})",
                adapter,
            )
        )

    if requested_name and requested_name not in {profile.name, *profile.aliases}:
        lines.extend(
            (
                "",
                f"Requested style `{requested_name}` is unavailable here. Use `{profile.name}` instead.",
            )
        )

    if profile.source != "builtin":
        lines.extend(
            (
                "",
                f"Style source: {profile.source}",
            )
        )

    lines.extend(
        (
            "",
            "### Output Efficiency",
            "- Lead with the answer or the action; the reasoning, if needed, comes after.",
            "- If you can say it in one sentence, don't use three. Skip filler transitions.",
            "- Reserve text output for: (a) decisions needing user input, (b) status at natural milestones, (c) errors or blockers that change the plan.",
            "- This brevity rule applies to your prose only — code blocks and tool-call arguments stay as detailed as the work requires.",
        )
    )

    return "\n".join(lines).strip()


__all__ = [
    "DEFAULT_OUTPUT_STYLE",
    "PIPELINE_OPERATOR_OUTPUT_STYLE",
    "REPORT_REVIEW_OUTPUT_STYLE",
    "SCIENTIFIC_BRIEF_OUTPUT_STYLE",
    "TEACHING_OUTPUT_STYLE",
    "OutputStyleProfile",
    "build_output_style_registry",
    "get_builtin_output_style_profiles",
    "get_output_style_profiles",
    "normalize_output_style_name",
    "normalize_output_style_surface",
    "render_output_style_layer",
    "resolve_output_style_profile",
]
