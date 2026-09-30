"""Tab completion over the slash commands, and over paths.

Skills are not slash commands, so a bare ``/`` offers the commands and
nothing else; a line whose first token is a path completes as a path.

``prompt_toolkit`` is optional (plan 0031 §9-4), so the whole module
skips when it is absent rather than turning an optional dependency into
a required one.
"""

from __future__ import annotations

import pytest

pytest.importorskip("prompt_toolkit")

from omicsclaw.entry.cli._input import build_completer  # noqa: E402
from omicsclaw.entry.cli._slash_command_support import (  # noqa: E402
    SlashCommandSpec,
)

SPECS = (
    SlashCommandSpec("/skills", "List indexed skills"),
    SlashCommandSpec("/exit", "Leave"),
)


def completions(text: str):
    from prompt_toolkit.document import Document

    completer = build_completer(specs=SPECS)
    document = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(document, None))


def offered(text: str) -> list[str]:
    """The completion texts for *text*, in the order the menu shows them."""
    return [completion.text for completion in completions(text)]


def test_a_bare_slash_offers_the_commands_and_nothing_else():
    assert offered("/") == ["/skills", "/exit"]


def test_a_prefix_narrows_the_commands():
    assert offered("/ex") == ["/exit"]
    assert offered("/spatial") == []


def test_the_default_menu_is_the_implemented_commands_only():
    """No skill names: they used to be ~94 of the entries under a bare ``/``."""
    from prompt_toolkit.document import Document

    from omicsclaw.entry.cli._slash_command_support import (
        REPL_SLASH_COMMAND_SPECS,
    )

    completer = build_completer()
    document = Document(text="/", cursor_position=1)
    texts = [c.text for c in completer.get_completions(document, None)]

    assert texts == [spec.name for spec in REPL_SLASH_COMMAND_SPECS]


def test_a_completion_replaces_the_whole_token():
    """A candidate carries its slash, so it must delete the typed one too."""
    assert [c.start_position for c in completions("/ex")] == [-len("/ex")]


def test_the_retired_run_command_completes_nothing():
    """``/run`` was the deleted skill runner's; offering names for it lied."""
    assert offered("/run ") == []


def test_a_command_carries_its_description():
    metas = {c.text: c.display_meta_text for c in completions("/")}

    assert metas["/skills"] == "List indexed skills"


def accepted(text: str) -> list[str]:
    """What the line reads as after accepting each completion offered."""
    return [
        text[: len(text) + completion.start_position] + completion.text
        for completion in completions(text)
    ]


def test_a_path_typed_at_the_start_of_the_line_completes_as_a_path(tmp_path):
    """``/data/ru`` is a path, and the command branch must let it through."""
    (tmp_path / "run7").mkdir()

    assert f"{tmp_path}/run7" in accepted(f"{tmp_path}/ru")


def test_accepting_a_path_completion_keeps_the_rest_of_the_line(tmp_path):
    """The completion extends the word; it used to replace it with the tail."""
    (tmp_path / "run7").mkdir()

    assert accepted(f"look at {tmp_path}/ru") == [f"look at {tmp_path}/run7"]
