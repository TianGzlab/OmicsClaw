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

from openai import APIError, AsyncOpenAI, OpenAIError  # APIError + OpenAIError kept for bot.session.init() monkeypatch + bot.session error-handling

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
from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.transcript_store import (
    TranscriptStore,
    build_selective_replay_context,
    sanitize_tool_history as _runtime_sanitize_tool_history,
)

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



# ---------------------------------------------------------------------------
# System prompt + tool-registry hooks — extracted to bot.agent_loop per ADR 0001 (#121).
# Re-exported lazily via ``__getattr__`` below to avoid circular load.
# ---------------------------------------------------------------------------


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



_AGENT_LOOP_REEXPORTS = frozenset({
    "SYSTEM_PROMPT",
    "MAX_TOOL_ITERATIONS",
    "_build_bot_query_engine_callbacks",
    "_build_bot_tool_context",
    "_build_llm_timeout",
    "_build_tool_result_callback_metadata",
    "_coerce_timeout_seconds",
    "_emit_tool_callback",
    "_ensure_system_prompt",
    "_extract_timeout_seconds_from_text",
    "_extract_tool_timeout_seconds",
    "_format_llm_api_error_message",
    "_maybe_resume_pending_preflight_request",
    "_normalize_tool_callback_args",
    "_sanitize_tool_history",
    "get_tool_registry",
    "get_tools",
    "llm_tool_loop",
})


def __getattr__(name: str):
    if name == "TOOL_RUNTIME":
        return get_tool_runtime()
    if name == "TOOLS":
        return get_tools()
    if name == "TOOL_EXECUTORS":
        return get_tool_executors()
    if name in _AGENT_LOOP_REEXPORTS:
        # Lazy re-export — avoids circular load when ``bot.agent_loop`` is
        # imported directly (test path or downstream module imports
        # ``bot.agent_loop`` before ``bot.core``). The agent loop module
        # itself only depends on stable bot.core symbols defined before
        # this point (paths, transcript_store, audit, etc.).
        #
        # Memoise: write the resolved value back to bot.core's globals so
        # subsequent lookups skip ``__getattr__`` entirely (O(1) module
        # dict access ≈ 55ns vs the ~780ns first call).
        import bot.agent_loop
        value = getattr(bot.agent_loop, name)
        globals()[name] = value
        return value
    raise AttributeError(name)

# ---------------------------------------------------------------------------
# Agent loop — extracted to bot.agent_loop per ADR 0001 (#121).
# Re-exported lazily via ``__getattr__`` to avoid circular load.
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
