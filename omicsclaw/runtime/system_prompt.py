from __future__ import annotations

from pathlib import Path

from .context_assembler import assemble_prompt_context
from .context_layers import (
    DEFAULT_SOUL_MD,
    ContextAssemblyRequest,
    load_base_persona,
)


def build_system_prompt(
    memory_context: str = "",
    scoped_memory_context: str = "",
    skill_context: str = "",
    skill: str = "",
    skill_candidates: tuple[str, ...] = (),
    query: str = "",
    domain: str = "",
    capability_context: str = "",
    plan_context: str = "",
    prompt_pack_context: str = "",
    knowledge_context: str = "",
    transcript_context: str = "",
    soul_md: Path = DEFAULT_SOUL_MD,
    *,
    surface: str = "bot",
    output_style: str = "",
    omicsclaw_dir: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    mcp_servers: tuple[object, ...] | list[object] | None = None,
    base_persona: str = "",
    include_knowhow: bool | None = None,
    include_knowledge_guidance: bool | None = None,
    include_extension_prompt_packs: bool = True,
    workspace_placement: str = "system",
) -> str:
    prompt_context = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface=surface,
            omicsclaw_dir=omicsclaw_dir,
            base_persona=base_persona,
            output_style=output_style,
            memory_context=memory_context,
            skill_context=skill_context,
            scoped_memory_context=scoped_memory_context,
            skill=skill,
            skill_candidates=skill_candidates,
            query=query,
            domain=domain,
            capability_context=capability_context,
            plan_context=plan_context,
            prompt_pack_context=prompt_pack_context,
            knowledge_context=knowledge_context,
            transcript_context=transcript_context,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
            mcp_servers=tuple(mcp_servers or ()),
            soul_md=soul_md,
            include_knowhow=include_knowhow,
            include_knowledge_guidance=include_knowledge_guidance,
            include_extension_prompt_packs=include_extension_prompt_packs,
            workspace_placement=workspace_placement,
        )
    )
    return prompt_context.system_prompt


__all__ = [
    "DEFAULT_SOUL_MD",
    "build_system_prompt",
    "load_base_persona",
]
