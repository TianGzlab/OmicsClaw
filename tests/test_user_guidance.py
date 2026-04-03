from omicsclaw.common.user_guidance import (
    extract_user_guidance_lines,
    extract_user_guidance_payloads,
    format_user_guidance,
    format_user_guidance_payload,
    render_guidance_block,
)


def test_extract_user_guidance_lines():
    stderr = "INFO: load\nWARNING: USER_GUIDANCE: run sc-standardize-input first\nWARNING: other\nWARNING: USER_GUIDANCE: confirm sample_key before pseudobulk DE\n"
    lines = extract_user_guidance_lines(stderr)
    assert lines == [
        "run sc-standardize-input first",
        "confirm sample_key before pseudobulk DE",
    ]


def test_render_guidance_block():
    block = render_guidance_block(
        [
            "User confirmation required: confirm sample_key",
            "Cannot continue yet: missing spliced/unspliced layers",
            "run sc-standardize-input first",
        ],
        title="Important follow-up",
    )
    assert "## Before I run this, please confirm" in block
    assert "## I Need This First" in block
    assert "## Important follow-up" in block
    assert "run sc-standardize-input first" in block
    assert format_user_guidance("hello").startswith("USER_GUIDANCE:")


def test_extract_structured_user_guidance_payloads():
    payload = {
        "kind": "preflight",
        "skill_name": "sc-de",
        "status": "needs_user_input",
        "guidance": ["run sc-standardize-input first"],
        "confirmations": ["confirm groupby column"],
        "missing_requirements": [],
    }
    stderr = "WARNING: " + format_user_guidance_payload(payload) + "\n"
    parsed = extract_user_guidance_payloads(stderr)
    assert parsed and parsed[0]["skill_name"] == "sc-de"

    block = render_guidance_block([], payloads=parsed)
    assert "## Before I run this, please confirm" in block
    assert "confirm groupby column?" in block
