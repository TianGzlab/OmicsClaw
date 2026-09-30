"""The setup wizard: what it writes, what it refuses to destroy, what it hides.

``oc cli -- --configure``'s own tests. The command-level ones —— a real
process, a scripted stdin, and a repository ``.env`` that must not be
touched —— are in ``tests/launch/test_configure_command.py``; what is
here is the library underneath it.

**The prompter these tests drive is the one production uses here.**
``questionary`` is not installed on this machine and is not a declared
dependency, so :func:`~omicsclaw.entry.cli._configure.open_prompter`
falls back to :class:`StreamPrompter` —— which means the fallback is not
a fallback in practice, it is the implementation. Testing the other
branch and calling it covered would be testing the path nobody runs.

**The accounting for ``tests/test_onboard.py``.** That file tested
``omicsclaw/surfaces/cli/setup_wizard.py``, which has been unimportable
since ``omicsclaw.providers`` was deleted: four tests, all four red at
collection with ``ModuleNotFoundError: No module named
'omicsclaw.providers'``, and none of them able to go green without
reviving a package the rebuild replaced. Judged legacy along with its
subject and deleted —— responsibility moved, so the tests moved with it
(step 6's third recorded lesson), except for the one whose subject is
not coming back:

``test_onboard_save_env_updates_and_removes_keys`` asserted four
properties of one save, and each has its own test here:
``test_it_keeps_a_comment_it_did_not_write``,
``test_a_value_with_a_space_survives_the_round_trip``,
``test_a_variable_the_file_lacks_is_appended``,
``test_a_removal_takes_the_line_with_it``.

``test_run_onboard_writes_core_runtime_and_channel_config`` becomes
``test_the_five_answers_reach_the_file`` plus
``test_both_optional_channels_and_the_desktop_token_are_written``, and
the process half of it is in the command test.

``test_configure_llm_replaces_legacy_deepseek_default`` becomes
``test_a_model_the_vendor_retired_is_replaced``.

``test_run_onboard_switches_wechat_backend_and_clears_conflicting_env``
is **not ported**, and deliberately: the rebuilt stack has no WeChat
channel, so the wizard has no WeChat section to test.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from omicsclaw.provider import PRESETS

from omicsclaw.entry.cli import missing_credential_hint, run_configuration_wizard
from omicsclaw.entry.cli._configure import (
    StreamPrompter,
    _mask,
    _target_key,
    open_prompter,
    read_dotenv,
    write_dotenv,
)


def _drive(answers: list[str]) -> tuple[StreamPrompter, io.StringIO]:
    """A prompter fed a script, and the transcript it prints."""
    sink = io.StringIO()
    return StreamPrompter(io.StringIO("\n".join(answers) + "\n"), sink), sink


_MINIMAL = [
    "deepseek",  # provider
    "sk-abcdefgh1234",  # api key
    "",  # model: take the preset default
    "",  # base URL: take the preset's own
    "/tmp/ws",  # workspace
    "n",  # telegram
    "n",  # feishu
    "n",  # desktop token
    "y",  # save
]
"""The shortest complete run: five answers and three declined sections.

Written out because its **length** is the property the owner's scope
ruling is about —— a wizard that grows a tenth question has to edit this
list, and that is the moment to ask whether the question earns it.
"""


# ---- what it writes ---------------------------------------------------


def test_the_five_answers_reach_the_file(tmp_path):
    path = tmp_path / ".env"
    ask, _ = _drive(_MINIMAL)

    written = run_configuration_wizard(
        path, prompter=ask, sink=io.StringIO(), workspace_default="/nowhere"
    )

    assert written == path
    assert read_dotenv(path) == {
        "LLM_PROVIDER": "deepseek",
        "LLM_API_KEY": "sk-abcdefgh1234",
        "LLM_MODEL": "deepseek-v4-flash",
        "LLM_BASE_URL": "",
        "OMICSCLAW_WORKSPACE": "/tmp/ws",
    }


def test_the_variables_written_are_ones_the_template_publishes(tmp_path):
    """``.env.example`` is the authority, so nothing invented may appear.

    A wizard writing a variable the stack does not read is the failure
    mode this whole exercise is about: the user answers a question, the
    file changes, and the deployment does not.
    """
    template = pathlib.Path(".env.example").read_text(encoding="utf-8")
    path = tmp_path / ".env"
    ask, _ = _drive(
        [
            "deepseek", "sk-k", "m", "", "/tmp/ws",
            "y", "tok", "owner-1", "", "y", "app", "sec", "sender", "bot",
            "y", "bearer",
            "y",
        ]
    )

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    published = {
        line.lstrip("#").split("=", 1)[0].strip()
        for line in template.splitlines()
        if "=" in line and line.lstrip("#")[:1].isalpha()
    }
    assert set(read_dotenv(path)) <= published, set(read_dotenv(path)) - published


def test_both_optional_channels_and_the_desktop_token_are_written(tmp_path):
    path = tmp_path / ".env"
    ask, _ = _drive(
        [
            "deepseek", "sk-k", "m", "", "/tmp/ws",
            "y", "bot-token", "owner-1", "9", "y",
            "cli_x", "secret-x", "ou_owner", "ou_bot",
            "y", "bearer-token",
            "y",
        ]
    )

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["TELEGRAM_BOT_TOKEN"] == "bot-token"
    assert saved["TELEGRAM_ALLOWED_SENDERS"] == "owner-1"
    assert saved["TELEGRAM_CHAT_ID"] == "9"
    assert saved["FEISHU_APP_ID"] == "cli_x"
    assert saved["FEISHU_APP_SECRET"] == "secret-x"
    assert saved["FEISHU_ALLOWED_SENDERS"] == "ou_owner"
    assert saved["FEISHU_BOT_OPEN_ID"] == "ou_bot"
    assert saved["OMICSCLAW_REMOTE_AUTH_TOKEN"] == "bearer-token"


def test_a_declined_section_is_not_written(tmp_path):
    path = tmp_path / ".env"
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert not [name for name in read_dotenv(path) if name.startswith("TELEGRAM_")]
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" not in read_dotenv(path)


def test_a_channel_that_would_refuse_to_start_is_refused_here_instead(tmp_path):
    """Telegram needs an owner list or a chat id; the shell will not start
    without one, so the wizard re-asks rather than writing a deployment
    that boots and then answers nobody.
    """
    path = tmp_path / ".env"
    ask, transcript = _drive(
        [
            "deepseek", "sk-k", "m", "", "/tmp/ws",
            "y", "bot-token", "", "",  # neither: refused
            "owner-1", "",  # second attempt
            "n", "n", "y",
        ]
    )

    run_configuration_wizard(path, prompter=ask, sink=transcript)

    assert "One of the two is required" in transcript.getvalue()
    assert read_dotenv(path)["TELEGRAM_ALLOWED_SENDERS"] == "owner-1"


# ---- what it refuses to destroy ---------------------------------------


_EXISTING = """\
# my own notes, keep these
UNKNOWN_KEY=leave-me-alone

LLM_PROVIDER=openai
export LLM_API_KEY=sk-oldkey9999
# a trailing comment
"""


def test_it_keeps_a_comment_it_did_not_write(tmp_path):
    """Plan 0037's most concrete near-miss, as a test.

    A save that rebuilt the file from its key/value pairs removed 332 of
    370 lines of a real file in this repository, every one of them a
    comment. The property is not "comments are usually kept"; it is that
    a line this wizard has no opinion about is copied.
    """
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = path.read_text(encoding="utf-8")

    assert "# my own notes, keep these" in saved
    assert "# a trailing comment" in saved
    assert "UNKNOWN_KEY=leave-me-alone" in saved
    assert read_dotenv(path)["UNKNOWN_KEY"] == "leave-me-alone"


def test_an_answered_key_is_rewritten_where_it_stands(tmp_path):
    """In place, so a hand-ordered file stays hand-ordered."""
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines.index("LLM_PROVIDER=deepseek") < lines.index("# a trailing comment")


def test_a_variable_the_file_lacks_is_appended(tmp_path):
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert read_dotenv(path)["OMICSCLAW_WORKSPACE"] == "/tmp/ws"


def test_the_previous_version_is_kept_beside_it(tmp_path):
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    backups = sorted(tmp_path.glob(".env.backup-*"))

    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == _EXISTING


def test_no_partial_file_is_left_behind(tmp_path):
    """The write is a rename, so the staging file must not survive it."""
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert not list(tmp_path.glob("*.partial"))


def test_a_first_run_creates_the_file_and_no_backup(tmp_path):
    path = tmp_path / ".env"
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert path.is_file()
    assert not list(tmp_path.glob(".env.backup-*"))


def test_a_new_file_is_readable_only_by_its_owner(tmp_path):
    """It holds API keys; a world-readable one hands them to the machine."""
    path = tmp_path / ".env"
    ask, _ = _drive(_MINIMAL)

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert path.stat().st_mode & 0o077 == 0


def test_declining_to_save_leaves_the_file_exactly_as_it_was(tmp_path):
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, _ = _drive(_MINIMAL[:-1] + ["n"])

    written = run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert written is None
    assert path.read_text(encoding="utf-8") == _EXISTING
    assert not list(tmp_path.glob(".env.backup-*"))


def test_input_that_ends_early_writes_nothing(tmp_path):
    """EOF is abandonment, not a crash: no file, no traceback, no backup."""
    path = tmp_path / ".env"
    path.write_text(_EXISTING, encoding="utf-8")
    ask, transcript = _drive(["deepseek", "sk-k"])

    written = run_configuration_wizard(path, prompter=ask, sink=transcript)

    assert written is None
    assert path.read_text(encoding="utf-8") == _EXISTING
    assert "nothing was written" in transcript.getvalue()


def test_a_value_with_a_space_survives_the_round_trip(tmp_path):
    path = tmp_path / ".env"

    write_dotenv(path, {"A": "/mnt/data one", "B": "plain", "C": "has#hash"})

    assert read_dotenv(path) == {"A": "/mnt/data one", "B": "plain", "C": "has#hash"}


def test_a_key_answered_for_is_left_assigned_once(tmp_path):
    """A duplicate assignment would shadow the value that was just written.

    The file format takes the last assignment, so a save that rewrote the
    first occurrence and left the second would report success and change
    nothing —— the exact failure this wizard exists to remove.
    """
    path = tmp_path / ".env"
    path.write_text("LLM_MODEL=first\nKEEP=me\nLLM_MODEL=second\n", encoding="utf-8")

    write_dotenv(path, {"LLM_MODEL": "chosen"})
    body = path.read_text(encoding="utf-8")

    assert body.count("LLM_MODEL=") == 1
    assert read_dotenv(path) == {"LLM_MODEL": "chosen", "KEEP": "me"}


def test_a_removal_takes_the_line_with_it(tmp_path):
    path = tmp_path / ".env"
    path.write_text("GONE=1\nSTAYS=2\n", encoding="utf-8")

    write_dotenv(path, {"GONE": None})

    assert read_dotenv(path) == {"STAYS": "2"}


# ---- what it hides ----------------------------------------------------


@pytest.mark.parametrize(
    "secret,shown",
    [("sk-abcdefgh1234", "…1234"), ("short", "…"), ("", "")],
)
def test_a_stored_secret_is_shown_as_four_characters_at_most(secret, shown):
    assert _mask(secret) == shown


def test_no_secret_is_echoed_anywhere_the_wizard_prints(tmp_path):
    """``SAFETY_RULES`` rule 1, asserted over the whole transcript.

    Both halves: the key typed in this run, and the one already stored in
    the file —— the second is the one a "show the current value" default
    leaks by accident.
    """
    path = tmp_path / ".env"
    path.write_text("LLM_PROVIDER=deepseek\nLLM_API_KEY=sk-stored-9876\n", "utf-8")
    ask, transcript = _drive(
        ["deepseek", "sk-typed-5432", "m", "", "/tmp/ws", "n", "n", "y", "t0ken", "y"]
    )

    run_configuration_wizard(path, prompter=ask, sink=transcript)
    printed = transcript.getvalue()

    assert "sk-typed-5432" not in printed
    assert "sk-stored-9876" not in printed
    assert "t0ken" not in printed
    assert "…5432" in printed  # it did read the new one


def test_keeping_a_stored_secret_needs_no_retyping(tmp_path):
    """An empty answer keeps what is there rather than clearing it."""
    path = tmp_path / ".env"
    path.write_text("LLM_PROVIDER=deepseek\nLLM_API_KEY=sk-stored-9876\n", "utf-8")
    ask, _ = _drive(["deepseek", "", "m", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert read_dotenv(path)["LLM_API_KEY"] == "sk-stored-9876"


# ---- the spelling that actually wins ----------------------------------


def test_the_spelling_already_in_the_file_is_the_one_written():
    """``resolve_config`` does not read these in the order a person guesses.

    ``OMICSCLAW_MODEL`` beats ``LLM_MODEL`` and ``DEEPSEEK_API_KEY`` beats
    ``LLM_API_KEY``, so writing the canonical spelling into a file that
    already sets a higher-precedence one produces a correct file and a
    wrong deployment.
    """
    assert _target_key({}, "LLM_MODEL", "OMICSCLAW_MODEL", "LLM_MODEL") == "LLM_MODEL"
    assert (
        _target_key({"OMICSCLAW_MODEL": "x"}, "LLM_MODEL", "OMICSCLAW_MODEL")
        == "OMICSCLAW_MODEL"
    )
    assert (
        _target_key({"DEEPSEEK_API_KEY": "x"}, "LLM_API_KEY", "DEEPSEEK_API_KEY")
        == "DEEPSEEK_API_KEY"
    )


def test_a_vendor_scoped_key_is_updated_rather_than_shadowed(tmp_path):
    """End to end: the file already sets the variable that outranks ours."""
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-old\nOMICSCLAW_MODEL=old-model\n",
        encoding="utf-8",
    )
    ask, _ = _drive(
        ["deepseek", "sk-new", "new-model", "", "/tmp/ws", "n", "n", "n", "y"]
    )

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["DEEPSEEK_API_KEY"] == "sk-new"
    assert saved["OMICSCLAW_MODEL"] == "new-model"
    assert "LLM_API_KEY" not in saved
    assert "LLM_MODEL" not in saved


def test_a_model_the_vendor_retired_is_replaced(tmp_path):
    """Carried over from ``tests/test_onboard.py``.

    ``deepseek-chat`` is a model DeepSeek has withdrawn; left in a
    ``.env`` it produces a 404 that reads like an outage. The offer is
    the current default instead, which is
    :func:`~omicsclaw.provider.config.normalize_model_for_provider`'s
    whole reason for existing.
    """
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=deepseek\nOMICSCLAW_MODEL=deepseek-chat\n", encoding="utf-8"
    )
    ask, _ = _drive(["deepseek", "", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert read_dotenv(path)["OMICSCLAW_MODEL"] == "deepseek-v4-flash"


def test_changing_the_backend_does_not_carry_the_old_endpoint_over(tmp_path):
    """``.env.example``'s warning, cured rather than repeated.

    An endpoint left over from one vendor silently hijacks the next one
    selected, so the offer on a changed backend is empty —— which the
    resolver reads as "the preset's own".
    """
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=openai\nLLM_BASE_URL=https://old.example/v1\n", encoding="utf-8"
    )
    ask, _ = _drive(["deepseek", "sk-k", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())

    assert read_dotenv(path)["LLM_BASE_URL"] == ""


def _next_start(env: dict[str, str]):
    """Provider settings the next start resolves from *env*: ``AppConfig``
    names the provider and model, ``resolve_config`` fills in the rest."""
    from omicsclaw.entry.config import resolve_app_config
    from omicsclaw.provider import resolve_config

    config = resolve_app_config([], env)
    return resolve_config(config.provider, config.model, env=env)


@pytest.mark.parametrize(
    "initial",
    [
        "LLM_PROVIDER=openai\n",
        "OMICSCLAW_PROVIDER=openai\n",
        "OMICSCLAW_PROVIDER=openai\nLLM_PROVIDER=openai\n",
    ],
    ids=["llm-only", "omicsclaw-only", "both"],
)
def test_a_new_backend_is_the_one_the_next_start_runs(tmp_path, initial):
    """Every provider spelling the file has is rewritten, so neither
    ``AppConfig`` (``OMICSCLAW_PROVIDER`` first) nor ``resolve_config``
    (``LLM_PROVIDER`` first) is left reading the old vendor. The generic
    key applies only when ``resolve_config`` agrees on the provider, so
    the key checks that agreement."""
    path = tmp_path / ".env"
    path.write_text(initial + "LLM_MODEL=gpt-5.5\n", encoding="utf-8")
    ask, _ = _drive(["deepseek", "sk-k", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    for name in ("OMICSCLAW_PROVIDER", "LLM_PROVIDER"):
        if name in initial:
            assert saved[name] == "deepseek", name
    resolved = _next_start(saved)
    assert resolved.provider == "deepseek"
    assert resolved.model == PRESETS["deepseek"].default_model
    assert resolved.base_url == PRESETS["deepseek"].base_url
    assert resolved.api_key == "sk-k"


def test_the_backend_offered_first_is_the_one_the_file_names(tmp_path):
    """The picker's default follows ``AppConfig``'s order, so pressing
    Enter keeps a backend named only by ``OMICSCLAW_PROVIDER`` and its
    model, rather than the one another vendor's key would suggest."""
    path = tmp_path / ".env"
    path.write_text(
        "OMICSCLAW_PROVIDER=zhipu\nDEEPSEEK_API_KEY=sk-deepseek-old\nLLM_MODEL=glm-x\n",
        encoding="utf-8",
    )
    ask, _ = _drive(["", "", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["OMICSCLAW_PROVIDER"] == "zhipu"
    assert "LLM_PROVIDER" not in saved
    assert saved["LLM_MODEL"] == "glm-x"


def test_a_stale_endpoint_under_a_lower_spelling_is_cleared_too(tmp_path):
    """``LLM_BASE_URL`` beats ``OMICSCLAW_BASE_URL`` only when it is
    non-empty, so clearing the higher one alone would let the old
    vendor's endpoint through the lower one."""
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=openai\nLLM_BASE_URL=https://old.example/v1\n"
        "OMICSCLAW_BASE_URL=https://old.example/v1\n",
        encoding="utf-8",
    )
    ask, _ = _drive(["deepseek", "sk-k", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["LLM_BASE_URL"] == saved["OMICSCLAW_BASE_URL"] == ""
    assert _next_start(saved).base_url == PRESETS["deepseek"].base_url


def test_the_spelling_that_takes_effect_is_the_one_offered(tmp_path):
    """Readers skip an empty variable, so the offer on an unchanged backend
    is the first non-empty spelling, and Enter keeps it in effect."""
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-kept-000\n"
        "DEEPSEEK_BASE_URL=\nLLM_BASE_URL=https://proxy.example/v1\n"
        "OMICSCLAW_MODEL=\nLLM_MODEL=my-model\n",
        encoding="utf-8",
    )
    ask, _ = _drive(["deepseek", "", "", "", "/tmp/ws", "n", "n", "n", "y"])

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["DEEPSEEK_BASE_URL"] == saved["LLM_BASE_URL"] == "https://proxy.example/v1"
    assert saved["OMICSCLAW_MODEL"] == saved["LLM_MODEL"] == "my-model"
    resolved = _next_start(saved)
    assert (resolved.base_url, resolved.model) == ("https://proxy.example/v1", "my-model")


def test_an_empty_model_does_not_let_a_lower_spelling_through(tmp_path):
    """``custom`` has no default model; an empty answer is written to every
    spelling, so the old vendor's model under ``LLM_MODEL`` is not used."""
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=openai\nOMICSCLAW_MODEL=gpt-new\nLLM_MODEL=gpt-old\n",
        encoding="utf-8",
    )
    ask, _ = _drive(
        ["custom", "sk-k", "", "http://h/v1", "/tmp/ws", "n", "n", "n", "y"]
    )

    run_configuration_wizard(path, prompter=ask, sink=io.StringIO())
    saved = read_dotenv(path)

    assert saved["OMICSCLAW_MODEL"] == saved["LLM_MODEL"] == ""
    assert _next_start(saved).model not in {"gpt-new", "gpt-old"}


def test_the_report_names_the_backend_the_next_start_runs(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OMICSCLAW_PROVIDER=openai\n", encoding="utf-8")
    ask, _ = _drive(["zhipu", "sk-k", "", "", "/tmp/ws", "n", "n", "n", "y"])
    sink = io.StringIO()

    run_configuration_wizard(path, prompter=ask, sink=sink)

    assert "provider  zhipu" in sink.getvalue()


# ---- the prompter -----------------------------------------------------


def test_the_prompter_this_machine_builds_is_the_standard_library_one():
    """``questionary`` is not installed and is not a declared dependency.

    So the branch the tests above drive is the branch production takes.
    If somebody installs it, this test says so rather than silently
    letting the coverage move.
    """
    assert isinstance(open_prompter(io.StringIO(), io.StringIO()), StreamPrompter)


def test_a_default_is_taken_by_pressing_enter():
    ask, _ = _drive(["", "typed"])

    assert ask.text("q", default="fallback") == "fallback"
    assert ask.text("q", default="fallback") == "typed"


@pytest.mark.parametrize(
    "answer,default,expected",
    [("y", False, True), ("", True, True), ("", False, False), ("no", True, False)],
)
def test_a_confirmation_reads_the_word_and_falls_back_to_the_default(
    answer, default, expected
):
    ask, _ = _drive([answer])

    assert ask.confirm("q", default=default) is expected


def test_a_choice_accepts_a_number_or_a_name_and_re_asks_otherwise():
    ask, transcript = _drive(["2", "beta", "nope", "1"])
    options = ["alpha", "beta"]

    assert ask.choose("pick", options, default="alpha") == "beta"
    assert ask.choose("pick", options, default="alpha") == "beta"
    assert ask.choose("pick", options, default="alpha") == "alpha"
    assert "not one of them" in transcript.getvalue()


def test_the_end_of_input_is_reported_as_eof():
    ask, _ = _drive([])
    ask.text("q")  # the single empty line the joiner produced

    with pytest.raises(EOFError):
        ask.text("q")


# ---- the hint ---------------------------------------------------------


def test_a_deployment_with_no_key_is_told_the_whole_command():
    hint = missing_credential_hint({})

    assert "oc cli --configure" in hint


def test_a_configured_deployment_is_told_nothing():
    assert missing_credential_hint({"LLM_API_KEY": "sk-x"}) == ""
    assert missing_credential_hint({"DEEPSEEK_API_KEY": "sk-x"}) == ""


def test_a_backend_that_needs_no_key_is_not_nagged():
    """An Ollama deployment will never have a key; a hint it cannot act on
    is how people learn to stop reading hints."""
    assert missing_credential_hint({"LLM_PROVIDER": "ollama"}) == ""


# ---- write_dotenv never destroys what it cannot read (plan 0050 §3.3) --


def test_an_unreadable_file_is_not_replaced(tmp_path, monkeypatch):
    """The old ``except OSError: original = ""`` made "cannot read your
    credentials" mean "replace them with one line": a rename needs only the
    directory to be writable. Simulated, because this suite runs as root
    and a mode of 000 would not stop it."""
    path = tmp_path / ".env"
    path.write_text("LLM_API_KEY=sk-keep-me\n", encoding="utf-8")
    real = pathlib.Path.read_text

    def refuse(self, *args, **kwargs):
        if self == path:
            raise PermissionError("denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", refuse)

    with pytest.raises(PermissionError):
        write_dotenv(path, {"OMICSCLAW_CLI_PERMISSION_MODE": "auto-approve"})

    monkeypatch.undo()
    assert path.read_text(encoding="utf-8") == "LLM_API_KEY=sk-keep-me\n"


def test_a_file_that_is_not_utf8_is_not_replaced(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"LLM_API_KEY=\xff\xfe\n")

    with pytest.raises(UnicodeDecodeError):
        write_dotenv(path, {"A": "b"})

    assert path.read_bytes() == b"LLM_API_KEY=\xff\xfe\n"


def test_a_symlink_is_followed_and_kept(tmp_path):
    real = tmp_path / "shared.env"
    real.write_text("LLM_API_KEY=sk-x\n", encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(real)

    write_dotenv(link, {"A": "b"}, backup=False)

    assert link.is_symlink()
    assert "A=b" in real.read_text(encoding="utf-8")


def test_a_new_file_is_private_and_a_failed_save_leaves_nothing(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    write_dotenv(path, {"A": "b"})
    assert path.stat().st_mode & 0o777 == 0o600

    def fail(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "replace", fail)
    with pytest.raises(OSError):
        write_dotenv(path, {"A": "c"}, backup=False)

    assert not list(tmp_path.glob("*.partial"))
    monkeypatch.undo()
    assert "A=b" in path.read_text(encoding="utf-8")


def test_backup_false_writes_no_backup(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\n", encoding="utf-8")

    assert write_dotenv(path, {"A": "2"}, backup=False) is None
    assert not list(tmp_path.glob(".env.backup-*"))


def test_a_backup_is_as_private_as_the_file_it_copies(tmp_path):
    path = tmp_path / ".env"
    path.write_text("LLM_API_KEY=sk-x\n", encoding="utf-8")
    path.chmod(0o600)

    backup = write_dotenv(path, {"A": "b"})

    assert backup is not None
    assert backup.stat().st_mode & 0o777 == 0o600
