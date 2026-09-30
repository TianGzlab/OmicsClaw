"""``GET /skills``, ``GET /skills/{domain}/{name}`` and ``GET /mcp/servers``
as plain functions, without a web framework.

The shapes are the ones the desktop client's parsers accept
(``parseSkillCatalogResponse``, ``mergeSkillDetailResponse``,
``toSourcedConfig`` and the MCP status reader): a missing required field
there is an error page, so every required field is asserted here.

The MCP masking tests are the security half (plan 0065 §3.3, Q12 = a):
``${VAR}`` is expanded in ``command``, ``args``, ``url``, ``env`` and
``headers``, so the running configuration can hold a token in any of
them. The page shows the unexpanded text of ``.mcp.json`` for the first
three and only the keys of the last two, and replaces variable values
inside a rejected entry's reason.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from types import SimpleNamespace

import pytest

from omicsclaw.entry.desktop.catalog import (
    MASK,
    MAX_RESOURCES,
    mcp_servers,
    skill_catalog,
    skill_detail,
)
from omicsclaw.entry.desktop.turn_submission import DesktopIngressError
from omicsclaw.mcp import (
    MCPConfig,
    RejectedServer,
    ServerState,
    ServerStatus,
)
from omicsclaw.mcp.config import load_mcp_config
from omicsclaw.skills import Skill, SkillIndex


def write_skill(root: pathlib.Path, relative: str, name: str, body: str = "Body.") -> Skill:
    path = root / relative / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {name} does things\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return Skill(
        name=name,
        description=f"{name} does things",
        path=path,
        root=root,
        tags=("t1",),
    )


def app_with(index: SkillIndex, mcp=None):
    return SimpleNamespace(skills=index, mcp=mcp)


# ---- the catalog ---------------------------------------------------------


def test_the_catalog_groups_by_domain_in_index_order(tmp_path):
    skills = (
        write_skill(tmp_path, "spatial/spatial-de", "spatial-de"),
        write_skill(tmp_path, "spatial/spatial-qc", "spatial-qc"),
        write_skill(tmp_path, "bulkrna/bulk-de", "bulk-de"),
    )
    payload = skill_catalog(app_with(SkillIndex(skills=skills, root=tmp_path)))

    assert payload["total"] == 3
    assert [d["domain"] for d in payload["domains"]] == ["spatial", "bulkrna"]
    spatial = payload["domains"][0]
    assert spatial["domain_name"] == "spatial"
    assert spatial["primary_data_types"] == []
    assert [s["name"] for s in spatial["skills"]] == ["spatial-de", "spatial-qc"]
    assert spatial["skills"][0] == {
        "name": "spatial-de",
        "description": "spatial-de does things",
        "domain": "spatial",
        "collection": "curated",
        "status": "ready",
    }


def test_the_total_is_the_number_of_skills_listed(tmp_path):
    """The client's parser refuses a catalog whose total disagrees."""
    skills = tuple(
        write_skill(tmp_path, f"d{i % 2}/s{i}", f"s{i}") for i in range(5)
    )
    payload = skill_catalog(app_with(SkillIndex(skills=skills, root=tmp_path)))
    listed = sum(len(d["skills"]) for d in payload["domains"])
    assert payload["total"] == listed == 5


def test_a_skill_at_the_root_is_filed_under_general(tmp_path):
    """The client requires a non-empty domain on every skill."""
    skills = (
        write_skill(tmp_path, "", "rooted"),
        write_skill(tmp_path, "general/other", "other"),
    )
    payload = skill_catalog(app_with(SkillIndex(skills=skills, root=tmp_path)))

    assert [d["domain"] for d in payload["domains"]] == ["general"]
    assert [s["domain"] for s in payload["domains"][0]["skills"]] == [
        "general",
        "general",
    ]


def test_an_empty_index_is_an_empty_catalog(tmp_path):
    assert skill_catalog(app_with(SkillIndex(root=tmp_path))) == {
        "domains": [],
        "total": 0,
    }


# ---- one skill -----------------------------------------------------------


def test_the_detail_carries_the_body_and_relative_resources(tmp_path):
    skill = write_skill(tmp_path, "spatial/spatial-de", "spatial-de", body="# Use\nRun it.")
    directory = skill.directory
    (directory / "scripts").mkdir()
    (directory / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    (directory / "references").mkdir()
    (directory / "references" / "notes.md").write_text("n\n", encoding="utf-8")
    (directory / "params.yaml").write_text("a: 1\n", encoding="utf-8")
    payload = skill_detail(
        app_with(SkillIndex(skills=(skill,), root=tmp_path)), "spatial", "spatial-de"
    )

    assert payload["name"] == "spatial-de"
    assert payload["domain"] == "spatial"
    assert payload["description"] == "spatial-de does things"
    assert payload["aliases"] == []
    assert payload["script_path"] is None
    assert payload["tags"] == ["t1"]
    assert payload["skill_md"] == "# Use\nRun it."
    assert payload["resources"] == [
        {"path": "SKILL.md", "kind": "doc"},
        {"path": "params.yaml", "kind": "config"},
        {"path": "references/notes.md", "kind": "reference"},
        {"path": "scripts/run.py", "kind": "script"},
    ]
    assert str(tmp_path) not in json.dumps(payload)


@pytest.mark.parametrize(
    ("domain", "name"),
    [("spatial", "nope"), ("bulkrna", "spatial-de"), ("general", "spatial-de")],
)
def test_an_unknown_name_or_a_wrong_domain_is_a_404(tmp_path, domain, name):
    skill = write_skill(tmp_path, "spatial/spatial-de", "spatial-de")
    app = app_with(SkillIndex(skills=(skill,), root=tmp_path))
    with pytest.raises(DesktopIngressError) as caught:
        skill_detail(app, domain, name)
    assert (caught.value.code, caught.value.status_code) == ("skill_not_found", 404)


def test_a_root_skill_is_found_under_general(tmp_path):
    skill = write_skill(tmp_path, "", "rooted")
    app = app_with(SkillIndex(skills=(skill,), root=tmp_path))
    assert skill_detail(app, "general", "rooted")["domain"] == "general"


def test_an_unreadable_body_is_null_and_not_a_failure(tmp_path):
    skill = write_skill(tmp_path, "spatial/broken", "broken")
    skill.path.write_bytes(b"---\nname: broken\n---\n\xff\xfe not utf-8")
    app = app_with(SkillIndex(skills=(skill,), root=tmp_path))
    payload = skill_detail(app, "spatial", "broken")
    assert payload["skill_md"] is None
    assert {"path": "SKILL.md", "kind": "doc"} in payload["resources"]


def test_resources_skip_hidden_files_caches_and_symlinks(tmp_path):
    """S19: a symlink could lead the listing out of the skill directory."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    skill = write_skill(tmp_path, "d/s", "s")
    directory = skill.directory
    (directory / ".hidden").write_text("x", encoding="utf-8")
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__" / "m.pyc").write_bytes(b"x")
    (directory / "linked-dir").symlink_to(outside, target_is_directory=True)
    (directory / "linked-file.txt").symlink_to(outside / "secret.txt")
    app = app_with(SkillIndex(skills=(skill,), root=tmp_path))

    paths = [r["path"] for r in skill_detail(app, "d", "s")["resources"]]
    assert paths == ["SKILL.md"]


def test_resources_stop_at_the_cap(tmp_path):
    skill = write_skill(tmp_path, "d/s", "s")
    data = skill.directory / "data"
    data.mkdir()
    for i in range(MAX_RESOURCES + 20):
        (data / f"f{i:04d}.txt").write_text("x", encoding="utf-8")
    app = app_with(SkillIndex(skills=(skill,), root=tmp_path))

    paths = [r["path"] for r in skill_detail(app, "d", "s")["resources"]]
    assert len(paths) == MAX_RESOURCES
    assert paths == sorted(paths)


# ---- MCP -----------------------------------------------------------------


def manager(config: MCPConfig, *statuses: ServerStatus):
    return SimpleNamespace(config=config, statuses=lambda: statuses)


def mcp_file(tmp_path: pathlib.Path, servers: dict) -> pathlib.Path:
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return path


TOKEN = "tok-0123456789abcdef"
ENV = {"TOKEN": TOKEN, "HOME": "/home/someone"}


def loaded(tmp_path: pathlib.Path, servers: dict) -> MCPConfig:
    return load_mcp_config(mcp_file(tmp_path, servers), ENV)


def test_no_mcp_manager_is_an_empty_list():
    assert mcp_servers(SimpleNamespace(mcp=None)) == {"servers": []}


def test_configured_servers_carry_the_client_fields_and_their_state(tmp_path):
    config = loaded(
        tmp_path,
        {
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
                "env": {"API_KEY": "${TOKEN}"},
                "tools": ["resolve"],
            },
            "remote": {
                "type": "http",
                "url": "https://example.org/mcp",
                "headers": {"Authorization": "Bearer ${TOKEN}"},
            },
            "off": {"command": "x", "enabled": False},
        },
    )
    app = SimpleNamespace(
        mcp=manager(
            config,
            ServerStatus("context7", ServerState.CONNECTED, transport="stdio"),
            ServerStatus("remote", ServerState.FAILED, transport="http", error="refused"),
            ServerStatus("off", ServerState.DISABLED, transport="stdio"),
        )
    )
    servers = {s["name"]: s for s in mcp_servers(app, startup=ENV)["servers"]}

    assert servers["context7"] == {
        "name": "context7",
        "type": "stdio",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "env": {"API_KEY": MASK},
        "enabled": True,
        "tools": ["resolve"],
        "state": "connected",
        "active": True,
        "error": "",
    }
    assert servers["remote"] == {
        "name": "remote",
        "type": "http",
        "transport": "http",
        "url": "https://example.org/mcp",
        "headers": {"Authorization": MASK},
        "enabled": True,
        "state": "failed",
        "active": False,
        "error": "refused",
    }
    assert servers["off"]["state"] == "disabled"
    assert servers["off"]["enabled"] is False
    assert "tools" not in servers["off"]


def test_expanded_tokens_never_reach_the_page(tmp_path):
    """Q12 = a: ``args`` and ``url`` are shown as written, not as expanded."""
    config = loaded(
        tmp_path,
        {
            "stdio": {"command": "run-${TOKEN}", "args": ["--token", "${TOKEN}"]},
            "http": {"url": "https://example.org/mcp?key=${TOKEN}"},
        },
    )
    assert TOKEN in config.servers[0].args  # the running configuration has it
    app = SimpleNamespace(mcp=manager(config))
    payload = mcp_servers(app, startup=ENV)

    assert TOKEN not in json.dumps(payload)
    servers = {s["name"]: s for s in payload["servers"]}
    assert servers["stdio"]["command"] == "run-${TOKEN}"
    assert servers["stdio"]["args"] == ["--token", "${TOKEN}"]
    assert servers["http"]["url"] == "https://example.org/mcp?key=${TOKEN}"


def test_an_unreadable_source_drops_the_three_raw_fields(tmp_path):
    config = loaded(
        tmp_path,
        {
            "stdio": {"command": "npx", "args": ["${TOKEN}"], "env": {"K": "v"}},
            "http": {"url": "https://example.org/${TOKEN}"},
        },
    )
    config.source.unlink()
    payload = mcp_servers(SimpleNamespace(mcp=manager(config)), startup=ENV)

    assert TOKEN not in json.dumps(payload)
    servers = {s["name"]: s for s in payload["servers"]}
    assert "command" not in servers["stdio"] and "args" not in servers["stdio"]
    assert servers["stdio"]["env"] == {"K": MASK}
    assert "url" not in servers["http"]
    assert servers["http"]["state"] == "pending"


def test_a_rejected_entry_has_its_variable_values_replaced(tmp_path):
    config = loaded(
        tmp_path, {"bad": {"type": "http", "url": "ftp://host/${TOKEN}"}}
    )
    assert TOKEN in config.rejected[0].reason
    payload = mcp_servers(SimpleNamespace(mcp=manager(config)), startup=ENV)

    assert payload["servers"] == [
        {
            "name": "bad",
            "state": "failed",
            "active": False,
            "error": payload["servers"][0]["error"],
        }
    ]
    assert TOKEN not in payload["servers"][0]["error"]
    assert MASK in payload["servers"][0]["error"]


def test_a_rejected_entry_without_the_startup_environment_gives_no_reason(tmp_path):
    config = loaded(
        tmp_path, {"bad": {"type": "http", "url": "ftp://host/${TOKEN}"}}
    )
    payload = mcp_servers(SimpleNamespace(mcp=manager(config)))
    assert payload["servers"][0]["error"] == "invalid_config"


def test_an_error_is_cut_to_300_characters():
    config = MCPConfig(rejected=(RejectedServer("bad", "x" * 1000),))
    payload = mcp_servers(SimpleNamespace(mcp=manager(config)), startup={})
    assert len(payload["servers"][0]["error"]) == 300


def test_short_values_are_not_replaced():
    """Only values of eight characters or more are replaced; replacing
    ``1`` or ``yes`` everywhere would make every reason unreadable."""
    config = MCPConfig(rejected=(RejectedServer("bad", "needs yes and 1"),))
    payload = mcp_servers(
        SimpleNamespace(mcp=manager(config)), startup={"A": "yes", "B": "1"}
    )
    assert payload["servers"][0]["error"] == "needs yes and 1"


def test_a_configured_servers_error_has_start_up_values_replaced(tmp_path):
    """A connection failure echoes the expanded command, token included."""
    config = loaded(tmp_path, {"local": {"command": "run-${TOKEN}"}})
    status = ServerStatus(
        "local",
        ServerState.FAILED,
        transport="stdio",
        error=f"cannot start 'run-{TOKEN}': No such file or directory",
    )
    payload = mcp_servers(SimpleNamespace(mcp=manager(config, status)), startup=ENV)
    error = payload["servers"][0]["error"]
    assert TOKEN not in error
    assert error == f"cannot start 'run-{MASK}': No such file or directory"
