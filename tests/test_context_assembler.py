"""Tests for chat context assembly and prompt preparation."""

import asyncio
import json

from omicsclaw.interactive import _mcp
from omicsclaw.extensions import write_extension_state, write_install_record
from omicsclaw.runtime.context_layers import (
    build_mcp_instructions_block,
    get_execution_discipline,
    should_prefetch_knowledge_guidance,
    should_prefetch_skill_context,
)
from omicsclaw.runtime.context_assembler import (
    ContextAssemblyRequest,
    assemble_chat_context,
    assemble_prompt_context,
    build_user_message_content,
    extract_analysis_hints,
    should_attach_capability_context,
)


def test_build_user_message_content_converts_multimodal_blocks():
    content = build_user_message_content(
        [
            {"type": "text", "text": "hello"},
            {
                "type": "image",
                "source": {
                    "media_type": "image/png",
                    "data": "abc123",
                },
            },
        ]
    )

    assert content == [
        {"type": "text", "text": "hello"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc123"},
        },
    ]


def test_extract_analysis_hints_and_capability_trigger_are_stable():
    skill_hint, domain_hint = extract_analysis_hints(
        "Please run spatial-preprocess on this Visium dataset."
    )

    assert skill_hint == "spatial-preprocess"
    assert domain_hint == "spatial"
    assert should_attach_capability_context("analyze sample.h5ad") is True
    assert should_attach_capability_context("hello there") is False


def test_assemble_prompt_context_layers_are_ordered_and_accounted():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            memory_context="preferred language: Chinese",
            skill="spatial-preprocess",
            query="Analyze sample.h5ad with spatial-preprocess",
            domain="spatial",
            capability_context="## Deterministic Capability Assessment\n- coverage: exact_skill",
            workspace="/tmp/session",
            pipeline_workspace="/tmp/pipeline",
            mcp_servers=("seq-think", "bio-tools"),
            include_knowhow=True,
            knowhow_loader=lambda **_: "⚠️ MANDATORY SCIENTIFIC CONSTRAINTS\n- Validate QC first.",
        )
    )

    assert assembly.layer_names == (
        "base_persona",
        "output_format",
        "role_guardrails",
        "execution_discipline",
        "skill_contract",
        "memory_context",
        "skill_context",
        "capability_assessment",
        "knowhow_constraints",
        "workspace_context",
        "mcp_instructions",
    )
    assert assembly.layer_stats["workspace_context"]["placement"] == "system"
    assert assembly.layer_stats["mcp_instructions"]["order"] > assembly.layer_stats["workspace_context"]["order"]
    assert assembly.layer_stats["knowhow_constraints"]["cost_chars"] > 0
    assert assembly.total_estimated_tokens >= len(assembly.layer_names)
    assert "BASE PERSONA" in assembly.system_prompt
    assert "## Output Style Profile" in assembly.system_prompt
    assert "preferred language: Chinese" in assembly.system_prompt
    assert "## Prefetched Skill Context" in assembly.system_prompt
    assert "Selected skill: `spatial-preprocess`" in assembly.system_prompt
    assert "seq-think" in assembly.system_prompt
    assert "Execution discipline:" in assembly.system_prompt
    assert assembly.message_context == ""


def test_assemble_prompt_context_can_route_workspace_to_message_context():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="bot",
            base_persona="BASE PERSONA",
            workspace="/tmp/session",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
            workspace_placement="message",
        )
    )

    # Bot mode includes output_format layer, so system prompt is not just base persona
    assert "BASE PERSONA" in assembly.system_prompt
    assert "## Output Style Profile" in assembly.system_prompt
    assert "Surface Adapter (bot)" in assembly.system_prompt
    assert assembly.message_context.startswith("## Workspace Context")
    assert "/tmp/session" in assembly.message_context
    assert assembly.layer_stats["workspace_context"]["placement"] == "message"


def test_get_execution_discipline_adapts_to_surface_and_workspace():
    bot_rules = get_execution_discipline(surface="bot")
    interactive_rules = get_execution_discipline(
        surface="interactive",
        workspace="/tmp/session",
        pipeline_workspace="/tmp/pipeline",
        plan_context_present=True,
    )

    assert "Chat Mode Discipline" in bot_rules
    assert "Workspace Continuity" not in bot_rules
    assert "Workspace Continuity" in interactive_rules
    assert "`plan.md`" in interactive_rules
    assert "`tool_search`" in interactive_rules


def test_assemble_prompt_context_can_disable_execution_discipline():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            include_execution_discipline=False,
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
        )
    )

    assert "execution_discipline" not in assembly.layer_stats
    assert "Execution discipline:" not in assembly.system_prompt


def test_assemble_chat_context_loads_memory_and_builds_prompt():
    calls = {
        "session": [],
        "resolver": None,
        "prompt": None,
    }

    class FakeSessionManager:
        async def get_or_create(self, user_id, platform, chat_id):
            calls["session"].append(("get_or_create", user_id, platform, chat_id))

        async def load_context(self, session_id):
            calls["session"].append(("load_context", session_id))
            return "preferred language: Chinese"

    class FakeDecision:
        chosen_skill = "spatial-preprocess"
        domain = "spatial"

        def to_prompt_block(self):
            return "## Deterministic Capability Assessment\n- coverage: exact_skill"

    def fake_capability_resolver(query, *, domain_hint=""):
        calls["resolver"] = (query, domain_hint)
        return FakeDecision()

    def fake_prompt_builder(**kwargs):
        calls["prompt"] = kwargs
        return "PROMPT"

    context = asyncio.run(
        assemble_chat_context(
            chat_id="chat-1",
            user_content="Analyze sample.h5ad with spatial-preprocess",
            user_id="user-1",
            platform="telegram",
            session_manager=FakeSessionManager(),
            system_prompt_builder=fake_prompt_builder,
            capability_resolver=fake_capability_resolver,
            skill_aliases=("spatial-preprocess", "sc-qc"),
        )
    )

    assert context.session_id == "telegram:user-1:chat-1"
    assert context.memory_context == "preferred language: Chinese"
    assert context.user_text == "Analyze sample.h5ad with spatial-preprocess"
    assert context.user_message_content == "Analyze sample.h5ad with spatial-preprocess"
    assert context.skill_hint == "spatial-preprocess"
    assert context.domain_hint == "spatial"
    assert context.capability_context.startswith("## Deterministic Capability Assessment")
    assert context.system_prompt == "PROMPT"
    assert calls["session"] == [
        ("get_or_create", "user-1", "telegram", "chat-1"),
        ("load_context", "telegram:user-1:chat-1"),
    ]
    assert calls["resolver"] == (
        "Analyze sample.h5ad with spatial-preprocess",
        "spatial",
    )
    assert calls["prompt"]["memory_context"] == "preferred language: Chinese"
    assert calls["prompt"]["scoped_memory_context"] == ""
    assert calls["prompt"]["skill"] == "spatial-preprocess"
    assert calls["prompt"]["skill_candidates"] == ("spatial-preprocess",)
    assert calls["prompt"]["query"] == "Analyze sample.h5ad with spatial-preprocess"
    assert calls["prompt"]["domain"] == "spatial"
    assert calls["prompt"]["capability_context"] == "## Deterministic Capability Assessment\n- coverage: exact_skill"
    assert calls["prompt"]["plan_context"] == ""
    assert calls["prompt"]["transcript_context"] == ""
    assert calls["prompt"]["surface"] == "bot"
    assert calls["prompt"]["output_style"] == ""
    assert calls["prompt"]["workspace"] == ""
    assert calls["prompt"]["pipeline_workspace"] == ""
    assert calls["prompt"]["mcp_servers"] == ()
    assert calls["prompt"]["skill_context"].startswith("## Prefetched Skill Context")
    assert "Selected skill: `spatial-preprocess`" in calls["prompt"]["skill_context"]
    assert "- Domain: `spatial`" in calls["prompt"]["skill_context"]
    assert "- Summary:" in calls["prompt"]["skill_context"]
    assert "workspace_context" not in context.prompt_context.layer_stats


def test_assemble_chat_context_passes_interactive_surface_to_prompt_builder():
    calls = {"prompt": None}

    def fake_prompt_builder(**kwargs):
        calls["prompt"] = kwargs
        return "PROMPT"

    context = asyncio.run(
        assemble_chat_context(
            chat_id="chat-2",
            user_content="hello there",
            user_id="user-2",
            platform="cli",
            system_prompt_builder=fake_prompt_builder,
            output_style="teaching",
            workspace="/tmp/chat-workspace",
            pipeline_workspace="/tmp/pipeline-workspace",
            mcp_servers=("seq-think", "bio-tools"),
        )
    )

    assert context.system_prompt == "PROMPT"
    assert calls["prompt"] == {
        "memory_context": "",
        "scoped_memory_context": "",
        "skill_context": "",
        "skill": "",
        "skill_candidates": (),
        "query": "hello there",
        "domain": "",
        "capability_context": "",
        "plan_context": "",
        "transcript_context": "",
        "surface": "interactive",
        "output_style": "teaching",
        "workspace": "/tmp/chat-workspace",
        "pipeline_workspace": "/tmp/pipeline-workspace",
        "mcp_servers": ("seq-think", "bio-tools"),
    }


def test_assemble_chat_context_loads_scoped_memory_and_forwards_to_prompt_builder():
    calls = {"prompt": None}

    class FakeRecall:
        def to_context_text(self):
            return "1. PBMC QC defaults\n   scope=project | owner=tester | freshness=evolving | updated=2026-04-02"

    def fake_prompt_builder(**kwargs):
        calls["prompt"] = kwargs
        return "PROMPT"

    context = asyncio.run(
        assemble_chat_context(
            chat_id="chat-scoped-memory",
            user_content="Continue the PBMC QC analysis",
            user_id="user-scoped-memory",
            platform="cli",
            workspace="/tmp/project",
            system_prompt_builder=fake_prompt_builder,
            scoped_memory_scope="project",
            scoped_memory_loader=lambda **_: FakeRecall(),
        )
    )

    assert context.system_prompt == "PROMPT"
    assert "PBMC QC defaults" in context.scoped_memory_context
    assert calls["prompt"]["scoped_memory_context"].startswith("1. PBMC QC defaults")


def test_assemble_prompt_context_prefetches_knowledge_guidance_for_method_questions():
    calls = []

    def fake_knowledge_loader(**kwargs):
        calls.append(kwargs)
        return "## Preloaded Knowledge Guidance\n\nPrefer Harmony for batch correction."

    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            query="Which method should I use for batch correction?",
            domain="singlecell",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
            knowledge_loader=fake_knowledge_loader,
        )
    )

    assert "knowledge_guidance" in assembly.layer_stats
    assert "Prefer Harmony for batch correction." in assembly.system_prompt
    assert calls == [
        {
            "query": "Which method should I use for batch correction?",
            "skill": "",
            "domain": "singlecell",
        }
    ]


def test_should_prefetch_knowledge_guidance_covers_more_real_world_queries():
    assert should_prefetch_knowledge_guidance(
        query="Can you recommend a suitable workflow for single-cell batch correction?"
    ) is True
    assert should_prefetch_knowledge_guidance(
        query="Seurat vs Harmony for integration, which should I choose?"
    ) is True
    assert should_prefetch_knowledge_guidance(
        query="帮我推荐适合这个数据的空间变异基因方法"
    ) is True
    assert should_prefetch_knowledge_guidance(
        query="这两种方法有什么区别，参数怎么选？"
    ) is True
    assert should_prefetch_knowledge_guidance(
        query="Analyze sample.h5ad and save outputs."
    ) is False


def test_should_prefetch_skill_context_tracks_skill_or_capability_hits():
    assert should_prefetch_skill_context(
        skill="spatial-preprocess",
        query="Analyze sample.h5ad",
    ) is True
    assert should_prefetch_skill_context(
        query="Analyze sample.h5ad",
        capability_context="## Deterministic Capability Assessment\n- coverage: exact_skill",
    ) is True
    assert should_prefetch_skill_context(
        query="hello there",
    ) is False


def test_assemble_prompt_context_skips_knowledge_guidance_for_generic_requests():
    calls = []

    def fake_knowledge_loader(**kwargs):
        calls.append(kwargs)
        return "## Preloaded Knowledge Guidance\n\nThis should not be used."

    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            query="Analyze sample.h5ad",
            domain="singlecell",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
            knowledge_loader=fake_knowledge_loader,
        )
    )

    assert "knowledge_guidance" not in assembly.layer_stats
    assert "This should not be used." not in assembly.system_prompt
    assert calls == []


def test_assemble_prompt_context_includes_skill_context_only_when_relevant():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            skill="spatial-preprocess",
            query="Analyze sample.h5ad with spatial-preprocess",
            domain="spatial",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
        )
    )

    assert "skill_context" in assembly.layer_stats
    assert "## Prefetched Skill Context" in assembly.system_prompt
    assert "Selected skill: `spatial-preprocess`" in assembly.system_prompt


def test_build_mcp_instructions_block_skips_inactive_entries():
    block = build_mcp_instructions_block(
        [
            {"name": "offline-http", "transport": "http", "active": False},
            {"name": "seq-think", "transport": "stdio", "active": True},
        ]
    )

    assert "seq-think" in block
    assert "offline-http" not in block
    assert "Active MCP transports: stdio" in block


def test_load_active_mcp_server_entries_for_prompt_filters_per_server(monkeypatch):
    monkeypatch.setattr(
        _mcp,
        "load_mcp_config",
        lambda: {
            "seq-think": {"transport": "stdio", "command": "npx"},
            "offline-http": {"transport": "http", "url": "http://offline"},
        },
    )

    async def _fake_probe(name, server):
        if name == "seq-think":
            return {
                "name": name,
                "transport": server["transport"],
                "active": True,
                "loaded": True,
            }
        return None

    monkeypatch.setattr(_mcp, "_probe_mcp_server_entry_for_prompt", _fake_probe)
    monkeypatch.setattr(_mcp, "_PROMPT_STATUS_CACHE_KEY", None)
    monkeypatch.setattr(_mcp, "_PROMPT_STATUS_CACHE_VALUE", ())
    monkeypatch.setattr(_mcp, "_PROMPT_STATUS_CACHE_AT", 0.0)

    entries = asyncio.run(_mcp.load_active_mcp_server_entries_for_prompt())

    assert entries == (
        {
            "name": "seq-think",
            "transport": "stdio",
            "active": True,
            "loaded": True,
        },
    )


def test_mcp_runtime_config_skips_disabled_entries_and_forwards_headers(monkeypatch):
    monkeypatch.setenv("MCP_AUTH", "Bearer token")
    monkeypatch.setattr(
        _mcp,
        "_load_raw",
        lambda: {
            "disabled-remote": {
                "transport": "sse",
                "url": "https://disabled.example/sse",
                "headers": {"Authorization": "${MCP_AUTH}"},
                "enabled": False,
            },
            "secure-remote": {
                "transport": "http",
                "url": "https://enabled.example/mcp",
                "headers": {"Authorization": "${MCP_AUTH}"},
            },
        },
    )

    runtime_config = _mcp.load_mcp_config()
    all_config = _mcp.load_mcp_config(include_disabled=True)
    connection = _mcp._build_mcp_connection(all_config["secure-remote"])

    assert "disabled-remote" not in runtime_config
    assert all_config["disabled-remote"]["enabled"] is False
    assert all_config["secure-remote"]["headers"] == {"Authorization": "Bearer token"}
    assert connection == {
        "transport": "http",
        "url": "https://enabled.example/mcp",
        "headers": {"Authorization": "Bearer token"},
    }
    assert _mcp._build_mcp_connection(all_config["disabled-remote"]) is None


def test_assemble_chat_context_forwards_knowledge_guidance_to_prompt_builder(monkeypatch):
    calls = {"prompt": None}

    def fake_prompt_builder(**kwargs):
        calls["prompt"] = kwargs
        return "PROMPT"

    monkeypatch.setattr(
        "omicsclaw.runtime.context_layers.load_knowledge_guidance",
        lambda **_: "## Preloaded Knowledge Guidance\n\nPrefer Harmony for batch correction.",
    )

    context = asyncio.run(
        assemble_chat_context(
            chat_id="chat-knowledge",
            user_content="Which method should I use for batch correction?",
            user_id="user-knowledge",
            platform="cli",
            system_prompt_builder=fake_prompt_builder,
        )
    )

    assert context.system_prompt == "PROMPT"
    assert calls["prompt"]["knowledge_context"].startswith("## Preloaded Knowledge Guidance")
    assert calls["prompt"]["include_knowledge_guidance"] is True


def test_assemble_prompt_context_includes_plan_context_layer():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            plan_context="## Active Plan Mode\n\n- Status: approved",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
        )
    )

    assert "plan_context" in assembly.layer_stats
    assert "## Active Plan Mode" in assembly.system_prompt


def test_assemble_prompt_context_routes_transcript_context_to_message_layer():
    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            base_persona="BASE PERSONA",
            transcript_context="## Selective Transcript Replay\n\n- omitted older refs",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
        )
    )

    assert "transcript_context" in assembly.layer_stats
    assert assembly.layer_stats["transcript_context"]["placement"] == "message"
    assert "## Selective Transcript Replay" in assembly.message_context


def test_assemble_prompt_context_includes_active_prompt_pack_layer(tmp_path):
    prompt_pack = tmp_path / "installed_extensions" / "prompt-packs" / "local-rules"
    prompt_pack.mkdir(parents=True)
    (prompt_pack / "rules.md").write_text(
        "Use concise scientific tone.\nPreserve exact output paths.\n",
        encoding="utf-8",
    )
    (prompt_pack / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "local-rules",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "trusted_capabilities": ["prompt-rules"],
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        prompt_pack,
        extension_name="local-rules",
        source_kind="local",
        source="/tmp/local-rules",
        extension_type="prompt-pack",
        relative_install_path="installed_extensions/prompt-packs/local-rules",
    )
    write_extension_state(prompt_pack, enabled=True)

    assembly = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface="interactive",
            omicsclaw_dir=str(tmp_path),
            base_persona="BASE PERSONA",
            include_role_guardrails=False,
            include_skill_contract=False,
            include_knowhow=False,
        )
    )

    assert "extension_prompt_packs" in assembly.layer_stats
    assert "## Active Local Prompt Packs" in assembly.system_prompt
    assert "Use concise scientific tone." in assembly.system_prompt
    assert assembly.layer_stats["extension_prompt_packs"]["placement"] == "system"


def test_assemble_chat_context_forwards_prompt_pack_context_to_builder(tmp_path):
    prompt_pack = tmp_path / "installed_extensions" / "prompt-packs" / "local-rules"
    prompt_pack.mkdir(parents=True)
    (prompt_pack / "rules.md").write_text(
        "Prefer exact status summaries.\n",
        encoding="utf-8",
    )
    (prompt_pack / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": "local-rules",
                "version": "1.0.0",
                "type": "prompt-pack",
                "entrypoints": ["rules.md"],
                "trusted_capabilities": ["prompt-rules"],
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        prompt_pack,
        extension_name="local-rules",
        source_kind="local",
        source="/tmp/local-rules",
        extension_type="prompt-pack",
        relative_install_path="installed_extensions/prompt-packs/local-rules",
    )
    write_extension_state(prompt_pack, enabled=True)

    calls = {"prompt": None}

    def fake_prompt_builder(**kwargs):
        calls["prompt"] = kwargs
        return "PROMPT"

    context = asyncio.run(
        assemble_chat_context(
            chat_id="chat-pack",
            user_content="hello there",
            user_id="user-pack",
            platform="cli",
            system_prompt_builder=fake_prompt_builder,
            omicsclaw_dir=str(tmp_path),
        )
    )

    assert context.system_prompt == "PROMPT"
    assert calls["prompt"]["omicsclaw_dir"] == str(tmp_path)
    assert "## Active Local Prompt Packs" in calls["prompt"]["prompt_pack_context"]
    assert "Prefer exact status summaries." in calls["prompt"]["prompt_pack_context"]
