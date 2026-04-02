from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass
from typing import Any

from omicsclaw.core.registry import registry

from .context_layers import (
    ContextAssemblyRequest,
    ContextLayer,
    ContextLayerInjector,
    get_default_context_injectors,
)

registry.load_all()

LOGGER = logging.getLogger("omicsclaw.runtime.context")

_DOMAIN_KEYWORDS = {
    "bulkrna": [
        "deseq2", "edger", "limma", "bulk rna", "bulk-rna",
        "differential expression", "rnaseq", "rna-seq", "deg",
        "差异表达", "差异基因", "差异分析",
    ],
    "singlecell": [
        "single cell", "single-cell", "scrna", "scanpy",
        "seurat", "scvi", "cellranger", "10x",
        "单细胞", "单细胞测序",
    ],
    "spatial": [
        "spatial", "visium", "merfish", "slide-seq", "stereo-seq",
        "10x visium", "squidpy",
        "空间转录组", "空间组学",
    ],
    "genomics": [
        "variant", "gwas", "vcf", "plink", "crispr", "depmap",
        "essentiality", "genomic",
        "基因组", "变异", "遗传变异",
    ],
    "proteomics": [
        "proteomic", "mass spec", "peptide", "maxquant",
        "蛋白质组", "蛋白组学",
    ],
    "metabolomics": [
        "metabolomic", "xcms", "mzml", "metabolite",
        "代谢组", "代谢物",
    ],
}


@dataclass(frozen=True, slots=True)
class PromptContextAssembly:
    request: ContextAssemblyRequest
    layers: tuple[ContextLayer, ...]

    def layers_for(self, placement: str) -> tuple[ContextLayer, ...]:
        normalized = str(placement or "").strip().lower()
        return tuple(layer for layer in self.layers if layer.placement == normalized)

    @property
    def system_layers(self) -> tuple[ContextLayer, ...]:
        return self.layers_for("system")

    @property
    def message_layers(self) -> tuple[ContextLayer, ...]:
        return self.layers_for("message")

    @property
    def attachment_layers(self) -> tuple[ContextLayer, ...]:
        return self.layers_for("attachment")

    @property
    def system_prompt(self) -> str:
        return _render_layers(self.system_layers)

    @property
    def message_context(self) -> str:
        return _render_layers(self.message_layers)

    @property
    def attachment_context(self) -> str:
        return _render_layers(self.attachment_layers)

    @property
    def total_estimated_tokens(self) -> int:
        return sum(layer.estimated_tokens for layer in self.layers)

    @property
    def total_chars(self) -> int:
        return sum(layer.cost_chars for layer in self.layers)

    @property
    def layer_names(self) -> tuple[str, ...]:
        return tuple(layer.name for layer in self.layers)

    @property
    def layer_stats(self) -> dict[str, dict[str, Any]]:
        return {
            layer.name: {
                "placement": layer.placement,
                "order": layer.order,
                "cost_chars": layer.cost_chars,
                "estimated_tokens": layer.estimated_tokens,
            }
            for layer in self.layers
        }


@dataclass(frozen=True, slots=True)
class AssembledChatContext:
    session_id: str | None
    memory_context: str
    scoped_memory_context: str
    user_text: str
    user_message_content: str | list[dict[str, Any]]
    skill_hint: str
    domain_hint: str
    capability_context: str
    prompt_context: PromptContextAssembly
    system_prompt: str


def _render_layers(layers: tuple[ContextLayer, ...]) -> str:
    return "\n\n".join(layer.content for layer in layers if layer.content).strip()


def message_mentions_term(text: str, term: str) -> bool:
    term = (term or "").strip().lower()
    if not term:
        return False
    if len(term) <= 3 and term.replace("-", "").replace("_", "").isalnum():
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        return bool(re.search(pattern, text))
    return term in text


def should_attach_capability_context(
    text: str,
    *,
    skill_aliases: tuple[str, ...] | None = None,
) -> bool:
    if not text:
        return False

    lower = text.lower()
    aliases = skill_aliases or tuple(registry.skills.keys())
    if any(message_mentions_term(lower, alias.lower()) for alias in aliases):
        return True

    return bool(
        re.search(r"\.(h5ad|h5|loom|mzml|fastq|fq|bam|vcf|csv|tsv)\b", lower)
        or any(
            kw in lower
            for kw in (
                "analy",
                "create skill",
                "add skill",
                "scaffold",
                "创建 skill",
                "封装成skill",
                "preprocess",
                "qc",
                "cluster",
                "differential",
                "deconvolution",
                "trajectory",
                "velocity",
                "enrichment",
                "survival",
                "空间",
                "单细胞",
            )
        )
    )


def extract_analysis_hints(
    text: str,
    *,
    skill_aliases: tuple[str, ...] | None = None,
) -> tuple[str, str]:
    if not text:
        return "", ""

    text_lower = text.lower()
    aliases = skill_aliases or tuple(registry.skills.keys())

    skill_hint = ""
    for alias in aliases:
        if message_mentions_term(text_lower, alias.lower()):
            skill_hint = alias
            break

    domain_hint = ""
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            domain_hint = domain
            break

    return skill_hint, domain_hint


def extract_user_text(user_content: str | list[dict[str, Any]]) -> str:
    if isinstance(user_content, str):
        return user_content
    return " ".join(
        block.get("text", "")
        for block in (user_content or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def build_user_message_content(
    user_content: str | list[dict[str, Any]],
    *,
    message_context: str = "",
) -> str | list[dict[str, Any]]:
    message_context = str(message_context or "").strip()

    if isinstance(user_content, str):
        if not message_context:
            return user_content
        return "\n\n".join(
            part
            for part in (
                message_context,
                "## User Request",
                user_content,
            )
            if part
        )

    oai_parts: list[dict[str, Any]] = []
    if message_context:
        oai_parts.append({"type": "text", "text": message_context})
    for block in user_content:
        if block.get("type") == "text":
            oai_parts.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "image":
            src = block.get("source", {})
            data_uri = f"data:{src['media_type']};base64,{src['data']}"
            oai_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                }
            )
    return oai_parts


def _default_capability_resolver(query: str, *, domain_hint: str = ""):
    from omicsclaw.core.capability_resolver import resolve_capability

    return resolve_capability(query, domain_hint=domain_hint)


def _invoke_legacy_prompt_builder(prompt_builder, **kwargs) -> str:
    try:
        signature = inspect.signature(prompt_builder)
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            return prompt_builder(**kwargs)
        accepted = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
        return prompt_builder(**accepted)
    except (TypeError, ValueError):
        return prompt_builder(**kwargs)


def assemble_prompt_context(
    *,
    request: ContextAssemblyRequest | None = None,
    injectors: tuple[ContextLayerInjector, ...] | None = None,
    **request_kwargs,
) -> PromptContextAssembly:
    current_request = request or ContextAssemblyRequest(**request_kwargs)
    selected_layers: list[ContextLayer] = []

    for injector in injectors or get_default_context_injectors():
        if not injector.applies(current_request):
            continue
        layer = injector.render(current_request)
        if layer is not None:
            selected_layers.append(layer)

    selected_layers.sort(key=lambda layer: (layer.order, layer.name))
    return PromptContextAssembly(
        request=current_request,
        layers=tuple(selected_layers),
    )


async def assemble_chat_context(
    *,
    chat_id: int | str,
    user_content: str | list[dict[str, Any]],
    user_id: str | None = None,
    platform: str | None = None,
    session_manager=None,
    system_prompt_builder=None,
    capability_resolver=None,
    skill_aliases: tuple[str, ...] | None = None,
    plan_context: str = "",
    transcript_context: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    scoped_memory_scope: str = "",
    mcp_servers: tuple[str, ...] | None = None,
    output_style: str = "",
    omicsclaw_dir: str = "",
    context_injectors: tuple[ContextLayerInjector, ...] | None = None,
    scoped_memory_loader=None,
) -> AssembledChatContext:
    session_id = f"{platform}:{user_id}:{chat_id}" if user_id and platform else None
    memory_context = ""
    if session_manager and session_id:
        await session_manager.get_or_create(user_id, platform, str(chat_id))
        memory_context = await session_manager.load_context(session_id)

    user_text = extract_user_text(user_content)
    skill_hint, domain_hint = extract_analysis_hints(
        user_text,
        skill_aliases=skill_aliases,
    )

    capability_context = ""
    if should_attach_capability_context(user_text, skill_aliases=skill_aliases):
        resolver = capability_resolver or _default_capability_resolver
        try:
            decision = resolver(user_text, domain_hint=domain_hint)
            capability_context = decision.to_prompt_block()
            if not skill_hint and getattr(decision, "chosen_skill", ""):
                skill_hint = decision.chosen_skill
            if not domain_hint and getattr(decision, "domain", ""):
                domain_hint = decision.domain
        except Exception as exc:
            LOGGER.warning("Capability resolution context failed (non-fatal): %s", exc)

    surface = "interactive" if platform in {"cli", "tui"} else "bot"
    prompt_pack_context = ""
    if omicsclaw_dir:
        try:
            from omicsclaw.extensions import build_prompt_pack_context

            prompt_pack_context = build_prompt_pack_context(
                omicsclaw_dir,
                surface=surface,
                skill=skill_hint,
                query=user_text[:200] if user_text else "",
                domain=domain_hint,
            )
        except Exception as exc:
            LOGGER.warning("Prompt-pack context preparation failed (non-fatal): %s", exc)

    scoped_memory_context = ""
    if workspace or pipeline_workspace:
        try:
            loader = scoped_memory_loader
            if loader is None:
                from omicsclaw.memory.scoped_memory_select import load_scoped_memory_context as _load_scoped_memory_context

                loader = _load_scoped_memory_context
            recall = loader(
                query=user_text[:200] if user_text else "",
                domain=domain_hint,
                workspace=workspace,
                pipeline_workspace=pipeline_workspace,
                preferred_scope=scoped_memory_scope,
            )
            if recall is None:
                scoped_memory_context = ""
            elif hasattr(recall, "to_context_text"):
                scoped_memory_context = str(recall.to_context_text()).strip()
            else:
                scoped_memory_context = str(recall).strip()
        except Exception as exc:
            LOGGER.warning("Scoped memory context preparation failed (non-fatal): %s", exc)

    prompt_context = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface=surface,
            omicsclaw_dir=omicsclaw_dir,
            output_style=output_style,
            memory_context=memory_context,
            scoped_memory_context=scoped_memory_context,
            skill=skill_hint,
            query=user_text[:200] if user_text else "",
            domain=domain_hint,
            capability_context=capability_context,
            plan_context=plan_context,
            prompt_pack_context=prompt_pack_context,
            transcript_context=transcript_context,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
            mcp_servers=tuple(mcp_servers or ()),
        ),
        injectors=context_injectors,
    )
    system_prompt = prompt_context.system_prompt

    if system_prompt_builder is not None:
        builder_kwargs = {
            "memory_context": memory_context,
            "scoped_memory_context": scoped_memory_context,
            "skill": skill_hint,
            "query": user_text[:200] if user_text else "",
            "domain": domain_hint,
            "capability_context": capability_context,
            "plan_context": plan_context,
            "transcript_context": transcript_context,
            "surface": surface,
            "output_style": output_style,
            "workspace": workspace,
            "pipeline_workspace": pipeline_workspace,
            "mcp_servers": tuple(mcp_servers or ()),
        }
        if omicsclaw_dir:
            builder_kwargs["omicsclaw_dir"] = omicsclaw_dir
        if prompt_pack_context:
            builder_kwargs["prompt_pack_context"] = prompt_pack_context
        knowledge_layer = next(
            (layer for layer in prompt_context.layers if layer.name == "knowledge_guidance"),
            None,
        )
        if knowledge_layer is not None:
            builder_kwargs["knowledge_context"] = knowledge_layer.content
            builder_kwargs["include_knowledge_guidance"] = True
        system_prompt = _invoke_legacy_prompt_builder(
            system_prompt_builder,
            **builder_kwargs,
        )

    return AssembledChatContext(
        session_id=session_id,
        memory_context=memory_context,
        scoped_memory_context=scoped_memory_context,
        user_text=user_text,
        user_message_content=build_user_message_content(
            user_content,
            message_context=prompt_context.message_context,
        ),
        skill_hint=skill_hint,
        domain_hint=domain_hint,
        capability_context=capability_context,
        prompt_context=prompt_context,
        system_prompt=system_prompt,
    )
