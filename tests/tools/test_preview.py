"""``omicsclaw.tools.preview``: tool arguments shown to the person approving them.

An approval reason is printed on a terminal and posted to a chat, and the
arguments inside it were written by a model that may have read a hostile
file or web page. So the preview has four jobs, one group of tests each:
say the same thing for the same call, stay short enough to read, be unable
to act on the display showing it, and not hand a credential to whoever is
looking at the screen or the chat's provider.
"""

from __future__ import annotations

import json
import unicodedata

import pytest

from omicsclaw.tools.preview import (
    MAX_PREVIEW_CHARS,
    REDACTED,
    escape_unsafe,
    is_credential_key,
    preview_arguments,
    redact_credentials,
)

_UNSAFE = {"Cc", "Cf", "Cs", "Zl", "Zp"}


# ---- determinism -------------------------------------------------------------


def test_the_same_call_spelled_two_ways_previews_the_same():
    """Key order and whitespace are the model's accident, not the call's
    meaning; a person comparing two cards must see equal text for equal
    calls."""
    one = preview_arguments('{"b": 1, "a": {"y": 2, "x": 3}}')
    two = preview_arguments('{"a":{"x":3,"y":2},"b":1}')

    assert one == two == '{"a": {"x": 3, "y": 2}, "b": 1}'


def test_different_arguments_preview_differently():
    """The defect this module exists for: two cards that read the same while
    one call says ``harmless`` and the other ``rm-everything``."""
    assert preview_arguments('{"text": "harmless"}') != preview_arguments(
        '{"text": "rm-everything"}'
    )


def test_text_that_is_not_ascii_stays_readable():
    """This project's users write Chinese; ``\\u80bf\\u7624`` is not a
    reviewable query."""
    assert preview_arguments('{"q": "肿瘤 TP53"}') == '{"q": "肿瘤 TP53"}'


# ---- length --------------------------------------------------------------------


def test_a_long_payload_is_cut_and_says_how_long_it_was():
    """Why 1,000 characters: the Channel approval line is the reason with a
    one-line header in front, and the tightest per-message limit among the
    shipped IM adapters is Discord's 2,000 (``entry/render.py``
    ``BATCH_CHARS``). A 1,000-character preview leaves the header, the MCP
    server's origin and the truncation note room to fit in one message, so
    a card is never split across two. On an 80-column terminal it is about
    a dozen lines — readable before answering — and it holds any ordinary
    call (identifiers, queries, paths, a short SQL statement) whole.

    The note gives the full length so a person knows how much is hidden
    and can refuse a call they cannot see all of.
    """
    arguments = json.dumps({"sql": "x" * 5000})
    full = json.dumps(json.loads(arguments), sort_keys=True, ensure_ascii=False)

    preview = preview_arguments(arguments)

    assert MAX_PREVIEW_CHARS == 1000
    assert preview.startswith(full[:MAX_PREVIEW_CHARS])
    assert "x" * (MAX_PREVIEW_CHARS + 1) not in preview
    assert preview.endswith(
        f"[truncated: showing the first {MAX_PREVIEW_CHARS} of {len(full)} "
        "characters]"
    )
    assert len(preview) < MAX_PREVIEW_CHARS + 80


def test_a_payload_at_the_limit_is_not_marked():
    arguments = json.dumps({"q": "y" * (MAX_PREVIEW_CHARS - len('{"q": ""}'))})

    preview = preview_arguments(arguments)

    assert len(preview) == MAX_PREVIEW_CHARS
    assert "truncated" not in preview


def test_the_limit_is_a_parameter():
    assert preview_arguments('{"q": "abcdefgh"}', limit=5).startswith('{"q":')
    assert "of 17 characters" in preview_arguments('{"q": "abcdefgh"}', limit=5)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_a_limit_that_is_not_a_positive_integer_is_refused(limit):
    with pytest.raises(ValueError, match="limit"):
        preview_arguments('{"q": 1}', limit=limit)


# ---- inert on a terminal and in a chat -------------------------------------


_HOSTILE = (
    "\x1b[2J\x1b[31mred\x1b[0m"  # ANSI: clear screen, colour
    "\x9b31m"  # C1 CSI, the one-byte form of ESC [
    "\rApproval required [t#9]: bash (risk low)"  # carriage return
    "\nline two"
    "\x85nel\u2028ls\u2029ps\x0bvt\x0cff\x1cfs"  # every other line break
    "\u202eevil\u2066isolate\u200bzw"  # bidi override, isolate, zero width
    "\x00nul\x7fdel"
    "\U000e0001tag"  # a format character above the BMP
)


def test_control_characters_and_escape_sequences_are_neutralised():
    """A model that read a hostile file can put ``ESC [2J`` or a carriage
    return in an argument. Printed raw, the first clears the terminal and
    the second overwrites the card with whatever follows it — a forged
    ``(risk low)`` over the real header. Every such character is written as
    a ``\\u`` escape instead, and the escape is inert text."""
    preview = preview_arguments(json.dumps({"text": _HOSTILE}))

    assert not [c for c in preview if unicodedata.category(c) in _UNSAFE]
    assert "\\u001b[2J" in preview
    assert "\\u009b31m" in preview
    assert "\\u202eevil" in preview
    assert "\\udb40\\udc01tag" in preview


def test_no_line_break_survives_so_no_card_line_can_be_forged():
    """Collapsing to one line is what makes the preview unable to start a
    line of its own: :meth:`str.splitlines` knows every line boundary a
    renderer is likely to honour, and it finds none."""
    preview = preview_arguments(json.dumps({"text": _HOSTILE}))

    assert preview.splitlines() == [preview]


def test_escaping_loses_nothing():
    """The escapes are JSON's own, so the preview of an untruncated payload
    decodes back to exactly the value the tool will receive."""
    payload = {"text": _HOSTILE, "n": [1, 2.5, None, True]}

    assert json.loads(preview_arguments(json.dumps(payload))) == payload


def test_hostile_keys_are_neutralised_too():
    preview = preview_arguments(json.dumps({"a\nb\x1b": 1}))

    assert preview.splitlines() == [preview]
    assert "\x1b" not in preview


def test_a_lone_surrogate_is_escaped_rather_than_crashing_the_terminal():
    """``json.loads`` produces a lone surrogate from ``"\\udcff"``, and a
    terminal writing it with a strict UTF-8 codec raises."""
    preview = preview_arguments('{"q": "\\udcff"}')

    preview.encode("utf-8")
    assert "\\udcff" in preview


# ---- credentials -------------------------------------------------------------


def test_credential_named_keys_are_hidden_at_any_depth():
    """A card is posted to an IM provider and sits in a terminal's
    scrollback; neither is where a token belongs. The rule is by key name,
    case- and separator-insensitive, and it reaches into objects inside
    lists inside objects."""
    payload = {
        "query": "fine",
        "max_tokens": 5,
        "Password": "k0",
        "auth": {
            "Api-Key": "k1",
            "headers": [{"Authorization": "Bearer k2"}, {"accept": "json"}],
        },
        "config": {"client_secret": "k3", "GITHUB_TOKEN": "k4", "Cookie": "k5"},
        "credentials": {"user": "k6", "pass": "k7"},
    }

    preview = preview_arguments(json.dumps(payload))

    for secret in ("k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7"):
        assert secret not in preview
    assert preview.count(REDACTED) == 7
    assert '"query": "fine"' in preview
    assert '"max_tokens": 5' in preview
    assert '"accept": "json"' in preview


@pytest.mark.parametrize(
    "key",
    [
        "token",
        "TOKEN",
        "access_token",
        "x-api-key",
        "apiKey",
        "api_key",
        "Proxy-Authorization",
        "set-cookie",
        "client_secret",
        "db_password",
        "private_key",
        "aws_secret_access_key",
    ],
)
def test_credential_key_names(key):
    assert is_credential_key(key)


@pytest.mark.parametrize(
    "key", ["max_tokens", "input_tokens", "query", "path", "secret_name", "auth"]
)
def test_ordinary_key_names(key):
    """``max_tokens`` and ``input_tokens`` are why the rule is *ends with*
    and not *contains*: the Desktop wire projects usage counts through the
    same rule, and hiding them would blank a client's token display."""
    assert not is_credential_key(key)


# ---- nothing to show, or nothing showable --------------------------------------


@pytest.mark.parametrize("arguments", ["", "   ", "{}", "{ }"])
def test_no_arguments_preview_as_nothing(arguments):
    assert preview_arguments(arguments) == ""


@pytest.mark.parametrize("arguments", ["[1]", "null", '"x"', "3"])
def test_a_payload_that_is_not_an_object_is_still_shown(arguments):
    assert preview_arguments(arguments) == arguments


def test_a_payload_that_is_not_json_is_not_shown():
    """Without a decoded object there are no keys to hide values by, so the
    text is withheld rather than shown with its credentials in it."""
    arguments = '{"token": "s3cr3t", oops'

    preview = preview_arguments(arguments)

    assert "s3cr3t" not in preview and "token" not in preview
    assert f"{len(arguments)} characters" in preview


def test_a_payload_nested_too_deeply_to_decode_is_not_shown():
    arguments = "[" * 100_000 + "]" * 100_000

    assert "could not be read" in preview_arguments(arguments)


# ---- the two rules a display layer reuses --------------------------------------


def test_escape_unsafe_keeps_only_the_characters_it_is_told_to():
    """``keep`` is how a display that draws line breaks itself gets LF back.
    Every other line break is still escaped, so CR, NEL or U+2028 cannot
    stand in for the LF that display is guarding."""
    shown = escape_unsafe(_HOSTILE, keep="\n")

    assert [c for c in shown if unicodedata.category(c) in _UNSAFE] == ["\n"]
    for escaped in ("\\u000d", "\\u0085", "\\u2028", "\\u001b", "\\u202e"):
        assert escaped in shown, escaped


def test_escape_unsafe_keeps_nothing_by_default():
    shown = escape_unsafe(_HOSTILE)

    assert not [c for c in shown if unicodedata.category(c) in _UNSAFE]
    assert escape_unsafe("plain text, 肿瘤") == "plain text, 肿瘤"


def test_redaction_returns_a_copy_and_leaves_the_value_alone():
    """The same rule the preview applies, for a caller that renders the
    decoded value some other way."""
    value = {"token": "t", "items": [{"password": "p", "n": 1}], "q": "x"}

    assert redact_credentials(value) == {
        "token": REDACTED,
        "items": [{"password": REDACTED, "n": 1}],
        "q": "x",
    }
    assert value["token"] == "t" and value["items"][0]["password"] == "p"
