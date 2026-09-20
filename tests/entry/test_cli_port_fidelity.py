"""What was moved is the same as what it was moved from.

Plan 0031 §9-13 makes "ported rather than rewritten" an acceptance
criterion, and a line count is not evidence of it — a file can be counted
as moved and still have been retyped wrong. These tests compare the
ported data and the ported behaviour against the originals in
``omicsclaw/surfaces/cli/``, which are still on disk and still importable
for exactly the three modules this package took whole.

They also pin the **boundary**: the modules plan 0031 §5.1 called "strictly
clean" that are not, each named with the import that makes it not. That
half is the part a reader of the plan needs most, because the plan's table
is the thing they will otherwise believe.
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

from omicsclaw.entry.cli import _constants as ported_constants
from omicsclaw.entry.cli import _markdown, _session_state
from omicsclaw.entry.cli import _slash_command_support as ported_slash
from omicsclaw.surfaces.cli import _constants as origin_constants
from omicsclaw.surfaces.cli import _session_state as origin_state
from omicsclaw.surfaces.cli import _slash_command_support as origin_slash

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ORIGIN = _REPO_ROOT / "omicsclaw" / "surfaces" / "cli"


# ---- the data came across unchanged ----------------------------------


def test_the_logo_survived_being_split_across_source_lines():
    """The one port that had to be re-typed, checked character by character.

    Each row is 74 characters of box drawing, three bytes per character,
    so one row on one source line is ~200 bytes and §9-3's byte-counting
    ``awk`` refuses it. Splitting each row into three adjacent literals is
    the only change, and this is what makes that claim checkable rather
    than asserted.
    """
    assert ported_constants.LOGO_LINES == origin_constants.LOGO_LINES
    assert {len(row) for row in ported_constants.LOGO_LINES} == {74}


def test_the_command_catalogue_came_across_whole():
    """All thirty-eight rows, including the ones this build cannot run.

    Deleting the blocked families' rows would mean retyping them when
    those steps land; see ``_constants.py``'s module docstring.
    """
    assert ported_constants.SLASH_COMMANDS == origin_constants.SLASH_COMMANDS
    assert ported_constants.WELCOME_SLOGANS == origin_constants.WELCOME_SLOGANS
    assert ported_constants.LOGO_GRADIENT == origin_constants.LOGO_GRADIENT


@pytest.mark.parametrize(
    "line",
    [
        "/help",
        "/exit",
        "/quit",
        "/q",
        "/run spatial-preprocess --demo",
        "/skills spatial",
        "not a command at all",
        "",
        "  /HELP  ",
    ],
)
def test_the_parser_answers_exactly_as_the_original_did(line: str):
    """Behavioural equality, not textual: the point of a port is the answer.

    Parametrized over the shapes the original's callers relied on —
    aliases, an argument, a leading space, a non-command — because a
    re-typed lookup table is wrong in exactly one of them.
    """
    ported = ported_slash.parse_slash_command(
        line, ported_slash.CLI_SLASH_COMMAND_SPECS
    )
    origin = origin_slash.parse_slash_command(
        line, origin_slash.CLI_SLASH_COMMAND_SPECS
    )
    assert (ported is None) == (origin is None)
    if ported is not None and origin is not None:
        assert (ported.name, ported.arg, ported.token) == (
            origin.name,
            origin.arg,
            origin.token,
        )


def test_the_repl_offers_a_subset_of_the_catalogue_and_nothing_else():
    """§9-18's shape, applied to a menu rather than to imports.

    Every implemented name must exist in the catalogue it was filtered
    from; a name here that is not there would be a command invented during
    the move, which is the failure mode "port" is supposed to exclude.
    """
    catalogue = {spec.name for spec in ported_slash.CLI_SLASH_COMMAND_SPECS}
    offered = {spec.name for spec in ported_slash.REPL_SLASH_COMMAND_SPECS}

    assert offered < catalogue
    assert offered  # a filter that matched nothing would pass vacuously


def test_the_session_state_dataclass_kept_its_fields():
    """Including ``pipeline_workspace``, which this build never sets.

    The blocked families' fields are carried rather than deleted for the
    reason the catalogue is; asserting they are still here is what stops
    a later tidy-up from quietly making the next step's port a rewrite.
    """
    ported_fields = {
        name: field.type
        for name, field in _session_state.SessionState.__dataclass_fields__.items()
    }
    origin_fields = {
        name: field.type
        for name, field in origin_state.SessionState.__dataclass_fields__.items()
    }

    assert ported_fields == origin_fields


def test_the_markdown_regexes_are_the_ones_interactive_py_compiled():
    """``interactive.py`` cannot be imported, so compare its source text.

    It imports ``omicsclaw.control``, which this rebuild deleted — the
    reason the file is an input to this step rather than a dependency of
    it. Its regex block is still readable, and a re-typed character class
    is the sort of defect that only shows up on the one input nobody
    tried.
    """
    source = (_ORIGIN / "interactive.py").read_text(encoding="utf-8")
    # Join adjacent string literals, so a pattern written over six source
    # lines compares against the one string the compiler built from them.
    joined = re.sub(r'"\s*\n\s*r?"', "", source)

    for pattern in (
        _markdown._STRONG_LINE_RE,
        _markdown._ATX_HEADING_RE,
        _markdown._BULLET_LINE_RE,
        _markdown._NUMBERED_LINE_RE,
        _markdown._BLOCKQUOTE_LINE_RE,
        _markdown._INLINE_MARKDOWN_TOKEN_RE,
        _markdown._UNCERTAIN_MARKDOWN_PREFIX_RE,
        _markdown._MARKDOWN_LINE_START_RE,
    ):
        assert pattern.pattern in joined, pattern.pattern


# ---- where the plan's port list was wrong ----------------------------


@pytest.mark.parametrize(
    "module",
    [
        "_style_support",
        "_diagnostics_support",
        "_interpret_command_support",
        "_mcp",
        "_session",
        "tui",
        "interactive",
    ],
)
def test_the_modules_that_were_not_ported_cannot_be_imported_today(module: str):
    """Why each omission is an omission and not an oversight.

    Plan 0031 §5.1 calls the first four "strictly clean" and gives
    ``tui.py`` as nine lines of re-plumbing. None of the seven imports at
    all in this working tree: each reaches, directly or through one
    sibling, a package this rebuild deleted. Porting one as it stands
    would turn ``test_entry_is_the_top_layer.py::
    test_no_entry_module_names_a_replaced_package`` red, and porting it
    without that import would mean writing its dependency from scratch —
    which is the rewrite §9-13 is there to prevent.

    Behavioural rather than a grep: the failure is often **transitive**
    (``tui.py`` names no deleted package itself; its
    ``_llm_bridge_support`` sibling does), and a source scan of one file
    cannot see that.

    This test fails the day one of them is cleaned up, which is the right
    time to revisit the omission.
    """
    with pytest.raises(ModuleNotFoundError) as caught:
        importlib.import_module(f"omicsclaw.surfaces.cli.{module}")

    assert str(caught.value.name or "").startswith("omicsclaw.")
    assert not (_REPO_ROOT / "omicsclaw" / "entry" / "cli" / f"{module}.py").exists()
