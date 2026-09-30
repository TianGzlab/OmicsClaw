"""Every ``tuning.yaml`` agrees with the argparse of the script it describes.

The search space and the script are two files, and nothing but this test
keeps them from drifting: a renamed flag would make every trial of that
parameter fail at argument parsing, and a changed script default would make
the "default" trial in the spec a different run from the script's own
default. The real parser is captured by running the script's ``main()`` in a
subprocess with ``ArgumentParser.parse_args`` patched to raise before the
script does anything, so the test reads exactly what the script builds.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from omicsclaw.ensemble.space import TuningCatalog, TuningSpec
from omicsclaw.skills import load_skills

REPO = Path(__file__).resolve().parents[2]

_PROBE = r"""
import argparse, json, runpy, sys

class _Captured(Exception):
    def __init__(self, parser):
        self.parser = parser

def _capture(self, *args, **kwargs):
    raise _Captured(self)

argparse.ArgumentParser.parse_args = _capture
sys.argv = [sys.argv[1]]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except _Captured as captured:
    actions = []
    for action in captured.parser._actions:
        if not action.option_strings:
            continue
        kind = getattr(action.type, "__name__", None) if action.type is not None else None
        actions.append({
            "flags": list(action.option_strings),
            "dest": action.dest,
            "type": kind,
            "action": type(action).__name__,
            "choices": list(action.choices) if action.choices is not None else None,
            "default": action.default if isinstance(action.default, (str, int, float, bool, type(None))) else repr(action.default),
        })
    print("ACTIONS=" + json.dumps(actions))
else:
    print("NO_PARSER")
"""


def _actions(script: Path) -> dict[str, dict]:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, str(script)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", "MPLBACKEND": "Agg", "HOME": "/tmp"},
    )
    line = next(
        (item for item in completed.stdout.splitlines() if item.startswith("ACTIONS=")), None
    )
    assert line is not None, completed.stdout[-2000:] + completed.stderr[-4000:]
    by_flag: dict[str, dict] = {}
    for action in json.loads(line[len("ACTIONS="):]):
        for flag in action["flags"]:
            by_flag[flag] = action
    return by_flag


def _expected_type(action: dict) -> str | None:
    if action["action"] in ("_StoreTrueAction", "_StoreFalseAction"):
        return "switch"
    return {"float": "float", "int": "int", "str2bool": "bool", None: "str", "str": "str"}.get(
        action["type"], action["type"]
    )


def mismatches(spec: TuningSpec, actions: dict[str, dict], skill_name: str) -> list[str]:
    """Every disagreement between *spec* and the parser's *actions*."""
    problems: list[str] = []
    if spec.skill != skill_name:
        problems.append(f"skill {spec.skill!r} != SKILL.md name {skill_name!r}")
    if not spec.script_path.is_file():
        problems.append(f"script {spec.script} does not exist")
    if spec.method_flag is not None:
        method_action = actions.get(spec.method_flag)
        if method_action is None:
            problems.append(f"method flag {spec.method_flag} is not in the parser")
        elif set(method_action["choices"] or ()) != set(spec.methods):
            problems.append(
                f"methods {sorted(spec.methods)} != {spec.method_flag} choices "
                f"{sorted(method_action['choices'] or ())}"
            )
    params = [*spec.context.values()]
    for method in spec.methods.values():
        params.extend(method.params.values())
    for param in params:
        action = actions.get(param.flag)
        if action is None:
            problems.append(f"{param.name}: flag {param.flag} is not in the parser")
            continue
        kind = _expected_type(action)
        if param.type == "bool":
            wanted = "switch" if param.switch else "bool"
            if kind != wanted:
                problems.append(f"{param.name}: bool needs {wanted}, parser has {kind}")
        elif param.type == "categorical":
            element = {int: "int", float: "float", str: "str"}[type(param.choices[0])]
            if kind != element:
                problems.append(f"{param.name}: choices are {element}, parser type is {kind}")
            if action["choices"] is not None and not set(param.choices) <= set(action["choices"]):
                problems.append(f"{param.name}: choices not a subset of {action['choices']}")
        elif kind != param.type:
            problems.append(f"{param.name}: {param.type} but parser type is {kind}")
        default = action["default"]
        if default is None:
            if param.default is not None and not param.note:
                problems.append(
                    f"{param.name}: parser default is None; the note must say where "
                    f"{param.default!r} comes from"
                )
        elif default != param.default or type(default) is not type(param.default):
            problems.append(f"{param.name}: default {param.default!r} != parser default {default!r}")
    return problems


def _specs() -> list[tuple[TuningSpec, str]]:
    index = load_skills(REPO / "skills")
    catalogue = TuningCatalog.from_skills(index)
    assert not catalogue.skipped, catalogue.skipped
    return [(spec, index.get(spec.skill).name) for spec in catalogue.specs()]


SPECS = _specs()


@pytest.fixture(scope="module")
def parsed():
    return {spec.skill: _actions(spec.script_path) for spec, _ in SPECS}


def test_there_is_at_least_one_tuning_file():
    assert any(spec.skill == "spatial-domains" for spec, _ in SPECS)


@pytest.mark.parametrize("spec, skill_name", SPECS, ids=[spec.skill for spec, _ in SPECS])
def test_the_tuning_file_matches_the_script(spec, skill_name, parsed):
    assert mismatches(spec, parsed[spec.skill], skill_name) == []


def _spatial_domains():
    return next(spec for spec, _ in SPECS if spec.skill == "spatial-domains")


def _with_param(spec: TuningSpec, method: str, name: str, **changes) -> TuningSpec:
    methods = dict(spec.methods)
    params = dict(methods[method].params)
    params[name] = dataclasses.replace(params[name], **changes)
    methods[method] = dataclasses.replace(methods[method], params=params)
    return dataclasses.replace(spec, methods=methods)


def test_a_renamed_flag_is_caught(parsed):
    spec = _with_param(_spatial_domains(), "leiden", "resolution", flag="--resolutoin")
    assert any("--resolutoin" in problem for problem in mismatches(spec, parsed[spec.skill], spec.skill))


def test_a_removed_method_is_caught(parsed):
    spec = _spatial_domains()
    methods = {name: method for name, method in spec.methods.items() if name != "banksy"}
    spec = dataclasses.replace(spec, methods=methods)
    assert any("choices" in problem for problem in mismatches(spec, parsed[spec.skill], spec.skill))


def test_a_changed_default_is_caught(parsed):
    spec = _with_param(_spatial_domains(), "leiden", "spatial_weight", default=0.4)
    assert any("spatial_weight" in problem for problem in mismatches(spec, parsed[spec.skill], spec.skill))


def test_a_none_default_without_a_note_is_caught(parsed):
    spec = _with_param(_spatial_domains(), "cellcharter", "auto_k_max", note="")
    assert any("auto_k_max" in problem for problem in mismatches(spec, parsed[spec.skill], spec.skill))
