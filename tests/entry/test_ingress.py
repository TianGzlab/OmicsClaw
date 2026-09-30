"""The edge: who is admitted, and whether a reply landed.

The acceptance this file is written against (plan 0031 §9-9) is unusual
in one respect worth stating, because it changes what the assertions look
like: it pins the **tightening** direction. "There is a test for the
allowlist" is not the property — a test that a refused sender gets a
polite refusal message would satisfy that sentence while the turn ran
anyway. What is asserted instead is that a refused message produces
**nothing**: :meth:`SenderPolicy.admits` answers ``False`` and the caller's
obligation is to create no turn at all.

Plan 0028's lesson in the handover is the same shape: "having a test" is
not "being wired up", and the wiring has to be pinned in the direction
that closes rather than the direction that opens.
"""

from __future__ import annotations

import dataclasses

import pytest

from omicsclaw.entry.ingress import (
    GROUP_CHAT_TYPES,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
    Acceptance,
    DeliveryResult,
    InboundMessage,
    SenderPolicy,
    parse_senders,
)

OWNER = "ou_owner"
BOT = "ou_this_bot"


def _message(**overrides: object) -> InboundMessage:
    fields: dict[str, object] = {
        "text": "hello",
        "session_id": "s1",
        "source_request_id": "req-1",
        "sender": OWNER,
    }
    fields.update(overrides)
    return InboundMessage(**fields)  # type: ignore[arg-type]


def _policy(**overrides: object) -> SenderPolicy:
    fields: dict[str, object] = {"allowed_senders": frozenset({OWNER})}
    fields.update(overrides)
    return SenderPolicy(**fields)  # type: ignore[arg-type]


# ---- InboundMessage --------------------------------------------------


def test_an_idempotency_key_is_not_optional():
    """``source_request_id`` has no default, and the reason is a retry.

    The desktop client's published contract declares
    ``durable_ingress_idempotency``: a redelivered request must resolve to
    the same turn. A default would make "the surface forgot to send one"
    look exactly like "this is a new message", and the symptom — one
    question answered twice — only appears under the retry nobody
    reproduces deliberately.
    """
    with pytest.raises(TypeError):
        InboundMessage(text="hi", session_id="s1")  # type: ignore[call-arg]


def test_the_optional_fields_default_to_empty_and_the_values_map_is_empty():
    message = InboundMessage(text="hi", session_id="s1", source_request_id="r")

    assert message.sender == ""
    assert message.surface == ""
    assert dict(message.values) == {}


def test_an_inbound_message_cannot_be_edited_after_submission():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _message().text = "something else"  # type: ignore[misc]


# ---- SenderPolicy: the tightening direction --------------------------


def test_a_policy_cannot_be_constructed_without_an_allowlist():
    """Omitting it is a :exc:`TypeError`, which is the whole design.

    ``FEISHU_ALLOWED_SENDERS`` is required: authoritative Feishu ingress
    admits nobody else and refuses to start without it.
    A keyword with a default is a keyword that gets omitted.
    """
    with pytest.raises(TypeError):
        SenderPolicy()  # type: ignore[call-arg]


def test_an_empty_allowlist_refuses_to_start():
    """Fail-closed is not enough when it is also silent.

    ``frozenset()`` would already admit nobody. That is the failure being
    prevented: a bot that admits nobody is indistinguishable from a bot
    nobody has messaged, so an unset variable parsed to an empty set
    would be discovered days later rather than at start-up.
    """
    with pytest.raises(ValueError):
        SenderPolicy(allowed_senders=frozenset())


def test_an_owner_in_a_direct_chat_is_admitted():
    assert _policy().admits(_message()) is True


def test_a_sender_outside_the_allowlist_produces_nothing():
    """The answer is ``False`` — not a refusal message, not a turn."""
    assert _policy().admits(_message(sender="ou_stranger")) is False


def test_an_unidentified_sender_is_never_admitted():
    """An allowlist never contains ``""``, and this pins that it cannot.

    A platform that fails to report a sender is the case where an
    ``in`` test against a set that happened to contain an empty string
    would open the gate to everybody at once.
    """
    assert _policy().admits(_message(sender="")) is False
    assert _policy(allowed_senders=frozenset({""})).admits(_message(sender="")) is False


# ---- SenderPolicy: group attribution ---------------------------------


def _group(**values: object) -> InboundMessage:
    return _message(values={VALUE_CHAT_TYPE: "group", **values})


def test_a_group_message_is_refused_when_this_bot_has_no_identity():
    """Group chats fail closed without ``FEISHU_BOT_OPEN_ID``.

    Without ``FEISHU_BOT_OPEN_ID`` there is no way to tell a mention of
    this agent from a mention of another participant, so an owner's
    message in a group that was addressed to somebody else would start a
    turn here.
    """
    assert _policy().admits(_group(**{VALUE_MENTIONS: [BOT]})) is False


def test_a_bot_with_no_identity_refuses_every_group_message():
    """§9-9(c)'s fail-closed gate, pinned where deleting it actually shows.

    The test above reads like this one and does not pin the gate: with
    the gate removed, the mention check below it answers
    ``"" in {"ou_this_bot"}`` — ``False``, for the wrong reason. Deleting
    ``if not self.bot_identity: return False`` therefore left the whole
    suite green, which made this the one surviving mutant of its round.

    The case that separates them is an empty identity *among* the
    mentions, which is what a platform sends when it could not attribute
    one and what an absent gate reads as "this bot was addressed". Every
    group spelling is covered because the gate is centralised here
    precisely so that seven adapters are not seven chances to forget it.
    """
    policy = SenderPolicy(allowed_senders=frozenset({OWNER}), bot_identity="")
    mention_lists: tuple[object, ...] = ((), ("",), (OWNER,), ("", BOT), [BOT])

    for chat_type in sorted(GROUP_CHAT_TYPES):
        assert policy.admits(_message(values={VALUE_CHAT_TYPE: chat_type})) is False
        for mentions in mention_lists:
            message = _message(
                values={VALUE_CHAT_TYPE: chat_type, VALUE_MENTIONS: mentions}
            )
            assert policy.admits(message) is False, (chat_type, mentions)


def test_a_group_message_addressed_to_somebody_else_is_refused():
    policy = _policy(bot_identity=BOT)

    assert policy.admits(_group(**{VALUE_MENTIONS: ["ou_other_bot"]})) is False


def test_a_group_message_with_no_mentions_is_refused():
    policy = _policy(bot_identity=BOT)

    assert policy.admits(_group()) is False
    assert policy.admits(_group(**{VALUE_MENTIONS: []})) is False


def test_a_group_message_that_mentions_this_bot_is_admitted():
    policy = _policy(bot_identity=BOT)

    assert policy.admits(_group(**{VALUE_MENTIONS: [BOT, "ou_other"]})) is True
    assert policy.admits(_group(**{VALUE_MENTIONS: (BOT,)})) is True


def test_a_mention_list_given_as_one_string_is_refused():
    """A ``str`` is iterable, so a lazy membership test would match it.

    ``"ou_this_bot" in "ou_this_bot"`` is ``True`` for the substring
    reason rather than the identity reason, and a surface that reports a
    single mention as a bare string is the realistic way in.
    """
    policy = _policy(bot_identity=BOT)

    assert policy.admits(_group(**{VALUE_MENTIONS: BOT})) is False


def test_every_group_spelling_the_platforms_use_needs_proof():
    policy = _policy(bot_identity=BOT)

    for chat_type in sorted(GROUP_CHAT_TYPES):
        message = _message(values={VALUE_CHAT_TYPE: chat_type})
        assert policy.admits(message) is False, chat_type


def test_an_unfamiliar_chat_type_falls_back_to_the_allowlist_alone():
    """A spelling this layer does not know is read as a direct message.

    The alternative — refuse everything unrecognised — would make the
    sender check unreachable on any platform whose vocabulary drifts, and
    the sender check is the gate that never stops applying.
    """
    policy = _policy(bot_identity=BOT)

    assert policy.admits(_message(values={VALUE_CHAT_TYPE: "p2p"})) is True
    assert policy.admits(_message(values={VALUE_CHAT_TYPE: 7})) is True
    assert policy.admits(_message(values={VALUE_CHAT_TYPE: "p2p"}, sender="x")) is False


# ---- parsing ---------------------------------------------------------


def test_an_allowlist_parses_the_way_the_env_file_spells_it():
    assert parse_senders(" ou_a , ou_b ") == frozenset({"ou_a", "ou_b"})


def test_a_trailing_comma_does_not_admit_an_unidentified_sender():
    """``"ou_a,"`` must not become ``{"ou_a", ""}``.

    An empty entry in the allowlist is how a platform that fails to
    report a sender would end up admitted, which is
    :func:`test_an_unidentified_sender_is_never_admitted` arriving
    through the configuration instead.
    """
    assert parse_senders("ou_a,,  ,") == frozenset({"ou_a"})
    assert parse_senders("") == frozenset()


# ---- delivery --------------------------------------------------------


def test_acceptance_has_three_states_and_the_third_is_not_a_failure():
    """``UNKNOWN`` is a state a pump must handle, not a soft ``REJECTED``.

    ``telegram_delivery.py:161-164`` in the layer being replaced says it
    outright: "The Pump must not retry blindly." Collapsing the three
    into a boolean is how one dropped connection becomes two identical
    messages in a group chat.
    """
    assert sorted(Acceptance) == ["accepted", "rejected", "unknown"]
    assert Acceptance.UNKNOWN != Acceptance.REJECTED


def test_a_delivery_result_does_not_invent_a_retry_delay():
    """``None`` means "the platform did not say", never "retry now"."""
    assert DeliveryResult(Acceptance.REJECTED).retry_after is None
    assert DeliveryResult(Acceptance.REJECTED, retry_after=30.0).retry_after == 30.0


# ---- Q23: no Any ------------------------------------------------------


def test_nothing_in_the_assembly_foundation_is_typed_any():
    """Plan 0031 Q23's ruling, as a property of the source.

    ``ControlRuntimePorts`` had twenty-two fields and six of them were
    :data:`~typing.Any`; that shape is what the owner's "low coupling"
    instruction was aimed at. The rule is cheap to keep and impossible to
    keep by intention alone, because ``Any`` is what a field gets when
    nobody decides what it holds.

    Read from the syntax tree rather than with a substring search, so
    that prose explaining *why* the rule exists does not violate it —
    ``ingress.py``'s module docstring names ``Any`` twice.

    **Scoped to the four modules Q23 was written about**, not to the
    package. Plan 0031 §3.2 itself declares ``to_wire(event) ->
    dict[str, Any]`` and ``Session.values: Mapping[str, Any]``, so a
    package-wide rule would contradict the frozen contract two other
    lanes are building against. What Q23 forbids is an entry-level
    *request object* that avoids deciding what it carries;
    :attr:`InboundMessage.values` is ``Mapping[str, object]`` for exactly
    that reason.
    """
    import ast
    import pathlib

    entry = pathlib.Path(__file__).resolve().parents[2] / "omicsclaw" / "entry"
    scope = ("__init__.py", "config.py", "assembly.py", "ingress.py")
    offenders = []
    for path in sorted(entry / name for name in scope):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            named = isinstance(node, ast.Name) and node.id == "Any"
            attributed = isinstance(node, ast.Attribute) and node.attr == "Any"
            if named or attributed:
                offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, f"{offenders} use Any as a type"
