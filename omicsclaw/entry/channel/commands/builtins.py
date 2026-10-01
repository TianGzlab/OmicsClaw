"""The built-in slash commands, reconnected to the assembled app.

Ported from ``omicsclaw/surfaces/channels/commands/builtins.py`` for plan 0031
task D1. The registry around them crossed unchanged; these handler **bodies**
did not, and that is a port cost the plan's line count does not show: the file
was clean by the plan's ``DEAD`` grep at four module-level imports, but every
one of the fourteen handlers read something out of ``omicsclaw.runtime.agent
.state`` — a transcript store, a data directory, a provider name, a skills
table. None of those globals exists now. Each handler therefore reads the same
fact off :class:`~omicsclaw.entry.assembly.AgentApp`, which is where the
assembled deployment actually lives.

**Two commands are gone rather than reconnected**, because what they did
belongs to a step that has not happened:

``/forget``
    Cleared the conversation *and* deleted its graph memory. The memory layer
    is plan 0031 Q23 family ③ and is not in this step. A ``/forget`` that
    silently did only half of that would be a lie told to somebody who asked
    for a complete reset, which is the one moment they are entitled to believe
    the answer.

``/plan``
    Read ``plan.md`` from a pipeline workspace. Plan mode is blocked for this
    step (plan 0031 §5.1) and the field it read left with it.

:func:`~omicsclaw.entry.channel.commands._registry.registered_commands` is the
list of what survived, and ``/help`` is generated from nothing else — a help
text that advertises a command the dispatcher does not have is the same defect
as the missing command, delivered personally.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from omicsclaw.context import CompactionRecord, CompactionState

from ...project import recent_modules
from ...session import SubmissionRefused
from ._registry import SlashCommandContext, register, registered_commands

_PROCESS_START = time.monotonic()
"""When this process came up, for ``/status``.

Monotonic rather than :func:`time.time`, which the original used: an uptime
computed from the wall clock jumps when the clock is corrected, and the number
this reports is a duration and never a date.
"""

_NO_APP = "OmicsClaw is not bound to a deployment yet, so there is nothing to report."
_NO_SESSION = "This command needs a conversation, and this message is not in one."


# ---- helpers ---------------------------------------------------------


def _data_dir(ctx: SlashCommandContext) -> Path:
    """Where a user's input files live, derived rather than configured.

    ``DATA_DIR = OMICSCLAW_DIR / "data"`` in the deleted state module
    (``HEAD:omicsclaw/runtime/agent/state.py:70``), with the workspace the
    app was assembled over standing in for the package directory.
    """
    return Path(ctx.workspace or ".") / "data"


def _output_dir(ctx: SlashCommandContext) -> Path:
    """Where analysis runs write, same derivation as :func:`_data_dir`.

    ``OUTPUT_DIR`` was ``OMICSCLAW_DIR / "output"`` unless
    ``OMICSCLAW_OUTPUT_DIR`` overrode it (same file, line 69). The override is
    not read here: plan 0031 Q8 leaves exactly one function allowed to read
    the environment, and a second reader is how two parts of one process end
    up disagreeing about where the outputs are.
    """
    return Path(ctx.workspace or ".") / "output"


# ---- conversation lifecycle -----------------------------------------


def _clear(ctx: SlashCommandContext) -> str | None:
    """Drop one conversation's history and its carried summary.

    Returns a refusal sentence, or ``None`` when it worked.

    Both fields go together: keeping
    :attr:`~omicsclaw.entry.session.Session.compaction` over a cleared history
    would leave the next exchange summarising a conversation that no longer
    exists, and the summary is the part the model would believe.

    The store is written on the next exchange, not here — the registry saves a
    session after it runs one, and reaching around it to save now would race
    the exchange that may be running in this very session.
    """
    if ctx.app is None or ctx.app.sessions is None:
        return _NO_APP
    if not ctx.session_id:
        return _NO_SESSION
    session = ctx.app.sessions.session(ctx.session_id)
    if session is None:
        return None
    session.history = ()
    session.compaction = CompactionState()
    return None


@register("/clear")
async def _cmd_clear(ctx: SlashCommandContext) -> str:
    """Clear conversation history for this chat."""
    refused = _clear(ctx)
    return refused or "Conversation history cleared."


def _describe_compaction(record: CompactionRecord) -> str:
    """One reply sentence about a manual compaction."""
    if not record.written_back:
        if record.degraded:
            return (
                "Compaction failed and the conversation was left as it was: "
                f"{record.degraded}"
            )
        return "Nothing to compact yet: the conversation is already short."
    saved = 1.0 - record.compression_ratio
    parts = [
        f"Compacted: {record.tokens_before} -> {record.tokens_after} tokens "
        f"({saved:.0%} smaller)"
    ]
    if record.summarized:
        parts.append(f"{record.summarized} messages summarized")
    if record.offloaded:
        parts.append(f"{len(record.offloaded)} tool outputs saved to files")
    return "; ".join(parts) + "."


@register("/compact")
async def _cmd_compact(ctx: SlashCommandContext) -> str:
    """Summarize this conversation now, keeping the recent messages."""
    if ctx.app is None or ctx.app.sessions is None:
        return _NO_APP
    if not ctx.session_id:
        return _NO_SESSION
    try:
        handle = await ctx.app.sessions.compact(ctx.session_id)
    except SubmissionRefused as refused:
        return f"Cannot compact now: {refused}"
    outcome = await handle.wait()
    if outcome is None or outcome.compaction is None:
        return "Compaction did not finish."
    return _describe_compaction(outcome.compaction)


@register("/new")
async def _cmd_new(ctx: SlashCommandContext) -> str:
    """Same effect as ``/clear``; phrased as a "new conversation" intent."""
    refused = _clear(ctx)
    return refused or "New conversation started."


# ---- filesystem introspection ----------------------------------------


@register("/files")
async def _cmd_files(ctx: SlashCommandContext) -> str:
    """List the first 20 entries of the data directory."""
    directory = _data_dir(ctx)
    try:
        items = [
            f"{item.name} ({item.stat().st_size / (1024 * 1024):.2f} MB)"
            for item in sorted(directory.iterdir())
            if item.is_file()
        ]
    except OSError:
        return f"No data directory yet: {directory}"
    if not items:
        return f"Data directory is empty: {directory}"
    return f"Data files ({directory}):\n" + "\n".join(items[:20])


@register("/outputs")
async def _cmd_outputs(ctx: SlashCommandContext) -> str:
    """List the 10 most recently modified analysis output directories."""
    try:
        items = [
            f"{item.name} ({_stamp(item)})" for item in _recent_runs(ctx, limit=10)
        ]
    except OSError:
        items = []
    if not items:
        return f"No analysis outputs yet: {_output_dir(ctx)}"
    return f"Recent outputs ({_output_dir(ctx)}):\n" + "\n".join(items)


@register("/recent")
async def _cmd_recent(ctx: SlashCommandContext) -> str:
    """Show the 3 most recently changed analysis modules: status and report headline."""
    modules = recent_modules(Path(ctx.workspace or "."), limit=3)
    items = [
        f"{module.name} [{(module.status or 'draft').upper()}]\n"
        f"   {datetime.fromtimestamp(module.modified).strftime('%Y-%m-%d %H:%M')} - "
        f"{module.headline or 'No report yet'}"
        for module in modules
    ]
    if not items:
        return "No recent analyses found."
    return f"Last {len(items)} analyses:\n\n" + "\n\n".join(items)


def _recent_runs(ctx: SlashCommandContext, *, limit: int) -> tuple[Path, ...]:
    """Output directories, newest first. Raises :exc:`OSError` if there are none."""
    directory = _output_dir(ctx)
    runs = sorted(
        (item for item in directory.iterdir() if item.is_dir()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return tuple(runs[:limit])


def _stamp(run: Path) -> str:
    return datetime.fromtimestamp(run.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


# ---- catalogue and status --------------------------------------------


@register("/skills")
async def _cmd_skills(ctx: SlashCommandContext) -> str:
    """List the skills this deployment actually loaded.

    ``SkillIndex.domain_summary`` rather than the full one: the same scan the
    system prompt was built from, rendered at the size a chat window can
    carry. The old handler rendered a table and fell back to plain text on
    Feishu; there is no table here to fall back from.
    """
    if ctx.app is None:
        return _NO_APP
    if ctx.app.skills.is_empty:
        return "No skills are loaded in this deployment."
    return ctx.app.skills.domain_summary()


@register("/status")
async def _cmd_status(ctx: SlashCommandContext) -> str:
    """Uptime and what this deployment was assembled with."""
    uptime = int(time.monotonic() - _PROCESS_START)
    hours, remainder = divmod(uptime, 3600)
    minutes = remainder // 60
    lines = [f"Uptime: {hours}h {minutes}m"]
    if ctx.app is None:
        lines.append(_NO_APP)
        return "\n".join(lines)
    app = ctx.app
    running = len(app.sessions.running()) if app.sessions is not None else 0
    lines += [
        f"Provider: {app.provider.name}",
        f"Model: {app.config.model or 'provider default'}",
        f"Tools available: {len(app.tools_snapshot)}",
        f"Skills loaded: {len(app.skills)}",
        f"Exchanges running: {running}",
        f"Workspace: {app.config.workspace}",
    ]
    return "\n".join(lines)


@register("/version")
async def _cmd_version(ctx: SlashCommandContext) -> str:
    """What this build is, counted from the deployment rather than prose."""
    skills = len(ctx.app.skills) if ctx.app is not None else 0
    tools = len(ctx.app.tools_snapshot) if ctx.app is not None else 0
    return (
        "OmicsClaw Multi-Omics Analysis Platform\n"
        "Domains: spatial, single-cell, genomics, proteomics, metabolomics, "
        "bulk RNA-seq\n"
        f"Skills: {skills}\n"
        f"Tools: {tools}\n"
        "Repository: https://github.com/TianGzlab/OmicsClaw"
    )


# ---- static text ------------------------------------------------------


@register("/demo")
async def _cmd_demo(ctx: SlashCommandContext) -> str:
    return (
        "Quick demo options. Ask for any of these in plain words:\n"
        '- "run spatial-preprocess demo"\n'
        '- "run spatial-domain-identification demo"\n'
        '- "run spatial-de demo"\n'
        '- "run proteomics-ms-qc demo"'
    )


@register("/examples")
async def _cmd_examples(ctx: SlashCommandContext) -> str:
    return (
        "Usage examples:\n\n"
        "Literature\n"
        '- "Parse this paper: https://pubmed.ncbi.nlm.nih.gov/12345"\n'
        '- "Fetch GEO metadata for GSE204716"\n\n'
        "Analysis\n"
        '- "Run spatial-preprocess on brain_visium.h5ad"\n'
        '- "Run proteomics-ms-qc on proteomics_data.mzML"\n\n'
        "Files\n"
        '- "List files in the data directory"\n'
        '- "Show the first 20 lines of results.csv"'
    )


@register("/help")
async def _cmd_help(ctx: SlashCommandContext) -> str:
    """List exactly the commands that are registered, and nothing else.

    Generated rather than written out, because the handwritten version it
    replaces advertised ``/forget`` and ``/plan``, which this port removed.
    A help text is the one place where a stale list is read by the person it
    misleads.
    """
    names = "\n".join(f"- {name}" for name in registered_commands())
    return (
        "OmicsClaw commands:\n"
        f"{names}\n\n"
        "Anything else is sent to the agent. OmicsClaw is a research tool, "
        "not a medical device; consult a domain expert before making "
        "decisions based on these results."
    )
