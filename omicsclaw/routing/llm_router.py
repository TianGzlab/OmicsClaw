"""LLM-based query routing for orchestrators."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Tuple

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, use system environment variables

logger = logging.getLogger(__name__)

def route_with_llm(query: str, skills: Dict[str, str], domain: str) -> Tuple[str, float]:
    """Route query using LLM API.

    Supported providers: deepseek, gemini, openai, custom

    Args:
        query: User's natural language query
        skills: Dict of {skill_name: description}
        domain: Omics domain (spatial, singlecell, etc.)

    Returns:
        (skill_name, confidence) tuple
    """
    # Check provider-specific API keys first
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        logger.warning("No API key found (DEEPSEEK_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or LLM_API_KEY)")
        return None, 0.0

    # Check for LLM_PROVIDER for auto-configuration
    provider = os.getenv("LLM_PROVIDER", "").lower()
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("OMICSCLAW_MODEL") or os.getenv("LLM_MODEL")

    # Auto-configure based on provider
    if provider and not base_url:
        if provider == "deepseek":
            base_url = "https://api.deepseek.com/v1"
            model = model or "deepseek-chat"
        elif provider == "openai":
            base_url = "https://api.openai.com/v1"
            model = model or "gpt-4o-mini"
        elif provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta"
            model = model or "gemini-2.0-flash"

    # Fallback auto-detection if no provider set
    if not base_url:
        if os.getenv("DEEPSEEK_API_KEY"):
            base_url = "https://api.deepseek.com/v1"
            model = model or "deepseek-chat"
        elif os.getenv("OPENAI_API_KEY"):
            base_url = "https://api.openai.com/v1"
            model = model or "gpt-4o-mini"
        else:
            base_url = "https://api.openai.com/v1"
            model = model or "gpt-4o-mini"
    else:
        model = model or "gpt-4o-mini"
    
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
        url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
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
