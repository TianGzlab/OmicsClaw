from omicsclaw.interactive._style_support import build_style_command_view


def test_build_style_command_view_lists_available_styles():
    view = build_style_command_view(
        "list",
        session_metadata={"active_style": "scientific-brief"},
    )

    assert view.success is True
    assert "Active output style: scientific-brief" in view.output_text
    assert "default" in view.output_text
    assert "scientific-brief" in view.output_text


def test_build_style_command_view_sets_style_in_session_metadata():
    view = build_style_command_view(
        "set teaching",
        session_metadata={"pipeline_workspace": "/tmp/pipeline"},
    )

    assert view.success is True
    assert view.replace_session_metadata is True
    assert view.session_metadata["pipeline_workspace"] == "/tmp/pipeline"
    assert view.session_metadata["active_style"] == "teaching"
    assert "Active output style set to: teaching" in view.output_text


def test_build_style_command_view_rejects_unknown_style():
    view = build_style_command_view(
        "set missing-style",
        session_metadata={},
    )

    assert view.success is False
    assert "Unknown output style" in view.output_text
