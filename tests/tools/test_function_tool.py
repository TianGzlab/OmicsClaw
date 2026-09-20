"""Contract tests for ``omicsclaw.tools.function_tool`` (plan 0028, task B).

Traps 8 and 9 of plan 0028 §7 are the subject, and they are two halves of
one property: **a model that got the arguments wrong must be told
something it can act on, and the tool must not run.**

Trap 8 is the sharper half because the wrong behaviour looks like success.
:meth:`ToolCall.parsed_arguments <omicsclaw.schema.ToolCall.parsed_arguments>`
answers ``{}`` for a truncated payload *by design* — raising there would
crash runs — so an adapter built on it calls the function with no
arguments and reports whatever that returns. The named tests below are the
pair that separates "the model sent ``{}``" from "the model's ``{}`` is
the wreckage of a longer payload"; each asserts the *function call* as
well as the result, because "did not run" is the half a message-only
assertion would miss.

The wording cross-check is the other subject, and it is here rather than
in a separate file because it is a property of :func:`validate_arguments`
rather than a study of the module it replaced: plan 0028 §5 required that
rewrite and required the rewrite not to drift.

That check used to load ``omicsclaw/runtime/tools/validation.py`` from
disk and compare against it live. The framework rebuild deleted the legacy
tool layer, so the expectations below are a **frozen snapshot** of what
that validator answered, captured from the last revision that shipped it
and verified equal to this implementation at the time of capture. The
coverage is the same — full message lists, in order — and it no longer
depends on a module that is gone.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import sys
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.schema import ToolCall, ToolDefinition
from omicsclaw.tools import FunctionTool, ToolArgumentError, ToolPolicy, ToolRegistry
from omicsclaw.tools.function_tool import as_text, validate_arguments

_T = TypeVar("_T")

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; ``tests/provider/`` drives this way."""
    return asyncio.run(asyncio.wait_for(main, 5.0))


def _call(name: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(id="c1", name=name, arguments=arguments)


class Recorder:
    """A function that remembers being called, so "did not run" is assertable."""

    def __init__(self, result: Any = "ok") -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._result


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "limit": {"type": "integer"},
        "method": {"type": "string", "enum": ["leiden", "louvain"]},
    },
    "required": ["path"],
}

_OPEN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
}


def _tool(func: Any, *, schema: dict[str, Any] | None = None) -> FunctionTool:
    return FunctionTool("analyze", "Analyze something.", func, parameters=schema)


# ---- the shape of a tool -------------------------------------------------


def test_a_plain_callable_becomes_a_tool():
    tool = _tool(Recorder(), schema=_OPEN_SCHEMA)

    assert tool.name == "analyze"
    assert isinstance(tool.definition(), ToolDefinition)
    assert tool.definition().name == "analyze"
    assert tool.definition().description == "Analyze something."
    assert tool.definition().input_schema == _OPEN_SCHEMA


def test_a_tool_with_no_declared_schema_still_offers_an_object_schema():
    """Vendors reject a function whose parameters are absent, not merely empty."""
    assert _tool(Recorder()).definition().input_schema == {
        "type": "object",
        "properties": {},
    }


def test_two_tools_taking_the_default_schema_do_not_share_it():
    """Including the nested ``properties`` a shallow copy would still share.

    The bug this is the regression for is invisible until a second tool
    exists: one tool's schema is edited and another tool's parameters
    change, in a value the model is shown.
    """
    first = _tool(Recorder())
    second = _tool(Recorder())

    first.definition().input_schema["properties"]["leaked"] = {"type": "string"}

    assert second.definition().input_schema == {"type": "object", "properties": {}}


def test_two_tools_given_one_schema_constant_do_not_share_it():
    """The same defect on the path that was left unguarded.

    ``_default_schema()`` was made a factory to stop tools sharing nested
    state, and the explicit ``parameters=`` path then stored
    ``dict(parameters)`` — a shallow copy, under which every tool built
    from one module-level constant kept pointing at that constant's
    ``properties``. The natural way to migrate fifty tools is a
    module-level ``SCHEMA`` beside each of them, so this is the spelling
    that will actually be written.

    Three victims, because the damage has three directions: the sibling
    tool's ``definition()`` is what the *model* is shown, the constant is
    the caller's own, and the tool's validation reads the same dict its
    definition does.
    """
    shared: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    first = _tool(Recorder(), schema=shared)
    second = _tool(Recorder(), schema=shared)

    first.definition().input_schema["properties"]["path"]["type"] = "integer"
    first.definition().input_schema["required"].append("leaked")

    assert second.definition().input_schema["properties"]["path"] == {
        "type": "string"
    }
    assert second.definition().input_schema["required"] == ["path"]
    assert shared["properties"]["path"] == {"type": "string"}
    assert shared["required"] == ["path"]
    assert validate_arguments({"path": "/d"}, shared) == []


# ``test_a_reference_tools_factory_gives_each_instance_its_own_schema``
# stood here. It drove the same guard through ``sequence_tool()``, one of
# plan 0028's three reference tools, to show the deep copy survived moving
# from the call site into the adapter. The reference tools were removed
# (owner, 2026-09-18) and with them the only thing that test asserted
# beyond its neighbour above — which covers the same property through the
# spelling fifty migrated tools will actually use.


def test_the_definition_is_stable_between_turns():
    """The prompt prefix it is serialized into is billed on staying identical."""
    tool = _tool(Recorder(), schema=_SCHEMA)

    assert tool.definition() is tool.definition()


def test_the_registry_mounts_a_function_tool_and_reads_its_policy():
    """Structural conformance: no base class, no registration argument."""
    policy = ToolPolicy(read_only=True)
    tool = FunctionTool("probe", "d", Recorder(), policy=policy)
    registry = ToolRegistry([tool])

    assert registry.get("probe") is tool
    assert registry.policy_for("probe") is policy


def test_a_function_tool_without_a_policy_resolves_to_the_guarded_default():
    registry = ToolRegistry([FunctionTool("probe", "d", Recorder())])

    assert registry.policy_for("probe") == ToolPolicy()


# ---- trap 8: unreadable is not the same as absent ------------------------


def test_a_truncated_payload_is_reported_as_unreadable_and_the_tool_does_not_run():
    """Plan 0028 trap 8, the half that would otherwise pass silently.

    The schema requires nothing, so an adapter that decoded this payload
    with ``parsed_arguments()`` semantics would get ``{}``, call the
    function with no arguments, and return its cheerful output as the
    Observation — a call the model never finished sending, reported as a
    success. ``recorder.calls`` is the assertion that matters; the
    message assertions only say the refusal is usable.
    """
    recorder = Recorder("swept the whole workspace")
    registry = ToolRegistry([_tool(recorder, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", '{"note": "half a sent')))

    assert recorder.calls == []
    assert result.is_error is True
    assert "not valid JSON" in result.output
    assert "half a sent" in result.output
    assert "swept the whole workspace" not in result.output


def test_an_empty_object_payload_runs_the_tool_instead_of_being_rejected():
    """The other half of trap 8: ``{}`` from a model is a real, valid call."""
    recorder = Recorder()
    registry = ToolRegistry([_tool(recorder, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", "{}")))

    assert recorder.calls == [{}]
    assert result.is_error is False
    assert result.output == "ok"


@pytest.mark.parametrize("payload", ["", "   ", "\n"])
def test_an_absent_payload_reads_as_no_arguments(payload: str):
    """Vendors emit an empty string for an argument-free call."""
    recorder = Recorder()
    registry = ToolRegistry([_tool(recorder, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", payload)))

    assert recorder.calls == [{}]
    assert result.is_error is False


@pytest.mark.parametrize(
    ("payload", "described"),
    [('["path"]', "array"), ('"path"', "string"), ("7", "number"), ("null", "null")],
)
def test_a_readable_payload_that_is_not_an_object_is_refused(
    payload: str, described: str
):
    """Decodable, and still unusable: none of these become keyword arguments.

    ``parsed_arguments()`` answers ``{}`` for every one of them, which is
    the same silent-success failure as a truncation, reached by a
    different route.
    """
    recorder = Recorder()
    registry = ToolRegistry([_tool(recorder, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", payload)))

    assert recorder.calls == []
    assert result.is_error is True
    assert "must be a JSON object" in result.output
    assert described in result.output


def test_an_enormous_malformed_payload_is_quoted_back_only_in_part():
    """The excerpt rides in the conversation tail and is paid for every turn."""
    registry = ToolRegistry([_tool(Recorder(), schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", '{"note": "' + "x" * 5000)))

    assert result.is_error is True
    assert len(result.output) < 600
    assert "truncated" in result.output


# ---- trap 9: a validation failure is an Observation, not a crash ---------


def test_a_missing_required_argument_becomes_an_error_result():
    """Plan 0028 trap 9. Nothing raises out of ``registry.execute``."""
    recorder = Recorder()
    registry = ToolRegistry([_tool(recorder, schema=_SCHEMA)])

    result = _run(registry.execute(_call("analyze", '{"limit": 3}')))

    assert recorder.calls == []
    assert result.is_error is True
    assert "input.path is required" in result.output


def test_the_rejection_lists_every_problem_at_once():
    """A retry costs a whole turn, so one turn should be able to fix everything."""
    registry = ToolRegistry([_tool(Recorder(), schema=_SCHEMA)])

    result = _run(
        registry.execute(_call("analyze", '{"limit": "three", "method": "kmeans"}'))
    )

    assert "input.path is required" in result.output
    assert "input.limit must be an integer; got str" in result.output
    assert "input.method must be one of ['leiden', 'louvain']" in result.output


def test_a_rejection_names_the_tool_once_and_asks_for_a_corrected_call():
    """The registry supplies the name; repeating it wastes a line per failure."""
    registry = ToolRegistry([_tool(Recorder(), schema=_SCHEMA)])

    result = _run(registry.execute(_call("analyze", "{}")))

    assert result.output.count("analyze") == 1
    assert result.output.startswith("tool 'analyze' raised ToolArgumentError:")
    assert "Re-send" in result.output


def test_an_unexpected_argument_is_refused_when_the_schema_closes_the_object():
    """The documented remedy for a schema and a signature disagreeing.

    Without ``additionalProperties: false`` the surplus key reaches the
    function and fails there as a ``TypeError`` about a keyword argument,
    which names a Python detail the model cannot act on.
    """
    closed = {**_SCHEMA, "additionalProperties": False}
    registry = ToolRegistry([_tool(Recorder(), schema=closed)])

    result = _run(registry.execute(_call("analyze", '{"path": "p", "verbose": 1}')))

    assert result.is_error is True
    assert "input.verbose is not allowed" in result.output


def test_validation_failure_raises_a_named_exception_rather_than_returning_text():
    """Checked directly, because the registry is what makes it an Observation.

    ``execute`` returns ``str``, so there is no in-band way to say "this
    is an error"; raising is the seam's failure protocol and the registry
    is where it becomes ``is_error``. Pinning the class here stops a
    future refactor from turning the rejection into ordinary output that
    the model would read as a successful result.
    """
    tool = _tool(Recorder(), schema=_SCHEMA)

    with pytest.raises(ToolArgumentError):
        _run(tool.execute("{}"))


# ---- calling the function ------------------------------------------------


def test_the_function_receives_keyword_arguments():
    seen: dict[str, Any] = {}

    def probe(*, path: str, limit: int = 10) -> str:
        seen.update(path=path, limit=limit)
        return "done"

    registry = ToolRegistry([_tool(probe, schema=_SCHEMA)])
    result = _run(registry.execute(_call("analyze", '{"path": "/d", "limit": 3}')))

    assert seen == {"path": "/d", "limit": 3}
    assert result.output == "done"


def test_an_async_function_is_awaited():
    async def probe(*, note: str = "") -> str:
        await asyncio.sleep(0)
        return f"slept for {note}"

    registry = ToolRegistry([_tool(probe, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", '{"note": "a while"}')))

    assert result.output == "slept for a while"


def test_a_function_can_reject_its_own_arguments_the_same_way():
    """The successor to ``ToolSpec.input_validator``, checked end to end.

    A check no JSON Schema can express — here, one argument forbidding
    another — reaches the model as a correction rather than as a crash,
    and reaches it through the same path a schema failure takes. That is
    what makes the third slot the legacy ``ToolSpec`` needed unnecessary:
    the function and the validator are the same object now.
    """

    def probe(*, path: str, method: str = "leiden") -> str:
        if path.startswith("/etc") and method != "leiden":
            raise ToolArgumentError(
                "input.method must be 'leiden' for a path under /etc"
            )
        return "ran"

    registry = ToolRegistry([_tool(probe, schema=_SCHEMA)])

    result = _run(
        registry.execute(_call("analyze", '{"path": "/etc/x", "method": "louvain"}'))
    )

    assert result.is_error is True
    assert "must be 'leiden' for a path under /etc" in result.output


def test_a_function_can_normalise_its_own_arguments():
    """The other half of ``input_validator``: it could rewrite arguments too."""
    seen: list[str] = []

    def probe(*, path: str) -> str:
        seen.append(path.rstrip("/"))
        return seen[-1]

    registry = ToolRegistry([_tool(probe, schema=_SCHEMA)])

    assert _run(registry.execute(_call("analyze", '{"path": "/d/"}'))).output == "/d"
    assert seen == ["/d"]


def test_a_raising_function_becomes_an_error_result_carrying_its_message():
    def probe(**_: Any) -> str:
        raise RuntimeError("the reference genome is missing")

    registry = ToolRegistry([_tool(probe, schema=_OPEN_SCHEMA)])

    result = _run(registry.execute(_call("analyze", "{}")))

    assert result.is_error is True
    assert "the reference genome is missing" in result.output


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("already text", "already text"),
        (None, ""),
        ({"genes": ["TP53"]}, '{"genes": ["TP53"]}'),
        ([1, 2], "[1, 2]"),
        (3, "3"),
        (True, "true"),
    ],
)
def test_a_returned_value_becomes_the_text_a_model_can_read(value: Any, expected: str):
    assert as_text(value) == expected


def test_a_returned_value_json_cannot_encode_falls_back_to_its_repr():
    class Opaque:
        def __repr__(self) -> str:
            return "<an AnnData object>"

    assert as_text(Opaque()) == '"<an AnnData object>"'


def test_non_latin_output_survives_as_itself():
    assert as_text({"组织": "肝"}) == '{"组织": "肝"}'


# ---- the cross-check against the validator being replaced ----------------
#
# The legacy tool layer is deleted. What it answered for every case below
# is frozen in ``_EXPECTED``, so the wording contract outlives the module
# that set it.

_NESTED: dict[str, Any] = {
    "type": "object",
    "required": ["inner"],
    "properties": {"inner": {"type": "integer"}},
}

_FULL: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "limit": {"type": "integer"},
        "ratio": {"type": "number"},
        "force": {"type": "boolean"},
        "method": {"type": "string", "enum": ["leiden", "louvain"]},
        "genes": {"type": "array", "items": {"type": "string"}},
        "nested": _NESTED,
    },
    "required": ["path"],
}

_CLOSED: dict[str, Any] = {**_FULL, "additionalProperties": False}

_CROSSCHECK: list[tuple[str, Any, Any]] = [
    ("everything valid", {"path": "/d", "limit": 3, "ratio": 1.5}, _FULL),
    ("missing required", {"limit": 3}, _FULL),
    ("string got int", {"path": 7}, _FULL),
    ("integer got str", {"path": "/d", "limit": "3"}, _FULL),
    ("integer got bool", {"path": "/d", "limit": True}, _FULL),
    ("number got bool", {"path": "/d", "ratio": False}, _FULL),
    ("number got int is fine", {"path": "/d", "ratio": 2}, _FULL),
    ("boolean got int", {"path": "/d", "force": 1}, _FULL),
    ("enum miss", {"path": "/d", "method": "kmeans"}, _FULL),
    ("enum miss non-string", {"path": "/d", "method": 4}, _FULL),
    ("enum miss null", {"path": "/d", "method": None}, _FULL),
    ("array got string", {"path": "/d", "genes": "TP53"}, _FULL),
    ("array item wrong", {"path": "/d", "genes": ["TP53", 7, None]}, _FULL),
    ("array empty", {"path": "/d", "genes": []}, _FULL),
    ("nested missing required", {"path": "/d", "nested": {}}, _FULL),
    ("nested not an object", {"path": "/d", "nested": 5}, _FULL),
    ("nested field wrong", {"path": "/d", "nested": {"inner": "x"}}, _FULL),
    ("several at once", {"limit": "x", "method": "kmeans", "genes": 3}, _FULL),
    ("extra key, open object", {"path": "/d", "verbose": True}, _FULL),
    ("extra key, closed object", {"path": "/d", "verbose": True}, _CLOSED),
    ("two extra keys, closed", {"path": "/d", "a": 1, "b": 2}, _CLOSED),
    ("closed and missing required", {"a": 1}, _CLOSED),
    ("root is a list", ["path"], _FULL),
    ("root is a string", "path", _FULL),
    ("root is None", None, _FULL),
    ("root is empty", {}, _FULL),
    ("schema is None", {"path": "/d"}, None),
    ("schema is a string", {"path": "/d"}, "not a schema"),
    ("schema is an int", {"path": "/d"}, 7),
    ("schema has no type", {"path": "/d"}, {"properties": {"path": {}}}),
    ("schema type unknown", {"path": "/d"}, {"type": "null"}),
    ("schema type is a list", "x", {"type": ["string", "null"]}),
    ("required is None", {"a": 1}, {"type": "object", "required": None}),
    ("properties is None", {"a": 1}, {"type": "object", "properties": None}),
    ("items is not a mapping", [1, 2], {"type": "array", "items": "string"}),
    ("enum containing a bool", 1, {"enum": [True, "yes"]}),
    ("enum containing an int", True, {"enum": [1, "yes"]}),
    ("bare enum satisfied", "yes", {"enum": ["yes", "no"]}),
    ("array of objects", [{"inner": "x"}, {}], {"type": "array", "items": _NESTED}),
    ("deeply nested", {"path": "/d", "nested": {"inner": [1]}}, _FULL),
]


_EXPECTED: dict[str, list[str]] = {
    'everything valid': [],
    'missing required': ['input.path is required'],
    'string got int': ['input.path must be a string; got int'],
    'integer got str': ['input.limit must be an integer; got str'],
    'integer got bool': ['input.limit must be an integer; got bool'],
    'number got bool': ['input.ratio must be a number; got bool'],
    'number got int is fine': [],
    'boolean got int': ['input.force must be a boolean; got int'],
    'enum miss': [
        "input.method must be one of ['leiden', 'louvain']; got 'kmeans'",
    ],
    'enum miss non-string': [
        "input.method must be one of ['leiden', 'louvain']; got 4",
    ],
    'enum miss null': [
        "input.method must be one of ['leiden', 'louvain']; got None",
    ],
    'array got string': ['input.genes must be an array; got str'],
    'array item wrong': [
        'input.genes[1] must be a string; got int',
        'input.genes[2] must be a string; got NoneType',
    ],
    'array empty': [],
    'nested missing required': ['input.nested.inner is required'],
    'nested not an object': ['input.nested must be an object; got int'],
    'nested field wrong': ['input.nested.inner must be an integer; got str'],
    'several at once': [
        'input.path is required',
        'input.limit must be an integer; got str',
        "input.method must be one of ['leiden', 'louvain']; got 'kmeans'",
        'input.genes must be an array; got int',
    ],
    'extra key, open object': [],
    'extra key, closed object': ['input.verbose is not allowed'],
    'two extra keys, closed': [
        'input.a is not allowed',
        'input.b is not allowed',
    ],
    'closed and missing required': [
        'input.path is required',
        'input.a is not allowed',
    ],
    'root is a list': ['input must be an object; got list'],
    'root is a string': ['input must be an object; got str'],
    'root is None': ['input must be an object; got NoneType'],
    'root is empty': ['input.path is required'],
    'schema is None': [],
    'schema is a string': [],
    'schema is an int': [],
    'schema has no type': [],
    'schema type unknown': [],
    'schema type is a list': [],
    'required is None': [],
    'properties is None': [],
    'items is not a mapping': [],
    'enum containing a bool': [],
    'enum containing an int': [],
    'bare enum satisfied': [],
    'array of objects': [
        'input[0].inner must be an integer; got str',
        'input[1].inner is required',
    ],
    'deeply nested': ['input.nested.inner must be an integer; got list'],
}
"""Every case above, with the exact list the deleted legacy validator
answered for it. Captured from the last revision that shipped
``omicsclaw/runtime/tools/validation.py`` and verified equal to
:func:`validate_arguments` at capture time."""


@pytest.mark.parametrize(
    ("label", "value", "schema"),
    _CROSSCHECK,
    ids=[label for label, _, _ in _CROSSCHECK],
)
def test_validation_says_exactly_what_the_legacy_validator_said(
    label: str, value: Any, schema: Any
):
    """Plan 0028 §5: the rewrite must not drift from the fifty tools' wording.

    Full message lists are compared, in order — not counts, not
    truthiness. The messages are the product here: an enum failure phrased
    differently is a different thing for a model to read, and half the
    existing tools' prompts were written against these exact strings.
    """
    assert validate_arguments(value, schema) == _EXPECTED[label]


_ISOLATION_CORPUS: list[tuple[Any, Any]] = [
    ({}, _FULL),
    ({"path": "/d", "limit": "x"}, _FULL),
    ({"path": "/d", "method": "kmeans"}, _FULL),
    ({"path": "/d", "genes": ["TP53", 7]}, _FULL),
    ({"path": "/d", "verbose": True}, _CLOSED),
    ({"path": "/d", "nested": {"inner": "x"}}, _FULL),
    ({"path": "/d"}, _FULL),
]
"""A JSON-round-trippable slice of ``_CROSSCHECK``, for the subprocess below.

Six failures and one clean pass, so the isolated run has to produce
*messages* rather than seven empty lists — an agreement on nothing is the
false green this whole section is built to avoid.
"""

_ISOLATION_EXPECTED: list[list[str]] = [
    [
        'input.path is required',
    ],
    [
        'input.limit must be an integer; got str',
    ],
    [
        "input.method must be one of ['leiden', 'louvain']; got 'kmeans'",
    ],
    [
        'input.genes[1] must be a string; got int',
    ],
    [
        'input.verbose is not allowed',
    ],
    [
        'input.nested.inner must be an integer; got str',
    ],
    [],
]
"""What the deleted legacy validator answered for ``_ISOLATION_CORPUS``."""


_ISOLATION_PROBE = """
import json
import sys


class Blocker:
    @staticmethod
    def find_spec(name, *args, **kwargs):
        if name.split(".")[:2] == ["omicsclaw", "runtime"]:
            raise ImportError("blocked: " + name)
        return None


sys.meta_path.insert(0, Blocker())

from omicsclaw.tools.function_tool import validate_arguments

corpus = json.loads({corpus!r})
print(json.dumps([validate_arguments(value, schema) for value, schema in corpus]))
"""


def test_the_validator_produces_its_messages_with_the_legacy_layer_unreachable():
    """A re-export would make every case above pass without proving anything.

    This used to be three assertions about identity — that
    ``validate_arguments.__module__`` is this module, that ``_LEGACY``
    was loaded from the legacy file, and that the two functions are not
    the same object. All three hold of a **one-line delegation**::

        def validate_arguments(arguments, schema):
            legacy = importlib.import_module("omicsclaw.runtime.tools.validation")
            return legacy.validate_arguments_against_schema(arguments, schema)

    — a different object, defined in this module, wrapping the legacy one.
    So they caught the spelling ``from ... import ... as`` and nothing
    else, while the crossing plan 0028 §5 forbids by name is precisely the
    one they missed.

    What is asserted instead is the property the re-implementation was
    *for*: in a process where ``omicsclaw.runtime`` cannot be imported at
    all, this validator still produces the legacy wording, in order,
    message for message. A delegation of any spelling — eager, lazy, by
    string, by path — dies on the blocker and takes the subprocess's
    return code with it.
    """
    corpus_json = json.dumps(_ISOLATION_CORPUS)
    probe = subprocess.run(
        [sys.executable, "-c", _ISOLATION_PROBE.format(corpus=corpus_json)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == _ISOLATION_EXPECTED


def test_the_isolation_probe_is_comparing_something_to_something():
    """The fixture half, kept: an empty expectation would agree with anything.

    The snapshot has to carry real messages, or the corpus comparison
    above is an agreement about nothing.
    """
    assert sum(1 for issues in _ISOLATION_EXPECTED if issues) == 6
    assert _ISOLATION_EXPECTED[-1] == []
    assert len(_ISOLATION_EXPECTED) == len(_ISOLATION_CORPUS)


def test_the_crosscheck_corpus_actually_produces_failures():
    """An agreement on forty empty lists is an agreement about nothing."""
    assert set(_EXPECTED) == {label for label, _, _ in _CROSSCHECK}
    produced = [_EXPECTED[label] for label, _, _ in _CROSSCHECK]
    failing = [issues for issues in produced if issues]
    messages = {message for issues in failing for message in issues}

    assert len(failing) >= 20
    assert any(len(issues) > 1 for issues in failing), "no multi-issue case"
    assert any("is required" in m for m in messages)
    assert any("is not allowed" in m for m in messages)
    assert any("must be one of" in m for m in messages)
    assert any("must be an object" in m for m in messages)
    assert any("must be an array" in m for m in messages)
    assert any("must be an integer" in m for m in messages)
    assert any("must be a number" in m for m in messages)
    assert any("must be a boolean" in m for m in messages)
    assert any("must be a string" in m for m in messages)
    assert any("[0]" in m for m in messages), "no array index path"
    assert any(m.count(".") >= 2 for m in messages), "no nested path"


def test_the_root_of_a_complaint_is_called_input():
    """Part of the byte-identity: the fifty tools' messages start this way."""
    assert validate_arguments({}, _FULL) == ["input.path is required"]


def test_a_rejection_message_is_json_safe_for_the_conversation():
    """It travels as message content, so it must survive the trip unchanged."""
    registry = ToolRegistry([_tool(Recorder(), schema=_SCHEMA)])

    result = _run(registry.execute(_call("analyze", '{"method": "k\\"means"}')))

    assert json.loads(json.dumps(result.output)) == result.output
