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
            memory_store = CompatMemoryStore(db_url)
            session_manager = SessionManager(memory_store)
            logger.info(f"Memory system initialised: {memory_store.backend}")
        except Exception as e:
            logger.warning(f"Memory system disabled (init failed): {e}")
            memory_store = None
            session_manager = None
    else:
        logger.info("Memory system disabled via OMICSCLAW_MEMORY_ENABLED=false")
        memory_store = None
        session_manager = None

# Load .env from project root for local development if present.
# This keeps bot entrypoints simple and mirrors previous behaviour.
_env = OMICSCLAW_DIR / ".env"
if _env.exists():
    load_dotenv(_env)

# ---------------------------------------------------------------------------
# Deep learning methods that need progress notifications
# ---------------------------------------------------------------------------

DEEP_LEARNING_METHODS = {
    # Spatial methods
    "cellcharter", "graphst", "stagate", "spagcn", "constrastive-st",
    "spatialde", "nnsvg", "sparseae", "cell2location", "spacexr",

    # Single-cell methods
    "scvi", "scanvi", "totalvi", "scgen", "scgpt", "geneformer",
    "celltypist", "singler", "sctype", "scvelo",

    # Proteomics methods
    "dia-nn", "maxquant", "fragpipe", "msfragger", "alphapept",

    # Generic DL/AI methods
    "vae", "autoencoder", "transformer", "gnn", "bert", "llm",
}


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://\S+", text)


def extract_gse_id(text: str) -> str | None:
    m = re.search(r"\b(GSE\d{3,})\b", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# Data-file classification helpers
# ---------------------------------------------------------------------------

def _norm_ext(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".txt.gz"):
        return ".txt.gz"
    if name.endswith(".fastq.gz"):
        return ".fastq.gz"
    if name.endswith(".fq.gz"):
        return ".fq.gz"
    if len(path.suffixes) >= 2:
        tail2 = "".join(path.suffixes[-2:]).lower()
        if tail2 in (".csv.gz", ".tsv.gz"):
            return tail2
    return path.suffix.lower()


def is_data_file(path: Path) -> bool:
    return _norm_ext(path) in OMICS_EXTENSIONS


def detect_data_type_from_extension(path: Path) -> str:
    """Infer omics data type from file extension / filename."""
    ext = _norm_ext(path)
    name = path.name.lower()

    # Spatial / single-cell AnnData
    if ext == ".h5ad":
        return "h5ad"

    # Generic omics tables
    if ext in {".csv", ".tsv", ".txt", ".txt.gz", ".csv.gz", ".tsv.gz"}:
        return ext.lstrip(".")

    # FASTQ
    if ext in {".fastq", ".fq", ".fastq.gz", ".fq.gz"}:
        return "fastq"

    # Alignment / variant
    if ext == ".bam":
        return "bam"
    if ext == ".vcf":
        return "vcf"
    if ext == ".bed":
        return "bed"

    # Proteomics / metabolomics
    if ext in {".mzml", ".mzxml", ".raw"}:
        return "ms"

    # Common 10x directories / names could be treated specially elsewhere
    return ext.lstrip(".") or name


# ---------------------------------------------------------------------------
# GEO / literature tool helpers
# ---------------------------------------------------------------------------

def fetch_geo_metadata(gse_id: str) -> str:
    """Fetch GEO Series metadata via NCBI ESummary."""
    try:
        # Step 1: search GEO DataSets DB for GSE accession
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=gds&term={gse_id}[ACCN]&retmode=json"
        )
        r = requests.get(search_url, timeout=20)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return f"No GEO record found for {gse_id}."

        uid = ids[0]
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=gds&id={uid}&retmode=json"
        )
        r2 = requests.get(summary_url, timeout=20)
        r2.raise_for_status()
        result = r2.json().get("result", {})
        rec = result.get(uid, {})
        if not rec:
            return f"GEO metadata lookup failed for {gse_id}."

        title = rec.get("title", "(no title)")
        summary = rec.get("summary", "")
        gpl = rec.get("gpl", "")
        samples = rec.get("n_samples") or rec.get("samples", "")
        taxon = rec.get("taxon", "")
        return (
            f"GEO {gse_id}\n"
            f"Title: {title}\n"
            f"Platform: {gpl}\n"
            f"Samples: {samples}\n"
            f"Organism: {taxon}\n\n"
            f"Summary:\n{summary}"
        )
    except Exception as e:
        return f"Error fetching GEO metadata for {gse_id}: {e}"


def fetch_url_text(url: str, max_chars: int = 12000) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (OmicsClawBot literature parser)",
        "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    if "application/pdf" in ctype or url.lower().endswith(".pdf"):
        return "[PDF content fetching not implemented in lightweight mode]"
    text = r.text
    # Very lightweight cleanup
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def ensure_safe_relpath(rel_path: str) -> Path:
    """Resolve a user-provided relative path within OUTPUT_DIR safely.

    Also accepts the following trusted absolute locations:
    - data/
    - output/
    - examples/
    - .omicstmp/
    - Uploaded temp dirs created under system tmp that contain "omicsclaw-bot-"
    - Any path explicitly registered in TRUSTED_DATA_DIRS (e.g. received upload dirs)
    """
    p = Path(rel_path)
    if p.is_absolute():
        rp = p.resolve()
        # Allow project-root known dirs
        project_allowed = [DATA_DIR.resolve(), OUTPUT_DIR.resolve(), EXAMPLES_DIR.resolve()]
        # Allow hidden temp dir at project root if used
        hidden_tmp = (OMICSCLAW_DIR / ".omicstmp").resolve()
        project_allowed.append(hidden_tmp)

        # Allow explicitly trusted directories (registered at runtime)
        _ensure_trusted_dirs()
        explicit_allowed = [td.resolve() for td in TRUSTED_DATA_DIRS]

        # Allow OS temp upload dirs created by the bot
        try:
            tmp_root = Path(tempfile.gettempdir()).resolve()
        except Exception:
            tmp_root = None

        def _in_allowed(base: Path) -> bool:
            try:
                return rp == base or base in rp.parents
            except Exception:
                return False

        if any(_in_allowed(base) for base in (project_allowed + explicit_allowed)):
            return rp

        if tmp_root is not None:
            try:
                if tmp_root in rp.parents and "omicsclaw-bot-" in str(rp):
                    return rp
            except Exception:
                pass

        raise ValueError("Absolute paths are only allowed under project dirs or trusted upload dirs")

    target = (OUTPUT_DIR / p).resolve()
    if OUTPUT_DIR.resolve() not in target.parents and target != OUTPUT_DIR.resolve():
        raise ValueError("Path traversal detected")
    return target


# Directories trusted for absolute-path access in read/list/move operations.
TRUSTED_DATA_DIRS: set[Path] = set()


def _ensure_trusted_dirs() -> None:
    """Populate default trusted directories if not already present."""
    defaults = {DATA_DIR, OUTPUT_DIR, EXAMPLES_DIR, OMICSCLAW_DIR / ".omicstmp"}
    TRUSTED_DATA_DIRS.update(defaults)


# ---------------------------------------------------------------------------
# Tool execution helpers
# ---------------------------------------------------------------------------

def _read_utf8(path: Path, max_chars: int = 150_000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text


def _json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# OmicsClaw analysis tool
# ---------------------------------------------------------------------------

async def execute_omicsclaw(args: dict, session_id: str = None, chat_id: int | str = None) -> str:
    skill = args.get("skill", "")
    mode = args.get("mode", "demo")
    file_path = args.get("file_path", "")
    return_media = (args.get("return_media") or "").strip()
    # Re-introduced support for method selection (used by many skills)
    method = (args.get("method") or "").strip()

    # Allow legacy phrasing from prompts/tests
    if skill in {"auto", ""}:
        # Try light routing based on file extension / prompt hints.
        if file_path:
            inferred = detect_data_type_from_extension(Path(file_path))
            if inferred in {"h5ad"}:
                skill = "spatial-preprocessing"
            elif inferred in {"mzml", "mzxml", "raw", "ms"}:
                skill = "ms-qc"
            elif inferred in {"fastq", "fq", "fastq.gz", "fq.gz", "bam", "vcf", "bed"}:
                skill = "genomics-alignment"
            else:
                skill = "spatial-preprocessing"
        else:
            skill = "spatial-preprocessing"

    if mode not in {"demo", "file", "path"}:
        return "Error: mode must be one of demo, file, or path."

    if mode == "file":
        # Expect file uploaded earlier and tracked by chat_id.
        if chat_id is None or chat_id not in received_files:
            return "Error: no uploaded file available for this chat."
        file_info = received_files[chat_id]
        file_path = file_info["path"]

    if mode == "path":
        if not file_path:
            return "Error: file_path is required when mode='path'."
        try:
            # Allow trusted absolute paths or output-relative paths.
            p = Path(file_path)
            if not p.is_absolute():
                p = (OMICSCLAW_DIR / file_path).resolve()
            else:
                # Validate absolute path against trusted dirs
                _ensure_trusted_dirs()
                rp = p.resolve()
                if not any(
                    str(rp).startswith(str(td.resolve()))
                    for td in TRUSTED_DATA_DIRS
                ):
                    return f"Error: absolute path not under trusted dirs: {p}"
                p = rp
            if not p.exists():
                return f"Error: file not found: {p}"
            if not p.is_file():
                return f"Error: path is not a file: {p}"
            file_path = str(p)
        except Exception as e:
            return f"Error resolving path: {e}"

    # Build command.
    cmd = [PYTHON, str(OMICSCLAW_PY), "run", skill]

    # Pass through --method if the skill allows it per registry metadata.
    try:
        info = registry.skills.get(skill, {})
        allowed_flags = set(info.get("allowed_extra_flags", set()))
        if method and "--method" in allowed_flags:
            cmd += ["--method", method]
    except Exception:
        # Registry lookup should never be fatal here.
        pass

    if mode == "demo":
        cmd.append("--demo")
    else:
        cmd += ["--input", file_path]

    # Create unique output dir per run.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"{skill}_{stamp}"
    out_dir = OUTPUT_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd += ["--output", str(out_dir)]

    logger.info("Running OmicsClaw: %s", " ".join(cmd))
    audit("omicsclaw_run", chat_id=str(chat_id) if chat_id else None,
          skill=skill, mode=mode, file=file_path or None, output=str(out_dir))

    # Auto-capture dataset memory if processing a file
    if session_id and mode in ("file", "path") and file_path:
        data_type = detect_data_type_from_extension(Path(file_path))
        await _auto_capture_dataset(session_id, file_path, data_type)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(OMICSCLAW_DIR),
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace")
        success = proc.returncode == 0

        # Auto-capture analysis memory
        if session_id:
            await _auto_capture_analysis(session_id, skill, args, out_dir, success)

        # Gather outputs.
        media_files = []
        text_snippets = []
        report_file = out_dir / "report.md"
        if report_file.exists():
            try:
                text_snippets.append(_read_utf8(report_file, max_chars=12_000))
            except Exception:
                pass
        summary_files = sorted(out_dir.glob("*.txt")) + sorted(out_dir.glob("*.md"))
        for p in summary_files:
            if p == report_file:
                continue
            try:
                text_snippets.append(f"--- {p.name} ---\n" + _read_utf8(p, max_chars=8000))
            except Exception:
                pass
        # Media: images/tables/archive-like documents
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.pdf", "*.csv", "*.tsv", "*.h5ad", "*.html"):
            media_files.extend(sorted(out_dir.glob(pattern)))

        # Build user-facing response. Never drop stdout entirely since many skills
        # only print a textual report.
        pieces = []
        pieces.append(f"Analysis {'completed' if success else 'failed'}: {skill}")
        pieces.append(f"Output directory: {out_dir}")
        if text_snippets:
            pieces.append("\n\n".join(text_snippets[:3]))
        else:
            pieces.append(text[:12000] if text else "(no textual output)")

        # Stash media for outer platform layers to deliver after the final reply.
        media_items = []
        for f in media_files:
            ext = f.suffix.lower()
            if ext in {".pdf", ".csv", ".tsv", ".h5ad", ".html"}:
                media_items.append({"type": "document", "path": str(f)})
            elif ext in {".png", ".jpg", ".jpeg"}:
                media_items.append({"type": "photo", "path": str(f)})

        # Always make media discoverable to users, but only attach when requested.
        if media_files:
            other_lines = []
            for f in media_files[:20]:
                kind = "image" if f.suffix.lower() in {".png", ".jpg", ".jpeg"} else "file"
                other_lines.append(f"- {f.name} ({kind})")
            if return_media and media_items:
                # Apply optional filename keyword filter.
                filtered = media_items
                if return_media.lower() != "all":
                    keywords = [k.strip().lower() for k in return_media.split(",") if k.strip()]
                    if keywords:
                        filtered = [
                            item for item in media_items
                            if any(k in Path(item["path"]).name.lower() for k in keywords)
                        ]
                pending_media[chat_id] = filtered
                logger.info(f"return_media='{return_media}': sending {len(filtered)}/{len(media_items)} items")
                pieces.append(
                    f"\n\n[MEDIA DELIVERY]\nAttached {len(filtered)} output file(s)."
                )
                if other_lines:
                    pieces.append("[Other available outputs]\n" + "\n".join(other_lines))
            else:
                pieces.append(
                    "\n\n[Available outputs]\n"
                    + "This analysis produced files. Ask me to send them if you want them.\n"
                    + "Examples: '请把图发我', 'send all outputs', 'send UMAP plot only'.\n"
                    + "\n".join(other_lines)
                )

        return "\n\n".join(pieces)
    except Exception as e:
        logger.exception("OmicsClaw execution error")

        if session_id:
            await _auto_capture_analysis(session_id, skill, args, out_dir, False)

        return f"Error running OmicsClaw: {e}"


# ---------------------------------------------------------------------------
# Uploaded file handling
# ---------------------------------------------------------------------------

async def register_received_file(
    chat_id: int | str,
    filename: str,
    data: bytes,
) -> dict:
    """Persist a received upload to a temp dir and track it by chat id.

    Returns metadata dict with path/filename/ext/data_type.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large (> {MAX_UPLOAD_BYTES} bytes)")

    tmp_dir = Path(tempfile.mkdtemp(prefix="omicsclaw-bot-"))
    safe_name = sanitize_filename(filename)
    path = tmp_dir / safe_name
    path.write_bytes(data)

    info = {
        "filename": safe_name,
        "path": str(path),
        "ext": _norm_ext(path),
        "data_type": detect_data_type_from_extension(path),
        "size": len(data),
    }
    received_files[chat_id] = info
    # Trust this temp directory for future read/list operations.
    TRUSTED_DATA_DIRS.add(tmp_dir)
    logger.info(f"Registered upload for chat {chat_id}: {info}")
    audit("upload", chat_id=str(chat_id), filename=safe_name, size=len(data))
    return info


def describe_received_file(chat_id: int | str) -> str:
    info = received_files.get(chat_id)
    if not info:
        return "No uploaded file registered."
    return (
        f"Uploaded file: {info['filename']}\n"
        f"Path: {info['path']}\n"
        f"Type: {info['data_type']}\n"
        f"Size: {info['size']} bytes"
    )


# ---------------------------------------------------------------------------
# Utility: prompt/assistant routing helpers
# ---------------------------------------------------------------------------

def build_system_prompt(memory_context: str = "") -> str:
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
    return prompt

SYSTEM_PROMPT: str = ""


def _ensure_system_prompt():
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = build_system_prompt()

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
                            "description": "Required when mode='path'. Absolute paths allowed under data/, output/, examples/, or trusted upload dirs.",
                        },
                        "method": {
                            "type": "string",
                            "description": (
                                "Optional method/algorithm to use if supported by the chosen skill "
                                "(e.g. 'spagcn', 'cellcharter', 'graphst', 'cell2location', 'dea', 'fgsea')."
                            ),
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
                "description": "Save arbitrary text content to a file in the output directory. ONLY use when the user explicitly asks to save or export content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Filename relative to output/ (e.g. notes.txt)"},
                        "content": {"type": "string", "description": "Text content to write"},
                    },
                    "required": ["filename", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file with text content. Saved to output/ by default. ONLY use when the user explicitly asks to create or save a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Destination file path (relative to output/ or absolute under trusted dirs)"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_audio",
                "description": "Generate an MP3 audio file from text using TTS. ONLY use when the user explicitly asks for audio/voice output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to synthesise"},
                        "filename": {"type": "string", "description": "Optional output filename (relative to output/)"},
                        "voice": {"type": "string", "description": "Optional Edge-TTS voice name (default en-US-AriaNeural)"},
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "parse_literature",
                "description": "Fetch a URL (HTML/PDF placeholder) and return extracted text summary. Use when user sends a paper URL or DOI landing page.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Article/paper URL"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_geo_metadata",
                "description": "Retrieve metadata for a GEO Series accession (e.g. GSE204716). Use when user asks about a GEO dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gse_id": {"type": "string", "description": "GEO Series accession like GSE123456"},
                    },
                    "required": ["gse_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List files in a directory (data/, output/, examples/, or trusted upload dirs). Use when user asks to browse files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path (optional, defaults to data/)"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_file",
                "description": "Show the first lines or metadata of a file (CSV/TSV/TXT/JSON/MD). Use when user asks to inspect file content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "max_lines": {"type": "integer", "description": "Maximum number of lines to display (default 40)"},
                    },
                    "required": ["path"],
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
                        "destination": {"type": "string", "description": "Destination file path"},
                    },
                    "required": ["source", "destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_file",
                "description": "Delete a file or empty directory under trusted dirs. ONLY use when the user explicitly asks to delete something.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to remove"}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_size",
                "description": "Get file size and metadata. Use when user asks about file size or storage.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": "Save important user/project context to persistent memory. Use proactively for preferences, project details, confirmed annotations, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "enum": ["preference", "insight", "project_context"],
                            "description": "Type of memory to save"
                        },
                        "key": {
                            "type": "string",
                            "description": "Memory key (e.g. 'language', 'dpi', 'cluster_0')"
                        },
                        "value": {
                            "type": "string",
                            "description": "Memory value (e.g. 'Chinese', '300', 'T_cell')"
                        },
                        "domain": {
                            "type": "string",
                            "description": "Preference scope: global, plotting, analysis, etc."
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "For insights: cluster, region, gene_signature, etc."
                        },
                        "source_analysis_id": {
                            "type": "string",
                            "description": "Optional source analysis memory ID"
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["ai_predicted", "user_confirmed", "imported"],
                            "description": "Confidence level for biological insights"
                        },
                        "project_goal": {
                            "type": "string",
                            "description": "For project_context: research goal or question"
                        },
                        "species": {
                            "type": "string",
                            "description": "For project_context: species (e.g. human, mouse)"
                        },
                        "tissue_type": {
                            "type": "string",
                            "description": "For project_context: tissue (e.g. brain, liver)"
                        },
                        "disease_model": {
                            "type": "string",
                            "description": "For project_context: disease/condition"
                        },
                    },
                    "required": ["memory_type"],
                },
            },
        },
    ]


TOOLS = get_tools()


def get_role_guardrails() -> str:
    """Instruction block used in the system prompt.

    These guardrails steer the LLM to use tools correctly and avoid
    fabricating analysis outputs.
    """
    domain_names = ", ".join(d["name"].lower() for d in registry.domains.values())
    # List skills for transparency (short descriptions only).
    # Keep prompt length reasonable.
    skill_lines = []
    for alias, info in registry.skills.items():
        desc = info.get("description", "").strip()
        skill_lines.append(f"- {alias}: {desc}")
    skills_catalog = "\n".join(skill_lines)

    return f"""
You are OmicsClaw, a careful multi-omics analysis assistant for {domain_names}.

Core rules:
1. NEVER fabricate that an analysis ran successfully if the `omicsclaw` tool was not called.
2. If the user asks to run analysis, inspect data, fetch GEO metadata, parse a paper URL,
   list files, or save/export content, you MUST call the relevant tool rather than only explaining.
3. When using `omicsclaw`, choose the most appropriate skill from the available list below.
4. If the user uploaded a file in the chat, use `omicsclaw` with mode='file'.
5. If the user explicitly provides a file path on the server, use mode='path' and pass `file_path`.
6. If the user wants a quick example/demo, use mode='demo'.
7. If a request involves GEO series like GSE123456, call `fetch_geo_metadata`.
8. If the user shares a URL/DOI and wants paper analysis, call `parse_literature`.
9. If the user asks to view/browse files, call `list_directory` or `inspect_file`.
10. When `omicsclaw` returns, present its textual output clearly and accurately.
    If it says outputs are available, explain how the user can request them.
11. Do NOT claim you created/saved/moved/deleted a file unless the corresponding tool succeeded.
12. MEMORY (IMPORTANT): You have persistent memory across conversations.
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

Available skills:
{skills_catalog}

Tool usage examples:
- User: "Run spatial preprocessing on my uploaded .h5ad" → call `omicsclaw` with mode='file', skill='spatial-preprocessing'.
- User: "Analyze /data/sample.mzML" → call `omicsclaw` with mode='path'.
- User: "Show files in output" → call `list_directory`.
- User: "Fetch GEO metadata for GSE204716" → call `fetch_geo_metadata`.
- User: "Please save this summary to a file" → call `save_file` or `write_file`.

Output discipline:
- If tool output contains errors or caveats, preserve them.
- If no tool is needed, answer concisely and scientifically.
- For analysis requests, prefer acting with tools over giving generic advice.
- When a tool returns a long report, summarize the most important findings first
  but keep the concrete paths / next steps.
- If outputs are available but not attached, tell the user they can ask for them.
- Do not promise plots/tables unless tool output indicates they exist.
- When relaying tool output, if it already contains the main answer, keep a short
  intro line but never replace or condense the tool output.
"""

# ... truncated in this API push for brevity not allowed
