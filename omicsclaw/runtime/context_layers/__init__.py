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


def get_role_guardrails(*, capability_context_present: bool = False) -> str:
    domain_names = ", ".join(d["name"].lower() for d in registry.domains.values())
    capability_rule = (
        "A `## Deterministic Capability Assessment` block is already present below. "
        "Follow it directly and do NOT call `resolve_capability` again unless the user materially changes the request."
        if capability_context_present
        else "If the request is non-trivial and the best skill is not obvious, call `resolve_capability` before analysis."
    )

    return f"""
Operational guardrails:
1. Identity
   - You are a multi-omics analysis assistant powered by OmicsClaw skills.
   - Supported domains: {domain_names}.
   - Keep outputs concise, evidence-led, and explicit about confidence and gaps.

2. Language Matching
   - Reply in the same language the user uses.
   - If memory contains a language preference, follow it.
   - Default to English only when no preference is evident.

3. Capability Discipline
   - {capability_rule}

4. Result Fidelity
   - Preserve all numerical values, adjusted p-values, gene lists, file paths, warnings, and error messages exactly.
   - You may remove raw progress/debug noise and add a brief interpretation after the exact result block.
   - Never silently round, alter, or omit scientific outputs.

5. Failure Handling
   - When a tool fails, report the exact error once, give the likely cause if clear, and propose the next step.
   - Do not loop repeated retries after the same failure unless the user changes inputs or explicitly asks to retry.
   - If a user-specified method fails, never silently switch to another method; ask before changing methods.

6. Memory Use
   - Use `remember` for stable preferences, confirmed biological insights, and durable project context.
   - Treat injected `## Scoped Memory` as local project/dataset/lab heuristics, not general scientific knowledge.
   - Do not store secrets, API keys, raw patient identifiers, transient file paths, temporary errors, or unconfirmed annotations.
   - If helpful, briefly acknowledge durable preferences or confirmed context in natural language; do not dump internal memory fields.

7. Knowledge and Scientific Constraints
   - Use `consult_knowledge` proactively for method selection, parameter advice, and troubleshooting.
   - Treat injected `⚠️ MANDATORY SCIENTIFIC CONSTRAINTS` as highest-priority scientific rules.
   - You may summarize them for the user, but never weaken, ignore, or override them.

8. Tone and Style
   - Avoid emojis unless the user explicitly requests them.
   - Be concise and direct; skip preamble and don't restate the user's question.
   - When citing code, use `path:line` so the user can navigate.
   - Do not write "Let me X:" before a tool call — just take the action.
""".strip()


def get_execution_discipline(
    *,
    surface: str = "bot",
    workspace: str = "",
    pipeline_workspace: str = "",
    plan_context_present: bool = False,
) -> str:
    normalized_surface = str(surface or "bot").strip().lower() or "bot"
    workspace_present = bool(
        _normalize_path_text(workspace) or _normalize_path_text(pipeline_workspace)
    )

    sections = [
        """
Execution discipline:
1. Scope Control
   - Fulfil the user's stated request first.
   - Do not add extra analyses, exports, files, refactors, or follow-on steps unless the user asks.
   - For exploratory questions, inspect or explain first; do not trigger expensive runs by default.

2. Existing-First Work
   - Read relevant files, plans, current outputs, and exact errors before changing code or rerunning analysis.
   - Prefer existing OmicsClaw skills, workspace artifacts, and built-in utilities over ad hoc scripts or new abstractions.
   - In workspace-oriented tasks, use `tool_search`, `file_read`, `glob_files`, and `grep_files` to inspect before `file_edit` or `file_write`.

3. Minimal Changes
   - Choose the smallest clear change that solves the present task.
   - Do not introduce speculative abstractions, future-proof frameworks, or broad cleanups without a concrete need.
   - Avoid new files, notebooks, helper scripts, and fallback branches unless they are required for the requested outcome.

4. Failure Diagnosis
   - If a step fails, inspect the exact error, inputs, and surrounding context before retrying.
   - Do not loop the same failing action with unchanged inputs.
   - Do not silently switch methods, references, parameters, or datasets after a failure.

5. Reporting Integrity
   - Report exactly what you inspected, executed, changed, and verified.
   - Never claim a test, command, file, figure, or output exists unless you directly observed it.
   - Do not give time estimates; when relevant, describe relative cost or note that a step may be long-running.

6. Action Risk Discipline
   - Before any action, weigh reversibility and blast radius. Local edits, test runs, and read-only queries are free. Operations affecting shared state (push, PR, cloud delete, drop table, send message) require explicit user confirmation unless already authorised in this session.
   - When you hit an obstacle, do not use a destructive shortcut (force-push, --no-verify, rm -rf, hard reset) to make it go away. Investigate the root cause first.
   - If the same action fails twice the same way, stop and re-examine the assumption — do not retry blindly.
""".strip()
    ]

    if normalized_surface == "bot":
        sections.append(
            """
7. Chat Mode Discipline
   - If the user only needs explanation, interpretation, or translation, answer directly instead of calling tools.
   - Do not create saved artifacts unless the user explicitly asks for a file, export, or workspace change.
""".strip()
        )

    if normalized_surface in {"interactive", "pipeline"} or workspace_present or plan_context_present:
        sections.append(
            """
8. Workspace Continuity
   - Treat the active workspace or pipeline workspace as the source of truth for `plan.md`, `todos.md`, reports, and run artifacts.
   - Before rerunning a stage or editing outputs, check whether the relevant artifact already exists and whether the user asked to refresh it.
   - Use `todo_write` and task tools only when the work is genuinely multi-step; do not create busywork task lists.
   - Keep writes inside the active workspace or the declared `output/` contract; do not scatter temporary files across the repo.
""".strip()
        )

    return "\n\n".join(section for section in sections if section).strip()


def get_skill_contract(*, capability_context_present: bool = False) -> str:
    capability_rule = (
        "- A `## Deterministic Capability Assessment` block is already present below. "
        "Follow it directly and do NOT call `resolve_capability` again unless the user materially changes the request."
        if capability_context_present
        else "- If the request is non-trivial and the best skill is not obvious, call `resolve_capability` before analysis."
    )

    return f"""
Skill contract:
1. Skill Routing and Capability
   {capability_rule}
   - If the user names an exact skill or gives an obvious exact skill invocation, call `omicsclaw` directly.
   - Prefer canonical skill aliases when possible; legacy aliases may exist but should not be your default.
   - Use `mode='demo'` only when the user explicitly asks for a demo.
   - If an exact skill exists, do NOT jump to custom code.
   - If coverage='partial_skill', explain which step is covered by the skill and which step requires custom analysis before proceeding.
   - If coverage='no_skill', you may use `web_method_search` and then `custom_analysis_execute`.
   - Use `create_omics_skill` only when the user explicitly asks to add, scaffold, package, or persist a reusable skill.

2. Method and Parameter Handling
   - When the user specifies a method, pass it in lowercase via the `method` parameter.
   - Prefer canonical backend names from the chosen skill, capability assessment, SKILL.md metadata, or knowledge guidance; do not rely on stale hardcoded method lists.
   - For method suitability or default-parameter questions, use `inspect_data` only for `.h5ad` / AnnData preflight and use `consult_knowledge` for cross-domain method advice.
   - Warn the user before long deep-learning analyses; they often take 10-60 minutes.
   - If `sc-batch-integration` pauses because upstream preparation is recommended and the user explicitly agrees to continue with those prep steps, call `omicsclaw` again with `auto_prepare=true` instead of manually chaining separate tool calls yourself.
   - If the user explicitly insists on direct integration despite the workflow warning, only then use `confirm_workflow_skip=true`.

3. File Path Discipline
   - When the user provides a file path, use exactly that file.
   - Do not browse for "better" substitutes, auto-preprocess, or auto-fix missing prerequisites.
   - If the requested method cannot run on that file, explain why and ask before changing course.

4. Data Exploration and Preflight
   - Use `inspect_data` first only when the user is exploring or previewing an `.h5ad` / AnnData file without requesting a concrete pipeline.
   - Do not use `inspect_data` as a generic preflight for mzML, VCF, BAM, or other non-AnnData inputs.
   - After inspection, suggest a small set of appropriate analyses and wait for the user's choice before running expensive jobs.

5. Literature and PDF Handling
   - Use `parse_literature` when the user wants dataset extraction, GEO accession discovery, or structured paper metadata from a scientific paper or uploaded PDF.
   - Not every PDF requires `parse_literature` first; if the user only wants summary, translation, or explanation, answer directly unless structured extraction would materially help.

6. Controlled Execution and File Writing
   - Run analysis code via `omicsclaw` or `custom_analysis_execute`, not via generated shell scripts.
   - Never use `write_file` to create executable shell scripts such as `.sh` or `.bash`.
   - Only write `.py` or `.R` scripts when the user explicitly asks to save or export them, and save them under `output/`.
   - Use `custom_analysis_execute` for execution; use saved scripts only as exported artifacts.

7. Output Location
   - User-facing saved artifacts should go under `output/`.
   - Prefer a fresh per-analysis subdirectory over writing into the root of `output/`.
   - When relaying saved paths, report the exact generated directory or file path.

8. Engineering Discipline
   - Read code before proposing changes to it. Don't suggest modifications based on file names alone.
   - Prefer editing an existing file over creating a new one.
   - Stay within scope: a bug fix doesn't need surrounding cleanup; a small feature doesn't need configurability.
   - Don't add comments or docstrings to code you didn't change. Only annotate logic that isn't self-evident.
   - Don't add error handling, fallbacks, or validation for scenarios that can't happen. Trust internal-call invariants; validate only at system boundaries.
   - Don't add backwards-compat shims (renamed `_var`, removed-comment markers, dead re-exports) — delete unused code outright.
   - Be careful not to introduce OWASP-class vulnerabilities (command injection, SQL injection, unsafe deserialization). Fix any insecure code you notice.
""".strip()


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
        constraints = injector.get_constraints(
            skill=skill or None,
            query=query or None,
            domain=domain or None,
            phase=phase,
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
    include_role_guardrails: bool = True
    include_execution_discipline: bool = True
    include_skill_contract: bool = True
    include_knowhow: bool | None = None
    include_knowledge_guidance: bool | None = None
    include_extension_prompt_packs: bool = True
    workspace_placement: str = "system"
    transcript_context_placement: str = "message"
    base_persona_loader: Callable[[Path], str] | None = None
    role_guardrails_builder: Callable[..., str] | None = None
    execution_discipline_builder: Callable[..., str] | None = None
    skill_contract_builder: Callable[..., str] | None = None
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


@dataclass(frozen=True, slots=True)
class ContextLayerInjector:
    name: str
    order: int
    placement: str
    surfaces: tuple[str, ...]
    builder: LayerBuilder

    def applies(self, request: ContextAssemblyRequest) -> bool:
        return request.surface in self.surfaces

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


def _build_role_guardrails_layer(request: ContextAssemblyRequest) -> str | None:
    if not request.include_role_guardrails:
        return None
    builder = request.role_guardrails_builder or get_role_guardrails
    return builder(capability_context_present=bool(request.capability_context)).strip()


def _build_execution_discipline_layer(request: ContextAssemblyRequest) -> str | None:
    if not request.include_execution_discipline:
        return None
    builder = request.execution_discipline_builder or get_execution_discipline
    return builder(
        surface=request.surface,
        workspace=request.workspace,
        pipeline_workspace=request.pipeline_workspace,
        plan_context_present=bool(request.plan_context),
    ).strip()


def _build_skill_contract_layer(request: ContextAssemblyRequest) -> str | None:
    if not request.include_skill_contract:
        return None
    builder = request.skill_contract_builder or get_skill_contract
    return builder(capability_context_present=bool(request.capability_context)).strip()


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


def _build_output_format_layer(request: ContextAssemblyRequest) -> str | None:
    from .output_format import build_output_format_layer
    return build_output_format_layer(request)


DEFAULT_CONTEXT_LAYER_INJECTORS = (
    ContextLayerInjector(
        name="base_persona",
        order=10,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_base_persona_layer,
    ),
    ContextLayerInjector(
        name="role_guardrails",
        order=20,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_role_guardrails_layer,
    ),
    ContextLayerInjector(
        name="execution_discipline",
        order=25,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_execution_discipline_layer,
    ),
    ContextLayerInjector(
        name="skill_contract",
        order=30,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_build_skill_contract_layer,
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
    "get_execution_discipline",
    "get_role_guardrails",
    "get_skill_contract",
    "load_base_persona",
    "load_knowledge_guidance",
    "load_skill_context",
    "load_knowhow_constraints",
    "should_prefetch_knowledge_guidance",
    "should_prefetch_skill_context",
]
