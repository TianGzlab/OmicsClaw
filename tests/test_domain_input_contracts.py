from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "engineering" / "domain-input-contracts.md"


def test_domain_input_contract_document_covers_all_registered_domains():
    text = DOC.read_text(encoding="utf-8")
    domains = [
        "spatial",
        "singlecell",
        "genomics",
        "proteomics",
        "metabolomics",
        "bulkrna",
        "orchestrator",
        "literature",
    ]

    missing: list[str] = []
    for domain in domains:
        marker = f"## {domain}"
        if marker not in text:
            missing.append(f"{domain}: missing section")
            continue
        section = text.split(marker, 1)[1].split("\n## ", 1)[0]
        for label in (
            "**Supported suffixes**:",
            "**Real loader / entrypoint**:",
            "**Minimum fields**:",
            "**Downstream conventions**:",
        ):
            if label not in section:
                missing.append(f"{domain}: missing {label}")
        if "`skills/" not in section and "`omicsclaw/" not in section:
            missing.append(f"{domain}: missing concrete code path")

    assert not missing, "\n".join(missing)
