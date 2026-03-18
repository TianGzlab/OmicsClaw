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
# LLM provider presets
# ---------------------------------------------------------------------------
# Each provider maps to (base_url, default_model).
# Users set LLM_PROVIDER=<key> for one-step configuration;
# LLM_BASE_URL and OMICSCLAW_MODEL can still override.

PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.0-flash",
    ),
    "openai": ("", "gpt-4o"),
    "custom": ("", ""),
}


def resolve_provider(
    provider: str = "",
    base_url: str = "",
    model: str = "",
) -> tuple[str | None, str]:
    """Return (base_url_or_None, model) after applying provider defaults.

    Priority: explicit env vars > provider preset > hardcoded fallback.
    """
    preset_url, preset_model = PROVIDER_PRESETS.get(
        provider.lower().strip(), ("", "")
    )
    resolved_url = base_url or preset_url or None
    resolved_model = model or preset_model or "deepseek-chat"
    return resolved_url, resolved_model


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

async def _auto_capture_analysis(session_id: str, skill: str, args: dict, output_dir: Path, success: bool):
    """Auto-capture analysis memory after skill execution."""
    if not session_manager or not session_id:
        return

    try:
        from bot.memory.models import AnalysisMemory

        # Extract key parameters
        method = args.get("method", "default")
        input_path = args.get("file_path", "")

        # Link to most recent dataset memory for lineage (optional, don't fail if missing)
        source_dataset_id = ""
        try:
            datasets = await memory_store.get_memories(session_id, "dataset", limit=1)
            if datasets:
                source_dataset_id = datasets[0].memory_id
        except Exception:
            # Dataset not found is OK, just skip the linkage
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
        # Log but don't fail the main workflow
        logger.warning(f"Auto-capture failed: {e}")


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
            session = await self.store.create_session(user_id, platform, chat_id)
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
    api_key: str,
    base_url: str | None = None,
    model: str = "",
    provider: str = "",
):
    """Initialise the shared LLM client. Call once at startup.

    ``provider`` selects a preset (deepseek, gemini, openai, custom).
    Explicit ``base_url`` / ``model`` override the preset.
    """
    global llm, OMICSCLAW_MODEL, LLM_PROVIDER_NAME, memory_store, session_manager

    resolved_url, resolved_model = resolve_provider(
        provider=provider,
        base_url=base_url or "",
        model=model,
    )
    OMICSCLAW_MODEL = resolved_model
    LLM_PROVIDER_NAME = provider or ("custom" if base_url else "openai")

    kw: dict = {"api_key": api_key}
    if resolved_url:
        kw["base_url"] = resolved_url
    llm = AsyncOpenAI(**kw)

    logger.info(
        f"LLM initialised: provider={LLM_PROVIDER_NAME}, "
        f"model={OMICSCLAW_MODEL}, base_url={resolved_url or '(default)'}"
    )

    # Optional memory initialization
    if os.getenv("OMICSCLAW_MEMORY_BACKEND") == "sqlite":
        try:
            from bot.memory import SQLiteBackend, SecureFieldEncryptor

            db_path = os.getenv("OMICSCLAW_MEMORY_DB_PATH", "bot/data/memory.db")
            encryption_key = os.getenv("ENCRYPTION_KEY")

            if not encryption_key:
                import secrets
                encryption_key = secrets.token_urlsafe(32)[:32].ljust(32, '0')
                logger.warning("No encryption key set, using temporary key")

            encryptor = SecureFieldEncryptor(encryption_key.encode()[:32])
            store = SQLiteBackend(db_path, encryptor)
            # NOTE: initialize() is called lazily on first async operation
            # via _ensure_initialized(), since init() runs in sync context
            # where asyncio.create_task() may not have a running loop.

            memory_store = store
            session_manager = SessionManager(store)
            logger.info("Memory system initialized")
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
10. NO CODE GENERATION (STRICT): You are an analysis assistant, NOT a code generator.
   - NEVER proactively create Python scripts, shell scripts, or code files.
   - NEVER use write_file to generate .py, .sh, .r, .R, or other script files.
   - All analysis MUST go through the omicsclaw tool — the skills already implement
     the code. Your role is to route user requests to the right skill, not to write code.
   - Only use write_file/create_csv_file/create_json_file when the user EXPLICITLY
     asks to save or export specific data. All such files go to the output/ directory.
   - Do NOT use list_directory to browse output directories after an omicsclaw call —
     the tool result already contains all the information you need.
11. NO SILENT FALLBACK (STRICT): When a user specifies a method and it FAILS:
    - NEVER silently switch to a different method. This is a CRITICAL violation.
    - Report the EXACT error message from the failed method to the user.
    - Ask the user if they want to try an alternative method.
    - Only switch methods with EXPLICIT user confirmation.
    Example: User asks for DestVI, it fails → Tell user "DestVI failed: <error>.
    Would you like to try Tangram or Cell2Location instead?"
    WRONG: Silently run Tangram and say "The Tangram analysis succeeded".
"""

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
                        "data": {"type": "array", "description": "Array of row objects"},
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

    # --- Auto-routing via orchestrator ---
    if skill_key == "auto":
        orch_script = OMICSCLAW_DIR / "skills" / "orchestrator" / "omics_orchestrator.py"
        if not orch_script.exists():
            return "Error: omics-orchestrator not found."

        orch_input = query
        if resolved_path:
            orch_input = str(resolved_path)
        elif mode == "file":
            for _cid, info in received_files.items():
                orch_input = info["path"]
                break
        if not orch_input:
            return "Error: skill='auto' requires either a file, a file_path, or a query to route."

        try:
            orch_cmd = [PYTHON, str(orch_script)]
            if query:
                orch_cmd.extend(["--query", query])
            else:
                orch_cmd.extend(["--input", orch_input])
            orch_cmd.extend(["--output", str(OUTPUT_DIR / "orchestrator_auto")])

            proc = await asyncio.create_subprocess_exec(
                *orch_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(orch_script.parent),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return f"Orchestrator error: {stderr.decode()[-500:]}"

            result_json = OUTPUT_DIR / "orchestrator_auto" / "result.json"
            if result_json.exists():
                routing = json.loads(result_json.read_text())
                detected = routing.get("data", {}).get("detected_skill", "")
                if detected:
                    skill_key = detected
                    logger.info(f"Auto-routed to: {skill_key}")
                else:
                    return f"Orchestrator could not determine a skill. Output: {stdout.decode()[:500]}"
            else:
                return f"Orchestrator completed but no result.json found. stdout: {stdout.decode()[:500]}"
        except asyncio.TimeoutError:
            return "Error: orchestrator timed out."
        except Exception as e:
            return f"Error running orchestrator: {e}"

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
    out_dir = OUTPUT_DIR / f"{skill_key}_{ts}_{uuid.uuid4().hex[:8]}"

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
        return f"{skill_key} failed (exit {proc.returncode}):\n{err}"

    # Collect report + figures from output directory
    return_media = str(args.get("return_media", "")).strip().lower()
    figure_names = []
    table_names = []
    sent_names = []
    if out_dir.exists():
        media_items = []
        for f in sorted(out_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix in (".md", ".html"):
                media_items.append({"type": "document", "path": str(f)})
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

    # Auto-capture analysis memory
    if session_id:
        await _auto_capture_analysis(session_id, skill_key, args, out_dir, True)

    result_text = "\n".join(keep_lines).strip()

    # Append media delivery status so the LLM knows what happened
    # and does NOT attempt to browse output directories itself.
    all_names = figure_names + table_names
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
        result_text += (
            "\n\n---\n"
            f"[Available outputs: {'; '.join(hints)}. "
            "Tell the user they can request specific figures or tables by name if interested.]"
        )

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
}

MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))  # Increased from 10, configurable


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


async def llm_tool_loop(chat_id: int | str, user_content: str | list, user_id: str = None, platform: str = None, progress_fn=None, progress_update_fn=None) -> str:
    """
    Run the LLM tool-use loop:
    1. Append user message to history
    2. Call LLM with system prompt + history + tools
    3. If tool_calls -> execute -> append results -> call again
    4. Return final text

    progress_fn: async callable(msg) -> handle. Sends a progress message, returns a handle.
    progress_update_fn: async callable(handle, msg). Updates a previously sent progress message.
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
• Repository: https://github.com/zhou-1314/OmicsClaw

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

    # Build system prompt with memory context
    system_prompt = build_system_prompt(memory_context) if memory_context else SYSTEM_PROMPT

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

    # Sanitise: drop orphaned tool messages
    sanitised: list[dict] = []
    for msg in history:
        if msg.get("role") == "tool":
            if sanitised and sanitised[-1].get("role") == "assistant":
                if sanitised[-1].get("tool_calls"):
                    sanitised.append(msg)
                    continue
            logger.warning("Dropped orphaned tool message from history")
            continue
        sanitised.append(msg)
    history[:] = sanitised

    last_message = None
    _notified_methods: set[str] = set()  # Avoid duplicate progress messages
    for _iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await llm.chat.completions.create(
                model=OMICSCLAW_MODEL,
                max_tokens=8192,
                messages=[{"role": "system", "content": system_prompt}] + history,
                tools=TOOLS,
            )
        except APIError as e:
            logger.error(f"LLM API error: {e}")
            return f"Sorry, I'm having trouble thinking right now -- API error: {e}"

        choice = response.choices[0]
        last_message = choice.message

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
                    # Pass session_id and chat_id to omicsclaw executor
                    if func_name == "omicsclaw" and user_id and platform:
                        session_id = f"{platform}:{user_id}:{chat_id}"
                        result = await executor(func_args, session_id, chat_id=chat_id)
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
            else:
                result = f"Unknown tool: {func_name}"

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
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
