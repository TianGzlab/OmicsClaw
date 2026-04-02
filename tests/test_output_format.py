"""Tests for output style layer rendering."""

import json

from omicsclaw.extensions import (
    ExtensionManifest,
    extension_store_dir,
    write_extension_state,
    write_install_record,
)
from omicsclaw.runtime.context_layers import ContextAssemblyRequest
from omicsclaw.runtime.context_layers.output_format import build_output_format_layer


def test_default_interactive_style_instructions_use_registry_and_surface_adapter():
    request = ContextAssemblyRequest(surface="interactive")
    result = build_output_format_layer(request)

    assert result is not None
    assert "## Output Style Profile" in result
    assert "Active style: `default`" in result
    assert "Surface Adapter (interactive)" in result
    assert "emoji" in result.lower()


def test_bot_surface_uses_shared_style_layer_with_bot_adapter():
    request = ContextAssemblyRequest(surface="bot")
    result = build_output_format_layer(request)

    assert result is not None
    assert "Active style: `default`" in result
    assert "Surface Adapter (bot)" in result
    assert "Markdown is acceptable" in result


def test_pipeline_surface_can_use_pipeline_operator_profile():
    request = ContextAssemblyRequest(
        surface="pipeline",
        output_style="pipeline-operator",
    )
    result = build_output_format_layer(request)

    assert result is not None
    assert "Active style: `pipeline-operator`" in result
    assert "status, current step, and blocking issues" in result
    assert "Surface Adapter (pipeline)" in result


def test_extension_output_style_pack_is_available_to_output_layer(tmp_path):
    pack_dir = extension_store_dir(tmp_path, "output-style-pack") / "lab-style-pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "styles.yaml").write_text(
        (
            "styles:\n"
            "  - name: lab-review\n"
            "    description: Findings-first lab review style.\n"
            "    aliases: [lab]\n"
            "    instructions: |\n"
            "      - Lead with deviations from SOP.\n"
            "      - End with a reproducibility note.\n"
        ),
        encoding="utf-8",
    )
    manifest = ExtensionManifest(
        name="lab-style-pack",
        version="1.0.0",
        type="output-style-pack",
        entrypoints=["styles.yaml"],
        trusted_capabilities=["output-style-entry"],
    )
    (pack_dir / "omicsclaw-extension.json").write_text(
        json.dumps(
            {
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type,
                "entrypoints": manifest.entrypoints,
                "trusted_capabilities": manifest.trusted_capabilities,
            }
        ),
        encoding="utf-8",
    )
    write_install_record(
        pack_dir,
        extension_name="lab-style-pack",
        source_kind="local",
        source="/tmp/lab-style-pack",
        manifest=manifest,
        extension_type="output-style-pack",
        relative_install_path="installed_extensions/output-style-packs/lab-style-pack",
    )
    write_extension_state(pack_dir, enabled=True)

    request = ContextAssemblyRequest(
        surface="interactive",
        omicsclaw_dir=str(tmp_path),
        output_style="lab",
    )
    result = build_output_format_layer(request)

    assert result is not None
    assert "Active style: `lab-review`" in result
    assert "Lead with deviations from SOP." in result
    assert "Style source: extension:lab-style-pack" in result
