"""Pure literals shared by the step runner, the framework and the tests.

Every name here is a literal that code outside this package reads with
``ast.literal_eval`` instead of importing it, the way ``DEPENDENCIES`` in
``skills/_sdk/deps.py`` is read.

``LAYOUT`` fixes the project layout: the module, step, validate-step and
report names, the output folders a step may write, and where the runner
keeps its state inside a module's results, the review brief included.

``ENVIRONMENT`` names the variables the runner sets for a step's kernel.

``LEDGER_EVENTS`` maps every ledger event to the fields it always carries.
Every ledger line is one JSON object that also carries ``v`` (the ledger
version, 1), ``event`` and ``at`` (UTC, ISO 8601).

``MANIFEST_SCHEMA`` describes ``provenance/manifest.json``: its required
keys and their types, the keys that may be ``null``, the module status
values, the keys and states of each step entry, and the keys of the replay
record and of each ``review_history`` entry.
"""

from __future__ import annotations

__all__ = ["LAYOUT", "MANIFEST_SCHEMA", "LEDGER_EVENTS", "ENVIRONMENT"]

LAYOUT = {
    "module_dir": r"^(\d{2})_([a-z0-9][a-z0-9_]*)$",
    "step_file": r"^(\d{2})([a-z]?)_([a-z0-9][a-z0-9_]*)\.(py|R)$",
    "validate_step": r"^\d{2}[a-z]?_validate\.py$",
    "report": "M{nn}_{slug}_REPORT.md",
    "output_dirs": ["figures", "tables", "intermediate", "logs"],
    "runner_dirs": ["notebooks", "provenance", "reviews", "baseline"],
    "manifest": "provenance/manifest.json",
    "runs": "provenance/runs",
    "review_brief": "provenance/review_brief.md",
    "strategy_file": "docs/analysis_strategy/STRATEGY.md",
    "archive_dir": "results/_archive",
}

ENVIRONMENT = {
    "step_file": "OMICSCLAW_STEP_FILE",
    "step_ledger": "OMICSCLAW_STEP_LEDGER",
    "skill_stubs": "OMICSCLAW_SKILL_STUBS",
    "demo_dir": "OMICSCLAW_DEMO_DIR",
    "step_io": "OMICSCLAW_STEP_IO",
    "sdk_dir": "OMICSCLAW_SDK_DIR",
}

LEDGER_EVENTS = {
    "run_start": ["step", "kind", "mode", "step_sha256", "previous_sha256", "interpreter",
                  "interpreter_changed_from", "stub_dir"],
    "input": ["path", "sha256", "bytes", "via", "outside_contract"],
    "skill_load": ["skill", "root", "candidate", "git", "content_sha256", "dependencies", "stub"],
    "skill_call": ["skill", "function", "args", "seconds", "stub"],
    "skill_cli": ["skill", "script", "argv", "exit_code", "output_dir", "seconds", "stub"],
    "output": ["path", "sha256", "bytes", "kind"],
    "stub_target_missing": ["skill", "names", "reason"],
    "run_end": ["status", "seconds", "error", "notebook", "log"],
    "r_session": ["rscript", "r_version", "packages"],
}

MANIFEST_SCHEMA = {
    "schema": 1,
    "required": {
        "schema": "int", "module": "str", "number": "int", "slug": "str", "status": "str",
        "frozen": "bool", "interpreter": "dict", "steps": "list", "validate_step": "str",
        "replay": "dict", "review": "dict", "review_history": "list", "accepted": "dict", "revisions": "list",
        "report": "str", "rscript": "dict",
    },
    "nullable": ["interpreter", "validate_step", "replay", "review", "accepted", "rscript"],
    "status_values": ["draft", "replayed", "reviewed", "accepted"],
    "step_keys": ["file", "kind", "sha256", "state", "reason", "last_run", "history", "inputs",
                  "outputs", "skills"],
    "step_states": ["ok", "stale", "failed", "never_run"],
    "interpreter_keys": ["path", "prefix", "version", "overlay"],
    "rscript_keys": ["path", "version"],
    "step_kinds": ["python", "r"],
    "replay_keys": ["at", "status", "interpreter", "new_interpreter_reason", "step_sha256",
                    "changed_outputs", "orphan_outputs"],
    "review_history_keys": ["file", "original", "verdict", "sha256", "archived_at"],
}
