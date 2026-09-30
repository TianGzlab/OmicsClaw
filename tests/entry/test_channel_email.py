"""The Email adapter, over fake IMAP and SMTP objects.

There is no mail server here. What this file tests is what is *particular*
to email: a mailbox that has no groups and therefore no identity for this
bot, headers that make a client thread a reply, attachments that are no
longer written anywhere, and an SMTP failure classified by exception type
rather than by searching its message for a number. The eight rules email
shares with every other adapter are in
``test_channel_cutover_conformance.py``, which drives it through the fixture
registered at the bottom.
"""

from __future__ import annotations

import asyncio
import itertools
import pathlib
import smtplib

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from omicsclaw.entry.channel.email import (
    EMAIL_TEXT_CHUNK_LIMIT,
    EmailChannel,
    EmailConfig,
)
from omicsclaw.entry.channel.email_delivery import (
    EmailDeliveryAdapter,
    SmtpSettings,
    build_reply,
)
from omicsclaw.entry.ingress import VALUE_CHAT_TYPE
from tests.entry.channel_conformance import (  # type: ignore[import-not-found]
    ChannelFixture,
    DeliveryCase,
    register,
)
from tests.entry.test_channel_slack import (  # type: ignore[import-not-found]
    CountingRuntime,
)

WAIT_S = 5.0
OWNER_ADDRESS = "owner@example.org"
BOT_ADDRESS = "omicsclaw@example.org"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- platform doubles --------------------------------------------------


SETTINGS = SmtpSettings(
    host="smtp.example.org",
    port=587,
    username=BOT_ADDRESS,
    password="secret",
    from_address=BOT_ADDRESS,
)


class RecordingSender:
    """Stands in for one blocking SMTP conversation."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.texts: list[str] = []
        self.messages: list = []

    def __call__(self, settings, to_address, message) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((to_address, message))
        self.texts.append(message.get_content().rstrip("\n"))


_MESSAGE_IDS = itertools.count(100)


def mail(
    *,
    text: str = "analyse this",
    sender: str = OWNER_ADDRESS,
    subject: str = "A question",
) -> dict:
    return {
        "from_addr": sender,
        "subject": subject,
        "body": text,
        "message_id": f"<m{next(_MESSAGE_IDS)}@example.org>",
        "references": "",
    }


def email_channel() -> EmailChannel:
    return EmailChannel(
        EmailConfig(
            imap_host="imap.example.org",
            imap_username=BOT_ADDRESS,
            imap_password="secret",
            smtp_host="smtp.example.org",
            smtp_username=BOT_ADDRESS,
            smtp_password="secret",
            from_address=BOT_ADDRESS,
            allowed_senders={OWNER_ADDRESS},
        )
    )


def bound(runtime) -> EmailChannel:
    channel = email_channel()
    channel._account_namespace = BOT_ADDRESS
    channel.bind_control_runtime(runtime)
    channel._running = True
    channel.activate_ingress()
    return channel


# ---- the binding -------------------------------------------------------


def test_the_email_binding_has_no_identity_because_there_are_no_groups():
    """And the empty identity is what makes a group label fail closed."""

    async def scenario():
        return await email_channel().prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "email"
    assert binding.account_namespace == BOT_ADDRESS
    assert binding.sender_policy.bot_identity == ""
    assert binding.sender_policy.allowed_senders == frozenset({OWNER_ADDRESS})
    assert binding.attachment_input_enabled is False


def test_the_email_binding_names_a_chunk_limit_the_chunker_can_act_on():
    """Trap 2, where it would actually have been reached.

    The email capability profile says ``max_text_length = 0`` and means "no
    practical limit"; the chunker reads a zero budget and never advances. So
    this adapter names a real number instead of inheriting that one.
    """

    async def scenario():
        return await email_channel().prepare_control_binding()

    binding = run(scenario())

    assert binding.text_chunk_limit == EMAIL_TEXT_CHUNK_LIMIT
    assert binding.text_chunk_limit > 20


def test_the_email_binding_refuses_to_start_with_no_owners():
    async def scenario():
        channel = EmailChannel(
            EmailConfig(
                imap_host="i",
                imap_username="u",
                smtp_host="s",
                smtp_username="u",
            )
        )
        with pytest.raises(RuntimeError, match="EMAIL_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- trap 6: nothing is written to disk -------------------------------


def test_an_attachment_is_never_written_anywhere(monkeypatch, tmp_path):
    """The path this replaces wrote every attachment to ``/tmp`` and read none.

    The filename came from the mail's own ``Content-Disposition`` header —
    unsanitised external input pasted into a path — so ``../`` in it escaped
    the directory that was named. Deleting the write removes both the dead
    feature and the traversal with it.
    """
    import email.message

    written: list[str] = []
    monkeypatch.setattr(
        pathlib.Path,
        "write_bytes",
        lambda self, data: written.append(str(self)),
    )

    outer = email.message.EmailMessage()
    outer["From"] = OWNER_ADDRESS
    outer["Subject"] = "with an attachment"
    outer["Message-ID"] = "<m1@example.org>"
    outer.set_content("analyse this")
    outer.add_attachment(
        b"payload",
        maintype="application",
        subtype="octet-stream",
        filename="../../../tmp/escaped.bin",
    )

    channel = email_channel()

    class FakeImap:
        def noop(self):
            return ("OK", [b""])

        def search(self, charset, criterion):
            return ("OK", [b"1"])

        def fetch(self, uid, spec):
            return ("OK", [(b"1", outer.as_bytes())])

        def store(self, uid, flags, value):
            return ("OK", [b""])

    channel._imap = FakeImap()
    fetched = channel._fetch_unseen()

    assert written == []
    assert len(fetched) == 1
    assert "attachments" not in fetched[0]
    assert "analyse this" in fetched[0]["body"]


# ---- reading what a mail actually says ---------------------------------


def test_an_encoded_header_is_decoded_and_a_broken_one_is_kept():
    """A subject is put in front of the model, so it has to be readable.

    Falling back to the raw value rather than raising: a header this
    machine cannot decode is still better than no subject at all.
    """
    from omicsclaw.entry.channel.email import decode_header_value

    assert decode_header_value("=?utf-8?q?A_question?=") == "A question"
    assert decode_header_value("") == ""
    assert decode_header_value("=?bogus?x?zz?=") == "=?bogus?x?zz?="


def test_an_html_only_mail_is_reduced_to_its_text():
    """Tags reach the model as tokens and mean nothing to it."""
    from omicsclaw.entry.channel.email import strip_html

    assert strip_html("<p>one</p><p>two<br/>three</p>") == "one\n\ntwo\nthree"
    assert strip_html("a &amp; b") == "a & b"


# ---- inbound -----------------------------------------------------------


def test_a_mail_carries_its_message_id_and_the_headers_a_reply_needs():
    async def scenario():
        runtime = CountingRuntime()
        letter = mail()
        await bound(runtime)._on_message(letter)
        return runtime, letter

    runtime, letter = run(scenario())

    (inbound,) = runtime.messages
    assert inbound.source_request_id == letter["message_id"]
    assert inbound.session_id == f"email:{OWNER_ADDRESS}"
    assert inbound.surface == "email"
    assert inbound.values[VALUE_CHAT_TYPE] == "private"
    assert inbound.text.startswith("Subject: A question")
    target = inbound.values["reply_target"]
    assert target["original_message_id"] == letter["message_id"]
    assert target["subject"] == "A question"


def test_a_mail_from_outside_the_allowlist_creates_no_exchange():
    """The adapter's own check, which is redundant with ingress on purpose.

    Both deny by default, so the redundancy only ever tightens; this one
    exists to stop the work before the runtime is asked.
    """

    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(mail(sender="stranger@example.org"))
        return runtime

    assert run(scenario()).messages == []


def test_a_refused_mail_can_still_land_when_it_is_redelivered():
    async def scenario():
        from omicsclaw.entry.channel.runtime import TurnAcceptanceStatus

        runtime = CountingRuntime(
            TurnAcceptanceStatus.REJECTED, TurnAcceptanceStatus.ACCEPTED
        )
        channel = bound(runtime)
        letter = mail()
        await channel._on_message(letter)
        await channel._on_message(dict(letter))
        return runtime

    assert len(run(scenario()).messages) == 2


def test_email_has_no_way_to_attach_a_file_at_all():
    """A closure, not a gap: the implementation worked and had no caller.

    ``_smtp_send_attachment`` built a valid multipart message and nothing
    in the repository called it, because nothing in this layer names an
    artefact in a way an outbound path could resolve. Removing the method
    rather than making it raise is what stops it reading as a thing to
    call; reopening it means answering "which file".
    """
    assert not hasattr(email_channel(), "send_media")


# ---- delivery ----------------------------------------------------------


def email_request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    built = reply_target.build(
        "email",
        BOT_ADDRESS,
        target.pop("destination", OWNER_ADDRESS),
        **target,
    )
    return DeliveryAttemptRequest(item_id="t1-0", text=text, reply_target=built)


def test_a_reply_is_threaded_onto_the_mail_it_answers():
    """Without the two headers a client starts a new conversation each time."""
    _to, message = build_reply(
        SETTINGS,
        email_request(
            subject="A question",
            original_message_id="<m1@example.org>",
            references="<m0@example.org>",
        ),
    )

    assert message["Subject"] == "Re: A question"
    assert message["In-Reply-To"] == "<m1@example.org>"
    assert message["References"] == "<m0@example.org> <m1@example.org>"
    assert message["From"] == BOT_ADDRESS
    assert message["To"] == OWNER_ADDRESS


def test_a_subject_that_is_already_a_reply_is_not_prefixed_again():
    _to, message = build_reply(SETTINGS, email_request(subject="Re: A question"))

    assert message["Subject"] == "Re: A question"


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            smtplib.SMTPRecipientsRefused({}),
            DeliveryAttemptOutcome.REJECTED_PERMANENT,
        ),
        (
            smtplib.SMTPAuthenticationError(535, b"bad"),
            DeliveryAttemptOutcome.REJECTED_PERMANENT,
        ),
        (
            smtplib.SMTPResponseException(550, b"no such user"),
            DeliveryAttemptOutcome.REJECTED_PERMANENT,
        ),
        (
            smtplib.SMTPResponseException(421, b"busy"),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        (
            smtplib.SMTPServerDisconnected("gone"),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        (TimeoutError("slow"), DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN),
    ],
)
def test_smtp_failures_are_classified_by_type_and_never_by_message(error, expected):
    """The path this replaces searched the *text* of the exception.

    A server that words a refusal differently looked like a transport
    failure, and a transport failure whose message happened to contain
    "auth" looked permanent — both directions, and neither visible.
    """
    adapter = EmailDeliveryAdapter(SETTINGS, RecordingSender(error))

    result = run(adapter.attempt(email_request()))

    assert result.outcome is expected


def test_no_email_outcome_is_ever_retryable():
    """SMTP names no interval to come back after, so nothing here may repeat."""
    outcomes = [
        smtplib.SMTPResponseException(421, b"busy"),
        smtplib.SMTPServerDisconnected("gone"),
        smtplib.SMTPRecipientsRefused({}),
        TimeoutError("slow"),
    ]

    for error in outcomes:
        adapter = EmailDeliveryAdapter(SETTINGS, RecordingSender(error))
        assert not run(adapter.attempt(email_request())).retryable


def test_a_target_for_another_platform_never_reaches_smtp():
    sender = RecordingSender()
    other = reply_target.build("slack", "team-T1", "C1")

    result = run(
        EmailDeliveryAdapter(SETTINGS, sender).attempt(
            DeliveryAttemptRequest(item_id="t1-0", text="hi", reply_target=other)
        )
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert sender.messages == []


# ---- the conformance fixture -------------------------------------------


async def _conformance_submit(
    channel: EmailChannel,
    *,
    text: str,
    sender: str = OWNER_ADDRESS,
    group: bool = False,
    mentions_bot: bool = False,
) -> None:
    await channel._on_message(mail(text=text, sender=sender, subject=""))


def _conformance_accepting_delivery():
    sender = RecordingSender()
    return EmailDeliveryAdapter(SETTINGS, sender), sender.texts


def _conformance_delivery_cases() -> tuple[DeliveryCase, ...]:
    return (
        DeliveryCase(
            "timeout",
            EmailDeliveryAdapter(SETTINGS, RecordingSender(TimeoutError("slow"))),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "unknown",
            EmailDeliveryAdapter(SETTINGS, RecordingSender(RuntimeError("?"))),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "refused",
            EmailDeliveryAdapter(
                SETTINGS, RecordingSender(smtplib.SMTPRecipientsRefused({}))
            ),
            DeliveryAttemptOutcome.REJECTED_PERMANENT,
        ),
    )


register(
    ChannelFixture(
        name="email",
        new_channel=email_channel,
        reply_target=lambda channel: reply_target.build(
            "email", BOT_ADDRESS, OWNER_ADDRESS, subject="A question"
        ),
        accepting_delivery=_conformance_accepting_delivery,
        delivery_cases=_conformance_delivery_cases,
        submit=_conformance_submit,
        direct_replies=lambda _channel, transport: list(transport.sent),
        has_groups=False,
        strips_markdown=False,
        unregistered_commands_reach_the_agent=True,
        owner=OWNER_ADDRESS,
        stranger="stranger@example.org",
        has_retryable_refusal=False,
    )
)
