"""Deployment settings of the ensemble layer and the sandbox it shares with ``bash``.

The sandbox mounts this repository's ``omicsclaw/`` and ``skills/`` read-only
whether or not the ensemble is on: the ablation baseline of the end-to-end
benchmark runs the same skill scripts through ``bash``, and the two arms must
see the same code. Nothing else of the repository is mounted — its root holds
``.env`` and ``.omicsclaw/``. The resource defaults are sized for several
concurrent trials in one container, and ``sandbox_memory=auto`` leaves 20% of
the machine to the host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.entry.config import AppConfig, AppConfigError, SandboxMode, mem_total_gib, resolve_app_config

REPO = Path(__file__).resolve().parents[2]


def _sandboxed(workspace: Path, **overrides) -> AppConfig:
    return AppConfig(workspace=workspace, sandbox=SandboxMode.DOCKER, sandbox_image="omics:1", **overrides)


def test_every_ensemble_setting_arrives_from_flags_and_the_environment(tmp_path):
    config = resolve_app_config(
        [
            "--workspace", str(tmp_path), "--ensemble", "true", "--ensemble-gpus", "0,1",
            "--ensemble-slots-per-gpu", "2", "--ensemble-memory-gb", "500", "--ensemble-reserved-gb", "32",
            "--ensemble-cpus", "48", "--ensemble-memory-gb-cap", "128", "--ensemble-max-trial", "3600",
            "--ensemble-max-queue", "1800", "--ensemble-keep-all", "true", "--ensemble-python", "/opt/py",
            "--sandbox-tmpfs-size", "8g", "--sandbox-shm-size", "16g", "--sandbox-pids-limit", "9999",
            "--sandbox-nofile", "1024", "--sandbox-code-in-image", "true",
        ],
        env={},
    )  # fmt: skip
    assert config.ensemble is True and config.ensemble_gpus == "0,1"
    assert (config.ensemble_slots_per_gpu, config.ensemble_memory_gb, config.ensemble_reserved_gb) == (2, 500.0, 32.0)
    assert (config.ensemble_cpus, config.ensemble_memory_gb_cap) == (48, 128.0)
    assert (config.ensemble_max_trial_s, config.ensemble_max_queue_s) == (3600.0, 1800.0)
    assert config.ensemble_keep_all and config.ensemble_python == "/opt/py"
    assert (config.sandbox_tmpfs_size, config.sandbox_shm_size) == ("8g", "16g")
    assert (config.sandbox_pids_limit, config.sandbox_nofile, config.sandbox_code_in_image) == (9999, 1024, True)
    env = resolve_app_config([], env={"OMICSCLAW_WORKSPACE": str(tmp_path), "OMICSCLAW_ENSEMBLE": "false"})
    assert env.ensemble is False


def test_the_defaults(tmp_path):
    config = AppConfig(workspace=tmp_path)
    assert config.ensemble is None
    assert (config.ensemble_gpus, config.ensemble_slots_per_gpu, config.ensemble_reserved_gb) == ("", 1, 64.0)
    assert (config.ensemble_max_trial_s, config.ensemble_max_queue_s) == (7200.0, 7200.0)
    assert config.sandbox_memory == "auto"
    assert (config.sandbox_tmpfs_size, config.sandbox_shm_size) == ("64g", "128g")
    assert (config.sandbox_pids_limit, config.sandbox_nofile) == (65536, 65536)


def test_a_bad_ensemble_flag_is_refused(tmp_path):
    with pytest.raises(AppConfigError):
        resolve_app_config(["--workspace", str(tmp_path), "--ensemble", "maybe"], env={})


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


@pytest.mark.parametrize("ensemble", [None, True, False])
def test_the_code_is_mounted_read_only_whatever_the_ensemble_switch(tmp_path, ensemble):
    repo = _repo(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    sandbox = _sandboxed(workspace, skills_dir=repo / "skills", ensemble=ensemble).sandbox_config()
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


def test_the_pool_memory_follows_the_container_limit_in_the_sandbox(tmp_path, monkeypatch):
    from omicsclaw.entry import ensemble
    from omicsclaw.entry.ensemble import _pool_memory
    from omicsclaw.entry.sandbox import SandboxBinding
    from omicsclaw.sandbox import SandboxConfig

    config = AppConfig(workspace=tmp_path)
    running = SandboxBinding(
        mode=SandboxMode.DOCKER, environment=object(), config=SandboxConfig(image="omics:1", memory="1557g")
    )
    assert _pool_memory(config, running) == pytest.approx(1557 - 64 - 128 - 64)
    monkeypatch.setattr(ensemble, "mem_total_gib", lambda: 100.0)
    local = _pool_memory(config, SandboxBinding())
    assert local == pytest.approx(100.0 * 0.8 - 64)
    capped = AppConfig(workspace=tmp_path, ensemble_memory_gb=100)
    assert _pool_memory(capped, running) == 100


def test_a_pool_without_memory_refuses_start_up(tmp_path):
    from omicsclaw.entry.ensemble import _pool_memory
    from omicsclaw.entry.sandbox import SandboxBinding
    from omicsclaw.sandbox import SandboxConfig

    running = SandboxBinding(
        mode=SandboxMode.DOCKER, environment=object(), config=SandboxConfig(image="omics:1", memory="200g")
    )
    with pytest.raises(AppConfigError, match="ensemble pool"):
        _pool_memory(AppConfig(workspace=tmp_path), running)


def test_the_tuning_settings_arrive_from_flags_and_the_environment(tmp_path):
    config = resolve_app_config(
        [
            "--workspace", str(tmp_path), "--ensemble-tools", "free",
            "--ensemble-run-budget", "leiden:60,spagcn:12", "--ensemble-tuning-model", "m1",
            "--ensemble-tuning-tissue", "false", "--ensemble-tuning-budget", "8",
            "--ensemble-tuning-max", "3600", "--ensemble-obs-allowlist", "batch",
        ],
        env={"OMICSCLAW_ENSEMBLE_TUNING_PROVIDER": "deepseek"},
    )
    assert config.ensemble_tools == "free" and config.ensemble_run_budget == "leiden:60,spagcn:12"
    assert (config.ensemble_tuning_model, config.ensemble_tuning_provider) == ("m1", "deepseek")
    assert config.ensemble_tuning_tissue is False and config.ensemble_tuning_budget == 8
    assert config.ensemble_tuning_max_s == 3600.0 and config.ensemble_obs_allowlist == "batch"
    defaults = resolve_app_config(["--workspace", str(tmp_path)], env={})
    assert (defaults.ensemble_tools, defaults.ensemble_run_budget, defaults.ensemble_tuning_budget) == ("all", "", 12)
    assert defaults.ensemble_tuning_tissue is True and defaults.ensemble_tuning_images is False


@pytest.mark.parametrize(
    "flag, value",
    [("--ensemble-tools", "some"), ("--ensemble-run-budget", "leiden:x"), ("--ensemble-tuning-max", "0")],
)
def test_bad_tuning_settings_are_refused(tmp_path, flag, value):
    with pytest.raises(AppConfigError):
        resolve_app_config(["--workspace", str(tmp_path), flag, value], env={})


def test_images_for_the_k_decision_refuse_start_up(tmp_path):
    """Partition images cannot reach a direct model call (messages carry text
    only), so asking for them is refused rather than silently ignored."""
    from omicsclaw.entry.assembly import build_tuning_model

    with pytest.raises(AppConfigError, match="not supported"):
        build_tuning_model(AppConfig(workspace=tmp_path, ensemble_tuning_images=True), provider=None)


def test_the_trial_seed_defaults_to_zero_and_can_be_turned_off(tmp_path):
    from omicsclaw.ensemble.resources import GpuDetection
    from omicsclaw.entry.assembly import build_skill_index
    from omicsclaw.entry.ensemble import build_ensemble
    from omicsclaw.entry.sandbox import SandboxBinding

    assert resolve_app_config(["--workspace", str(tmp_path)], env={}).ensemble_seed == 0
    assert resolve_app_config(["--workspace", str(tmp_path), "--ensemble-seed", "none"], env={}).ensemble_seed is None
    assert resolve_app_config(["--workspace", str(tmp_path)], env={"OMICSCLAW_ENSEMBLE_SEED": "11"}).ensemble_seed == 11
    with pytest.raises(AppConfigError):
        resolve_app_config(["--workspace", str(tmp_path), "--ensemble-seed", "-1"], env={})
    fake = Path(__file__).resolve().parents[1] / "ensemble" / "fake_skills"
    config = AppConfig(workspace=tmp_path, skills_dir=fake, ensemble=True, ensemble_seed=5)
    runner = build_ensemble(config, build_skill_index(config), SandboxBinding(), gpus=GpuDetection((), "none"))
    assert runner.seed == 5
