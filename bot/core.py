"""
core.py — OmicsClaw Bot shared engine
=====================================
Platform-independent logic shared by OmicsClaw messaging frontends:
LLM tool-use loop, skill execution, security helpers, audit logging.

All channel frontends import this module, call ``init()`` once at startup, then
use the async helper functions to process user messages.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time

import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI, APIError, OpenAIError

from omicsclaw.common.runtime_env import load_project_dotenv
from omicsclaw.core.llm_timeout import (
    DEFAULT_LLM_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    build_llm_timeout_policy,
)
from omicsclaw.core.provider_registry import (
    PROVIDER_DETECT_ORDER,
    PROVIDER_PRESETS,
    normalize_model_for_provider,
    resolve_provider,
)
from omicsclaw.core.provider_runtime import (
    provider_requires_api_key,
    set_active_provider_runtime,
)

_PROVIDER_DETECT_ORDER = PROVIDER_DETECT_ORDER


# ---------------------------------------------------------------------------
# Paths (relative to OmicsClaw project root)
# ---------------------------------------------------------------------------


def _resolve_omicsclaw_dir() -> Path:
    """Find a writable OmicsClaw workspace directory.

    The historical assumption was that bot/ sits directly next to
    ``omicsclaw.py`` in a source tree, so ``Path(__file__).parent.parent``
    was always correct. That breaks for two newer install shapes:

    1. **Pip-installed** (e.g. ``pip install omicsclaw``): bot/ lives
       under site-packages/, so ``parent.parent`` resolves to
       site-packages — not a meaningful project dir, and usually
       read-only inside a packaged app bundle.
    2. **OmicsClaw-App bundled runtime**: a signed/notarized .app bundle
       on macOS puts site-packages under
       ``/Applications/.../Contents/Resources``, which is strictly
       read-only. ``_AUDIT_LOG_DIR.mkdir(...)`` a few lines down would
       raise ``PermissionError`` at import time.

    Resolution priority:
      1. ``OMICSCLAW_DIR`` env var (explicit override — honoured first
         so operators can point at a shared or external workspace).
      2. Source-tree layout (``bot/`` sibling of ``omicsclaw.py``) —
         preserves every existing dev install behavior unchanged.
      3. ``~/.omicsclaw`` — the per-user writable fallback used by
         pip-installed / bundled-runtime deployments. Mirrors the
         convention used by jupyter / matplotlib / mypy.
    """
    env = os.getenv("OMICSCLAW_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()

    source_tree = Path(__file__).resolve().parent.parent
    if (source_tree / "omicsclaw.py").is_file():
        return source_tree

    return (Path.home() / ".omicsclaw").resolve()


OMICSCLAW_DIR = _resolve_omicsclaw_dir()
load_project_dotenv(OMICSCLAW_DIR, override=False)
OMICSCLAW_PY = OMICSCLAW_DIR / "omicsclaw.py"
OUTPUT_DIR = Path(os.getenv("OMICSCLAW_OUTPUT_DIR", "") or (OMICSCLAW_DIR / "output")).expanduser().resolve()
DATA_DIR = OMICSCLAW_DIR / "data"
EXAMPLES_DIR = OMICSCLAW_DIR / "examples"


# OutputMediaPaths + collector — extracted to bot.skill_orchestration per ADR 0001.
from bot.skill_orchestration import OutputMediaPaths, _collect_output_media_paths


def _path_names(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


def get_skill_runner_python() -> str:
    """Return the Python executable used for skill subprocesses.

    By default this is the current interpreter, but advanced deployments can
    override it with ``OMICSCLAW_RUN_PYTHON`` when the app server itself runs
    in a lighter environment than the scientific analysis stack.
    """
    candidate = str(os.getenv("OMICSCLAW_RUN_PYTHON", "") or "").strip()
    if not candidate:
        return sys.executable

    expanded = os.path.expanduser(candidate)
    if os.path.sep in expanded or (os.path.altsep and os.path.altsep in expanded):
        resolved_path = Path(expanded)
        if resolved_path.exists():
            return str(resolved_path.resolve())
        logging.getLogger("omicsclaw.bot").warning(
            "OMICSCLAW_RUN_PYTHON=%s does not exist; falling back to sys.executable=%s",
            candidate,
            sys.executable,
        )
        return sys.executable

    resolved = shutil.which(expanded)
    if resolved:
        return resolved

    logging.getLogger("omicsclaw.bot").warning(
        "OMICSCLAW_RUN_PYTHON=%s was not found on PATH; falling back to sys.executable=%s",
        candidate,
        sys.executable,
    )
    return sys.executable


PYTHON = get_skill_runner_python()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PHOTO_BYTES = 20 * 1024 * 1024

if str(OMICSCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(OMICSCLAW_DIR))
from omicsclaw.common.report import build_output_dir_name
from omicsclaw.common.user_guidance import (
    extract_user_guidance_lines,
    extract_user_guidance_payloads,
    format_user_guidance_payload,
    render_guidance_block,
    strip_user_guidance_lines,
)
from omicsclaw.core.registry import ensure_registry_loaded, registry
from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_registry
from omicsclaw.runtime.context_assembler import assemble_chat_context as _assemble_chat_context
from omicsclaw.runtime.engineering_tools import build_engineering_tool_executors
from omicsclaw.runtime.query_engine import (
    QueryEngineCallbacks,
    QueryEngineConfig,
    QueryEngineContext,
    run_query_engine,
)
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.policy import TOOL_POLICY_ALLOW
from omicsclaw.runtime.policy_state import ToolPolicyState
from omicsclaw.runtime.system_prompt import build_system_prompt
from omicsclaw.runtime.tool_orchestration import (
    EXECUTION_STATUS_POLICY_BLOCKED,
    ToolExecutionRequest,
)
from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.transcript_store import (
    TranscriptStore,
    build_selective_replay_context,
    sanitize_tool_history as _runtime_sanitize_tool_history,
)
from omicsclaw.runtime.tool_spec import PROGRESS_POLICY_ANALYSIS
from omicsclaw.runtime.verification import format_completion_mapping_summary

OMICS_EXTENSIONS = {
    f".{ext.lstrip('.')}"
    for domain in registry.domains.values()
    for ext in domain.get("primary_data_types", [])
    if ext != "*"
}
OMICS_EXTENSIONS.update({".csv", ".tsv", ".txt.gz"}) # Add generic table formats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("omicsclaw.bot")


def _skill_registry():
    return ensure_registry_loaded()

# ---------------------------------------------------------------------------
# Skills table formatter (for /skills command in bot)
# ---------------------------------------------------------------------------


def format_skills_table(plain: bool = False) -> str:
    """Format all registered skills as categorized tables for bot display.

    Args:
        plain: If True, use ASCII markers instead of emoji (for platforms
               like Feishu where emoji gets stripped by strip_markup).
    """
    skill_registry = _skill_registry()

    # Group canonical skills by domain (exclude legacy alias duplicates)
    domain_skills: dict[str, list[tuple[str, dict]]] = {}
    for alias, info in skill_registry.skills.items():
        if alias != info.get("alias", alias):
            continue  # skip legacy alias pointers
        d = info.get("domain", "other")
        domain_skills.setdefault(d, []).append((alias, info))

    total = sum(len(v) for v in domain_skills.values())
    if plain:
        lines = [f"OmicsClaw Skills ({total} total)", "=" * 40, ""]
    else:
        lines = [f"🔬 OmicsClaw Skills ({total} total)", ""]

    for domain_key, domain_info in skill_registry.domains.items():
        skills_in_domain = domain_skills.get(domain_key, [])
        if not skills_in_domain:
            continue

        domain_name = domain_info.get("name", domain_key.title())
        data_types = domain_info.get("primary_data_types", [])
        types_str = ", ".join(f".{t}" if t != "*" else "*" for t in data_types)
        n = len(skills_in_domain)

        if plain:
            lines.append(f"[{domain_name}] ({n} skills, {types_str})")
            lines.append("~" * 40)
            for alias, info in skills_in_domain:
                script = info.get("script")
                tag = "[OK]" if script and script.exists() else "[--]"
                desc = info.get("description", "").split("—")[0].strip()
                lines.append(f"  {tag} {alias}")
                lines.append(f"       {desc}")
        else:
            lines.append(f"📂 {domain_name} [{types_str}]")
            for alias, info in skills_in_domain:
                script = info.get("script")
                status = "✅" if script and script.exists() else "📋"
                desc = info.get("description", "").split("—")[0].strip()
                lines.append(f"  {status} {alias}")
                lines.append(f"      {desc}")

        lines.append("")

    # Dynamically discovered skills not in known domains
    known = set(skill_registry.domains.keys())
    extra = [
        (a, i)
        for a, i in skill_registry.skills.items()
        if i.get("domain", "other") not in known
    ]
    if extra:
        if plain:
            lines.append("[Other] (Dynamically Discovered)")
            lines.append("~" * 40)
        else:
            lines.append("📂 Other (Dynamically Discovered)")
        for alias, info in extra:
            script = info.get("script")
            desc = info.get("description", "").split("—")[0].strip()
            if plain:
                tag = "[OK]" if script and script.exists() else "[--]"
                lines.append(f"  {tag} {alias}")
                lines.append(f"       {desc}")
            else:
                status = "✅" if script and script.exists() else "📋"
                lines.append(f"  {status} {alias}")
                lines.append(f"      {desc}")
        lines.append("")

    if plain:
        lines.append("[OK] = ready  [--] = planned")
    else:
        lines.append("✅ = ready  📋 = planned")
    return "\n".join(lines)


def _iter_primary_skill_entries() -> list[tuple[str, dict]]:
    """Return canonical skill entries only, excluding alias pointers."""
    skill_registry = _skill_registry()
    items = [
        (alias, info)
        for alias, info in skill_registry.skills.items()
        if alias == info.get("alias", alias)
    ]
    items.sort(key=lambda pair: (str(pair[1].get("domain", "")), pair[0]))
    return items


def _primary_skill_count() -> int:
    return len(_iter_primary_skill_entries())


# ---------------------------------------------------------------------------
# Audit log (JSONL) — extracted to bot.audit per ADR 0001.
# ---------------------------------------------------------------------------

from bot.audit import audit  # re-export


# ---------------------------------------------------------------------------
# Module-level state (initialised by init())
# ---------------------------------------------------------------------------

llm: AsyncOpenAI | None = None
OMICSCLAW_MODEL: str = PROVIDER_PRESETS["deepseek"][1]
LLM_PROVIDER_NAME: str = ""

MAX_HISTORY = int(os.getenv("OMICSCLAW_MAX_HISTORY", "50"))
MAX_HISTORY_CHARS = int(os.getenv("OMICSCLAW_MAX_HISTORY_CHARS", "0"))
MAX_CONVERSATIONS = int(os.getenv("OMICSCLAW_MAX_CONVERSATIONS", "1000"))
TOOL_RESULT_INLINE_BYTES = int(os.getenv("OMICSCLAW_TOOL_RESULT_INLINE_BYTES", "6000"))
TOOL_RESULT_PREVIEW_CHARS = int(os.getenv("OMICSCLAW_TOOL_RESULT_PREVIEW_CHARS", "1200"))
TOOL_RESULT_STORAGE_DIR = OMICSCLAW_DIR / "bot" / "logs" / "tool_results"
transcript_store = TranscriptStore(
    max_history=MAX_HISTORY,
    max_history_chars=MAX_HISTORY_CHARS or None,
    max_conversations=MAX_CONVERSATIONS,
    sanitizer=_runtime_sanitize_tool_history,
)
tool_result_store = ToolResultStore(
    storage_dir=TOOL_RESULT_STORAGE_DIR,
    inline_bytes=TOOL_RESULT_INLINE_BYTES,
    preview_chars=TOOL_RESULT_PREVIEW_CHARS,
)
conversations = transcript_store.messages_by_chat
_conversation_access = transcript_store.access_by_chat  # LRU tracking

# received_files moved to bot.session (re-exported via the SessionManager import below).
pending_media: dict[int | str, list[dict]] = {}
pending_text: list[str] = []
pending_preflight_requests: dict[int | str, dict] = {}

BOT_START_TIME = time.time()

# Preflight state machine — extracted to bot.preflight per ADR 0001.
from bot.preflight import (
    _PREFLIGHT_TOP_LEVEL_ARGS,
    _apply_preflight_answers,
    _build_pending_preflight_message,
    _coerce_preflight_value,
    _extract_pending_preflight_payload,
    _is_affirmative_preflight_confirmation,
    _parse_preflight_reply,
    _preflight_payload_needs_reply,
    _remember_pending_preflight_request,
    _set_or_replace_extra_arg,
    _strip_answer_prefix,
)



# Memory system (optional)
memory_store = None
session_manager = None

# ---------------------------------------------------------------------------
# Usage statistics (token counters) — extracted to bot.billing per ADR 0001.
# Names below are re-exported so legacy callers (tests, app integration)
# resolve through bot.core unchanged.
# ---------------------------------------------------------------------------

from bot.billing import (
    _TOKEN_PRICES,
    _TOKEN_PRICE_KEYS_BY_LENGTH,
    _get_token_price,
    _usage,
    accumulate_usage,
    get_token_price,
    reset_usage,
)
from bot.billing import accumulate_usage as _accumulate_usage  # legacy alias
from bot.billing import get_usage_snapshot as _billing_snapshot


def get_usage_snapshot() -> dict:
    """Zero-arg snapshot using the active bot model + provider."""
    return _billing_snapshot(model=OMICSCLAW_MODEL, provider=LLM_PROVIDER_NAME)


# ---------------------------------------------------------------------------
# Shared rate limiter — extracted to bot.rate_limit per ADR 0001.
# ---------------------------------------------------------------------------

from bot.rate_limit import (
    RATE_LIMIT_PER_HOUR,
    _rate_buckets,
    check_rate_limit,
)


# ---------------------------------------------------------------------------
# Memory auto-capture + env-error parsing + output state — extracted to
# bot.skill_orchestration per ADR 0001 (#119 reduced-scope follow-up).
# ---------------------------------------------------------------------------

from bot.skill_orchestration import (
    _auto_capture_analysis,
    _auto_capture_dataset,
    _classify_env_error,
    _extract_env_snippet,
    _extract_fix_hint,
    _format_next_steps,
    _read_result_json,
    _resolve_last_output_dir,
    _update_preprocessing_state,
)



# ---------------------------------------------------------------------------
# Session Manager + init() — extracted to bot.session per ADR 0001.
# ---------------------------------------------------------------------------

from bot.session import SessionManager, _evict_lru_conversations, init, received_files  # re-export



SYSTEM_PROMPT: str = ""

def _ensure_system_prompt():
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = build_system_prompt(omicsclaw_dir=str(OMICSCLAW_DIR))

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

def get_tools() -> list[dict]:
    return list(get_tool_runtime().openai_tools)


def _build_bot_tool_context() -> BotToolContext:
    """Thin alias around the canonical ``build_default_bot_tool_context``
    in ``omicsclaw/runtime/bot_tools.py``. Kept as a module-private hook
    so other bot/core.py callers can monkeypatch in tests if needed —
    do not inline this call site away."""
    from omicsclaw.runtime.bot_tools import build_default_bot_tool_context

    return build_default_bot_tool_context()


def get_tool_registry():
    return build_bot_tool_registry(_build_bot_tool_context())


def _build_llm_timeout():
    """Build the shared timeout policy for the AsyncOpenAI client."""
    return build_llm_timeout_policy(log=logger).as_httpx_timeout()

# ---------------------------------------------------------------------------
# Path validation + file discovery — extracted to bot.path_validation per ADR 0001.
# ---------------------------------------------------------------------------

from bot.path_validation import (
    TRUSTED_DATA_DIRS,
    _build_trusted_dirs,
    _ensure_trusted_dirs,
    discover_file,
    resolve_dest,
    sanitize_filename,
    validate_input_path,
    validate_path,
)


# ---------------------------------------------------------------------------
# execute_omicsclaw
# ---------------------------------------------------------------------------


# Deep learning methods that may take a long time
DEEP_LEARNING_METHODS = {
    "cell2location", "destvi", "stereoscope", "tangram",
    "spagcn", "stagate", "graphst", "scvi", "velovi",
    "scanvi", "cellassign",
}

# sc-batch-integration preflight — extracted to omicsclaw.runtime.preflight.sc_batch per ADR 0001.
from omicsclaw.runtime.preflight.sc_batch import (
    _BATCH_KEY_EXACT_PREFERENCES,
    _BATCH_KEY_EXCLUDED_COLUMNS,
    _BATCH_KEY_HINT_TERMS,
    _auto_prepare_sc_batch_integration,
    _extract_flag_value,
    _find_batch_key_candidates,
    _format_auto_prepare_summary,
    _format_batch_key_clarification,
    _format_sc_batch_workflow_guidance,
    _get_sc_batch_integration_workflow_plan,
    _inspect_h5ad_integration_readiness,
    _load_h5ad_obs_dataframe,
    _maybe_require_batch_integration_workflow,
    _maybe_require_batch_key_selection,
    _normalize_obs_key,
    _resolve_requested_batch_key,
    _score_batch_key_candidate,
)




# ---------------------------------------------------------------------------
# Skill execution + lookup + param-hint helpers — extracted to
# bot.skill_orchestration per ADR 0001 (#119 reduced-scope follow-up).
# ---------------------------------------------------------------------------

from bot.skill_orchestration import (
    _build_method_preview,
    _build_param_hint,
    _infer_skill_for_method,
    _lookup_skill_info,
    _normalize_extra_args,
    _resolve_param_hint_info,
    _run_omics_skill_step,
    _run_skill_via_shared_runner,
)



# If the top-1 capability candidate and top-2 score within this gap, we do
# NOT blindly execute — instead the tool returns a disambiguation list so the
# LLM re-invokes with a specific skill. Calibrated against
# ``capability_resolver._candidate_score`` output magnitudes (single keyword
# match is worth ~0.85 points; an alias hit is worth ~10).
# _AUTO_DISAMBIGUATE_GAP + auto-routing banner / disambiguation —
# extracted to bot.skill_orchestration per ADR 0001.
from bot.skill_orchestration import (
    _AUTO_DISAMBIGUATE_GAP,
    _format_auto_disambiguation,
    _format_auto_route_banner,
)


# ---------------------------------------------------------------------------
# Tool executors (24 execute_* functions) + dispatch — extracted to
# bot.tool_executors per ADR 0001 (#120).
# ---------------------------------------------------------------------------

from bot.tool_executors import (
    _available_tool_executors,
    _build_tool_runtime,
    execute_consult_knowledge,
    execute_create_omics_skill,
    execute_custom_analysis_execute,
    execute_fetch_geo_metadata,
    execute_forget,
    execute_generate_audio,
    execute_get_file_size,
    execute_inspect_data,
    execute_inspect_file,
    execute_list_directory,
    execute_list_skills_in_domain,
    execute_make_directory,
    execute_move_file,
    execute_omicsclaw,
    execute_parse_literature,
    execute_read_knowhow,
    execute_recall,
    execute_remember,
    execute_remove_file,
    execute_replot_skill,
    execute_resolve_capability,
    execute_save_file,
    execute_web_method_search,
    execute_write_file,
    get_tool_executors,
    get_tool_runtime,
)



def __getattr__(name: str):
    if name == "TOOL_RUNTIME":
        return get_tool_runtime()
    if name == "TOOLS":
        return get_tools()
    if name == "TOOL_EXECUTORS":
        return get_tool_executors()
    raise AttributeError(name)

MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))  # Increased from 10, configurable


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


def _format_llm_api_error_message(exc: Exception) -> str:
    detail = str(exc).strip() or type(exc).__name__
    provider = (LLM_PROVIDER_NAME or "").strip().lower()
    base_url = ""
    try:
        from omicsclaw.core.provider_runtime import get_active_provider_runtime

        runtime = get_active_provider_runtime()
        base_url = str(getattr(runtime, "base_url", "") or "").strip()
    except Exception:
        base_url = ""
    if not base_url:
        base_url = str(
            os.getenv("LLM_BASE_URL", "") or os.getenv("OMICSCLAW_BASE_URL", "") or ""
        ).strip()

    if provider == "custom":
        endpoint_hint = (
            f" Custom endpoint base_url is `{base_url}`."
            if base_url
            else " Custom endpoint base_url is empty."
        )
        return (
            "LLM provider request failed for the custom endpoint:"
            f" {detail}.{endpoint_hint} Ensure the base URL is the "
            "OpenAI-compatible API root, commonly ending in `/v1`, not the "
            "provider dashboard or homepage."
        )

    return f"Sorry, I'm having trouble thinking right now -- API error: {detail}"


def _sanitize_tool_history(history: list[dict], warn: bool = True) -> list[dict]:
    return _runtime_sanitize_tool_history(history, warn=warn)


def _normalize_tool_callback_args(callback, args: tuple) -> tuple:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return args

    positional_capacity = 0
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            return args
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional_capacity += 1
    return args[:positional_capacity]


async def _emit_tool_callback(callback, *args) -> None:
    if not callback:
        return
    callback_args = _normalize_tool_callback_args(callback, args)
    if asyncio.iscoroutinefunction(callback):
        await callback(*callback_args)
    else:
        callback(*callback_args)


def _coerce_timeout_seconds(value) -> int | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return max(1, round(seconds))


def _extract_timeout_seconds_from_text(text: str) -> int | None:
    if not text:
        return None

    patterns = (
        r"timed out after (?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
        r"timeout after (?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        seconds = _coerce_timeout_seconds(match.group("seconds"))
        if seconds is not None:
            return seconds
    return None


def _extract_tool_timeout_seconds(execution_result, display_output) -> int | None:
    error = getattr(execution_result, "error", None)
    if error is not None:
        for attr_name in (
            "timeout",
            "timeout_seconds",
            "elapsed_seconds",
            "elapsed_time_seconds",
            "seconds",
        ):
            seconds = _coerce_timeout_seconds(getattr(error, attr_name, None))
            if seconds is not None:
                return seconds

        seconds = _extract_timeout_seconds_from_text(str(error))
        if seconds is not None:
            return seconds

    display_text = str(display_output or "")
    if "timed out" in display_text.lower() or "timeout" in display_text.lower():
        return _extract_timeout_seconds_from_text(display_text)

    return None


def _build_tool_result_callback_metadata(execution_result, display_output) -> dict[str, object]:
    timeout_seconds = _extract_tool_timeout_seconds(execution_result, display_output)
    metadata: dict[str, object] = {
        "status": getattr(execution_result, "status", ""),
        "success": bool(getattr(execution_result, "success", False)),
        "is_error": bool(not getattr(execution_result, "success", False) or timeout_seconds),
    }

    error = getattr(execution_result, "error", None)
    if error is not None:
        metadata["error_type"] = type(error).__name__
    if timeout_seconds is not None:
        metadata["timed_out"] = True
        metadata["elapsed_seconds"] = timeout_seconds
    return metadata


def _build_bot_query_engine_callbacks(
    *,
    chat_id: int | str,
    progress_fn,
    progress_update_fn,
    on_tool_call,
    on_tool_result,
    on_stream_content,
    on_stream_reasoning,
    request_tool_approval,
    logger_obj,
    audit_fn,
    deep_learning_methods: set[str],
    usage_accumulator,
    on_context_compacted=None,
):
    notified_methods: set[str] = set()

    async def before_tool(request: ToolExecutionRequest):
        func_name = request.name
        func_args = request.arguments
        spec = request.spec
        policy_decision = request.policy_decision
        logger_obj.info(f"Tool call: {func_name}({json.dumps(func_args)[:200]})")
        audit_fn(
            "tool_call",
            chat_id=str(chat_id),
            tool=func_name,
            args_preview=json.dumps(func_args, default=str)[:300],
            policy_action=(
                policy_decision.action if policy_decision is not None else TOOL_POLICY_ALLOW
            ),
        )
        await _emit_tool_callback(on_tool_call, func_name, func_args)

        progress_handle = None
        if (
            policy_decision is not None
            and not policy_decision.allows_execution
        ):
            return {"progress_handle": None}

        if spec is not None and spec.progress_policy == PROGRESS_POLICY_ANALYSIS and progress_fn:
            dl_method = (func_args.get("method") or "").lower()
            if dl_method in deep_learning_methods and dl_method not in notified_methods:
                notified_methods.add(dl_method)
                method_display = func_args.get("method", dl_method)
                progress_handle = await progress_fn(
                    f"⏳ **{method_display}** is a deep learning method and may take "
                    f"10-60 minutes depending on data size. Please be patient...\n\n"
                    f"💡 The analysis is running on the server, you can leave this "
                    f"chat open and come back later."
                )
        return {"progress_handle": progress_handle}

    async def after_tool(execution_result, result_record, tool_state):
        request = execution_result.request
        func_name = request.name
        func_args = request.arguments
        progress_handle = (tool_state or {}).get("progress_handle")
        policy_decision = execution_result.policy_decision

        if progress_handle and progress_update_fn:
            method_display = func_args.get("method") or "analysis"
            if execution_result.success:
                await progress_update_fn(
                    progress_handle,
                    f"✅ **{method_display}** analysis complete!"
                )
            else:
                error_name = type(execution_result.error).__name__ if execution_result.error else "Error"
                await progress_update_fn(
                    progress_handle,
                    f"❌ **{method_display}** failed: {error_name}"
                )

        if (
            execution_result.status == EXECUTION_STATUS_POLICY_BLOCKED
            and policy_decision is not None
        ):
            audit_fn(
                "tool_policy_blocked",
                chat_id=str(chat_id),
                tool=func_name,
                action=policy_decision.action,
                reason=policy_decision.reason[:300],
                risk=policy_decision.risk_level,
            )

        if execution_result.error:
            logger_obj.error(
                "Tool %s raised: %s",
                func_name,
                execution_result.error,
                exc_info=(
                    type(execution_result.error),
                    execution_result.error,
                    execution_result.error.__traceback__,
                ),
            )
            audit_fn(
                "tool_error",
                chat_id=str(chat_id),
                tool=func_name,
                error=str(execution_result.error)[:300],
            )

        if request.executor:
            display_output = result_record.content
            if func_name == "omicsclaw":
                pending_payload = _extract_pending_preflight_payload(display_output)
                if _preflight_payload_needs_reply(pending_payload):
                    _remember_pending_preflight_request(
                        chat_id,
                        args=func_args,
                        payload=pending_payload,
                    )
                else:
                    pending_preflight_requests.pop(chat_id, None)
            if func_name == "consult_knowledge":
                try:
                    from omicsclaw.knowledge.retriever import consume_runtime_notice

                    notice = consume_runtime_notice()
                    if notice:
                        display_output = f"{notice}\n{display_output}"
                except Exception:
                    pass
            await _emit_tool_callback(
                on_tool_result,
                func_name,
                display_output,
                _build_tool_result_callback_metadata(execution_result, display_output),
            )

    def on_llm_error(exc: Exception) -> str:
        logger_obj.debug("LLM API error: %s", exc)
        return _format_llm_api_error_message(exc)

    return QueryEngineCallbacks(
        accumulate_usage=usage_accumulator,
        on_stream_content=on_stream_content,
        on_stream_reasoning=on_stream_reasoning,
        before_tool=before_tool,
        after_tool=after_tool,
        request_tool_approval=request_tool_approval,
        on_llm_error=on_llm_error,
        on_context_compacted=on_context_compacted,
    )


async def _maybe_resume_pending_preflight_request(
    *,
    chat_id: int | str,
    user_content: str | list,
    session_id: str | None,
) -> str | None:
    state = pending_preflight_requests.get(chat_id)
    if not state or not isinstance(user_content, str):
        return None

    user_text = user_content.strip()
    if not user_text or user_text.startswith("/"):
        return None

    if (
        state.get("payload", {}).get("confirmations")
        and not state.get("pending_fields")
        and not _is_affirmative_preflight_confirmation(user_text)
    ):
        pending_preflight_requests.pop(chat_id, None)
        return None

    resolved, remaining = _parse_preflight_reply(state, user_text)
    state["answers"] = resolved
    if remaining:
        pending_preflight_requests[chat_id] = state
        return _build_pending_preflight_message(state, answered=resolved, remaining_fields=remaining)

    updated_args = _apply_preflight_answers(
        state.get("original_args", {}),
        state.get("pending_fields", []),
        resolved,
    )
    if state.get("payload", {}).get("confirmations"):
        updated_args["confirmed_preflight"] = True
    pending_preflight_requests.pop(chat_id, None)
    result = await execute_omicsclaw(updated_args, session_id=session_id, chat_id=chat_id)

    pending_payload = _extract_pending_preflight_payload(result)
    if _preflight_payload_needs_reply(pending_payload):
        _remember_pending_preflight_request(
            chat_id,
            args=updated_args,
            payload=pending_payload,
        )
    return strip_user_guidance_lines(result) or result


async def llm_tool_loop(
    chat_id: int | str,
    user_content: str | list,
    user_id: str = None,
    platform: str = None,
    plan_context: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    scoped_memory_scope: str = "",
    mcp_servers: tuple[str, ...] | None = None,
    output_style: str = "",
    progress_fn=None,
    progress_update_fn=None,
    on_tool_call=None,
    on_tool_result=None,
    on_stream_content=None,
    on_stream_reasoning=None,
    on_context_compacted=None,
    # Per-request runtime overrides (desktop app frontend)
    model_override: str = "",
    extra_api_params: dict | None = None,
    max_tokens_override: int = 0,
    system_prompt_append: str = "",
    mode: str = "",
    usage_accumulator=None,
    request_tool_approval=None,
    policy_state=None,
) -> str:
    """
    Run the LLM tool-use loop:
    1. Append user message to history
    2. Call LLM with system prompt + history + tools
    3. If tool_calls -> execute -> append results -> call again
    4. Return final text

    progress_fn: async callable(msg) -> handle. Sends a progress message, returns a handle.
    progress_update_fn: async callable(handle, msg). Updates a previously sent progress message.
    on_tool_call: async callable(tool.name, arguments: dict). Called before a tool executes.
    on_tool_result: async callable(tool.name, result: Any). Called after a tool completes.
    on_stream_content: async callable(chunk: str). Called as final text streams in.
    """
    # Handle commands before LLM call
    if isinstance(user_content, str) and user_content.strip().startswith("/"):
        cmd = user_content.strip().lower()

        if cmd == "/clear":
            # Only clear conversation history, keep memory intact
            transcript_store.clear(chat_id)
            tool_result_store.clear(chat_id)
            return "✓ Conversation history cleared. (Memory preserved)"

        elif cmd == "/new":
            # Clear conversation history but keep memory
            transcript_store.clear(chat_id)
            tool_result_store.clear(chat_id)
            return "✓ New conversation started. (Memory preserved)"

        elif cmd == "/forget":
            # Clear both conversation and memory for a complete reset
            transcript_store.clear(chat_id)
            tool_result_store.clear(chat_id)

            if session_manager and user_id and platform:
                session_id = f"{platform}:{user_id}:{chat_id}"
                await memory_store.delete_session(session_id)

            return "✓ Memory and conversation cleared. (Fresh start)"

        elif cmd == "/plan":
            from pathlib import Path as _PlanPath

            candidate_dirs: list[_PlanPath] = []
            for raw in (pipeline_workspace, workspace):
                if raw:
                    candidate_dirs.append(_PlanPath(str(raw)))

            for directory in candidate_dirs:
                plan_path = directory / "plan.md"
                if plan_path.is_file():
                    try:
                        text = plan_path.read_text(encoding="utf-8")
                    except OSError as exc:
                        return f"✗ Failed to read {plan_path}: {exc}"
                    max_chars = 8000
                    if len(text) > max_chars:
                        text = (
                            text[:max_chars]
                            + f"\n\n... (truncated; full plan at {plan_path})"
                        )
                    return f"📋 Plan from `{plan_path}`:\n\n{text}"
            return (
                "No plan saved yet. Set a workspace and ask me to create a "
                "plan, or invoke a pipeline that writes plan.md."
            )

        elif cmd == "/compact":
            from omicsclaw.runtime.context_compaction import (
                ContextCompactionConfig,
                compact_history,
                is_compaction_summary_message,
                unwrap_compaction_summary,
                wrap_compaction_summary,
            )

            history = transcript_store.get_history(chat_id)
            # Boundary tracking: locate the LAST manual-/compact summary so
            # we don't feed it back into the summariser. Messages before and
            # including that marker are already-compacted; only what comes
            # after needs new compaction.
            boundary_index = -1
            for idx in range(len(history) - 1, -1, -1):
                if is_compaction_summary_message(history[idx]):
                    boundary_index = idx
                    break

            previous_body = (
                unwrap_compaction_summary(history[boundary_index]["content"])
                if boundary_index >= 0
                else ""
            )
            tail_to_compact = (
                history[boundary_index + 1:] if boundary_index >= 0 else list(history)
            )

            compaction_config = ContextCompactionConfig()
            result = compact_history(
                tail_to_compact,
                preserve_messages=compaction_config.reactive_preserve_messages,
                preserve_chars=compaction_config.reactive_preserve_chars,
                config=compaction_config,
                workspace=workspace or pipeline_workspace or None,
            )
            if result.omitted_count == 0:
                if boundary_index >= 0:
                    return (
                        "✓ Already compacted; no new messages to compact "
                        "since last /compact."
                    )
                return "✓ Nothing to compact — current history is already short."

            if previous_body:
                combined_body = (
                    f"{previous_body}\n\n---\n\n{result.summary}".strip()
                )
            else:
                combined_body = result.summary
            new_history: list[dict] = [
                {
                    "role": "system",
                    "content": wrap_compaction_summary(combined_body),
                }
            ] + list(result.messages)
            transcript_store.replace_history(chat_id, new_history)
            return (
                f"✓ Compacted {result.omitted_count} earlier message(s); "
                f"kept the most recent {len(result.messages)}. "
                "Summary preserved as a system note."
            )

        elif cmd == "/files":
            try:
                items = []
                for item in sorted(DATA_DIR.iterdir()):
                    if item.is_file():
                        size_mb = item.stat().st_size / (1024 * 1024)
                        ext = item.suffix
                        items.append(f"📄 {item.name} ({size_mb:.2f} MB)")
                if not items:
                    return f"📁 Data directory is empty: {DATA_DIR}"
                return f"📁 Data files ({DATA_DIR}):\n" + "\n".join(items[:20])
            except Exception as e:
                return f"Error listing files: {e}"

        elif cmd == "/outputs":
            try:
                items = []
                if OUTPUT_DIR.exists():
                    for item in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                        if item.is_dir():
                            mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                            items.append(f"📊 {item.name} ({mtime})")
                if not items:
                    return f"📂 No analysis outputs yet: {OUTPUT_DIR}"
                return f"📂 Recent outputs ({OUTPUT_DIR}):\n" + "\n".join(items[:10])
            except Exception as e:
                return f"Error listing outputs: {e}"

        elif cmd == "/skills":
            return format_skills_table(plain=(platform == "feishu"))

        elif cmd == "/recent":
            try:
                items = []
                if OUTPUT_DIR.exists():
                    for item in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                        if item.is_dir():
                            mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                            report = item / "report.md"
                            summary = "No report"
                            if report.exists():
                                lines = report.read_text(encoding="utf-8").split("\n")
                                summary = next((l.strip("# ") for l in lines if l.startswith("# ")), "Analysis complete")
                            items.append(f"📊 {item.name}\n   {mtime} - {summary}")
                if not items:
                    return "📂 No recent analyses found"
                return "📂 Last 3 Analyses:\n\n" + "\n\n".join(items)
            except Exception as e:
                return f"Error: {e}"

        elif cmd == "/demo":
            return """🎬 Quick Demo Options:

Run any of these for instant results:
• "run spatial-preprocess demo"
• "run spatial-domain-identification demo"
• "run spatial-de demo"
• "run proteomics-ms-qc demo"

Or try: "show me a spatial transcriptomics demo" """

        elif cmd == "/examples":
            return """📚 Usage Examples:

**Literature Analysis:**
• "Parse this paper: https://pubmed.ncbi.nlm.nih.gov/12345"
• "Fetch GEO metadata for GSE204716"
• Upload a PDF file directly

**Data Analysis:**
• "Run spatial-preprocess on brain_visium.h5ad"
• "Analyze data/sample.h5ad with spatial-domain-identification"
• "Run proteomics-ms-qc on proteomics_data.mzML"

**File Operations:**
• "List files in data directory"
• "Show first 20 lines of results.csv"
• "Download https://example.com/data.h5ad"

**Path Mode (for large files):**
• "分析 data/brain_visium.h5ad"
• "对 /mnt/nas/exp1.mzML 做质量控制" """

        elif cmd == "/status":
            uptime = int(time.time() - BOT_START_TIME)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            return f"""🤖 Bot Status:

• Uptime: {hours}h {minutes}m
• LLM Provider: {LLM_PROVIDER_NAME}
• Model: {OMICSCLAW_MODEL}
• Active Conversations: {transcript_store.active_conversation_count}
• Tools Available: {len(get_tool_executors())}
• Skills Loaded: {_primary_skill_count()}
• Data Directory: {DATA_DIR}
• Output Directory: {OUTPUT_DIR}"""

        elif cmd == "/version":
            return f"""ℹ️ OmicsClaw Version:

• Project: OmicsClaw Multi-Omics Analysis Platform
• Domains: Spatial Transcriptomics, Single-Cell, Genomics, Proteomics, Metabolomics
• Skills: {_primary_skill_count()} analysis skills
• Tools: {len(get_tool_executors())} bot tools
• Repository: https://github.com/TianGzlab/OmicsClaw

For updates and documentation, visit the GitHub repository."""

        elif cmd == "/help":
            return """# OmicsClaw Bot Commands

**Quick Commands:**
- `/new` - Start new conversation (memory preserved)
- `/clear` - Clear conversation history (memory preserved)
- `/forget` - Clear conversation + memory (complete reset)
- `/compact` - Shrink long history to recent tail with a summary
- `/plan` - Show plan.md from the active workspace
- `/help` - Show this help message
- `/files` - List data files
- `/outputs` - Show recent analysis results
- `/skills` - List all available analysis skills
- `/recent` - Show last 3 analyses
- `/demo` - Run a quick demo
- `/examples` - Show usage examples
- `/status` - Bot status and uptime
- `/version` - Show version info

**Memory System:**
- `/clear` and `/new` preserve your analysis history and preferences
- Only `/forget` completely clears all memory
- Bot remembers your datasets, analyses, and preferences across sessions

**Literature Analysis:**
- Upload PDF or send article URL/DOI
- "Fetch GEO metadata for GSE123456"
- "Parse this paper: https://..."

**File Operations:**
- "List files in data directory"
- "Show contents of file.csv"
- "Download file from URL"

**Data Analysis:**
- "Run spatial-preprocess on data.h5ad"
- "Analyze GSE123456 dataset"

For more info: https://github.com/TianGzlab/OmicsClaw"""

    resumed_result = await _maybe_resume_pending_preflight_request(
        chat_id=chat_id,
        user_content=user_content,
        session_id=f"{platform}:{user_id}:{chat_id}" if user_id and platform else None,
    )
    if resumed_result is not None:
        transcript_store.append_user_message(chat_id, user_content)
        transcript_store.append_assistant_message(chat_id, content=resumed_result)
        return resumed_result

    _ensure_system_prompt()
    if llm is None:
        return "Error: LLM client not initialised. Call core.init() first."

    transcript_store.max_history = MAX_HISTORY
    transcript_store.max_history_chars = MAX_HISTORY_CHARS or None
    transcript_store.max_conversations = MAX_CONVERSATIONS
    transcript_context = build_selective_replay_context(
        transcript_store.get_history(chat_id),
        metadata={"pipeline_workspace": pipeline_workspace} if pipeline_workspace else None,
        workspace=workspace,
        max_messages=transcript_store.max_history,
        max_chars=transcript_store.max_history_chars,
        sanitizer=transcript_store.sanitizer,
    )

    chat_context = await _assemble_chat_context(
        chat_id=chat_id,
        user_content=user_content,
        user_id=user_id,
        platform=platform,
        session_manager=session_manager,
        system_prompt_builder=build_system_prompt,
        skill_aliases=tuple(_skill_registry().skills.keys()),
        plan_context=plan_context,
        transcript_context=transcript_context,
        omicsclaw_dir=str(OMICSCLAW_DIR),
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
        scoped_memory_scope=scoped_memory_scope,
        mcp_servers=tuple(mcp_servers or ()),
        output_style=output_style,
    )
    session_id = chat_context.session_id
    system_prompt = chat_context.system_prompt

    # Identity anchor: many open-source / distilled models will claim to be
    # Claude or GPT when asked about their base model because of training-data
    # contamination. Tell them the truth about what is actually serving them,
    # using the per-request model override when the frontend provided one.
    effective_model = (model_override or OMICSCLAW_MODEL or "").strip()
    effective_provider = (LLM_PROVIDER_NAME or "").strip()
    if effective_model and effective_provider:
        system_prompt = system_prompt.rstrip() + (
            "\n\n## Underlying model identity\n"
            f"You are powered by the LLM `{effective_model}` served via the `{effective_provider}` provider. "
            "If the user asks which model or provider backs you, answer truthfully with these exact names. "
            "Do NOT claim to be Claude, GPT, Gemini, DeepSeek, or any other assistant unless it matches the names above. "
            "Do NOT claim to be built by Anthropic, OpenAI, or Google unless the provider above matches."
        )

    # Apply per-request system prompt additions
    if system_prompt_append:
        system_prompt = system_prompt.rstrip() + "\n\n" + system_prompt_append.strip()
    if mode and mode != "ask":
        _mode_hints = {
            "code": "You are in code mode. Prefer writing and editing code to accomplish the user's goals.",
            "plan": "You are in plan mode. Create detailed plans and explain your reasoning before taking action.",
        }
        hint = _mode_hints.get(mode, "")
        if hint:
            system_prompt = system_prompt.rstrip() + "\n\n## Mode\n" + hint

    tool_runtime = _build_tool_runtime()
    # Phase 1 (tool-list-compression): build the per-request filtered
    # tool payload. ``chat_context.prompt_context.request`` carries the
    # ContextAssemblyRequest that drove system-prompt assembly; reusing
    # it here means tool selection sees the same query / surface /
    # workspace / capability context the system prompt did.
    _tool_selection_request = chat_context.prompt_context.request
    request_tools = tuple(
        get_tool_registry().to_openai_tools_for_request(_tool_selection_request)
    )
    hook_runtime = build_default_lifecycle_hook_runtime(OMICSCLAW_DIR)
    callbacks = _build_bot_query_engine_callbacks(
        chat_id=chat_id,
        progress_fn=progress_fn,
        progress_update_fn=progress_update_fn,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
        on_stream_content=on_stream_content,
        on_stream_reasoning=on_stream_reasoning,
        request_tool_approval=request_tool_approval,
        logger_obj=logger,
        audit_fn=audit,
        deep_learning_methods=DEEP_LEARNING_METHODS,
        usage_accumulator=usage_accumulator or _accumulate_usage,
        on_context_compacted=on_context_compacted,
    )
    resolved_policy_state = ToolPolicyState.from_mapping(
        policy_state,
        surface=platform or "bot",
    )
    return await run_query_engine(
        llm=llm,
        context=QueryEngineContext(
            chat_id=chat_id,
            session_id=session_id,
            system_prompt=system_prompt,
            user_message_content=chat_context.user_message_content,
            surface=platform or "bot",
            policy_state=resolved_policy_state,
            hook_runtime=hook_runtime,
            tool_runtime_context={
                "omicsclaw_dir": str(OMICSCLAW_DIR),
                "workspace": workspace,
                "pipeline_workspace": pipeline_workspace,
            },
            request_tools=request_tools,
        ),
        tool_runtime=tool_runtime,
        transcript_store=transcript_store,
        tool_result_store=tool_result_store,
        config=QueryEngineConfig(
            model=model_override or OMICSCLAW_MODEL,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=max_tokens_override if max_tokens_override > 0 else 8192,
            llm_error_types=(APIError,),
            extra_api_params=extra_api_params or {},
            deepseek_reasoning_passback=(
                (LLM_PROVIDER_NAME or "").strip().lower() == "deepseek"
            ),
        ),
        callbacks=callbacks,
    )


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def strip_markup(text: str) -> str:
    """Remove markdown/emoji formatting for plain-text messaging.

    Preserves structural elements like list bullets and code content
    while stripping decorative formatting.
    """
    # Strip internal system annotations (not meant for end-users)
    text = re.sub(r"\n*-{3}\n*", "\n", text)  # Strip --- separators
    text = re.sub(
        r"\[(?:MEDIA DELIVERY|Available outputs|Other available outputs)[^\]]*\]\n*",
        "", text,
    )

    # Convert code blocks to indented text (keep content, remove fences)
    text = re.sub(r"```\w*\n?(.*?)```", r"\1", text, flags=re.DOTALL)

    # Inline formatting → plain text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)

    # Markdown links → text only
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

    # Heading markers → plain text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Block quotes → plain text (keep content)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # List bullets: normalise to "- " (keep structure)
    text = re.sub(r"^[\s]*[*]\s+", "- ", text, flags=re.MULTILINE)

    # Strip emojis
    text = re.sub(
        r"[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF"
        r"\U0000200D\U00002B50\U00002B55\U000023CF\U000023E9-\U000023F3"
        r"\U000023F8-\U000023FA\U0000231A\U0000231B\U00003030\U000000A9"
        r"\U000000AE\U00002122\U00002139\U00002194-\U00002199"
        r"\U000021A9-\U000021AA\U0000FE0F]+",
        "",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
