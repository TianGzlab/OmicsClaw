"""The 14 built-in slash commands carved out of
``bot/agent_loop.py:llm_tool_loop`` (Phase 1 P0-E, Task #8).

Each handler is registered via ``@register("/foo")`` so the
dispatcher in ``_registry.py`` finds it by name. Behaviour is a
faithful port of the pre-refactor if-elif chain — the test
``tests/bot/test_commands_registry.py::test_all_legacy_commands_registered``
pins the full set so future refactors cannot silently drop one.

The handlers reach into ``bot.core`` / ``bot.tool_executors`` /
``omicsclaw.runtime.context_compaction`` directly because they are
themselves bot-side code; only request-scoped values arrive via
``SlashCommandContext``.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import bot.core as _core
from bot.core import (
    BOT_START_TIME,
    DATA_DIR,
    OUTPUT_DIR,
    _primary_skill_count,
    format_skills_table,
    transcript_store,
    tool_result_store,
)
from bot.tool_executors import get_tool_executors

from ._registry import SlashCommandContext, register


# ── Conversation lifecycle ──────────────────────────────────────────


@register("/clear")
async def _cmd_clear(ctx: SlashCommandContext) -> str:
    """Clear conversation history; keep graph memory intact."""
    transcript_store.clear(ctx.chat_id)
    tool_result_store.clear(ctx.chat_id)
    return "✓ Conversation history cleared. (Memory preserved)"


@register("/new")
async def _cmd_new(ctx: SlashCommandContext) -> str:
    """Same effect as ``/clear``; phrased as a "new conversation" intent."""
    transcript_store.clear(ctx.chat_id)
    tool_result_store.clear(ctx.chat_id)
    return "✓ New conversation started. (Memory preserved)"


@register("/forget")
async def _cmd_forget(ctx: SlashCommandContext) -> str:
    """Clear conversation + delete the session's graph memory."""
    transcript_store.clear(ctx.chat_id)
    tool_result_store.clear(ctx.chat_id)

    if _core.session_manager and ctx.user_id and ctx.platform:
        session_id = f"{ctx.platform}:{ctx.user_id}:{ctx.chat_id}"
        await _core.memory_store.delete_session(session_id)

    return "✓ Memory and conversation cleared. (Fresh start)"


# ── Workspace + plan introspection ──────────────────────────────────


@register("/plan")
async def _cmd_plan(ctx: SlashCommandContext) -> str:
    """Show ``plan.md`` from the active pipeline / workspace dir."""
    candidate_dirs: list[Path] = []
    for raw in (ctx.pipeline_workspace, ctx.workspace):
        if raw:
            candidate_dirs.append(Path(str(raw)))

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


@register("/compact")
async def _cmd_compact(ctx: SlashCommandContext) -> str:
    """Deterministically rebuild the persisted transcript using the
    template-based collapse logic — no LLM call. Tracked as a
    boundary so subsequent /compact calls only summarise the new
    tail."""
    from omicsclaw.runtime.context_compaction import (
        ContextCompactionConfig,
        compact_history,
        is_compaction_summary_message,
        unwrap_compaction_summary,
        wrap_compaction_summary,
    )

    history = transcript_store.get_history(ctx.chat_id)
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
        workspace=ctx.workspace or ctx.pipeline_workspace or None,
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
    transcript_store.replace_history(ctx.chat_id, new_history)
    return (
        f"✓ Compacted {result.omitted_count} earlier message(s); "
        f"kept the most recent {len(result.messages)}. "
        "Summary preserved as a system note."
    )


# ── Filesystem introspection ────────────────────────────────────────


@register("/files")
async def _cmd_files(ctx: SlashCommandContext) -> str:
    """List the first 20 entries of the data directory."""
    try:
        items = []
        for item in sorted(DATA_DIR.iterdir()):
            if item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                items.append(f"📄 {item.name} ({size_mb:.2f} MB)")
        if not items:
            return f"📁 Data directory is empty: {DATA_DIR}"
        return f"📁 Data files ({DATA_DIR}):\n" + "\n".join(items[:20])
    except Exception as e:
        return f"Error listing files: {e}"


@register("/outputs")
async def _cmd_outputs(ctx: SlashCommandContext) -> str:
    """List the 10 most recently modified analysis output dirs."""
    try:
        items = []
        if OUTPUT_DIR.exists():
            for item in sorted(
                OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
            ):
                if item.is_dir():
                    mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    items.append(f"📊 {item.name} ({mtime})")
        if not items:
            return f"📂 No analysis outputs yet: {OUTPUT_DIR}"
        return f"📂 Recent outputs ({OUTPUT_DIR}):\n" + "\n".join(items[:10])
    except Exception as e:
        return f"Error listing outputs: {e}"


@register("/recent")
async def _cmd_recent(ctx: SlashCommandContext) -> str:
    """Show the last 3 analyses with their report.md headlines."""
    try:
        items = []
        if OUTPUT_DIR.exists():
            for item in sorted(
                OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
            )[:3]:
                if item.is_dir():
                    mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    report = item / "report.md"
                    summary = "No report"
                    if report.exists():
                        lines = report.read_text(encoding="utf-8").split("\n")
                        summary = next(
                            (line.strip("# ") for line in lines if line.startswith("# ")),
                            "Analysis complete",
                        )
                    items.append(f"📊 {item.name}\n   {mtime} - {summary}")
        if not items:
            return "📂 No recent analyses found"
        return "📂 Last 3 Analyses:\n\n" + "\n\n".join(items)
    except Exception as e:
        return f"Error: {e}"


# ── Catalog / capabilities ──────────────────────────────────────────


@register("/skills")
async def _cmd_skills(ctx: SlashCommandContext) -> str:
    """Render the skills table; fall back to plain text on Feishu
    where rich tables don't render well."""
    return format_skills_table(plain=(ctx.platform == "feishu"))


# ── Static text replies ─────────────────────────────────────────────


@register("/demo")
async def _cmd_demo(ctx: SlashCommandContext) -> str:
    return """🎬 Quick Demo Options:

Run any of these for instant results:
• "run spatial-preprocess demo"
• "run spatial-domain-identification demo"
• "run spatial-de demo"
• "run proteomics-ms-qc demo"

Or try: "show me a spatial transcriptomics demo" """


@register("/examples")
async def _cmd_examples(ctx: SlashCommandContext) -> str:
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


# ── Dynamic info ────────────────────────────────────────────────────


@register("/status")
async def _cmd_status(ctx: SlashCommandContext) -> str:
    uptime = int(time.time() - BOT_START_TIME)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    return f"""🤖 Bot Status:

• Uptime: {hours}h {minutes}m
• LLM Provider: {_core.LLM_PROVIDER_NAME}
• Model: {_core.OMICSCLAW_MODEL}
• Active Conversations: {transcript_store.active_conversation_count}
• Tools Available: {len(get_tool_executors())}
• Skills Loaded: {_primary_skill_count()}
• Data Directory: {DATA_DIR}
• Output Directory: {OUTPUT_DIR}"""


@register("/version")
async def _cmd_version(ctx: SlashCommandContext) -> str:
    return f"""ℹ️ OmicsClaw Version:

• Project: OmicsClaw Multi-Omics Analysis Platform
• Domains: Spatial Transcriptomics, Single-Cell, Genomics, Proteomics, Metabolomics
• Skills: {_primary_skill_count()} analysis skills
• Tools: {len(get_tool_executors())} bot tools
• Repository: https://github.com/TianGzlab/OmicsClaw

For updates and documentation, visit the GitHub repository."""


@register("/help")
async def _cmd_help(ctx: SlashCommandContext) -> str:
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
