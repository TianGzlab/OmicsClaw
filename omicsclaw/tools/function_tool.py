"""``FunctionTool`` — a plain callable, wearing the :class:`Tool` shape.

Plan 0028 §4 Q1. Most tools are a function: some arguments in, some text
out. Making each of them a hand-written class with three members would be
ceremony, and the fifty tools waiting to be migrated are all plain
functions today, so the adapter is what they arrive through.

What the adapter adds is the part a plain function has no way to do for
itself: **turning the model's mistakes into something the model can fix.**
Two of them, and they are different mistakes:

*The payload was unreadable.* :meth:`ToolCall.parsed_arguments
<omicsclaw.schema.ToolCall.parsed_arguments>` answers ``{}`` for a
truncated or malformed payload, by design — it exists so a bad argument
string cannot crash a run. But ``{}`` is also what a genuinely
argument-free call looks like, so a tool that used it would run with no
arguments and report success for a call that was never fully transmitted.
This adapter never calls it. A payload that does not decode is reported as
undecodable, with the decoder's own complaint and a bounded excerpt of
what actually arrived, and the function is not invoked. Plan 0028 trap 8.

*The arguments were readable but wrong.* Checked against the tool's own
declared schema, and every problem is listed at once so one retry can fix
all of them. Plan 0028 trap 9.

**Both are reported by raising** :exc:`ToolArgumentError`, which is how
this seam spells failure: ``execute`` returns ``str``, so there is no
in-band way to say "this is an error", and
:meth:`~omicsclaw.tools.registry.ToolRegistry.execute` is what turns an
exception into an ``is_error`` Observation. What trap 9 forbids is a
validation failure that ends the run; one raised inside ``execute`` never
leaves the registry.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools.base``, and the
standard library.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any

from omicsclaw.schema import ToolDefinition

from .base import ToolPolicy

_EXCERPT_LIMIT = 120
"""Characters of a rejected payload echoed back to the model.

Enough to see where a truncation happened, short enough that a tool called
with a megabyte of malformed JSON does not put a megabyte into the
conversation — and the excerpt rides in the tail, outside the cached
prefix, so it is paid for every turn it survives.
"""

_ROOT_PATH = "input"
"""What the top level of an argument object is called in a complaint.

Byte-identical to ``omicsclaw/runtime/tools/validation.py``, which the
existing fifty tools' messages are written against. See
:func:`validate_arguments`.
"""


def _default_schema() -> dict[str, Any]:
    """A fresh empty object schema, never the same dict twice.

    A module-level constant handed out with ``dict(...)`` would still
    share its nested ``properties`` mapping with every tool that took the
    default, so one tool editing its own schema would edit theirs.
    """
    return {"type": "object", "properties": {}}


class ToolArgumentError(ValueError):
    """The model's arguments could not be used, and the model can fix it.

    A ``ValueError`` because that is what it is, but the class matters
    less than the text: this exception's message is delivered verbatim to
    a model that is expected to correct itself from it. "invalid input" is
    a failed message; "input.threshold is required" is a successful one.

    **Public so a tool can raise it.** It is the successor to
    ``ToolSpec.input_validator``, and the way a check no JSON Schema can
    express — "this path is inside the workspace", "these two options are
    mutually exclusive" — reaches the model as a correction rather than
    as a crash.
    """


class FunctionTool:
    """One callable, exposed as a tool.

    ``func`` is called with the decoded arguments **as keyword
    arguments** — ``func(**arguments)`` — so the function's own signature
    is the second, executable statement of what it accepts, and a
    parameter that the schema and the code disagree about shows up as a
    :exc:`TypeError` rather than as a silently missing value.

    The consequence worth knowing: a schema property whose name is not a
    Python identifier, or one the function does not accept, reaches
    ``func`` and fails there. Declaring ``additionalProperties: false``
    turns that into a schema complaint the model can act on, which is the
    recommended shape and is why the check is implemented.

    A returned value that is not already ``str`` goes through
    :func:`as_text`. Synchronous and ``async`` callables are both
    accepted.

    ``parameters`` is **deep-copied**, so a schema handed to two tools —
    the module-level ``SCHEMA`` constant the fifty migrating tools will
    each want — is two independent schemas, and neither of them is the
    caller's.

    ``policy`` is the *author's* view of this tool and is read by
    :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for`; leaving it
    ``None`` resolves to ``ToolPolicy()``, which grants nothing.

    **There is no ``input_validator`` hook, and its absence is the
    point.** The existing tool layer needs one because a tool's metadata
    and its executor are two objects: a check that is neither pure schema
    nor part of the run has nowhere to live, so a third slot was added for
    it. Here the function *is* the tool, so "validate, normalise, then
    run" is three statements in one body — the function coerces its own
    arguments and raises :exc:`ToolArgumentError` for anything a schema
    cannot express, and gets the same correctable ``is_error`` Observation
    this class produces. The capability is kept; the slot is not.

    **A known limitation, stated rather than hidden:** the wrapped
    function receives decoded keyword arguments and never sees the raw
    payload, so a function calling
    :func:`~omicsclaw.tools.context.require_approval` cannot show a human
    the exact bytes the model sent — only what it can reconstruct. A tool
    whose approval prompt must be byte-faithful should be written against
    the :class:`~omicsclaw.tools.base.Tool` Protocol directly, where
    ``execute`` is handed the payload unparsed.
    """

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        *,
        parameters: Mapping[str, Any] | None = None,
        policy: ToolPolicy | None = None,
    ) -> None:
        self._name = name
        self._func = func
        # ``deepcopy``, and the depth is the whole of it. ``dict(...)``
        # copies the top level and leaves every tool sharing the nested
        # ``properties`` mapping of the dict it was handed — so one tool
        # editing its own schema edits the *argument table another tool
        # shows the model*, and writes through to the caller's constant.
        # The natural migration spelling is a module-level ``SCHEMA`` fed
        # to several ``FunctionTool``s, which is exactly the shape that
        # triggers it, so this is not a hypothetical.
        self._schema: dict[str, Any] = (
            copy.deepcopy(dict(parameters))
            if parameters is not None
            else _default_schema()
        )
        self._definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=self._schema,
        )
        self.policy = policy

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        """The same object every turn.

        Built once rather than per call: a definition that is rebuilt is a
        definition that can drift, and the prompt prefix these are
        serialized into is worth an order of magnitude in billing when it
        stays byte-identical between turns.

        It shares the schema dict with :func:`validate_arguments`
        deliberately, so the schema the model was shown and the schema its
        arguments are checked against cannot be two different things.
        """
        return self._definition

    async def execute(self, arguments: str) -> str:
        arguments_dict = decode_arguments(arguments)
        issues = validate_arguments(arguments_dict, self._schema)
        if issues:
            raise ToolArgumentError(_rejection(issues))

        outcome = self._func(**arguments_dict)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return as_text(outcome)


def validate_arguments(
    arguments: Any,
    schema: Mapping[str, Any] | None,
) -> list[str]:
    """Problems with ``arguments`` under ``schema``, worst-first by depth.

    **A deliberate re-implementation of
    ``omicsclaw/runtime/tools/validation.py``, not a reuse of it.** Plan
    0028 §5 records the trade: this package may import ``omicsclaw.schema``
    and nothing else inside the ``omicsclaw`` namespace (§9-4), and the
    legacy validator lives under ``omicsclaw.runtime.tools`` — the one
    import that would look entirely unremarkable in a diff, since that
    package is also called ``tools``.

    Rewriting a validator normally means diverging from it, and the fifty
    tools whose prompts and tests were written against the old wording
    would each diverge separately and silently. So the rule adopted here
    is **byte-identical output**: same messages, same ordering, same
    path syntax, same root name ``input``, same treatment of
    ``additionalProperties: false``, same enum phrasing. It is pinned by a
    cross-check in ``tests/tools/test_function_tool.py`` that loads the
    legacy module from its file and compares full message lists over a
    corpus, so a divergence introduced later fails rather than ships.

    **Known differences: none.** Known *shared* limits, inherited on
    purpose rather than fixed, because fixing them here would be the
    divergence the cross-check exists to prevent:

    ``anyOf`` / ``oneOf`` / ``allOf`` / ``$ref`` / ``const`` / ``format``,
    the numeric bounds (``minimum``, ``maximum``, ``multipleOf``), the
    string bounds (``minLength``, ``pattern``) and the array bounds
    (``minItems``, ``uniqueItems``) are all **not checked** — a schema
    using them is accepted and the constraint is not enforced. ``type``
    is matched only when it is one of the six spelled out below; any other
    value, including a list of types and ``"null"``, is not checked.
    A tool needing one of these validates it in its own body, where it can
    also phrase the error in its own terms.

    Returns an empty list when ``schema`` is not a mapping, which is what
    "this tool declared no schema" means.
    """
    if not isinstance(schema, Mapping):
        return []
    return _issues(arguments, schema, path=_ROOT_PATH)


def as_text(value: Any) -> str:
    """One rule for turning whatever a tool returned into what a model reads.

    Shared by :class:`FunctionTool` and
    :class:`~omicsclaw.tools.mcp_tool.MCPTool` so there is one rule rather
    than two that drift. JSON for anything structured, because a model
    reads ``{"genes": ["TP53"]}`` and cannot reliably read the Python
    ``repr`` of the same dict; ``ensure_ascii=False`` so non-Latin text
    survives as itself.

    ``None`` becomes the empty string rather than ``"null"``: a tool that
    returned nothing said nothing, and the engine already substitutes a
    placeholder for an empty Observation, in the wording the deployment
    configured.
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


# ---- reading what the model sent ----------------------------------------


def decode_arguments(arguments: str) -> dict[str, Any]:
    """The raw payload as a dict, or a complaint the model can act on.

    **Public, and it had to become so.** A tool written against the
    :class:`~omicsclaw.tools.base.Tool` Protocol directly — which is the
    documented way to get a byte-faithful approval prompt — has the same
    payload to read and no adapter to read it for it. While this was
    private, ``builtin/gene_panel.py`` wrote its own copy, and the two had
    already drifted: the copy dropped the character count and the excerpt,
    which are the parts trap 8 exists for, so a model whose call was
    truncated was told the JSON was bad without being shown where it
    stopped. :mod:`omicsclaw.tools.mcp_tool` states the rule this breaks —
    two implementations of one rule are one implementation and one bug —
    and it applies here.

    Three outcomes a caller must not conflate, which is the whole point of
    not reusing ``parsed_arguments()``:

    *Absent* — an empty or blank payload — reads as ``{}``. Vendors emit
    ``""`` for a call with no arguments, so this is not a mistake; if the
    schema requires something, validation says so next, naming the field.

    *Unreadable* raises. This is the case ``{}`` would hide.

    *Readable but not an object* raises too: a JSON array or string cannot
    become keyword arguments, and answering ``{}`` would run the tool with
    none of what the model sent.

    **None of these messages names the tool.**
    :meth:`~omicsclaw.tools.registry.ToolRegistry.execute` already
    prefixes ``tool 'x' raised ToolArgumentError:``, and a second copy of
    the name in the same sentence is a wasted line in every failing
    Observation the model reads.
    """
    text = arguments.strip() if isinstance(arguments, str) else arguments
    if not text:
        return {}
    try:
        decoded = json.loads(text)
    except ValueError as exc:
        raise ToolArgumentError(
            f"the arguments were not valid JSON ({exc}). Received "
            f"{len(arguments)} characters starting {_excerpt(arguments)}. "
            "Re-send the call with one complete JSON object."
        ) from exc
    if not isinstance(decoded, dict):
        raise ToolArgumentError(
            f"the arguments must be a JSON object, but a "
            f"{_json_type_name(decoded)} arrived: {_excerpt(arguments)}. "
            "Re-send the call with an object of named arguments."
        )
    return decoded


def _rejection(issues: list[str]) -> str:
    """Every problem at once, because a retry costs a whole turn."""
    listed = "\n".join(f"  - {issue}" for issue in issues)
    return (
        "the arguments do not match this tool's schema:\n"
        f"{listed}\nRe-send the call with all of these corrected."
    )


# ---- validation internals -----------------------------------------------


def _issues(value: Any, schema: Mapping[str, Any], *, path: str) -> list[str]:
    """One node of the walk. Mirrors the legacy ``_validate_value`` exactly."""
    found: list[str] = []
    expected_type = schema.get("type")
    enum_values = schema.get("enum")

    if enum_values is not None and value not in list(enum_values):
        # Checked before ``type`` and returning immediately, so an enum
        # miss is reported once instead of as a type complaint as well.
        return [f"{path} must be one of {list(enum_values)!r}; got {value!r}"]

    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path} must be an object; got {_type_name(value)}"]
        for key in schema.get("required", []) or []:
            if key not in value:
                found.append(f"{path}.{key} is required")
        properties = schema.get("properties", {}) or {}
        if schema.get("additionalProperties", True) is False:
            for key in value:
                if key not in properties:
                    found.append(f"{path}.{key} is not allowed")
        for key, nested in properties.items():
            if key in value and isinstance(nested, Mapping):
                found.extend(_issues(value[key], nested, path=f"{path}.{key}"))
        return found

    if expected_type == "array":
        if not isinstance(value, list):
            return [f"{path} must be an array; got {_type_name(value)}"]
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                found.extend(_issues(item, items, path=f"{path}[{index}]"))
        return found

    if expected_type == "string" and not isinstance(value, str):
        return [f"{path} must be a string; got {_type_name(value)}"]

    if expected_type == "integer" and (
        isinstance(value, bool) or not isinstance(value, int)
    ):
        # ``bool`` is an ``int`` in Python and is not one in JSON Schema.
        return [f"{path} must be an integer; got {_type_name(value)}"]

    if expected_type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        return [f"{path} must be a number; got {_type_name(value)}"]

    if expected_type == "boolean" and not isinstance(value, bool):
        return [f"{path} must be a boolean; got {_type_name(value)}"]

    return found


def _type_name(value: Any) -> str:
    """The **Python** type name, as the legacy validator reports it.

    ``got NoneType`` rather than ``got null``, because that is the wording
    the existing tools' callers already read. Changing it would be the
    kind of small improvement that makes a cross-check impossible.
    """
    return type(value).__name__


def _json_type_name(value: Any) -> str:
    """The JSON name of a decoded top-level value.

    Used only where the complaint is about the payload as a whole rather
    than a schema violation, so it is free to speak the model's dialect —
    a model that sent ``[1, 2]`` is helped more by "array" than by "list".
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _excerpt(payload: Any) -> str:
    """A bounded, quoted look at what actually arrived.

    ``repr`` rather than the raw text, so a payload that is whitespace, or
    that ends mid-escape, is visible as such instead of blending into the
    sentence around it.
    """
    text = payload if isinstance(payload, str) else str(payload)
    if len(text) <= _EXCERPT_LIMIT:
        return repr(text)
    return f"{text[:_EXCERPT_LIMIT]!r} (truncated)"


__all__ = [
    "FunctionTool",
    "ToolArgumentError",
    "as_text",
    "decode_arguments",
    "validate_arguments",
]
