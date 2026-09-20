"""``omicsclaw.entry.cli`` costs no optional package to import or to drive.

These three tests were in ``tests/entry/test_cli_main.py`` until plan
0037 moved the process out of this package. They did **not** move with
it: they are properties of the surface *library* —— what importing it
costs, and which input source it picks —— not of the command that starts
it. The command's own tests are now in ``tests/launch/``.

``prompt_toolkit`` **is** installed here, which is exactly why these are
subprocess probes of :data:`sys.modules` rather than import assertions:
a module-scope import would not fail, it would simply be paid by
everybody, including the desktop server and the channel runner, and no
other test in this repository would notice.
"""

from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import textwrap

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_importing_the_surface_costs_no_optional_dependency():
    """Plan 0031 trap 13, for this subpackage specifically."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, omicsclaw.entry.cli;"
            "print(sorted(m for m in sys.modules"
            " if m in ('prompt_toolkit', 'textual', 'openai', 'anthropic')))",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_a_pipe_is_read_as_a_stream_and_not_through_a_terminal_library():
    """``main.go:453-468`` makes this test before it chooses a UI.

    ``prompt_toolkit`` has its own fallbacks and will often survive being
    pointed at a pipe, which is exactly why the branch needs its own
    assertion: a surface that took the interactive path for
    ``cli < questions.txt`` would be relying on another package's
    forgiveness, and would print a prompt into the output of every
    scripted run.
    """
    from omicsclaw.entry.cli._input import StreamSource, open_prompt_source

    piped = io.StringIO("what is Moran's I?\n")

    assert isinstance(open_prompt_source((), stream=piped), StreamSource)


def test_the_surface_still_works_with_neither_optional_package_installed():
    """Both blocked at :data:`sys.meta_path`, then the loop is driven.

    Keeps its meaning on a machine where ``prompt_toolkit`` *is*
    installed, which is this one: asserting it is absent would only be
    asserting something about this container.
    """
    program = textwrap.dedent(
        """
        import sys

        class Blocker:
            @staticmethod
            def find_spec(name, *a, **k):
                if name.split(".")[0] in ("prompt_toolkit", "textual"):
                    raise ImportError("blocked: " + name)
                return None

        sys.meta_path.insert(0, Blocker())

        import asyncio, io, pathlib, tempfile
        from omicsclaw.entry.cli import Repl, Screen, open_prompt_source
        from omicsclaw.entry.cli._input import StreamSource

        source = open_prompt_source((), stream=io.StringIO(""), interactive=True)
        assert isinstance(source, StreamSource), type(source)
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
