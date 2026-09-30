"""Where installed files landed and which top-level names they add (plan 0061 §4.5 step 7.9, F63, F93, R19).

``RECORD`` is the backstop for the install-location guard: whatever pip's
configuration did — including settings pip adds after this was written — a
recorded path outside the overlay, or an installed distribution missing
from the overlay's site-packages, fails the installation. Top-level names
come from ``RECORD`` too, because a distribution's name says nothing about
the modules it puts at the top of site-packages (palettable ships ``build/``,
``docs/``, ``scripts/`` and ``test/``, F63): a module or regular package the
base can already import fails; a namespace directory is only reported,
since namespace portions merge rather than hide. Only the distributions this
installation added are read — a pip that ``ensurepip`` bootstrapped into the
overlay is not a new package hiding the base's pip.
"""

from __future__ import annotations

from pathlib import Path

from omicsclaw.skillenv.overlay import check_records

from .installing import harness
from .wheels import make_wheel, pip_conf


def _dist(site: Path, name: str, paths: list[str]) -> None:
    info = site / f"{name.replace('-', '_')}-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n\n")
    (info / "RECORD").write_text("".join(f"{p},,\n" for p in paths))


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    venv = tmp_path / ".venv"
    site = venv / "lib" / "python3.11" / "site-packages"
    site.mkdir(parents=True)
    return venv, site


def test_paths_outside_the_overlay_are_found(tmp_path):
    venv, site = _layout(tmp_path)
    _dist(site, "oc-a", ["oc_a.py", "../../../bin/oc-a", "../../../../../escaped.py"])
    result = check_records(site, venv, {}, ["oc-a"])
    assert result.outside == ("../../../../../escaped.py",)
    assert result.landed == frozenset({"oc-a"})


def test_top_level_names_are_classified_against_the_base(tmp_path):
    venv, site = _layout(tmp_path)
    _dist(site, "oc-a", ["six.py", "requests/__init__.py", "requests/x.py", "docs/readme.txt", "fresh/__init__.py",
                         "oc_hook.pth", "__pycache__/six.cpython-311.pyc", "oc_a-1.0.dist-info/RECORD",
                         "oc_a-1.0.data/scripts/x", "_native.cpython-311-x86_64-linux-gnu.so"])
    base = {"six": "module", "requests": "package", "docs": "namespace", "_native": "module"}
    result = check_records(site, venv, base, ["oc-a"])
    assert result.shadows == ("_native", "requests", "six")
    assert result.namespaces == ("docs",)
    assert result.pth_files == ("oc_hook.pth",)


def test_only_the_distributions_installed_now_are_read(tmp_path):
    venv, site = _layout(tmp_path)
    _dist(site, "pip", ["pip/__init__.py", "../../../../../elsewhere"])
    _dist(site, "oc-a", ["oc_a.py"])
    result = check_records(site, venv, {"pip": "package"}, ["oc-a"])
    assert result.shadows == () and result.outside == () and result.landed == frozenset({"oc-a"})


def test_an_installation_whose_metadata_is_not_in_the_overlay_fails(tmp_path):
    """Whatever moved it — a pip setting the guard does not know, a ``sitecustomize`` — the backstop sees it."""
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-leaf", "1.0")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))

    def moved_elsewhere():
        (info,) = list(h.root.glob("*/.venv/lib/python*/site-packages/oc_leaf-1.0.dist-info"))
        info.rename(tmp_path / info.name)

    h.runner.after["install"] = moved_elsewhere
    output = h.call(["oc-leaf"])
    assert "installed packages are not in the overlay's site-packages: oc-leaf" in output, output
    assert h.key_dirs() == []
    assert "Nothing was changed" not in output
    assert "may have been written outside the overlay" in output


def test_a_record_naming_files_outside_the_overlay_fails_and_says_so(tmp_path):
    """The builder acts on ``outside`` too, not only on distributions missing from the overlay."""
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-leaf", "1.0")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))

    def recorded_elsewhere():
        (record,) = list(h.root.glob("*/.venv/lib/python*/site-packages/oc_leaf-1.0.dist-info/RECORD"))
        with open(record, "a") as sink:
            sink.write("../../../../../../../etc/oc_written_elsewhere.cfg,,\n")

    h.runner.after["install"] = recorded_elsewhere
    output = h.call(["oc-leaf"])
    assert "installed files landed outside the overlay: ../../../../../../../etc/oc_written_elsewhere.cfg" in output
    assert "Nothing was changed" not in output
    assert "may have been written outside the overlay" in output
    assert h.key_dirs() == []


def test_an_escape_is_reported_even_when_it_also_breaks_requirements(tmp_path):
    """Found by the second review: with the files elsewhere but visible (``prefix`` pointing at the base),
    ``pip check`` failed first and the result said nothing had changed. The file-only checks now come
    before it."""
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-needs-old", "1.0", requires=["packaging<1"])
    make_wheel(wheels, "packaging", "0.9")
    elsewhere = tmp_path / "elsewhere"
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]), declared=("oc-needs-old",))

    def landed_elsewhere_but_visible():
        (site,) = list(h.root.glob("*/.venv/lib/python*/site-packages"))
        elsewhere.mkdir()
        for name in ("oc_needs_old-1.0.dist-info", "oc_needs_old.py"):
            (site / name).rename(elsewhere / name)
        (site / "oc_elsewhere.pth").write_text(f"{elsewhere}\n")

    h.runner.after["install"] = landed_elsewhere_but_visible
    output = h.call(["oc-needs-old"])
    assert "installed packages are not in the overlay's site-packages: oc-needs-old" in output, output
    assert "may have been written outside the overlay" in output and "Nothing was changed" not in output
    assert h.runner.stages()[-1] == "install", "the pip check after installation ran before the file checks"
