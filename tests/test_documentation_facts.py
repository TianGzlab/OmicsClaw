from __future__ import annotations

from collections import Counter
from pathlib import Path

from omicsclaw.core.registry import OmicsRegistry


ROOT = Path(__file__).resolve().parent.parent


def _registry_counts() -> tuple[int, dict[str, int]]:
    reg = OmicsRegistry()
    reg.load_all()
    items = reg.iter_primary_skills()
    counts = Counter(str(info.get("domain", "")).strip() for _, info in items)
    return len(items), dict(counts)


def test_public_docs_match_registry_skill_counts():
    total, counts = _registry_counts()
    domain_count = len(counts)

    expected_fragments = {
        "README.md": [
            f"**{total} registered skills**",
        ],
        "README_zh-CN.md": [
            f"{total} 个分析技能",
            f"全部 {total} 个技能的机器可读注册表",
        ],
        "AGENTS.md": [
            f"{counts['spatial']} spatial transcriptomics skills",
            f"{counts['singlecell']} single-cell omics skills",
            f"{counts['genomics']} genomics skills",
            f"{counts['proteomics']} proteomics skills",
            f"{counts['metabolomics']} metabolomics skills",
            f"{counts['bulkrna']} bulk RNA skills",
            f"{counts['orchestrator']} orchestration skills",
            f"{counts['literature']} literature skill",
        ],
        "docs/architecture/overview.mdx": [
            f"{total} 个 skill",
            f"{domain_count} 个 domain",
        ],
        "docs/architecture/skill-system.mdx": [
            f"{total} 个 skill",
            f"{domain_count} 个领域",
            f"（共 {counts['spatial']} 个）",
            f"singlecell/    （{counts['singlecell']} 个）",
            f"literature/    （{counts['literature']} 个）",
        ],
        "docs/architecture/orchestrator.mdx": [
            f"{total} 个 skill",
            f"{domain_count} 个组学/支撑领域",
        ],
    }

    missing: list[str] = []
    for relative_path, fragments in expected_fragments.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in text:
                missing.append(f"{relative_path}: {fragment}")

    assert not missing, "\n".join(missing)


def test_public_docs_do_not_claim_legacy_framework_facts():
    stale_fragments = {
        "AGENTS.md": [
            "supporting 5 domains",
            "List all 50+ skills across 5 domains",
            "`execute_omicsclaw()` — runs `omicsclaw.py run <skill>` as subprocess",
        ],
        "omicsclaw.py": [
            "List all 50+ available analysis skills",
        ],
        "omicsclaw/interactive/_constants.py": [
            "50+ analysis skills",
        ],
        "tests/test_execution_default_executor.py": [
            "default ``SubprocessExecutor`` wiring used by /jobs",
            "test_build_default_executor_returns_subprocess_executor",
            "test_jobs_router_default_executor_is_subprocess_executor",
        ],
        "docs/architecture/overview.mdx": [
            "cmd 拼接 → skill 入口脚本路径 + flags",
            "subprocess 执行 skill 脚本",
        ],
    }

    found: list[str] = []
    for relative_path, fragments in stale_fragments.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment in text:
                found.append(f"{relative_path}: {fragment}")

    assert not found, "\n".join(found)
