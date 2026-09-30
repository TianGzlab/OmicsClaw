"""New code runs after installation without the agent's credentials (plan 0061 case 18b, §4.5 steps 7.8 and 7.10).

A new wheel's code first runs not at the verification import but in the
first interpreter started in the overlay after installation — the ``pip
check`` of step 7.8 — because a ``.pth`` file runs at interpreter start (F73).
So both that ``pip check`` and the verification import run with an
environment built from nothing: ``PATH``, ``LANG``, ``LC_*`` and
``LD_LIBRARY_PATH`` from the agent, a fresh temporary ``HOME``/``TMPDIR``,
``PYTHONNOUSERSITE=1`` and, for ``pip check``, ``PIP_CONFIG_FILE=/dev/null``.
The agent environment here carries a proxy with a token, a package index
with a password, the model's API key, the desktop bearer token and a
``PIP_PROXY``; none of them may be seen. This does not stop new code from
reading files by path or opening sockets (R6) — only from being handed the
credentials in its environment.

The last test is the import that never returns: the verification is time
limited and its whole process group is killed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from omicsclaw.skillenv.overlay import InstallLimits

from .installing import harness
from .wheels import make_wheel, pip_conf

SECRETS = {
    "HTTPS_PROXY": "http://u:tok@127.0.0.1:9",
    "PIP_INDEX_URL": "http://u:tok@127.0.0.1:9/simple",
    "PIP_PROXY": "http://u:tok@127.0.0.1:9",
    "LLM_API_KEY": "sk-secret",
    "OMICSCLAW_REMOTE_AUTH_TOKEN": "bearer-secret",
}
ALLOWED = {"PATH", "LANG", "LD_LIBRARY_PATH", "HOME", "TMPDIR", "PYTHONNOUSERSITE", "PIP_CONFIG_FILE"}


def _spy(record: Path, where: str) -> str:
    return (
        f"import os, json; open({str(record)!r}, 'a').write(json.dumps({{'where': {where!r}, "
        "'keys': sorted(os.environ), 'home': os.environ.get('HOME')}) + '\\n')"
    )


def test_code_run_after_installation_sees_none_of_the_agents_credentials(tmp_path):
    record = tmp_path / "seen.jsonl"
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-envspy", "1.0", files={"oc_envspy.py": _spy(record, "import") + "\n"})
    make_wheel(wheels, "oc-pthspy", "1.0", files={"oc_pthspy.py": "", "oc_pthspy.pth": _spy(record, "pth") + "\n"})
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]),
                LD_LIBRARY_PATH="/usr/local/lib", **SECRETS)
    output = h.call(["oc-envspy", "oc-pthspy"])
    assert output.startswith("Installed into the overlay"), output
    assert "oc_pthspy.pth" in output

    seen = [json.loads(line) for line in record.read_text().splitlines()]
    wheres = [entry["where"] for entry in seen]
    assert wheres.count("pth") >= 2, wheres  # the pip check after installation, and the verification
    assert "import" in wheres
    for entry in seen:
        keys = set(entry["keys"])
        extra = {k for k in keys - ALLOWED if not k.startswith("LC_")}
        assert not extra, (entry["where"], extra)
        assert not keys & set(SECRETS), entry
        assert entry["home"] and Path(entry["home"]).name == "home" and not Path(entry["home"]).exists()


def _running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat[stat.rfind(")") + 2:].split()[0] != "Z"


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads process state from /proc")
def test_an_import_that_never_returns_is_cut_off_with_its_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = (
        "import subprocess, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-hang", "1.0", files={"oc_hang.py": code})
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]), limits=InstallLimits(verify_s=3.0))
    began = time.monotonic()
    output = h.call(["oc-hang"])
    assert time.monotonic() - began < 60
    assert "verifying imports timed out after 3 s" in output, output
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _running(pid)
    assert h.key_dirs() == []
