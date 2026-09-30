"""``SandboxConfig``: the recalibrated defaults, and what it refuses."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from omicsclaw.sandbox import NETWORK_NONE, SandboxConfig, SandboxConfigError


def test_the_defaults_are_recalibrated_for_omics_rather_than_ported():
    """harness9's ``ubuntu:22.04`` / 1 CPU / 512m / 256 pids / open network
    were tuned for SWE-bench repositories. One ``sc.pp.neighbors()`` needs
    more than 512m, BLAS threads count against the pids cgroup, and the
    threat this project guards is data leaving the machine — so the network
    is off and nothing is capped unless an operator caps it."""
    config = SandboxConfig(image="omics:1")

    assert config.network == NETWORK_NONE
    assert config.isolates_network
    assert config.memory == "" and config.cpus == "" and config.gpus == ""
    assert config.pids_limit == 65536
    assert config.tmpfs_size == "64g"
    assert config.shm_size == "128g"
    assert config.nofile == 65536
    assert config.runtime == "docker"
    assert config.bootstrap == ""
    assert config.bootstrap_timeout_s == 600.0


def test_the_default_user_is_this_process():
    """Files a command writes into the bind-mounted workspace must belong
    to the person running the agent, not to root."""
    assert SandboxConfig(image="x").user == f"{os.getuid()}:{os.getgid()}"


@pytest.mark.parametrize("network", ["bridge", "host", "omics-egress"])
def test_any_other_network_does_not_isolate(network: str):
    assert not SandboxConfig(image="x", network=network).isolates_network


@pytest.mark.parametrize(
    "overrides",
    [
        {"image": ""},
        {"image": "   "},
        {"image": "--privileged"},
        {"image": "a b"},
        {"network": "-host"},
        {"memory": "--oom-kill-disable"},
        {"cpus": "1 --privileged"},
        {"user": ""},
        {"runtime": " "},
        {"pids_limit": 0},
        {"start_timeout_s": 0},
        {"bootstrap_timeout_s": -1},
        {"stop_grace_s": -1},
        {"read_only_mounts": (Path("relative/data"),)},
        {"read_only_mounts": (Path("/data/a:b"),)},
    ],
)
def test_a_value_that_would_change_the_command_line_is_refused(overrides):
    """Operator configuration, so trusted — but an image or network that
    starts with ``-`` is read by the CLI as an option, and a ``:`` in a
    mount path is ``-v``'s own separator. Both fail here, by name, instead
    of turning into a different container."""
    values = {"image": "omics:1", **overrides}

    with pytest.raises(SandboxConfigError):
        SandboxConfig(**values)


def test_a_runtime_path_may_contain_spaces():
    """It is ``argv[0]``, never parsed by a shell."""
    config = SandboxConfig(image="x", runtime="/Applications/Docker App/docker")

    assert config.runtime.endswith("docker")


def test_mounts_are_normalised_to_paths_and_the_config_is_frozen():
    mounts = ("/ref/genome",)
    config = SandboxConfig(image="x", read_only_mounts=mounts)  # type: ignore[arg-type]

    assert config.read_only_mounts == (Path("/ref/genome"),)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.image = "y"  # type: ignore[misc]


def test_the_error_is_a_value_error():
    assert issubclass(SandboxConfigError, ValueError)
