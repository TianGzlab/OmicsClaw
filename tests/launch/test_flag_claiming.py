"""Which half of the command line owns which flag (plan 0048).

``oc cli --configure`` used to be refused by ``resolve_app_config`` as an
unknown deployment flag, and then answered with the surface usage that
lists ``--configure``. The fix is not an exception to the cut in
``split_command_line`` —— that function is unchanged —— but a statement
about ownership: a surface takes its own flags out of the deployment
half, wherever they were typed, because the two flag families are
disjoint and a flag's owner therefore does not depend on which side of
``--`` it landed on.

Two properties are worth more than the rest of this file:

*The walk is the deployment's walk.* :func:`flag_stride` is shared with
``_grammar``'s help hoist and mirrors ``config.py``'s ``_from_argv``, so
no token can be a flag to one reader and a value to the other.

*The tables cannot drift from the parsers.* The three surfaces keep
hand-written parsers on purpose, so the arity tables they publish are
checked against them by probing, not by review.
"""

from __future__ import annotations

import pytest

from omicsclaw.entry.config import AppConfigError
from omicsclaw.launch._surfaces import (
    CHANNEL_FLAGS,
    CLI_FLAGS,
    DESKTOP_FLAGS,
    ChannelOptions,
    DesktopOptions,
    ReplOptions,
    _claim_surface_flags,
    flag_stride,
)
from tests.launch.test_launch_is_above_entry import (  # type: ignore[import-not-found]
    SHELL_FLAGS,
)

SURFACES = (
    (CLI_FLAGS, ReplOptions),
    (DESKTOP_FLAGS, DesktopOptions),
    (CHANNEL_FLAGS, ChannelOptions),
)


# ---- the claim --------------------------------------------------------


@pytest.mark.parametrize(
    ("deployment", "kept", "claimed"),
    [
        (["--configure"], [], ["--configure"]),
        (["--session", "run-7"], [], ["--session", "run-7"]),
        (
            ["--workspace", "/data", "--configure"],
            ["--workspace", "/data"],
            ["--configure"],
        ),
        (["--session=run-7"], [], ["--session", "run-7"]),
        ([], [], []),
    ],
)
def test_this_surfaces_flags_are_taken_with_their_values(
    deployment, kept, claimed
):
    assert _claim_surface_flags(deployment, CLI_FLAGS) == (kept, claimed)


def test_a_flag_in_value_position_is_not_claimed():
    """``--configure`` here is the workspace's name, absurd as that is.

    The same ruling as ``test_a_help_flag_that_is_a_value_is_not_hoisted``
    and for the same reason: claiming it would leave ``--workspace
    /data``, a *different, well-formed* deployment plus a wizard, from a
    command line that is not well formed at all.
    """
    line = ["--workspace", "--configure", "/data"]

    assert _claim_surface_flags(line, CLI_FLAGS) == (line, [])


def test_an_empty_inline_value_does_not_end_its_flag():
    """``--workspace=`` goes on to eat the next token, as ``_from_argv`` does.

    The discriminating case for :func:`flag_stride`. A walk written as
    ``"=" in token`` —— which is what ``_grammar`` used to carry —— reads
    ``--configure`` below as a flag and claims it, while
    ``resolve_app_config`` reads it as the workspace's name: one command
    line, two answers. ``--workspace=/data`` cannot tell the two walks
    apart, which is why this case is here.
    """
    line = ["--workspace=", "--configure"]

    assert _claim_surface_flags(line, CLI_FLAGS) == (line, [])
    assert flag_stride(line, 0) == 1 + 1


def test_an_unknown_flag_keeps_its_value_and_its_refusal():
    """Claiming may not know the deployment's flags, and does not need to.

    An unknown flag is strided past rather than refused here, so
    ``--configure`` below stays the value of ``--bogus`` and the whole
    line reaches ``resolve_app_config``, which refuses the flag the user
    actually mistyped.
    """
    line = ["--bogus", "--configure"]

    assert _claim_surface_flags(line, CLI_FLAGS) == (line, [])


def test_nothing_here_raises():
    """A missing value is refused by the parser, in its own words.

    Claiming a flag without its value and letting ``ReplOptions.parse``
    say so keeps one wording of that refusal instead of two.
    """
    kept, claimed = _claim_surface_flags(["--session"], CLI_FLAGS)

    assert (kept, claimed) == ([], ["--session"])
    with pytest.raises(AppConfigError, match="needs a value"):
        ReplOptions.parse(claimed)


def test_a_terminator_stops_the_claim():
    """Unreachable through ``main``, defined anyway.

    ``split_command_line`` cuts at the first ``--``, so a deployment half
    never contains one; this function is called directly by the tests
    above, and a walk whose behaviour is undefined for an input it can be
    given is a walk that will be given it.
    """
    line = ["--configure", "--", "--session", "x"]

    kept, claimed = _claim_surface_flags(line, CLI_FLAGS)

    assert claimed == ["--configure"]
    assert kept == ["--", "--session", "x"]


# ---- the two halves, once they are one line again ---------------------


def test_the_explicit_spelling_wins_when_a_flag_is_given_twice():
    """Claimed flags are parsed first, so the half after ``--`` wins."""
    kept, claimed = _claim_surface_flags(["--session", "a"], CLI_FLAGS)
    options = ReplOptions.parse([*claimed, "--session", "b"])

    assert kept == []
    assert options.session_id == "b"


@pytest.mark.parametrize(
    "argv",
    [
        ["--session=run-7"],
        ["--session", "run-7"],
    ],
)
def test_the_inline_spelling_means_the_same_on_both_sides(argv):
    """One spelling, one answer, whichever side of ``--`` it was typed on."""
    _kept, claimed = _claim_surface_flags(argv, CLI_FLAGS)

    assert ReplOptions.parse(claimed).session_id == "run-7"
    assert ReplOptions.parse(argv).session_id == "run-7"


@pytest.mark.parametrize("flag", ["--configure", "--show-reasoning"])
def test_a_flag_that_takes_no_value_refuses_one(flag):
    with pytest.raises(AppConfigError, match="takes no value"):
        ReplOptions.parse([f"{flag}=yes"])


# ---- the tables agree with the parsers --------------------------------


def _arity(parser, flag: str) -> int | None:
    """What *parser* thinks *flag* is, read from the parser itself.

    ``None`` means it does not own the flag. A flag that takes a value
    refuses a line consisting of only itself; one that does not, parses.
    ``--prompt-file`` is safe to probe this way because its missing-value
    check runs before it opens anything.
    """
    try:
        parser.parse([flag])
    except AppConfigError as refusal:
        if "unknown surface option" in str(refusal):
            return None
        if "needs a value" in str(refusal):
            return 1
        raise
    return 0


@pytest.mark.parametrize(("table", "parser"), SURFACES)
def test_the_flag_table_matches_the_parser(table, parser):
    """Every flag this shell knows of, asked of every parser.

    ``SHELL_FLAGS`` is the enumeration source because it is finite and
    pinned: ``test_the_flags_the_shell_acts_on_are_exactly_these``
    asserts it equals the flag literals in the package. So a new surface
    flag turns that test red until it is added there, and this one red
    until it is registered in its surface's table —— which is the drift
    the table could otherwise develop in silence.
    """
    found = {
        flag: _arity(parser, flag)
        for flag in sorted(SHELL_FLAGS - {"--"})
        if _arity(parser, flag) is not None
    }

    assert found == dict(table)


@pytest.mark.parametrize(("table", "_parser"), SURFACES)
def test_every_table_is_read_only(table, _parser):
    """A table a plugin can grow is not an inventory (cf. ``COMMANDS``)."""
    with pytest.raises(TypeError):
        table["--nonesuch"] = 0  # type: ignore[index]
