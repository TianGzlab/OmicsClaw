"""The published contract, unchanged — and the proof that it is unchanged.

Plan 0031 §9-14 and Q24. ``POST /chat/stream`` is an external project's
contract: ``OmicsClaw-App`` (Electron + Next.js) calls it from
``src/app/api/chat/route.ts``, which describes itself as a Transform Proxy.
A backend-internal rebuild step is not where a version number that an
external client already depends on gets changed, so the central assertion
here compares this port against the **pre-port file on disk**, not against a
value somebody retyped.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

from omicsclaw.entry.desktop import _chat_sse, wire_contract
from omicsclaw.entry.desktop._chat_sse import (
    CHAT_SSE_MAX_FRAME_BYTES,
    CHAT_SSE_QUEUE_MAX_ITEMS,
    render_chat_sse_frame,
    utf8_size,
)
from omicsclaw.entry.desktop.server import (
    health_payload,
    unauthenticated_health_payload,
)
from omicsclaw.entry.config import resolve_app_config
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    make_app,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
ORIGINAL = REPO / "omicsclaw" / "surfaces" / "desktop" / "wire_contract.py"
ORIGINAL_SSE = REPO / "omicsclaw" / "surfaces" / "desktop" / "_chat_sse.py"

SCHEMA_VERSION_NAMES = (
    "DESKTOP_CHAT_REQUEST_SCHEMA_VERSION",
    "DESKTOP_CHAT_SSE_SCHEMA_VERSION",
    "DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION",
    "DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION",
    "DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_RUN_REQUEST_SCHEMA_VERSION",
    "DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION",
)
"""The eight the plan forbids this step from touching."""

FROZEN_CHAT_CONTRACT = {
    "request_schema_version": 1,
    "sse_schema_version": 1,
    "interrupt_schema_version": 1,
    "authoritative_ingress": True,
    "durable_ingress_idempotency": True,
    "source_request_id_required": True,
    "attachments_supported": False,
    "max_sse_frame_bytes": 4 * 1024 * 1024,
    "event_queue_capacity": 8,
    "producer_backpressure": True,
    "oversize_event_projection": True,
    "terminal_error_type_preserved": True,
}
"""A literal snapshot of ``desktop_chat_contract()`` as it stood before the
port.

Redundant with :func:`test_every_contract_descriptor_matches_the_pre_port_file`
**today** and not tomorrow: plan 0031 §10 deletes
``omicsclaw/surfaces/`` once the second and third families land, and the
assertion that survives that deletion is this one. Two checks of one fact,
with different lifetimes.
"""


def _pre_port_namespace() -> dict[str, object]:
    """Execute the pre-port module with its two imports satisfied locally.

    It cannot simply be imported. ``wire_contract.py`` reads four bounds from
    ``desktop/run_wire.py``, which imports ``pydantic``, ``starlette``, the
    deleted ``omicsclaw.control`` and the deleted ``omicsclaw.skill``
    (singular — the name plan 0031 §9-17 forbids from ``sys.modules``).
    **That makes the plan's "0 lines to change" for this file wrong**: the
    coupling scan matched only ``^(from|import) omicsclaw\\.…`` and a
    relative import is neither. So the import statements are dropped and
    their six names are supplied, which is exactly the substitution the port
    made, and everything else is executed verbatim from disk.
    """
    source = ORIGINAL.read_text(encoding="utf-8")
    module = ast.parse(source)
    module.body = [
        node
        for node in module.body
        if not (isinstance(node, ast.ImportFrom) and node.level == 1)
    ]
    namespace: dict[str, object] = {
        "CHAT_SSE_MAX_FRAME_BYTES": 4 * 1024 * 1024,
        "CHAT_SSE_QUEUE_MAX_ITEMS": 8,
        "DESKTOP_RUN_INCIDENT_MAX_PAGE_SIZE": 100,
        "DESKTOP_RUN_MAX_JSON_NESTING": 64,
        "DESKTOP_RUN_MAX_REQUEST_BYTES": 64 * 1024,
        "DESKTOP_RUN_READ_TIMEOUT_SECONDS": 60,
    }
    exec(compile(module, str(ORIGINAL), "exec"), namespace)  # noqa: S102
    return namespace


@pytest.mark.skipif(not ORIGINAL.exists(), reason="the pre-port file is gone")
def test_every_contract_descriptor_matches_the_pre_port_file():
    """§9-14, against the source rather than against a memory of it.

    All four descriptors, not only the chat one: three of them describe
    routes this package does not serve, and a port that quietly edited a
    descriptor it was not implementing would be the easiest way to publish
    a change nobody reviewed.

    **Mutation**: flip any single value or version number in
    ``entry/desktop/wire_contract.py`` ⇒ this fails and names the key.
    """
    before = _pre_port_namespace()
    for name in (
        "desktop_chat_contract",
        "desktop_turn_submission_contract",
        "desktop_turn_observation_contract",
        "desktop_run_contract",
    ):
        expected = before[name]()  # type: ignore[operator]
        actual = getattr(wire_contract, name)()
        assert actual == expected, name
        # Key order too: these are serialised into ``/health`` and a client
        # may be comparing the document, not the mapping.
        assert list(actual) == list(expected), name


@pytest.mark.skipif(not ORIGINAL.exists(), reason="the pre-port file is gone")
def test_the_eight_schema_versions_are_the_pre_port_values():
    before = _pre_port_namespace()
    for name in SCHEMA_VERSION_NAMES:
        assert getattr(wire_contract, name) == before[name], name


def test_the_chat_contract_matches_its_frozen_snapshot():
    """The half of §9-14 that outlives ``omicsclaw/surfaces/``."""
    assert wire_contract.desktop_chat_contract() == FROZEN_CHAT_CONTRACT
    assert list(wire_contract.desktop_chat_contract()) == list(FROZEN_CHAT_CONTRACT)


def test_every_schema_version_is_one():
    """A blunt restatement, and deliberately so.

    The previous two tests both compare against something derived from the
    same repository. This one states the number, so that a change which
    somehow moved both sides together still has to get past a literal.
    """
    for name in SCHEMA_VERSION_NAMES:
        assert getattr(wire_contract, name) == 1, name


def test_the_contract_is_json_serialisable():
    """``/health`` puts all four descriptors in one document."""
    for name in (
        "desktop_chat_contract",
        "desktop_turn_submission_contract",
        "desktop_turn_observation_contract",
        "desktop_run_contract",
    ):
        json.dumps(getattr(wire_contract, name)(), allow_nan=False)


def test_a_fresh_descriptor_is_returned_each_call():
    """"Return a **fresh** … descriptor" is the source's own docstring.

    A caller that mutated a shared dictionary would be editing what every
    later ``/health`` reports.
    """
    first = wire_contract.desktop_chat_contract()
    first["attachments_supported"] = True
    assert wire_contract.desktop_chat_contract()["attachments_supported"] is False


def test_served_paths_names_only_what_is_mounted():
    """Four descriptors, two routes — and the gap is stated, not implied."""
    assert wire_contract.SERVED_PATHS == ("/chat/stream", "/health")


# ---- ``/health`` against the client's own validator ---------------------


def _app_for_health(tmp_path: pathlib.Path, **overrides):
    """A real assembled app, so ``/health`` reports its real facts."""
    return make_app(tmp_path, Scripted(), tools=(), **overrides)


_CURRENT_FULL_STRINGS = (
    "provider",
    "model",
    "python_executable",
    "skill_python_executable",
    "omicsclaw_dir",
    "launch_id",
)
"""``OmicsClaw-App/src/lib/backend-health.ts:199-206``, transcribed.

The client calls a payload carrying *any* of these — or ``skills_count`` —
the "current-full" shape, and then demands **all seven**. So the three this
route used to answer were not a smaller correct payload; they were the
tripwire for a shape check the rest of the payload then failed.
"""


def test_health_answers_every_field_the_client_requires(tmp_path):
    """``:230-239``: all six strings, plus a non-negative integer count.

    Written against the transcribed rule rather than against a frozen
    dictionary because the failure it guards is asymmetric: an extra key
    the client ignores costs nothing, and a missing one makes the desktop
    reject this backend entirely — ``invalid-payload`` for any client,
    ``legacy-shape`` then ``launch-id-mismatch`` for a managed launch.
    """
    app = _app_for_health(tmp_path, launch_id="run-7")
    payload = health_payload(app)

    assert payload["status"] == "ok"
    assert isinstance(payload["version"], str) and payload["version"].strip()
    for field in _CURRENT_FULL_STRINGS:
        assert isinstance(payload[field], str), field
    assert isinstance(payload["skills_count"], int)
    assert payload["skills_count"] >= 0

    assert payload["launch_id"] == "run-7"
    assert payload["python_executable"] == sys.executable
    assert payload["skill_python_executable"] == sys.executable
    assert payload["omicsclaw_dir"] == str(tmp_path)


def test_a_managed_launch_can_tell_this_backend_from_a_leftover_one(tmp_path):
    """``:313``: the launcher compares ``launch_id`` and refuses a mismatch.

    The unauthenticated form carries it too, because the question "is this
    the child I started" has to be answerable before the token is.
    """
    app = _app_for_health(tmp_path, launch_id="run-7")

    assert health_payload(app)["launch_id"] == "run-7"
    assert unauthenticated_health_payload("run-7") == {
        "status": "ok",
        "version": health_payload(app)["version"],
        "launch_id": "run-7",
        "auth_required": True,
    }
    assert unauthenticated_health_payload()["launch_id"] == ""


def test_the_launch_id_comes_from_the_one_deployment_reader(tmp_path):
    """Q8: the route never reads a variable; ``AppConfig`` carries it.

    Naming the variable in ``config.py`` rather than in ``server.py`` is
    what keeps that true, and this is the test that notices if the route
    starts reading it itself.

    Since plan 0037 §5.4 the environment is an **argument**, so this no
    longer mutates the process to say what it means —— which also means
    it now says something slightly stronger: the value reaches
    ``launch_id`` from the mapping it was handed, whatever the machine
    running the test happens to export.
    """
    base = {"OMICSCLAW_WORKSPACE": str(tmp_path)}

    supplied = resolve_app_config(
        [], {**base, "OMICSCLAW_DESKTOP_LAUNCH_ID": "from-the-parent"}
    )
    assert supplied.launch_id == "from-the-parent"

    assert resolve_app_config([], base).launch_id == ""


# ---- the bounded frame renderer -----------------------------------------


@pytest.mark.skipif(not ORIGINAL_SSE.exists(), reason="the pre-port file is gone")
def test_the_frame_renderer_is_byte_identical_to_the_pre_port_one():
    """The port of ``_chat_sse.py`` changed one line's layout and no bytes.

    Compares rendered output, which is the only definition of "unchanged"
    that matters at a wire seam: the source's 100-column string literal was
    wrapped to satisfy the repository's 88-column rule, and implicit
    concatenation makes that a source-layout change rather than a payload
    change. This test is what says so rather than asserting it in a
    comment.
    """
    namespace: dict[str, object] = {}
    exec(  # noqa: S102
        compile(ORIGINAL_SSE.read_text(encoding="utf-8"), str(ORIGINAL_SSE), "exec"),
        namespace,
    )
    before = namespace["render_chat_sse_frame"]
    cases: list[tuple[str, object]] = [
        ("text", "ok"),
        ("done", ""),
        ("error", "RuntimeError"),
        ("tool_result", {"tool_use_id": "c0", "tool_name": "bash", "content": "hi"}),
        (
            "tool_result",
            {
                "tool_use_id": "c1",
                "tool_name": "read",
                "content": "x" * (CHAT_SSE_MAX_FRAME_BYTES + 1),
                "is_error": True,
            },
        ),
        ("tool_use", {"tool_use_id": "c2", "arguments": '{"b":1,"a":2}'}),
        ("status", {"kind": "compaction", "tokens_after": 10}),
        ("text", "中文与 emoji 🧬"),
    ]
    for event_type, data in cases:
        assert render_chat_sse_frame(event_type, data) == before(  # type: ignore
            event_type, data
        ), event_type


def test_a_frame_is_one_data_line_with_exactly_two_keys():
    """``route.ts:88-97`` rejects anything else, by counting the keys."""
    frame = render_chat_sse_frame("text", "hello")
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    payload = json.loads(frame[len("data: ") : -2])
    assert sorted(payload) == ["data", "type"]
    assert payload == {"type": "text", "data": "hello"}


def test_a_frame_is_ascii_so_the_asgi_bytes_are_always_valid_utf8():
    """The source's own reason, kept: a tool may return a lone surrogate."""
    frame = render_chat_sse_frame("text", "\ud800 中文")
    frame.encode("ascii")


def test_an_oversized_tool_result_keeps_its_correlation_identity():
    """``oversize_event_projection: True``, and why it is not truncation.

    A 4 MiB scientific result cannot be cut in half and still be JSON, so
    the renderer replaces the content and keeps the two fields that say
    *which* call this was — otherwise a client holding a pending
    ``tool_use`` never learns it completed.
    """
    frame = render_chat_sse_frame(
        "tool_result",
        {
            "tool_use_id": "call-42",
            "tool_name": "spatial_deconv",
            "content": "x" * (CHAT_SSE_MAX_FRAME_BYTES + 10),
        },
    )
    payload = json.loads(json.loads(frame[len("data: ") : -2])["data"])
    assert payload["tool_use_id"] == "call-42"
    assert payload["tool_name"] == "spatial_deconv"
    assert payload["content_truncated"] is True
    assert utf8_size(frame) <= CHAT_SSE_MAX_FRAME_BYTES


def test_an_oversized_error_stays_an_error():
    """The renderer's own docstring: a failure must not become a clean end.

    An oversized non-terminal frame degrades to ``event_omitted``; an
    oversized ``error`` stays ``error``, because a consumer that saw
    ``event_omitted`` in its place would read the stream as having ended
    successfully.
    """
    huge = "x" * (CHAT_SSE_MAX_FRAME_BYTES + 10)
    assert json.loads(
        render_chat_sse_frame("error", huge)[len("data: ") : -2]
    )["type"] == "error"
    assert json.loads(
        render_chat_sse_frame("text", huge)[len("data: ") : -2]
    )["type"] == "event_omitted"


def test_every_frame_fits_the_declared_bound():
    """``max_sse_frame_bytes`` in the descriptor is a promise about bytes."""
    for data in ("x" * 10, "x" * (CHAT_SSE_MAX_FRAME_BYTES + 1), {"a": "y" * 10}):
        for kind in ("text", "tool_result", "error", "status"):
            assert utf8_size(render_chat_sse_frame(kind, data)) <= (
                CHAT_SSE_MAX_FRAME_BYTES
            )


def test_utf8_size_counts_bytes_not_characters():
    assert utf8_size("abc") == 3
    assert utf8_size("中文") == 6
    # Crosses the internal 16 KiB chunking boundary, which is where a
    # naive implementation splits a multi-byte character in half.
    value = "中" * (_chat_sse._UTF8_COUNT_CHARS + 5)
    assert utf8_size(value) == len(value) * 3


def test_the_queue_capacity_in_the_contract_is_the_renderer_constant():
    """The descriptor reports a real constant, not a retyped number."""
    contract = wire_contract.desktop_chat_contract()
    assert contract["event_queue_capacity"] == CHAT_SSE_QUEUE_MAX_ITEMS
    assert contract["max_sse_frame_bytes"] == CHAT_SSE_MAX_FRAME_BYTES


# ---- trap 13: no optional dependency at import time ----------------------

_PROBE = """
import sys
import omicsclaw.entry.desktop as desktop

leaked = sorted(
    name
    for name in sys.modules
    if name.split(".")[0]
    in {"fastapi", "starlette", "pydantic", "textual", "prompt_toolkit", "multipart"}
)
assert not leaked, leaked
assert desktop.desktop_chat_contract()["sse_schema_version"] == 1
done = desktop.render_chat_sse_frame("done", "")
assert done == 'data: {"type": "done", "data": ""}\\n\\n', done
print("ok")
"""


def test_importing_the_desktop_package_costs_no_web_framework():
    """Trap 13, in a subprocess so an earlier import cannot mask it.

    The wire contract has to be readable where no server is installed —
    which is this repository's own environment — so ``fastapi`` is imported
    inside ``create_desktop_app`` and nowhere else.

    **Mutation**: move ``from fastapi import FastAPI`` to module scope in
    ``entry/desktop/server.py`` ⇒ the import itself fails here, which is
    why the probe runs as a subprocess and asserts on ``returncode``.
    """
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")


def test_building_the_http_app_needs_fastapi_and_says_so():
    """The other half of the same decision: the adapter still needs it.

    Deferring the import must not turn "FastAPI is not installed" into a
    route that silently does nothing.
    """
    pytest.importorskip.__doc__  # keeps the intent local to this test
    try:
        import fastapi  # noqa: F401
    except ModuleNotFoundError:
        from omicsclaw.entry.desktop import create_desktop_app

        with pytest.raises(ModuleNotFoundError):
            create_desktop_app(object())  # type: ignore[arg-type]
    else:  # pragma: no cover - not this machine
        pytest.skip("fastapi is installed here; see test_desktop_http.py")
