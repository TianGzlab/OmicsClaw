"""``install_skill_deps`` end to end, offline, with real pip and wheels built in the test (plan 0061 cases 18 and 14).

The base is this test process's interpreter (or ``OMICSCLAW_TEST_BASE_PYTHON``);
packages come from a pip configuration file written by the test —
``[global] no-index = true`` plus ``find-links`` — named by ``PIP_CONFIG_FILE``
in the agent environment, with ``HOME`` in a temporary directory. That is the
version-7.2 design (owner ruling D8, Q34): the tool installs from this
machine's pip configuration and does not check it.

What each test pins, and why:

* the success path: approve → resolve → fill-only → pinned install compared
  with the plan → ``pip check`` difference → ``RECORD`` and top-level names →
  imports verified in a credential-free environment → ``.meta.json`` and the
  fingerprint; the base is unchanged; the second call reuses the overlay
  without asking and without a find-links directory at all (so it cannot have
  reached a package source); no requirements file, nothing after ``--`` but
  requirements, and ``uv`` is never run;
* a new violation (``oc-needs-old`` wants ``packaging<1``; the base's newer
  packaging is kept) rolls back; so do a sdist-only package (``no-wheel``), a
  top-level module hiding one the base has, a wheel swapped between the dry
  run and the installation (F68: ``name==version`` does not pin the file), and
  a dependency named by direct URL (F67; Q33 = a: refused, and the result
  says which package's metadata named it — F84 notes that pip may already
  have *built* such a dependency during the dry run if it were an sdist);
* ``no-binary`` in the pip configuration or ``PIP_NO_BINARY`` cannot make pip
  build a source distribution, because ``--only-binary=:all:`` is on the
  command line (F92);
* ``target``/``prefix``/``root`` in the pip configuration, or ``PIP_TARGET``,
  are refused before the dry run and nothing is written anywhere (F93);
* (i) ``pip/__main__.py`` and ``venv/__main__.py`` in the test's working
  directory and beside the overlay root are never executed: every command
  starts ``<python> -I`` in an empty temporary directory, since removed (F86);
* (ii) a direct URL in the registry's ``also`` fails before any process
  starts and the server it names receives nothing (F85);
* (iv) a find-links server answering 401 makes pip fail rather than wait for
  a password (``PIP_NO_INPUT=1``).
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import threading
from pathlib import Path

import pytest

from omicsclaw.skillenv.overlay import FINGERPRINT, META, PACKAGE_SOURCES

from .installing import BASE_PYTHON, SKILL, harness
from .wheels import make_sdist, make_wheel, pip_conf

_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


def _wheels(directory: Path) -> Path:
    make_wheel(directory, "oc-leaf", "1.0", requires=["oc-dep>=1"])
    make_wheel(directory, "oc-dep", "1.0")
    return directory


def _base_imports(module: str) -> bool:
    probe = subprocess.run([BASE_PYTHON, "-I", "-c", f"import {module}"], capture_output=True, timeout=60)
    return probe.returncode == 0


def _after_dash_dash(argv):
    return argv[argv.index("--") + 1:] if "--" in argv else []


def test_a_leaf_and_its_dependency_install_verify_and_are_reused(tmp_path):
    wheels = _wheels(tmp_path / "wh")
    conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels])
    h = harness(tmp_path, conf)
    output = h.call(["oc-leaf"])

    assert output.startswith("Installed into the overlay "), output
    (key_dir,) = h.key_dirs()
    python = key_dir / ".venv" / "bin" / "python"
    assert f"- oc-leaf==1.0  oc_leaf-1.0-py3-none-any.whl  from file:{wheels}\n" in output
    assert f"- oc-dep==1.0  oc_dep-1.0-py3-none-any.whl  from file:{wheels}\n" in output
    assert f"PYTHONNOUSERSITE=1 {python} " in output and "oc_skill.py" in output
    assert "oc_leaf ok" in output

    # asked exactly once, before any process of the installation
    assert len(h.asked) == 1 and h.calls_at_ask == [0]
    assert h.runner.stages() == ["venv", "config", "check", "dry-run", "install", "check", "verify"]

    # the overlay imports the package, the base does not, and the base's own site-packages is untouched
    assert subprocess.run([str(python), "-I", "-c", "import oc_leaf, oc_dep"], timeout=60).returncode == 0
    assert not _base_imports("oc_leaf")

    # every process: -I, an emptied temporary cwd, no requirements file, only requirements after --
    for call in h.runner.calls:
        assert call.argv[1] == "-I", call.argv
        assert not Path(call.cwd).exists()
        assert "-r" not in call.argv and "--requirement" not in call.argv
        assert not any("://" in item for item in call.argv), call.argv
        for item in _after_dash_dash(call.argv):
            assert not item.startswith("-") and "@" not in item
    # both pip checks compare like with like: no pip configuration, no credentials (after the evaluation of P2)
    before_check, after_check = [c for c in h.runner.calls if c.stage == "check"]
    assert before_check.env == after_check.env
    assert after_check.env["PIP_CONFIG_FILE"] == os.devnull and "PIP_NO_INPUT" not in after_check.env
    install = next(c for c in h.runner.calls if c.stage == "install")
    assert sorted(_after_dash_dash(install.argv)) == ["oc-dep==1.0", "oc-leaf==1.0"]
    dry = next(c for c in h.runner.calls if c.stage == "dry-run")
    assert _after_dash_dash(dry.argv) == ["oc-leaf"]
    assert not (tmp_path / "UV_CALLED").exists()

    # case 14: the metadata
    meta = json.loads((key_dir / META).read_text())
    assert (key_dir / ".venv" / FINGERPRINT).read_text().strip() == key_dir.name == meta["key"]
    for field in ("skill", "packages", "requested_specs", "installed", "kept_from_base", "package_sources",
                  "base_executable", "base_version", "base_prefix", "base_mtime_ns", "base_dists_sha256",
                  "pip_version", "created"):
        assert field in meta, field
    assert meta["skill"] == SKILL and meta["packages"] == ["oc-leaf"] and meta["requested_specs"] == ["oc-leaf"]
    assert meta["package_sources"] == PACKAGE_SOURCES
    assert sorted((i["name"], i["wheel"], i["source"], i["transport"]) for i in meta["installed"]) == [
        ("oc-dep", "oc_dep-1.0-py3-none-any.whl", f"file:{wheels}", "file"),
        ("oc-leaf", "oc_leaf-1.0-py3-none-any.whl", f"file:{wheels}", "file"),
    ]
    text = json.dumps(meta)
    assert _DIGEST.findall(text) == [meta["base_dists_sha256"]]
    assert "@" not in text
    assert (h.root / ".locks" / f"{key_dir.name}.lock").is_file()

    # the second call reuses the overlay, asks nobody and needs no package source
    h.environment["PIP_CONFIG_FILE"] = str(pip_conf(tmp_path / "empty.conf"))
    calls_before = len(h.runner.calls)
    again = h.call(["oc-leaf"])
    assert "already exists" in again and str(python) in again
    assert len(h.asked) == 1 and len(h.runner.calls) == calls_before


def test_a_refusal_has_no_side_effects(tmp_path):
    from omicsclaw.tools.context import ApprovalDenied

    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))
    with pytest.raises(ApprovalDenied):
        h.call(["oc-leaf"], approve=False)
    assert len(h.asked) == 1 and h.runner.calls == [] and not h.root.exists()


def test_a_new_violation_rolls_back(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-needs-old", "1.0", requires=["packaging<1"])
    make_wheel(wheels, "packaging", "0.9")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    output = h.call(["oc-needs-old"])
    assert output.startswith("install_skill_deps failed: the installation breaks declared requirements"), output
    assert re.search(r"oc[-_]needs[-_]old 1\.0 has requirement packaging<1, but you have packaging ", output)
    assert "kept from the base: packaging" in output
    assert h.key_dirs() == []
    assert list((h.root / ".locks").glob("*.lock"))


def test_an_sdist_only_package_is_not_built(tmp_path):
    wheels = tmp_path / "wh"
    marker = tmp_path / "SDIST_RAN"
    make_sdist(wheels, "oc-sdist-only", "1.0", setup_code=f"open({str(marker)!r}, 'w').write('ran')")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    output = h.call(["oc-sdist-only"])
    assert "no-wheel" in output and "oc-sdist-only" in output
    assert not marker.exists() and h.key_dirs() == []


def test_a_module_hiding_one_the_base_has_rolls_back(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-shadow", "1.0", files={"oc_shadow.py": "", "pytest.py": "HIJACKED = True\n"})
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    output = h.call(["oc-shadow"])
    assert "would hide ones the base environment already has: pytest" in output
    assert h.key_dirs() == []


def test_a_namespace_directory_is_reported_and_kept(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-nsdir", "1.0", files={"oc_nsdir.py": "", "test/oc_nsdir_data.txt": "x\n"})
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    output = h.call(["oc-nsdir"])
    assert output.startswith("Installed into the overlay"), output
    assert "Namespace directories shared with the base (reported, not a problem): test" in output
    assert len(h.key_dirs()) == 1


def test_a_wheel_swapped_between_resolution_and_installation_rolls_back(tmp_path):
    wheels = _wheels(tmp_path / "wh")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    h.runner.after["dry-run"] = lambda: make_wheel(wheels, "oc-dep", "1.0", build=1, files={"oc_dep.py": "V = 666\n"})
    output = h.call(["oc-leaf"])
    assert "pip installed other files than it planned" in output, output
    assert "oc_dep-1.0-1-py3-none-any.whl" in output
    assert h.key_dirs() == []


def test_a_dependency_named_by_direct_url_is_refused(tmp_path):
    far = make_wheel(tmp_path / "far", "oc-far", "1.0")
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-near", "1.0", requires=[f"oc-far @ {far.resolve().as_uri()}"])
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    output = h.call(["oc-near"])
    assert "not ordinary wheels" in output and "oc-far 1.0" in output and "named by oc-near" in output
    assert "install" not in h.runner.stages()
    assert h.key_dirs() == []


@pytest.mark.parametrize("via", ["config", "environment"])
def test_no_binary_cannot_make_pip_build_a_source_distribution(tmp_path, via):
    wheels = tmp_path / "wh"
    marker = tmp_path / "SDIST_RAN"
    make_sdist(wheels, "oc-sdist-only", "1.0", setup_code=f"open({str(marker)!r}, 'w').write('ran')")
    extra = "no-binary = :all:\n" if via == "config" else ""
    conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=extra)
    env = {"PIP_NO_BINARY": ":all:"} if via == "environment" else {}
    h = harness(tmp_path, conf, **env)
    output = h.call(["oc-sdist-only"])
    assert "no-wheel" in output and not marker.exists()
    dry = next(c for c in h.runner.calls if c.stage == "dry-run")
    assert "--only-binary=:all:" in dry.argv


@pytest.mark.parametrize(
    "setting",
    ["[install]\ntarget = {out}\n", "[install]\nprefix = {out}\n", "[install]\nroot = {out}\n",
     "[install]\nuser = true\n", "env:PIP_TARGET", "env:PIP_PREFIX"],
)
def test_install_location_settings_are_refused_before_resolving(tmp_path, setting):
    wheels = _wheels(tmp_path / "wh")
    out = tmp_path / "elsewhere"
    env = {}
    if setting.startswith("env:"):
        env[setting[4:]] = str(out)
        conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels])
    else:
        conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=setting.format(out=out))
    h = harness(tmp_path, conf, **env)
    output = h.call(["oc-leaf"])
    assert "pip is configured to install somewhere other than the overlay" in output, output
    assert h.runner.stages() == ["venv", "config"]
    assert not out.exists() or not any(out.rglob("*"))
    assert h.key_dirs() == []
    assert not _base_imports("oc_leaf")


def test_python_m_hijacks_nearby_are_never_executed(tmp_path, monkeypatch):
    marker = tmp_path / "HIJACKED"
    for place in (tmp_path / "here", tmp_path / "beside"):
        for module in ("pip", "venv"):
            (place / module).mkdir(parents=True)
            (place / module / "__main__.py").write_text(f"open({str(marker)!r}, 'a').write('{module}\\n')\n")
    monkeypatch.chdir(tmp_path / "here")
    wheels = _wheels(tmp_path / "wh")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]), root=tmp_path / "beside" / "envs")
    output = h.call(["oc-leaf"])
    assert output.startswith("Installed into the overlay"), output
    assert not marker.exists()
    for call in h.runner.calls:
        assert call.argv[1] == "-I" and not Path(call.cwd).exists()


class _Counting(http.server.BaseHTTPRequestHandler):
    requests: list[str] = []
    status = 404

    def do_GET(self):  # noqa: N802 - the http.server hook name
        type(self).requests.append(self.path)
        self.send_response(type(self).status)
        if type(self).status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="oc"')
        self.end_headers()

    def log_message(self, *args):
        pass


def _serve(status):
    handler = type("Handler", (_Counting,), {"requests": [], "status": status})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, handler


def test_a_direct_url_in_the_registry_fails_before_any_process(tmp_path):
    server, handler = _serve(404)
    try:
        port = server.server_address[1]
        registry = {"oc-leaf": {"module": "oc_leaf", "kind": "pip", "install": "pip install oc-leaf",
                                "description": "d", "also": [f"oc-far @ http://127.0.0.1:{port}/oc_far-1.0.tar.gz"]}}
        h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]),
                    registry=registry)
        output = h.call(["oc-leaf"])
    finally:
        server.shutdown()
    assert "field also" in output and "not a plain requirement" in output
    assert h.probe.calls == 0 and h.runner.calls == [] and h.asked == []
    assert handler.requests == []


def test_a_find_links_server_answering_401_fails_without_waiting(tmp_path):
    server, handler = _serve(401)
    try:
        conf = pip_conf(tmp_path / "pip.conf", find_links=[f"http://127.0.0.1:{server.server_address[1]}/"])
        h = harness(tmp_path, conf, NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        output = h.call(["oc-auth"])
    finally:
        server.shutdown()
    assert output.startswith("install_skill_deps failed:"), output
    assert handler.requests, "pip never asked the find-links server"
    dry = next(c for c in h.runner.calls if c.stage == "dry-run")
    assert dry.env["PIP_NO_INPUT"] == "1"
    assert h.key_dirs() == []


def test_the_suggested_command_and_result_carry_no_credentials(tmp_path):
    wheels = _wheels(tmp_path / "wh")
    conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels])
    h = harness(tmp_path, conf, HTTPS_PROXY="http://u:tok@127.0.0.1:9", PIP_INDEX_URL="http://u:tok@127.0.0.1:9/s")
    output = h.call(["oc-leaf"])
    assert output.startswith("Installed into the overlay"), output
    assert "tok" not in output and "u:tok" not in h.asked[0].reason
    assert os.environ.get("PIP_INDEX_URL") != "http://u:tok@127.0.0.1:9/s"



# ---- after the independent evaluation of P2 --------------------------------------------------


@pytest.mark.parametrize(
    "extra, env",
    [
        ("quiet = 1\n", {}),
        ("", {"PIP_QUIET": "1"}),
        ("site = true\n", {}),
        ("global = true\n", {}),
        ("[config]\nsite = true\n", {}),
        ("[config]\nglobal = true\n", {}),
        ("", {"PIP_GLOBAL": "1"}),
    ],
    ids=["quiet-config", "quiet-env", "site-global", "global-global", "site-config", "global-config", "global-env"],
)
def test_settings_that_hide_pip_config_list_output_do_not_hide_a_location_key(tmp_path, extra, env):
    """``quiet`` silences ``pip config list``; ``site``/``global`` make it list one file only.

    Found by the independent evaluation of P2: with any of these, the guard read an
    empty or partial listing, and pip installed into the configured ``prefix``. pip
    install ignores ``site``/``global``, so the listing is read with those three and
    ``user`` forced off in the environment, which outranks every configuration file.
    """
    wheels = _wheels(tmp_path / "wh")
    out = tmp_path / "fake_base_prefix"
    conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=f"{extra}[install]\nprefix = {out}\n")
    h = harness(tmp_path, conf, **env)
    output = h.call(["oc-leaf"])
    assert "pip is configured to install somewhere other than the overlay" in output, output
    assert "install.prefix" in output
    assert h.runner.stages() == ["venv", "config"]
    assert not out.exists()
    assert h.key_dirs() == []


def _plant_an_existing_problem(h) -> None:
    """Before anything is installed, put a distribution with an unmet requirement where ``pip check`` sees it.

    This makes the existing problem a fixture rather than a property of the base:
    on a base with no broken requirements the test would otherwise pass for
    nothing.
    """
    (site,) = list(h.root.glob("*/.venv/lib/python*/site-packages"))
    info = site / "oc_planted-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: oc-planted\nVersion: 1.0\nRequires-Dist: oc-absent>=1\n\n")
    (info / "RECORD").write_text("oc_planted-1.0.dist-info/METADATA,,\noc_planted-1.0.dist-info/RECORD,,\n")


@pytest.mark.parametrize("extra, env", [("quiet = 1\n", {}), ("", {"PIP_QUIET": "1"})], ids=["config", "env"])
def test_a_quiet_pip_does_not_turn_base_problems_into_new_ones(tmp_path, extra, env):
    """A silenced ``pip check`` before installation made every existing base problem look new."""
    wheels = _wheels(tmp_path / "wh")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=extra), **env)
    h.runner.after["venv"] = lambda: _plant_an_existing_problem(h)
    output = h.call(["oc-leaf"])
    before = next(c for c in h.runner.calls if c.stage == "check")
    assert "oc-planted 1.0 requires oc-absent, which is not installed." in before.output.stdout, "premise"
    assert output.startswith("Installed into the overlay"), output


@pytest.mark.parametrize(
    "extra, env",
    [("[:env:]\nprefix = {out}\n", {}), ("", {"PIP___PREFIX": "{out}"}), ("", {"PIP_Prefix": "{out}"})],
    ids=["env-section-in-a-file", "leading-underscores", "mixed-case"],
)
def test_other_spellings_of_a_location_key_are_refused(tmp_path, extra, env):
    """Found by the second review: a file section literally named ``[:env:]`` is read like
    ``PIP_`` variables and listed as ``:env:.prefix``; ``PIP___PREFIX`` is normalised by pip
    to ``prefix`` (lower-cased, ``_`` to ``-``, a leading ``--`` removed)."""
    wheels = _wheels(tmp_path / "wh")
    out = tmp_path / "fake_base_prefix"
    conf = pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=extra.format(out=out))
    h = harness(tmp_path, conf, **{k: v.format(out=out) for k, v in env.items()})
    output = h.call(["oc-leaf"])
    assert "pip is configured to install somewhere other than the overlay" in output, output
    assert h.runner.stages() == ["venv", "config"]
    assert not out.exists()
    assert h.key_dirs() == []


@pytest.mark.parametrize("via", ["config", "environment"])
def test_pips_python_option_is_refused_before_resolving(tmp_path, via):
    """``python`` makes pip install into another interpreter (owner ruling 2026-09-26: a location key)."""
    stand_in = tmp_path / "stand_in_base"
    subprocess.run([BASE_PYTHON, "-I", "-m", "venv", "--without-pip", str(stand_in)], check=True, timeout=120)
    wheels = _wheels(tmp_path / "wh")
    target = f"{stand_in}/bin/python"
    extra = f"python = {target}\n" if via == "config" else ""
    env = {"PIP_PYTHON": target} if via == "environment" else {}
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels], extra=extra), **env)
    output = h.call(["oc-leaf"])
    assert "pip is configured to install somewhere other than the overlay" in output, output
    assert h.runner.stages() == ["venv", "config"]
    assert not list(stand_in.glob("lib/python*/site-packages/oc_*"))
    assert h.key_dirs() == []


def test_a_module_that_fails_to_import_rolls_back(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-broken", "1.0", files={"oc_broken.py": "raise RuntimeError('broken on import')\n"})
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]), declared=("oc-broken",))
    output = h.call(["oc-broken"])
    assert "the installed packages do not import: oc_broken: RuntimeError: broken on import" in output, output
    assert h.key_dirs() == []


def test_a_relative_overlay_root_works(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-leaf", "1.0")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]), root=Path("relenvs"))
    output = h.call(["oc-leaf"])
    assert output.startswith("Installed into the overlay"), output
    assert len(list((tmp_path / "relenvs").glob("*/.venv/.omicsclaw.fingerprint"))) == 1
    assert str(tmp_path / "relenvs") in output
