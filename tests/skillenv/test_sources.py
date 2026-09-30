"""Pure checks on what reaches pip, and on what pip reports back (plan 0061 case 15b, §4.5 steps 7.3 and 7.6).

Since version 7.2 of the plan (owner ruling D8, Q34) ``install_skill_deps``
installs from this machine's own pip configuration, like a person typing
``pip install``; the tool no longer decides or checks where packages come
from. What it still owns:

* **the install-location guard** (F93): a pip configuration or environment
  that sets ``target``, ``prefix``, ``root``, ``user`` or ``src`` would put
  packages outside the overlay — ``prefix`` pointing at the base is a change
  to the base — so any such *key* is refused. Only key names are read, never
  values, so a URL that happens to contain ``target`` is not refused, and no
  URL is ever parsed (the version-6 review's B2 was a URL-parser mismatch).
  ``PIP_GLOBAL`` / ``PIP_SITE`` / ``PIP_USER`` narrow what ``pip config
  list`` itself shows (they are the ``config`` command's own ``--global`` /
  ``--site`` / ``--user``); found while implementing, so they are dropped from
  the environment the guard lists with.
* **the pip environment**: a small whitelist, every ``PIP_*`` of the agent's
  environment (the same as a person's terminal), and ``PYTHONNOUSERSITE``,
  ``PIP_NO_INPUT`` and ``PIP_DISABLE_PIP_VERSION_CHECK`` forced on; nothing
  else — the model's API key and the desktop bearer token stay behind.
* **the requirement grammar** (F85, F91): a requirement placed after ``--``
  is only ever a name, optional extras and optional version constraints. A
  direct URL there would make pip build that sdist while resolving; the specs
  come from ``pyproject.toml`` and the registry's ``also``, both files the
  model can edit, so the error names the file and entry.
* **the artifact check** on pip's report: direct URLs, non-archives and
  non-wheels are foreign; the artifact URL (never the index) gives the
  transport, because an https index may link a plain-http file (F88).
"""

from __future__ import annotations

import tomllib

import pytest

from omicsclaw.skillenv.sources import (
    RequirementError,
    artifact_source,
    artifact_transport,
    check_pin,
    check_requirement,
    clean_environment,
    config_list_environment,
    foreign_reason,
    location_settings,
    pip_environment,
    redact,
    wheel_name,
)

from .conftest import REPO

# ---- the install-location guard (F93) -------------------------------------------------------


@pytest.mark.parametrize(
    "line, named",
    [
        ("install.target='/tmp/elsewhere'", "install.target"),
        ("global.prefix='/opt/conda/envs/OmicsClaw'", "global.prefix"),
        ("install.root='/tmp/root'", "install.root"),
        ("install.user='true'", "install.user"),
        ("global.src='/tmp/src'", "global.src"),
        ("global.python='/opt/conda/envs/OmicsClaw/bin/python'", "global.python"),
        ("config.user='true'", "config.user"),
        ("user.prefix='/x'", "user.prefix"),
    ],
)
def test_a_location_key_in_pip_config_list_is_refused(line, named):
    listed = f"global.index-url='https://pypi.org/simple'\n{line}\nglobal.trusted-host='10.20.16.126'\n"
    found = location_settings(listed, {})
    assert len(found) == 1 and named in found[0]


def test_ordinary_pip_settings_pass():
    listed = (
        "global.index-url='http://u:secret@10.20.16.126:8081/repository/pypi-proxy/simple'\n"
        "global.trusted-host='10.20.16.126'\n"
        "global.proxy='http://127.0.0.1:7891'\n"
        "global.no-binary=':all:'\n"
        "global.extra-index-url='\\nhttps://a.example/simple\\nhttp://b.example:8081/simple'\n"
        ":env:.config-file='/tmp/pip.conf'\n"
    )
    assert location_settings(listed, {"PIP_INDEX_URL": "https://x/simple", "PIP_NO_BINARY": ":all:"}) == ()


def test_only_the_key_is_read_never_the_value():
    listed = (
        "global.index-url='https://mirror.example/target/prefix/root/simple'\n"
        "global.find-links='/srv/user/src/wheels'\n"
    )
    assert location_settings(listed, {"PIP_FIND_LINKS": "/data/target"}) == ()


@pytest.mark.parametrize(
    "variable", ["PIP_TARGET", "PIP_PREFIX", "PIP_ROOT", "PIP_USER", "PIP_SRC", "PIP_PYTHON", "PIP_Target", "PIP_python"]
)
def test_a_location_variable_in_the_pip_environment_is_refused(variable):
    """pip reads every ``PIP_``-prefixed variable, lower-casing the rest of the name."""
    found = location_settings("", {variable: "/tmp/x", "PIP_INDEX_URL": "https://pypi.org/simple"})
    assert found and variable in found[0]


@pytest.mark.parametrize("variable", ["PIP___PREFIX", "PIP___TARGET", "PIP___python"])
def test_a_variable_pip_normalises_to_a_location_key_is_refused(variable):
    """pip lower-cases, turns ``_`` into ``-`` and drops a leading ``--``: ``PIP___PREFIX`` is ``prefix``."""
    assert location_settings("", {variable: "/tmp/x"}) == (f"{variable} in the environment",)


def test_a_single_extra_underscore_is_not_an_option_pip_reads():
    """``PIP__TARGET`` normalises to ``-target``, which pip lists but matches to no option (checked on pip 25.3)."""
    assert location_settings("", {"PIP__TARGET": "/tmp/x"}) == ()


def test_an_env_line_of_the_listing_is_judged_unless_it_echoes_a_forced_value():
    """``:env:.prefix`` can come from a file section named ``[:env:]``; only the four forced keys are echoes."""
    found = location_settings(":env:.prefix='/opt/conda/envs/OmicsClaw'\n:env:.user='0'\n", {})
    assert len(found) == 1 and found[0].startswith(":env:.prefix")


def test_leading_underscore_spellings_of_the_forced_variables_are_replaced():
    assert config_list_environment({"PIP___QUIET": "3", "PIP___GLOBAL": "1"}) == {
        "PIP_QUIET": "0", "PIP_GLOBAL": "0", "PIP_SITE": "0", "PIP_USER": "0",
    }


def test_pip_python_version_is_not_the_python_option():
    assert location_settings("global.python-version='3.11'\n", {"PIP_PYTHON_VERSION": "3.11"}) == ()


def test_environment_lines_of_the_listing_are_judged_from_the_environment_itself():
    """The listing echoes the forced ``PIP_USER=0`` as ``:env:.user='0'``; that is not the agent's setting."""
    listed = ":env:.user='0'\n:env:.quiet='0'\n:env:.global='0'\n:env:.site='0'\n:env:.config-file='/p.conf'\n"
    assert location_settings(listed, {"PIP_CONFIG_FILE": "/p.conf"}) == ()
    assert location_settings(listed, {"PIP_USER": "1"}) == ("PIP_USER in the environment",)


def test_the_listing_is_read_with_verbosity_and_file_selectors_forced_off():
    environment = {"PIP_GLOBAL": "1", "PIP_Site": "1", "PIP_USER": "1", "PIP_QUIET": "3", "pip_quiet": "2",
                   "PIP_INDEX_URL": "x", "PATH": "/bin"}
    assert config_list_environment(environment) == {
        "PIP_INDEX_URL": "x", "PATH": "/bin", "pip_quiet": "2",
        "PIP_QUIET": "0", "PIP_GLOBAL": "0", "PIP_SITE": "0", "PIP_USER": "0",
    }


# ---- the pip environment --------------------------------------------------------------------

AGENT = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/root",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TMPDIR": "/tmp",
    "XDG_CACHE_HOME": "/root/.cache",
    "XDG_CONFIG_HOME": "/root/.config",
    "SSL_CERT_FILE": "/etc/ssl/cert.pem",
    "REQUESTS_CA_BUNDLE": "/etc/ssl/ca.pem",
    "HTTPS_PROXY": "http://u:tok@127.0.0.1:7891",
    "http_proxy": "http://u:tok@127.0.0.1:7891",
    "NO_PROXY": "10.0.0.0/8",
    "all_proxy": "socks5h://u:tok@127.0.0.1:7891",
    "PIP_INDEX_URL": "http://10.20.16.126:8081/simple",
    "PIP_TRUSTED_HOST": "10.20.16.126",
    "PIP_NO_INPUT": "0",
    "LLM_API_KEY": "sk-secret",
    "OMICSCLAW_REMOTE_AUTH_TOKEN": "bearer",
    "OMICSCLAW_SKILL_ENV": "install",
    "PYTHONPATH": "/somewhere",
    "LD_LIBRARY_PATH": "/usr/local/nvidia/lib",
    "CONDA_PREFIX": "/opt/conda/envs/OmicsClaw",
}


def test_the_pip_environment_is_the_whitelist_plus_every_pip_variable():
    env = pip_environment(AGENT)
    for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
                 "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "http_proxy", "NO_PROXY", "all_proxy",
                 "PIP_INDEX_URL", "PIP_TRUSTED_HOST"):
        assert env[name] == AGENT[name], name
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PIP_NO_INPUT"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"
    for name in ("LLM_API_KEY", "OMICSCLAW_REMOTE_AUTH_TOKEN", "OMICSCLAW_SKILL_ENV", "PYTHONPATH",
                 "LD_LIBRARY_PATH", "CONDA_PREFIX"):
        assert name not in env, name
    assert "PIP_CONFIG_FILE" not in env


def test_a_pip_config_file_the_agent_chose_is_kept():
    assert pip_environment({**AGENT, "PIP_CONFIG_FILE": "/dev/null"})["PIP_CONFIG_FILE"] == "/dev/null"


def test_the_clean_environment_carries_no_credentials(tmp_path):
    env = clean_environment(AGENT, str(tmp_path))
    assert env == {
        "PATH": AGENT["PATH"],
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LD_LIBRARY_PATH": AGENT["LD_LIBRARY_PATH"],
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONNOUSERSITE": "1",
    }


# ---- the requirement grammar (F85, F91) -----------------------------------------------------


@pytest.mark.parametrize(
    "spec, placed",
    [
        ("SpaGCN>=1.2.5,<2.0", "SpaGCN>=1.2.5,<2.0"),
        ("scanpy >= 1.9", "scanpy>=1.9"),
        ("scvi-tools[cuda12]>=1.0", "scvi-tools[cuda12]>=1.0"),
        ("pkg[a,b] ~= 2.1 , != 2.1.3", "pkg[a,b]~=2.1,!=2.1.3"),
        ("x===1.0+local", "x===1.0+local"),
        ("mygene", "mygene"),
        ("omicsclaw[spatial,singlecell]", "omicsclaw[spatial,singlecell]"),
    ],
)
def test_plain_requirements_are_accepted_and_lose_their_spaces(spec, placed):
    assert check_requirement(spec, source="pyproject.toml") == placed


@pytest.mark.parametrize(
    "spec",
    [
        "oc-far @ http://127.0.0.1:18810/oc_far-1.0.tar.gz",
        "x@http://evil.example/x.whl",
        "numpy; python_version<'3.12'",
        "x --no-binary :all:",
        "x --no-binary",
        "-e .",
        "--no-binary=:all:",
        "x==1.0 --hash=sha256:abcd",
        "file:///tmp/x.whl",
        "x\\y",
        "x/y",
        "x==1.0\n--index-url http://evil",
        "x\t==1.0",
        "",
        " leading",
    ],
)
def test_anything_else_is_refused_naming_its_source(spec):
    with pytest.raises(RequirementError) as caught:
        check_requirement(spec, source="skills/_sdk/deps.py: entry 'oc-leaf' field also")
    assert "skills/_sdk/deps.py: entry 'oc-leaf' field also" in str(caught.value)


def test_every_requirement_in_the_repository_pyproject_passes():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    assert len(specs) >= 10
    for spec in specs:
        check_requirement(spec, source="pyproject.toml")


@pytest.mark.parametrize("name, version", [("oc-leaf", "1.0"), ("scikit_learn", "1.7.2"), ("x", "1!2.0.post1+cu12")])
def test_a_pin_from_the_report_is_name_equals_version(name, version):
    assert check_pin(name, version) == f"{name}=={version}"


@pytest.mark.parametrize("name, version", [("-x", "1.0"), ("x y", "1.0"), ("x", "-1.0"), ("x", "1.0 --no-deps"),
                                           ("x", ""), ("x@y", "1"), ("x", "1;2")])
def test_a_malformed_pin_from_the_report_is_refused(name, version):
    with pytest.raises(RequirementError):
        check_pin(name, version)


# ---- what pip reports back (F66, F67, F88) --------------------------------------------------


def _item(url, *, direct=False, archive=True):
    info = {"url": url}
    if archive:
        info["archive_info"] = {"hashes": {"sha256": "0" * 64}}
    return {"download_info": info, "is_direct": direct, "metadata": {"name": "x", "version": "1"}}


def test_an_index_wheel_is_not_foreign():
    assert foreign_reason(_item("https://files.pythonhosted.org/packages/ab/x-1-py3-none-any.whl")) == ""


def test_a_wheel_on_another_host_than_the_index_is_not_foreign():
    """The index is not compared with the artifact host (Q32 void since version 7.2)."""
    assert foreign_reason(_item("http://cdn.example:8080/x-1-py3-none-any.whl")) == ""


@pytest.mark.parametrize(
    "item, why",
    [
        (_item("http://127.0.0.1:18766/oc_far-1.0-py3-none-any.whl", direct=True), "direct URL"),
        (_item("file:///tmp/src", archive=False), "not an archive"),
        (_item("https://example/x-1.tar.gz"), "not a wheel"),
    ],
)
def test_direct_urls_non_archives_and_sdists_are_foreign(item, why):
    assert why in foreign_reason(item)


@pytest.mark.parametrize(
    "url, source, transport",
    [
        ("https://files.pythonhosted.org/packages/x/six-1.16.0-py2.py3-none-any.whl",
         "https://files.pythonhosted.org", "https"),
        ("http://u:tok@10.20.16.126:8081/repository/pypi-proxy/packages/six/1.16.0/six-1.16.0-py2.py3-none-any.whl",
         "http://10.20.16.126:8081", "http"),
        ("file:///tmp/wheel%20house/oc_leaf-1.0-py3-none-any.whl", "file:/tmp/wheel house", "file"),
    ],
)
def test_source_and_transport_come_from_the_artifact_url(url, source, transport):
    assert artifact_source(url) == source
    assert artifact_transport(url) == transport
    assert "tok" not in artifact_source(url)


def test_the_wheel_name_is_the_last_path_segment():
    assert wheel_name("file:///tmp/wheel%20house/oc_leaf-1.0-py3-none-any.whl") == "oc_leaf-1.0-py3-none-any.whl"


def test_userinfo_is_redacted_wherever_it_appears():
    text = "Looking in indexes: https://user:token@idx.example/simple, http://u@b.example:8081/s and 'ftp://a:b@c/d'"
    cleaned = redact(text)
    assert "token" not in cleaned and "user" not in cleaned and "u@" not in cleaned and "a:b" not in cleaned
    assert "https://***@idx.example/simple" in cleaned
    assert redact("no url here @ all") == "no url here @ all"
