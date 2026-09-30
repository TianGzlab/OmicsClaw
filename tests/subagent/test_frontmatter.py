"""Reading one agent file: the header, the body, and what is refused.

Plan 0046 §10. The parser covers the subset an agent file uses and drops
anything outside it rather than guessing — a definition that half-parsed
would be a sub-agent with a tool set nobody wrote.
"""

from __future__ import annotations

import pytest

from omicsclaw.subagent import InvalidDefinition, parse_agent_file

MINIMAL = """---
name: surveyor
description: Surveys a tree of files
---
You survey.
"""


def test_the_header_and_the_body_both_arrive():
    definition = parse_agent_file(MINIMAL)

    assert definition.name == "surveyor"
    assert definition.description == "Surveys a tree of files"
    assert definition.system_prompt == "You survey."


def test_every_optional_field_is_read():
    definition = parse_agent_file(
        """---
name: reviewer
description: Reviews a diff
model: cheap-model
max_turns: 12
tools: read_file, bash
disallowed_tools: bash
skills: spatial-de
---
Review it.
"""
    )

    assert definition.model == "cheap-model"
    assert definition.max_turns == 12
    assert definition.tools == ("read_file", "bash")
    assert definition.disallowed_tools == ("bash",)
    assert definition.skills == ("spatial-de",)


def test_a_block_sequence_says_the_same_thing_as_a_comma_list():
    block = parse_agent_file(
        """---
name: reviewer
description: Reviews a diff
tools:
  - read_file
  - bash
---
Review it.
"""
    )

    assert block.tools == ("read_file", "bash")


def test_quotes_are_stripped_from_scalars_and_from_sequence_items():
    definition = parse_agent_file(
        """---
name: "reviewer"
description: 'Reviews a diff'
tools:
  - "read_file"
---
Review it.
"""
    )

    assert definition.name == "reviewer"
    assert definition.description == "Reviews a diff"
    assert definition.tools == ("read_file",)


def test_a_comment_line_is_not_a_field():
    definition = parse_agent_file(
        """---
# who this is
name: reviewer
description: Reviews a diff
---
Review it.
"""
    )

    assert definition.name == "reviewer"
    assert "who this is" not in definition.description


def test_a_max_turns_that_is_not_a_number_reads_as_no_ceiling():
    """Better than refusing the whole file over one malformed budget."""
    definition = parse_agent_file(
        """---
name: reviewer
description: Reviews a diff
max_turns: soon
---
Review it.
"""
    )

    assert definition.max_turns == 0


def test_a_missing_name_falls_back_to_the_one_offered():
    definition = parse_agent_file(
        """---
description: Reviews a diff
---
Review it.
""",
        fallback_name="reviewer",
    )

    assert definition.name == "reviewer"


def test_a_missing_description_falls_back_to_the_first_line_of_the_body():
    definition = parse_agent_file(
        """---
name: reviewer
---

Review a diff and report what is wrong.
More detail here.
"""
    )

    assert definition.description == "Review a diff and report what is wrong."


def test_a_block_scalar_is_dropped_and_the_body_supplies_the_description():
    """Truncating would be worse than dropping: ``'>'`` validates.

    The parser reads one line per key, so a block scalar's indicator is
    all it would see. A description of ``'>'`` is non-empty, so
    ``validate()`` passes it, and the sub-agent reaches the model's
    ``subagent_type`` enum described by a punctuation mark — unchoosable,
    and with nothing logged. Dropping the key instead lets the existing
    fallback do its job.

    Two guards in ``_fields`` cover this shape between them, so the
    mutations that isolate them are below rather than here:
    :func:`test_a_block_scalar_whose_body_reads_as_a_sequence_is_still_dropped`
    for the indicator, and
    :func:`test_a_folded_continuation_is_dropped_rather_than_cut_at_the_first_line`
    for the continuation.
    """
    definition = parse_agent_file(
        """---
name: surveyor
description: >
  Surveys a tree of files and reports what it found.
---

You survey things.
""",
        fallback_name="surveyor",
    )

    assert definition.description == "You survey things."
    assert definition.name == "surveyor"
    assert definition.system_prompt == "You survey things."


def test_a_folded_continuation_is_dropped_rather_than_cut_at_the_first_line():
    """Same principle for a plain scalar carried onto an indented line.

    Mutation: drop the ``elif scalar`` arm of ``_fields`` and this goes
    red with ``description == 'Surveys a tree'`` — a sentence cut in half
    that ``validate()`` is happy with.
    """
    definition = parse_agent_file(
        """---
name: surveyor
description: Surveys a tree
  of files.
---

You survey things.
""",
        fallback_name="surveyor",
    )

    assert definition.description == "You survey things."


@pytest.mark.parametrize("indicator", [">", "|", ">-", "|-", ">+", "|+"])
def test_every_block_scalar_indicator_is_refused_the_same_way(indicator: str):
    definition = parse_agent_file(
        f"""---
name: surveyor
description: {indicator}
  Surveys a tree of files.
---
You survey things.
"""
    )

    assert definition.description == "You survey things."


def test_a_block_scalar_name_falls_back_to_the_file_instead_of_refusing():
    """``name: >`` is not a name; the stem the loader offers is."""
    definition = parse_agent_file(
        """---
name: >
  surveyor
description: Surveys a tree of files
---
You survey things.
""",
        fallback_name="surveyor",
    )

    assert definition.name == "surveyor"


def test_a_block_scalar_whose_body_reads_as_a_sequence_is_still_dropped():
    """The indicator decides, not what happens to be written under it.

    ``|`` opens a literal *string*; the dashes under it are two of its
    characters, not two list items. This is the one shape the folded
    continuation guard cannot catch — ``- read_file`` is taken for a
    sequence item before that guard is reached — so it is what isolates
    the indicator check.

    Mutation: delete the ``value in _BLOCK_SCALARS`` arm of ``_fields``
    and this goes red with ``tools == ('read_file', 'bash')`` — a sub-agent
    given an allow-list nobody wrote.
    """
    definition = parse_agent_file(
        """---
name: surveyor
description: Surveys a tree of files
tools: |
  - read_file
  - bash
---
You survey things.
"""
    )

    assert definition.tools == ()
    assert definition.resolve_tools(("read_file", "bash")) == ("read_file", "bash")


def test_a_block_scalar_with_nothing_under_it_is_dropped_too():
    """No continuation for the second guard to see, so the first must hold."""
    definition = parse_agent_file(
        """---
name: surveyor
description: >
model: cheap-model
---
You survey things.
"""
    )

    assert definition.description == "You survey things."
    assert definition.model == "cheap-model"


def test_a_definition_with_a_dropped_key_is_still_usable_everywhere():
    """The point of dropping: what comes back is a working sub-agent."""
    definition = parse_agent_file(
        """---
name: surveyor
description: >
  Surveys a tree of files.
model: cheap-model
---
Survey the tree and report what you found.
""",
        source="/agents/surveyor.md",
    )

    definition.validate()
    assert definition.description == "Survey the tree and report what you found."
    assert definition.model == "cheap-model"


def test_the_source_is_recorded_for_diagnostics():
    definition = parse_agent_file(MINIMAL, source="/agents/surveyor.md")

    assert definition.source == "/agents/surveyor.md"


@pytest.mark.parametrize(
    "content",
    [
        "no header at all\n",
        "---\nname: reviewer\ndescription: d\nnever closed\n",
    ],
    ids=["absent", "unclosed"],
)
def test_a_file_without_a_closed_header_is_refused(content: str):
    with pytest.raises(InvalidDefinition, match="frontmatter"):
        parse_agent_file(content)


def test_a_file_with_no_body_is_refused():
    """A sub-agent with no instructions would run as nobody in particular."""
    with pytest.raises(InvalidDefinition, match="system prompt"):
        parse_agent_file("---\nname: reviewer\ndescription: d\n---\n")


def test_a_file_with_neither_a_name_nor_a_fallback_is_refused():
    with pytest.raises(InvalidDefinition):
        parse_agent_file("---\ndescription: d\n---\nbody\n")
