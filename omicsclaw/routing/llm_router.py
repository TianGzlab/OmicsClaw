"""LLM-based query routing for orchestrators."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

from omicsclaw.common.runtime_env import load_project_dotenv

load_project_dotenv(Path(__file__).resolve().parent.parent.parent, override=False)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider resolution — reuses bot.core when available, else falls back
# ---------------------------------------------------------------------------

# Import shared provider presets from bot.core (avoids hard-coding provider
# URLs in multiple places).  Graceful fallback for standalone usage.
try:
    from bot.core import PROVIDER_PRESETS, _PROVIDER_DETECT_ORDER
    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False
    # Minimal fallback matching the most common providers
    PROVIDER_PRESETS = {
        "deepseek":   ("https://api.deepseek.com",                                "deepseek-chat",       "DEEPSEEK_API_KEY"),
        "openai":     ("https://api.openai.com/v1",                               "gpt-4o",              "OPENAI_API_KEY"),
        "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash",    "GOOGLE_API_KEY"),
        "anthropic":  ("https://api.anthropic.com/v1/",                            "claude-sonnet-4-5-20250514", "ANTHROPIC_API_KEY"),
        "nvidia":     ("https://integrate.api.nvidia.com/v1",                      "deepseek-ai/deepseek-r1",    "NVIDIA_API_KEY"),
        "siliconflow":("https://api.siliconflow.cn/v1",                           "deepseek-ai/DeepSeek-V3",    "SILICONFLOW_API_KEY"),
        "openrouter": ("https://openrouter.ai/api/v1",                            "deepseek/deepseek-chat-v3-0324", "OPENROUTER_API_KEY"),
        "volcengine": ("https://ark.cn-beijing.volces.com/api/v3",                "doubao-1.5-pro-256k", "VOLCENGINE_API_KEY"),
        "dashscope":  ("https://dashscope.aliyuncs.com/compatible-mode/v1",       "qwen-max",            "DASHSCOPE_API_KEY"),
        "zhipu":      ("https://open.bigmodel.cn/api/paas/v4",                    "glm-4-flash",         "ZHIPU_API_KEY"),
        "ollama":     ("http://localhost:11434/v1",                                "qwen2.5:7b",          ""),
        "custom":     ("",                                                         "",                    ""),
    }
    _PROVIDER_DETECT_ORDER = [
        "deepseek", "openai", "anthropic", "gemini", "nvidia",
        "siliconflow", "openrouter", "volcengine", "dashscope", "zhipu",
    ]


def _resolve_llm_config() -> Tuple[str, str, str]:
    """Resolve (api_key, base_url, model) for LLM routing calls.

    Priority: LLM_PROVIDER env > provider-specific key auto-detection > LLM_API_KEY fallback.

    Returns:
        (api_key, base_url, model) tuple.
    """
    provider = os.getenv("LLM_PROVIDER", "").lower().strip()
    base_url = os.getenv("LLM_BASE_URL", "")
    model = os.getenv("OMICSCLAW_MODEL") or os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")

    # If provider is set, use its preset
    if provider and provider in PROVIDER_PRESETS:
        purl, pmodel, pkey_env = PROVIDER_PRESETS[provider]
        base_url = base_url or os.getenv(f"{provider.upper()}_BASE_URL", "") or purl
        model = model or pmodel
        if not api_key and pkey_env:
            api_key = os.getenv(pkey_env, "")
    elif not provider:
        # Auto-detect from available API keys
        for p in _PROVIDER_DETECT_ORDER:
            purl, pmodel, pkey_env = PROVIDER_PRESETS[p]
            if pkey_env and os.getenv(pkey_env):
                api_key = api_key or os.getenv(pkey_env, "")
                base_url = base_url or purl
                model = model or pmodel
                provider = p
                break

    # Ultimate fallback
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "")
    if not base_url:
        base_url = "https://api.openai.com/v1"
    if not model:
        model = "gpt-4o-mini"

    return api_key, base_url, model


def route_with_llm(query: str, skills: Dict[str, str], domain: str) -> Tuple[Optional[str], float]:
    """Route query using LLM API.

    Supports all providers configured in bot/core.py PROVIDER_PRESETS:
    deepseek, openai, anthropic, gemini, nvidia, siliconflow, openrouter,
    volcengine, dashscope, zhipu, ollama, custom

    Args:
        query: User's natural language query
        skills: Dict of {skill_name: description}
        domain: Omics domain (spatial, singlecell, etc.)

    Returns:
        (skill_name, confidence) tuple
    """
    api_key, base_url, model = _resolve_llm_config()
    if not api_key:
        logger.warning("No API key found for LLM routing. Check provider config or set LLM_API_KEY.")
        return None, 0.0

    # Build skill list for prompt
    skill_list = "\n".join([f"- {name}: {desc}" for name, desc in skills.items()])
    
    prompt = f"""You are an expert in {domain} omics analysis. Given a user query, select the MOST appropriate skill and provide a confidence score.

Available skills:
{skill_list}

User query: "{query}"

Respond with ONLY a JSON object in this exact format:
{{"skill": "skill-name", "confidence": 0.95}}

The confidence should be between 0.0 and 1.0, where:
- 1.0 = perfect match, no ambiguity
- 0.8-0.9 = strong match, clear intent
- 0.6-0.7 = reasonable match, some ambiguity
- 0.5 or below = weak match, uncertain"""
    
    try:
        import requests
        url = f"{base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"API error {response.status_code}: {response.text}")
            return None, 0.0

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        try:
            parsed = json.loads(content)
            skill = parsed.get("skill", "").strip()
            confidence = float(parsed.get("confidence", 0.0))
        except (json.JSONDecodeError, ValueError, KeyError):
            # Fallback: treat as plain skill name
            skill = content
            confidence = 0.8

        # Validate skill exists
        if skill in skills:
            return skill, min(max(confidence, 0.0), 1.0)  # Clamp to [0, 1]
        else:
            logger.warning(f"LLM returned invalid skill: {skill}")
            return None, 0.0
    except Exception as e:
        logger.error(f"LLM routing failed: {e}")
        return None, 0.0
