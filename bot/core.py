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
import json
import logging
import os
import re
import requests
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI, APIError

from omicsclaw.common.runtime_env import load_project_dotenv
from omicsclaw.core.provider_registry import (
    PROVIDER_DETECT_ORDER,
    PROVIDER_PRESETS,
    resolve_provider,
)

_PROVIDER_DETECT_ORDER = PROVIDER_DETECT_ORDER


# ---------------------------------------------------------------------------
# Paths (relative to OmicsClaw project root)
# ---------------------------------------------------------------------------

OMICSCLAW_DIR = Path(__file__).resolve().parent.parent
load_project_dotenv(OMICSCLAW_DIR, override=False)
OMICSCLAW_PY = OMICSCLAW_DIR / "omicsclaw.py"
OUTPUT_DIR = OMICSCLAW_DIR / "output"
DATA_DIR = OMICSCLAW_DIR / "data"
EXAMPLES_DIR = OMICSCLAW_DIR / "examples"
PYTHON = sys.executable

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PHOTO_BYTES = 20 * 1024 * 1024

if str(OMICSCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(OMICSCLAW_DIR))
from omicsclaw.common.report import build_output_dir_name
from omicsclaw.core.registry import registry
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
from omicsclaw.runtime.system_prompt import build_system_prompt, get_role_guardrails
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
registry.load_all()

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

# ---------------------------------------------------------------------------
# Skills table formatter (for /skills command in bot)
# ---------------------------------------------------------------------------


def format_skills_table(plain: bool = False) -> str:
    """Format all registered skills as categorized tables for bot display.

    Args:
        plain: If True, use ASCII markers instead of emoji (for platforms
               like Feishu where emoji gets stripped by strip_markup).
    """
    # Group skills by domain
    domain_skills: dict[str, list[tuple[str, dict]]] = {}
    for alias, info in registry.skills.items():
        d = info.get("domain", "other")
        domain_skills.setdefault(d, []).append((alias, info))

    total = len(registry.skills)
    if plain:
        lines = [f"OmicsClaw Skills ({total} total)", "=" * 40, ""]
    else:
        lines = [f"🔬 OmicsClaw Skills ({total} total)", ""]

    for domain_key, domain_info in registry.domains.items():
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
    known = set(registry.domains.keys())
    extra = [(a, i) for a, i in registry.skills.items() if i.get("domain", "other") not in known]
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
    items = [
        (alias, info)
        for alias, info in registry.skills.items()
        if alias == info.get("alias", alias)
    ]
    items.sort(key=lambda pair: (str(pair[1].get("domain", "")), pair[0]))
    return items


def _primary_skill_count() -> int:
    return len(_iter_primary_skill_entries())


# ---------------------------------------------------------------------------
# Audit log (JSONL)
# ---------------------------------------------------------------------------

_AUDIT_LOG_DIR = OMICSCLAW_DIR / "bot" / "logs"
_AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
_AUDIT_LOG_PATH = _AUDIT_LOG_DIR / "audit.jsonl"


def audit(event: str, **kwargs):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
    try:
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        logger.warning(f"Audit log write failed: {e}")


# ---------------------------------------------------------------------------
# Module-level state (initialised by init())
# ---------------------------------------------------------------------------

llm: AsyncOpenAI | None = None
OMICSCLAW_MODEL: str = "deepseek-chat"
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

received_files: dict[int | str, dict] = {}
pending_media: dict[int | str, list[dict]] = {}
pending_text: list[str] = []

BOT_START_TIME = time.time()

# Memory system (optional)
memory_store = None
session_manager = None

# ---------------------------------------------------------------------------
# Usage statistics (token counters)
# ---------------------------------------------------------------------------

_usage: dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "api_calls": 0,
}

# Approximate pricing per 1M tokens (USD) — keyed by provider:model fragment.
# These are reference values; override via LLM_INPUT_PRICE / LLM_OUTPUT_PRICE env vars.
_TOKEN_PRICES: dict[str, tuple[float, float]] = {
    # (input $/1M, output $/1M)
    "deepseek-chat":        (0.27,  1.10),
    "deepseek-reasoner":    (0.55,  2.19),
    "gpt-4o":               (2.50, 10.00),
    "gpt-4o-mini":          (0.15,  0.60),
    "gpt-4-turbo":          (10.0, 30.00),
    "gpt-3.5-turbo":        (0.50,  1.50),
    "claude-3-5-sonnet":    (3.00, 15.00),
    "claude-3-5-haiku":     (0.80,  4.00),
    "claude-3-opus":        (15.0, 75.00),
    "gemini-1.5-pro":       (1.25,  5.00),
    "gemini-1.5-flash":     (0.075, 0.30),
    "gemini-2.0-flash":     (0.10,  0.40),
    "qwen-plus":            (0.40,  1.20),
    "qwen-long":            (0.05,  0.20),
}


def _get_token_price(model: str) -> tuple[float, float]:
    """Return (input_price, output_price) per 1M tokens for the current model."""
    # Allow explicit override via env vars
    try:
        inp = float(os.environ.get("LLM_INPUT_PRICE", ""))
        out = float(os.environ.get("LLM_OUTPUT_PRICE", ""))
        return inp, out
    except (ValueError, TypeError):
        pass
    model_lower = model.lower()
    for key, prices in _TOKEN_PRICES.items():
        if key in model_lower:
            return prices
    return (0.0, 0.0)  # Unknown model — no cost estimate


def _accumulate_usage(response_usage) -> dict[str, int]:
    """Add API response usage to global counters. Returns per-call delta."""
    if response_usage is None:
        return {}
    delta = {
        "prompt_tokens":     getattr(response_usage, "prompt_tokens",     0) or 0,
        "completion_tokens": getattr(response_usage, "completion_tokens", 0) or 0,
        "total_tokens":      getattr(response_usage, "total_tokens",      0) or 0,
    }
    _usage["prompt_tokens"]     += delta["prompt_tokens"]
    _usage["completion_tokens"] += delta["completion_tokens"]
    _usage["total_tokens"]      += delta["total_tokens"]
    _usage["api_calls"]         += 1
    return delta


def get_usage_snapshot() -> dict:
    """Return a copy of the current cumulative usage statistics plus cost estimate."""
    inp_price, out_price = _get_token_price(OMICSCLAW_MODEL)
    cost = (
        _usage["prompt_tokens"]     / 1_000_000 * inp_price +
        _usage["completion_tokens"] / 1_000_000 * out_price
    )
    return {
        **_usage,
        "model": OMICSCLAW_MODEL,
        "provider": LLM_PROVIDER_NAME,
        "input_price_per_1m":  inp_price,
        "output_price_per_1m": out_price,
        "estimated_cost_usd":  round(cost, 6),
    }


def reset_usage() -> None:
    """Reset session-level usage counters to zero."""
    for k in _usage:
        _usage[k] = 0



# ---------------------------------------------------------------------------
# Shared rate limiter used across messaging channels
# ---------------------------------------------------------------------------

RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "10"))
_rate_buckets: dict[str, list[float]] = {}


def check_rate_limit(user_id: str, admin_id: str = "") -> bool:
    """Check per-user rate limit. Returns True if allowed."""
    if RATE_LIMIT_PER_HOUR <= 0 or (admin_id and user_id == admin_id):
        return True
    now = time.time()
    bucket = _rate_buckets.setdefault(user_id, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= RATE_LIMIT_PER_HOUR:
        return False
    bucket.append(now)
    return True


def _evict_lru_conversations():
    """Evict least-recently-used conversations when limit exceeded."""
    transcript_store.max_conversations = MAX_CONVERSATIONS
    evicted = transcript_store.evict_lru_conversations()
    for chat_id in evicted:
        tool_result_store.clear(chat_id)
    if evicted:
        logger.debug(f"Evicted {len(evicted)} stale conversation(s)")


# ---------------------------------------------------------------------------
# Memory Auto-Capture Helpers
# ---------------------------------------------------------------------------

async def _auto_capture_dataset(session_id: str, input_path: str, data_type: str = ""):
    """Auto-capture dataset memory when a file is processed."""
    if not memory_store or not session_id or not input_path:
        return

    try:
        from omicsclaw.memory.compat import DatasetMemory

        # Make path relative to project dir if possible
        try:
            rel_path = str(Path(input_path).relative_to(OMICSCLAW_DIR))
        except ValueError:
            # External path — use basename only to avoid leaking absolute paths
            rel_path = Path(input_path).name

        # Try to detect observation count from h5ad files
        n_obs = None
        n_vars = None
        try:
            suffix = Path(input_path).suffix.lower()
            if suffix in (".h5ad",):
                import h5py
                with h5py.File(input_path, "r") as h5:
                    if "obs" in h5 and hasattr(h5["obs"], "attrs"):
                        shape = h5["obs"].attrs.get("_index", h5["obs"].attrs.get("encoding-type", None))
                    if "X" in h5:
                        x = h5["X"]
                        if hasattr(x, "shape"):
                            n_obs, n_vars = x.shape
        except Exception:
            pass  # Best-effort metadata extraction

        ds_mem = DatasetMemory(
            file_path=rel_path,
            platform=data_type or None,
            n_obs=n_obs,
            n_vars=n_vars,
            preprocessing_state="raw",
        )
        await memory_store.save_memory(session_id, ds_mem)
        logger.debug(f"Auto-captured dataset: {rel_path}")
    except Exception as e:
        logger.warning(f"Auto-capture dataset failed: {e}")


async def _auto_capture_analysis(session_id: str, skill: str, args: dict, output_dir: Path, success: bool):
    """Auto-capture analysis memory after skill execution."""
    if not memory_store or not session_id:
        return

    try:
        from omicsclaw.memory.compat import AnalysisMemory

        # Extract key parameters
        method = args.get("method", "default")
        input_path = args.get("file_path", "")

        # Link to most recent dataset memory for lineage
        source_dataset_id = ""
        try:
            datasets = await memory_store.get_memories(session_id, "dataset", limit=1)
            if datasets:
                source_dataset_id = datasets[0].memory_id
        except Exception:
            pass

        memory = AnalysisMemory(
            source_dataset_id=source_dataset_id if source_dataset_id else "",
            skill=skill,
            method=method,
            parameters={"input": input_path} if input_path else {},
            output_path=str(output_dir) if output_dir else "",
            status="completed" if success else "failed"
        )

        await memory_store.save_memory(session_id, memory)
        logger.debug(f"Auto-captured analysis: {skill} ({method})")
    except Exception as e:
        logger.warning(f"Auto-capture analysis failed: {e}")


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages user sessions with memory persistence."""

    def __init__(self, store):
        self.store = store

    async def get_or_create(self, user_id: str, platform: str, chat_id: str):
        """Get existing session or create new one."""
        session_id = f"{platform}:{user_id}:{chat_id}"
        session = await self.store.get_session(session_id)
        if not session:
            session = await self.store.create_session(user_id, platform, chat_id, session_id=session_id)
        else:
            await self.store.update_session(session_id, {"last_activity": datetime.now(timezone.utc)})
        return session

    async def load_context(self, session_id: str) -> str:
        """Load recent memories and format for LLM context."""
        try:
            # Get recent memories (limit to keep context small)
            # Wrap each get_memories call in try-except to handle decryption errors
            datasets = []
            analyses = []
            prefs = []
            insights = []
            project_ctx = []

            try:
                datasets = await self.store.get_memories(session_id, "dataset", limit=2)
            except Exception as e:
                logger.warning(f"Failed to load dataset memories: {e}")

            try:
                analyses = await self.store.get_memories(session_id, "analysis", limit=3)
            except Exception as e:
                logger.warning(f"Failed to load analysis memories: {e}")

            try:
                prefs = await self.store.get_memories(session_id, "preference", limit=5)
            except Exception as e:
                logger.warning(f"Failed to load preference memories: {e}")

            try:
                insights = await self.store.get_memories(session_id, "insight", limit=3)
            except Exception as e:
                logger.warning(f"Failed to load insight memories: {e}")

            try:
                project_ctx = await self.store.get_memories(session_id, "project_context", limit=1)
            except Exception as e:
                logger.warning(f"Failed to load project context memories: {e}")

            parts = []

            # Project context (top-level)
            if project_ctx:
                pc = project_ctx[0]
                ctx_parts = []
                if pc.project_goal:
                    ctx_parts.append(f"Goal: {pc.project_goal}")
                if pc.species:
                    ctx_parts.append(f"Species: {pc.species}")
                if pc.tissue_type:
                    ctx_parts.append(f"Tissue: {pc.tissue_type}")
                if pc.disease_model:
                    ctx_parts.append(f"Disease: {pc.disease_model}")
                if ctx_parts:
                    parts.append("**Project Context**: " + " | ".join(ctx_parts))

            # Dataset context
            if datasets:
                ds = datasets[0]
                parts.append(f"**Current Dataset**: {ds.file_path} ({ds.platform or 'unknown'}, {ds.n_obs or '?'} obs, {ds.preprocessing_state})")

            # Recent analyses
            if analyses:
                parts.append("**Recent Analyses**:")
                for i, a in enumerate(analyses[:3], 1):
                    parts.append(f"{i}. {a.skill} ({a.method}) - {a.status}")

            # User preferences
            if prefs:
                parts.append("**User Preferences**:")
                for p in prefs:
                    parts.append(f"- {p.key}: {p.value}")

            # Biological insights
            if insights:
                parts.append("**Known Insights**:")
                for ins in insights:
                    confidence = "confirmed" if ins.confidence == "user_confirmed" else "predicted"
                    parts.append(f"- {ins.entity_type} {ins.entity_id}: {ins.biological_label} ({confidence})")

            return "\n".join(parts) if parts else ""
        except Exception as e:
            logger.error(f"Failed to load memory context: {e}", exc_info=True)
            return ""


def init(
    api_key: str = "",
    base_url: str | None = None,
    model: str = "",
    provider: str = "",
):
    """Initialise the shared LLM client. Call once at startup.

    ``provider`` selects a preset (deepseek, gemini, openai, anthropic,
    nvidia, siliconflow, openrouter, volcengine, dashscope, zhipu, ollama,
    custom).  Explicit ``base_url`` / ``model`` override the preset.

    When ``api_key`` is empty, the key is auto-resolved from provider-
    specific environment variables (e.g. DEEPSEEK_API_KEY for deepseek).
    """
    global llm, OMICSCLAW_MODEL, LLM_PROVIDER_NAME, memory_store, session_manager

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider=provider,
        base_url=base_url or "",
        model=model,
        api_key=api_key,
    )
    OMICSCLAW_MODEL = resolved_model

    # Determine display name for the provider
    if provider:
        LLM_PROVIDER_NAME = provider
    elif resolved_url:
        # Try to match resolved_url back to a known provider
        for pname, (purl, _, _) in PROVIDER_PRESETS.items():
            if purl and resolved_url and purl.rstrip("/") in resolved_url.rstrip("/"):
                LLM_PROVIDER_NAME = pname
                break
        else:
            LLM_PROVIDER_NAME = "custom"
    else:
        LLM_PROVIDER_NAME = "openai"

    kw: dict = {"api_key": resolved_key or api_key}
    if resolved_url:
        kw["base_url"] = resolved_url
    llm = AsyncOpenAI(**kw)

    logger.info(
        f"LLM initialised: provider={LLM_PROVIDER_NAME}, "
        f"model={OMICSCLAW_MODEL}, base_url={resolved_url or '(default)'}"
    )

    # Memory initialization — uses the new graph-based memory system
    # Enabled by default; disable with OMICSCLAW_MEMORY_ENABLED=false
    if os.getenv("OMICSCLAW_MEMORY_ENABLED", "true").lower() not in ("false", "0", "no"):
        try:
            from omicsclaw.memory.compat import CompatMemoryStore

            db_url = os.getenv("OMICSCLAW_MEMORY_DB_URL")  # None = use default (~/.config/omicsclaw/memory.db)

            store = CompatMemoryStore(
                database_url=db_url,
            )
            # NOTE: initialize() is called lazily on first async operation
            # from MemoryClient._ensure_init(), since init() runs in sync context.

            memory_store = store
            session_manager = SessionManager(store)
            logger.info("Graph memory system initialized (omicsclaw.memory)")
        except ImportError:
            logger.warning("Memory dependencies not installed, skipping memory init")
        except Exception as e:
            logger.error(f"Memory init failed: {e}")


SYSTEM_PROMPT: str = ""

def _ensure_system_prompt():
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = build_system_prompt(omicsclaw_dir=str(OMICSCLAW_DIR))

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

def get_tools() -> list[dict]:
    return get_tool_registry().to_openai_tools()


def _build_bot_tool_context() -> BotToolContext:
    skill_names = tuple(list(registry.skills.keys()) + ["auto"])
    skill_descriptions = [
        f"{alias} ({info.get('description', alias)})"
        for alias, info in _iter_primary_skill_entries()
    ]
    return BotToolContext(
        skill_names=skill_names,
        skill_desc_text=", ".join(skill_descriptions),
    )


def get_tool_registry():
    return build_bot_tool_registry(_build_bot_tool_context())

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def sanitize_filename(filename: str) -> str:
    filename = Path(filename).name
    filename = re.sub(r"[\x00-\x1f]", "", filename)
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")
    return filename or "unnamed_file"


def resolve_dest(folder: str | None, default: Path | None = None) -> Path:
    fallback = default if default is not None else DATA_DIR
    dest = Path(folder) if folder else fallback
    if not dest.is_absolute():
        dest = OMICSCLAW_DIR / dest
    try:
        dest.resolve().relative_to(OMICSCLAW_DIR.resolve())
    except ValueError:
        logger.warning(f"Path escape blocked: {dest}")
        audit("security", severity="HIGH", detail="path_escape_blocked", attempted_path=str(dest))
        dest = fallback
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def validate_path(filepath: Path, allowed_root: Path) -> bool:
    try:
        filepath.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Trusted data directories + file discovery
# ---------------------------------------------------------------------------

def _build_trusted_dirs() -> list[Path]:
    """Build the list of directories where data files may be read from."""
    dirs = [DATA_DIR, EXAMPLES_DIR, OUTPUT_DIR]
    extra = os.environ.get("OMICSCLAW_DATA_DIRS", os.environ.get("SPATIALCLAW_DATA_DIRS", ""))
    if extra:
        for d in extra.split(","):
            d = d.strip()
            if d:
                p = Path(d)
                if p.is_absolute() and p.is_dir():
                    dirs.append(p)
                else:
                    logger.warning(f"OMICSCLAW_DATA_DIRS: ignoring '{d}' (not an absolute directory)")
    return dirs


TRUSTED_DATA_DIRS: list[Path] = []


def _ensure_trusted_dirs():
    global TRUSTED_DATA_DIRS
    if not TRUSTED_DATA_DIRS:
        TRUSTED_DATA_DIRS = _build_trusted_dirs()
        logger.info(f"Trusted data dirs: {[str(d) for d in TRUSTED_DATA_DIRS]}")


def validate_input_path(filepath: str) -> Path | None:
    """Validate that a user-supplied file path points to a real file in a trusted directory.

    Returns resolved Path if valid, None otherwise.
    """
    _ensure_trusted_dirs()
    p = Path(filepath).expanduser()
    if not p.is_absolute():
        # 1. Try relative to project root first (most common case)
        candidate = OMICSCLAW_DIR / p
        if candidate.exists() and candidate.is_file():
            p = candidate
        else:
            # 2. Try each trusted data directory
            for d in TRUSTED_DATA_DIRS:
                candidate = d / p
                if candidate.exists() and candidate.is_file():
                    p = candidate
                    break
            else:
                # 3. Fall back to DATA_DIR
                p = DATA_DIR / p

    resolved = p.resolve()
    if not resolved.exists() or not resolved.is_file():
        return None

    for trusted in TRUSTED_DATA_DIRS:
        try:
            resolved.relative_to(trusted.resolve())
            return resolved
        except ValueError:
            continue

    # Also allow files anywhere under project root
    try:
        resolved.relative_to(OMICSCLAW_DIR.resolve())
        return resolved
    except ValueError:
        pass

    logger.warning(f"Path not in trusted dirs: {resolved}")
    audit("security", severity="MEDIUM", detail="untrusted_path_rejected", path=str(resolved))
    return None


def discover_file(filename_or_pattern: str) -> list[Path]:
    """Search trusted data directories for files matching the given name or glob pattern.

    Returns a list of matching paths, sorted by modification time (newest first).
    """
    _ensure_trusted_dirs()

    # Handle absolute paths directly
    if filename_or_pattern.startswith('/'):
        p = Path(filename_or_pattern)
        if p.is_file():
            return [p]
        return []

    matches: list[Path] = []
    for d in TRUSTED_DATA_DIRS:
        if not d.exists():
            continue
        if "*" in filename_or_pattern or "?" in filename_or_pattern:
            matches.extend(f for f in d.rglob(filename_or_pattern) if f.is_file())
        else:
            exact = d / filename_or_pattern
            if exact.is_file():
                matches.append(exact)
            for f in d.rglob(filename_or_pattern):
                if f.is_file() and f not in matches:
                    matches.append(f)
    matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return matches


# ---------------------------------------------------------------------------
# execute_omicsclaw
# ---------------------------------------------------------------------------


# Deep learning methods that may take a long time
DEEP_LEARNING_METHODS = {
    "cell2location", "destvi", "stereoscope", "tangram",
    "spagcn", "stagate", "graphst", "scvi", "velovi",
    "scanvi", "cellassign",
}

def _lookup_skill_info(skill_key: str, force_reload: bool = False) -> dict:
    from omicsclaw.core.registry import registry

    if force_reload:
        registry._loaded = False
        registry.skills.clear()
        registry.lazy_skills.clear()
    registry.load_all()

    info = registry.skills.get(skill_key)
    if info:
        return info

    # Fallback: find by canonical alias stored in metadata.
    for _k, meta in registry.skills.items():
        if meta.get("alias") == skill_key:
            return meta
    return {}


def _resolve_param_hint_info(skill_key: str, method: str) -> tuple[str, dict, dict]:
    """Return (method_lower, tip_info, skill_info) from SKILL.md param_hints."""
    method_lower = (method or "").lower().strip()
    if not method_lower:
        return "", {}, {}

    try:
        skill_info = _lookup_skill_info(skill_key, force_reload=False)
        hints = skill_info.get("param_hints", {}) if skill_info else {}
        tip_info = hints.get(method_lower)

        # If no hints found, force-refresh registry once. This picks up edits
        # to SKILL.md made during a long-lived `oc chat` session.
        if not tip_info:
            skill_info = _lookup_skill_info(skill_key, force_reload=True)
            hints = skill_info.get("param_hints", {}) if skill_info else {}
            tip_info = hints.get(method_lower)

        logger.info(
            "param_hint lookup: skill_key=%s, method=%s, skill_found=%s, hints_keys=%s",
            skill_key,
            method_lower,
            bool(skill_info),
            list(hints.keys()) if hints else "EMPTY",
        )
        return method_lower, (tip_info or {}), (skill_info or {})
    except Exception as e:
        logger.warning("param_hint loading failed: %s", e)
        return method_lower, {}, {}


def _infer_skill_for_method(method: str, preferred_domain: str = "") -> str:
    """Infer a skill alias from method name using registry param_hints."""
    method_lower = (method or "").strip().lower()
    if not method_lower:
        return ""
    try:
        from omicsclaw.core.registry import registry
        registry.load_all()

        candidates: list[str] = []
        for alias, info in registry.skills.items():
            # Only keep canonical aliases (skip legacy alias duplicates).
            if alias != info.get("alias", alias):
                continue
            if preferred_domain and info.get("domain", "") != preferred_domain:
                continue
            hints = info.get("param_hints", {}) or {}
            if method_lower in hints:
                candidates.append(alias)

        if len(candidates) == 1:
            return candidates[0]
        return sorted(candidates)[0] if candidates else ""
    except Exception:
        return ""


def _build_method_preview(
    *,
    skill_key: str,
    method: str,
    n_obs: int | None,
    has_spatial: bool,
    has_x_pca: bool,
    has_raw: bool,
    has_counts_layer: bool,
    platform: str,
) -> str:
    """Build pre-run suitability + default parameter preview for inspect_data."""
    method_lower, tip_info, skill_info = _resolve_param_hint_info(skill_key, method)
    if not method_lower or not tip_info:
        return ""

    checks: list[str] = []
    seen_checks: set[str] = set()

    def _add_check(line: str) -> None:
        if line not in seen_checks:
            checks.append(line)
            seen_checks.add(line)

    suitable = True

    requires = tip_info.get("requires", []) if isinstance(tip_info, dict) else []
    requires_tokens = {str(r).strip().lower() for r in requires}

    # Generic base checks by detected platform (avoid duplicate if explicitly
    # declared in method-level `requires`).
    if "spatial" in platform.lower() and "obsm.spatial" not in requires_tokens:
        if has_spatial:
            _add_check("- `obsm['spatial']`: found ✅")
        else:
            _add_check("- `obsm['spatial']`: missing ❌ (spatial methods usually require this)")
            suitable = False

    # Optional declarative requirements from SKILL.md:
    # metadata.omicsclaw.param_hints.<method>.requires
    # Supported tokens: obsm.spatial, obsm.X_pca, raw, layers.counts, raw_or_counts
    for req in requires:
        req_token = str(req).strip().lower()
        if req_token == "obsm.spatial":
            ok = has_spatial
            text = "`obsm['spatial']`"
        elif req_token == "obsm.x_pca":
            ok = has_x_pca
            text = "`obsm['X_pca']`"
        elif req_token == "raw":
            ok = has_raw
            text = "`adata.raw`"
        elif req_token == "layers.counts":
            ok = has_counts_layer
            text = "`layers['counts']`"
        elif req_token == "raw_or_counts":
            ok = has_raw or has_counts_layer
            text = "`adata.raw` or `layers['counts']`"
        else:
            _add_check(f"- Requirement `{req}`: please verify manually")
            continue

        if ok:
            _add_check(f"- Requirement {text}: found ✅")
        else:
            _add_check(f"- Requirement {text}: missing ⚠️")
            suitable = False

    if has_x_pca:
        _add_check("- `obsm['X_pca']`: found ✅")
    if isinstance(n_obs, int):
        size_note = f"{n_obs:,} cells/spots"
        if n_obs > 30000 and "epochs" in (tip_info.get("params", []) or []):
            size_note += " (large; start with fewer epochs)"
        _add_check(f"- Dataset size: {size_note}")

    defaults = tip_info.get("defaults", {}) if isinstance(tip_info, dict) else {}
    param_lines = []
    recommended_args = [f"--method {method_lower}"]
    for p in tip_info.get("params", []):
        default_val = defaults.get(p, "default")
        if (
            p == "epochs"
            and isinstance(n_obs, int)
            and n_obs > 30000
        ):
            default_text = f"{default_val} (for large data, try 50-100 first)"
            recommended_val = 50
        else:
            default_text = str(default_val)
            recommended_val = default_val
        param_lines.append(f"- `{p}`: {default_text}")

        if recommended_val != "default":
            cli_flag = f"--{p.replace('_', '-')}"
            recommended_args.append(f"{cli_flag} {recommended_val}")

    suitability_text = "✅ Suitable for a first run" if suitable else "❌ Not suitable yet"
    canonical_alias = skill_info.get("alias", skill_key) if skill_info else skill_key

    lines = [
        "### Method Suitability & Parameter Preview",
        f"- Requested skill: `{canonical_alias}`",
        f"- Requested method: `{method_lower}`",
        f"- Suitability: {suitability_text}",
    ]
    if checks:
        lines.append("- Checks:")
        lines.extend([f"  {c}" for c in checks])
    if param_lines:
        lines.append("- Default parameter preview:")
        lines.extend([f"  {p}" for p in param_lines])
    lines.append(f"- Tuning priority: {tip_info.get('priority', 'N/A')}")
    lines.append(f"- Suggested first run: `{ ' '.join(recommended_args) }`")
    return "\n".join(lines)


def _build_param_hint(skill_key: str, method: str, cmd: list[str]) -> str:
    """Build a parameter summary block from SKILL.md-declared param_hints.

    Reads ``param_hints`` from the registry (loaded from each skill's SKILL.md
    YAML frontmatter). Returns a markdown-formatted string to prepend to the
    tool result. Returns empty string if the skill has no hints for *method*.

    Adding hints for a new skill or method requires only editing its SKILL.md —
    no changes to bot/core.py are needed.
    """
    method_lower, tip_info, skill_info = _resolve_param_hint_info(skill_key, method)
    if not tip_info:
        hints = skill_info.get("param_hints", {}) if skill_info else {}
        logger.info("param_hint: no hints for method '%s' in %s", method_lower, list(hints.keys()))
        return ""

    # Extract CLI arg values from the built command
    params_found = {}
    for i, arg in enumerate(cmd):
        if arg.startswith("--") and i + 1 < len(cmd) and not cmd[i + 1].startswith("--"):
            params_found[arg.lstrip("-").replace("-", "_")] = cmd[i + 1]

    # Build the hint block
    lines = [
        f"📋 **Running {skill_key} with method={method_lower}**",
        "",
        "**Current Parameters:**",
    ]
    for key in tip_info.get("params", []):
        lines.append(f"  - `{key}`: {params_found.get(key, 'default')}")

    lines.append("")
    lines.append(f"**Tuning Priority:** {tip_info.get('priority', 'N/A')}")
    for t in tip_info.get("tips", []):
        lines.append(f"  - {t}")
    lines.append("")
    return "\n".join(lines)


async def execute_omicsclaw(args: dict, session_id: str = None, chat_id: int | str = 0) -> str:
    """Execute an OmicsClaw skill via subprocess (waits until completion)."""
    skill_key = args.get("skill", "auto")
    mode = args.get("mode", "demo")
    query = args.get("query", "")
    method = args.get("method", "")
    data_type = args.get("data_type", "")
    file_path_arg = args.get("file_path", "")

    # --- Resolve input file for path mode ---
    resolved_path: Path | None = None
    if mode == "path" or file_path_arg:
        mode = "path"
        if file_path_arg:
            resolved_path = validate_input_path(file_path_arg)
            if resolved_path is None:
                found = discover_file(file_path_arg)
                if found:
                    resolved_path = found[0]
                    if len(found) > 1:
                        listing = "\n".join(f"  - {f}" for f in found[:8])
                        return (
                            f"Multiple files match '{file_path_arg}':\n{listing}\n\n"
                            "Please specify the full path."
                        )
                else:
                    _ensure_trusted_dirs()
                    dirs_str = ", ".join(str(d) for d in TRUSTED_DATA_DIRS)
                    return (
                        f"File not found: '{file_path_arg}'\n\n"
                        f"Place your data files in one of these directories:\n{dirs_str}\n\n"
                        "Then tell me the filename and I'll find it automatically."
                    )
            logger.info(f"Resolved input path: {resolved_path}")
            audit("file_resolve", file_path=str(resolved_path), original=file_path_arg)

    # --- Auto-routing via capability resolver ---
    if skill_key == "auto":
        from omicsclaw.core.capability_resolver import resolve_capability

        capability_input = query
        if resolved_path:
            capability_input = str(resolved_path)
        elif mode == "file":
            for _cid, info in received_files.items():
                capability_input = info["path"]
                break

        if not capability_input:
            return "Error: skill='auto' requires either a file, a file_path, or a query to route."

        try:
            decision = resolve_capability(
                query or capability_input,
                file_path=str(resolved_path or capability_input or ""),
            )
            if decision.chosen_skill:
                if getattr(decision, "should_create_skill", False):
                    return (
                        "This request is asking to add a reusable OmicsClaw skill.\n\n"
                        "Use create_omics_skill instead of auto-running an analysis skill."
                    )
                skill_key = decision.chosen_skill
                logger.info(
                    "Auto-routed via capability resolver to: %s (%s, %.2f)",
                    skill_key,
                    decision.coverage,
                    decision.confidence,
                )
            else:
                missing = "; ".join(decision.missing_capabilities) or "no matching skill"
                return (
                    "No existing OmicsClaw skill fully matches this request.\n"
                    f"Coverage: {decision.coverage}\n"
                    f"Reason: {missing}\n\n"
                    "If the user wants a reusable repository skill, use create_omics_skill. "
                    "Otherwise use web_method_search and custom_analysis_execute for controlled fallback."
                )
        except Exception as e:
            return f"Error resolving skill automatically: {e}"

    # --- Resolve input for file/path mode ---
    input_path = str(resolved_path) if resolved_path else None
    session_path = None

    if not input_path and session_id:
        file_info = received_files.get(session_id)
        if file_info:
            input_path = file_info.get("path")
            session_path = file_info.get("session_path")

    if mode in ("file", "path") and not input_path and not session_path:
        _ensure_trusted_dirs()
        dirs_str = ", ".join(str(d) for d in TRUSTED_DATA_DIRS)
        return (
            "No input file available. You can either:\n"
            "1. Upload a file via messaging (if small enough)\n"
            f"2. Place your file in a data directory ({dirs_str}) "
            "and tell me the filename\n"
            "3. Provide the full server path to the file"
        )

    # Output directory
    import uuid
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / build_output_dir_name(
        skill_key,
        ts,
        method=method,
        unique_suffix=uuid.uuid4().hex[:8],
    )

    # Build command
    cmd = [PYTHON, str(OMICSCLAW_PY), "run"]
    if skill_key == "pipeline":
        cmd.append("spatial-pipeline")
    else:
        cmd.append(skill_key)

    if mode == "demo":
        cmd.append("--demo")
    elif input_path:
        cmd.extend(["--input", str(input_path)])

    cmd.extend(["--output", str(out_dir)])

    if method:
        cmd.extend(["--method", method])
    if data_type:
        cmd.extend(["--data-type", data_type])

    # Pass n_epochs if user specified
    n_epochs = args.get("n_epochs")
    if n_epochs is not None:
        cmd.extend(["--n-epochs", str(int(n_epochs))])

    extra_args = args.get("extra_args")
    if extra_args and isinstance(extra_args, list):
        # Filter out --output to prevent overriding bot-managed output directory
        # Also normalise underscores to hyphens in flag names (LLM often
        # generates --leiden_resolution instead of --leiden-resolution)
        filtered = []
        skip_next = False
        for arg in extra_args:
            if skip_next:
                skip_next = False
                continue
            if arg == "--output":
                skip_next = True
                continue
            if arg.startswith("--output="):
                continue
            # Normalise: --leiden_resolution -> --leiden-resolution
            if arg.startswith("--"):
                eq_pos = arg.find("=")
                if eq_pos > 0:
                    flag_part = arg[:eq_pos].replace("_", "-")
                    arg = flag_part + arg[eq_pos:]
                else:
                    arg = arg.replace("_", "-")
            filtered.append(arg)
        cmd.extend(filtered)

    # Build a parameter hint block so the LLM can relay it to the user
    param_hint = _build_param_hint(skill_key, method, cmd)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Log start for deep learning methods
        is_dl = method.lower() in DEEP_LEARNING_METHODS
        if is_dl:
            logger.info(f"Starting {skill_key} with {method} (no timeout, may take 10-60 minutes)")

        # Wait until completion — no timeout
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout_str = stdout_bytes.decode(errors="replace")
        stderr_str = stderr_bytes.decode(errors="replace")
    except Exception as e:
        import traceback as _tb
        # Clean up empty output directory on crash
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        return f"{skill_key} crashed:\n{_tb.format_exc()[-1500:]}"

    if proc.returncode != 0:
        err = stderr_str[-1500:] if stderr_str else stdout_str[-1500:] if stdout_str else "unknown error"
        # Clean up empty output directory on failure
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        # Capture failed analysis to memory (so we remember what was tried)
        if session_id:
            await _auto_capture_analysis(session_id, skill_key, args, None, False)
        return f"{skill_key} failed (exit {proc.returncode}):\n{err}"

    # Collect report + figures from output directory
    return_media = str(args.get("return_media", "")).strip().lower()
    figure_names = []
    table_names = []
    notebook_names = []
    sent_names = []
    if out_dir.exists():
        media_items = []
        for f in sorted(out_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix in (".md", ".html"):
                media_items.append({"type": "document", "path": str(f)})
            elif f.suffix == ".ipynb":
                media_items.append({"type": "document", "path": str(f)})
                notebook_names.append(f.name)
            elif f.suffix == ".png":
                media_items.append({"type": "photo", "path": str(f)})
                figure_names.append(f.name)
            elif f.suffix == ".csv":
                media_items.append({"type": "document", "path": str(f)})
                table_names.append(f.name)

        if return_media and media_items:
            if return_media == "all":
                filtered = media_items
            else:
                keywords = [k.strip() for k in return_media.split(",") if k.strip()]
                filtered = [
                    item for item in media_items
                    if any(kw in Path(item["path"]).stem.lower() for kw in keywords)
                ]
            if filtered:
                pending_media[session_id] = pending_media.get(session_id, []) + filtered
                sent_names = [Path(item["path"]).name for item in filtered]
                logger.info(f"return_media='{return_media}': sending {len(filtered)}/{len(media_items)} items")

    # Read report for chat display
    report_text = ""
    if out_dir.exists():
        for pattern in ["report.md", "*_report.md", "*.md"]:
            for md_file in sorted(out_dir.glob(pattern)):
                if md_file.name.startswith("."):
                    continue
                report_text = md_file.read_text(encoding="utf-8")
                break
            if report_text:
                break

    if not report_text:
        return stdout_str if stdout_str else f"{skill_key} completed. Output: {out_dir}"

    # Trim verbose sections for chat readability; full report is on disk.
    keep_lines = []
    skip = False
    for line in report_text.split("\n"):
        if line.startswith("## Methods") or line.startswith("## Reproducibility"):
            skip = True
        elif line.startswith("## Disclaimer"):
            skip = False
        if line.startswith("!["):
            continue
        if not skip:
            keep_lines.append(line)

    # Auto-capture dataset + analysis memory
    if session_id:
        if input_path:
            await _auto_capture_dataset(session_id, input_path, data_type)
        await _auto_capture_analysis(session_id, skill_key, args, out_dir, True)

    result_text = "\n".join(keep_lines).strip()
    notebook_path = out_dir / "reproducibility" / "analysis_notebook.ipynb"
    if notebook_path.exists():
        result_text += (
            "\n\n---\n"
            f"[Reproducibility notebook available: {notebook_path}. "
            "Tell the user they can open it in Jupyter to inspect code, outputs, and rerun the analysis.]"
        )

    # Prepend parameter hint so the LLM relays it to the user
    if param_hint:
        result_text = param_hint + "\n---\n" + result_text

    # Append media delivery status so the LLM knows what happened
    # and does NOT attempt to browse output directories itself.
    all_names = figure_names + table_names + notebook_names
    if sent_names:
        result_text += (
            "\n\n---\n"
            f"[MEDIA DELIVERY: {len(sent_names)} file(s) already queued for the user: "
            f"{', '.join(sent_names)}. DO NOT use list_directory or other tools to find/send "
            "these files — they will be delivered automatically.]"
        )
        unsent = [n for n in all_names if n not in sent_names]
        if unsent:
            result_text += (
                f"\n[Other available outputs not requested: {', '.join(unsent)}.]"
            )
    elif not return_media and all_names:
        hints = []
        if figure_names:
            hints.append(f"Figures: {', '.join(figure_names)}")
        if table_names:
            hints.append(f"Tables: {', '.join(table_names)}")
        if notebook_names:
            hints.append(f"Notebooks: {', '.join(notebook_names)}")
        result_text += (
            "\n\n---\n"
            f"[Available outputs: {'; '.join(hints)}. "
            "Tell the user they can request specific figures, tables, or notebooks by name if interested.]"
        )

    # Stage 2+4: Emit AdvisoryEvent and resolve post-execution knowledge
    try:
        from omicsclaw.knowledge.resolver import AdvisoryEvent, get_resolver

        # Determine domain from skill registry
        _skill_domain = "general"
        try:
            from omicsclaw.core.registry import registry
            skill_info = registry.skills.get(skill_key, {})
            _skill_domain = skill_info.get("domain", "general")
        except Exception:
            pass

        event = AdvisoryEvent(
            skill=skill_key,
            phase="post_run",
            domain=_skill_domain,
            toolchain=method or "",
            signals=[method, data_type] if method else [],
            severity="info",
            metrics={},
            message=f"Completed {skill_key}" + (f" with method={method}" if method else ""),
        )
        resolver = get_resolver()
        advice = resolver.resolve(
            event,
            session_id=session_id or str(chat_id),
        )
        if advice:
            advice_text = resolver.format_advice(advice, channel="bot")
            if advice_text:
                result_text += f"\n\n{advice_text}"
                logger.info("Post-execution advice appended for %s (%d snippets)",
                            skill_key, len(advice))
    except Exception as e:
        logger.debug("Post-execution advisory skipped: %s", e)

    return result_text


# ---------------------------------------------------------------------------
# execute_save_file
# ---------------------------------------------------------------------------


async def execute_save_file(args: dict) -> str:
    file_info = None
    for _cid, info in received_files.items():
        file_info = info
        break

    if not file_info:
        return "No recently received file to save. Send a file first."

    src_path = Path(file_info["path"])
    if not src_path.exists():
        return "The temporary file has expired. Please send it again."

    dest_path = resolve_dest(args.get("destination_folder"))
    filename = sanitize_filename(args.get("filename") or file_info["filename"])
    final_path = dest_path / filename

    if not validate_path(final_path, dest_path):
        return f"Error: filename '{filename}' would escape the destination directory."

    shutil.copy2(str(src_path), str(final_path))
    logger.info(f"Saved file: {final_path}")
    try:
        src_path.unlink()
    except OSError:
        pass
    return f"File saved to {final_path}"


# ---------------------------------------------------------------------------
# execute_write_file
# ---------------------------------------------------------------------------


async def execute_write_file(args: dict) -> str:
    content = args.get("content")
    filename = args.get("filename")
    if not content:
        return "Error: 'content' is required."
    if not filename:
        return "Error: 'filename' is required."

    dest = resolve_dest(args.get("destination_folder"), default=OUTPUT_DIR)
    filename = sanitize_filename(filename)
    filepath = dest / filename

    if not validate_path(filepath, dest):
        return f"Error: filename '{filename}' would escape the destination directory."

    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Wrote file: {filepath} ({len(content)} chars)")
    return f"File written to {filepath} ({len(content)} chars)"


# ---------------------------------------------------------------------------
# execute_generate_audio
# ---------------------------------------------------------------------------


async def execute_generate_audio(args: dict) -> str:
    text = args.get("text")
    filename = args.get("filename")
    if not text:
        return "Error: 'text' is required."
    if not filename:
        return "Error: 'filename' is required."
    if not filename.endswith(".mp3"):
        filename += ".mp3"

    filename = sanitize_filename(filename)
    voice = args.get("voice", "en-GB-RyanNeural")
    rate = args.get("rate", "-5%")
    dest = resolve_dest(args.get("destination_folder"))
    filepath = dest / filename

    if not validate_path(filepath, dest):
        return f"Error: filename '{filename}' would escape the destination directory."

    text_path = dest / f".tmp_{filename}.txt"
    text_path.write_text(text, encoding="utf-8")

    try:
        proc = await asyncio.create_subprocess_exec(
            "edge-tts",
            "--voice", voice,
            f"--rate={rate}",
            "--file", str(text_path),
            "--write-media", str(filepath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        try:
            text_path.unlink()
        except OSError:
            pass

        if proc.returncode != 0:
            err = stderr.decode()[-300:] if stderr else "unknown error"
            return f"Audio generation failed (exit {proc.returncode}): {err}"

        size_mb = filepath.stat().st_size / (1024 * 1024)
        word_count = len(text.split())
        est_minutes = word_count / 150
        logger.info(f"Generated audio: {filepath} ({size_mb:.1f} MB)")
        return f"Audio saved to {filepath} ({size_mb:.1f} MB, ~{word_count} words, ~{est_minutes:.0f} min)"

    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        try:
            text_path.unlink()
        except OSError:
            pass
        return "Audio generation timed out after 5 minutes."
    except FileNotFoundError:
        try:
            text_path.unlink()
        except OSError:
            pass
        return "edge-tts not found. Install with: pip install edge-tts"


# ---------------------------------------------------------------------------
# execute_parse_literature
# ---------------------------------------------------------------------------


async def execute_parse_literature(args: dict) -> str:
    """Execute literature parsing skill."""
    input_value = args.get("input_value", "")
    input_type = args.get("input_type", "auto")
    auto_download = args.get("auto_download", True)

    # Check for uploaded PDF files
    if not input_value:
        for _cid, info in received_files.items():
            file_path = info.get("path", "")
            if file_path and Path(file_path).suffix.lower() == ".pdf":
                input_value = file_path
                input_type = "file"
                logger.info(f"Detected uploaded PDF: {file_path}")
                break

    if not input_value:
        return "Error: input_value is required."

    # Output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / f"literature-parse_{ts}"

    # Build command
    lit_script = OMICSCLAW_DIR / "skills" / "literature" / "literature_parse.py"
    if not lit_script.exists():
        return "Error: literature parsing skill not found."

    cmd = [PYTHON, str(lit_script)]
    cmd.extend(["--input", input_value])
    cmd.extend(["--input-type", input_type])
    cmd.extend(["--output", str(out_dir)])
    cmd.extend(["--data-dir", str(DATA_DIR)])

    if not auto_download:
        cmd.append("--no-download")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=180,
        )
        stdout_str = stdout_bytes.decode(errors="replace")
        stderr_str = stderr_bytes.decode(errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return "Literature parsing timed out after 180 seconds."
    except Exception as e:
        import traceback as _tb
        return f"Literature parsing crashed:\n{_tb.format_exc()[-1500:]}"

    if proc.returncode != 0:
        err = stderr_str[-1500:] if stderr_str else stdout_str[-1500:] if stdout_str else "unknown error"
        return f"Literature parsing failed (exit {proc.returncode}):\n{err}"

    # Read report
    report_file = out_dir / "report.md"
    if report_file.exists():
        return report_file.read_text(encoding="utf-8")
    else:
        return stdout_str if stdout_str else "Literature parsing completed but no report generated."


# ---------------------------------------------------------------------------
# execute_fetch_geo_metadata
# ---------------------------------------------------------------------------


async def execute_fetch_geo_metadata(args: dict) -> str:
    """Fetch GEO metadata for a specific accession."""
    accession = args.get("accession", "").strip().upper()
    download = args.get("download", False)

    if not accession:
        return "Error: accession is required."

    # Import downloader functions
    sys.path.insert(0, str(OMICSCLAW_DIR / "skills" / "literature"))
    try:
        from core.downloader import fetch_geo_metadata, download_geo_dataset
    except ImportError as e:
        return f"Error importing GEO tools: {e}"

    # Fetch metadata
    try:
        metadata = fetch_geo_metadata(accession)
        if not metadata:
            return f"Failed to fetch metadata for {accession}. Please check the accession ID."

        # Format response
        lines = [
            f"# GEO Metadata: {accession}",
            f"\n**Title**: {metadata.get('title', 'N/A')}",
            f"\n**Organism**: {metadata.get('organism', 'N/A')}",
            f"\n**Platform**: {metadata.get('platform', 'N/A')}",
        ]

        summary = metadata.get('summary', '')
        if summary:
            lines.append(f"\n**Summary**: {summary[:300]}{'...' if len(summary) > 300 else ''}")

        samples = metadata.get('samples', [])
        if samples:
            lines.append(f"\n**Samples**: {len(samples)} samples")
            lines.append(f"- {', '.join(samples[:5])}")
            if len(samples) > 5:
                lines.append(f"- ... and {len(samples) - 5} more")

        # Download if requested
        if download and accession.startswith('GSE'):
            lines.append(f"\n## Downloading {accession}...")
            result = download_geo_dataset(accession, DATA_DIR)
            if result['status'] == 'success':
                lines.append(f"\n✓ Downloaded {len(result['files'])} files to data/{accession}/")
            else:
                lines.append(f"\n✗ Download failed: {', '.join(result.get('errors', ['Unknown error']))}")

        return '\n'.join(lines)

    except Exception as e:
        return f"Error fetching GEO metadata: {e}"


# ---------------------------------------------------------------------------
# execute_list_directory
# ---------------------------------------------------------------------------


async def execute_list_directory(args: dict) -> str:
    """List directory contents (restricted to trusted directories)."""
    path_arg = args.get("path", "")
    target_path = Path(path_arg) if path_arg else DATA_DIR

    if not target_path.is_absolute():
        target_path = DATA_DIR / target_path

    # Validate against trusted directories
    _ensure_trusted_dirs()
    resolved = target_path.resolve()
    if not any(
        resolved == td.resolve() or str(resolved).startswith(str(td.resolve()) + os.sep)
        for td in TRUSTED_DATA_DIRS
    ):
        dirs_str = ", ".join(str(d) for d in TRUSTED_DATA_DIRS)
        return f"Access denied: {target_path} is not in trusted directories ({dirs_str})"

    if not target_path.exists():
        return f"Directory not found: {target_path}"

    if not target_path.is_dir():
        return f"Not a directory: {target_path}"

    try:
        items = []
        for item in sorted(target_path.iterdir()):
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size / (1024 * 1024)
                items.append(f"📄 {item.name} ({size:.2f} MB)")

        if not items:
            return f"Empty directory: {target_path}"

        return f"Contents of {target_path}:\n" + "\n".join(items[:50])
    except Exception as e:
        return f"Error listing directory: {e}"


# ---------------------------------------------------------------------------
# execute_inspect_file
# ---------------------------------------------------------------------------


async def execute_inspect_file(args: dict) -> str:
    """Inspect file contents."""
    file_path_arg = args.get("file_path", "")
    lines_limit = args.get("lines", 20)

    if not file_path_arg:
        return "Error: file_path is required."

    file_path = validate_input_path(file_path_arg)
    if not file_path:
        return f"File not found or not accessible: {file_path_arg}"

    try:
        suffix = file_path.suffix.lower()
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        preview = "\n".join(lines[:lines_limit])
        total = len(lines)

        return f"File: {file_path.name}\nShowing {min(lines_limit, total)} of {total} lines:\n\n{preview}"
    except Exception as e:
        return f"Error reading file: {e}"


# ---------------------------------------------------------------------------
# execute_inspect_data
# ---------------------------------------------------------------------------


async def execute_inspect_data(args: dict) -> str:
    """Inspect an h5ad AnnData file's metadata without loading the expression matrix."""
    file_path_arg = args.get("file_path", "")
    skill_arg = str(args.get("skill", "")).strip()
    method_arg = str(args.get("method", "")).strip().lower()
    preview_params = bool(args.get("preview_params", False) or method_arg)
    if not file_path_arg:
        return "Error: file_path is required."

    file_path = validate_input_path(file_path_arg)
    if not file_path:
        return f"File not found or not accessible: {file_path_arg}"

    if file_path.suffix.lower() != ".h5ad":
        return f"inspect_data only supports .h5ad files. Got: {file_path.suffix}"

    try:
        import h5py

        info: dict = {}

        with h5py.File(file_path, "r") as f:
            # n_obs / n_vars from index arrays (faster than loading X)
            if "obs" in f and "_index" in f["obs"]:
                info["n_obs"] = len(f["obs"]["_index"])
            elif "X" in f:
                info["n_obs"] = f["X"].shape[0]

            if "var" in f and "_index" in f["var"]:
                info["n_vars"] = len(f["var"]["_index"])
            elif "X" in f:
                info["n_vars"] = f["X"].shape[1]

            # obs/var column names (drop internal HDF5 keys)
            _skip = {"_index", "__categories"}
            info["obs_columns"] = [k for k in f["obs"].keys() if k not in _skip] if "obs" in f else []
            info["var_columns"] = [k for k in f["var"].keys() if k not in _skip] if "var" in f else []

            info["obsm_keys"] = list(f["obsm"].keys()) if "obsm" in f else []
            info["obsp_keys"] = list(f["obsp"].keys()) if "obsp" in f else []
            info["layers"] = list(f["layers"].keys()) if "layers" in f else []
            info["uns_keys"] = list(f["uns"].keys()) if "uns" in f else []
            info["has_raw"] = "raw" in f

    except ImportError:
        # Fallback: use anndata backed mode (no full matrix loaded)
        try:
            import anndata as ad
            adata = ad.read_h5ad(file_path, backed="r")
            info = {
                "n_obs": adata.n_obs,
                "n_vars": adata.n_vars,
                "obs_columns": list(adata.obs.columns),
                "var_columns": list(adata.var.columns),
                "obsm_keys": list(adata.obsm.keys()),
                "obsp_keys": list(adata.obsp.keys()),
                "layers": list(adata.layers.keys()),
                "uns_keys": list(adata.uns.keys()),
                "has_raw": adata.raw is not None,
            }
            adata.file.close()
        except Exception as e2:
            return f"Error inspecting {file_path.name}: {e2}"
    except Exception as e:
        return f"Error inspecting {file_path.name}: {e}"

    # Platform detection (heuristic, no model execution)
    obsm_keys_lower = [k.lower() for k in info.get("obsm_keys", [])]
    obs_cols_lower = [c.lower() for c in info.get("obs_columns", [])]

    if "spatial" in obsm_keys_lower:
        platform = "Spatial transcriptomics"
        suggestions = [
            "- **Spatial preprocessing** (QC → normalization → clustering): `spatial-preprocessing`",
            "- **Spatial domain identification** (tissue regions/niches): `spatial-domain-identification`",
            "- **Spatially variable genes** (SpatialDE, SPARK-X): `spatial-svg-detection`",
            "- **Cell type annotation** (Tangram, scANVI): `spatial-cell-annotation`",
            "- **Cell-cell communication** (LIANA, CellPhoneDB): `spatial-cell-communication`",
            "- **Pathway enrichment** (GSEA, ORA): `spatial-enrichment`",
        ]
    elif any(c in obs_cols_lower for c in ("leiden", "louvain", "cell_type", "celltype", "cluster")):
        platform = "Single-cell RNA-seq (already clustered/annotated)"
        suggestions = [
            "- **Differential expression** between groups: `sc-de`",
            "- **Marker gene detection**: `sc-markers`",
            "- **Trajectory / pseudotime** (DPT, PAGA): `sc-pseudotime`",
            "- **RNA velocity** (scVelo): `sc-velocity`",
            "- **Cell-cell communication** (LIANA, CellChat): `sc-cell-communication`",
            "- **Gene regulatory networks** (SCENIC): `sc-grn`",
        ]
    elif any(c in obs_cols_lower for c in ("pct_counts_mt", "n_genes_by_counts", "total_counts")):
        platform = "Single-cell RNA-seq (raw / QC stage)"
        suggestions = [
            "- **QC metrics & visualization**: `sc-qc`",
            "- **Cell filtering** (QC thresholds): `sc-filter`",
            "- **Doublet detection** (Scrublet, scDblFinder): `sc-doublet-detection`",
            "- **Full preprocessing** (QC → normalization → clustering → UMAP): `sc-preprocessing`",
            "- **Ambient RNA removal** (CellBender): `sc-ambient-removal`",
        ]
    else:
        platform = "Single-cell / generic h5ad"
        suggestions = [
            "- **Full preprocessing** (QC → normalization → clustering → UMAP): `sc-preprocessing`",
            "- **QC metrics**: `sc-qc`",
            "- **Cell type annotation**: `sc-cell-annotation`",
            "- **Batch integration** (Harmony, scVI): `sc-batch-integration`",
        ]

    domain_hint = ""
    if "spatial" in platform.lower():
        domain_hint = "spatial"
    elif "single-cell" in platform.lower() or "singlecell" in platform.lower():
        domain_hint = "singlecell"

    preview_skill = skill_arg
    if preview_params and not preview_skill and method_arg:
        preview_skill = _infer_skill_for_method(method_arg, preferred_domain=domain_hint)

    # Format report
    n_obs = info.get("n_obs", "?")
    n_vars = info.get("n_vars", "?")
    obs_cols = ", ".join(info.get("obs_columns", [])) or "none"
    var_cols = ", ".join(info.get("var_columns", [])) or "none"
    obsm = ", ".join(info.get("obsm_keys", [])) or "none"
    obsp = ", ".join(info.get("obsp_keys", [])) or "none"
    layers = ", ".join(info.get("layers", [])) or "none (X only)"
    uns = ", ".join(info.get("uns_keys", [])) or "none"
    has_spatial = "spatial" in obsm_keys_lower
    has_x_pca = "x_pca" in obsm_keys_lower
    has_counts_layer = "counts" in [k.lower() for k in info.get("layers", [])]
    has_raw = bool(info.get("has_raw", False))

    lines = [
        f"## Data Inspection: `{file_path.name}`",
        f"",
        f"| Property | Value |",
        f"|---|---|",
        f"| **Shape** | {n_obs:,} cells × {n_vars:,} genes |" if isinstance(n_obs, int) else f"| **Shape** | {n_obs} cells × {n_vars} genes |",
        f"| **Platform** | {platform} |",
        f"| **Cell metadata (obs)** | {obs_cols} |",
        f"| **Gene metadata (var)** | {var_cols} |",
        f"| **Embeddings / coords (obsm)** | {obsm} |",
        f"| **Graph matrices (obsp)** | {obsp} |",
        f"| **Layers** | {layers} |",
        f"| **uns keys** | {uns} |",
    ]

    if preview_params and method_arg:
        preview_block = _build_method_preview(
            skill_key=preview_skill or "",
            method=method_arg,
            n_obs=n_obs if isinstance(n_obs, int) else None,
            has_spatial=has_spatial,
            has_x_pca=has_x_pca,
            has_raw=has_raw,
            has_counts_layer=has_counts_layer,
            platform=platform,
        )
        lines.append("")
        if preview_block:
            lines.append(preview_block)
        else:
            lines.append("### Method Suitability & Parameter Preview")
            lines.append("- No `param_hints` found for this `skill/method` combination.")
            lines.append("- Add method hints in SKILL.md: `metadata.omicsclaw.param_hints.<method>`.")
            if not preview_skill:
                lines.append("- Tip: pass `skill` with `inspect_data` for accurate method preview.")

    lines.extend([
        "",
        "**Suggested analyses for this dataset:**",
    ])
    lines.extend(suggestions)
    lines.extend([
        "",
        "Tell me which analysis you'd like to run and I'll get started.",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# execute_download_file
# ---------------------------------------------------------------------------


async def execute_download_file(args: dict) -> str:
    """Download file from URL."""
    url = args.get("url", "")
    dest_arg = args.get("destination", "")

    if not url:
        return "Error: url is required."

    try:
        filename = url.split("/")[-1] or "downloaded_file"
        filename = sanitize_filename(filename)

        dest_dir = resolve_dest(dest_arg) if dest_arg else DATA_DIR
        dest_path = dest_dir / filename

        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = dest_path.stat().st_size / (1024 * 1024)
        return f"Downloaded: {dest_path} ({size_mb:.2f} MB)"
    except Exception as e:
        return f"Download failed: {e}"


# ---------------------------------------------------------------------------
# execute_create_json_file
# ---------------------------------------------------------------------------


async def execute_create_json_file(args: dict) -> str:
    """Create JSON file from data."""
    data = args.get("data", {})
    filename = args.get("filename", "")
    dest_arg = args.get("destination", "")

    if not filename:
        return "Error: filename is required."

    filename = sanitize_filename(filename)
    if not filename.endswith(".json"):
        filename += ".json"

    dest_dir = resolve_dest(dest_arg, default=OUTPUT_DIR) if dest_arg else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename

    try:
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"JSON file created: {filepath}"
    except Exception as e:
        return f"Error creating JSON file: {e}"


# ---------------------------------------------------------------------------
# execute_create_csv_file
# ---------------------------------------------------------------------------


async def execute_create_csv_file(args: dict) -> str:
    """Create CSV file from tabular data."""
    data = args.get("data", [])
    filename = args.get("filename", "")
    dest_arg = args.get("destination", "")

    if not filename:
        return "Error: filename is required."
    if not data:
        return "Error: data is required."

    filename = sanitize_filename(filename)
    if not filename.endswith(".csv"):
        filename += ".csv"

    dest_dir = resolve_dest(dest_arg, default=OUTPUT_DIR) if dest_arg else OUTPUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / filename

    try:
        import csv
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            if isinstance(data[0], dict):
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            else:
                writer = csv.writer(f)
                writer.writerows(data)
        return f"CSV file created: {filepath}"
    except Exception as e:
        return f"Error creating CSV file: {e}"


# ---------------------------------------------------------------------------
# execute_make_directory
# ---------------------------------------------------------------------------


async def execute_make_directory(args: dict) -> str:
    """Create a new directory (restricted to trusted directories)."""
    path_arg = args.get("path", "")

    if not path_arg:
        return "Error: path is required."

    target_path = Path(path_arg)
    if not target_path.is_absolute():
        target_path = OUTPUT_DIR / target_path

    # Validate against trusted directories
    _ensure_trusted_dirs()
    resolved = target_path.resolve() if target_path.exists() else target_path.parent.resolve() / target_path.name
    if not any(
        str(resolved).startswith(str(td.resolve()))
        for td in TRUSTED_DATA_DIRS
    ):
        dirs_str = ", ".join(str(d) for d in TRUSTED_DATA_DIRS)
        return f"Access denied: {target_path} is not in trusted directories ({dirs_str})"
        target_path = DATA_DIR / target_path

    try:
        target_path.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {target_path}"
    except Exception as e:
        return f"Error creating directory: {e}"


# ---------------------------------------------------------------------------
# execute_move_file
# ---------------------------------------------------------------------------


async def execute_move_file(args: dict) -> str:
    """Move or rename a file."""
    source_arg = args.get("source", "")
    dest_arg = args.get("destination", "")

    if not source_arg or not dest_arg:
        return "Error: source and destination are required."

    source_path = validate_input_path(source_arg)
    if not source_path:
        return f"Source file not found: {source_arg}"

    dest_path = Path(dest_arg)
    if not dest_path.is_absolute():
        dest_path = DATA_DIR / dest_path

    try:
        shutil.move(str(source_path), str(dest_path))
        return f"Moved: {source_path} → {dest_path}"
    except Exception as e:
        return f"Error moving file: {e}"


# ---------------------------------------------------------------------------
# execute_remove_file
# ---------------------------------------------------------------------------


async def execute_remove_file(args: dict) -> str:
    """Remove a file or directory."""
    path_arg = args.get("path", "")

    if not path_arg:
        return "Error: path is required."

    target_path = validate_input_path(path_arg)
    if not target_path:
        return f"Path not found: {path_arg}"

    try:
        if target_path.is_dir():
            shutil.rmtree(target_path)
            return f"Removed directory: {target_path}"
        else:
            target_path.unlink()
            return f"Removed file: {target_path}"
    except Exception as e:
        return f"Error removing: {e}"


# ---------------------------------------------------------------------------
# execute_get_file_size
# ---------------------------------------------------------------------------


async def execute_get_file_size(args: dict) -> str:
    """Get file size."""
    file_path_arg = args.get("file_path", "")

    if not file_path_arg:
        return "Error: file_path is required."

    file_path = validate_input_path(file_path_arg)
    if not file_path:
        return f"File not found: {file_path_arg}"

    try:
        size_bytes = file_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        return f"File: {file_path.name}\nSize: {size_mb:.2f} MB ({size_bytes:,} bytes)"
    except Exception as e:
        return f"Error getting file size: {e}"


# ---------------------------------------------------------------------------
# execute_remember — LLM tool for saving persistent memories
# ---------------------------------------------------------------------------


async def execute_remember(args: dict, session_id: str = None) -> str:
    """Save information to persistent memory (preferences, insights, project context)."""
    if not memory_store:
        return "Memory system not enabled. Set OMICSCLAW_MEMORY_BACKEND=sqlite in .env"
    if not session_id:
        return "Memory save requires an active session (user_id + platform)."

    mem_type = args.get("memory_type", "")

    try:
        if mem_type == "preference":
            from omicsclaw.memory.compat import PreferenceMemory

            key = args.get("key", "")
            value = args.get("value", "")
            domain = args.get("domain", "global")

            if not key or not value:
                return "Error: preference requires 'key' and 'value'."

            pref = PreferenceMemory(
                domain=domain,
                key=key,
                value=value,
                is_strict=False,
            )
            mem_id = await memory_store.save_memory(session_id, pref)
            logger.info(f"Memory saved: preference {key}={value} (domain={domain})")
            return f"✓ Preference saved: {key} = {value} (scope: {domain})"

        elif mem_type == "insight":
            from omicsclaw.memory.compat import InsightMemory

            entity_id = args.get("key", "")
            label = args.get("value", "")
            entity_type = args.get("entity_type", "cluster")
            source_id = args.get("source_analysis_id", "")
            confidence = args.get("confidence", "ai_predicted")

            if not entity_id or not label:
                return "Error: insight requires 'key' (entity ID) and 'value' (label)."

            insight = InsightMemory(
                source_analysis_id=source_id or "",
                entity_type=entity_type,
                entity_id=entity_id,
                biological_label=label,
                confidence=confidence,
            )
            mem_id = await memory_store.save_memory(session_id, insight)
            logger.info(f"Memory saved: insight {entity_type} {entity_id} = {label}")
            return f"✓ Insight saved: {entity_type} '{entity_id}' → {label} ({confidence})"

        elif mem_type == "project_context":
            from omicsclaw.memory.compat import ProjectContextMemory

            ctx = ProjectContextMemory(
                project_goal=args.get("project_goal", ""),
                species=args.get("species"),
                tissue_type=args.get("tissue_type"),
                disease_model=args.get("disease_model"),
            )

            if not any([ctx.project_goal, ctx.species, ctx.tissue_type, ctx.disease_model]):
                return "Error: project_context requires at least one of: project_goal, species, tissue_type, disease_model."

            mem_id = await memory_store.save_memory(session_id, ctx)
            parts = []
            if ctx.project_goal:
                parts.append(f"Goal: {ctx.project_goal}")
            if ctx.species:
                parts.append(f"Species: {ctx.species}")
            if ctx.tissue_type:
                parts.append(f"Tissue: {ctx.tissue_type}")
            if ctx.disease_model:
                parts.append(f"Disease: {ctx.disease_model}")
            logger.info(f"Memory saved: project context ({', '.join(parts)})")
            return f"✓ Project context saved: {' | '.join(parts)}"

        else:
            return f"Error: unknown memory_type '{mem_type}'. Use: preference, insight, project_context."

    except Exception as e:
        logger.error(f"Memory save failed: {e}", exc_info=True)
        return f"Error saving memory: {e}"


async def execute_consult_knowledge(args: dict, **kwargs) -> str:
    """Query the OmicsClaw knowledge base for analysis guidance."""
    try:
        import time as _t
        _ck_start = _t.monotonic()

        from omicsclaw.knowledge import KnowledgeAdvisor
        from omicsclaw.knowledge.semantic_bridge import (
            generate_query_rewrites,
            rerank_candidates_with_llm,
        )

        advisor = KnowledgeAdvisor()
        query = args.get("query", "")
        if not query:
            return "Error: 'query' parameter is required."
        if not advisor.ensure_available(auto_build=True):
            return "Knowledge base not built yet. Run: python omicsclaw.py knowledge build"

        domain = args.get("domain", "all")
        category = args.get("category", "all")
        domain_filter = domain if domain != "all" else None
        category_filter = category if category != "all" else None

        rewrites = await generate_query_rewrites(
            query=query,
            domain=domain_filter or "",
            doc_type=category_filter or "",
            llm_client=llm,
            model=OMICSCLAW_MODEL,
            available_topics=advisor.list_topics(domain_filter),
            max_queries=4,
        )
        results = advisor.search(
            query=query,
            domain=domain_filter,
            doc_type=category_filter,
            limit=8,
            extra_queries=rewrites,
        )
        results = await rerank_candidates_with_llm(
            query=query,
            candidates=results,
            llm_client=llm,
            model=OMICSCLAW_MODEL,
            limit=5,
        )
        result = advisor.format_results(query, results)

        # Stage 0: Telemetry
        _ck_elapsed_ms = (_t.monotonic() - _ck_start) * 1000
        try:
            from omicsclaw.knowledge.telemetry import get_telemetry
            results_count = result.count("--- Result") if result else 0
            get_telemetry().log_consult_knowledge(
                session_id=kwargs.get("session_id", "unknown"),
                query=query,
                category=category,
                domain=domain,
                results_count=results_count,
                latency_ms=_ck_elapsed_ms,
            )
        except Exception:
            pass

        return result
    except Exception as e:
        logger.error(f"Knowledge query failed: {e}", exc_info=True)
        return f"Error querying knowledge base: {e}"


async def execute_resolve_capability(args: dict, **kwargs) -> str:
    """Resolve whether a request maps to an existing skill or needs fallback."""
    try:
        from omicsclaw.core.capability_resolver import resolve_capability

        query = args.get("query", "")
        if not query:
            return "Error: 'query' parameter is required."

        file_path_arg = args.get("file_path", "")
        resolved_path = validate_input_path(file_path_arg) if file_path_arg else None
        decision = resolve_capability(
            query,
            file_path=str(resolved_path or file_path_arg or ""),
            domain_hint=args.get("domain_hint", ""),
        )
        return decision.to_json()
    except Exception as e:
        logger.error(f"Capability resolution failed: {e}", exc_info=True)
        return f"Error resolving capability: {e}"


async def execute_create_omics_skill(args: dict, **kwargs) -> str:
    """Create a new OmicsClaw skill scaffold inside the repository."""
    try:
        from omicsclaw.core.skill_scaffolder import create_skill_scaffold

        request = args.get("request", "")
        domain = args.get("domain", "")
        if not request:
            return "Error: 'request' parameter is required."

        result = create_skill_scaffold(
            request=request,
            domain=domain,
            skill_name=args.get("skill_name", ""),
            summary=args.get("summary", ""),
            source_analysis_dir=args.get("source_analysis_dir", ""),
            promote_from_latest=bool(args.get("promote_from_latest", False)),
            output_root=OUTPUT_DIR,
            input_formats=args.get("input_formats") or [],
            primary_outputs=args.get("primary_outputs") or [],
            methods=args.get("methods") or [],
            trigger_keywords=args.get("trigger_keywords") or [],
            create_tests=bool(args.get("create_tests", True)),
        )
        created = "\n".join(f"- {path}" for path in result.created_files or [])
        completion_summary = format_completion_mapping_summary(result.completion)
        return (
            "Created OmicsClaw skill scaffold.\n"
            f"Skill: {result.skill_name}\n"
            f"Domain: {result.domain}\n"
            f"Directory: {result.skill_dir}\n"
            f"Registry refreshed: {result.registry_refreshed}\n"
            f"Manifest: {result.manifest_path or '<none>'}\n"
            f"Completion report: {result.completion_report_path or '<none>'}\n"
            f"Gate:\n{completion_summary or '<unavailable>'}\n"
            f"Source analysis: {args.get('source_analysis_dir') or ('<latest autonomous analysis>' if args.get('promote_from_latest') else '<none>')}\n"
            "Files:\n"
            f"{created}"
        )
    except FileExistsError as e:
        return f"Error creating OmicsClaw skill: {e}"
    except Exception as e:
        logger.error(f"Create OmicsClaw skill failed: {e}", exc_info=True)
        return f"Error creating OmicsClaw skill: {e}"


async def execute_web_method_search(args: dict, **kwargs) -> str:
    """Search the web for methods/docs to support custom analysis fallback."""
    try:
        from omicsclaw.research import search_web_markdown

        query = args.get("query", "")
        if not query:
            return "Error: 'query' parameter is required."

        max_results = int(args.get("max_results", 3) or 3)
        topic = args.get("topic", "general") or "general"
        return await search_web_markdown(query, max_results=max_results, topic=topic)
    except ImportError as e:
        return (
            "Error: web search dependencies are not installed. "
            'Install with: pip install -e ".[autonomous]" or pip install -e ".[research]". '
            f"Details: {e}"
        )
    except Exception as e:
        logger.error(f"Web method search failed: {e}", exc_info=True)
        return f"Error searching the web for methods: {e}"


async def execute_custom_analysis_execute(args: dict, **kwargs) -> str:
    """Run custom analysis code in a restricted notebook sandbox."""
    try:
        from omicsclaw.core.capability_resolver import resolve_capability
        from omicsclaw.execution import run_autonomous_analysis

        goal = args.get("goal", "")
        analysis_plan = args.get("analysis_plan", "")
        python_code = args.get("python_code", "")
        if not goal or not analysis_plan or not python_code:
            return "Error: 'goal', 'analysis_plan', and 'python_code' are required."

        file_path_arg = args.get("file_path", "")
        resolved_path = None
        if file_path_arg:
            resolved_path = validate_input_path(file_path_arg)
            if resolved_path is None:
                found = discover_file(file_path_arg)
                if len(found) == 1:
                    resolved_path = found[0]
                elif len(found) > 1:
                    listing = "\n".join(f"  - {f}" for f in found[:8])
                    return (
                        f"Multiple files match '{file_path_arg}':\n{listing}\n\n"
                        "Please specify the full path before custom analysis."
                    )
                else:
                    return f"Error: input file not found or not trusted: {file_path_arg}"

        capability = resolve_capability(
            f"{goal}\n{analysis_plan}",
            file_path=str(resolved_path or ""),
        )

        result = await asyncio.to_thread(
            run_autonomous_analysis,
            output_root=str(OUTPUT_DIR),
            goal=goal,
            analysis_plan=analysis_plan,
            python_code=python_code,
            context=args.get("context", ""),
            web_context=args.get("web_context", ""),
            input_file=str(resolved_path or ""),
            sources=args.get("sources", ""),
            capability_decision=capability.to_dict(),
            output_label=args.get("output_label", "autonomous-analysis") or "autonomous-analysis",
        )

        if not result.get("ok"):
            completion_summary = format_completion_mapping_summary(result.get("completion"))
            return (
                "Custom analysis failed.\n"
                f"Output dir: {result.get('output_dir', '<unknown>')}\n"
                f"Notebook: {result.get('notebook_path', '<unknown>')}\n"
                f"Manifest: {result.get('manifest_path', '<unknown>')}\n"
                f"Completion report: {result.get('completion_report_path', '<unknown>')}\n"
                f"Gate:\n{completion_summary or '<unavailable>'}\n"
                f"Error: {result.get('error', 'unknown error')}"
            )

        preview = str(result.get("output_preview", "") or "")
        completion_summary = format_completion_mapping_summary(result.get("completion"))
        return (
            "Custom analysis completed.\n"
            f"Output dir: {result.get('output_dir')}\n"
            f"Notebook: {result.get('notebook_path')}\n"
            f"Summary: {result.get('summary_path')}\n"
            f"Manifest: {result.get('manifest_path')}\n"
            f"Completion report: {result.get('completion_report_path')}\n"
            f"Gate:\n{completion_summary or '<unavailable>'}\n"
            f"Preview:\n{preview or '<no stdout preview>'}"
        )
    except ImportError as e:
        return (
            "Error: autonomous notebook dependencies are not installed. "
            'Install with: pip install -e ".[autonomous]" or pip install -e ".[research]". '
            f"Details: {e}"
        )
    except Exception as e:
        logger.error(f"Custom analysis execution failed: {e}", exc_info=True)
        return f"Error running custom analysis: {e}"


# ---------------------------------------------------------------------------
# Tool executor registry
# ---------------------------------------------------------------------------

def _available_tool_executors() -> dict[str, object]:
    executors = {
        "omicsclaw": execute_omicsclaw,
        "save_file": execute_save_file,
        "write_file": execute_write_file,
        "generate_audio": execute_generate_audio,
        "parse_literature": execute_parse_literature,
        "fetch_geo_metadata": execute_fetch_geo_metadata,
        "list_directory": execute_list_directory,
        "inspect_file": execute_inspect_file,
        "download_file": execute_download_file,
        "create_json_file": execute_create_json_file,
        "create_csv_file": execute_create_csv_file,
        "make_directory": execute_make_directory,
        "move_file": execute_move_file,
        "remove_file": execute_remove_file,
        "get_file_size": execute_get_file_size,
        "remember": execute_remember,
        "consult_knowledge": execute_consult_knowledge,
        "resolve_capability": execute_resolve_capability,
        "create_omics_skill": execute_create_omics_skill,
        "web_method_search": execute_web_method_search,
        "custom_analysis_execute": execute_custom_analysis_execute,
        "inspect_data": execute_inspect_data,
    }
    executors.update(
        build_engineering_tool_executors(
            omicsclaw_dir=OMICSCLAW_DIR,
            tool_specs_supplier=lambda: get_tool_registry().specs,
        )
    )
    return executors


def _build_tool_runtime():
    return get_tool_registry().build_runtime(_available_tool_executors())


def get_tool_executors() -> dict[str, object]:
    return _build_tool_runtime().executors


TOOL_RUNTIME = _build_tool_runtime()
TOOLS = list(TOOL_RUNTIME.openai_tools)
TOOL_EXECUTORS = dict(TOOL_RUNTIME.executors)

MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))  # Increased from 10, configurable


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


def _sanitize_tool_history(history: list[dict], warn: bool = True) -> list[dict]:
    return _runtime_sanitize_tool_history(history, warn=warn)


async def _emit_tool_callback(callback, *args) -> None:
    if not callback:
        return
    if asyncio.iscoroutinefunction(callback):
        await callback(*args)
    else:
        callback(*args)


def _build_bot_query_engine_callbacks(
    *,
    chat_id: int | str,
    progress_fn,
    progress_update_fn,
    on_tool_call,
    on_tool_result,
    on_stream_content,
    logger_obj,
    audit_fn,
    deep_learning_methods: set[str],
    usage_accumulator,
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
            if func_name == "consult_knowledge":
                try:
                    from omicsclaw.knowledge.retriever import consume_runtime_notice

                    notice = consume_runtime_notice()
                    if notice:
                        display_output = f"{notice}\n{display_output}"
                except Exception:
                    pass
            await _emit_tool_callback(on_tool_result, func_name, display_output)

    def on_llm_error(exc: Exception) -> str:
        logger_obj.error(f"LLM API error: {exc}")
        return f"Sorry, I'm having trouble thinking right now -- API error: {exc}"

    return QueryEngineCallbacks(
        accumulate_usage=usage_accumulator,
        on_stream_content=on_stream_content,
        before_tool=before_tool,
        after_tool=after_tool,
        on_llm_error=on_llm_error,
    )


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
        skill_aliases=tuple(registry.skills.keys()),
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

    tool_runtime = _build_tool_runtime()
    hook_runtime = build_default_lifecycle_hook_runtime(OMICSCLAW_DIR)
    callbacks = _build_bot_query_engine_callbacks(
        chat_id=chat_id,
        progress_fn=progress_fn,
        progress_update_fn=progress_update_fn,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
        on_stream_content=on_stream_content,
        logger_obj=logger,
        audit_fn=audit,
        deep_learning_methods=DEEP_LEARNING_METHODS,
        usage_accumulator=_accumulate_usage,
    )
    return await run_query_engine(
        llm=llm,
        context=QueryEngineContext(
            chat_id=chat_id,
            session_id=session_id,
            system_prompt=system_prompt,
            user_message_content=chat_context.user_message_content,
            surface=platform or "bot",
            policy_state=ToolPolicyState(surface=platform or "bot"),
            hook_runtime=hook_runtime,
            tool_runtime_context={
                "omicsclaw_dir": str(OMICSCLAW_DIR),
                "workspace": workspace,
                "pipeline_workspace": pipeline_workspace,
            },
        ),
        tool_runtime=tool_runtime,
        transcript_store=transcript_store,
        tool_result_store=tool_result_store,
        config=QueryEngineConfig(
            model=OMICSCLAW_MODEL,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=8192,
            llm_error_types=(APIError,),
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
