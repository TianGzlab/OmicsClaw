"""Nine rules every authoritative channel adapter obeys, on every adapter.

The suite walks ``CHANNEL_REGISTRY``, keeps the adapters that declare
``authoritative_ingress``, and holds each one to the same nine assertions
over the fixture it published in :mod:`tests.entry.channel_conformance`.
Declaring the flag and registering a fixture are therefore the same act — an
adapter that claims the first without the second fails here by name.

This is what replaces a shared base class. The nine rules are exactly the
places where seven similar implementations would otherwise diverge silently:
a reply target whose two halves disagree, a timeout classified as retryable,
a group gate that is always open, a slash command that reaches the model, a
Markdown asterisk in a client that renders none. None of them raises; all of
them look like a bot behaving slightly oddly.

Sibling suites stay: ``test_channel_adapters.py`` and each
``test_channel_<platform>.py`` test what is **particular** to a platform —
two mention spellings, an SDK thread, a gateway callback name. This file
tests only what they all share.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import pathlib

import pytest

from omicsclaw.entry.channel import CHANNEL_REGISTRY, get_channel_class
from omicsclaw.entry.channel.binding import ChannelSurfaceBinding
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from omicsclaw.entry.channel.commands import registered_commands
from omicsclaw.entry.channel.runtime import ChannelRuntime, TurnAcceptanceStatus
from omicsclaw.entry.ingress import VALUE_CHAT_TYPE, VALUE_MENTIONS
from omicsclaw.schema import Message, Role, ToolCall
from tests.entry.channel_conformance import (  # type: ignore[import-not-found]
    FIXTURES,
    MENTION_GUARDED_ADAPTERS,
    MENTION_PROBE,
    REQUIRED_DELIVERY_CASES,
    RETRYABLE_DELIVERY_CASE,
)
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    Transport,
    deployment,
)
from tests.entry.test_channel_runtime import (  # type: ignore[import-not-found]
    deployment as deployment_with_tools,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
)

WAIT_S = 5.0
MARKDOWN_PROBE = "**bold** and `code`"


def _publish_every_fixture() -> None:
    """Import the per-platform test modules so their fixtures register.

    Discovered rather than listed, which is what lets a newly lit adapter
    join this suite by adding its own test file and nothing else. Importing
    a test module is what pytest is about to do anyway; doing it here only
    fixes the order.
    """
    here = pathlib.Path(__file__)
    for path in sorted(here.parent.glob("test_channel_*.py")):
        if path.name == here.name:
            continue
        importlib.import_module(f"tests.entry.{path.stem}")


_publish_every_fixture()


def authoritative_adapters() -> list[str]:
    """Every registry name whose class declares authoritative ingress."""
    return sorted(
        name
        for name in CHANNEL_REGISTRY
        if get_channel_class(name).authoritative_ingress
    )


AUTHORITATIVE = authoritative_adapters()


def fixture_for(name: str):
    fixture = FIXTURES.get(name)
    assert fixture is not None, (
        f"{name!r} declares authoritative_ingress but published no conformance "
        "fixture; an adapter that can be started has to be one this suite can "
        "drive"
    )
    return fixture


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


async def bind(fixture, tmp_path):
    """One adapter, one runtime, one recording transport, ingress open.

    The binding's own delivery adapter is replaced by the transport so that
    "the reply left" is observable; everything else about the binding is the
    adapter's own, including the sender policy the gates read.
    """
    app, spy = deployment(tmp_path)
    channel = fixture.new_channel()
    binding = await channel.prepare_control_binding()
    transport = Transport()
    runtime = ChannelRuntime(
        app, [dataclasses.replace(binding, delivery_adapter=transport)]
    )
    await runtime.start()
    channel.bind_control_runtime(runtime, loop=asyncio.get_running_loop())
    channel._running = True
    channel.activate_ingress()
    return channel, runtime, app, spy, transport, binding


async def settle(app) -> None:
    """Wait for whatever the last submission started, bounded by the caller."""
    for handle in app.sessions.running():
        await handle.wait()


# ---- 1: the binding ----------------------------------------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_the_binding_names_the_same_adapter_the_channel_does(name, tmp_path):
    """Rule 1. The binding is how an inbound message finds its way out.

    ``ChannelRuntime`` indexes bindings by adapter name and looks one up by
    the surface the message names. A binding whose ``adapter`` disagreed
    with ``Channel.name`` would make every message on that platform land in
    ``CODE_UNKNOWN_ADAPTER`` — one warning per message, and no reply.
    """
    fixture = fixture_for(name)

    async def scenario():
        channel = fixture.new_channel()
        return channel, await channel.prepare_control_binding()

    channel, binding = run(scenario())

    assert isinstance(binding, ChannelSurfaceBinding)
    assert binding.adapter == channel.name == name
    assert binding.account_namespace
    assert binding.attachment_input_enabled is False
    assert binding.text_chunk_limit > 20


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_every_normalised_message_names_its_own_surface(name, tmp_path):
    """Rule 1, the other end of the same key.

    ``Channel.inbound`` lets a caller override the surface, and an adapter
    that passed a qualified name such as ``f"{name}-{backend}"`` would
    produce a message the binding, keyed by the plain adapter name, could
    never route.
    """
    fixture = fixture_for(name)

    async def scenario():
        channel, runtime, app, spy, _transport, _binding = await bind(
            fixture, tmp_path
        )
        await fixture.submit(channel, text="analyse this", sender=fixture.owner)
        await settle(app)
        await runtime.close(WAIT_S)
        return spy

    spy = run(scenario())

    assert [message.surface for message in spy.delivered] == [name]


# ---- 2: there is only one way in and one way out -----------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_the_second_path_in_and_out_is_closed(name, tmp_path):
    """Rule 2. Four members that used to be a whole second ingress.

    Written to hold both before and after the base-class implementations are
    deleted: a member that is gone is as closed as one that refuses, and
    "there is no such method" is the stronger of the two.
    """
    fixture = fixture_for(name)
    calls = {
        "process_message": ("c", "u", "hi"),
        "send": ("c", "hi"),
        "_send_chunk": ("c", "hi", "hi", {}),
        "send_media": ("c", "/tmp/not-a-file"),
    }

    async def scenario():
        channel = fixture.new_channel()
        for member_name, args in calls.items():
            member = getattr(channel, member_name, None)
            if member is None:
                continue
            with pytest.raises(RuntimeError):
                await member(*args)

    run(scenario())


# ---- 3: what a failed send is allowed to mean --------------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_only_a_named_rate_limit_is_ever_retryable(name, tmp_path):
    """Rule 3. ``deliver`` retries exactly one outcome, so only one may say so.

    A timeout and an unanticipated exception both mean *we do not know*: the
    message may already be in front of the person, and a second copy is
    worse than a missing one because nothing downstream can see it. Only a
    refusal the platform named — a rate limit, with or without a hint — is
    evidence that nothing was delivered.

    A platform whose protocol has no such refusal declares that, and is then
    held to having **no** retryable outcome at all rather than to having one.
    """
    fixture = fixture_for(name)
    cases = {case.label: case for case in fixture.delivery_cases()}

    required = list(REQUIRED_DELIVERY_CASES)
    if fixture.has_retryable_refusal:
        required.append(RETRYABLE_DELIVERY_CASE)
    missing = [label for label in required if label not in cases]
    assert not missing, f"{name} published no delivery case for {missing}"

    async def scenario():
        channel = fixture.new_channel()
        target = fixture.reply_target(channel)
        results = {}
        for label, case in cases.items():
            results[label] = await case.adapter(
                DeliveryAttemptRequest(
                    item_id="conformance-0", text="hello", reply_target=target
                )
            )
        return results

    results = run(scenario())

    for label, case in cases.items():
        assert results[label].outcome is case.expected, label
    assert results["timeout"].outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    assert results["unknown"].outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    retryable = sorted(label for label, r in results.items() if r.retryable)
    assert retryable == (
        [RETRYABLE_DELIVERY_CASE] if fixture.has_retryable_refusal else []
    )


# ---- 4: the two halves of a reply target agree -------------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_the_target_the_inbound_path_builds_is_one_this_platform_accepts(
    name, tmp_path
):
    """Rule 4. Construction and validation are one piece of knowledge.

    They live several layers and one exchange apart, so a disagreement over
    a key name is not an exception — it is a permanent rejection, one log
    line, and a bot that stops mid-answer.
    """
    fixture = fixture_for(name)
    adapter, _sent = fixture.accepting_delivery()

    async def scenario():
        channel = fixture.new_channel()
        target = fixture.reply_target(channel)
        result = await adapter(
            DeliveryAttemptRequest(
                item_id="conformance-0", text="hello", reply_target=target
            )
        )
        return target, result

    target, result = run(scenario())

    assert target["schema_version"] == 1
    assert target["kind"] == "channel"
    assert target["adapter"] == name
    assert target["destination_id"]
    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED, result.error_code


# ---- 5: nobody outside the allowlist ----------------------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_a_sender_outside_the_allowlist_creates_no_exchange_and_no_reply(
    name, tmp_path
):
    """Rule 5. Not a polite refusal — nothing at all.

    Answering an unknown sender tells them the bot exists, that somebody is
    listening, and that their identity was checked against a list.
    """
    fixture = fixture_for(name)

    async def scenario():
        channel, runtime, app, spy, transport, _binding = await bind(
            fixture, tmp_path
        )
        await fixture.submit(channel, text="analyse this", sender=fixture.stranger)
        await settle(app)
        await runtime.close(WAIT_S)
        return spy, transport, channel

    spy, transport, channel = run(scenario())

    assert spy.delivered == []
    assert transport.sent == []
    assert fixture.direct_replies(channel, transport) == []


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_a_stranger_gets_nothing_from_a_registered_command_either(name, tmp_path):
    """Rule 5, on the path rule 7 opens.

    A slash command is answered by a direct provider call that reaches
    neither the rate limiter nor the ingress gate, so "outside the
    allowlist" has to be decided before the command runs rather than after.
    Probing only with prose (above) and only as the owner (rule 7) leaves
    exactly this intersection untested, and what an unchecked ``/files``,
    ``/outputs`` or ``/recent`` hands a stranger is real workspace
    filenames, sizes and report titles.

    Nothing at all is the assertion, same as above: an answer — even a
    refusal — tells an unknown sender that the bot exists and that their id
    was checked.
    """
    fixture = fixture_for(name)
    assert "/skills" in registered_commands()

    async def scenario():
        channel, runtime, app, spy, transport, _binding = await bind(
            fixture, tmp_path
        )
        await fixture.submit(channel, text="/skills", sender=fixture.stranger)
        await settle(app)
        answered = list(fixture.direct_replies(channel, transport))
        await runtime.close(WAIT_S)
        return spy, transport, answered

    spy, transport, answered = run(scenario())

    assert spy.delivered == [], "a stranger's command must not become an exchange"
    assert transport.sent == []
    assert answered == [], "and must not be answered on any path"


# ---- 6: a group message has to prove it was addressed here -------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_a_group_message_must_prove_it_was_aimed_at_this_bot(name, tmp_path):
    """Rule 6. Fail closed, in whichever of the two shapes applies.

    On a platform with groups: an owner @-mentioning a colleague in a shared
    room must not make this agent answer. On a platform without them the
    claim is stronger and is asserted directly — the bot has no identity to
    attribute a mention to, so any message that arrives labelled as a group
    message is refused rather than answered to whoever spoke.
    """
    fixture = fixture_for(name)

    async def scenario():
        channel, runtime, app, spy, transport, binding = await bind(
            fixture, tmp_path
        )
        if fixture.has_groups:
            await fixture.submit(
                channel,
                text="what do you think",
                sender=fixture.owner,
                group=True,
                mentions_bot=False,
            )
            refusal = None
        else:
            assert binding.sender_policy.bot_identity == "", (
                "a 1:1 platform must leave bot_identity empty, so that a "
                "message labelled as a group message fails closed"
            )
            refusal = await runtime.submit(
                channel.inbound(
                    "conformance-chat",
                    fixture.owner,
                    "what do you think",
                    source_request_id="conformance-group-1",
                    reply_target=dict(fixture.reply_target(channel)),
                    values={VALUE_CHAT_TYPE: "group", VALUE_MENTIONS: ()},
                )
            )
        await settle(app)
        await runtime.close(WAIT_S)
        return spy, transport, refusal

    spy, transport, refusal = run(scenario())

    assert spy.delivered == []
    assert transport.sent == []
    if refusal is not None:
        assert refusal.acceptance.status is TurnAcceptanceStatus.REJECTED


# ---- 7: a slash command is answered, not modelled ----------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_a_registered_command_is_answered_without_a_model_call(name, tmp_path):
    """Rule 7. Twelve built-ins that used to work on one platform only.

    ``/clear`` reaching the model is not an error anybody sees: the person
    gets a paragraph explaining the word "clear" and their conversation is
    still there.
    """
    fixture = fixture_for(name)
    assert "/skills" in registered_commands()

    async def scenario():
        channel, runtime, app, spy, transport, _binding = await bind(
            fixture, tmp_path
        )
        await fixture.submit(channel, text="/skills", sender=fixture.owner)
        await settle(app)
        answered = list(fixture.direct_replies(channel, transport))
        await runtime.close(WAIT_S)
        return spy, answered

    spy, answered = run(scenario())

    assert spy.delivered == [], "a registered command must not become an exchange"
    assert answered, "and the person has to be told what it said"


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_something_that_is_not_a_registered_command_still_reaches_the_agent(
    name, tmp_path
):
    """Rule 7's other half, so the refusal above is not vacuous.

    Which text proves it depends on how the platform routes commands. Where
    they are detected by text prefix, an unregistered ``/verb`` is ordinary
    text and must reach the model — that is ``dispatch``'s own contract.
    Where the platform routes only the verbs registered with it, an unknown
    one reaches no handler at all, so ordinary prose carries the proof.
    """
    fixture = fixture_for(name)
    probe = (
        "/definitely-not-a-registered-command"
        if fixture.unregistered_commands_reach_the_agent
        else "analyse this"
    )

    async def scenario():
        channel, runtime, app, spy, _transport, _binding = await bind(
            fixture, tmp_path
        )
        await fixture.submit(channel, text=probe, sender=fixture.owner)
        await settle(app)
        await runtime.close(WAIT_S)
        return spy

    spy = run(scenario())

    assert [message.text for message in spy.delivered] == [probe]


# ---- 8: the platform is handed text it can render ----------------------


@pytest.mark.parametrize("name", AUTHORITATIVE)
def test_outbound_text_is_formatted_for_the_platform_that_receives_it(
    name, tmp_path
):
    """Rule 8. The one regression the acceptance classification cannot see.

    Two platforms render no Markdown at all, and the old outbound path
    reduced it for them in a hook the reply pump does not call. Moving that
    duty into the delivery adapter is what keeps a cut-over from filling
    those clients with asterisks — and rule 3 would stay green throughout,
    because an asterisk is accepted just as happily as a word.
    """
    fixture = fixture_for(name)
    adapter, sent = fixture.accepting_delivery()

    async def scenario():
        channel = fixture.new_channel()
        return await adapter(
            DeliveryAttemptRequest(
                item_id="conformance-0",
                text=MARKDOWN_PROBE,
                reply_target=fixture.reply_target(channel),
            )
        )

    result = run(scenario())

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED
    assert len(sent) == 1
    if fixture.strips_markdown:
        assert "*" not in sent[0] and "`" not in sent[0]
        assert "bold" in sent[0] and "code" in sent[0]
    else:
        assert sent[0] == MARKDOWN_PROBE


# ---- 9: nothing the bot sends notifies a room --------------------------

MENTION_GUARDED = sorted(
    name
    for name in AUTHORITATIVE
    if name in FIXTURES and FIXTURES[name].mention_guard is not None
)
MENTION_CHUNK_LIMIT = 100
"""Small enough that a reply of several probes leaves in several chunks."""


def notifies_nobody(call, guard) -> bool:
    """Whether one provider call leaves no live mention for the platform to act on."""
    return not call.notifies or not any(
        spelling in call.text for spelling in guard.live_spellings
    )


async def bind_guarded(fixture, tmp_path, *, provider=None, tools=(), **overrides):
    """One adapter bound to a runtime that delivers through its mention guard.

    Unlike :func:`bind`, the binding keeps a real platform delivery adapter,
    because what is under test is what that adapter hands the provider.
    """
    adapter, calls = fixture.mention_guard.accepting_delivery()
    app = deployment_with_tools(tmp_path, provider, tools=tools, **overrides)
    channel = fixture.new_channel()
    binding = await channel.prepare_control_binding()
    runtime = ChannelRuntime(
        app,
        [
            dataclasses.replace(
                binding,
                delivery_adapter=adapter,
                text_chunk_limit=MENTION_CHUNK_LIMIT,
            )
        ],
    )
    await runtime.start()
    channel.bind_control_runtime(runtime, loop=asyncio.get_running_loop())
    channel._running = True
    channel.activate_ingress()
    return channel, runtime, app, calls


def test_every_platform_that_renders_mentions_declares_how_it_neutralises_them():
    """Rule 9 cannot be skipped by leaving a fixture's guard out.

    The rule is parametrised over the fixtures that declare a guard, so a
    fixture that dropped its own would otherwise leave that platform
    untested while the suite stayed green.
    """
    assert set(MENTION_GUARDED) == MENTION_GUARDED_ADAPTERS
    for name in MENTION_GUARDED:
        spellings = fixture_for(name).mention_guard.live_spellings
        assert spellings, name
        for spelling in spellings:
            assert spelling in MENTION_PROBE, (name, spelling)


@pytest.mark.parametrize("name", MENTION_GUARDED)
def test_a_mention_in_outbound_text_notifies_nobody(name):
    """Rule 9 (plan 0052 A11). The model writes every word the bot sends.

    An answer and an approval card are both model text, and since the card
    carries the command and its arguments, a prompt-injected model can put
    ``<!channel>`` or ``@everyone`` in front of a whole room. No reply has a
    legitimate reason to notify everybody, so the delivery adapter
    neutralises mentions on every send rather than on some.
    """
    fixture = fixture_for(name)
    guard = fixture.mention_guard
    adapter, calls = guard.accepting_delivery()

    async def scenario():
        channel = fixture.new_channel()
        return await adapter(
            DeliveryAttemptRequest(
                item_id="conformance-0",
                text=MENTION_PROBE,
                reply_target=fixture.reply_target(channel),
            )
        )

    result = run(scenario())

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED, result.error_code
    assert len(calls) == 1
    assert notifies_nobody(calls[0], guard), calls[0]


@pytest.mark.parametrize("name", MENTION_GUARDED)
def test_every_chunk_of_a_long_reply_notifies_nobody(name, tmp_path):
    """Rule 9 on the reply pump's own path, where an answer is chunked.

    Each chunk is a separate provider call, so a guard applied to the
    first chunk only, or to the text before it was chunked, leaves the
    rest of the answer live.
    """
    fixture = fixture_for(name)
    answer = "\n\n".join([MENTION_PROBE] * 4)
    provider = Scripted(Message(role=Role.ASSISTANT, content=answer))

    async def scenario():
        channel, runtime, app, calls = await bind_guarded(
            fixture, tmp_path, provider=provider
        )
        await fixture.submit(channel, text="analyse this", sender=fixture.owner)
        await settle(app)
        await runtime.close(WAIT_S)
        return calls

    calls = run(scenario())

    assert len(calls) > 1, "the reply was meant to leave in several chunks"
    guard = fixture.mention_guard
    assert all(notifies_nobody(call, guard) for call in calls), calls


@pytest.mark.parametrize("name", MENTION_GUARDED)
def test_an_approval_card_carrying_a_mention_notifies_nobody(name, tmp_path):
    """Rule 9 on the approval card, which shows the call's arguments.

    The arguments are chosen by the model, so this is the path an injected
    instruction takes to put a mention in front of a group that never asked
    for the tool.
    """
    fixture = fixture_for(name)
    provider = Scripted(
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(
                    id="c0",
                    name="ask",
                    arguments=json.dumps({"command": MENTION_PROBE}),
                ),
            ),
        ),
        Message(role=Role.ASSISTANT, content="done"),
    )

    async def scenario():
        channel, runtime, app, calls = await bind_guarded(
            fixture,
            tmp_path,
            provider=provider,
            tools=(Asking(),),
            approval_timeout_s=0.05,
        )
        await fixture.submit(channel, text="analyse this", sender=fixture.owner)
        await settle(app)
        await runtime.close(WAIT_S)
        return calls

    calls = run(scenario())

    assert any("Approval required" in call.text for call in calls), calls
    # The card is chunked like any other text, so its arguments may arrive in
    # a later call than its header. Nothing but the arguments says "everyone".
    assert any("everyone" in call.text for call in calls), (
        "the card's arguments never reached the platform"
    )
    guard = fixture.mention_guard
    assert all(notifies_nobody(call, guard) for call in calls), calls


@pytest.mark.parametrize("name", MENTION_GUARDED)
def test_command_output_carrying_a_mention_notifies_nobody(name, tmp_path):
    """Rule 9 on the one direct send outside an exchange.

    Command output is chunked and sent by the channel itself, not by the
    reply pump, and a workspace listing can contain any file name.
    """
    fixture = fixture_for(name)
    listing = "\n\n".join([MENTION_PROBE] * 4)

    async def scenario():
        channel, runtime, _app, calls = await bind_guarded(fixture, tmp_path)
        await channel.send_command_output(fixture.reply_target(channel), listing)
        await runtime.close(WAIT_S)
        return calls

    calls = run(scenario())

    assert len(calls) > 1, "the listing was meant to leave in several chunks"
    guard = fixture.mention_guard
    assert all(notifies_nobody(call, guard) for call in calls), calls


# ---- no adapter invents a thread boundary it does not have -------------


def test_only_the_adapter_whose_sdk_uses_a_thread_hops_between_loops():
    """A source probe, and the reason it is one: the defect is copied, not written.

    Feishu needs ``run_coroutine_threadsafe`` because ``lark-oapi`` delivers
    its callbacks on its own WebSocket thread, and an asyncio primitive
    belongs to the loop that created it. No other SDK here does that —
    discord.py, slack_sdk's aiohttp Socket Mode, botpy and ``websockets``
    all run on the loop they were started from, and the
    blocking calls in the email adapter are awaited back through an executor
    rather than delivered as callbacks.

    Copying the hop anyway would add a thread boundary to a single-threaded
    adapter, which costs nothing visible and is impossible to find later.
    """
    package = pathlib.Path(__file__).resolve().parents[2] / "omicsclaw/entry/channel"
    offenders = sorted(
        path.name
        for path in package.glob("*.py")
        if path.name != "feishu.py"
        and "run_coroutine_threadsafe" in path.read_text(encoding="utf-8")
    )

    assert offenders == [], (
        f"{offenders} hop between loops; only the Feishu adapter has an SDK "
        "thread to hop from"
    )


# ---- the registry itself -----------------------------------------------


def test_every_registered_adapter_is_either_authoritative_or_named_as_not():
    """The registry and the gate cannot drift apart unnoticed.

    ``require_authoritative_ingress`` is what refuses a start-up, and this
    suite is what an adapter has to pass to lift that refusal. Listing the
    names here makes the count a fact in the suite rather than a claim in a
    document.
    """
    assert AUTHORITATIVE, "no adapter declares authoritative ingress"
    assert set(AUTHORITATIVE) <= set(CHANNEL_REGISTRY)
    for name in AUTHORITATIVE:
        assert name in FIXTURES, name
