"""The YAML subset ``SKILL.md`` headers are parsed with."""

from __future__ import annotations

from omicsclaw.skills.frontmatter import parse_frontmatter


def test_a_plain_header_yields_its_scalars_and_its_body():
    header = parse_frontmatter(
        "---\nname: go-refactor\ndescription: refactor Go code\n---\nbody text\n"
    )

    assert header.has_frontmatter
    assert header.text("name") == "go-refactor"
    assert header.text("description") == "refactor Go code"
    assert header.body == "body text\n"


def test_matching_surrounding_quotes_are_removed():
    header = parse_frontmatter(
        "---\nname: \"quoted\"\ndescription: 'single'\ntrigger: \"/go\"\n---\nx"
    )

    assert header.text("name") == "quoted"
    assert header.text("description") == "single"
    assert header.text("trigger") == "/go"


def test_a_file_with_no_opening_delimiter_is_all_body():
    content = "# Just a document\n\nno header here\n"

    header = parse_frontmatter(content)

    assert not header.has_frontmatter
    assert header.fields == {}
    assert header.body == content


def test_an_unclosed_header_is_all_body():
    """A missing closing ``---`` must not swallow the document as metadata."""
    content = "---\nname: broken\ndescription: never closed\n\nbody\n"

    header = parse_frontmatter(content)

    assert not header.has_frontmatter
    assert header.body == content


def test_a_header_with_no_body_parses_to_an_empty_body():
    header = parse_frontmatter("---\nname: n\ndescription: d\n---\n")

    assert header.has_frontmatter
    assert header.body == ""


def test_exactly_one_leading_newline_is_taken_off_the_body():
    header = parse_frontmatter("---\nname: n\ndescription: d\n---\n\n\n# Title")

    assert header.body == "\n# Title"


def test_an_absent_key_reads_as_the_default():
    header = parse_frontmatter("---\nname: n\ndescription: d\n---\nx")

    assert header.text("trigger") == ""
    assert header.text("trigger", "none") == "none"
    assert header.items("tags") == ()


def test_an_indented_continuation_folds_into_the_scalar():
    """The corpus writes descriptions across several lines; all of it counts."""
    header = parse_frontmatter(
        "---\n"
        "name: spatial-de\n"
        "description: Load when running differential expression.\n"
        "  Skip when the data is single-cell (use sc-de); spatially\n"
        "  variable genes (use spatial-genes).\n"
        "version: 0.6.0\n"
        "---\nbody"
    )

    assert header.text("description") == (
        "Load when running differential expression. Skip when the data is "
        "single-cell (use sc-de); spatially variable genes (use spatial-genes)."
    )
    assert header.text("version") == "0.6.0"


def test_a_continuation_starting_with_a_dash_stays_part_of_the_scalar():
    """An indented line belongs to the open scalar, not to a new sequence."""
    header = parse_frontmatter(
        "---\nname: n\ndescription: counts per cell\n  - and per gene\n---\nx"
    )

    assert header.text("description") == "counts per cell - and per gene"
    assert header.items("description") == ("counts per cell - and per gene",)


def test_a_block_sequence_becomes_a_tuple():
    header = parse_frontmatter(
        "---\nname: n\ndescription: d\ntags:\n- spatial\n- visium\n- qc\n---\nx"
    )

    assert header.fields["tags"] == ("spatial", "visium", "qc")
    assert header.items("tags") == ("spatial", "visium", "qc")


def test_an_indented_block_sequence_becomes_a_tuple_too():
    header = parse_frontmatter(
        "---\nname: n\ndescription: d\nrequires:\n  - scanpy\n  - numpy\n---\nx"
    )

    assert header.items("requires") == ("scanpy", "numpy")


def test_a_comment_line_at_column_zero_is_ignored():
    """Every generated header opens with an AUTO-GENERATED comment."""
    header = parse_frontmatter(
        "---\n# AUTO-GENERATED header — do not edit by hand.\n"
        "name: n\ndescription: d\n---\nx"
    )

    assert header.fields == {"name": "n", "description": "d"}


def test_a_blank_line_ends_a_scalar_rather_than_folding_into_it():
    header = parse_frontmatter(
        "---\nname: n\ndescription: first\n\nversion: 1\n---\nx"
    )

    assert header.text("description") == "first"
    assert header.text("version") == "1"


def test_a_key_with_no_value_reads_as_an_empty_string():
    header = parse_frontmatter("---\nname: n\ndescription: d\nemoji:\n---\nx")

    assert header.text("emoji") == ""


def test_a_nested_mapping_drops_its_key_rather_than_flattening_it():
    """Half a mapping rendered as a string would read like a value."""
    header = parse_frontmatter(
        "---\nname: n\ndescription: d\nsummary:\n  load_when: something\n"
        "version: 2\n---\nx"
    )

    assert "summary" not in header.fields
    assert header.text("summary") == ""
    assert header.text("version") == "2"


def test_a_literal_block_scalar_keeps_its_line_breaks():
    header = parse_frontmatter(
        "---\nname: n\ndescription: |\n  first line\n  second line\nversion: 1\n---\nx"
    )

    assert header.text("description") == "first line\nsecond line"
    assert header.text("version") == "1"


def test_a_folded_block_scalar_joins_its_lines():
    header = parse_frontmatter(
        "---\nname: n\ndescription: >-\n  first line\n  second line\n"
        "\n  new paragraph\nversion: 1\n---\nx"
    )

    assert header.text("description") == "first line second line\nnew paragraph"
    assert header.text("version") == "1"


def test_crlf_line_endings_parse_the_same_way():
    header = parse_frontmatter(
        "---\r\nname: n\r\ndescription: d\r\ntags:\r\n- a\r\n---\r\nbody\r\n"
    )

    assert header.has_frontmatter
    assert header.text("name") == "n"
    assert header.items("tags") == ("a",)


def test_the_fields_mapping_cannot_be_written_to():
    header = parse_frontmatter("---\nname: n\ndescription: d\n---\nx")

    try:
        header.fields["name"] = "other"  # type: ignore[index]
    except TypeError:
        return
    raise AssertionError("Frontmatter.fields accepted a write")


def test_a_key_ordered_last_still_parses():
    """The final key has no following line to flush it; the loop must."""
    header = parse_frontmatter("---\nname: n\ndescription: d\ntags:\n- last\n---\nx")

    assert header.items("tags") == ("last",)


def test_a_three_dash_line_inside_the_body_is_not_a_delimiter():
    header = parse_frontmatter("---\nname: n\ndescription: d\n---\nintro\n\n---\nmore")

    assert header.text("name") == "n"
    assert header.body == "intro\n\n---\nmore"
