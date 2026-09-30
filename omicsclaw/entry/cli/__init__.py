"""OmicsClaw's terminal surface: one prompt, one conversation, one process.

Plan 0031 task D3, and the third of the three surfaces to be ported onto
:mod:`omicsclaw.entry`. Run it::

    oc cli
    oc cli --workspace /data --session run-7
    oc cli --prompt-file brief.md
    oc cli --configure

**This package is a library and not a process.** It used to carry a
``__main__.py``; plan 0037 moved that responsibility up into
:mod:`omicsclaw.launch`, so that all three facades have the same shape
and this package stops being the only one that also reads a command
line. ``python -m omicsclaw.entry.cli`` is **not** kept as an alias —
plan 0037 §6: it is exactly the kind of entry point the redesign
removes, and an alias would keep it.

**This package is a port, and a smaller one than plan 0031 §5.1
projected.** Its input was ``omicsclaw/surfaces/cli/`` — 26 files, 14,936
lines — which has since been **deleted**, once the REPL's own behaviour
was covered directly rather than by comparison against it. What follows
is therefore a record rather than a reading guide: the tree it describes
is in ``git log``, not on disk, and this is the only place the reasoning
survives. The plan's reading of that tree turned out to be optimistic in
a way that is worth keeping, because the next person to read §5.1's table
will make the same estimate:

*The eight "strictly clean" modules are five.* ``_style_support`` imports
``omicsclaw.runtime.output_styles``, ``_diagnostics_support`` imports
``omicsclaw.diagnostics`` (deleted), and ``_interpret_command_support``
imports ``omicsclaw.routing``. All three already failed to import at the
time of the port, and two of the three named packages that
``tests/entry/test_entry_is_the_top_layer.py`` forbids any file here to
name. ``_history_support`` did import, and formatted a *research
pipeline*'s history — the family §5.1 blocks.

*``_mcp.py`` is not clean either* (it imports ``omicsclaw.skill``, the
deleted singular package), and it manages a second MCP configuration —
``~/.config/omicsclaw/mcp.yaml``, over ``langchain_mcp_adapters`` — while
this deployment already connects its servers from ``.mcp.json`` through
:mod:`omicsclaw.mcp` in :func:`~omicsclaw.entry.assembly.open_app`. Two
managers over two files is worse than one management UI fewer, so
``/mcp`` here reports the live manager and the module was not ported.

*``_session.py`` is a persistence layer*, not a session-command module:
its one blocked import pulls ``build_transcript_summary`` and
``sanitize_tool_history`` out of a deleted 584-line file, and ``aiosqlite``
is not installed here. It was not ported, and conversations are persisted
anyway — by :mod:`omicsclaw.memory`, which
:func:`~omicsclaw.entry.session.attach_sessions` reaches through a
Protocol. ``/sessions`` and ``/resume`` are this surface's half of that,
written against the registry rather than revived from the old module.

*``tui.py`` could not be re-plumbed by changing three imports.* It imports
nine blocked support modules at module scope and roughly half of
``OmicsClawTUI``'s methods are handlers for the blocked families. There is
no Textual TUI in this package; §1.3 already puts the TUI after the REPL
("the harness's own order") and this is what that ordering costs.

**What is here.** :class:`~omicsclaw.entry.cli._repl.Repl` — the loop,
with the input source as a parameter (``cli.go:36``) — over the ported
REPL shell: the command catalogue and its parser, the ASCII banner, the
streaming Markdown renderer, the completer, the typed session state.

**No optional dependency is imported at module scope** (plan 0031 trap
13). ``prompt_toolkit`` is imported inside
:func:`~omicsclaw.entry.cli._input.open_prompt_source`, in plainly visible
``import`` syntax, and a deployment without it degrades to reading lines
from the stream rather than failing — which is also the path a pipe and
``--prompt-file`` take.
"""

from ._auto import CLI_PERMISSION_MODE_VARIABLE
from ._configure import missing_credential_hint, run_configuration_wizard
from ._input import (
    PromptSource,
    PromptToolkitSource,
    ScriptedSource,
    StreamSource,
    open_prompt_source,
)
from ._markdown import MarkdownStreamFormatter
from ._repl import PROMPT, Repl, run_once
from ._screen import Screen, terminal_owned_logging
from ._session_state import SessionState
from ._slash_command_support import (
    CLI_SLASH_COMMAND_SPECS,
    REPL_SLASH_COMMAND_SPECS,
    SlashCommandMatch,
    SlashCommandSpec,
    parse_slash_command,
)

__all__ = [
    "CLI_PERMISSION_MODE_VARIABLE",
    "CLI_SLASH_COMMAND_SPECS",
    "PROMPT",
    "MarkdownStreamFormatter",
    "PromptSource",
    "PromptToolkitSource",
    "REPL_SLASH_COMMAND_SPECS",
    "Repl",
    "Screen",
    "ScriptedSource",
    "SessionState",
    "SlashCommandMatch",
    "SlashCommandSpec",
    "StreamSource",
    "missing_credential_hint",
    "open_prompt_source",
    "parse_slash_command",
    "run_configuration_wizard",
    "run_once",
    "terminal_owned_logging",
]
