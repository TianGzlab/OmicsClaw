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
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Module-level state (initialised by init())
# ---------------------------------------------------------------------------

llm: AsyncOpenAI | None = None
OMICSCLAW_MODEL: str = "deepseek-chat"
LLM_PROVIDER_NAME: str = ""

conversations: dict[int | str, list] = {}
MAX_HISTORY = 20

received_files: dict[int | str, dict] = {}
pending_media: dict[int | str, list[dict]] = {}
pending_text: list[str] = []

BOT_START_TIME = time.time()


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
    global llm, OMICSCLAW_MODEL, LLM_PROVIDER_NAME

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
5. TOOL OUTPUT RELAY (STRICT): When the omicsclaw tool returns results, relay
   the output VERBATIM. Do not paraphrase, summarise, or rewrite. The output
   contains precise numerical data that must not be altered. You may add a brief
   intro line but never replace or condense the tool output.
6. For uploaded data or visual evidence, suggest appropriate OmicsClaw analysis skills.
7. For quick demos: say "run preprocess demo", "run ms-qc demo", etc.
   Use mode='demo' to run with built-in synthetic data.
8. FILE PATH MODE (IMPORTANT): Omics data files are often too large to upload
   via messaging. When the user mentions a file path or filename, use mode='path'
   and set file_path to the path or filename they provided. The system will automatically search
   trusted directories.
   Examples:
   - User: "分析 data/brain_visium.h5ad" → mode='path', file_path='data/brain_visium.h5ad'
   - User: "run preprocess on my_data.h5ad" → mode='path', file_path='my_data.h5ad'
   - User: "对 /mnt/nas/exp1.mzML 做质量控制" → mode='path', file_path='/mnt/nas/exp1.mzML', skill='ms-qc'
"""

def build_system_prompt() -> str:
    if SOUL_MD.exists():
        soul = SOUL_MD.read_text(encoding="utf-8")
        logger.info(f"Loaded SOUL.md ({{len(soul)}} chars)")
    else:
        soul = (
            "You are a multi-omics AI assistant. "
            "Help users analyse multi-omics data with clarity and rigour."
        )
        logger.warning("SOUL.md not found, using fallback prompt")
    return f"{soul}\n\n{get_role_guardrails()}"

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
                    "IMPORTANT: When this tool returns results, relay the output VERBATIM."
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
                "description": "Create or overwrite a file on the filesystem with the given content.",
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


def resolve_dest(folder: str | None) -> Path:
    dest = Path(folder) if folder else DATA_DIR
    if not dest.is_absolute():
        dest = OMICSCLAW_DIR / dest
    try:
        dest.resolve().relative_to(OMICSCLAW_DIR.resolve())
    except ValueError:
        logger.warning(f"Path escape blocked: {dest}")
        audit("security", severity="HIGH", detail="path_escape_blocked", attempted_path=str(dest))
        dest = DATA_DIR
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
        for d in TRUSTED_DATA_DIRS:
            candidate = d / p
            if candidate.exists() and candidate.is_file():
                p = candidate
                break
        else:
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

    logger.warning(f"Path not in trusted dirs: {resolved}")
    audit("security", severity="MEDIUM", detail="untrusted_path_rejected", path=str(resolved))
    return None


def discover_file(filename_or_pattern: str) -> list[Path]:
    """Search trusted data directories for files matching the given name or glob pattern.

    Returns a list of matching paths, sorted by modification time (newest first).
    """
    _ensure_trusted_dirs()
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


async def execute_omicsclaw(args: dict) -> str:
    """Execute an OmicsClaw skill via subprocess."""
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

    if not input_path:
        for _cid, info in received_files.items():
            input_path = info.get("path")
            session_path = info.get("session_path")
            break

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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / f"{skill_key}_{ts}"

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

    extra_args = args.get("extra_args")
    if extra_args and isinstance(extra_args, list):
        cmd.extend(extra_args)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=300,
        )
        stdout_str = stdout_bytes.decode(errors="replace")
        stderr_str = stderr_bytes.decode(errors="replace")
    except asyncio.TimeoutError:
        return f"{skill_key} timed out after 300 seconds."
    except Exception as e:
        import traceback as _tb
        return f"{skill_key} crashed:\n{_tb.format_exc()[-1500:]}"

    if proc.returncode != 0:
        err = stderr_str[-1500:] if stderr_str else stdout_str[-1500:] if stdout_str else "unknown error"
        return f"{skill_key} failed (exit {proc.returncode}):\n{err}"

    # Collect report + figures from output directory
    if out_dir.exists():
        media_items = []
        for f in sorted(out_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix in (".md", ".html"):
                media_items.append({"type": "document", "path": str(f)})
            elif f.suffix == ".png":
                media_items.append({"type": "photo", "path": str(f)})
        if media_items:
            pending_media[0] = pending_media.get(0, []) + media_items

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

    return "\n".join(keep_lines).strip()


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

    dest = resolve_dest(args.get("destination_folder"))
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
# Tool executor registry
# ---------------------------------------------------------------------------

TOOL_EXECUTORS = {
    "omicsclaw": execute_omicsclaw,
    "save_file": execute_save_file,
    "write_file": execute_write_file,
    "generate_audio": execute_generate_audio,
}

MAX_TOOL_ITERATIONS = 10


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------


async def llm_tool_loop(chat_id: int | str, user_content: str | list) -> str:
    """
    Run the LLM tool-use loop:
    1. Append user message to history
    2. Call LLM with system prompt + history + tools
    3. If tool_calls -> execute -> append results -> call again
    4. Return final text
    """
    _ensure_system_prompt()
    if llm is None:
        return "Error: LLM client not initialised. Call core.init() first."

    history = conversations.setdefault(chat_id, [])

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
    for _iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await llm.chat.completions.create(
                model=OMICSCLAW_MODEL,
                max_tokens=8192,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
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
                try:
                    result = await executor(func_args)
                except Exception as tool_err:
                    logger.error(f"Tool {func_name} raised: {tool_err}", exc_info=True)
                    audit("tool_error", chat_id=str(chat_id), tool=func_name,
                          error=str(tool_err)[:300])
                    result = f"Error executing {func_name}: {type(tool_err).__name__}: {tool_err}"
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
    """Remove markdown/emoji formatting for plain-text messaging."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*]\s+", "", text, flags=re.MULTILINE)
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
