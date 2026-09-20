"""What ``/chat/stream`` accepts, what it refuses, and what a retry means.

Plan 0031 Q24 and §9-15. Two of the three contract facts the desktop client
publishes are decided here — ``source_request_id_required`` and
``durable_ingress_idempotency`` — and they are one promise rather than two: a
field is required *because* a redelivery of it has to resolve to the same
exchange, and a request with no key cannot be given that guarantee.

The refusal codes are published too. A client branches on them, so they are
asserted by value.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from omicsclaw.entry.desktop.server import open_chat_stream
from omicsclaw.entry.desktop.turn_submission import (
    DEFAULT_MAX_JSON_NESTING,
    DEFAULT_MAX_REQUEST_BYTES,
    DesktopIngressError,
    decode_chat_stream_request,
    ingress_identity,
    parse_chat_stream_document,
)
from omicsclaw.entry.ingress import SenderPolicy
from omicsclaw.entry.session import attach_sessions
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    make_app,
)

WAIT_S = 5.0
KEY = "a" * 32
OTHER_KEY = "b" * 32


def document(**overrides) -> dict:
    body = {
        "content": "分析这份 Visium 数据",
        "session_id": "s1",
        "source_request_id": KEY,
    }
    body.update(overrides)
    return body


def app_with_sessions(tmp_path: pathlib.Path):
    return attach_sessions(
        make_app(tmp_path, Scripted(), tools=()), abandon_grace_s=None
    )


async def finish(stream) -> list[str]:
    frames: list[str] = []
    async with stream.body as body:
        async for frame in body:
            frames.append(frame)
    return frames


# ---- the document parser -------------------------------------------------


def test_a_body_over_the_limit_is_refused_before_it_is_parsed():
    body = b'{"content": "' + b"x" * DEFAULT_MAX_REQUEST_BYTES + b'"}'
    with pytest.raises(DesktopIngressError) as caught:
        parse_chat_stream_document(body)
    assert caught.value.code == "request_document_too_large"
    assert caught.value.status_code == 413


def test_a_deeply_nested_body_is_refused_without_recursing():
    """``turn_submission.py:396``. The depth gate runs on the *text*.

    Python's recursion limit is a process setting; whether a document is
    admissible must not be.
    """
    body = ("[" * (DEFAULT_MAX_JSON_NESTING + 5)).encode() + (
        "]" * (DEFAULT_MAX_JSON_NESTING + 5)
    ).encode()
    with pytest.raises(DesktopIngressError) as caught:
        parse_chat_stream_document(body)
    assert caught.value.code == "invalid_request_json"


def test_a_repeated_key_is_a_rejection_and_not_a_merge():
    """Which duplicate wins is a parser's private choice, and the two
    parsers on the two sides of this seam need not have made the same one."""
    with pytest.raises(DesktopIngressError):
        parse_chat_stream_document(b'{"content": "a", "content": "b"}')


def test_a_non_finite_constant_is_refused():
    """``NaN`` is Python's JSON extension, not JSON."""
    with pytest.raises(DesktopIngressError):
        parse_chat_stream_document(b'{"content": "a", "after_seq": NaN}')


def test_a_body_that_is_not_an_object_is_refused():
    with pytest.raises(DesktopIngressError):
        parse_chat_stream_document(b'["content"]')


def test_a_body_that_is_not_utf8_is_refused():
    with pytest.raises(DesktopIngressError) as caught:
        parse_chat_stream_document(b'{"content": "\xff\xfe"}')
    assert caught.value.code == "invalid_request_encoding"


def test_a_well_formed_body_parses():
    assert parse_chat_stream_document(b'{"content":"hi"}') == {"content": "hi"}


# ---- admission -----------------------------------------------------------


def test_an_empty_source_request_id_is_refused():
    """``source_request_id_required: True``.

    **Mutation**: default ``require_source_request_id`` to ``False`` ⇒
    this fails, and so does the idempotency test below, because a request
    with no key cannot resolve to anything.
    """
    with pytest.raises(DesktopIngressError) as caught:
        decode_chat_stream_request(document(source_request_id=""))
    assert caught.value.code == "source_request_id_required"


def test_a_malformed_source_request_id_is_refused():
    """``server.py:1237`` — 32 lowercase hex, or nothing."""
    for bad in ("A" * 32, "a" * 31, "a" * 33, "zz", "a" * 32 + "!"):
        with pytest.raises(DesktopIngressError) as caught:
            decode_chat_stream_request(document(source_request_id=bad))
        assert caught.value.code == "invalid_source_request_id", bad


@pytest.mark.parametrize("field", ["source_request_id", "installation_id"])
@pytest.mark.parametrize("bad", ["\n", "\r\n", "\n\n", "a" * 32 + "\n"])
def test_a_trailing_newline_is_not_a_valid_opaque_id(field: str, bad: str):
    """Python's ``$`` also matches before a trailing newline.

    ``re.match(r"^(?:|[0-9a-f]{32})$", "\\n")`` is truthy — it matches the
    *empty* alternative and then finds ``$`` in front of the newline — and
    one character passes the length guard beside it. So a bare newline was
    a valid idempotency key, concatenated into ``source_namespace`` and
    keyed on by the registry.

    ``installation_id`` is parametrized with it because the two share the
    pattern, and a fix applied to whichever one a test named would leave
    the other one open.
    """
    with pytest.raises(DesktopIngressError) as caught:
        decode_chat_stream_request(document(**{field: bad}))
    assert caught.value.code == f"invalid_{field}", (field, bad)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("files", [{"name": "x.h5ad"}], "attachments_not_supported"),
        ("file_selections", [{"path": "x"}], "file_references_not_supported"),
        ("attachment_descriptors", [{"ordinal": 0}], "file_references_not_supported"),
        ("job_id", "job-1", "remote_job_binding_not_supported"),
        (
            "provider_config",
            {"provider": "openai", "api_key": "sk-x"},
            "per_turn_provider_credentials_not_supported",
        ),
    ],
)
def test_inputs_this_route_never_served_are_refused_by_name(
    field: str, value: object, code: str
):
    """``attachments_supported: False`` is a contract fact, not an omission.

    ``server.py:2023-2032`` states the reason in its own words: a backend
    that reached this branch must "neither persist a second copy nor
    silently drop files the caller believed were uploaded". So the refusal
    is unconditional and comes before every other question.
    """
    with pytest.raises(DesktopIngressError) as caught:
        decode_chat_stream_request(document(**{field: value}))
    assert caught.value.code == code
    assert caught.value.status_code == 409


def test_an_empty_message_is_refused():
    with pytest.raises(DesktopIngressError) as caught:
        decode_chat_stream_request(document(content=""))
    assert caught.value.code == "content_required"


def test_an_unknown_ingress_version_is_refused():
    with pytest.raises(DesktopIngressError):
        decode_chat_stream_request(document(ingress_schema_version=2))


def test_fields_this_layer_does_not_model_are_accepted_and_ignored():
    """A client is allowed to send them; refusing would break it.

    ``server.py:1262-1267`` does the same with ``thread_id`` and ``stage``
    — "accepted but inert". Acting on them instead would be inventing
    behaviour for a field this rebuild does not model.
    """
    request = decode_chat_stream_request(
        document(
            model="claude",
            effort="high",
            thinking={"budget": 1},
            context_1m=True,
            permission_profile="full_access",
            thread_id="t",
            stage="analysis",
            output_style="terse",
        )
    )
    assert request.content == "分析这份 Visium 数据"


def test_the_owner_profile_is_pinned_by_the_backend():
    """``server.py:1274``. The client does not get to choose whose
    conversations it is continuing."""
    request = decode_chat_stream_request(document(profile_id="somebody-else"))
    assert request.to_inbound().sender == "owner"
    assert request.source_namespace.endswith("/owner")
    assert ingress_identity("") == ("local", "owner", "desktop/v1/local/owner")


def test_a_missing_session_id_gets_a_fresh_one():
    first = decode_chat_stream_request(document(session_id=""))
    second = decode_chat_stream_request(document(session_id=""))
    assert first.session_id != second.session_id
    assert len(first.session_id) == 32


# ---- idempotency (§9-15) -------------------------------------------------


def test_a_redelivered_request_resolves_to_the_same_exchange(
    tmp_path: pathlib.Path,
):
    """``durable_ingress_idempotency``: a retry answers, it does not repeat.

    Asserted on the *provider*, not only on the handle: "the same turn_id"
    could be true while a second model call had already been paid for. The
    backend must have been called exactly once.

    **Mutation**: drop the ``source_request_id`` lookup in
    ``SessionRegistry.submit`` ⇒ two turn ids and two provider calls.
    """
    provider = Scripted()
    app = attach_sessions(
        make_app(tmp_path, provider, tools=()), abandon_grace_s=None
    )

    async def scenario() -> tuple[str, str, bool, bool, int, int]:
        first = await open_chat_stream(app, document(), keepalive_s=None)
        await asyncio.wait_for(finish(first), WAIT_S)
        second = await open_chat_stream(app, document(), keepalive_s=None)
        await asyncio.wait_for(finish(second), WAIT_S)
        return (
            first.turn_id,
            second.turn_id,
            first.resumed,
            second.resumed,
            provider.calls,
            len(app.sessions._handles),
        )

    one, two, first_resumed, second_resumed, calls, handles = asyncio.run(scenario())
    assert one == two
    assert first_resumed is False
    assert second_resumed is True
    assert calls == 1
    assert handles == 1


def test_a_different_key_starts_a_second_exchange(tmp_path: pathlib.Path):
    """The other direction of the same rule, which a test that only
    asserted "same key ⇒ same turn" would pass while ignoring every key."""
    app = app_with_sessions(tmp_path)

    async def scenario() -> tuple[str, str]:
        first = await open_chat_stream(app, document(), keepalive_s=None)
        await asyncio.wait_for(finish(first), WAIT_S)
        second = await open_chat_stream(
            app, document(source_request_id=OTHER_KEY), keepalive_s=None
        )
        await asyncio.wait_for(finish(second), WAIT_S)
        return first.turn_id, second.turn_id

    one, two = asyncio.run(scenario())
    assert one != two


def test_the_idempotency_key_is_scoped_to_its_namespace(tmp_path: pathlib.Path):
    """``server.py:2051-2055`` looked a redelivery up by the **triple**
    ``(surface, source_namespace, source_request_id)``.

    :meth:`SessionRegistry.submit` keys on ``(session_id, id)``, which
    does not separate two installations sharing one session id, so the
    namespace is folded into the key by ``ChatStreamRequest.to_inbound``.
    Two installations that minted the same 32-hex id would otherwise
    resolve to each other's exchange — a retry that answers a different
    person's question.

    **Mutation**: return the bare ``source_request_id`` from
    ``to_inbound`` ⇒ the two turn ids collapse into one.
    """
    app = app_with_sessions(tmp_path)

    async def scenario() -> tuple[str, str]:
        first = await open_chat_stream(
            app, document(installation_id="c" * 32), keepalive_s=None
        )
        await asyncio.wait_for(finish(first), WAIT_S)
        second = await open_chat_stream(
            app, document(installation_id="d" * 32), keepalive_s=None
        )
        await asyncio.wait_for(finish(second), WAIT_S)
        return first.turn_id, second.turn_id

    one, two = asyncio.run(scenario())
    assert one != two


def test_one_key_in_two_sessions_streams_two_exchanges(tmp_path: pathlib.Path):
    """A key reused across conversations must not cross the streams.

    The same client, two chats, one request id — ordinary whenever a
    client numbers requests per conversation. A registry keyed on the id
    alone hands the second request the *first* conversation's handle, and
    this route then returns that exchange's SSE stream: its deltas, its
    tool arguments and its tool outputs, to a caller asking about
    something else.

    Asserted on ``session_id`` as well as ``turn_id``, because "two turn
    ids" could be true while both belonged to one conversation.
    """
    app = app_with_sessions(tmp_path)

    async def scenario() -> tuple[str, str, str, str]:
        first = await open_chat_stream(
            app, document(session_id="mine"), keepalive_s=None
        )
        await asyncio.wait_for(finish(first), WAIT_S)
        second = await open_chat_stream(
            app, document(session_id="theirs"), keepalive_s=None
        )
        await asyncio.wait_for(finish(second), WAIT_S)
        return first.turn_id, second.turn_id, first.session_id, second.session_id

    one, two, mine, theirs = asyncio.run(scenario())
    assert one != two
    assert (mine, theirs) == ("mine", "theirs")


# ---- admission control ---------------------------------------------------


def test_a_sender_outside_the_policy_creates_no_exchange(tmp_path: pathlib.Path):
    """Plan 0031 §9-9(b): the obligation is to create no turn.

    Asserted by counting exchanges rather than by reading a refusal
    message, because a Surface that politely declined *after* submitting
    would pass the second check and fail the first.
    """
    app = app_with_sessions(tmp_path)
    policy = SenderPolicy(allowed_senders=frozenset({"somebody-else"}))

    async def scenario() -> tuple[str, int]:
        with pytest.raises(DesktopIngressError) as caught:
            await open_chat_stream(app, document(), policy=policy)
        return caught.value.code, len(app.sessions._handles)

    code, handles = asyncio.run(scenario())
    assert code == "sender_not_allowed"
    assert handles == 0


def test_the_owner_named_by_the_policy_is_admitted(tmp_path: pathlib.Path):
    """The tightening direction needs its opposite, or the test passes for
    a policy that admits nobody at all."""
    app = app_with_sessions(tmp_path)
    policy = SenderPolicy(allowed_senders=frozenset({"owner"}))

    async def scenario() -> int:
        stream = await open_chat_stream(app, document(), policy=policy)
        await asyncio.wait_for(finish(stream), WAIT_S)
        return len(app.sessions._handles)

    assert asyncio.run(scenario()) == 1


def test_a_request_for_another_workspace_is_refused(tmp_path: pathlib.Path):
    """``server.py:2091-2102``. Answering it from the configured workspace
    would run tools against files the caller did not mean."""
    app = app_with_sessions(tmp_path)

    async def scenario() -> tuple[str, int, int]:
        with pytest.raises(DesktopIngressError) as caught:
            await open_chat_stream(
                app, document(workspace=str(tmp_path / "elsewhere"))
            )
        return caught.value.code, caught.value.status_code, len(app.sessions._handles)

    code, status, handles = asyncio.run(scenario())
    assert code == "workspace_does_not_match_backend_runtime"
    assert status == 409
    assert handles == 0


def test_the_configured_workspace_is_accepted(tmp_path: pathlib.Path):
    app = app_with_sessions(tmp_path)

    async def scenario() -> str:
        stream = await open_chat_stream(
            app, document(workspace=str(tmp_path)), keepalive_s=None
        )
        await asyncio.wait_for(finish(stream), WAIT_S)
        return stream.turn_id

    assert asyncio.run(scenario())


def test_an_app_without_a_registry_says_which_call_is_missing(
    tmp_path: pathlib.Path,
):
    """``build_app`` leaves ``sessions=None`` on purpose; the error has to
    name ``attach_sessions`` or the next person reads it as a bug."""
    app = make_app(tmp_path, Scripted(), tools=())

    async def scenario() -> str:
        with pytest.raises(RuntimeError) as caught:
            await open_chat_stream(app, document())
        return str(caught.value)

    assert "attach_sessions" in asyncio.run(scenario())


def test_a_refused_request_leaks_nothing_about_the_deployment():
    """Q22 rule 1 at the ingress: a code, never a path or a payload."""
    for bad in (
        document(content=""),
        document(source_request_id="nope"),
        document(files=[{"name": "/home/someone/private.h5ad"}]),
    ):
        with pytest.raises(DesktopIngressError) as caught:
            decode_chat_stream_request(bad)
        rendered = str(caught.value)
        assert "/" not in rendered
        assert json.dumps(bad) not in rendered
