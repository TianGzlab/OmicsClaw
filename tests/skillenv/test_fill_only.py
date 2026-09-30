"""Install only what the base environment lacks (plan 0061 case 15, §4.6 "fill-only").

The inputs are pip ``--dry-run --report`` files recorded during the plan's
experiments (``fixtures/reports``: mygene F34/F38, pertpy F34, the direct-URL
dependency of F67) and a base inventory. An overlay's pip already counts what
the base has as satisfied, but where it wants a *different* version of a base
package (pertpy wants llvmlite 0.43.0, jax 0.10.2 …) that package is kept
from the base and reported, never shadowed. Whether the kept versions still
satisfy the new packages is left to the ``pip check`` difference (case 16).

Base metadata is messy (F48): the same name twice (llvmlite 0.47.0 dist-info
and 0.43.0 egg-info), records without a ``Name`` (mpmath's dist-info). Either
way the base "has" it. Since version 6 no artifact hash is carried; since
version 7.2 the artifact host is not compared with any declared source — a
PyPI wheel comes from files.pythonhosted.org, not pypi.org — but a direct URL
or a non-archive is still foreign, and the report is what names which
package's metadata brought it in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from omicsclaw.skillenv.overlay import base_distributions, fill_only
from omicsclaw.skillenv.sources import RequirementError

REPORTS = Path(__file__).resolve().parent / "fixtures" / "reports"


def _report(name: str) -> dict:
    return json.loads((REPORTS / name).read_text())


def _base(*records):
    return base_distributions(records)


def test_mygene_installs_both_missing_wheels():
    plan = fill_only(_report("mygene.json"), _base(("numpy", "2.0.2", "numpy-2.0.2.dist-info")))
    assert [(a.name, a.version) for a in plan.install] == [("mygene", "3.2.2"), ("biothings_client", "0.5.1")]
    first = plan.install[0]
    assert first.wheel.startswith("mygene-3.2.2-") and first.wheel.endswith(".whl")
    assert first.source == "http://10.20.16.126:8081" and first.transport == "http"
    assert first.requested and not plan.install[1].requested
    assert [a.pin for a in plan.install] == ["mygene==3.2.2", "biothings_client==0.5.1"]
    assert plan.kept_from_base == () and plan.foreign == ()


def test_pertpy_keeps_what_the_base_already_has():
    base = _base(
        ("llvmlite", "0.47.0", "llvmlite-0.47.0.dist-info"),
        ("llvmlite", "0.43.0", "llvmlite-0.43.0-py3.11.egg-info"),
        ("jax", "0.4.30", "jax-0.4.30.dist-info"),
        ("jaxlib", "0.4.30", "jaxlib-0.4.30.dist-info"),
        (None, None, "mpmath-1.4.1.dist-info"),
        ("scikit-misc", "0.0.0", "scikit_misc-0.0.0.dist-info"),
        ("scikit_misc", "0.5.2", "scikit_misc-0.5.2.dist-info"),
    )
    plan = fill_only(_report("pertpy.json"), base)
    kept = {k.name: k for k in plan.kept_from_base}
    assert set(kept) == {"llvmlite", "jax", "jaxlib", "mpmath", "scikit-misc"}
    assert kept["llvmlite"].base_versions == ("0.43.0", "0.47.0") and kept["llvmlite"].ambiguous
    assert kept["llvmlite"].wanted == "0.43.0"
    assert kept["mpmath"].base_versions == ("1.4.1",) and not kept["mpmath"].ambiguous
    assert kept["jax"].wanted == "0.10.2" and kept["jax"].base_versions == ("0.4.30",)
    assert len(plan.install) == 22 - 5
    assert not {a.name for a in plan.install} & set(kept)


def test_a_record_without_a_name_is_read_from_its_directory():
    base = _base((None, None, "mpmath-1.4.1.dist-info"), (None, None, "distributed-2024.8.0.dist-info"))
    assert base.has("mpmath") and base.versions["mpmath"] == ("1.4.1",)
    assert base.has("Distributed")
    assert base.unknown == 0


def test_an_unreadable_record_is_counted_not_guessed():
    base = _base((None, None, "not-a-metadata-dir"), ("ok", "1", "ok-1.dist-info"))
    assert base.unknown == 1 and base.has("ok")


def test_names_are_compared_in_their_normalised_form():
    report = {"install": [_entry("STAGATE-pyG", "1.0"), _entry("Other_Pkg", "2.0")]}
    plan = fill_only(report, _base(("stagate_pyg", "0.9", "stagate_pyg-0.9.dist-info")))
    assert [k.name for k in plan.kept_from_base] == ["STAGATE-pyG"]
    assert [a.name for a in plan.install] == ["Other_Pkg"]


def _entry(name, version, *, url=None, direct=False, archive=True, requested=True, requires=()):
    url = url or f"https://files.pythonhosted.org/packages/xx/{name.replace('-', '_')}-{version}-py3-none-any.whl"
    info = {"url": url}
    if archive:
        info["archive_info"] = {"hashes": {"sha256": "ab" * 32}}
    metadata = {"name": name, "version": version}
    if requires:
        metadata["requires_dist"] = list(requires)
    return {"download_info": info, "is_direct": direct, "requested": requested, "metadata": metadata}


def test_a_wheel_from_a_host_other_than_the_index_is_installed_normally():
    plan = fill_only({"install": [_entry("six", "1.16.0")]}, _base())
    assert [a.source for a in plan.install] == ["https://files.pythonhosted.org"]
    assert plan.foreign == ()


def test_a_dependency_named_by_direct_url_is_foreign_and_says_who_named_it():
    plan = fill_only(_report("direct_url.json"), _base())
    assert [f.name for f in plan.foreign] == ["oc-far"]
    (foreign,) = plan.foreign
    assert "direct URL" in foreign.reason
    assert foreign.required_by == ("oc-evil",)


def test_a_checkout_or_directory_is_foreign():
    plan = fill_only({"install": [_entry("x", "1.0", url="file:///tmp/x", archive=False)]}, _base())
    assert plan.foreign and "not an archive" in plan.foreign[0].reason


def test_the_transport_is_the_artifact_url_scheme_not_the_index():
    """An https index may link a plain-http file; pip checks only the page (F88)."""
    plan = fill_only({"install": [_entry("x", "1.0", url="http://files.example/x-1.0-py3-none-any.whl")]}, _base())
    assert plan.install[0].transport == "http"


@pytest.mark.parametrize("name, version", [("-x", "1.0"), ("x y", "1.0"), ("x", "1.0 --no-deps")])
def test_a_malformed_name_or_version_in_the_report_fails(name, version):
    with pytest.raises(RequirementError):
        fill_only({"install": [_entry(name, version, url="https://h/x-1.0-py3-none-any.whl")]}, _base())


def test_pins_carry_no_hash():
    plan = fill_only(_report("pertpy.json"), _base())
    for artifact in plan.install:
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9.!+_-]+", artifact.pin), artifact.pin
        assert "hash" not in json.dumps(artifact.as_record())


def test_the_digest_is_stable_and_order_independent():
    a = _base(("a", "1", "a-1.dist-info"), ("b", "2", "b-2.dist-info"))
    b = _base(("b", "2", "b-2.dist-info"), ("A", "1", "a-1.dist-info"))
    assert a.digest == b.digest and len(a.digest) == 64
    assert a.digest != _base(("a", "1", "a-1.dist-info"), ("b", "3", "b-3.dist-info")).digest
