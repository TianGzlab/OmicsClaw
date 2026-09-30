"""A real installation over the network, run by hand (plan 0061 case 24).

Skipped unless ``OMICSCLAW_TEST_NETWORK=1``. Uses this machine's own pip
configuration unchanged — here ``/root/.pip/pip.conf`` points at an internal
proxy index over plain http with a ``trusted-host`` — and configures no
source in OmicsClaw (version 7.2, owner ruling D8): the installation must
succeed, and since the artifacts come over http the metadata records
``transport: http`` and the result marks them ``(plaintext)``. The second
call reuses the overlay without asking.

The base defaults to the ``OmicsClaw`` environment; set
``OMICSCLAW_TEST_BASE_PYTHON`` to use another.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omicsclaw.tools.builtin.bash import without_control_credentials

pytestmark = pytest.mark.skipif(os.environ.get("OMICSCLAW_TEST_NETWORK") != "1",
                                reason="set OMICSCLAW_TEST_NETWORK=1 to install over the network")

BASE = os.environ.get("OMICSCLAW_TEST_BASE_PYTHON") or "/opt/conda/envs/OmicsClaw/bin/python"


def test_mygene_installs_from_this_machines_pip_configuration(tmp_path, monkeypatch):
    from . import installing
    from .installing import harness

    monkeypatch.setattr(installing, "BASE_PYTHON", BASE)
    h = harness(tmp_path, None, declared=("mygene",), registry={})
    h.environment.clear()
    h.environment.update(without_control_credentials())
    h.environment["PATH"] = f"{tmp_path / 'fakebin'}:{h.environment.get('PATH', '/usr/bin:/bin')}"
    h.probe._path = h.environment["PATH"]

    output = h.call(["mygene"])
    print(output)
    assert output.startswith("Installed into the overlay"), output
    (key_dir,) = h.key_dirs()
    meta = json.loads((key_dir / ".meta.json").read_text())
    transports = {item["transport"] for item in meta["installed"]}
    if transports == {"http"}:
        assert "(plaintext)" in output
    assert {item["name"].lower().replace("_", "-") for item in meta["installed"]} >= {"mygene"}

    again = h.call(["mygene"])
    assert "already exists" in again and len(h.asked) == 1
    print(json.dumps(meta, indent=1))
    Path(os.environ.get("OMICSCLAW_TEST_NETWORK_REPORT", os.devnull)).write_text(output + "\n" + json.dumps(meta))
