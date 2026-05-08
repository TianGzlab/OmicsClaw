from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

ARCHITECTURE_CONTRACT_DOCS = [
    "docs/engineering/2026-05-07-framework-optimization-spec.md",
    "docs/engineering/2026-05-07-skill-runner-contract.md",
    "docs/engineering/2026-05-07-output-ownership-contract.md",
    "docs/engineering/2026-05-07-alias-ownership-contract.md",
    "docs/engineering/2026-05-07-bot-runner-contract.md",
    "docs/engineering/2026-05-07-skill-help-contract.md",
    "docs/engineering/domain-input-contracts.md",
]


def _is_tracked(relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_architecture_contract_docs_are_tracked():
    missing = [path for path in ARCHITECTURE_CONTRACT_DOCS if not _is_tracked(path)]

    assert not missing, "\n".join(missing)


def test_readme_links_architecture_contract_docs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [
        path
        for path in ARCHITECTURE_CONTRACT_DOCS
        if path not in readme
    ]

    assert not missing, "\n".join(missing)


def test_readme_records_shared_runner_result_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "omicsclaw/core/skill_result.py" in readme
    assert "Shared result construction" in readme
