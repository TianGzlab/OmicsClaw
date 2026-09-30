"""The engine's two new seams are satisfied from above, with no adapter.

Plan 0027 §12.4.1 and §12.4.2. Both Protocols were shaped so that what
this layer already had would satisfy them as-is — ``PromptAssembler``
renders an ``AssembledPrompt``, and an ``AssembledPrompt`` already
exposes ``system_prompt``. The claim is checkable, so it is checked: a
narrower seam (``system_prompt() -> str``) would have forced an adapter
here, and an adapter would have dropped ``section_stats`` on the way
through — the only answer to "which block is eating the window".

The second half is the direction of the arrow. Satisfying a Protocol
structurally is worth nothing if the layer that declares it imports the
layer that satisfies it, so this file also pins that ``omicsclaw.engine``
names neither :mod:`omicsclaw.context` — where the prompt types live —
nor :mod:`omicsclaw.entry`, where the conversation does.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import subprocess
import sys

import pytest

from omicsclaw.context import AssembledPrompt, PromptAssembler, Section
from omicsclaw.engine import AgentEngine, Conversation, PromptSource, RenderedPrompt
from omicsclaw.entry.turn import _Carried
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENGINE_DIR = _REPO_ROOT / "omicsclaw" / "engine"


def _assembler() -> PromptAssembler:
    return PromptAssembler().with_section(
        Section(key="persona", heading="# Persona", source=lambda: "You are OmicsClaw.")
    )


def test_the_prompt_assembler_is_a_prompt_source_as_it_stands():
    assert isinstance(_assembler(), PromptSource)


def test_a_render_is_a_rendered_prompt_and_keeps_what_the_engine_ignores():
    """The reason the seam passes an object rather than a ``str``."""
    rendered = _assembler().render()

    assert isinstance(rendered, AssembledPrompt)
    assert isinstance(rendered, RenderedPrompt)
    assert "You are OmicsClaw." in rendered.system_prompt
    assert rendered.section_stats[0][0] == "persona"
    assert rendered.total_estimated_tokens > 0


def test_this_layers_carried_history_is_a_conversation():
    assert isinstance(_Carried(), Conversation)


def test_a_real_exchange_runs_on_this_layers_objects_unwrapped():
    """The claim end to end: assembler in, carried history out, no adapter.

    Both objects go to the engine exactly as ``turn.py`` hands them over,
    and what comes back is what :func:`~omicsclaw.entry.turn._outcome`
    reads — the render on the result, the conversation on the
    :class:`~omicsclaw.entry.turn._Carried`.
    """

    class Provider:
        name = "scripted"

        async def generate(self, messages, tools=None):
            return Completion(
                message=Message.assistant("done"), finish_reason="stop"
            )

        def generate_stream(self, messages, tools=None):  # pragma: no cover
            raise NotImplementedError

        def bind(self, **overrides):
            return self

    class Tools:
        def available_tools(self):
            return ()

        async def execute(self, call):  # pragma: no cover - none are declared
            raise NotImplementedError

    assembler = _assembler()
    carried = _Carried((Message.user("earlier"),))
    engine = AgentEngine(Provider(), Tools())

    result = asyncio.run(
        engine.exchange("go", prompt=assembler, conversation=carried)
    )

    assert isinstance(result.prompt, AssembledPrompt)
    assert result.prompt.section_stats[0][0] == "persona"
    assert [m.content for m in carried.carried] == ["earlier", "go", "done"]
    assert all(m.role is not Role.SYSTEM for m in carried.carried)


@pytest.mark.parametrize("forbidden", ["omicsclaw.context", "omicsclaw.entry"])
def test_the_engine_names_neither_layer_that_satisfies_its_new_seams(
    forbidden: str,
):
    offenders: list[str] = []
    for path in sorted(_ENGINE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            if any(
                name == forbidden or name.startswith(f"{forbidden}.")
                for name in names
            ):
                offenders.append(path.name)

    assert not offenders, (
        f"{offenders} import {forbidden} — the Protocols are declared in "
        "the engine and satisfied from above, never the other way round"
    )


def test_importing_the_engine_still_loads_nothing_of_this_layer():
    """The behavioural half: source text is a proxy, ``sys.modules`` is not."""
    source = (
        "import sys, omicsclaw.engine as engine;"
        "assert engine.Conversation is not None;"
        "assert engine.PromptSource is not None;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw')"
        " and not m.startswith('omicsclaw.engine')"
        " and not m.startswith('omicsclaw.provider')"
        " and not m.startswith('omicsclaw.schema') and m != 'omicsclaw'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['omicsclaw.version']", (
        f"importing the engine dragged in {result.stdout.strip()}"
    )
