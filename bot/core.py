"""
core.py — OmicsClaw Bot shared engine
=====================================
Platform-independent logic shared by Telegram and Feishu frontends:
LLM tool-use loop, skill execution, security helpers, audit logging.

Both frontends import this module, call ``init()`` once at startup, then
use the async helper functions to process user messages.
"""

from __future__ import annotations

import asyncio
import inspect
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

from dotenv import load_dotenv
from openai import AsyncOpenAI, APIError

# ---------------------------------------------------------------------------
# LLM provider presets  (Multi-Provider support)
# ---------------------------------------------------------------------------
# Each provider maps to (base_url, default_model, api_key_env_var).
# Users set LLM_PROVIDER=<key> for one-step configuration;
# LLM_BASE_URL and OMICSCLAW_MODEL can still override.
#
# Inspired by EvoScientist's Multi-Provider architecture, adapted for
# OmicsClaw's lightweight AsyncOpenAI-based design. All providers are
# accessed through the OpenAI-compatible API protocol.

PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    # --- Tier 1: Primary providers ---
    "deepseek":   ("https://api.deepseek.com",                                    "deepseek-chat",          "DEEPSEEK_API_KEY"),
    "openai":     ("",                                                             "gpt-4o",                 "OPENAI_API_KEY"),
    "anthropic":  ("https://api.anthropic.com/v1/",                                "claude-sonnet-4-5-20250514", "ANTHROPIC_API_KEY"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/",     "gemini-2.5-flash",       "GOOGLE_API_KEY"),
    "nvidia":     ("https://integrate.api.nvidia.com/v1",                          "deepseek-ai/deepseek-r1", "NVIDIA_API_KEY"),

    # --- Tier 2: Third-party aggregators ---
    "siliconflow": ("https://api.siliconflow.cn/v1",                              "deepseek-ai/DeepSeek-V3", "SILICONFLOW_API_KEY"),
    "openrouter":  ("https://openrouter.ai/api/v1",                               "deepseek/deepseek-chat-v3-0324", "OPENROUTER_API_KEY"),
    "volcengine":  ("https://ark.cn-beijing.volces.com/api/v3",                   "doubao-1.5-pro-256k",     "VOLCENGINE_API_KEY"),
    "dashscope":   ("https://dashscope.aliyuncs.com/compatible-mode/v1",          "qwen-max",                "DASHSCOPE_API_KEY"),
    "zhipu":       ("https://open.bigmodel.cn/api/paas/v4",                       "glm-4-flash",             "ZHIPU_API_KEY"),

    # --- Tier 3: Local & custom ---
    "ollama":     ("http://localhost:11434/v1",                                    "qwen2.5:7b",             ""),
    "custom":     ("",                                                             "",                        ""),

    # --- Legacy alias (backward compat — same as gemini) ---
}

# Ordered list for auto-detection: when LLM_PROVIDER is not set, we pick the
# first provider whose API key env var is present in the environment.
_PROVIDER_DETECT_ORDER = [
    "deepseek", "openai", "anthropic", "gemini", "nvidia",
    "siliconflow", "openrouter", "volcengine", "dashscope", "zhipu",
]


def resolve_provider(
    provider: str = "",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
) -> tuple[str | None, str, str]:
    """Return (base_url_or_None, model, resolved_api_key) after applying provider defaults.

    Priority: explicit env vars > provider preset > auto-detect > hardcoded fallback.

    When *provider* is empty and *api_key* is empty, we scan provider-specific
    environment variables (DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, …)
    to auto-detect the provider.
    """
    provider_key = provider.lower().strip() if provider else ""

    # Auto-detect provider from available API keys
    if not provider_key and not api_key:
        for p in _PROVIDER_DETECT_ORDER:
            env_var = PROVIDER_PRESETS[p][2]
            if env_var and os.environ.get(env_var):
                provider_key = p
                api_key = os.environ[env_var]
                break

    # Look up preset
    preset = PROVIDER_PRESETS.get(provider_key, ("", "", ""))
    preset_url, preset_model, preset_key_env = preset

    # Allow per-provider base_url override via env var (e.g. ANTHROPIC_BASE_URL)
    env_base_url = ""
    if provider_key:
        env_base_url = os.environ.get(f"{provider_key.upper()}_BASE_URL", "")

    resolved_url = base_url or env_base_url or preset_url or None
    resolved_model = model or preset_model or "deepseek-chat"

    # Resolve API key: explicit > per-provider env > LLM_API_KEY fallback
    if not api_key and preset_key_env:
        api_key = os.environ.get(preset_key_env, "")
    if not api_key:
        api_key = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

    return resolved_url, resolved_model, api_key


# ---------------------------------------------------------------------------
# Paths (relative to OmicsClaw project root)
# ---------------------------------------------------------------------------

OMICSCLAW_DIR = Path(__file__).resolve().parent.parent
OMICSCLAW_PY = OMICSCLAW_DIR / "omicsclaw.py"
SOUL_MD = OMICSCLAW_DIR / "SOUL.md"
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

conversations: dict[int | str, list] = {}
_conversation_access: dict[int | str, float] = {}  # LRU tracking
MAX_HISTORY = int(os.getenv("OMICSCLAW_MAX_HISTORY", "50"))
MAX_CONVERSATIONS = int(os.getenv("OMICSCLAW_MAX_CONVERSATIONS", "1000"))

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
# Shared rate limiter (used by both Telegram and Feishu)
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
    if len(conversations) <= MAX_CONVERSATIONS:
        return
    # Sort by access time, evict oldest
    sorted_keys = sorted(_conversation_access, key=_conversation_access.get)
    to_evict = len(conversations) - MAX_CONVERSATIONS
    for key in sorted_keys[:to_evict]:
        conversations.pop(key, None)
        _conversation_access.pop(key, None)
    logger.debug(f"Evicted {to_evict} stale conversation(s)")


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


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def get_role_guardrails() -> str:
    domain_names = ", ".join(d["name"].lower() for d in registry.domains.values())

    routing_lines = []
    for alias, info in registry.skills.items():
        desc = info.get("description", alias).split("—")[0].split("(")[0].strip()
        routing_lines.append(f"   - {desc}: skill='{alias}'")

    routing_text = "\n".join(routing_lines)

    return f"""
Operational constraints:
1. You are a multi-omics analysis assistant powered by OmicsClaw skills.
2. Supported domains: {domain_names}.
3. Keep outputs concise, evidence-led, and explicit about confidence and gaps.
4. When the user sends omics data or asks about analysis, use the omicsclaw tool. Skill routing:
{routing_text}
   - Auto-detect skill: skill='auto'
4b. METHOD PARAMETER (CRITICAL): When user specifies a method, pass it LOWERCASE via method parameter:
   - spatial-deconv methods: flashdeconv, cell2location, rctd, destvi, stereoscope, tangram, spotlight, card
   - spatial-domains methods: leiden, louvain, spagcn, stagate, graphst
   - spatial-annotate methods: tangram, scanvi, cellassign, sctype
   - spatial-communication methods: liana, cellphonedb, fastccc
   - spatial-trajectory methods: dpt, cellrank, palantir
   - spatial-genes methods: spatialde, sparkx
   - spatial-integration methods: harmony, bbknn, scanorama
   - spatial-velocity methods: scvelo, velovi
   Examples: "Cell2location" → method='cell2location', "Tangram" → method='tangram'
   IMPORTANT: Deep learning methods (cell2location, destvi, stereoscope, tangram, spagcn, stagate, graphst, scvi, velovi)
   may take 10-30 minutes. Inform user: "This will take 10-30 minutes, please wait..."
5. TOOL OUTPUT RELAY (STRICT): When the omicsclaw tool returns results, relay
   the output VERBATIM. Do not paraphrase, summarise, or rewrite. The output
   contains precise numerical data that must not be altered. You may add a brief
   intro line but never replace or condense the tool output.
6. For uploaded data or visual evidence, suggest appropriate OmicsClaw analysis skills.
7. PDF UPLOAD SUPPORT: When user uploads a PDF file (scientific paper), automatically
   call parse_literature tool to extract GEO accessions and metadata. The system
   will detect uploaded PDFs automatically.
8. For quick demos: say "run preprocess demo", "run ms-qc demo", etc.
   Use mode='demo' to run with built-in synthetic data.
9. FILE PATH MODE (IMPORTANT): Omics data files are often too large to upload
   via messaging. When the user mentions a file path or filename, use mode='path'
   and set file_path to the path or filename they provided. The system will automatically search
   trusted directories.
   **CRITICAL FILE USAGE RULES**:
   - When the user specifies a file path, use EXACTLY that file for the requested operation.
   - Do NOT automatically run preprocessing or other preparatory steps unless explicitly asked.
   - Do NOT explore directories to find "better" or "preprocessed" versions of the file.
   - Do NOT use list_directory to search for alternative files after the user specifies one.
   - If the operation fails because the file needs preprocessing, tell the user - don't auto-fix it.
   Examples:
   - User: "分析 data/brain_visium.h5ad" → mode='path', file_path='data/brain_visium.h5ad'
   - User: "run preprocess on my_data.h5ad" → mode='path', file_path='my_data.h5ad'
   - User: "对 /mnt/nas/exp1.mzML 做质量控制" → mode='path', file_path='/mnt/nas/exp1.mzML', skill='ms-qc'
9b. DATA EXPLORATION (IMPORTANT): When the user asks to "explore", "inspect",
    "what can I do with", or vaguely "analyze" a dataset WITHOUT specifying a
    concrete analysis pipeline, ALWAYS call `inspect_data` first:
    - Call inspect_data with the file path.
    - If user already mentions a specific method, also pass `method`,
      `skill` (if known), and `preview_params=true` to include parameter preview.
    - Based on the returned metadata (shape, obs columns, embeddings, platform),
      suggest 3-5 appropriate analysis skills to the user.
    - Do NOT call `omicsclaw` until the user picks a specific analysis.
    This prevents running expensive preprocessing pipelines when the user just
    wants to understand their data.
    Examples where you MUST use inspect_data first:
    - "帮我分析一下 data/brain.h5ad，我能做什么？"
    - "What analyses can I run on this dataset?"
    - "Tell me about this h5ad file"
    - "Explore my spatial data"
    - "I have data/foo.h5ad, what should I do with it?"
9c. METHOD SUITABILITY / PARAM PREVIEW (IMPORTANT): When users ask
    "is this method suitable?", "are defaults reasonable?", or request
    parameter advice before execution:
    - First call `inspect_data` with `file_path` and also pass
      `method`, `skill` (if known), and `preview_params=true`.
    - Relay the "Method Suitability & Parameter Preview" section.
    - Ask for confirmation before running expensive analysis.
    - Do NOT call `omicsclaw` immediately in this preflight scenario.
10. CAPABILITY-FIRST EXECUTION (STRICT):
   - Before a non-trivial analysis request, prefer `resolve_capability` unless the
     request is an obvious exact skill invocation.
   - If `should_create_skill=true`, use `create_omics_skill` when the user explicitly
     wants a reusable skill added to OmicsClaw.
   - If coverage='exact_skill', use `omicsclaw` and stay inside the existing skill.
   - If coverage='partial_skill', run the matched skill for the covered part and use
     `custom_analysis_execute` only for the missing step.
   - If coverage='no_skill', you MAY use `web_method_search` and then
     `custom_analysis_execute`.
   - Never silently jump to custom code when an exact skill exists.
10b. REUSABLE SKILL CREATION (STRICT):
   - Only create a new skill when the user explicitly asks to add, create, scaffold,
     package, or persist a reusable OmicsClaw skill.
   - For one-off analyses, do NOT create a new skill; use web-guided custom analysis instead.
   - Use `create_omics_skill` to scaffold the skill under `skills/<domain>/<skill-name>/`.
   - If the user wants to package a previously successful custom notebook, pass
     `source_analysis_dir`, or set `promote_from_latest=true` for the most recent autonomous run.
11. CONTROLLED CUSTOM ANALYSIS (STRICT):
   - NEVER use write_file to generate .py, .sh, .r, .R, or other standalone scripts.
   - Use `custom_analysis_execute` for custom code so execution stays in the
     restricted notebook sandbox.
   - `custom_analysis_execute` is for analysis only: no shell, no package install,
     no direct network, no arbitrary filesystem exploration.
   - Only use write_file/create_csv_file/create_json_file when the user EXPLICITLY
     asks to save or export specific data. All such files go to the output/ directory.
   - Do NOT use list_directory to browse output directories after an omicsclaw call —
     the tool result already contains all the information you need.
12. NO SILENT FALLBACK (STRICT): When a user specifies a method and it FAILS:
    - NEVER silently switch to a different method. This is a CRITICAL violation.
    - Report the EXACT error message from the failed method to the user.
    - Ask the user if they want to try an alternative method.
    - Only switch methods with EXPLICIT user confirmation.
    Example: User asks for DestVI, it fails → Tell user "DestVI failed: <error>.
    Would you like to try Tangram or Cell2Location instead?"
    WRONG: Silently run Tangram and say "The Tangram analysis succeeded".
13. MEMORY (IMPORTANT): You have persistent memory across conversations.
    - Use the 'remember' tool to save important context:
      * User preferences: language, default methods, output settings
      * Biological insights: cell type annotations, spatial domains identified
      * Project context: species, tissue type, disease model, research goals
    - Proactively remember when the user:
      * States a preference ("请用中文回答", "use DPI 300")
      * Tells you about their project ("我们研究小鼠大脑的阿尔茨海默病")
      * Confirms a biological annotation ("cluster 0 是T细胞")
    - Your memory context is loaded automatically at the start of each conversation
      under the "## Your Memory" section in the system prompt.
    - Do NOT tell the user you are saving memory; just do it silently.
14. KNOWLEDGE ADVISOR: You have a 'consult_knowledge' tool that searches decision
    guides, best practices, and troubleshooting docs. Use it proactively when users
    ask about method selection, parameters, or encounter errors. Extract the key
    recommendation concisely — do NOT dump full knowledge base content.
15. MANDATORY KNOW-HOW GUARDS (CRITICAL — READ BEFORE ANY ANALYSIS):
    Before starting ANY analysis task, you MUST check ALL relevant know-how guides
    that are injected into your context. These are non-negotiable scientific constraints
    derived from high-frequency AI errors in real-world analyses.

    **Routing table — which guide applies to which task:**
    • For ALL data analysis tasks → ALWAYS check "Best Practices for Data Analyses"
    • For RNA-seq / DEG analysis (DESeq2, edgeR, limma) → check "Bulk RNA-Seq DE"
      (MUST use padj not pvalue; MUST NOT confuse log2FC direction)
    • For pathway enrichment (ORA, GSEA, KEGG, Reactome) → check "Pathway Enrichment"
      (MUST separate up/down genes for ORA; MUST NOT use keyword filtering on pathways)
    • For gene essentiality / DepMap / CRISPR screens → check "Gene Essentiality"
      (MUST invert DepMap scores before correlation; negative raw = essential)

    When these guides appear under "⚠️ MANDATORY SCIENTIFIC CONSTRAINTS" in your
    context, follow them WITHOUT EXCEPTION. Do NOT skip, summarise, or override them.
"""

def build_system_prompt(
    memory_context: str = "",
    skill: str = "",
    query: str = "",
    domain: str = "",
    capability_context: str = "",
) -> str:
    if SOUL_MD.exists():
        soul = SOUL_MD.read_text(encoding="utf-8")
        logger.info(f"Loaded SOUL.md ({len(soul)} chars)")
    else:
        soul = (
            "You are a multi-omics AI assistant. "
            "Help users analyse multi-omics data with clarity and rigour."
        )
        logger.warning("SOUL.md not found, using fallback prompt")

    prompt = f"{soul}\n\n{get_role_guardrails()}"
    if memory_context:
        prompt += f"\n\n## Your Memory\n\n{memory_context}"
    if capability_context:
        prompt += f"\n\n{capability_context}"

    # Stage 1: Inject mandatory Know-How scientific constraints
    try:
        import time as _t
        _kh_start = _t.monotonic()
        from omicsclaw.knowledge.knowhow import get_knowhow_injector
        injector = get_knowhow_injector()
        constraints = injector.get_constraints(
            skill=skill or None,
            query=query or None,
            domain=domain or None,
        )
        _kh_elapsed_ms = (_t.monotonic() - _kh_start) * 1000
        if constraints:
            prompt += f"\n\n{constraints}"
            logger.info("Injected KH constraints (%d chars, %.1fms) for skill=%s",
                        len(constraints), _kh_elapsed_ms, skill or '(general)')
            # Stage 0: Telemetry
            try:
                from omicsclaw.knowledge.telemetry import get_telemetry
                injected_ids = injector.get_kh_for_skill(skill) if skill else injector.get_all_kh_ids()
                get_telemetry().log_kh_injection(
                    session_id="system",
                    skill=skill or "",
                    query=query[:200] if query else "",
                    domain=domain or "",
                    injected_khs=injected_ids,
                    constraints_length=len(constraints),
                    latency_ms=_kh_elapsed_ms,
                )
            except Exception:
                pass  # Telemetry must never block
    except Exception as e:
        logger.warning("KH injection failed (non-fatal): %s", e)

    return prompt

SYSTEM_PROMPT: str = ""

def _ensure_system_prompt():
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = build_system_prompt()


def _message_mentions_term(text: str, term: str) -> bool:
    term = (term or "").strip().lower()
    if not term:
        return False
    if len(term) <= 3 and term.replace("-", "").replace("_", "").isalnum():
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        return bool(re.search(pattern, text))
    return term in text


def _should_attach_capability_context(text: str) -> bool:
    if not text:
        return False

    lower = text.lower()
    if any(_message_mentions_term(lower, alias.lower()) for alias in registry.skills):
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


def _extract_analysis_hints(text: str) -> tuple[str, str]:
    """Extract skill name and domain hints from user message text.

    Returns (skill_hint, domain_hint) — both may be empty strings.
    Used by chat() to pass context to build_system_prompt() for
    targeted KH constraint injection.
    """
    if not text:
        return "", ""

    text_lower = text.lower()

    # Check for explicit skill names mentioned in the message
    skill_hint = ""
    try:
        from omicsclaw.core.registry import registry
        for alias in registry.skills:
            # Match skill names (e.g. "spatial-preprocessing", "sc-qc")
            if _message_mentions_term(text_lower, alias.lower()):
                skill_hint = alias
                break
    except Exception:
        pass

    # Check for domain hints
    domain_hint = ""
    _domain_keywords = {
        "bulkrna": ["deseq2", "edger", "limma", "bulk rna", "bulk-rna",
                     "differential expression", "rnaseq", "rna-seq", "deg",
                     "差异表达", "差异基因", "差异分析"],
        "singlecell": ["single cell", "single-cell", "scrna", "scanpy",
                        "seurat", "scvi", "cellranger", "10x",
                        "单细胞", "单细胞测序"],
        "spatial": ["spatial", "visium", "merfish", "slide-seq", "stereo-seq",
                     "10x visium", "squidpy",
                     "空间转录组", "空间组学"],
        "genomics": ["variant", "gwas", "vcf", "plink", "crispr", "depmap",
                      "essentiality", "genomic",
                      "基因组", "变异", "遗传变异"],
        "proteomics": ["proteomic", "mass spec", "peptide", "maxquant",
                        "蛋白质组", "蛋白组学"],
        "metabolomics": ["metabolomic", "xcms", "mzml", "metabolite",
                          "代谢组", "代谢物"],
    }
    for domain, keywords in _domain_keywords.items():
        if any(kw in text_lower for kw in keywords):
            domain_hint = domain
            break

    return skill_hint, domain_hint

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

def get_tools() -> list[dict]:
    skill_names = list(registry.skills.keys()) + ["auto"]
    skill_descriptions = [f"{alias} ({info.get('description', alias)})" for alias, info in registry.skills.items()]
    skill_desc_text = ", ".join(skill_descriptions)
    
    return [
        {
            "type": "function",
            "function": {
                "name": "omicsclaw",
                "description": (
                    f"Run an OmicsClaw multi-omics analysis skill. Available skills: {skill_desc_text}. "
                    "Use mode='demo' to run with built-in synthetic data. "
                    "Use mode='file' when the user has sent an omics data file. "
                    "IMPORTANT: When this tool returns results, relay the output VERBATIM. "
                    "By default only a text summary is returned (return_media omitted or empty). "
                    "Set return_media ONLY when the user explicitly asks for figures/plots/tables. "
                    "Use 'all' to send everything, or a keyword to filter "
                    "(e.g. 'umap' for UMAP plots, 'qc' for QC violin, 'cluster' for cluster tables). "
                    "Multiple keywords can be comma-separated (e.g. 'umap,qc')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "enum": skill_names,
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["file", "demo", "path"],
                            "description": (
                                "'demo' = built-in synthetic data; "
                                "'file' = user uploaded a file via messaging; "
                                "'path' = user provided a file path on the server."
                            ),
                        },
                        "return_media": {
                            "type": "string",
                            "description": (
                                "Filter for which figures/tables to send back. "
                                "Omit or leave empty for text summary only (default). "
                                "'all' = send all figures and tables. "
                                "Otherwise a comma-separated list of keywords to match filenames "
                                "(e.g. 'umap', 'qc', 'violin', 'cluster', 'umap,qc'). "
                                "Only set when the user explicitly asks for visual results."
                            ),
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Server-side file path or filename for mode='path'.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Natural language query for auto-routing.",
                        },
                        "extra_args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional CLI arguments (e.g. ['--method', 'spagcn']).",
                        },
                        "method": {
                            "type": "string",
                            "description": "Analysis method override passed as --method.",
                        },
                        "n_epochs": {
                            "type": "integer",
                            "description": (
                                "Number of training epochs for deep learning methods. "
                                "Defaults per method if omitted: "
                                "cell2location=30000, destvi=2500, stereoscope=150000, tangram=1000. "
                                "Only set when the user explicitly requests a custom epoch count."
                            ),
                        },
                        "data_type": {
                            "type": "string",
                            "description": "Data platform type passed as --data-type.",
                        },
                    },
                    "required": ["skill", "mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_file",
                "description": "Save a file that was sent via messaging to a specific folder. Default: OmicsClaw data/ directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination_folder": {"type": "string", "description": "Folder path (absolute)."},
                        "filename": {"type": "string", "description": "Optional filename."},
                    },
                    "required": ["destination_folder"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file with the given content. Files are saved to the output/ directory by default. ONLY use when user explicitly asks to create/save a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Full text content."},
                        "filename": {"type": "string", "description": "Filename with extension."},
                        "destination_folder": {"type": "string", "description": "Folder path (absolute). Default: OmicsClaw data/."},
                    },
                    "required": ["content", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_audio",
                "description": "Generate an MP3 audio file from text using edge-tts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to convert to speech."},
                        "filename": {"type": "string", "description": "Output MP3 filename."},
                        "voice": {"type": "string", "description": "TTS voice. Default: en-GB-RyanNeural."},
                        "rate": {"type": "string", "description": "Speech rate. Default: '-5%'."},
                        "destination_folder": {"type": "string", "description": "Output folder."},
                    },
                    "required": ["text", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "parse_literature",
                "description": "Parse scientific literature (PDF, URL, DOI, PubMed ID) to extract GEO accessions and metadata, then download datasets. Use when user mentions a paper, sends a PDF, or provides a literature reference.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_type": {
                            "type": "string",
                            "enum": ["auto", "url", "doi", "pubmed", "file", "text"],
                            "description": "Type of input (default: auto-detect)"
                        },
                        "input_value": {
                            "type": "string",
                            "description": "URL, DOI, PubMed ID, file path, or text content"
                        },
                        "auto_download": {
                            "type": "boolean",
                            "description": "Automatically download datasets (default: true)"
                        }
                    },
                    "required": ["input_value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_geo_metadata",
                "description": "Fetch metadata for a specific GEO accession (GSE, GSM, or GPL). Use when user asks to fetch, query, or get information about a specific GEO ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "accession": {
                            "type": "string",
                            "description": "GEO accession ID (e.g., GSE204716, GSM123456)"
                        },
                        "download": {
                            "type": "boolean",
                            "description": "Download the dataset after fetching metadata (default: false)"
                        }
                    },
                    "required": ["accession"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List contents of a directory. Use when user wants to see files in a folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path (default: current data directory)"}
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_file",
                "description": "Display contents of a CSV, JSON, or TXT file. Use when user wants to view file contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "lines": {"type": "integer", "description": "Number of lines to show (default: 20)"}
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "download_file",
                "description": "Download a file from a URL. Use when user provides a direct file URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "File URL"},
                        "destination": {"type": "string", "description": "Destination path (optional)"}
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_json_file",
                "description": "Create a JSON file from structured data. Saved to output/ by default. ONLY use when user explicitly asks to save data as JSON.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "object", "description": "Data to save as JSON"},
                        "filename": {"type": "string", "description": "Filename (without extension)"},
                        "destination": {"type": "string", "description": "Destination folder (optional)"}
                    },
                    "required": ["data", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_csv_file",
                "description": "Create a CSV file from tabular data. Saved to output/ by default. ONLY use when user explicitly asks to save data as CSV.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": {},
                            },
                            "description": "Array of row objects",
                        },
                        "filename": {"type": "string", "description": "Filename (without extension)"},
                        "destination": {"type": "string", "description": "Destination folder (optional)"}
                    },
                    "required": ["data", "filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "make_directory",
                "description": "Create a new directory under output/. ONLY use when user explicitly asks to create a folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to create"}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "move_file",
                "description": "Move or rename a file. ONLY use when user explicitly asks to move or rename files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source file path"},
                        "destination": {"type": "string", "description": "Destination path"}
                    },
                    "required": ["source", "destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_file",
                "description": "Delete a file or directory. ONLY use when user explicitly asks to remove files/folders.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File or directory path to remove"}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_size",
                "description": "Get file size in MB. Use when user asks about file size.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "File path"}
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": (
                    "Save important information to persistent memory so you can recall it "
                    "in future conversations. Use this to remember: user preferences "
                    "(language, default methods, DPI settings), biological insights "
                    "(cell type annotations, spatial domains found), and project context "
                    "(research goals, species, tissue type, disease model). "
                    "Memory persists across conversations and bot restarts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "enum": ["preference", "insight", "project_context"],
                            "description": (
                                "Type of memory to save. "
                                "'preference' = user settings (language, default method, DPI). "
                                "'insight' = biological discovery (cell types, clusters). "
                                "'project_context' = research context (species, tissue, disease, goal)."
                            ),
                        },
                        "key": {
                            "type": "string",
                            "description": (
                                "For preference: setting name (e.g. 'language', 'default_method', 'dpi'). "
                                "For insight: entity ID (e.g. 'cluster_0', 'domain_3'). "
                                "For project_context: not used."
                            ),
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "For preference: setting value (e.g. 'Chinese', 'tangram', '300'). "
                                "For insight: biological label (e.g. 'T cells', 'tumor region'). "
                                "For project_context: not used."
                            ),
                        },
                        "domain": {
                            "type": "string",
                            "description": "For preference: scope of the setting (e.g. 'global', 'spatial-preprocess'). Default: 'global'.",
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "For insight: type of entity (e.g. 'cluster', 'spatial_domain', 'cell_type').",
                        },
                        "source_analysis_id": {
                            "type": "string",
                            "description": "For insight: ID of the analysis that produced this insight (optional).",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["user_confirmed", "ai_predicted"],
                            "description": "For insight: confidence level. Use 'user_confirmed' when user explicitly states a label.",
                        },
                        "project_goal": {
                            "type": "string",
                            "description": "For project_context: research goal/objective.",
                        },
                        "species": {
                            "type": "string",
                            "description": "For project_context: species (e.g. 'human', 'mouse').",
                        },
                        "tissue_type": {
                            "type": "string",
                            "description": "For project_context: tissue type (e.g. 'brain', 'liver', 'tumor').",
                        },
                        "disease_model": {
                            "type": "string",
                            "description": "For project_context: disease model (e.g. 'breast cancer', 'Alzheimer').",
                        },
                    },
                    "required": ["memory_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consult_knowledge",
                "description": (
                    "Query the OmicsClaw knowledge base for analysis guidance. "
                    "Use this PROACTIVELY when: (1) user is unsure which analysis to run, "
                    "(2) user asks about method selection or parameters, "
                    "(3) an analysis fails and user needs troubleshooting, "
                    "(4) user asks 'how to' or 'which method' questions, "
                    "(5) before running complex analyses to check best practices. "
                    "Returns relevant decision guides, best practices, or troubleshooting advice."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language question about methodology, parameters, or troubleshooting",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "decision-guide", "best-practices", "troubleshooting",
                                "workflow", "method-reference", "interpretation",
                                "preprocessing-qc", "statistics", "tool-setup",
                                "domain-knowledge", "knowhow", "reference-script", "all",
                            ],
                            "description": "Filter by document type. Default: 'all'",
                        },
                        "domain": {
                            "type": "string",
                            "enum": [
                                "spatial", "singlecell", "genomics", "proteomics",
                                "metabolomics", "bulkrna", "general", "all",
                            ],
                            "description": "Filter by omics domain. Default: 'all'",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resolve_capability",
                "description": (
                    "Resolve whether a user request is fully covered by an existing OmicsClaw skill, "
                    "partially covered, or not covered. Use this before non-trivial analysis requests "
                    "when skill coverage is uncertain."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's analysis request in natural language.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional server-side data path or filename mentioned by the user.",
                        },
                        "domain_hint": {
                            "type": "string",
                            "enum": [
                                "spatial", "singlecell", "genomics", "proteomics",
                                "metabolomics", "bulkrna", "",
                            ],
                            "description": "Optional domain hint if the user has already narrowed the domain.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_method_search",
                "description": (
                    "Search external web sources for up-to-date method documentation, papers, or workflow guidance. "
                    "Use this when resolve_capability indicates no_skill or partial_skill and external references are needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing the method, package, or analysis goal.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search results to fetch. Default: 3.",
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["general", "news", "finance"],
                            "description": "Search topic. Default: general.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_omics_skill",
                "description": (
                    "Create a new OmicsClaw-native skill scaffold under skills/<domain>/<skill-name>/ "
                    "using templates/SKILL-TEMPLATE.md as the base structure. Use this only when the user "
                    "explicitly wants a reusable new skill added to OmicsClaw. If a previous "
                    "custom_analysis_execute run succeeded, you can promote that notebook into the new skill."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "Original user request describing the desired reusable skill.",
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Preferred lowercase hyphenated skill alias.",
                        },
                        "domain": {
                            "type": "string",
                            "enum": [
                                "spatial", "singlecell", "genomics", "proteomics",
                                "metabolomics", "bulkrna", "orchestrator",
                            ],
                            "description": "Target OmicsClaw domain for the new skill. Optional if it can be inferred from a promoted autonomous analysis.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "One-line summary of what the skill should do.",
                        },
                        "source_analysis_dir": {
                            "type": "string",
                            "description": "Optional path to a successful custom_analysis_execute output directory to promote into a skill.",
                        },
                        "promote_from_latest": {
                            "type": "boolean",
                            "description": "If true, promote the most recent successful autonomous analysis output when source_analysis_dir is not provided.",
                        },
                        "input_formats": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of domain-specific input format notes.",
                        },
                        "primary_outputs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of primary outputs the new skill should emit.",
                        },
                        "methods": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of primary methods/backends for the skill.",
                        },
                        "trigger_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of routing keywords users may say naturally.",
                        },
                        "create_tests": {
                            "type": "boolean",
                            "description": "Whether to generate a minimal test scaffold. Default: true.",
                        },
                    },
                    "required": ["request"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "custom_analysis_execute",
                "description": (
                    "Execute custom analysis code in a restricted Jupyter notebook when an existing OmicsClaw skill "
                    "does not fully cover the request. Provide one self-contained Python snippet. "
                    "The notebook exposes INPUT_FILE, ANALYSIS_GOAL, ANALYSIS_CONTEXT, WEB_CONTEXT, and AUTONOMOUS_OUTPUT_DIR. "
                    "Shell, package install, and direct network access are blocked."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal": {
                            "type": "string",
                            "description": "Short statement of the analysis objective.",
                        },
                        "analysis_plan": {
                            "type": "string",
                            "description": "Concise markdown plan describing what the custom analysis will do.",
                        },
                        "python_code": {
                            "type": "string",
                            "description": "A single self-contained Python snippet to execute inside the restricted notebook.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional local context from the conversation or prior skill outputs.",
                        },
                        "web_context": {
                            "type": "string",
                            "description": "Optional external method notes returned by web_method_search.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional input file path to expose as INPUT_FILE inside the notebook.",
                        },
                        "sources": {
                            "type": "string",
                            "description": "Optional markdown list of cited URLs or source notes to persist alongside the notebook.",
                        },
                        "output_label": {
                            "type": "string",
                            "description": "Optional short label for the output directory prefix.",
                        },
                    },
                    "required": ["goal", "analysis_plan", "python_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_data",
                "description": (
                    "Instantly inspect an AnnData (.h5ad) file's metadata — cell/gene counts, "
                    "obs/var columns, embeddings (obsm), layers, uns keys — WITHOUT loading "
                    "the expression matrix. Fast even for very large files. "
                    "Also supports pre-run method suitability and parameter preview when "
                    "`method` (and optionally `skill`) is provided. "
                    "ALWAYS call this when the user asks to 'explore', 'inspect', "
                    "'what can I do with', or vaguely 'analyze' a dataset WITHOUT specifying "
                    "a concrete analysis pipeline. Returns a formatted summary and suggested "
                    "analysis directions. Do NOT call omicsclaw for open-ended exploratory queries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the .h5ad file to inspect.",
                        },
                        "skill": {
                            "type": "string",
                            "description": "Optional skill alias for preflight preview (e.g. spatial-domain-identification).",
                        },
                        "method": {
                            "type": "string",
                            "description": "Optional method name for suitability + parameter preview.",
                        },
                        "preview_params": {
                            "type": "boolean",
                            "description": "If true, include a pre-run method suitability and default parameter preview block.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
    ]

TOOLS = get_tools()

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

        advisor = KnowledgeAdvisor()
        query = args.get("query", "")
        if not query:
            return "Error: 'query' parameter is required."

        domain = args.get("domain", "all")
        category = args.get("category", "all")

        result = advisor.search_formatted(
            query=query,
            domain=domain if domain != "all" else None,
            doc_type=category if category != "all" else None,
            limit=5,
        )

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
        return (
            "Created OmicsClaw skill scaffold.\n"
            f"Skill: {result.skill_name}\n"
            f"Domain: {result.domain}\n"
            f"Directory: {result.skill_dir}\n"
            f"Registry refreshed: {result.registry_refreshed}\n"
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
            return (
                "Custom analysis failed.\n"
                f"Output dir: {result.get('output_dir', '<unknown>')}\n"
                f"Notebook: {result.get('notebook_path', '<unknown>')}\n"
                f"Error: {result.get('error', 'unknown error')}"
            )

        preview = str(result.get("output_preview", "") or "")
        return (
            "Custom analysis completed.\n"
            f"Output dir: {result.get('output_dir')}\n"
            f"Notebook: {result.get('notebook_path')}\n"
            f"Summary: {result.get('summary_path')}\n"
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

TOOL_EXECUTORS = {
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

MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))  # Increased from 10, configurable


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


def _sanitize_tool_history(history: list[dict], warn: bool = True) -> list[dict]:
    """Drop orphaned or incomplete tool-call bundles from history."""
    sanitised: list[dict] = []
    pending_bundle: list[dict] | None = None
    pending_tool_ids: set[str] = set()

    def flush_pending(drop_incomplete: bool) -> None:
        nonlocal pending_bundle, pending_tool_ids
        if pending_bundle is None:
            return
        if drop_incomplete and pending_tool_ids:
            if warn:
                logger.warning(
                    "Dropped incomplete assistant/tool bundle from history; "
                    f"missing tool outputs for: {sorted(pending_tool_ids)}"
                )
        else:
            sanitised.extend(pending_bundle)
        pending_bundle = None
        pending_tool_ids = set()

    for msg in history:
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            flush_pending(drop_incomplete=True)
            pending_bundle = [msg]
            pending_tool_ids = {
                tc.get("id")
                for tc in msg.get("tool_calls", [])
                if isinstance(tc, dict) and tc.get("id")
            }
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if pending_bundle is not None and tool_call_id in pending_tool_ids:
                pending_bundle.append(msg)
                pending_tool_ids.remove(tool_call_id)
                if not pending_tool_ids:
                    flush_pending(drop_incomplete=False)
                continue

            if warn:
                logger.warning("Dropped orphaned tool message from history")
            continue

        flush_pending(drop_incomplete=True)
        sanitised.append(msg)

    flush_pending(drop_incomplete=True)
    return sanitised


async def llm_tool_loop(
    chat_id: int | str,
    user_content: str | list,
    user_id: str = None,
    platform: str = None,
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
            if chat_id in conversations:
                del conversations[chat_id]
            return "✓ Conversation history cleared. (Memory preserved)"

        elif cmd == "/new":
            # Clear conversation history but keep memory
            if chat_id in conversations:
                del conversations[chat_id]
            return "✓ New conversation started. (Memory preserved)"

        elif cmd == "/forget":
            # Clear both conversation and memory for a complete reset
            if chat_id in conversations:
                del conversations[chat_id]

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
• "run preprocess demo"
• "run spatial-domain-identification demo"
• "run spatial-de demo"
• "run ms-qc demo"

Or try: "show me a spatial transcriptomics demo" """

        elif cmd == "/examples":
            return """📚 Usage Examples:

**Literature Analysis:**
• "Parse this paper: https://pubmed.ncbi.nlm.nih.gov/12345"
• "Fetch GEO metadata for GSE204716"
• Upload a PDF file directly

**Data Analysis:**
• "Run spatial-preprocessing on brain_visium.h5ad"
• "Analyze data/sample.h5ad with spatial-domain-identification"
• "Run ms-qc on proteomics_data.mzML"

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
• Active Conversations: {len(conversations)}
• Tools Available: {len(TOOL_EXECUTORS)}
• Skills Loaded: {len(registry.skills)}
• Data Directory: {DATA_DIR}
• Output Directory: {OUTPUT_DIR}"""

        elif cmd == "/version":
            return f"""ℹ️ OmicsClaw Version:

• Project: OmicsClaw Multi-Omics Analysis Platform
• Domains: Spatial Transcriptomics, Single-Cell, Genomics, Proteomics, Metabolomics
• Skills: {len(registry.skills)} analysis skills
• Tools: {len(TOOL_EXECUTORS)} bot tools
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
- "Run spatial-preprocessing on data.h5ad"
- "Analyze GSE123456 dataset"

For more info: https://github.com/TianGzlab/OmicsClaw"""

    _ensure_system_prompt()
    if llm is None:
        return "Error: LLM client not initialised. Call core.init() first."

    # Load memory context if session manager available
    memory_context = ""
    if session_manager and user_id and platform:
        # Ensure session exists (create if first time)
        await session_manager.get_or_create(user_id, platform, str(chat_id))
        session_id = f"{platform}:{user_id}:{chat_id}"
        memory_context = await session_manager.load_context(session_id)

    # Build system prompt with memory context + dynamic KH injection
    # Extract skill/domain hints from the user's message for targeted KH loading
    _user_text = user_content if isinstance(user_content, str) else " ".join(
        b.get("text", "") for b in (user_content or []) if isinstance(b, dict)
    )
    _skill_hint, _domain_hint = _extract_analysis_hints(_user_text)
    _capability_context = ""
    if _should_attach_capability_context(_user_text):
        try:
            from omicsclaw.core.capability_resolver import resolve_capability

            decision = resolve_capability(_user_text, domain_hint=_domain_hint)
            _capability_context = decision.to_prompt_block()
            if not _skill_hint and decision.chosen_skill:
                _skill_hint = decision.chosen_skill
            if not _domain_hint and decision.domain:
                _domain_hint = decision.domain
        except Exception as e:
            logger.warning("Capability resolution context failed (non-fatal): %s", e)

    system_prompt = build_system_prompt(
        memory_context=memory_context,
        skill=_skill_hint,
        query=_user_text[:200] if _user_text else "",
        domain=_domain_hint,
        capability_context=_capability_context,
    )

    history = conversations.setdefault(chat_id, [])
    _conversation_access[chat_id] = time.time()
    _evict_lru_conversations()

    if isinstance(user_content, str):
        history.append({"role": "user", "content": user_content})
    else:
        oai_parts = []
        for block in user_content:
            if block.get("type") == "text":
                oai_parts.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "image":
                src = block.get("source", {})
                data_uri = f"data:{src['media_type']};base64,{src['data']}"
                oai_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                })
        history.append({"role": "user", "content": oai_parts})

    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]

    history[:] = _sanitize_tool_history(history)

    last_message = None
    _notified_methods: set[str] = set()  # Avoid duplicate progress messages
    for _iteration in range(MAX_TOOL_ITERATIONS):
        try:
            kwargs = {}
            if on_stream_content is not None:
                kwargs = {"stream": True, "stream_options": {"include_usage": True}}

            response = await llm.chat.completions.create(
                model=OMICSCLAW_MODEL,
                max_tokens=8192,
                messages=[{"role": "system", "content": system_prompt}] + history,
                tools=TOOLS,
                **kwargs
            )
            
            if on_stream_content is not None:
                class FakeFunction:
                    def __init__(self, name, arguments):
                        self.name = name
                        self.arguments = arguments
                class FakeToolCall:
                    def __init__(self, id, type_, function):
                        self.id = id
                        self.type = type_
                        self.function = function
                class FakeMessage:
                    def __init__(self, content, tool_calls):
                        self.content = content
                        self.tool_calls = tool_calls
                        
                final_content = ""
                tool_calls_dict = {}
                
                async for chunk in response:
                    if not chunk.choices:
                        if chunk.usage:
                            _accumulate_usage(chunk.usage)
                        continue
                    
                    delta = chunk.choices[0].delta
                    if delta.content:
                        final_content += delta.content
                        if inspect.iscoroutinefunction(on_stream_content):
                            await on_stream_content(delta.content)
                        else:
                            on_stream_content(delta.content)
                            
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            tc_index = tc_chunk.index
                            if tc_index not in tool_calls_dict:
                                tc_id = tc_chunk.id or ""
                                tc_type = tc_chunk.type or "function"
                                func_name = tc_chunk.function.name or ""
                                func_args = tc_chunk.function.arguments or ""
                                tool_calls_dict[tc_index] = FakeToolCall(tc_id, tc_type, FakeFunction(func_name, func_args))
                            else:
                                existing_tc = tool_calls_dict[tc_index]
                                if tc_chunk.function.name:
                                    existing_tc.function.name += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    existing_tc.function.arguments += tc_chunk.function.arguments
                
                tcs = [tool_calls_dict[idx] for idx in sorted(tool_calls_dict.keys())]
                last_message = FakeMessage(final_content if final_content else None, tcs if tcs else None)
            else:
                # Accumulate token usage statistics
                _accumulate_usage(response.usage)
                choice = response.choices[0]
                last_message = choice.message
                
        except APIError as e:
            logger.error(f"LLM API error: {e}")
            return f"Sorry, I'm having trouble thinking right now -- API error: {e}"

        assistant_msg: dict = {"role": "assistant", "content": last_message.content or ""}
        if last_message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in last_message.tool_calls
            ]
        history.append(assistant_msg)

        if not last_message.tool_calls:
            return last_message.content or "(no response)"

        for tc in last_message.tool_calls:
            func_name = tc.function.name
            executor = TOOL_EXECUTORS.get(func_name)
            if executor:
                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}
                logger.info(f"Tool call: {func_name}({json.dumps(func_args)[:200]})")
                audit("tool_call", chat_id=str(chat_id), tool=func_name,
                      args_preview=json.dumps(func_args, default=str)[:300])

                if on_tool_call:
                    if asyncio.iscoroutinefunction(on_tool_call):
                        await on_tool_call(func_name, func_args)
                    else:
                        on_tool_call(func_name, func_args)

                # Send progress message for deep learning methods (once per method)
                _progress_handle = None
                if func_name == "omicsclaw" and progress_fn:
                    dl_method = (func_args.get("method") or "").lower()
                    if dl_method in DEEP_LEARNING_METHODS and dl_method not in _notified_methods:
                        _notified_methods.add(dl_method)
                        method_display = func_args.get("method", dl_method)
                        _progress_handle = await progress_fn(
                            f"⏳ **{method_display}** is a deep learning method and may take "
                            f"10-60 minutes depending on data size. Please be patient...\n\n"
                            f"💡 The analysis is running on the server, you can leave this "
                            f"chat open and come back later."
                        )

                try:
                    # Pass session_id to tools that need it (omicsclaw, remember)
                    if func_name in ("omicsclaw", "remember") and user_id and platform:
                        session_id = f"{platform}:{user_id}:{chat_id}"
                        if func_name == "omicsclaw":
                            result = await executor(func_args, session_id, chat_id=chat_id)
                        else:
                            result = await executor(func_args, session_id)
                    elif func_name == "omicsclaw":
                        result = await executor(func_args, chat_id=chat_id)
                    else:
                        result = await executor(func_args)

                    # Update progress message on success
                    if _progress_handle and progress_update_fn:
                        method_display = (func_args.get("method") or "analysis")
                        await progress_update_fn(
                            _progress_handle,
                            f"✅ **{method_display}** analysis complete!"
                        )
                except Exception as tool_err:
                    logger.error(f"Tool {func_name} raised: {tool_err}", exc_info=True)
                    audit("tool_error", chat_id=str(chat_id), tool=func_name,
                          error=str(tool_err)[:300])
                    result = f"Error executing {func_name}: {type(tool_err).__name__}: {tool_err}"

                    # Update progress message on failure
                    if _progress_handle and progress_update_fn:
                        method_display = (func_args.get("method") or "analysis")
                        await progress_update_fn(
                            _progress_handle,
                            f"❌ **{method_display}** failed: {type(tool_err).__name__}"
                        )

                if on_tool_result:
                    if asyncio.iscoroutinefunction(on_tool_result):
                        await on_tool_result(func_name, result)
                    else:
                        on_tool_result(func_name, result)
            else:
                result = f"Unknown tool: {func_name}"

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    return last_message.content if last_message and last_message.content else "(max tool iterations reached)"


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
