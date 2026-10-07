"""The Desktop wire contract v3, as ``GET /health`` publishes it.

The backend defines this contract and versions it; the desktop client
implements the version it names and refuses any other. So the central
assertions here are literals: a change to a version number or a descriptor
field has to get past a test that states the value, which is the reminder
that such a change is a coordinated release with the client.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from omicsclaw.entry.desktop import _chat_sse, wire_contract
from omicsclaw.entry.desktop._chat_sse import (
    CHAT_SSE_MAX_FRAME_BYTES,
    render_chat_sse_frame,
    utf8_size,
)
from omicsclaw.entry.desktop.server import (
    health_payload,
    unauthenticated_health_payload,
)
from omicsclaw.entry.config import resolve_app_config
from omicsclaw.entry.session import attach_sessions
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    make_app,
)

REPO = pathlib.Path(__file__).resolve().parents[2]

CHAT_CONTRACT_V3 = {
    "request_schema_version": 3,
    "sse_schema_version": 3,
    "interrupt_schema_version": 1,
    "authoritative_ingress": True,
    "durable_ingress_idempotency": False,
    "source_request_id_required": True,
    "attachments_supported": False,
    "max_sse_frame_bytes": 4 * 1024 * 1024,
    "oversize_event_projection": True,
    "terminal_error_type_preserved": True,
    "gap_notice": True,
    "abandon_grace_s": None,
}
"""The ``desktop_chat`` descriptor of contract v3, written out.

``durable_ingress_idempotency`` is ``False`` because a redelivery resolves
to the same exchange only while this process holds it. The v1 keys
``event_queue_capacity`` and ``producer_backpressure`` are gone because
nothing in this backend implements them; ``gap_notice`` says a cursor that
falls behind the ring gets an ``event_omitted`` frame. ``abandon_grace_s``
is the running registry's, ``None`` for an app without one.
"""


def test_the_chat_contract_is_v3():
    """Values and key order: the descriptor is serialised into ``/health``
    and a client may be comparing the document, not the mapping."""
    assert wire_contract.desktop_chat_contract() == CHAT_CONTRACT_V3
    assert list(wire_contract.desktop_chat_contract()) == list(CHAT_CONTRACT_V3)


def test_the_three_schema_versions_are_stated_literally():
    """Request and SSE moved to 3 together, for ``resume`` and the ``id:``
    lines; the abort body did not change."""
    assert wire_contract.DESKTOP_CHAT_REQUEST_SCHEMA_VERSION == 3
    assert wire_contract.DESKTOP_CHAT_SSE_SCHEMA_VERSION == 3
    assert wire_contract.DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION == 1


def test_descriptors_for_routes_nobody_serves_are_gone():
    """v1 published ``/v1/turns`` and ``/v1/runs`` descriptors and eight
    version constants for routes this backend never mounted; a descriptor
    that over-promises is how a client ends up calling a 404."""
    for gone in (
        "desktop_run_contract",
        "desktop_turn_observation_contract",
        "desktop_turn_submission_contract",
        "DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION",
        "DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION",
        "DESKTOP_RUN_REQUEST_SCHEMA_VERSION",
        "DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION",
        "DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION",
    ):
        assert not hasattr(wire_contract, gone), gone


def test_the_contract_is_json_serialisable():
    json.dumps(wire_contract.desktop_chat_contract(), allow_nan=False)


def test_a_fresh_descriptor_is_returned_each_call():
    """A caller that mutated a shared dictionary would be editing what every
    later ``/health`` reports."""
    first = wire_contract.desktop_chat_contract()
    first["attachments_supported"] = True
    assert wire_contract.desktop_chat_contract()["attachments_supported"] is False


def test_served_paths_names_the_routes_the_app_mounts():
    assert wire_contract.SERVED_PATHS == (
        "/chat/stream",
        "/chat/permission",
        "/chat/abort",
        "/chat/session-permission-profile",
        "/workspace",
        "/env/doctor",
        "/health",
        "/skills",
        "/skills/{domain}/{name}",
        "/mcp/servers",
        "/providers",
        "/providers/test",
        "/chat/title",
        "/files/tree",
        "/files/serve",
    )


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


def test_health_publishes_only_the_chat_contract(tmp_path):
    """The client gates on ``contracts.desktop_chat.sse_schema_version``."""
    payload = health_payload(_app_for_health(tmp_path))

    assert payload["contracts"] == {"desktop_chat": CHAT_CONTRACT_V3}
    assert payload["served_paths"] == list(wire_contract.SERVED_PATHS)


@pytest.mark.parametrize(
    ("given", "published"),
    [({}, 30.0), ({"abandon_grace_s": 600.0}, 600.0), ({"abandon_grace_s": None}, None)],
)
def test_health_publishes_the_grace_the_registry_runs_with(tmp_path, given, published):
    """A client times its reconnect window from this, so it is the value
    in force, ``None`` meaning an unwatched exchange is never cancelled."""
    app = attach_sessions(_app_for_health(tmp_path), **given)

    chat = health_payload(app)["contracts"]["desktop_chat"]
    assert chat["abandon_grace_s"] == published
    assert chat["abandon_grace_s"] == app.sessions.abandon_grace_s


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


def test_the_frame_bound_in_the_contract_is_the_renderer_constant():
    """The descriptor reports a real constant, not a retyped number."""
    contract = wire_contract.desktop_chat_contract()
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
assert desktop.desktop_chat_contract()["sse_schema_version"] == 3
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



def test_source_build_identity_includes_untracked_runtime_files(tmp_path):
    import runpy
    import shutil
    import subprocess
    from omicsclaw import version

    root = tmp_path / 'source'
    module = root / 'omicsclaw' / 'version.py'
    module.parent.mkdir(parents=True)
    shutil.copyfile(version.__file__, module)

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL)

    git('init')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Test')
    git('add', 'omicsclaw/version.py')
    git('commit', '-m', 'test fixture')
    clean = runpy.run_path(str(module))['build_identity']()
    assert clean['commit'] == git('rev-parse', 'HEAD').decode().strip()
    assert clean['dirty'] is False
    (module.parent / 'new_runtime.py').write_text('value = 1')
    changed = runpy.run_path(str(module))['build_identity']()
    assert changed == {'commit': clean['commit'], 'dirty': True}
