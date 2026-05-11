from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from omicsclaw.core.registry import ensure_registry_loaded, registry

LOGGER = logging.getLogger("omicsclaw.runtime.context_layers")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOUL_MD = PROJECT_ROOT / "SOUL.md"

_KNOWLEDGE_GUIDANCE_MARKERS = (
    "which method",
    "what method",
    "which workflow",
    "which pipeline",
    "how to",
    "how do i",
    "how should i",
    "best practice",
    "best practices",
    "best way",
    "parameter",
    "parameters",
    "tune parameter",
    "tuning",
    "recommend",
    "recommended",
    "suggest",
    "suitable",
    "appropriate",
    "choose",
    "selection",
    "compare",
    "comparison",
    "difference",
    "troubleshoot",
    "troubleshooting",
    "debug",
    "issue",
    "problem",
    "error",
    "failed",
    "why does",
    "why did",
    "vs ",
    " versus ",
    "怎么做",
    "如何",
    "什么方法",
    "哪个方法",
    "哪种方法",
    "推荐",
    "建议",
    "适合",
    "如何选择",
    "怎么选",
    "选择",
    "哪个好",
    "哪一个",
    "哪种",
    "参数",
    "调参",
    "报错",
    "失败",
    "排错",
    "故障",
    "异常",
    "问题",
    "区别",
    "对比",
    "比较",
)

LayerBuilder = Callable[["ContextAssemblyRequest"], "ContextLayer | str | None"]
KnowhowLoader = Callable[..., str]


def load_base_persona(soul_md: Path = DEFAULT_SOUL_MD) -> str:
    # Primary: __file__-based resolution (works for source-tree installs)
    if soul_md.exists():
        soul = soul_md.read_text(encoding="utf-8")
        LOGGER.info("Loaded SOUL.md (%d chars)", len(soul))
        return soul

    # Fallback: check OMICSCLAW_DIR (works for pip-installed / bundled)
    env_dir = os.environ.get("OMICSCLAW_DIR", "").strip()
    if env_dir:
        alt = Path(env_dir) / "SOUL.md"
        if alt.exists():
            soul = alt.read_text(encoding="utf-8")
            LOGGER.info("Loaded SOUL.md from OMICSCLAW_DIR (%d chars)", len(soul))
            return soul

    LOGGER.warning("SOUL.md not found, using fallback prompt")
    return (
        "You are a multi-omics AI assistant. "
        "Help users analyse multi-omics data with clarity and rigour."
    )


def build_memory_context_block(memory_context: str) -> str:
    value = str(memory_context or "").strip()
    if not value:
        return ""
    return f"## Your Memory\n\n{value}"


def build_skill_context_block(skill_context: str) -> str:
    value = str(skill_context or "").strip()
    return value


def build_scoped_memory_context_block(scoped_memory_context: str) -> str:
    value = str(scoped_memory_context or "").strip()
    if not value:
        return ""
    return f"## Scoped Memory\n\n{value}"


def build_workspace_context_block(
    *,
    workspace: str = "",
    pipeline_workspace: str = "",
) -> str:
    workspace_value = _normalize_path_text(workspace)
    pipeline_value = _normalize_path_text(pipeline_workspace)
    if not workspace_value and not pipeline_value:
        return ""

    lines = ["## Workspace Context", ""]
    if workspace_value:
        lines.append(f"- Session workspace: `{workspace_value}`")
    if pipeline_value and pipeline_value != workspace_value:
        lines.append(f"- Active pipeline workspace: `{pipeline_value}`")
        lines.append("- Treat the pipeline workspace as the authoritative location for `plan.md`, `todos.md`, reports, and run artifacts.")
    elif pipeline_value:
        lines.append("- The active workspace is also the pipeline workspace for current research tasks.")
    return "\n".join(lines).strip()


def build_plan_context_block(plan_context: str) -> str:
    value = str(plan_context or "").strip()
    return value


def build_transcript_context_block(transcript_context: str) -> str:
    value = str(transcript_context or "").strip()
    return value


def build_extension_prompt_pack_block(prompt_pack_context: str) -> str:
    value = str(prompt_pack_context or "").strip()
    return value


def build_knowledge_guidance_block(knowledge_context: str) -> str:
    value = str(knowledge_context or "").strip()
    return value


def build_mcp_instructions_block(mcp_servers: tuple[str, ...] | list[str] | None) -> str:
    active_entries = []
    for entry in (mcp_servers or ()):
        if isinstance(entry, dict):
            name = str(entry.get("name", "") or "").strip()
            if not name:
                continue
            active = bool(
                entry.get("active")
                or entry.get("loaded")
                or entry.get("connected")
                or entry.get("ready")
            )
            if not active:
                continue
            active_entries.append(
                {
                    "name": name,
                    "transport": str(entry.get("transport", "") or "").strip(),
                }
            )
            continue

        name = str(entry).strip()
        if name:
            active_entries.append({"name": name, "transport": ""})

    if not active_entries:
        return ""

    names = tuple(dict.fromkeys(item["name"] for item in active_entries if item["name"]))
    if not names:
        return ""

    joined = ", ".join(names)
    transport_hints = sorted(
        {item["transport"] for item in active_entries if item.get("transport")}
    )
    transport_line = ""
    if transport_hints:
        transport_line = f"\n- Active MCP transports: {', '.join(transport_hints)}"
    return (
        "## MCP Instructions\n\n"
        f"- Active MCP servers for this session: {joined}{transport_line}\n"
        "- Only use MCP-backed tools when they are actually exposed in the active tool list.\n"
        "- If a needed MCP capability is configured but not loaded as a callable tool, say so explicitly instead of assuming it is available."
    )


def load_knowhow_constraints(
    *,
    skill: str | None = None,
    query: str | None = None,
    domain: str | None = None,
    phase: str = "before_run",
) -> str:
    if not any((skill, query, domain)):
        return ""

    try:
        started_at = time.monotonic()
        from omicsclaw.knowledge.knowhow import get_knowhow_injector

        injector = get_knowhow_injector()
        # Phase 2 (KH lazy-load): the runtime context-assembly path emits
        # only the one-line headlines. Models fetch the full guard body on
        # demand via the ``read_knowhow(name)`` tool when the headline alone
        # is insufficient. Tests still call ``get_constraints`` directly with
        # the legacy full-body default for body-content assertions.
        constraints = injector.get_constraints(
            skill=skill or None,
            query=query or None,
            domain=domain or None,
            phase=phase,
            headline_only=True,
        )
        elapsed_ms = (time.monotonic() - started_at) * 1000
        if constraints:
            LOGGER.info(
                "Injected KH constraints (%d chars, %.1fms) for skill=%s",
                len(constraints),
                elapsed_ms,
                skill or "(general)",
            )
            try:
                from omicsclaw.knowledge.telemetry import get_telemetry

                injected_ids = injector.get_matching_kh_ids(
                    skill=skill or None,
                    query=query or None,
                    domain=domain or None,
                    phase=phase,
                )
                get_telemetry().log_kh_injection(
                    session_id="system",
                    skill=skill or "",
                    query=(query or "")[:200],
                    domain=domain or "",
                    injected_khs=injected_ids,
                    constraints_length=len(constraints),
                    latency_ms=elapsed_ms,
                )
            except Exception:
                pass
        return constraints or ""
    except Exception as exc:
        LOGGER.warning("KH injection failed (non-fatal): %s", exc)
        return ""


def should_prefetch_knowledge_guidance(
    *,
    query: str = "",
    skill: str = "",
    domain: str = "",
    capability_context: str = "",
) -> bool:
    del skill, domain, capability_context
    normalized_query = f" {str(query or '').lower().strip()} "
    if not normalized_query.strip():
        return False
    return any(marker in normalized_query for marker in _KNOWLEDGE_GUIDANCE_MARKERS)


def should_prefetch_skill_context(
    *,
    query: str = "",
    skill: str = "",
    domain: str = "",
    capability_context: str = "",
) -> bool:
    if str(skill or "").strip():
        return True
    capability_lower = str(capability_context or "").lower()
    if "coverage: exact_skill" in capability_lower or "coverage: partial_skill" in capability_lower:
        return True

    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return False
    if domain and domain in normalized_query:
        return True
    return bool(
        any(token in normalized_query for token in ("run ", "analy", "preprocess", "cluster", "trajectory", "deconvolution"))
        or "." in normalized_query
    )


def load_skill_context(
    *,
    skill: str = "",
    query: str = "",
    domain: str = "",
    candidate_skills: tuple[str, ...] | list[str] | None = None,
    max_candidates: int = 3,
    max_param_hints: int = 4,
) -> str:
    if not should_prefetch_skill_context(
        query=query,
        skill=skill,
        domain=domain,
    ):
        return ""

    ensure_registry_loaded()
    selected_skill = str(skill or "").strip()
    candidate_list = [
        str(name).strip()
        for name in (candidate_skills or ())
        if str(name).strip()
    ]
    if not selected_skill and candidate_list:
        selected_skill = candidate_list[0]
    if not selected_skill:
        return ""

    info = registry.skills.get(selected_skill)
    if info is None:
        return ""

    domain_value = str(info.get("domain", "") or domain or "").strip()
    description = str(info.get("description", "") or "").strip()
    legacy_aliases = [
        str(alias).strip()
        for alias in info.get("legacy_aliases", []) or []
        if str(alias).strip()
    ]
    param_hints = list((info.get("param_hints", {}) or {}).keys())[:max_param_hints]

    lines = [
        "## Prefetched Skill Context",
        "",
        f"- Selected skill: `{selected_skill}`",
    ]
    if domain_value:
        lines.append(f"- Domain: `{domain_value}`")
    if description:
        lines.append(f"- Summary: {description}")
    if legacy_aliases:
        lines.append(
            "- Legacy aliases: "
            + ", ".join(f"`{alias}`" for alias in legacy_aliases[:3])
        )
    if param_hints:
        lines.append(
            "- Method/parameter hints declared in SKILL.md: "
            + ", ".join(f"`{hint}`" for hint in param_hints)
        )
    if info.get("requires_preprocessed"):
        lines.append("- This skill expects preprocessed input.")
    if info.get("saves_h5ad"):
        lines.append("- This skill typically writes updated `.h5ad` outputs.")

    nearby = [
        name for name in candidate_list
        if name and name != selected_skill
    ][: max(0, max_candidates - 1)]
    if nearby:
        lines.append(
            "- Nearby alternatives: "
            + ", ".join(f"`{name}`" for name in nearby)
        )

    # ADR 2026-05-11: surface SKILL.md Gotchas into runtime context so the
    # agent can avoid documented pitfalls without a separate Read tool call.
    # Phase 1 = inject all gotchas (no method-based filter); Phase 2 trigger
    # is data-driven from the telemetry log line below.
    gotchas = info.get("gotchas") or []
    if gotchas:
        lines.append("")
        lines.append("## Known pitfalls (from SKILL.md Gotchas)")
        lines.append("")
        for lead in gotchas:
            lead_str = str(lead).strip()
            if lead_str:
                lines.append(f"- {lead_str}")
        # Telemetry: rough token estimate (4 chars / token) for Phase 2 gating.
        approx_tokens = sum(len(str(g)) for g in gotchas) // 4
        LOGGER.info(
            "skill_context.gotchas_injected skill=%s gotcha_count=%d approx_tokens=%d",
            selected_skill,
            len(gotchas),
            approx_tokens,
            extra={
                "event": "skill_context.gotchas_injected",
                "skill": selected_skill,
                "gotcha_count": len(gotchas),
                "approx_tokens": approx_tokens,
            },
        )

    return "\n".join(lines).strip()


def load_knowledge_guidance(
    *,
    query: str = "",
    skill: str = "",
    domain: str = "",
    limit: int = 2,
    max_snippet: int = 500,
) -> str:
    if not should_prefetch_knowledge_guidance(
        query=query,
        skill=skill,
        domain=domain,
    ):
        return ""

    try:
        from omicsclaw.knowledge import KnowledgeAdvisor

        advisor = KnowledgeAdvisor()
        search_query = " ".join(
            part.strip()
            for part in (skill, query)
            if str(part).strip()
        )
        if not search_query:
            return ""

        result = advisor.search_formatted(
            query=search_query,
            domain=domain or None,
            limit=limit,
            max_snippet=max_snippet,
            auto_build=True,
        )
        result = str(result or "").strip()
        if not result or result.startswith("No knowledge base results found"):
            return ""
        if "Knowledge base not built yet" in result:
            return ""
        return "## Preloaded Knowledge Guidance\n\n" + result
    except Exception as exc:
        LOGGER.warning("Knowledge guidance prefetch failed (non-fatal): %s", exc)
        return ""


def _normalize_path_text(path_text: str) -> str:
    value = str(path_text or "").strip()
    if not value:
        return ""
    try:
        return str(Path(value).expanduser().resolve())
    except Exception:
        return value


@dataclass(frozen=True, slots=True)
class ContextLayer:
    name: str
    content: str
    placement: str = "system"
    order: int = 0
    estimated_tokens: int = 0
    cost_chars: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        content = str(self.content or "").strip()
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "placement", str(self.placement or "system").strip() or "system")
        if not self.cost_chars:
            object.__setattr__(self, "cost_chars", len(content))
        if not self.estimated_tokens:
            estimated = math.ceil(len(content) / 4) if content else 0
            object.__setattr__(self, "estimated_tokens", estimated)


@dataclass(frozen=True, slots=True)
class ContextAssemblyRequest:
    surface: str = "bot"
    omicsclaw_dir: str = ""
    base_persona: str = ""
    output_style: str = ""
    memory_context: str = ""
    skill_context: str = ""
    scoped_memory_context: str = ""
    skill: str = ""
    skill_candidates: tuple[str, ...] = ()
    query: str = ""
    domain: str = ""
    capability_context: str = ""
    plan_context: str = ""
    prompt_pack_context: str = ""
    knowledge_context: str = ""
    transcript_context: str = ""
    workspace: str = ""
    pipeline_workspace: str = ""
    mcp_servers: tuple[Any, ...] = ()
    soul_md: Path = DEFAULT_SOUL_MD
    include_knowhow: bool | None = None
    include_knowledge_guidance: bool | None = None
    include_extension_prompt_packs: bool = True
    workspace_placement: str = "system"
    transcript_context_placement: str = "message"
    base_persona_loader: Callable[[Path], str] | None = None
    knowhow_loader: KnowhowLoader | None = None
    knowledge_loader: Callable[..., str] | None = None
    extension_prompt_pack_loader: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        normalized_servers = tuple(
            dict.fromkeys(
                (
                    json.dumps(item, sort_keys=True, default=str)
                    if isinstance(item, dict)
                    else str(item).strip()
                )
                for item in self.mcp_servers
                if (
                    isinstance(item, dict)
                    and str(item.get("name", "") or "").strip()
                )
                or (not isinstance(item, dict) and str(item).strip())
            )
        )
        restored_servers: list[Any] = []
        for item in normalized_servers:
            if isinstance(item, str) and item.startswith("{"):
                restored_servers.append(json.loads(item))
            else:
                restored_servers.append(item)
        object.__setattr__(self, "mcp_servers", tuple(restored_servers))
        object.__setattr__(
            self,
            "skill_candidates",
            tuple(
                dict.fromkeys(
                    str(name).strip()
                    for name in self.skill_candidates
                    if str(name).strip()
                )
            ),
        )
        object.__setattr__(self, "workspace_placement", str(self.workspace_placement or "system").strip() or "system")
        object.__setattr__(
            self,
            "transcript_context_placement",
            str(self.transcript_context_placement or "message").strip() or "message",
        )
        object.__setattr__(self, "output_style", str(self.output_style or "").strip())


_PredicateEventSink = Callable[["events.LifecycleEvent"], None]
_predicate_event_sinks: dict[int, _PredicateEventSink] = {}
_next_predicate_event_sink_id: int = 1


def register_predicate_event_sink(sink: _PredicateEventSink) -> int:
    """Register a callback that receives ``EVENT_PREDICATE_HIT`` /
    ``EVENT_PREDICATE_MISS`` events when ``ContextLayerInjector`` evaluates
    a predicate-gated layer. Returns an ID for ``unregister_predicate_event_sink``.

    Used by the runtime telemetry pipeline (and by tests) to observe which
    conditional rules are actually firing per request.
    """
    global _next_predicate_event_sink_id
    sink_id = _next_predicate_event_sink_id
    _next_predicate_event_sink_id += 1
    _predicate_event_sinks[sink_id] = sink
    return sink_id


def unregister_predicate_event_sink(sink_id: int) -> None:
    _predicate_event_sinks.pop(sink_id, None)


def _emit_predicate_event(
    event_name: str,
    *,
    predicate: str,
    surface: str,
    source: str = "context_layers.predicate",
    kind: str = "layer",
) -> None:
    """Emit a predicate-evaluation event to all registered sinks.

    ``source`` distinguishes which subsystem fired the predicate
    (e.g. ``context_layers.predicate`` for layer gating vs
    ``tool_registry.predicate`` for tool-list selection). ``kind``
    is mirrored into the payload so consumers can filter without
    parsing the source string. This avoids the ambiguity that would
    occur if a layer and a tool happened to share a predicate name.
    """
    if not _predicate_event_sinks:
        return
    from .. import events as _events_mod  # local import to avoid cycles at module load

    evt = _events_mod.LifecycleEvent(
        name=event_name,
        payload={"predicate": predicate, "surface": surface, "kind": kind},
        surface=surface,
        source=source,
    )
    for sink in tuple(_predicate_event_sinks.values()):
        try:
            sink(evt)
        except Exception as exc:  # pragma: no cover - sink errors must not break assembly
            LOGGER.warning(
                "Predicate event sink raised %s; ignoring", exc.__class__.__name__
            )


@dataclass(frozen=True, slots=True)
class ContextLayerInjector:
    name: str
    order: int
    placement: str
    surfaces: tuple[str, ...]
    builder: LayerBuilder
    predicate: Callable[["ContextAssemblyRequest"], bool] | None = None

    def applies(self, request: ContextAssemblyRequest) -> bool:
        if request.surface not in self.surfaces:
            return False
        if self.predicate is None:
            return True
        try:
            decision = bool(self.predicate(request))
        except Exception as exc:  # fail-closed: misbehaving predicate must not inject
            LOGGER.warning(
                "Predicate for layer %r raised %s: %s; suppressing layer",
                self.name,
                exc.__class__.__name__,
                exc,
            )
            return False
        from .. import events as _events_mod

        _emit_predicate_event(
            _events_mod.EVENT_PREDICATE_HIT if decision else _events_mod.EVENT_PREDICATE_MISS,
            predicate=self.name,
            surface=str(request.surface or ""),
        )
        return decision

    def render(self, request: ContextAssemblyRequest) -> ContextLayer | None:
        result = self.builder(request)
        if result is None:
            return None

        if isinstance(result, ContextLayer):
            layer = result
        else:
            layer = ContextLayer(
                name=self.name,
                content=str(result),
                placement=self.placement,
                order=self.order,
            )

        if not layer.content:
            return None

        return ContextLayer(
            name=layer.name or self.name,
            content=layer.content,
            placement=layer.placement or self.placement,
            order=layer.order or self.order,
            estimated_tokens=layer.estimated_tokens,
            cost_chars=layer.cost_chars,
            metadata=dict(layer.metadata),
        )


def _build_base_persona_layer(request: ContextAssemblyRequest) -> str:
    if request.base_persona.strip():
        return request.base_persona.strip()
    loader = request.base_persona_loader or load_base_persona
    return loader(request.soul_md).strip()


def _build_memory_context_layer(request: ContextAssemblyRequest) -> str | None:
    return build_memory_context_block(request.memory_context) or None


def _build_skill_context_layer(request: ContextAssemblyRequest) -> str | None:
    include_skill = should_prefetch_skill_context(
        query=request.query,
        skill=request.skill,
        domain=request.domain,
        capability_context=request.capability_context,
    )
    if not include_skill:
        return None

    block = build_skill_context_block(request.skill_context)
    if block:
        return block

    return load_skill_context(
        skill=request.skill,
        query=request.query,
        domain=request.domain,
        candidate_skills=request.skill_candidates,
    ) or None


def _build_scoped_memory_context_layer(request: ContextAssemblyRequest) -> str | None:
    return build_scoped_memory_context_block(request.scoped_memory_context) or None


def _build_capability_context_layer(request: ContextAssemblyRequest) -> str | None:
    value = str(request.capability_context or "").strip()
    return value or None


def _build_knowledge_guidance_layer(request: ContextAssemblyRequest) -> str | None:
    include_knowledge = (
        request.include_knowledge_guidance
        if request.include_knowledge_guidance is not None
        else should_prefetch_knowledge_guidance(
            query=request.query,
            skill=request.skill,
            domain=request.domain,
            capability_context=request.capability_context,
        )
    )
    if not include_knowledge:
        return None

    block = build_knowledge_guidance_block(request.knowledge_context)
    if block:
        return block

    loader = request.knowledge_loader or load_knowledge_guidance
    return loader(
        query=request.query or "",
        skill=request.skill or "",
        domain=request.domain or "",
    ) or None


def _build_plan_context_layer(request: ContextAssemblyRequest) -> str | None:
    return build_plan_context_block(request.plan_context) or None


def _build_extension_prompt_pack_layer(request: ContextAssemblyRequest) -> ContextLayer | None:
    if not request.include_extension_prompt_packs:
        return None

    block = build_extension_prompt_pack_block(request.prompt_pack_context)
    metadata: dict[str, Any] = {}
    if not block and request.omicsclaw_dir:
        try:
            from omicsclaw.extensions import load_prompt_pack_runtime_context

            loader = request.extension_prompt_pack_loader or load_prompt_pack_runtime_context
            runtime_context = loader(
                request.omicsclaw_dir,
                surface=request.surface,
                skill=request.skill,
                query=request.query,
                domain=request.domain,
            )
            block = build_extension_prompt_pack_block(
                getattr(runtime_context, "content", runtime_context)
            )
            metadata = dict(getattr(runtime_context, "metadata", {}) or {})
            active_names = tuple(getattr(runtime_context, "active_prompt_packs", ()) or ())
            omitted_names = tuple(getattr(runtime_context, "omitted_prompt_packs", ()) or ())
            if active_names:
                metadata.setdefault("active_prompt_packs", active_names)
            if omitted_names:
                metadata.setdefault("omitted_prompt_packs", omitted_names)
        except Exception as exc:
            LOGGER.warning("Prompt-pack context injection failed (non-fatal): %s", exc)
            return None

    if not block:
        return None
    return ContextLayer(
        name="extension_prompt_packs",
        content=block,
        placement="system",
        metadata=metadata,
    )


def _build_transcript_context_layer(request: ContextAssemblyRequest) -> ContextLayer | None:
    block = build_transcript_context_block(request.transcript_context)
    if not block:
        return None
    return ContextLayer(
        name="transcript_context",
        content=block,
        placement=request.transcript_context_placement,
    )


def _build_knowhow_constraints_layer(request: ContextAssemblyRequest) -> str | None:
    include_knowhow = (
        request.include_knowhow
        if request.include_knowhow is not None
        else bool(request.skill or request.query or request.domain)
    )
    if not include_knowhow:
        return None

    loader = request.knowhow_loader or load_knowhow_constraints
    constraints = loader(
        skill=request.skill or None,
        query=request.query or None,
        domain=request.domain or None,
        phase="before_run",
    )
    return str(constraints or "").strip() or None


def _build_workspace_context_layer(request: ContextAssemblyRequest) -> ContextLayer | None:
    block = build_workspace_context_block(
        workspace=request.workspace,
        pipeline_workspace=request.pipeline_workspace,
    )
    if not block:
        return None
    return ContextLayer(
        name="workspace_context",
        content=block,
        placement=request.workspace_placement,
    )


def _build_mcp_instructions_layer(request: ContextAssemblyRequest) -> str | None:
    return build_mcp_instructions_block(request.mcp_servers) or None


_SURFACE_VOICE_RULES: dict[str, str] = {
    "bot": (
        "## Voice (chat surface)\n\n"
        "- Emoji OK sparingly: 🧬 (omics), 📊 (results), ⚠️ (warnings); "
        "at most one per message.\n"
        "- Markdown formatting allowed: **bold** for emphasis, *italic* for "
        "gene names, headers for structure.\n"
        "- Greet with `Hi [Name]`; sign off with `— OmicsBot`."
    ),
    "interactive": (
        "## Voice (CLI surface)\n\n"
        "- Plain text only. No emoji, no markdown bold/italic/headers.\n"
        "- Use UPPERCASE for emphasis and `-` or `•` for bullets.\n"
        "- Wrap file paths and commands in backticks for clarity."
    ),
    "pipeline": (
        "## Voice (pipeline surface)\n\n"
        "- Plain text only. No emoji, no markdown bold/italic/headers.\n"
        "- UPPERCASE for emphasis, `-` for bullets.\n"
        "- Pipeline outputs are consumed by other agents and CI logs — "
        "favour terse status lines over prose."
    ),
}


def _build_surface_voice_rules_layer(request: ContextAssemblyRequest) -> str | None:
    """Surface-conditional voice rules.

    Replaces the per-surface ``Bot Mode`` / ``CLI Mode`` subsections that
    used to live inside SOUL.md. The bot variant allows emoji and markdown;
    interactive and pipeline enforce plain text.
    """
    text = _SURFACE_VOICE_RULES.get(str(request.surface or "").strip().lower())
    if not text:
        return None
    return text


def _build_output_format_layer(request: ContextAssemblyRequest) -> str | None:
    from .output_format import build_output_format_layer
    return build_output_format_layer(request)


# --- Predicate-gated rule layers (Phase 4) ----------------------------------
#
# Each rule below replaces a section that used to live in the always-on
# ``execution_discipline`` or ``skill_contract`` layers. The text body is
# kept under ~400 chars per layer so the worst-case injection (all 7
# triggering simultaneously) stays well below the deleted layers' combined
# 7,800 chars. The actual fan-out is much smaller — typical sc-de turns
# trigger 2-3 of these.

_PREDICATE_GATED_RULES: dict[str, str] = {
    "scope_and_minimal_change_rule": (
        "## Scope and Minimal Change\n"
        "- Fulfil the user's stated request first. Don't add extra analyses, "
        "exports, refactors, or follow-on steps unless asked.\n"
        "- Choose the smallest clear change. No speculative abstractions, "
        "future-proof frameworks, or broad cleanups without a concrete need.\n"
        "- Read existing files, plans, and current outputs before changing code."
    ),
    "file_path_and_inspect_rule": (
        "## File Path Discipline\n"
        "- Use exactly the file the user provided. Don't browse for "
        "substitutes, auto-preprocess, or auto-fix missing prerequisites.\n"
        "- For `.h5ad` / AnnData previews, use `inspect_data` first; do NOT "
        "use `inspect_data` as a generic preflight for mzML/VCF/BAM.\n"
        "- After inspection, suggest a small set of analyses and wait for "
        "user choice before running expensive jobs."
    ),
    "parse_literature_rule": (
        "## Literature & PDF Handling\n"
        "- Use `parse_literature` for dataset extraction, GEO accession "
        "discovery, or structured paper metadata.\n"
        "- Not every PDF needs `parse_literature` — for summary, translation, "
        "or explanation, answer directly unless structured extraction "
        "would materially help."
    ),
    "workspace_continuity_rule": (
        "## Workspace Continuity\n"
        "- Treat the active workspace / pipeline workspace as the source of "
        "truth for `plan.md`, `todos.md`, reports, and run artifacts.\n"
        "- Before rerun, check whether the relevant artifact already exists "
        "and whether the user asked to refresh it.\n"
        "- Keep writes inside the active workspace; don't scatter temp "
        "files across the repo."
    ),
    "chat_mode_rule": (
        "## Chat-Mode Discipline\n"
        "- If the user only needs explanation, interpretation, or translation, "
        "answer directly without tool calls.\n"
        "- Don't create saved artifacts unless the user explicitly asks for "
        "a file, export, or workspace change."
    ),
    "memory_hygiene_rule": (
        "## Memory Hygiene\n"
        "- Use `remember` for stable preferences, confirmed biological insights, "
        "and durable project context. Never store secrets, API keys, PII, "
        "transient file paths, temporary errors, or unconfirmed annotations.\n"
        "- Treat injected `## Scoped Memory` as local project/dataset/lab "
        "heuristics, not general scientific knowledge."
    ),
    "capability_routing_hint_rule": (
        "## Capability Routing\n"
        "- For non-trivial analysis, call `resolve_capability(query='…', "
        "domain_hint='…')` to map the request to a skill before acting.\n"
        "- Prefer canonical skill aliases. Use `mode='demo'` only when the "
        "user explicitly asks for a demo."
    ),
}


def _make_predicate_rule_builder(rule_name: str) -> LayerBuilder:
    """Bind a static rule_text to a builder so the layer renders a
    constant string when its predicate fires."""
    def _builder(_request: ContextAssemblyRequest) -> str | None:
        return _PREDICATE_GATED_RULES.get(rule_name)

    return _builder


def _predicate(name: str) -> Callable[[ContextAssemblyRequest], bool]:
    """Lazy-import a predicate function from ``omicsclaw.runtime.predicates``
    so the import only triggers when ``ContextLayerInjector.applies`` is
    called — avoids the circular import between ``predicates`` (which
    imports ``ContextAssemblyRequest`` from this module) and the
    injector definitions below.
    """
    def _call(req: ContextAssemblyRequest) -> bool:
        from .. import predicates as _pred_mod

        fn = getattr(_pred_mod, name)
        return bool(fn(req))

    return _call


DEFAULT_CONTEXT_LAYER_INJECTORS = (
    ContextLayerInjector(
        name="base_persona",
        order=10,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_base_persona_layer,
    ),
    ContextLayerInjector(
        name="surface_voice_rules",
        order=11,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_surface_voice_rules_layer,
    ),
    # --- Predicate-gated rule layers (Phase 4) ---
    # Order 12-19 (skipping 15, taken by ``output_format``): lightweight,
    # conditional rules that replace fragments of the deleted
    # ``execution_discipline`` and ``skill_contract`` layers.
    ContextLayerInjector(
        name="scope_and_minimal_change_rule",
        order=12,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("scope_and_minimal_change_rule"),
        predicate=_predicate("implementation_intent"),
    ),
    ContextLayerInjector(
        name="file_path_and_inspect_rule",
        order=13,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("file_path_and_inspect_rule"),
        predicate=_predicate("anndata_or_file_path_in_query"),
    ),
    ContextLayerInjector(
        name="parse_literature_rule",
        order=14,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("parse_literature_rule"),
        predicate=_predicate("pdf_or_paper_intent"),
    ),
    ContextLayerInjector(
        name="workspace_continuity_rule",
        order=16,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("workspace_continuity_rule"),
        predicate=_predicate("workspace_active"),
    ),
    ContextLayerInjector(
        name="chat_mode_rule",
        order=17,
        placement="system",
        surfaces=("bot",),
        builder=_make_predicate_rule_builder("chat_mode_rule"),
        predicate=_predicate("chat_surface"),
    ),
    ContextLayerInjector(
        name="memory_hygiene_rule",
        order=18,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("memory_hygiene_rule"),
        predicate=_predicate("memory_in_use"),
    ),
    ContextLayerInjector(
        name="capability_routing_hint_rule",
        order=19,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_make_predicate_rule_builder("capability_routing_hint_rule"),
        predicate=_predicate("non_trivial_no_capability"),
    ),
    ContextLayerInjector(
        name="memory_context",
        order=40,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_memory_context_layer,
    ),
    ContextLayerInjector(
        name="skill_context",
        order=42,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_skill_context_layer,
    ),
    ContextLayerInjector(
        name="scoped_memory_context",
        order=45,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_scoped_memory_context_layer,
    ),
    ContextLayerInjector(
        name="extension_prompt_packs",
        order=35,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_extension_prompt_pack_layer,
    ),
    ContextLayerInjector(
        name="capability_assessment",
        order=50,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_capability_context_layer,
    ),
    ContextLayerInjector(
        name="knowledge_guidance",
        order=52,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_knowledge_guidance_layer,
    ),
    ContextLayerInjector(
        name="plan_context",
        order=55,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_plan_context_layer,
    ),
    ContextLayerInjector(
        name="transcript_context",
        order=58,
        placement="message",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_transcript_context_layer,
    ),
    ContextLayerInjector(
        name="knowhow_constraints",
        order=60,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_knowhow_constraints_layer,
    ),
    ContextLayerInjector(
        name="workspace_context",
        order=70,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_workspace_context_layer,
    ),
    ContextLayerInjector(
        name="mcp_instructions",
        order=80,
        placement="system",
        surfaces=("interactive",),
        builder=_build_mcp_instructions_layer,
    ),
    ContextLayerInjector(
        name="output_format",
        order=15,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_output_format_layer,
    ),
)


def get_default_context_injectors() -> tuple[ContextLayerInjector, ...]:
    return DEFAULT_CONTEXT_LAYER_INJECTORS


__all__ = [
    "DEFAULT_CONTEXT_LAYER_INJECTORS",
    "DEFAULT_SOUL_MD",
    "ContextAssemblyRequest",
    "ContextLayer",
    "ContextLayerInjector",
    "build_extension_prompt_pack_block",
    "build_knowledge_guidance_block",
    "build_mcp_instructions_block",
    "build_memory_context_block",
    "build_plan_context_block",
    "build_skill_context_block",
    "build_scoped_memory_context_block",
    "build_transcript_context_block",
    "build_workspace_context_block",
    "get_default_context_injectors",
    "load_base_persona",
    "load_knowledge_guidance",
    "load_skill_context",
    "load_knowhow_constraints",
    "should_prefetch_knowledge_guidance",
    "should_prefetch_skill_context",
]
