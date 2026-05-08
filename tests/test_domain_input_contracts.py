from __future__ import annotations

import subprocess
from pathlib import Path

from omicsclaw.core.registry import OmicsRegistry


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "docs" / "engineering" / "domain-input-contracts.md"


def test_domain_input_contract_document_is_tracked():
    relative_path = CONTRACT_PATH.relative_to(ROOT)
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(relative_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (
        "Domain input contracts must be tracked, not just present in a local "
        f"ignored workspace: {relative_path}\n{result.stderr}"
    )


def test_domain_input_contract_document_exists_for_all_registered_domains():
    registry = OmicsRegistry()
    registry.load_all()

    text = CONTRACT_PATH.read_text(encoding="utf-8")
    missing: list[str] = []
    for domain in sorted(registry.domains):
        heading = f"## {domain}"
        if heading not in text:
            missing.append(heading)

    assert not missing, "\n".join(missing)


def test_domain_input_contracts_name_required_sections():
    text = CONTRACT_PATH.read_text(encoding="utf-8")

    required_fragments = [
        "**Supported suffixes**",
        "**Real loader / entrypoint**",
        "**Minimum fields**",
        "**Downstream conventions**",
        "omicsclaw/loaders/__init__.py",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]

    assert not missing, "\n".join(missing)
