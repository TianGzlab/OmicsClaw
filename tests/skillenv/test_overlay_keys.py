"""What an overlay's key is made of (plan 0061 case 14; the metadata half is in ``test_install_offline``).

The key is a cache identity, not a check: it answers "can this overlay be
reused", and it changes whenever anything about the base changes — the
interpreter's real path, version, prefix and modification time, and the
digest of the distributions in the base's own site-packages — or the
requested requirements change. It does not depend on the agent's
``CONDA_PREFIX`` (the old implementation's mistake). The digest covers the
base's own site-packages only, so it is the same whether the inventory runs
in the repository root or in ``/tmp``, with or without ``PYTHONPATH``: run
from the repository root, ``sys.path[0] == ''`` would otherwise add the
repository's ``omicsclaw.egg-info`` (F48).
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from omicsclaw.skillenv.overlay import base_distributions, overlay_key
from omicsclaw.skillenv.probe import BaseInventory, run_inventory

from .conftest import REPO
from .installing import PathProbeRunner, agent_environment

INVENTORY = BaseInventory(
    executable="/opt/conda/envs/OmicsClaw/bin/python",
    real_executable="/opt/conda/envs/OmicsClaw/bin/python3.11",
    version="3.11.15",
    prefix="/opt/conda/envs/OmicsClaw",
    base_prefix="/opt/conda/envs/OmicsClaw",
    mtime_ns=1,
    platform="linux",
    machine="x86_64",
    pip_version="26.0.1",
    missing=(),
    records=(("numpy", "2.0.2", "numpy-2.0.2.dist-info"),),
)
BASE = base_distributions(INVENTORY.records)


def test_the_key_is_sixteen_hex_digits_and_deterministic():
    key = overlay_key(INVENTORY, BASE, ("b", "a"))
    assert len(key) == 16 and int(key, 16) >= 0
    assert key == overlay_key(INVENTORY, BASE, ("a", "b"))


@pytest.mark.parametrize(
    "change",
    [
        {"real_executable": "/other/bin/python3.11"},
        {"version": "3.11.16"},
        {"prefix": "/opt/conda/envs/Other"},
        {"mtime_ns": 2},
        {"platform": "darwin"},
        {"machine": "aarch64"},
    ],
)
def test_the_key_follows_the_base(change):
    assert overlay_key(dataclasses.replace(INVENTORY, **change), BASE, ("a",)) != overlay_key(INVENTORY, BASE, ("a",))


def test_the_key_follows_the_base_distributions_and_the_request():
    other = base_distributions((*INVENTORY.records, ("six", "1.16.0", "six-1.16.0.dist-info")))
    assert overlay_key(INVENTORY, other, ("a",)) != overlay_key(INVENTORY, BASE, ("a",))
    assert overlay_key(INVENTORY, BASE, ("a>=2",)) != overlay_key(INVENTORY, BASE, ("a",))


def test_the_symlink_the_interpreter_was_reached_by_is_not_part_of_the_key():
    renamed = dataclasses.replace(INVENTORY, executable="/usr/local/bin/python")
    assert overlay_key(renamed, BASE, ("a",)) == overlay_key(INVENTORY, BASE, ("a",))


def test_the_real_inventory_does_not_depend_on_where_or_how_it_runs(tmp_path):
    environment = agent_environment(tmp_path, None)
    probe = PathProbeRunner(environment)

    def take(cwd, **env):
        return asyncio.run(run_inventory(probe, (), "", cwd=str(cwd), env={"PYTHONNOUSERSITE": "1", **env}))

    plain = take(tmp_path)
    variants = [
        take(REPO),
        take(tmp_path, CONDA_PREFIX="/somewhere/else"),
        take(REPO, PYTHONPATH=str(REPO)),
    ]
    digest = base_distributions(plain.records).digest
    key = overlay_key(plain, base_distributions(plain.records), ("a",))
    for inventory in variants:
        assert base_distributions(inventory.records).digest == digest
        assert overlay_key(inventory, base_distributions(inventory.records), ("a",)) == key
