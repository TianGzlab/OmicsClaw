"""What ``install_skill_deps`` lets reach pip, and how it reads what pip reports back.

Pure functions. Packages come from this machine's pip configuration, which is
not inspected here beyond one question: whether it, or the environment pip
runs with, would install somewhere other than the overlay or into another
interpreter. Requirements put
on pip's command line are checked against a narrow grammar; artifacts in
pip's JSON report are checked for direct URLs, non-archives and non-wheels,
and described by the scheme and host of their own URL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote, urlsplit

__all__ = [
    "LOCATION_KEYS",
    "LOCATION_VARIABLES",
    "RequirementError",
    "artifact_source",
    "artifact_transport",
    "check_pin",
    "check_requirement",
    "clean_environment",
    "config_list_environment",
    "foreign_reason",
    "location_settings",
    "pip_environment",
    "redact",
    "wheel_name",
]

LOCATION_KEYS = frozenset({"target", "prefix", "root", "user", "src", "python"})
"""pip settings that choose where, or into which interpreter, packages are installed."""

LOCATION_VARIABLES = tuple(f"PIP_{key.upper()}" for key in sorted(LOCATION_KEYS))
"""The same settings as environment variables."""

_LISTING_OVERRIDES = {"PIP_QUIET": "0", "PIP_GLOBAL": "0", "PIP_SITE": "0", "PIP_USER": "0"}
"""Forced while listing pip's configuration: ``quiet`` would silence the listing,
and ``global``, ``site`` and ``user`` would restrict it to one file. An environment
variable outranks every configuration file."""

_PASSED_TO_PIP = frozenset({
    "PATH", "HOME", "LANG", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
})
_PROXIES = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY"})

_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_EXTRAS = rf"\[ *{_NAME}(?: *, *{_NAME})* *\]"
_CLAUSE = r"(?:~=|===|==|!=|<=|>=|<|>) *[A-Za-z0-9.*+!_-]+"
_REQUIREMENT = re.compile(rf"{_NAME}(?: *{_EXTRAS})?(?: *{_CLAUSE}(?: *, *{_CLAUSE})*)? *")
_PIN_NAME = re.compile(_NAME)
_PIN_VERSION = re.compile(r"[A-Za-z0-9.!+_][A-Za-z0-9.!+_-]*")
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s'\"]*@")


class RequirementError(ValueError):
    """A requirement or pin that is not a plain name, optional extras and optional version constraints."""


def check_requirement(spec: str, *, source: str) -> str:
    """*spec* with its spaces removed, if it is a name, optional extras and optional constraints.

    Spaces may surround operators, commas and brackets. Anything else —
    ``@``, ``;``, ``:``, ``/``, ``\\``, a URL, a control character, a leading
    ``-``, or text after the name that is not a constraint — is refused.

    :param source: Where *spec* came from, named in the error.
    :raises RequirementError: *spec* is not of that form.
    """
    if not _REQUIREMENT.fullmatch(spec):
        raise RequirementError(
            f"{source}: {spec!r} is not a plain requirement (a name, optional [extras] and optional "
            "version constraints such as >=1.2,<2); direct URLs, environment markers and pip options "
            "are not installed by install_skill_deps"
        )
    return spec.replace(" ", "")


def check_pin(name: str, version: str) -> str:
    """``name==version`` for a package pip resolved, if both parts are well formed.

    :raises RequirementError: The name is not a project name, or the version
        has characters a PEP 440 version cannot have or starts with ``-``.
    """
    if not _PIN_NAME.fullmatch(name) or not _PIN_VERSION.fullmatch(version):
        raise RequirementError(f"pip resolved {name!r} {version!r}, which is not a name and version it can be given")
    return f"{name}=={version}"


def location_settings(config_list: str, pip_env: Mapping[str, str]) -> tuple[str, ...]:
    """The settings that would make pip install outside the overlay, described for a person.

    :param config_list: What ``pip config list`` printed, one ``key=value`` per line.
        An ``:env:`` line comes from a ``PIP_`` variable of the listing's own
        environment or from a configuration-file section named ``[:env:]``; it is
        judged like any other line, except for the four keys the listing forces
        (``quiet``, ``global``, ``site``, ``user``), whose ``:env:`` lines echo those
        forced values.
    :param pip_env: The environment pip installs with. Every ``PIP_`` variable
        counts, its name normalised as pip normalises it.
    :returns: One description per offending key or variable; empty when there are none.
        Only key names are read: a value is never parsed.
    """
    found: list[str] = []
    for line in config_list.splitlines():
        key, equals, _ = line.partition("=")
        if not equals:
            continue
        key = key.strip()
        section, _, last = key.rpartition(".")
        option = _option(last)
        if option not in LOCATION_KEYS:
            continue
        if section == ":env:":
            if option in _FORCED_OPTIONS:
                continue
            found.append(f"{key} (a PIP_ variable, or an [:env:] section of a pip configuration file)")
        else:
            found.append(f"{key} in a pip configuration file (`pip config debug` shows which)")
    for name in pip_env:
        if name.startswith("PIP_") and _option(name[4:]) in LOCATION_KEYS:
            found.append(f"{name} in the environment")
    return tuple(found)


def config_list_environment(pip_env: Mapping[str, str]) -> dict[str, str]:
    """The environment ``pip config list`` runs with: *pip_env*, with verbosity and file selection forced.

    ``PIP_QUIET``, ``PIP_GLOBAL``, ``PIP_SITE`` and ``PIP_USER`` are set to ``0``,
    replacing any spelling of them in *pip_env*, so the listing is printed and
    covers every configuration file ``pip install`` reads.
    """
    kept = {
        name: value
        for name, value in pip_env.items()
        if not (name.startswith("PIP_") and _option(name[4:]) in _FORCED_OPTIONS)
    }
    return {**kept, **_LISTING_OVERRIDES}


def _option(name: str) -> str:
    """*name* as pip normalises an option name: lower case, ``_`` to ``-``, a leading ``--`` removed."""
    return name.lower().replace("_", "-").removeprefix("--")


_FORCED_OPTIONS = frozenset(_option(name[4:]) for name in _LISTING_OVERRIDES)


def pip_environment(agent: Mapping[str, str]) -> dict[str, str]:
    """The environment pip runs with during an installation.

    ``PATH``, ``HOME``, ``LANG``, ``LC_*``, ``TMPDIR``, the XDG cache and config
    directories, the CA bundle variables and the proxy variables (either
    case) are taken from *agent*, as is every ``PIP_*`` variable. Then
    ``PYTHONNOUSERSITE``, ``PIP_NO_INPUT`` and ``PIP_DISABLE_PIP_VERSION_CHECK``
    are set to ``1``. Nothing else is passed.
    """
    env = {
        name: value
        for name, value in agent.items()
        if name in _PASSED_TO_PIP
        or name.startswith("LC_")
        or name.upper() in _PROXIES
        or name.startswith("PIP_")
    }
    env.update(PYTHONNOUSERSITE="1", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    return env


def clean_environment(agent: Mapping[str, str], home: str) -> dict[str, str]:
    """The environment for interpreters started in the overlay once new packages are in it.

    Only ``PATH``, ``LANG``, ``LC_*`` and ``LD_LIBRARY_PATH`` come from *agent*;
    ``HOME`` and ``TMPDIR`` are *home*, and ``PYTHONNOUSERSITE`` is ``1``. No
    proxy, certificate or ``PIP_*`` variable is passed.
    """
    env = {
        name: value
        for name, value in agent.items()
        if name in ("PATH", "LANG", "LD_LIBRARY_PATH") or name.startswith("LC_")
    }
    env.update(HOME=home, TMPDIR=home, PYTHONNOUSERSITE="1")
    return env


def foreign_reason(item: Mapping[str, Any]) -> str:
    """Why an entry of pip's installation report is not an ordinary wheel; ``""`` when it is.

    An entry is foreign when it came from a direct URL (a dependency named by
    URL, which pip follows to any host), when it is not an archive (a VCS
    checkout or a local directory), or when the file is not a wheel.
    """
    info = item.get("download_info") or {}
    url = str(info.get("url") or "")
    if item.get("is_direct"):
        return f"it was named by a direct URL ({redact(url)})"
    if "archive_info" not in info:
        return f"it is not an archive but a VCS checkout or directory ({redact(url)})"
    if not wheel_name(url).endswith(".whl"):
        return f"it is not a wheel ({redact(url)})"
    return ""


def wheel_name(url: str) -> str:
    """The file name at the end of *url*'s path."""
    return unquote(urlsplit(url).path.rsplit("/", 1)[-1])


def artifact_source(url: str) -> str:
    """Where an artifact came from: ``scheme://host[:port]`` without user info, or ``file:<directory>``."""
    parts = urlsplit(url)
    if parts.scheme.lower() == "file":
        return "file:" + unquote(parts.path.rsplit("/", 1)[0] or "/")
    host = parts.netloc.rsplit("@", 1)[-1]
    return f"{parts.scheme.lower()}://{host}"


def artifact_transport(url: str) -> str:
    """The scheme of the artifact's own URL: ``https``, ``http`` (plain text) or ``file``."""
    return urlsplit(url).scheme.lower()


def redact(text: str) -> str:
    """*text* with the user info of every URL in it replaced by ``***``."""
    return _USERINFO.sub(r"\1***@", text)
