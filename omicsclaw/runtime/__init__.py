"""Shared runtime primitives for OmicsClaw adapters.

The framework rebuild tore the old agent stack out of this package. What
used to live here — ``agent/`` (dispatch loop), ``context/`` (prompt
assembly, compaction, budgets, layers), ``tools/`` (spec, registry,
execution, hooks) and ``storage/`` (transcript / tool-result / task
stores) — is being replaced by the top-level ``omicsclaw.engine``,
``omicsclaw.tools`` and the context and memory layers still to come.

Only ``output_styles`` survives the teardown with no dependency on the
removed stack, so it is the whole re-exported surface. ``consensus/`` and
``workflow/`` remain as sub-packages and are imported directly.
"""

from .output_styles import (
    DEFAULT_OUTPUT_STYLE,
    PIPELINE_OPERATOR_OUTPUT_STYLE,
    REPORT_REVIEW_OUTPUT_STYLE,
    SCIENTIFIC_BRIEF_OUTPUT_STYLE,
    TEACHING_OUTPUT_STYLE,
    OutputStyleProfile,
    build_output_style_registry,
    get_builtin_output_style_profiles,
    get_output_style_profiles,
    normalize_output_style_name,
    normalize_output_style_surface,
    render_output_style_layer,
    resolve_output_style_profile,
)

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
