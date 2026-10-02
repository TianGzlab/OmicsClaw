"""Container resource settings and the code mounts of the sandbox ``bash`` runs in.

The sandbox mounts this repository's ``omicsclaw/`` and ``skills/`` read-only,
so ``bash`` runs the skill scripts of the repository this process runs from.
Nothing else of the repository is mounted: its root holds ``.env`` and
``.omicsclaw/``. ``sandbox_memory=auto`` leaves 20% of the machine to the host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.entry.config import AppConfig, SandboxMode, mem_total_gib, resolve_app_config

REPO = Path(__file__).resolve().parents[2]


def _sandboxed(workspace: Path, **overrides) -> AppConfig:
    return AppConfig(workspace=workspace, sandbox=SandboxMode.DOCKER, sandbox_image="omics:1", **overrides)


def test_the_resource_settings_arrive_from_flags(tmp_path):
    config = resolve_app_config(
        [
            "--workspace", str(tmp_path),
            "--sandbox-tmpfs-size", "8g", "--sandbox-shm-size", "16g", "--sandbox-pids-limit", "9999",
            "--sandbox-nofile", "1024", "--sandbox-code-in-image", "true",
        ],
        env={},
    )  # fmt: skip
    assert (config.sandbox_tmpfs_size, config.sandbox_shm_size) == ("8g", "16g")
    assert (config.sandbox_pids_limit, config.sandbox_nofile, config.sandbox_code_in_image) == (9999, 1024, True)


def test_the_defaults(tmp_path):
    config = AppConfig(workspace=tmp_path)
    assert config.sandbox_memory == "auto"
    assert (config.sandbox_tmpfs_size, config.sandbox_shm_size) == ("64g", "128g")
    assert (config.sandbox_pids_limit, config.sandbox_nofile) == (65536, 65536)


def test_auto_memory_is_eighty_percent_of_memtotal(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       2041151900 kB\nMemFree: 1 kB\n")
    assert mem_total_gib(meminfo) == pytest.approx(1946.6, abs=0.1)
    config = _sandboxed(tmp_path)
    assert config.sandbox_memory_value(meminfo) == "1557g"
    assert _sandboxed(tmp_path, sandbox_memory="64g").sandbox_memory_value(meminfo) == "64g"
    assert _sandboxed(tmp_path, sandbox_memory="").sandbox_memory_value(meminfo) == ""
    assert config.sandbox_memory_value(tmp_path / "missing") == ""


def test_the_sandbox_config_carries_the_resource_settings(tmp_path):
    sandbox = _sandboxed(tmp_path, sandbox_shm_size="8g", sandbox_nofile=4096).sandbox_config()
    assert (sandbox.shm_size, sandbox.nofile, sandbox.pids_limit, sandbox.tmpfs_size) == ("8g", 4096, 65536, "64g")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "omicsclaw").mkdir(parents=True)
    (repo / "skills").mkdir()
    (repo / ".env").write_text("LLM_API_KEY=x\n")
    return repo


def test_the_code_is_mounted_read_only(tmp_path):
    repo = _repo(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    sandbox = _sandboxed(workspace, skills_dir=repo / "skills").sandbox_config()
    assert sandbox.read_only_mounts == (repo / "omicsclaw", repo / "skills")
    assert repo not in sandbox.read_only_mounts


def test_nothing_is_mounted_twice_when_the_workspace_is_the_repository(tmp_path):
    repo = _repo(tmp_path)
    assert _sandboxed(repo).sandbox_config().read_only_mounts == ()
    assert _sandboxed(tmp_path, skills_dir=repo / "skills").sandbox_config().read_only_mounts == ()


def test_code_in_the_image_turns_the_mounts_off(tmp_path):
    repo = _repo(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    config = _sandboxed(workspace, skills_dir=repo / "skills", sandbox_code_in_image=True)
    assert config.sandbox_config().read_only_mounts == ()


def test_operator_mounts_come_first_and_are_not_repeated(tmp_path):
    repo = _repo(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    config = _sandboxed(workspace, skills_dir=repo / "skills", sandbox_mounts=(Path("/ref"), repo / "skills"))
    assert config.sandbox_config().read_only_mounts == (Path("/ref"), repo / "skills", repo / "omicsclaw")


def test_this_repository_is_found_from_its_skills_directory(tmp_path):
    config = _sandboxed(tmp_path, skills_dir=REPO / "skills")
    assert config.repo_root() == REPO
    assert config.code_mounts() == (REPO / "omicsclaw", REPO / "skills")
