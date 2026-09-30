"""The file contracts between skills and the framework (plan 0062 §3.6, case 20).

Tests are the one place allowed to import both sides; that is what these
are for. ``skills/_sdk`` owns the writer side of three contracts — the
result.json envelope, the user-guidance line prefixes and the disclaimer —
and the framework keeps its own reader side in ``omicsclaw/common``. Each
check below feeds one side's output to the other or compares the two.
The ``optional`` part of ``RESULT_SCHEMA`` is documentation only: neither
validator checks ``lineage`` or ``replot`` types or rejects extra keys.
"""

from __future__ import annotations

import ast
import json
import logging

import pytest

from omicsclaw.common import report as framework_report
from omicsclaw.common import user_guidance as framework_guidance
from skills._sdk import report as sdk_report
from skills._sdk import result as sdk_result
from skills._sdk import user_guidance as sdk_guidance
from tests.sdk._scan import REPO_ROOT

_BASE = {
    "skill": "s",
    "version": "1",
    "completed_at": "2026-01-01T00:00:00+00:00",
    "input_checksum": "",
    "summary": {},
    "data": {},
}


def _variant(**changes):
    payload = dict(_BASE)
    for key, value in changes.items():
        if value is _DROP:
            payload.pop(key)
        else:
            payload[key] = value
    return payload


_DROP = object()

SAMPLES = {
    "valid": _variant(),
    "missing-skill": _variant(skill=_DROP),
    "missing-data": _variant(data=_DROP),
    "summary-not-dict": _variant(summary=[]),
    "checksum-not-str": _variant(input_checksum=None),
    "empty-version": _variant(version=""),
    "empty-completed": _variant(completed_at=""),
    "bad-status": _variant(status="done"),
    "scaffold-status": _variant(status="scaffold"),
    "ok-status": _variant(status="ok"),
    "lineage-is-a-string": _variant(lineage="not-a-list"),
    "replot-is-a-string": _variant(replot="x"),
    "extra-key": _variant(anything="goes"),
    "not-an-object": ["a", "list"],
}


def test_sdk_output_passes_both_validators(tmp_path):
    path = sdk_result.write_result_json(tmp_path, "s", "1", {"k": 1}, {"d": 2}, input_checksum="ab")
    payload = json.loads(path.read_text())
    assert sdk_result.validate_result_envelope(payload) == []
    assert framework_report.validate_result_envelope(payload) == []


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_both_validators_agree(name):
    payload = SAMPLES[name]
    sdk_ok = sdk_result.validate_result_envelope(payload) == []
    framework_ok = framework_report.validate_result_envelope(payload) == []
    assert sdk_ok == framework_ok
    if name in {"valid", "scaffold-status", "ok-status", "lineage-is-a-string", "replot-is-a-string", "extra-key"}:
        assert sdk_ok


def test_the_schema_is_a_literal_equal_to_the_import():
    tree = ast.parse((REPO_ROOT / "skills" / "_sdk" / "result.py").read_text(encoding="utf-8"))
    literal = None
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "RESULT_SCHEMA":
            literal = ast.literal_eval(node.value)
    assert literal == sdk_result.RESULT_SCHEMA


def test_the_ensemble_reads_the_device_an_sdk_envelope_reports(tmp_path):
    from omicsclaw.ensemble.runner import TrialResult
    from tests.ensemble.test_runner import _runner

    out = tmp_path / "out"
    envelope = sdk_result.write_result_json(out, "s", "1", {"device": "cuda"}, {})
    result = TrialResult(status="ok", stage="run", run_id="r1", method="m", trial="t0001",
                         output_dir=str(out), params={}, lease_gpu="2")
    _runner(tmp_path)._device(result, {"gpu_probe": "unattributable"}, envelope)
    assert (result.device, result.device_source) == ("cuda:2", "skill")


def test_guidance_lines_written_by_the_sdk_are_parsed_by_the_framework(caplog):
    assert sdk_guidance.USER_GUIDANCE_PREFIX == framework_guidance.USER_GUIDANCE_PREFIX
    assert sdk_guidance.USER_GUIDANCE_JSON_PREFIX == framework_guidance.USER_GUIDANCE_JSON_PREFIX
    logger = logging.getLogger("sdk-guidance-contract")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        sdk_guidance.emit_user_guidance(logger, "Install R first")
        sdk_guidance.emit_user_guidance_payload(logger, {"kind": "hint", "text": "ünïcode"})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert framework_guidance.extract_user_guidance_lines(text)[0] == "Install R first"
    assert framework_guidance.extract_user_guidance_payloads(text) == [{"kind": "hint", "text": "ünïcode"}]


def test_the_disclaimer_is_the_same_text_on_both_sides():
    assert sdk_report.DISCLAIMER == framework_report.DISCLAIMER
    assert sdk_report.DISCLAIMER in sdk_report.generate_report_footer()
