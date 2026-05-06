from omicsclaw.interactive._tui_support import (
    attach_reasoning_container,
    build_tui_header_label,
)


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


class _FakeWidget:
    def __init__(self):
        self.children = []
        self.mounted = False

    def mount(self, child):
        if not self.mounted:
            raise RuntimeError(
                f"Can't mount widget(s) before {self.__class__.__name__} is mounted"
            )
        child.mounted = True
        self.children.append(child)


class _FakeChat(_FakeWidget):
    def __init__(self):
        super().__init__()
        self.mounted = True


class _FakeCollapsible(_FakeWidget):
    def __init__(self, *, title):
        super().__init__()
        self.title = title


class _FakeVertical(_FakeWidget):
    pass


def test_attach_reasoning_container_mounts_parent_before_child():
    chat = _FakeChat()

    container = attach_reasoning_container(
        chat,
        collapsible_cls=_FakeCollapsible,
        vertical_cls=_FakeVertical,
    )

    assert isinstance(container, _FakeVertical)
    assert len(chat.children) == 1
    assert isinstance(chat.children[0], _FakeCollapsible)
    assert chat.children[0].children == [container]
