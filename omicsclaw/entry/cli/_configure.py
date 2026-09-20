"""The setup wizard: five questions, three optional sections, one file.

A port of ``omicsclaw/surfaces/cli/setup_wizard.py`` (734 lines), which
the rebuild left behind because its only import of substance —
``omicsclaw.providers`` — no longer exists. What was worth carrying
across is not the question list: it is the ``.env`` round-trip, the
quoting rules, and the prompt helpers that know how to offer a default
and how to keep a secret. Those are ported. The question list was cut
from roughly thirty to five plus three yes/no gates, on the owner's
scope: **a wizard that asks thirty questions is worse than one that asks
five**, and everything it used to ask about — sandbox, permissions, MCP,
compaction, seven chat platforms the rebuilt stack cannot start — either
has a safe default or is not read any more. ``.env.example`` is the
authority for which variable exists; this module may only write names
that appear there.

**It writes where the shell reads.** The path is an argument, resolved
once by :func:`omicsclaw.launch._dotenv.dotenv_target`. Computing it here
as well is how a wizard ends up configuring one file while the program
loads another.

**It never destroys what it did not write.** Comments, blank lines,
ordering and variables this module has never heard of survive a save
untouched; only the keys the user answered for are rewritten, in place.
The file is written to a temporary neighbour and moved over the original,
so an interrupted save leaves the old file whole, and a copy of the old
file is kept as ``.env.backup-<timestamp>`` first. That is not caution
for its own sake: the naive version of this — rebuild the file from the
key/value pairs — silently deleted 332 of 370 lines of a real
``.env.example`` in this repository, because every one of them was a
comment.

**A secret is never echoed.** An existing value is shown as its last four
characters and nothing else, no value reaches a log record, and no
exception message carries one (``CLAUDE.md`` safety rule 1). At a
terminal the answer itself is read without echo.

**``questionary`` is optional and is not installed here.** It appears in
``pyproject.toml`` only inside a comment, so the import lives inside
:func:`open_prompter` in plainly visible syntax (plan 0031 trap 13) and
the fallback is :class:`StreamPrompter`, built out of the standard
library. The fallback is the path this machine and CI actually run, so it
is the path the tests drive.
"""

from __future__ import annotations

import ast
import getpass
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol, Sequence, TextIO

from omicsclaw.provider import (
    DETECT_ORDER,
    PRESETS,
    detect_provider_from_env,
    preset_for,
    resolve_config,
)
from omicsclaw.provider.config import normalize_model_for_provider

__all__ = [
    "StreamPrompter",
    "missing_credential_hint",
    "open_prompter",
    "read_dotenv",
    "run_configuration_wizard",
    "write_dotenv",
]

DEFAULT_PROVIDER = "deepseek"
"""What the picker starts on when nothing in the file implies a backend.

The same default the wizard being ported used, and the vendor behind
``FALLBACK_MODEL`` in ``omicsclaw/provider/config.py`` — one guess, made
in one place's image, rather than two that can disagree.
"""

KEYLESS_PROVIDERS = frozenset({"ollama"})
"""Backends that are configured by their URL and have no key to ask for.

``custom`` is deliberately **not** here even though its preset declares
no key variable: a self-hosted gateway usually does want one, and asking
a question that can be answered with Enter costs less than not offering
the field at all.
"""


# ---- the file: read, write, and leave everything else alone -----------


def _parse_value(raw: str) -> str:
    """One value, unquoted. Ported verbatim from the wizard being replaced.

    Matches ``omicsclaw/common/runtime_env.py``'s fallback parser, which
    is what the shell actually loads the file with, so the wizard shows
    the value the deployment will see rather than a second reading of it.
    """
    value = raw.strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
        return str(parsed)
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def _serialise_value(value: str) -> str:
    """The inverse: quote only when leaving it bare would change it.

    Whitespace and ``#`` are the two characters the parser above treats
    specially, so they are the two that force quoting. Everything else is
    written plainly, because a file full of unnecessary quotes is a file
    people stop hand-editing.
    """
    if value == "":
        return ""
    if any(character.isspace() for character in value) or "#" in value:
        return repr(value)
    return value


def _assignment(line: str) -> str:
    """The variable a line assigns, or ``""`` for a comment or blank."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return ""
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    return stripped.split("=", 1)[0].strip()


def read_dotenv(path: Path) -> dict[str, str]:
    """The variables a ``.env`` sets, with quotes resolved.

    A missing file is an empty mapping and not an error: the first run is
    the case this wizard exists for.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        key = _assignment(line)
        if key:
            values[key] = _parse_value(line.split("=", 1)[1])
    return values


def _rewritten(lines: Sequence[str], updates: dict[str, str | None]) -> list[str]:
    """The original file with the answered keys replaced where they stand.

    Three properties, and the third is the one that is easy to miss:

    *Anything not answered for is copied byte for byte* — comments, blank
    lines, ``export`` prefixes, variables from a future version of this
    program.

    *An answer of ``None`` removes the line* rather than writing an empty
    value, because an empty value is a value and the caller that wants
    one passes ``""``.

    *A key assigned twice is left assigned once.* The file format takes
    the last assignment, so rewriting the first occurrence and leaving a
    stale second one would be a save that reports success and changes
    nothing. The later duplicates of an answered key are dropped; the
    surviving line keeps the original's position.

    :meth:`dict.pop` is what makes the last two properties one mechanism
    rather than two: a key is consumed by the first line that assigns it,
    so a second line finds nothing and is dropped for the same reason a
    removal is. An earlier draft also carried a ``seen`` set, which no
    mutation could kill because it could not change an outcome —— and an
    unkillable branch is a claim that nothing is standing over.
    """
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        key = _assignment(line)
        if not key or key not in updates:
            output.append(line)
            continue
        value = remaining.pop(key, None)
        if value is None:
            continue
        output.append(f"{key}={_serialise_value(value)}")
    for key, value in remaining.items():
        if value is not None:
            output.append(f"{key}={_serialise_value(value)}")
    return output


def write_dotenv(path: Path, updates: Mapping[str, str | None]) -> Path | None:
    """Apply *updates* to *path*. Returns the backup file, if one was made.

    The write is a temporary neighbour plus :meth:`Path.replace`, which is
    atomic within a directory: a reader either sees the whole old file or
    the whole new one, and an interruption cannot leave half a credential
    file behind. The backup is taken before anything is moved, so the
    recovery path does not depend on the save having got far enough to
    matter.

    The mode of an existing file is preserved and a new one is created
    ``0600``. This file holds API keys, and a default-permission ``.env``
    in a shared checkout is a credential handed to every account on the
    machine.
    """
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        original = ""
    lines = original.splitlines() if original else []

    backup: Path | None = None
    if original:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.backup-{stamp}")
        backup.write_text(original, encoding="utf-8")
        backup.chmod(_mode_of(path))

    body = "\n".join(_rewritten(lines, dict(updates)))
    temporary = path.with_name(f"{path.name}.partial")
    temporary.write_text(f"{body}\n" if body else "", encoding="utf-8")
    temporary.chmod(_mode_of(path))
    temporary.replace(path)
    return backup


def _mode_of(path: Path) -> int:
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return 0o600


# ---- asking: questionary when it is there, the standard library when not


class Prompter(Protocol):
    """Four questions, and one way to say "there is no more input".

    Every method raises :exc:`EOFError` when the input ends or the user
    interrupts, which is the same signal
    :class:`~omicsclaw.entry.cli._input.PromptSource` uses for the same
    event — one vocabulary for "the person went away", so the wizard has
    one abandonment path rather than one per prompt library.
    """

    def text(self, message: str, *, default: str = "") -> str: ...

    def secret(self, message: str) -> str: ...

    def confirm(self, message: str, *, default: bool = False) -> bool: ...

    def choose(
        self, message: str, options: Sequence[str], *, default: str = ""
    ) -> str: ...


class StreamPrompter:
    """Questions over two plain text streams. No dependency, no terminal.

    This is the implementation that runs here and in CI, so it is the one
    the tests drive: a fallback exercised only by the branch that says it
    exists is a fallback nobody has run.

    Reading a secret goes through :func:`getpass.getpass` **only when the
    input really is a terminal**. From a pipe there is nothing to hide
    the typing from, and ``getpass`` would try to open ``/dev/tty`` and
    read from somewhere other than the stream it was handed — a prompt
    that answers itself from the wrong place is worse than a visible one.
    """

    def __init__(self, source: TextIO, sink: TextIO) -> None:
        self._source = source
        self._sink = sink

    def _read(self, prompt: str) -> str:
        self._sink.write(prompt)
        self._sink.flush()
        line = self._source.readline()
        if line == "":
            raise EOFError
        return line.strip()

    def text(self, message: str, *, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        answer = self._read(f"{message}{suffix}: ")
        return answer or default

    def secret(self, message: str) -> str:
        if self._is_a_terminal():
            return getpass.getpass(f"{message}: ").strip()
        return self._read(f"{message}: ")

    def confirm(self, message: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        answer = self._read(f"{message} {suffix}: ").lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    def choose(
        self, message: str, options: Sequence[str], *, default: str = ""
    ) -> str:
        choices = list(options)
        while True:
            self._sink.write(f"{message}\n")
            for index, option in enumerate(choices, start=1):
                marker = " *" if option == default else "  "
                self._sink.write(f" {index:2d}){marker} {option}\n")
            answer = self._read(f"Choose 1-{len(choices)} or a name [{default}]: ")
            if not answer:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                return choices[int(answer) - 1]
            if answer in choices:
                return answer
            self._sink.write(f"{answer!r} is not one of them.\n")

    def _is_a_terminal(self) -> bool:
        checker = getattr(self._source, "isatty", None)
        return bool(checker and checker())


class _QuestionaryPrompter:
    """The same four questions with arrow keys, when the package is there.

    ``.ask()`` answers ``None`` when the user presses Ctrl-C, which this
    class turns into the :exc:`EOFError` the protocol is written around.
    """

    def __init__(self, questionary: object) -> None:
        self._questionary = questionary

    def _ask(self, widget: str, *args: object, **kwargs: object) -> object:
        answer = getattr(self._questionary, widget)(*args, **kwargs).ask()
        if answer is None:
            raise EOFError
        return answer

    def text(self, message: str, *, default: str = "") -> str:
        return str(self._ask("text", f"{message}:", default=default)).strip()

    def secret(self, message: str) -> str:
        return str(self._ask("password", f"{message}:")).strip()

    def confirm(self, message: str, *, default: bool = False) -> bool:
        return bool(self._ask("confirm", message, default=default))

    def choose(
        self, message: str, options: Sequence[str], *, default: str = ""
    ) -> str:
        choices = list(options)
        selected = default if default in choices else (choices[0] if choices else "")
        return str(self._ask("select", message, choices=choices, default=selected))


def open_prompter(
    source: TextIO | None = None, sink: TextIO | None = None
) -> Prompter:
    """The best prompter this deployment can build.

    Mirrors :func:`~omicsclaw.entry.cli._input.open_prompt_source`: the
    richer implementation is used only when the input is a terminal *and*
    the optional package is installed, and the degraded one is a normal
    outcome rather than a failure. ``questionary`` is not a declared
    dependency of this project — it appears in ``pyproject.toml`` inside a
    comment — so the import is inside this function and an
    :exc:`ImportError` is expected rather than reported.
    """
    stream = sys.stdin if source is None else source
    output = sys.stdout if sink is None else sink
    checker = getattr(stream, "isatty", None)
    if checker and checker():
        try:
            import questionary
        except ImportError:
            pass
        else:
            return _QuestionaryPrompter(questionary)
    return StreamPrompter(stream, output)


# ---- the questions ----------------------------------------------------


def _mask(value: str) -> str:
    """A secret, shown as the only part of it that is safe to print.

    Four characters is enough for a person to recognise which of their
    keys is in the file and not enough to be one. A short value is shown
    as nothing at all rather than as most of itself.
    """
    if not value:
        return ""
    return f"…{value[-4:]}" if len(value) > 8 else "…"


def _target_key(
    existing: Mapping[str, str], canonical: str, *by_precedence: str
) -> str:
    """Which spelling to write, given the ones already in the file.

    Several variables have more than one accepted name and
    ``resolve_config`` does not read them in the order a person would
    guess: ``DEEPSEEK_API_KEY`` beats ``LLM_API_KEY``, and
    ``OMICSCLAW_MODEL`` beats ``LLM_MODEL``. Writing the canonical
    spelling into a file that already sets a higher-precedence one is a
    save that changes nothing, and the user is left holding a correct
    ``.env`` and a wrong deployment.

    So the highest-precedence name **already present** wins, and the
    canonical one is used only when the file has none of them — which is
    the first-run case, and is where ``.env.example``'s spelling applies.
    """
    for name in by_precedence:
        if name and name in existing:
            return name
    return canonical


def _ask_llm(
    ask: Prompter,
    existing: Mapping[str, str],
    updates: dict[str, str | None],
    sink: TextIO,
) -> str:
    """Provider, key, model, base URL. Returns the backend chosen.

    **Changing the provider clears the endpoint and the model rather than
    carrying them over.** ``.env.example`` warns about exactly this: a
    ``LLM_BASE_URL`` left over from one vendor silently hijacks the next
    one selected, and a model id from one vendor fails against another as
    a 404 that reads like an outage. So an answer is offered as a default
    only while the backend is the same one; otherwise the offer is the
    new preset's model and an empty endpoint, which the resolver reads as
    "use the preset's own".
    """
    sink.write("\n1. Which model backend\n")
    current = detect_provider_from_env(env=existing) or DEFAULT_PROVIDER
    names = _provider_order()
    backend = ask.choose(
        "LLM provider",
        names,
        default=current if current in names else DEFAULT_PROVIDER,
    )
    preset = preset_for(backend)
    if preset is None:
        raise ValueError(f"{backend!r} is not a provider preset")
    updates["LLM_PROVIDER"] = backend
    unchanged = backend == current

    if backend not in KEYLESS_PROVIDERS:
        variable = _target_key(
            existing, "LLM_API_KEY", preset.api_key_env, "LLM_API_KEY",
            "OMICSCLAW_API_KEY",
        )
        held = existing.get(variable, "")
        suffix = f" (stored {_mask(held)}, Enter to keep)" if held else ""
        answer = ask.secret(f"{preset.display_name or backend} API key{suffix}")
        if answer:
            updates[variable] = answer
        elif not held:
            sink.write("   No key set — `oc cli` will refuse to reach a model.\n")

    model_variable = _target_key(
        existing, "LLM_MODEL", "OMICSCLAW_MODEL", "LLM_MODEL"
    )
    held_model = existing.get(model_variable, "")
    model_default = (
        normalize_model_for_provider(backend, held_model)
        if unchanged and held_model
        else preset.default_model
    )
    updates[model_variable] = ask.text("Model id", default=model_default)

    url_variable = _target_key(
        existing,
        "LLM_BASE_URL",
        f"{backend.upper()}_BASE_URL",
        "LLM_BASE_URL",
        "OMICSCLAW_BASE_URL",
    )
    url_default = existing.get(url_variable, "") if unchanged else ""
    hint = preset.base_url or "the SDK's own endpoint"
    while True:
        url = ask.text(f"Base URL (empty = {hint})", default=url_default)
        if url or backend != "custom":
            break
        sink.write("   A custom endpoint is only reachable by its URL.\n")
    updates[url_variable] = url
    return backend


def _provider_order() -> list[str]:
    """Presets in the order the environment is searched, then the rest.

    ``DETECT_ORDER`` is the repository's published preference and is what
    a bare API key resolves through, so a picker that listed the same
    presets alphabetically would be teaching a second order.
    """
    detected = [name for name in DETECT_ORDER if name in PRESETS]
    return detected + [name for name in PRESETS if name not in detected]


def _ask_workspace(
    ask: Prompter,
    existing: Mapping[str, str],
    updates: dict[str, str | None],
    fallback: str,
    sink: TextIO,
) -> None:
    sink.write("\n2. Where the agent may read and write\n")
    default = existing.get("OMICSCLAW_WORKSPACE", "") or fallback
    workspace = ask.text("Workspace directory", default=default)
    updates["OMICSCLAW_WORKSPACE"] = workspace
    if workspace and not Path(workspace).expanduser().is_dir():
        sink.write(f"   {workspace} does not exist yet.\n")


def _ask_telegram(
    ask: Prompter,
    existing: Mapping[str, str],
    updates: dict[str, str | None],
    sink: TextIO,
) -> bool:
    """``oc channel -- --channels telegram``, or nothing.

    The three variables are the ones ``_build_telegram`` refuses to start
    without: the token, and at least one of the two that say whom this
    bot will answer. Asked here rather than left to the adapter because a
    deployment that is configured except for its allowlist starts, runs
    and then refuses every message.
    """
    if not ask.confirm(
        "Configure Telegram", default=bool(existing.get("TELEGRAM_BOT_TOKEN"))
    ):
        return False
    held = existing.get("TELEGRAM_BOT_TOKEN", "")
    suffix = f" (stored {_mask(held)}, Enter to keep)" if held else ""
    token = ask.secret(f"Telegram bot token from @BotFather{suffix}")
    if token:
        updates["TELEGRAM_BOT_TOKEN"] = token
    while True:
        senders = ask.text(
            "Owner user ids, comma-separated",
            default=existing.get("TELEGRAM_ALLOWED_SENDERS", ""),
        )
        chat = ask.text(
            "Admin chat id (optional if owners are listed)",
            default=existing.get("TELEGRAM_CHAT_ID", ""),
        )
        if senders or chat:
            break
        sink.write("   One of the two is required; the bot answers nobody else.\n")
    updates["TELEGRAM_ALLOWED_SENDERS"] = senders
    updates["TELEGRAM_CHAT_ID"] = chat
    return True


def _ask_feishu(
    ask: Prompter,
    existing: Mapping[str, str],
    updates: dict[str, str | None],
    sink: TextIO,
) -> bool:
    """The four variables ``_build_feishu`` refuses to start without."""
    if not ask.confirm(
        "Configure Feishu / Lark", default=bool(existing.get("FEISHU_APP_ID"))
    ):
        return False
    updates["FEISHU_APP_ID"] = ask.text(
        "Feishu app id", default=existing.get("FEISHU_APP_ID", "")
    )
    held = existing.get("FEISHU_APP_SECRET", "")
    suffix = f" (stored {_mask(held)}, Enter to keep)" if held else ""
    secret = ask.secret(f"Feishu app secret{suffix}")
    if secret:
        updates["FEISHU_APP_SECRET"] = secret
    while True:
        senders = ask.text(
            "Owner open_id values, comma-separated",
            default=existing.get("FEISHU_ALLOWED_SENDERS", ""),
        )
        if senders:
            break
        sink.write("   Required: Feishu ingress admits nobody else.\n")
    updates["FEISHU_ALLOWED_SENDERS"] = senders
    while True:
        bot = ask.text(
            "This bot's own open_id",
            default=existing.get("FEISHU_BOT_OPEN_ID", ""),
        )
        if bot:
            break
        sink.write("   Required: group mentions cannot be attributed without it.\n")
    updates["FEISHU_BOT_OPEN_ID"] = bot
    return True


def _ask_desktop(
    ask: Prompter, existing: Mapping[str, str], updates: dict[str, str | None]
) -> bool:
    """The Desktop bearer token, which is not a flag and cannot be one.

    ``oc desktop`` refuses any non-loopback bind while this is empty, so
    it is the one variable that turns the HTTP backend from a private
    socket into something a second machine can reach.
    """
    held = existing.get("OMICSCLAW_REMOTE_AUTH_TOKEN", "")
    if not ask.confirm(
        "Configure a Desktop bearer token", default=bool(held)
    ):
        return False
    suffix = f" (stored {_mask(held)}, Enter to keep)" if held else ""
    token = ask.secret(f"Desktop bearer token{suffix}")
    if token:
        updates["OMICSCLAW_REMOTE_AUTH_TOKEN"] = token
    return True


# ---- the wizard -------------------------------------------------------


def run_configuration_wizard(
    path: Path,
    *,
    workspace_default: str = "",
    prompter: Prompter | None = None,
    sink: TextIO | None = None,
) -> Path | None:
    """Ask, confirm, save. Returns the file written, or ``None``.

    *path* is where the shell reads its ``.env`` from and is not
    negotiated here — see this module's docstring for why that is an
    argument rather than a search.

    ``None`` covers both ways nothing is written: the user declined to
    save, or the input ended before the questions did. Neither is an
    error, so neither raises; the caller reports success and the file on
    disk is exactly what it was.
    """
    output = sys.stdout if sink is None else sink
    ask = open_prompter(sink=output) if prompter is None else prompter
    existing = read_dotenv(path)
    updates: dict[str, str | None] = {}

    output.write("OmicsClaw setup\n")
    verb = "Updating" if path.is_file() else "Creating"
    output.write(f"{verb} {path}\n")

    try:
        backend = _ask_llm(ask, existing, updates, output)
        _ask_workspace(ask, existing, updates, workspace_default, output)
        output.write("\n3. Optional surfaces\n")
        telegram = _ask_telegram(ask, existing, updates, output)
        feishu = _ask_feishu(ask, existing, updates, output)
        _ask_desktop(ask, existing, updates)
        if not ask.confirm(f"Save to {path.name}", default=True):
            output.write("Nothing was written.\n")
            return None
    except EOFError:
        output.write("\nInput ended; nothing was written.\n")
        return None

    backup = write_dotenv(path, updates)
    output.write(f"\nWrote {path}\n")
    if backup is not None:
        output.write(f"Previous version kept at {backup.name}\n")
    _report(output, path, backend, telegram, feishu)
    return path


def _report(
    sink: TextIO, path: Path, backend: str, telegram: bool, feishu: bool
) -> None:
    """What the deployment will now resolve to, read back from the file.

    Read back rather than echoed from the answers, and resolved through
    :func:`~omicsclaw.provider.resolve_config` rather than printed as
    key/value pairs, because the question this answers is "did it take
    effect" — which a variable the file already set at a higher
    precedence can make the answer to differently from what was typed.
    """
    resolved = resolve_config(env=read_dotenv(path))
    sink.write("\nThis deployment now resolves to:\n")
    sink.write(f"  provider  {resolved.provider or '(none)'}\n")
    sink.write(f"  model     {resolved.model}\n")
    sink.write(f"  endpoint  {resolved.base_url or '(the SDK default)'}\n")
    sink.write(f"  api key   {_mask(resolved.api_key) or '(not set)'}\n")
    sink.write("\nStart it with:\n  oc cli\n")
    started = [name for name, on in (("telegram", telegram), ("feishu", feishu)) if on]
    if started:
        sink.write(f"  oc channel -- --channels {','.join(started)}\n")
    if backend in KEYLESS_PROVIDERS:
        sink.write(f"Make sure the {backend} server is running.\n")


def missing_credential_hint(env: Mapping[str, str]) -> str:
    """One line telling a first-time user what to type, or ``""``.

    The cheapest step in a first-run experience: a deployment with no key
    at all reaches a provider error several seconds later, and the remedy
    is a command nothing else in the program mentions. So the whole
    command is printed, ready to paste, rather than a pointer to a
    document.

    Silent when a key is configured, and silent for the backends that
    need none — nagging an Ollama deployment about a key it will never
    have is how a hint teaches people to stop reading hints.
    """
    if resolve_config(env=env).api_key:
        return ""
    if detect_provider_from_env(env=env) in KEYLESS_PROVIDERS:
        return ""
    return (
        "omicsclaw: no LLM API key is configured. Set one up with:\n"
        "    oc cli -- --configure"
    )
