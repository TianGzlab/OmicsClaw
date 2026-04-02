from omicsclaw.interactive._tui_support import build_tui_header_label


def test_build_tui_header_label_uses_default_model_without_mode():
    assert build_tui_header_label(model="", session_id="abc12345") == "AI · session abc12345"


def test_build_tui_header_label_includes_mode_prefix():
    assert (
        build_tui_header_label(
            model="gpt-test",
            session_id="abc12345",
            mode="run",
        )
        == "gpt-test · [run] · session abc12345"
    )
