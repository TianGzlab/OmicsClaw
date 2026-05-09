"""Tool → predicate mapping for the lazy-load tool list (Phase 1).

Centralizes the predicate that gates each non-always-on tool so the
mapping is inspectable in one file rather than scattered across 33
``ToolSpec(...)`` constructors. The 8 always-on tools are deliberately
absent from this map — their ``predicate`` stays ``None`` (always-on).

Always-on (predicate=None):
    omicsclaw, resolve_capability, consult_knowledge, inspect_data,
    list_directory, glob_files, file_read, read_knowhow

The 33 lazy-load tools below cover all remaining registered tools.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Callable

from . import predicates as _pred
from .context_layers import ContextAssemblyRequest
from .tool_spec import ToolSpec

# --- Custom narrow predicates for niche tools --------------------------------

_AUDIO_KEYWORDS_RE = re.compile(
    r"\b(audio|podcast|voice|narration|speak|tts)\b|音频|播客|语音",
    re.IGNORECASE,
)

def _audio_intent(req: ContextAssemblyRequest) -> bool:
    return bool(_AUDIO_KEYWORDS_RE.search(req.query or ""))


# --- The mapping -------------------------------------------------------------

TOOL_PREDICATE_MAP: dict[str, Callable[[ContextAssemblyRequest], bool]] = {
    # File operations → anndata_or_file_path_in_query
    "save_file": _pred.anndata_or_file_path_in_query,
    "write_file": _pred.anndata_or_file_path_in_query,
    "inspect_file": _pred.anndata_or_file_path_in_query,
    "make_directory": _pred.anndata_or_file_path_in_query,
    "move_file": _pred.anndata_or_file_path_in_query,
    "remove_file": _pred.anndata_or_file_path_in_query,
    "get_file_size": _pred.anndata_or_file_path_in_query,
    "file_write": _pred.anndata_or_file_path_in_query,
    "file_edit": _pred.anndata_or_file_path_in_query,
    "grep_files": _pred.anndata_or_file_path_in_query,
    "tool_search": _pred.anndata_or_file_path_in_query,
    # PDF / paper → pdf_or_paper_intent
    "parse_literature": _pred.pdf_or_paper_intent,
    "fetch_geo_metadata": _pred.pdf_or_paper_intent,
    # Memory → memory_in_use
    "remember": _pred.memory_in_use,
    "recall": _pred.memory_in_use,
    "forget": _pred.memory_in_use,
    # Implementation intent → custom code execution
    "custom_analysis_execute": _pred.implementation_intent,
    # Workspace continuity → todo / task tools
    "todo_write": _pred.workspace_active,
    "task_create": _pred.workspace_active,
    "task_get": _pred.workspace_active,
    "task_list": _pred.workspace_active,
    "task_update": _pred.workspace_active,
    # Routing helper → list_skills_in_domain (only when capability missing)
    "list_skills_in_domain": _pred.non_trivial_no_capability,
    # Plot intent → replot_skill
    "replot_skill": _pred.plot_intent,
    # Web / URL → web fetch + search family
    "web_method_search": _pred.web_or_url_intent,
    "web_fetch": _pred.web_or_url_intent,
    "web_search": _pred.web_or_url_intent,
    # Skill creation → create_omics_skill
    "create_omics_skill": _pred.skill_creation_intent,
    # Niche tools — narrow custom predicates
    "generate_audio": _audio_intent,
}


def attach_predicates(specs: tuple[ToolSpec, ...]) -> tuple[ToolSpec, ...]:
    """Return a new spec tuple with ``predicate`` populated from
    ``TOOL_PREDICATE_MAP``. Specs whose name is absent from the map keep
    ``predicate=None`` (always-on).
    """
    return tuple(
        dataclasses.replace(spec, predicate=TOOL_PREDICATE_MAP[spec.name])
        if spec.name in TOOL_PREDICATE_MAP
        else spec
        for spec in specs
    )


__all__ = [
    "TOOL_PREDICATE_MAP",
    "attach_predicates",
]
