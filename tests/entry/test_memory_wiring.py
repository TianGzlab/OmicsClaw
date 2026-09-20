"""Memory, from the composition root to the next system prompt.

``omicsclaw/memory/`` was complete and unreachable: nothing constructed a
:class:`~omicsclaw.memory.Database`, so ``LongTermStore``, ``Precis``,
``MemoryExtractor`` and ``SqliteSessionStore`` had no caller and the
running agent remembered nothing. This file is the guard on the wiring
that closed that gap, and the questions it asks are the ones a diff
cannot answer on its own:

*Does a memory survive the round trip?* ``test_a_compaction_reaches_the_
next_system_prompt`` drives one compaction with a scripted summarizer and
then re-renders the prompt. Every assertion before it can be green while
the loop is open at one joint — the store never written, the précis never
rebuilt, the section holding a snapshot taken before either.

*Do the summarizer and the extractor stay the same decision?* They are
two fields of one app and the extractor needs the first. Building it once
at assembly time compiles, passes an "extraction happened" test, and then
calls a summarizer the app was later given a different one of — which is
how four compaction tests in this suite went red: their substituted
summarizer was ignored and the extraction ran against the scripted
*provider* instead, eating replies the test had counted.

*Is a search honest about writing?* ``LongTermStore.search`` raises the
use count of every hit, because that counter is what stops an entry being
proposed as stale. A policy claiming ``read_only`` would be a claim the
tool does not keep, and the gate above it is entitled to believe it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from typing import Sequence

import pytest

from omicsclaw.context import Pressure
from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import (
    build_app,
    default_sections,
    foundation_tools,
    open_app,
)
from omicsclaw.entry.compaction import build_compactor
from omicsclaw.entry.config import AppConfig
from omicsclaw.entry.memory import (
    MEMORY_SEARCH_TOOL_NAME,
    MEMORY_SECTION_KEY,
    MEMORY_WRITE_TOOL_NAME,
    SEARCH_RESULT_MAX_BYTES,
    build_memory_extractor,
    memory_db_path,
    open_memory,
    precis_path,
    prepare_memory,
)
from omicsclaw.entry.session import InMemorySessionStore, attach_sessions
from omicsclaw.memory import (
    EXTRACTION_SYSTEM_PROMPT,
    MemoryEntry,
    SqliteSessionStore,
)
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role
from omicsclaw.tools import ApprovalMode, ToolArgumentError

WAIT_S = 10.0


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


class _ScriptedProvider:
    """A backend that answers everything with one fixed reply."""

    def __init__(self, reply: str = "done") -> None:
        self.reply = reply
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        self.calls += 1
        return Completion(message=Message(role=Role.ASSISTANT, content=self.reply))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return _ScriptedProvider(self.reply)


class _Summarizer:
    """Answers the extraction prompt with facts and anything else with prose.

    The two prompts are told apart by their system message, which is how
    one double can stand in for both halves of a compaction.
    """

    def __init__(self, *facts: dict[str, object]) -> None:
        self.facts = list(facts)
        self.systems: list[str] = []

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.systems.append(system)
        if system == EXTRACTION_SYSTEM_PROMPT:
            return json.dumps(self.facts, ensure_ascii=False)
        return "## Anchors\n\n### User Intent\nship it\n\n## Summary\nthey talked"


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda provider, model: _ScriptedProvider()
    )


def _config(workspace: pathlib.Path, **overrides: object) -> AppConfig:
    (workspace / "SOUL.md").write_text("You are OmicsClaw.", encoding="utf-8")
    return AppConfig(workspace=workspace, **overrides)


def _history() -> tuple[Message, ...]:
    """A conversation long enough to have a head worth summarizing.

    ``compact`` leaves ``min_tail`` messages behind the pinned prefix and
    refuses outright when the two cover everything — a three-message
    exchange compacts to nothing and calls no extractor at all.
    """
    messages: list[Message] = [Message(role=Role.SYSTEM, content="You are OmicsClaw.")]
    messages.append(Message.user("我们这个项目一律用 leiden 做域识别。"))
    messages.append(Message(role=Role.ASSISTANT, content="记下了。"))
    for index in range(8):
        messages.append(Message.user(f"第 {index} 步呢"))
        messages.append(Message(role=Role.ASSISTANT, content=f"跑第 {index} 步"))
    return tuple(messages)


# ---- the database is opened at all --------------------------------------


def test_building_an_app_opens_the_memory_database(tmp_path, offline):
    """The first thing that was missing: nobody constructed one."""
    app = build_app(_config(tmp_path))

    assert app.memory is not None
    assert memory_db_path(app.config).exists()
    _run(_aclose(app))


def test_memory_off_opens_nothing_and_mounts_nothing(tmp_path, offline):
    """One switch with one meaning: no file, no tools, no prompt block."""
    app = build_app(_config(tmp_path, memory=False))

    assert app.memory is None
    assert not memory_db_path(app.config).exists()
    assert MEMORY_WRITE_TOOL_NAME not in app.registry.names()
    assert MEMORY_SEARCH_TOOL_NAME not in app.registry.names()
    assert MEMORY_SECTION_KEY not in [
        section.key for section in default_sections(app.config)
    ]
    _run(_aclose(app))


def test_the_database_and_the_precis_sit_beside_the_other_state(tmp_path):
    """One directory for everything the agent writes about itself.

    The literal is asserted as well as the relationship: three paths that
    move together are still three paths in the wrong place.
    """
    config = _config(tmp_path)

    assert config.state_dir() == tmp_path / ".omicsclaw"
    assert memory_db_path(config).parent == config.state_dir()
    assert precis_path(config).parent == config.state_dir()
    assert config.plans_root().parent == config.state_dir()
    assert config.permission_rules_path().parent == config.state_dir()


# ---- the two tools ------------------------------------------------------


def test_the_memory_tools_are_mounted_after_everything_else(tmp_path, offline):
    """Appended, not inserted: the tool table is a cached prompt prefix."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    try:
        names = [tool.name for tool in foundation_tools(_config(tmp_path))]
        with_memory = [
            tool.name
            for tool in foundation_tools(_config(tmp_path), memory=memory)
        ]
    finally:
        memory.close()

    assert with_memory[: len(names)] == names
    assert with_memory[len(names) :] == [
        MEMORY_SEARCH_TOOL_NAME,
        MEMORY_WRITE_TOOL_NAME,
    ]


def test_the_memory_tools_reach_the_registry(tmp_path, offline):
    """Mounted by the composition root, not only buildable on their own."""
    app = build_app(_config(tmp_path))
    try:
        assert MEMORY_SEARCH_TOOL_NAME in app.registry.names()
        assert MEMORY_WRITE_TOOL_NAME in app.registry.names()
    finally:
        _run(_aclose(app))


def test_neither_memory_tool_stops_to_ask_a_human(tmp_path, offline):
    """A tool that declares no policy inherits ``ASK``, and approval fails
    closed with no channel bound — so an undeclared ``memory_write`` would
    make the agent stop remembering rather than remember unsafely."""
    app = build_app(_config(tmp_path))
    try:
        for name in (MEMORY_SEARCH_TOOL_NAME, MEMORY_WRITE_TOOL_NAME):
            policy = app.registry.policy_for(name)
            assert policy.approval_mode is ApprovalMode.AUTO, name
    finally:
        _run(_aclose(app))


def test_memory_search_does_not_claim_to_be_read_only(tmp_path, offline):
    """Searching raises the use count of every hit, and that counter is
    what keeps an entry out of ``stale_candidates``. The claim has to
    match, because a gate is entitled to act on it."""
    app = build_app(_config(tmp_path))
    try:
        assert app.registry.policy_for(MEMORY_SEARCH_TOOL_NAME).read_only is False
    finally:
        _run(_aclose(app))


def test_memory_write_stores_an_entry_and_rewrites_the_precis(tmp_path):
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        answer = json.loads(
            _run(
                tool.execute(
                    _call(
                        {
                            "action": "add",
                            "content": "域识别默认用 leiden",
                            "title": "域识别默认",
                            "category": "preference",
                            "importance": 8,
                        }
                    )
                )
            )
        )
        assert answer["id"]
        assert "域识别默认用 leiden" in memory.precis.read()
    finally:
        memory.close()


def test_memory_search_finds_what_memory_write_stored(tmp_path):
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        _run(
            write.execute(
                _call({"action": "add", "content": "deconvolution uses CARD here"})
            )
        )
        found = json.loads(_run(search.execute(_call({"query": "deconvolution"}))))
        missing = json.loads(_run(search.execute(_call({"query": "phylogenetics"}))))
    finally:
        memory.close()

    assert [hit["content"] for hit in found] == ["deconvolution uses CARD here"]
    assert missing == [], "an empty answer must still parse as JSON"


def test_a_search_hit_carries_the_id_an_update_needs(tmp_path):
    """Without the id, ``memory_write``'s update and remove are unusable.

    The précis renders titles and bodies and no ids, which is right for a
    prompt block and wrong for a search: the model can see a memory is
    stale and have no way to name it.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        written = json.loads(
            _run(
                write.execute(
                    _call({"action": "add", "content": "leiden is default"})
                )
            )
        )
        found = json.loads(_run(search.execute(_call({"query": "leiden"}))))
    finally:
        memory.close()

    assert found[0]["id"] == written["id"]


def test_memory_write_updates_only_the_fields_it_was_given(tmp_path):
    """A model correcting one field must not blank the rest.

    ``importance`` is the field that makes this more than a convenience:
    ``0`` is a valid rating, so "not provided" cannot be spelled as a
    zero default — the reference harness has that exact limitation
    written into its own source.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        written = json.loads(
            _run(
                tool.execute(
                    _call(
                        {
                            "action": "add",
                            "title": "域识别默认",
                            "content": "用 leiden，分辨率 1.0",
                            "importance": 7,
                        }
                    )
                )
            )
        )
        _run(
            tool.execute(
                _call(
                    {
                        "action": "update",
                        "id": written["id"],
                        "content": "用 leiden，分辨率 0.8",
                    }
                )
            )
        )
        entry = _run(memory.store.get(written["id"]))
        rendered = memory.precis.read()
    finally:
        memory.close()

    assert entry is not None
    assert entry.content == "用 leiden，分辨率 0.8"
    assert entry.title == "域识别默认", "the untouched field survived"
    assert entry.importance == 7, "an unsaid rating is not a zero rating"
    assert "0.8" in rendered, "the précis followed the correction"


def test_memory_write_removes_what_stopped_being_true(tmp_path):
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        written = json.loads(
            _run(tool.execute(_call({"action": "add", "content": "leiden is default"})))
        )
        _run(tool.execute(_call({"action": "remove", "id": written["id"]})))
        left = _run(memory.store.list())
        rendered = memory.precis.read()
    finally:
        memory.close()

    assert left == []
    assert "leiden" not in rendered, "the précis followed the removal"


def test_memory_write_refuses_an_id_the_store_does_not_hold(tmp_path):
    """Correctable: the message says to search for the id again."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        with pytest.raises(ToolArgumentError) as gone:
            _run(tool.execute(_call({"action": "remove", "id": "nope"})))
        with pytest.raises(ToolArgumentError) as missing:
            _run(tool.execute(_call({"action": "update", "content": "x"})))
    finally:
        memory.close()

    assert "input.id" in str(gone.value)
    assert "input.id is required" in str(missing.value)


def test_memory_write_refuses_what_the_model_can_correct(tmp_path):
    """A refusal the model can act on, not a crash it can only repeat."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        with pytest.raises(ToolArgumentError) as blank:
            _run(tool.execute(_call({"action": "add", "content": "   "})))
    finally:
        memory.close()

    assert "input.content" in str(blank.value)


def test_memory_write_refuses_a_category_it_does_not_have(tmp_path):
    """Refused once, by the schema, and named in the complaint.

    Guarding it a second time in the tool body reads as thorough and is
    unreachable: ``FunctionTool.execute`` validates against the schema
    before the body runs, so the two guards mask each other and neither
    can be shown to work.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    try:
        with pytest.raises(ToolArgumentError) as wrong:
            _run(
                tool.execute(
                    _call(
                        {"action": "add", "content": "x", "category": "philosophy"}
                    )
                )
            )
    finally:
        memory.close()

    assert "input.category" in str(wrong.value)
    assert "preference" in str(wrong.value)


def test_memory_search_refuses_an_empty_query(tmp_path):
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    tool = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        with pytest.raises(ToolArgumentError) as blank:
            _run(tool.execute(_call({"query": "   "})))
    finally:
        memory.close()

    assert "input.query" in str(blank.value)


def test_memory_search_clamps_the_limit_it_is_given(tmp_path):
    """A limit of zero is a search that answers nothing, which reads to the
    model as "there is no such memory" — the one answer it must not get
    from a call that simply asked badly."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        _run(
            write.execute(
                _call({"action": "add", "content": "deconvolution uses CARD here"})
            )
        )
        answer = _run(search.execute(_call({"query": "deconvolution", "limit": 0})))
    finally:
        memory.close()

    assert "CARD" in answer


def test_a_match_too_large_to_fit_is_shortened_rather_than_dropped(tmp_path):
    """The one answer a search must never give for a memory it found.

    Bounding the answer by dropping whole entries from the end is right
    until the *only* entry is the one that does not fit: the model is
    then told ``[]``, reads it as "you were never told this", and goes
    and asks the user something they already answered. Nothing in the
    reply says a byte was dropped, and the hit's use count went up all
    the same — so the entry also stops looking stale, on the strength of
    a read the model never got.

    The reference harness has no bound here and would return the entry
    whole; this keeps the bound and keeps the entry.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    body = "deconvolution " + "x" * (SEARCH_RESULT_MAX_BYTES * 2)
    try:
        written = json.loads(
            _run(write.execute(_call({"action": "add", "content": body})))
        )
        raw = _run(search.execute(_call({"query": "deconvolution"})))
    finally:
        memory.close()

    found = json.loads(raw)
    assert len(found) == 1, "the only match must survive the bound"
    assert found[0]["id"] == written["id"]
    assert found[0]["content_truncated"] is True, "a cut body has to say so"
    assert found[0]["content"].startswith("deconvolution")
    assert len(raw.encode("utf-8")) <= SEARCH_RESULT_MAX_BYTES


def test_a_shortened_answer_is_still_json_and_still_bounded(tmp_path):
    """Both halves at once, because either alone is easy to satisfy.

    Returning the entry whole keeps it parseable and blows the bound;
    cutting the JSON text to the bound keeps the size and stops it being
    JSON, which a model reads as a broken memory rather than a long one.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        for index in range(3):
            _run(
                write.execute(
                    _call(
                        {
                            "action": "add",
                            "title": "域识别 " + "题" * 4000,
                            "content": f"deconvolution {index} " + "记" * 4000,
                        }
                    )
                )
            )
        raw = _run(search.execute(_call({"query": "deconvolution", "limit": 3})))
    finally:
        memory.close()

    found = json.loads(raw)
    assert found, "three matches must not collapse to none"
    assert all("id" in hit for hit in found)
    assert len(raw.encode("utf-8")) <= SEARCH_RESULT_MAX_BYTES


def test_an_entry_whose_title_alone_overflows_is_still_answerable(tmp_path):
    """Shortening the body is not enough when the title is the big half.

    ``memory_write`` puts no ceiling on either field, so a one-word
    memory under a title the model ran away with is a shape the store
    really holds. Cutting only the body walks it down to nothing and
    leaves the title untouched — the answer is over the bound and the
    ``id``, which is the one field the model needs to reach the entry
    again, never arrives.
    """
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        written = json.loads(
            _run(
                write.execute(
                    _call(
                        {
                            "action": "add",
                            "title": "题" * 40_000,
                            "content": "deconvolution",
                        }
                    )
                )
            )
        )
        raw = _run(search.execute(_call({"query": "deconvolution"})))
    finally:
        memory.close()

    found = json.loads(raw)
    assert len(raw.encode("utf-8")) <= SEARCH_RESULT_MAX_BYTES
    assert [hit["id"] for hit in found] == [written["id"]]


def test_a_match_that_fits_is_not_marked_as_shortened(tmp_path):
    """The signal has to mean something, so it may not always be there."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    write = _tool(memory, MEMORY_WRITE_TOOL_NAME)
    search = _tool(memory, MEMORY_SEARCH_TOOL_NAME)
    try:
        _run(
            write.execute(
                _call({"action": "add", "content": "deconvolution uses CARD here"})
            )
        )
        found = json.loads(_run(search.execute(_call({"query": "deconvolution"}))))
    finally:
        memory.close()

    assert found[0]["content"] == "deconvolution uses CARD here"
    assert "content_truncated" not in found[0]


# ---- the prompt section -------------------------------------------------


def test_the_memory_block_is_the_last_section_of_the_prompt(tmp_path, offline):
    """After ``environment``, because it is the one block ``memory_write``
    rewrites mid-session; the last block is the one whose edit costs a
    cached prefix the least."""
    memory = open_memory(_config(tmp_path))
    assert memory is not None
    try:
        keys = [
            section.key
            for section in default_sections(_config(tmp_path), memory=memory)
        ]
    finally:
        memory.close()

    assert keys[-1] == MEMORY_SECTION_KEY
    assert keys[-2] == "environment"


def test_the_memory_block_is_re_read_on_every_render(tmp_path, offline):
    """The section source is a closure, not a snapshot.

    A snapshot taken when the app was assembled would show the agent the
    file as it was before the ``memory_write`` it just made — it would
    reason from the version it had already replaced.
    """
    app = build_app(_config(tmp_path))
    try:
        assert "## Long-term memory" not in app.prompt.render().system_prompt

        memory = app.memory
        assert memory is not None
        _run(memory.store.add(MemoryEntry(title="t", content="leiden", importance=9)))
        _run(memory.precis.regenerate())

        assert "leiden" in app.prompt.render().system_prompt
    finally:
        _run(_aclose(app))


# ---- extraction ---------------------------------------------------------


def test_a_compaction_extracts_into_the_long_term_store(tmp_path, offline):
    app = build_app(_config(tmp_path))
    app = dataclasses.replace(
        app,
        summarizer=_Summarizer(
            {
                "title": "域识别默认",
                "content": "这个项目一律用 leiden 做域识别",
                "category": "preference",
                "importance": 9,
            }
        ),
    )
    try:
        _run(build_compactor(app).force(_history(), app.tools_snapshot))
        assert app.memory is not None
        kept = _run(app.memory.store.list())
    finally:
        _run(_aclose(app))

    assert [entry.content for entry in kept] == ["这个项目一律用 leiden 做域识别"]


def test_the_extractor_follows_a_substituted_summarizer(tmp_path, offline):
    """The two fields are one decision, and an app can be given a new one.

    Capturing the summarizer when the app is assembled leaves extraction
    calling whatever was there then — which is not visibly wrong until a
    caller substitutes a summarizer and the extraction quietly keeps
    talking to the old one.
    """
    app = build_app(_config(tmp_path))
    later = _Summarizer({"content": "the substituted one was used", "importance": 5})
    app = dataclasses.replace(app, summarizer=later)
    try:
        _run(build_compactor(app).force(_history(), app.tools_snapshot))
        assert app.memory is not None
        kept = _run(app.memory.store.list())
    finally:
        _run(_aclose(app))

    assert EXTRACTION_SYSTEM_PROMPT in later.systems
    assert [entry.content for entry in kept] == ["the substituted one was used"]


def test_an_explicit_extractor_wins_over_the_derived_one(tmp_path, offline):
    """The field stays an override; setting it sends extraction elsewhere."""
    seen: list[tuple[Message, ...]] = []

    class Recorder:
        async def extract(self, messages: Sequence[Message]) -> None:
            seen.append(tuple(messages))

    app = build_app(_config(tmp_path))
    app = dataclasses.replace(
        app, summarizer=_Summarizer({"content": "not this one"}),
        memory_extractor=Recorder(),
    )
    try:
        _run(build_compactor(app).force(_history(), app.tools_snapshot))
        assert app.memory is not None
        kept = _run(app.memory.store.list())
    finally:
        _run(_aclose(app))

    assert seen, "the override was not consulted"
    assert kept == [], "the derived extractor ran as well"


def test_no_summarizer_means_no_extractor(tmp_path, offline):
    """Extraction is a model call, so a store on its own is not enough."""
    app = build_app(_config(tmp_path))
    app = dataclasses.replace(app, summarizer=None)
    try:
        assert build_memory_extractor(app.memory, app.summarizer) is None
    finally:
        _run(_aclose(app))


def test_extraction_without_memory_is_simply_off(tmp_path, offline):
    """No database, no extractor — and a compaction that still works."""
    app = build_app(_config(tmp_path, memory=False))
    app = dataclasses.replace(app, summarizer=_Summarizer())
    try:
        _, record = _run(build_compactor(app).force(_history(), app.tools_snapshot))
    finally:
        _run(_aclose(app))

    assert record.pressure is Pressure.FULL


# ---- the whole loop -----------------------------------------------------


def test_a_compaction_reaches_the_next_system_prompt(tmp_path, offline):
    """The only assertion that proves the loop is closed rather than wired.

    Store written, précis rebuilt, section re-read: each of the three can
    be broken on its own with every other test in this file still green.
    """
    app = build_app(_config(tmp_path))
    app = dataclasses.replace(
        app,
        summarizer=_Summarizer(
            {
                "title": "域识别默认",
                "content": "这个项目一律用 leiden 做域识别",
                "category": "preference",
                "importance": 9,
            }
        ),
    )
    before = app.prompt.render().system_prompt
    try:
        _run(build_compactor(app).force(_history(), app.tools_snapshot))
        after = app.prompt.render().system_prompt
    finally:
        _run(_aclose(app))

    assert "leiden" not in before
    assert "## Long-term memory" in after
    assert "这个项目一律用 leiden 做域识别" in after


# ---- sessions -----------------------------------------------------------


def test_attaching_sessions_defaults_to_the_apps_own_database(tmp_path, offline):
    """Persistence by calling it the short way, not by knowing to ask."""
    app = attach_sessions(build_app(_config(tmp_path)))
    try:
        assert app.sessions is not None
        assert isinstance(app.sessions._store, SqliteSessionStore)
    finally:
        _run(_aclose(app))


def test_an_app_without_memory_still_gets_an_in_memory_store(tmp_path, offline):
    app = attach_sessions(build_app(_config(tmp_path, memory=False)))
    try:
        assert app.sessions is not None
        assert isinstance(app.sessions._store, InMemorySessionStore)
    finally:
        _run(_aclose(app))


def test_a_caller_s_own_store_still_wins(tmp_path, offline):
    store = InMemorySessionStore()
    app = attach_sessions(build_app(_config(tmp_path)), store=store)
    try:
        assert app.sessions is not None
        assert app.sessions._store is store
    finally:
        _run(_aclose(app))


def test_a_conversation_outlives_the_process_that_held_it(tmp_path, offline):
    """Two apps over one workspace, which is what a restart looks like."""
    first = attach_sessions(build_app(_config(tmp_path)))
    assert first.sessions is not None
    _run(first.sessions._store.save(_stored("s1")))
    _run(_aclose(first))

    second = attach_sessions(build_app(_config(tmp_path)))
    try:
        assert second.sessions is not None
        restored = _run(second.sessions._store.load("s1"))
    finally:
        _run(_aclose(second))

    assert restored is not None
    assert [message.content for message in restored.history] == ["记得我吗"]


# ---- start-up maintenance -----------------------------------------------


def test_starting_up_purges_the_expired_and_rebuilds_the_precis(tmp_path, offline):
    app = build_app(_config(tmp_path))
    assert app.memory is not None
    try:
        stale = _run(
            app.memory.store.add(
                MemoryEntry(
                    title="stale",
                    content="last week's run directory",
                    importance=1,
                    ttl_days=1,
                )
            )
        )
        # The store stamps ``updated_at`` on write, so an entry can only
        # be old by having been written long ago. This is that, without
        # waiting a day for it.
        app.memory.database.run(
            lambda conn: conn.execute(
                "UPDATE long_term_memories SET updated_at = 0 WHERE id = ?",
                (stale,),
            )
        )
        _run(app.memory.store.add(MemoryEntry(title="kept", content="leiden")))

        purged = _run(prepare_memory(app.memory))
        rendered = app.memory.precis.read()
    finally:
        _run(_aclose(app))

    assert purged == 1
    assert "leiden" in rendered
    assert "last week's" not in rendered


def test_open_app_sweeps_a_memory_left_by_an_earlier_process(tmp_path, offline):
    """The sweep belongs to ``open_app``, which is what a surface calls.

    Writing an entry does not rebuild the précis — only ``memory_write``
    and the extractor do — so a process that ended between the two leaves
    a store the file does not describe. Starting up is when that is
    reconciled, and until it is the agent is shown the previous
    process's idea of what it knows.
    """
    first = build_app(_config(tmp_path))
    assert first.memory is not None
    _run(first.memory.store.add(MemoryEntry(title="kept", content="leiden")))
    _run(_aclose(first))
    assert not precis_path(_config(tmp_path)).exists()

    app = _run(open_app(_config(tmp_path)))
    try:
        assert "leiden" in app.prompt.render().system_prompt
    finally:
        _run(_aclose(app))


def test_a_broken_memory_does_not_stop_the_process_starting(tmp_path, offline):
    """Losing the sweep costs a stale précis; raising costs the process."""

    class Exploding:
        async def purge_expired(self, now=None):
            raise RuntimeError("the disk is gone")

    app = build_app(_config(tmp_path))
    assert app.memory is not None
    broken = dataclasses.replace(app.memory, store=Exploding())
    try:
        assert _run(prepare_memory(broken)) == 0
    finally:
        _run(_aclose(app))


def test_no_memory_at_all_is_a_sweep_that_does_nothing(tmp_path):
    assert _run(prepare_memory(None)) == 0


# ---- lifetime -----------------------------------------------------------


def test_closing_the_app_closes_the_memory_database(tmp_path, offline):
    app = build_app(_config(tmp_path))
    assert app.memory is not None
    _run(app.aclose())

    with pytest.raises(Exception):
        app.memory.database.run(lambda conn: conn.execute("SELECT 1"))


def test_an_assembly_that_raises_closes_the_memory_it_opened(tmp_path, offline):
    """``build_app`` owns what it opened until it hands the app over."""
    opened: list[object] = []
    real = assembly.open_memory

    def spy(config):
        binding = real(config)
        opened.append(binding)
        return binding

    original = assembly.build_registry
    assembly.open_memory = spy
    assembly.build_registry = _explode
    try:
        with pytest.raises(RuntimeError):
            build_app(_config(tmp_path))
    finally:
        assembly.open_memory = real
        assembly.build_registry = original

    assert opened and opened[0] is not None
    with pytest.raises(Exception):
        opened[0].database.run(lambda conn: conn.execute("SELECT 1"))


def _explode(*args, **kwargs):
    raise RuntimeError("assembly failed after the database was open")


# ---- helpers ------------------------------------------------------------


def _tool(memory, name: str):
    """The one mounted memory tool called *name*."""
    from omicsclaw.entry.memory import memory_tools

    return next(tool for tool in memory_tools(memory) if tool.name == name)


def _call(arguments: dict[str, object]) -> str:
    """The argument payload as a tool receives it: one JSON string."""
    return json.dumps(arguments, ensure_ascii=False)


def _stored(session_id: str):
    """One saved conversation, in the shape both stores accept."""
    from omicsclaw.entry.session import Session

    return Session(session_id=session_id, history=(Message.user("记得我吗"),))


async def _aclose(app) -> None:
    await app.aclose()
