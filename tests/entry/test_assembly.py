"""The composition root, and the three seams that are silent when wrong.

Each of the three is a defect that compiles, runs and passes a loosely
written test:

*Two workspaces instead of one.* ``write_file`` and ``read_file`` would
each work perfectly, against different sandbox roots, and the agent would
write a file it cannot then find. Asserted by identity **and** by a real
write-then-read through the registry.

*A wrapped registry.* :class:`~omicsclaw.engine.DeadlineAwareExecutor`
and :class:`~omicsclaw.engine.ConcurrencyAwareExecutor` are
``runtime_checkable`` Protocols the engine tests with :func:`isinstance`.
A wrapper that forwards ``execute`` and ``available_tools`` but not
``use_timeout_pause`` passes every functional test and quietly stops the
timeout pause reaching the tools — which puts a human's approval time
back inside ``tool_timeout``. That is defect R3, and this layer is the
first thing in the rebuild that binds an approval channel.

*A summary timeout in the wrong place.* Wrapping
:func:`~omicsclaw.context.compact` in :func:`asyncio.timeout` and
wrapping the summarizer look identical in a test that asserts "it did not
hang"; the first produces *no compaction*, the second produces a
*degraded* one. Every assertion here is on ``record.degraded``.
"""

from __future__ import annotations

import asyncio
import ast
import dataclasses
import logging
import pathlib
import re
import subprocess
import sys
from datetime import date

import pytest

from omicsclaw.context import (
    AssembledPrompt,
    ContextBudget,
    Pressure,
    PromptAssembler,
    compact,
    estimate_tool_tokens,
    measure,
)
from omicsclaw.engine import (
    ConcurrencyAwareExecutor,
    DeadlineAwareExecutor,
    EngineConfig,
)
from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import (
    LOGGER_NAME,
    SAFETY_RULES,
    SHUTDOWN_GRACE_S,
    AgentApp,
    build_app,
    build_budget,
    build_prompt,
    build_registry,
    build_skill_index,
    build_summarizer,
    default_sections,
    foundation_tools,
)
from omicsclaw.entry.config import AppConfig, SkillsIndex
from omicsclaw.provider import Completion, LLMProvider, get_model_limits
from omicsclaw.observability import Telemetry
from omicsclaw.observability.provider import TracedProvider
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ToolRegistry, use_tool_context
from tests.observability._support import RecordingMeter, RecordingTracer

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRY_DIR = _REPO_ROOT / "omicsclaw" / "entry"
_TASK_A_MODULES = ("__init__.py", "config.py", "assembly.py", "ingress.py")

FOUNDATION = ("read_file", "write_file", "edit_file", "bash", "web_fetch", "web_search")
MOUNTED = (*FOUNDATION, "use_skill")


def _config(workspace: pathlib.Path, **overrides: object) -> AppConfig:
    return AppConfig(workspace=workspace, **overrides)


@dataclasses.dataclass
class _ScriptedProvider:
    """Enough of :class:`~omicsclaw.provider.LLMProvider` to summarize.

    Structural conformance, no import of the Protocol, no SDK — which is
    the property the provider layer was shaped for and the reason these
    tests run on a machine with neither vendor package installed.
    """

    reply: str = "a summary"
    delay_s: float = 0.0
    bound: dict[str, object] = dataclasses.field(default_factory=dict)
    seen: list[tuple[tuple[Message, ...], object]] = dataclasses.field(
        default_factory=list
    )

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        self.seen.append((tuple(messages), tools))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return Completion(message=Message(role=Role.ASSISTANT, content=self.reply))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError("the summarizer never streams")

    def bind(self, **overrides):
        clone = _ScriptedProvider(reply=self.reply, delay_s=self.delay_s)
        clone.bound = dict(overrides)
        return clone


# ---- one workspace, six tools ----------------------------------------


def test_the_six_foundation_tools_are_mounted(tmp_path):
    """All six, in this order, ahead of whatever a later step adds.

    Written as a prefix rather than an equality on purpose: plan 0031 Q13
    leaves ``build_registry(tools=…)`` as the seam that hooks, MCP,
    sub-agents and ``use_skill`` all arrive through, so an exact
    membership assertion would be asserting that no later step ever
    happens. The order matters for a reason equality would not have
    explained — the tool table is part of the byte-stable cached prefix
    (plan 0028), so a tool appended at the end costs less than one
    inserted in the middle.
    """
    config = _config(tmp_path)
    mounted = tuple(tool.name for tool in foundation_tools(config))

    assert mounted[: len(FOUNDATION)] == FOUNDATION
    assert set(FOUNDATION) <= set(build_registry(config).names())


def test_every_filesystem_tool_got_the_same_workspace_object(tmp_path):
    """Identity, not equality: two equal workspaces are still two."""
    registry = build_registry(_config(tmp_path))
    roots = {
        id(registry.get(name)._workspace)
        for name in ("write_file", "edit_file", "bash")
    }

    assert len(roots) == 1
    assert registry.get("bash")._workspace.root == tmp_path


def test_a_file_written_by_one_tool_is_read_by_another(tmp_path):
    """The property identity is a proxy for, checked by running them.

    Two sandbox roots would leave both calls succeeding and the file
    invisible to the second — the failure mode a shared-object assertion
    exists to prevent, exercised here rather than assumed.
    """
    registry = build_registry(_config(tmp_path))

    async def main():
        with use_tool_context(approval=lambda request: True):
            written = await registry.execute(
                ToolCall(
                    id="1",
                    name="write_file",
                    arguments='{"path": "note.txt", "content": "hi"}',
                )
            )
            read = await registry.execute(
                ToolCall(id="2", name="read_file", arguments='{"path": "note.txt"}')
            )
        return written, read

    written, read = asyncio.run(asyncio.wait_for(main(), timeout=30))

    assert written.is_error is False, written.output
    assert read.is_error is False, read.output
    assert "hi" in read.output
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hi"


def test_bash_is_constructed_with_the_derived_half_of_the_ceiling(tmp_path):
    """``BashTool``'s timeout is a **constructor** argument.

    That fact is why plan 0031 §12-2 could rule the ceiling up to 600 s
    at all: ``max_timeout`` returns what the tool was constructed with,
    and this is the only place one is constructed, so the two halves
    cannot be raised separately.
    """
    config = _config(tmp_path, tool_timeout_s=300.0)
    bash = build_registry(config).get("bash")

    assert bash.timeout == config.bash_timeout()
    assert bash.max_timeout == config.bash_timeout()
    assert bash.timeout < config.engine_config().tool_timeout


def test_injected_tools_replace_the_default_set(tmp_path):
    """The seam hooks, MCP and sub-agents all arrive through (Q13)."""
    registry = build_registry(_config(tmp_path), tools=())

    assert registry.names() == ()


# ---- Q16: the registry reaches the engine unwrapped -------------------


def test_the_registry_answers_both_optional_protocols(tmp_path):
    registry = build_registry(_config(tmp_path))

    assert isinstance(registry, DeadlineAwareExecutor)
    assert isinstance(registry, ConcurrencyAwareExecutor)


def test_a_wrapper_that_forgets_the_timeout_pause_stops_being_an_executor(tmp_path):
    """The mutation, written as a test so it cannot be forgotten.

    ``Forgetful`` is what a logging or filtering wrapper looks like when
    somebody writes one: it forwards the two methods that obviously
    matter. Removing this class, or the two assertions in
    :func:`test_the_registry_answers_both_optional_protocols`, is what
    re-installing defect R3 would look like in a diff — a human's
    approval wait charged against ``tool_timeout`` again, on the first
    layer that ever binds an approval channel.
    """
    inner = build_registry(_config(tmp_path))

    class Forgetful:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        async def execute(self, call):
            return await self._wrapped.execute(call)

        def available_tools(self):
            return self._wrapped.available_tools()

        def is_concurrency_safe(self, name):
            return self._wrapped.is_concurrency_safe(name)

    forgetful = Forgetful(inner)

    assert isinstance(forgetful, ConcurrencyAwareExecutor)
    assert not isinstance(forgetful, DeadlineAwareExecutor)


def test_build_app_hands_the_engine_the_registry_itself(tmp_path, monkeypatch):
    """Checked where it happens, not where it is declared.

    ``AgentEngine`` is substituted so that what :func:`build_app`
    actually passed can be inspected — the engine's own
    :func:`isinstance` tests are what decide whether a timeout pause is
    handed down, so asserting on the object it received is asserting the
    thing that matters.
    """
    seen: dict[str, object] = {}

    class Recorder:
        def __init__(self, provider, tools, config, *, prompt=None, conversation=None):
            seen.update(
                provider=provider,
                tools=tools,
                config=config,
                prompt=prompt,
                conversation=conversation,
            )

    monkeypatch.setattr(assembly, "AgentEngine", Recorder)
    monkeypatch.setattr(
        assembly,
        "provider_from_env",
        lambda provider, model: _ScriptedProvider(),
    )

    config = _config(tmp_path)
    app = build_app(config)

    # Plan 0027 §12.5: the assembler is the engine's default PromptSource,
    # and the conversation is not bound at assembly — one engine serves
    # every session, so a history may only arrive per call.
    assert seen["prompt"] is app.prompt
    assert seen["conversation"] is None
    assert isinstance(seen["tools"], ToolRegistry)
    assert isinstance(seen["tools"], DeadlineAwareExecutor)
    assert isinstance(seen["tools"], ConcurrencyAwareExecutor)
    assert seen["config"] == EngineConfig(
        max_turns=config.max_turns,
        tool_timeout=config.tool_timeout_s,
    )


def test_build_app_leaves_the_session_registry_to_the_next_wave(tmp_path, monkeypatch):
    """``sessions`` is the one field still unbuilt, and it is ``None``.

    It used to raise :exc:`NotImplementedError`, which made the whole app
    unreachable and therefore made the composed prompt unreachable too.
    A turn needs the prompt, the budget and the engine and none of those
    is session state, so the app is now returned with the one missing
    field empty and ``omicsclaw/entry/turn.py`` drives an exchange
    against a caller-held history.
    """
    monkeypatch.setattr(
        assembly,
        "provider_from_env",
        lambda provider, model: _ScriptedProvider(),
    )

    app = build_app(_config(tmp_path))

    assert app.sessions is None
    assert app.engine is not None
    assert app.prompt is not None


def test_build_app_asks_the_provider_layer_for_what_the_config_named(
    tmp_path, monkeypatch
):
    """The one function still allowed to read the environment gets both
    hints from :class:`AppConfig`, so detection is a fallback rather than
    a second configuration path."""
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        assembly,
        "provider_from_env",
        lambda provider, model: asked.append((provider, model))
        or _ScriptedProvider(),
    )

    build_app(_config(tmp_path, provider="deepseek", model="deepseek-chat"))

    assert asked == [("deepseek", "deepseek-chat")]


@pytest.mark.parametrize(
    ("preset", "default_model"),
    [("deepseek", "deepseek-v4-flash"), ("zhipu", "glm-5.1")],
)
def test_an_unnamed_model_is_budgeted_as_the_preset_default(
    tmp_path, monkeypatch, preset, default_model
):
    """``LLM_PROVIDER`` alone runs the preset's default model, so the
    window is that model's — not the fallback an empty name would get,
    which is too small for DeepSeek and too large for GLM."""
    for name in ("LLM_MODEL", "OMICSCLAW_MODEL", "SPATIALCLAW_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", preset)
    monkeypatch.setattr(
        assembly,
        "provider_from_env",
        lambda provider, model: _ScriptedProvider(),
    )

    app = build_app(_config(tmp_path, provider=preset))

    expected = get_model_limits(default_model)
    assert expected is not get_model_limits("")
    assert app.budget.context_tokens == expected.context_tokens


# ---- Q7: the two reserves ---------------------------------------------


def test_the_context_budget_refuses_to_guess_its_reserves():
    """Neither field has a default, and neither could have one."""
    with pytest.raises(TypeError):
        ContextBudget(context_tokens=100_000)  # type: ignore[call-arg]


def test_both_reserves_are_computed_from_the_two_things_that_know(tmp_path):
    """Output from the model table, tools from the registry just built."""
    snapshot = build_registry(_config(tmp_path)).available_tools()
    budget = build_budget("deepseek-chat", snapshot)
    limits = get_model_limits("deepseek-chat")

    assert budget.context_tokens == limits.context_tokens
    assert budget.reserve_output_tokens == limits.output_tokens
    assert budget.reserve_tool_tokens == estimate_tool_tokens(snapshot)
    assert budget.reserve_tool_tokens > 0


def test_a_smaller_tool_table_reserves_less(tmp_path):
    """Pins that the reserve is measured rather than nominal."""
    full = build_registry(_config(tmp_path)).available_tools()
    none = build_registry(_config(tmp_path), tools=()).available_tools()

    assert build_budget("", none).reserve_tool_tokens < build_budget(
        "", full
    ).reserve_tool_tokens


def test_an_unnamed_model_budgets_against_limits_that_mean_unknown(tmp_path, caplog):
    """``output_tokens=8192`` from the default table means *unknown*.

    Plan 0031 §11-2 records that as debt; this layer is the first thing
    that ever asks the table, so it is the first place the optimism can
    be reported. The warning is the report.
    """
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        budget = build_budget("", ())

    assert budget.reserve_output_tokens == get_model_limits("").output_tokens
    assert "unknown" in caplog.text


# ---- Q9: the five sections --------------------------------------------


def test_the_default_prompt_is_contract_then_safety_then_guidance_in_this_order(
    tmp_path,
):
    """Planning sits between the tool guidance and the volatile blocks.

    It was six until plan 0039 added ``planning``; plan 0063 folded the
    persona and project sections into one ``contract``. The position is the
    assertion worth keeping: static guidance about how to work groups
    with the static guidance above it, and the two blocks that change —
    the sandbox's state and the skill catalogue — stay at the end, where
    editing one invalidates as little of the cached prefix as possible.
    """
    keys = tuple(s.key for s in default_sections(_config(tmp_path)))

    assert keys == (
        "contract",
        "safety",
        "tools",
        "planning",
        "skills",
        "environment",
    )


def test_the_catalogue_can_be_switched_off_and_its_section_goes(tmp_path):
    config = _config(tmp_path, skills_index=SkillsIndex.OFF)
    keys = tuple(s.key for s in default_sections(config))

    assert keys == (
        "contract",
        "safety",
        "tools",
        "planning",
        "environment",
    )


def test_planning_off_takes_its_section_with_it(tmp_path):
    """One switch, and the prompt half of it.

    The tool half is pinned by ``tests/entry/test_planning.py``; what
    matters here is that the two cannot come apart — a prompt telling the
    model to call ``plan_write`` when no such tool is mounted spends
    turns on a capability the deployment turned off.
    """
    keys = tuple(s.key for s in default_sections(_config(tmp_path, planning=False)))

    assert "planning" not in keys


def test_a_caller_with_its_own_tools_gets_no_planning_section(tmp_path):
    """``plan_tool=False`` is how the assembly says "I did not mount it".

    :func:`build_app` passes it whenever the mounted list has no
    ``plan_write`` in it, which is the case for a caller that supplied
    ``tools=``. Configuration asking for planning is not enough — what is
    mounted decides.
    """
    keys = tuple(s.key for s in default_sections(_config(tmp_path), plan_tool=False))

    assert "planning" not in keys


def _skill(root: pathlib.Path, domain: str, name: str, description: str) -> None:
    """Write one minimal ``SKILL.md`` under ``root/skills/<domain>/<name>/``."""
    directory = root / "skills" / domain / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\nHow to run {name}.\n",
        encoding="utf-8",
    )


def test_the_skills_index_reaches_the_system_prompt(tmp_path):
    """The third tier of the prompt: core identity, AGENTS/CLAUDE, skills.

    This replaces a test that pinned the opposite. That test was right
    while the legacy skill system was being retired and the catalogue was
    about to change under the prompt; the legacy package is now gone and
    ``omicsclaw.skills`` is what the catalogue comes from, so the ruling
    it encoded no longer has a premise.
    """
    _skill(tmp_path, "spatial", "spatial-preprocess", "Load when preprocessing.")
    config = _config(tmp_path)

    system = build_prompt(default_sections(config)).render().system_prompt

    assert "## Available skills" in system
    assert "- spatial-preprocess: Load when preprocessing." in system
    assert "`use_skill`" in system


def test_the_compact_catalogue_drops_the_descriptions(tmp_path):
    _skill(tmp_path, "spatial", "spatial-de", "Load when running DE.")
    config = _config(tmp_path, skills_index=SkillsIndex.COMPACT)

    system = build_prompt(default_sections(config)).render().system_prompt

    assert "- spatial (1 skills): spatial-de" in system
    assert "Load when running DE." not in system


def test_a_workspace_with_no_skills_gets_no_skills_section(tmp_path):
    """An empty index renders ``""``, and an empty section disappears."""
    config = _config(tmp_path)

    prompt = build_prompt(default_sections(config)).render()

    assert not any(key == "skills" for key, _ in prompt.section_stats)
    assert "Available skills" not in prompt.system_prompt


def test_build_app_gives_the_section_and_the_tool_one_scan(tmp_path, monkeypatch):
    """One scan, two consumers — the property :func:`build_app` holds.

    Driven by making the scan return a *different* catalogue each time it
    is called, because two scans of one unchanged directory produce equal
    catalogues and no assertion about content can tell them apart. Both
    catalogues stay on disk, so the only thing that decides whether
    ``use_skill`` can load ``alpha`` is which scan it was built from:
    under a second scan the prompt advertises ``alpha`` while the tool
    holds ``beta``, and the model reads its own correct call back as a
    mistake.
    """
    _skill(tmp_path / "a", "spatial", "alpha", "The catalogue the prompt shows.")
    _skill(tmp_path / "b", "spatial", "beta", "What a second scan would find.")
    first = build_skill_index(_config(tmp_path, skills_dir=tmp_path / "a" / "skills"))
    second = build_skill_index(_config(tmp_path, skills_dir=tmp_path / "b" / "skills"))
    scans = iter((first, second))

    monkeypatch.setattr(assembly, "build_skill_index", lambda config: next(scans))
    monkeypatch.setattr(
        assembly,
        "provider_from_env",
        lambda provider, model: _ScriptedProvider(),
    )

    app = build_app(_config(tmp_path))
    system = app.prompt.render().system_prompt

    assert "alpha" in system
    assert "beta" not in system
    assert app.skills is first
    loaded = asyncio.run(
        app.registry.get("use_skill").execute('{"skill_name": "alpha"}')
    )
    assert "alpha" in loaded


def test_the_safety_rules_reach_the_system_prompt(tmp_path):
    """§9-6. **The mutation**: delete the ``safety`` line from
    :func:`default_sections` and this test is the only one that turns
    red — the prompt still renders, the agent still runs, and nothing
    else in this suite notices that the agent was told it may send
    genetic data off this machine.
    """
    system = build_prompt(default_sections(_config(tmp_path))).render().system_prompt

    assert "## Safety rules" in system
    assert "never leaves this machine" in system
    assert "disclaimer" in system
    assert "SKILL.md methodology only" in system
    assert "Warn before overwriting" in system


def test_the_disclaimer_is_the_one_skill_reports_write():
    """The cost of holding the rules as a constant, charged here.

    A constant cannot vanish from the prompt the way a scraped heading
    can — it can only drift, and drift is what this assertion catches.
    Two texts must carry the same sentence: skill reports write
    ``skills._sdk.report.DISCLAIMER``, and a report the agent writes
    itself follows ``SAFETY_RULES``. Whether the framework's own
    ``omicsclaw.common.report.DISCLAIMER`` matches the ``_sdk`` one is
    ``tests/sdk/test_result_contract.py``'s check. The skill-SDK boundary
    forbids ``omicsclaw/**`` production code from importing
    ``skills._sdk``; a test is not bound by it.
    """
    from skills._sdk.report import DISCLAIMER

    assert DISCLAIMER in SAFETY_RULES


def test_a_missing_contract_file_removes_its_section(tmp_path):
    """``text_from_file`` treats absence as a state, and so does this."""
    system = build_prompt(default_sections(_config(tmp_path))).render().system_prompt

    assert "OmicsClaw" not in system.split("## Safety rules")[0]
    assert system.startswith("## Safety rules")


def test_prompt_files_replace_the_contract(tmp_path):
    """The configured prompt files are the whole front matter.

    The workspace is the checkout here (no ``skills_dir``), so the
    ``OMICSCLAW.md`` beside it is exactly the file the default would read.
    """
    (tmp_path / "OMICSCLAW.md").write_text("CONTRACT-SENTINEL", encoding="utf-8")
    first = tmp_path / "one.md"
    first.write_text("first file", encoding="utf-8")
    config = _config(tmp_path, system_prompt_files=(first,))

    sections = default_sections(config)
    system = build_prompt(sections).render().system_prompt

    assert tuple(s.key for s in sections)[0] == "prompt:one.md"
    assert "first file" in system
    assert "CONTRACT-SENTINEL" not in system
    assert "## Safety rules" in system


# ---- Q9: the date, and re-rendering ------------------------------------


def test_the_environment_section_names_today_to_the_day(tmp_path):
    system = build_prompt(default_sections(_config(tmp_path))).render().system_prompt

    assert f"- Today: {date.today().isoformat()}" in system


def test_the_prompt_carries_no_clock_reading(tmp_path):
    """**The mutation**: ``datetime.now().isoformat()`` in place of
    ``date.today().isoformat()``.

    DeepSeek and OpenAI cache by byte-exact prefix, so a prompt that
    changes every second is a prompt whose cached prefix is worth nothing
    — every turn pays in full. A date invalidates once a day. The
    workspace is empty here so the only text in the prompt is this
    layer's own; nothing a persona file happened to contain can make the
    assertion pass by accident.
    """
    system = build_prompt(default_sections(_config(tmp_path))).render().system_prompt

    assert re.search(r"\d{1,2}:\d{2}", system) is None, system


def test_two_renders_on_one_day_are_byte_identical(tmp_path):
    prompt = build_prompt(default_sections(_config(tmp_path)))

    assert prompt.render().system_prompt == prompt.render().system_prompt


def test_editing_a_prompt_file_changes_the_next_render(tmp_path):
    """What holding an :class:`AssembledPrompt` would silently break.

    ``AgentApp.prompt`` is the **assembler**, and this is the assertion
    that notices if it stops being one: an assembled prompt has no
    ``render`` at all, so a turn holding one would freeze the contract
    and the date at process start — and every other
    acceptance in plan 0031 §9 would still pass.
    """
    contract = tmp_path / "OMICSCLAW.md"
    contract.write_text("I am version one", encoding="utf-8")
    prompt = build_prompt(default_sections(_config(tmp_path)))
    first = prompt.render().system_prompt

    contract.write_text("I am version two", encoding="utf-8")
    second = prompt.render().system_prompt

    assert "version one" in first
    assert "version two" in second


def test_only_the_assembler_can_re_render(tmp_path):
    prompt = build_prompt(default_sections(_config(tmp_path)))

    assert isinstance(prompt, PromptAssembler)
    assert hasattr(PromptAssembler, "render")
    assert not hasattr(AssembledPrompt, "render")


# ---- Q11: where the summary timeout lands ------------------------------


def test_a_summarizer_that_runs_late_returns_nothing(tmp_path):
    summarizer = build_summarizer(
        _ScriptedProvider(delay_s=30.0),
        _config(tmp_path, summary_timeout_s=0.01),
    )

    async def main():
        return await asyncio.wait_for(
            summarizer.summarize("transcript", system="instruction"),
            timeout=10,
        )

    assert asyncio.run(main()) == ""


def test_a_late_summary_degrades_the_compaction_instead_of_cancelling_it(tmp_path):
    """Q11, asserted on ``degraded`` rather than on "it did not hang".

    ``asyncio.timeout`` around :func:`~omicsclaw.context.compact` and
    ``asyncio.timeout`` inside the summarizer are two lines that look the
    same. The first raises out of ``compact`` and the turn gets **no**
    compaction; the second lets ``compact``'s own fallback truncate and
    record why. Only an assertion on ``record.degraded`` separates them.
    """
    messages = _long_conversation()
    budget = _crowded_budget(messages)
    late = build_summarizer(
        _ScriptedProvider(delay_s=30.0),
        _config(tmp_path, summary_timeout_s=0.01),
    )

    async def main():
        return await asyncio.wait_for(
            compact(messages, budget, summarizer=late, pinned=1),
            timeout=20,
        )

    smaller, record, _state = asyncio.run(main())

    assert record.degraded, "a late summary must degrade, not vanish"
    assert len(smaller) < len(messages)


def test_a_prompt_summary_is_not_degraded(tmp_path):
    """The control the test above needs to mean anything.

    Without it, a :func:`build_summarizer` that returned ``""`` for every
    call would satisfy the degradation assertion perfectly.
    """
    messages = _long_conversation()
    budget = _crowded_budget(messages)
    prompt = build_summarizer(
        _ScriptedProvider(reply="## Summary\nwe were analysing a Visium slide"),
        _config(tmp_path, summary_timeout_s=30.0),
    )

    async def main():
        return await asyncio.wait_for(
            compact(messages, budget, summarizer=prompt, pinned=1),
            timeout=20,
        )

    _smaller, record, _state = asyncio.run(main())

    assert record.degraded == ""


def _long_conversation() -> tuple[Message, ...]:
    """Enough conversation that compaction has to do something."""
    filler = "spot-level counts and a domain assignment " * 20
    turns: list[Message] = [Message(role=Role.SYSTEM, content="you are OmicsClaw")]
    for index in range(30):
        turns.append(Message(role=Role.USER, content=f"{index} {filler}"))
        turns.append(Message(role=Role.ASSISTANT, content=f"{index} {filler}"))
    return tuple(turns)


def _crowded_budget(messages: tuple[Message, ...]) -> ContextBudget:
    """A window this conversation fills to ``FULL`` but not ``EMERGENCY``.

    The distinction is the whole setup rather than a detail: ``compact``
    never spends a model call at ``EMERGENCY`` — "the tier exists because
    there is no room left to spend one in" — so a budget tuned one tier
    too tight would make **every** summarizer look degraded, and the
    timeout test below would pass whatever this layer did with it. The
    tier is asserted here so the day an estimator changes, the setup
    fails instead of the conclusion.
    """
    budget = ContextBudget(
        context_tokens=17_000,
        reserve_output_tokens=500,
        reserve_tool_tokens=100,
    )
    assert measure(messages, (), budget).pressure is Pressure.FULL
    return budget


def test_the_summarizer_is_given_no_tools(tmp_path):
    """``tools=None`` strips them; a summarizer that could act is not one."""
    provider = _ScriptedProvider()
    summarizer = build_summarizer(provider, _config(tmp_path))

    asyncio.run(asyncio.wait_for(summarizer.summarize("p", system="s"), timeout=10))

    (messages, tools) = provider.seen[0]
    assert tools is None
    assert [m.role for m in messages] == [Role.SYSTEM, Role.USER]


def test_a_summary_model_binds_a_second_configuration(tmp_path):
    """``bind`` returns a copy, so the main conversation is untouched."""
    provider = _ScriptedProvider()
    summarizer = build_summarizer(provider, _config(tmp_path, summary_model="cheap"))

    assert summarizer.provider is not provider
    assert summarizer.provider.bound == {"model": "cheap"}


def test_no_summary_model_reuses_the_provider_as_given(tmp_path):
    provider = _ScriptedProvider()

    assert build_summarizer(provider, _config(tmp_path)).provider is provider


# ---- Q17: shutdown -----------------------------------------------------


def _app(tmp_path, sessions: object) -> AgentApp:
    """An app assembled by hand, without reaching for the environment.

    The field list is read from the dataclass rather than written out, so
    a later wave adding a field does not turn three shutdown tests red
    for a reason none of them is about. Whatever this test does not care
    about is ``None``: :class:`AgentApp` validates nothing, which is the
    point of a composition root that only wires.

    **A field that has a default keeps it**, rather than being overwritten
    with ``None``. That is what the paragraph above is actually promising,
    and it took ``telemetry`` — non-optional, defaulting to a
    :class:`~omicsclaw.observability.Telemetry` that records nothing — to
    show that the old spelling was not delivering it: filling every
    unnamed field with ``None`` hands the constructor a value its
    annotation forbids, and the failure surfaces in ``aclose``, three
    tests away from the line that caused it.
    """
    known: dict[str, object] = {
        "provider": _ScriptedProvider(),
        "registry": build_registry(_config(tmp_path), tools=()),
        "prompt": build_prompt(()),
        "tools_snapshot": (),
        "budget": build_budget("", ()),
        "config": _config(tmp_path),
        "sessions": sessions,
    }
    fields = {
        field.name: known.get(field.name)
        for field in dataclasses.fields(AgentApp)
        if field.name in known or not _has_default(field)
    }
    return AgentApp(**fields)  # type: ignore[arg-type]


def _has_default(field: dataclasses.Field) -> bool:
    return (
        field.default is not dataclasses.MISSING
        or field.default_factory is not dataclasses.MISSING
    )


def test_closing_the_app_drains_the_session_registry(tmp_path):
    """The whole of shutdown is delegating, and delegating is the test.

    A CLI that exits after one answer never needs this. A desktop server
    closed from an ASGI ``lifespan`` and a channel runner that receives
    ``SIGTERM`` — which is how a container asks a process to stop — both
    do, and neither will be written by whoever wrote ``aclose``.
    """
    drained: list[float] = []

    class StubSessions:
        async def shutdown(self, grace_s: float) -> None:
            await asyncio.sleep(0)
            drained.append(grace_s)

    app = _app(tmp_path, StubSessions())
    asyncio.run(asyncio.wait_for(app.aclose(), timeout=10))

    assert drained == [SHUTDOWN_GRACE_S]


def test_the_shutdown_grace_fits_inside_a_containers_own(tmp_path):
    """A judgement, pinned so that changing it is deliberate.

    ``docker stop`` defaults to ten seconds between ``SIGTERM`` and
    ``SIGKILL``. A grace longer than that would be spent by a process
    about to be killed anyway, and the rest of teardown has to fit
    inside what is left.
    """
    assert 0 < SHUTDOWN_GRACE_S < 10.0


def test_the_app_is_frozen_so_a_turn_cannot_reconfigure_it(tmp_path):
    app = _app(tmp_path, object())

    with pytest.raises(dataclasses.FrozenInstanceError):
        app.budget = None  # type: ignore[misc]


def test_a_scripted_provider_can_be_substituted_after_assembly(tmp_path):
    """The seam :func:`build_app` does not offer as a parameter.

    Plan 0031 §3.2 froze ``build_app(config, *, tools, sections)`` before
    §8.3 asked for an end-to-end turn driven by a scripted provider, so
    the substitution happens afterwards. Recorded as a test because the
    next lane needs to know it works on a ``frozen``/``slots`` dataclass.
    """
    app = _app(tmp_path, object())
    other = _ScriptedProvider(reply="different")

    swapped = dataclasses.replace(app, provider=other)

    assert swapped.provider is other
    assert app.provider is not other


# ---- R1: the provider's published surface, from both sides -------------

_PROVIDER_SURFACE = frozenset(
    name for name in dir(LLMProvider) if not name.startswith("_")
)
"""Everything :class:`~omicsclaw.provider.LLMProvider` publishes.

``bind``, ``generate``, ``generate_stream``, ``name`` — and **not**
``model``, which is why ``AppConfig.model`` is the only place a
deployment's model name lives.
"""

_TESTS_DIR = pathlib.Path(__file__).resolve().parent


def _provider_attribute_reads(tree: ast.AST) -> list[tuple[str, int]]:
    """``(attribute, line)`` for every ``….provider.<attribute>`` read."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        base = node.value
        if isinstance(base, ast.Attribute):
            spelled = base.attr
        elif isinstance(base, ast.Name):
            spelled = base.id
        else:
            continue
        if spelled == "provider":
            found.append((node.attr, node.lineno))
    return found


def test_this_layer_reads_no_provider_attribute_the_protocol_omits():
    """R1, structurally: ``app.provider.model`` is an :exc:`AttributeError`.

    Both surfaces reached for it — the REPL banner and ``GET /health`` —
    and both crashed on the first line of the delivered command, because
    the Protocol publishes four names and that is not one of them. A
    functional test did not notice: the scripted double every green test
    ran against declared a ``model`` the interface does not, so the
    double was wider than the thing it stood for.

    Structural rather than functional because the next such read will be
    in a third surface, written by somebody who saw the second one.
    """
    offenders: list[str] = []
    for path in sorted(_ENTRY_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for attribute, line in _provider_attribute_reads(tree):
            if attribute not in _PROVIDER_SURFACE:
                where = path.relative_to(_ENTRY_DIR)
                offenders.append(f"{where}:{line} reads .{attribute}")

    assert not offenders, f"{offenders}; LLMProvider publishes {_PROVIDER_SURFACE}"


def _declared_as_interface(node: ast.ClassDef) -> list[str]:
    """Names a class declares in the two spellings that mimic a Protocol.

    A ``@property`` and a bare class-level assignment both read, from a
    call site, as *this object implements that member*. An annotated
    class attribute is excluded on purpose: it is a dataclass field, and
    a double's recording fields (``seen``, ``calls``) are visibly
    bookkeeping rather than an interface claim.
    """
    declared: list[str] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(decorator, ast.Name) and decorator.id == "property"
            for decorator in item.decorator_list
        ):
            declared.append(item.name)
        elif isinstance(item, ast.Assign):
            declared.extend(
                target.id for target in item.targets if isinstance(target, ast.Name)
            )
    return [name for name in declared if not name.startswith("_")]


def provider_doubles(source: str, filename: str) -> list[ast.ClassDef]:
    """Every class in *source* shaped like an :class:`LLMProvider` double.

    Recognised by ``generate_stream``, which nothing else in these tests
    defines. Shared with ``tests/launch/test_cli_command.py``, whose
    double lives inside a ``sitecustomize`` template and so is not a
    class of that module.
    """
    tree = ast.parse(source, filename=filename)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "generate_stream"
            for item in node.body
        )
    ]


def test_no_provider_double_declares_more_interface_than_the_protocol():
    """The other half of R1: a double may not be wider than what it stands for.

    Five doubles across this suite each published a ``model`` property.
    ``LLMProvider`` does not, so 591 green tests said nothing about the
    two call sites that read one — including the subprocess test that
    runs the literal delivered command.
    """
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        for node in provider_doubles(source, str(path)):
            for name in _declared_as_interface(node):
                if name not in _PROVIDER_SURFACE:
                    offenders.append(f"{path.name}:{node.lineno} {node.name}.{name}")

    assert not offenders, f"{offenders}; LLMProvider publishes {_PROVIDER_SURFACE}"


# ---- Q22: logging ------------------------------------------------------


def test_this_layer_logs_under_one_name(tmp_path):
    assert LOGGER_NAME == "omicsclaw.entry"
    assert assembly._log.name.startswith(f"{LOGGER_NAME}.")


def test_importing_the_layer_does_not_set_a_level():
    """A library adds a handler; it does not decide an operator's level.

    Checked in a subprocess because pytest configures logging for the
    session, so the level seen inside this process says nothing about
    what a plain program would get. An unconfigured process inherits the
    root logger's ``WARNING``.
    """
    source = (
        "import logging, omicsclaw.entry;"
        "log = logging.getLogger('omicsclaw.entry');"
        "print(log.level, log.getEffectiveLevel(),"
        " any(isinstance(h, logging.NullHandler) for h in log.handlers))"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["0", str(logging.WARNING), "True"]


_FORBIDDEN_IN_A_LOG = frozenset(
    {"arguments", "output", "content", "command", "url", "text", "prompt"}
)
"""Names that carry what a log line must never carry.

:data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1 — genetic data never leaves this
machine — is a rule a log statement can break: a ``bash`` command line, a
``write_file`` body and a ``web_fetch`` query string can each hold a
subject identifier, and a log file is somewhere data leaves to.

``content`` and ``text`` are on the list for the **IM adapters**, where
the payload is not a tool's but a person's: "analyse P12345's Visium" is
the ordinary shape of a request to this agent, and the adapters that were
moved into ``omicsclaw/entry/channel/`` arrived logging ``content[:80]``
at INFO. Q22 rule 1 names tool arguments and outputs; a chat body is the
same category by the same reasoning.
"""

_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical"}
)


def _payloads_logged(tree: ast.AST) -> list[int]:
    """Lines where a log call is handed a name from :data:`_FORBIDDEN_IN_A_LOG`.

    ``len(x)`` is exempt and is the only exemption: the length of a
    message is a number, it is what a line should report instead, and
    exempting it is what lets the rule stay a plain name check. Anything
    else derived from a payload is bound to a differently named local
    first, which is a visible act rather than an argument expression a
    reviewer has to evaluate.
    """
    offending: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _LOG_METHODS:
            continue
        for argument in node.args:
            measured = _measured_nodes(argument)
            for inner in ast.walk(argument):
                if id(inner) in measured:
                    continue
                named = isinstance(inner, ast.Name) and inner.id
                attributed = isinstance(inner, ast.Attribute) and inner.attr
                if (named or attributed) in _FORBIDDEN_IN_A_LOG:
                    offending.append(node.lineno)
    return offending


def _measured_nodes(root: ast.AST) -> set[int]:
    """Ids of every node sitting under a ``len(...)`` within *root*."""
    measured: set[int] = set()
    for node in ast.walk(root):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "len"
        ):
            measured.update(id(child) for child in ast.walk(node))
    return measured


def test_no_log_call_in_this_layer_passes_a_tool_payload():
    """Structural, because a review cannot be re-run on the next diff.

    Over **every** module in the package, not only the four this file was
    written for. The four were clean; the ported adapters were not, and
    the rule had no way of saying so because it was never pointed at
    them. ``feishu.py`` had already been corrected by hand during its
    port, which is the evidence that the scope was the defect rather than
    the rule.
    """
    offenders: list[str] = []
    for path in sorted(_ENTRY_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line in _payloads_logged(tree):
            offenders.append(f"{path.relative_to(_ENTRY_DIR)}:{line}")

    assert not offenders, f"{offenders} log a tool payload or a chat body"


# ---- build_app(provider=) --------------------------------------------


def _unwrapped_task_runner(app):
    tool = app.registry.get("task")
    while hasattr(tool, "inner"):
        tool = tool.inner
    return tool._delegate


def test_a_provider_passed_to_build_app_reaches_every_consumer(tmp_path):
    """The engine, the summarizer and the sub-agent runner all get it.

    Replacing ``app.provider`` and ``app.engine`` afterwards with
    :func:`dataclasses.replace` would leave the summarizer and the
    sub-agent runner on the provider ``provider_from_env`` built, which
    is why ``build_app`` takes the provider as a parameter.
    """
    scripted = _ScriptedProvider()
    app = build_app(
        _config(tmp_path, provider="anthropic", model="claude-sonnet-4-5"),
        provider=scripted,
        telemetry=Telemetry(),
    )
    try:
        assert app.provider is scripted
        assert app.engine._provider is scripted
        assert app.summarizer.provider is scripted
        assert _unwrapped_task_runner(app)._provider is scripted
    finally:
        asyncio.run(app.aclose())


def test_an_active_telemetry_wraps_the_passed_provider(tmp_path):
    scripted = _ScriptedProvider()
    telemetry = Telemetry(tracer=RecordingTracer(), meter=RecordingMeter())
    app = build_app(
        _config(tmp_path, provider="anthropic", model="claude-sonnet-4-5"),
        provider=scripted,
        telemetry=telemetry,
    )
    try:
        assert isinstance(app.provider, TracedProvider)
        assert app.provider.inner is scripted
        assert app.engine._provider is app.provider
        assert app.summarizer.provider is app.provider
        assert _unwrapped_task_runner(app)._provider is app.provider
    finally:
        asyncio.run(app.aclose())
