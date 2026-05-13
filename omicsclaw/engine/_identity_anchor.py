"""Model-identity disclosure for the system prompt.

Distilled and fine-tuned open-source models routinely claim to be
Claude, GPT, or Gemini when asked about their backbone — training-data
contamination from those models' transcripts. The anchor below tells
the model the truth about which provider + model is actually serving
the request, and forbids impersonation.

Carved out of ``bot/agent_loop.py`` (May 2026 audit) so every surface
can apply the same disclosure instead of the bot loop being the only
one that does.
"""

from __future__ import annotations

_IDENTITY_ANCHOR_HEADER = "## Underlying model identity"


def resolve_effective_model_provider(
    override: str | None,
    default_model: str | None,
    default_provider: str | None,
) -> tuple[str, str]:
    """Return the (model, provider) pair to advertise this request.

    A per-request ``override`` (e.g. the desktop frontend forwarding a
    user-selected model) wins over the bot-wide defaults. All values
    are stripped; missing inputs become ``""``.
    """
    model = (override or default_model or "").strip()
    provider = (default_provider or "").strip()
    return model, provider


def apply_model_identity_anchor(
    system_prompt: str,
    model: str,
    provider: str,
) -> str:
    """Append the identity-anchor section to ``system_prompt``.

    Returns the prompt unchanged when either ``model`` or ``provider``
    is empty — there is no useful disclosure to make in that case, and
    a partial one would let the model invent the missing half.
    """
    if not (model and provider):
        return system_prompt
    return system_prompt.rstrip() + (
        f"\n\n{_IDENTITY_ANCHOR_HEADER}\n"
        f"You are powered by the LLM `{model}` served via the `{provider}` provider. "
        "If the user asks which model or provider backs you, answer truthfully with these exact names. "
        "Do NOT claim to be Claude, GPT, Gemini, DeepSeek, or any other assistant unless it matches the names above. "
        "Do NOT claim to be built by Anthropic, OpenAI, or Google unless the provider above matches."
    )
