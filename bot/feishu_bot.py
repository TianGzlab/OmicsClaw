#!/usr/bin/env python3
"""
feishu_bot.py — OmicsClaw Feishu (Lark) Bot (thin launcher)
============================================================
Feishu frontend for OmicsClaw multi-omics skills.
Uses the multi-channel abstraction (bot/channels/) and shared core engine
(bot/core.py) for LLM reasoning and skill execution.
Uses lark-oapi Python SDK with WebSocket long-connection (no public IP required).

Prerequisites:
    pip install -r bot/requirements.txt

Usage:
    python bot/feishu_bot.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_dotenv_candidates = [_PROJECT_ROOT / ".env", Path.cwd() / ".env"]
for _p in _dotenv_candidates:
    if _p.exists():
        from dotenv import load_dotenv
        load_dotenv(str(_p))
        break

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
OMICSCLAW_MODEL = os.environ.get("OMICSCLAW_MODEL", os.environ.get("SPATIALCLAW_MODEL", ""))
THINKING_THRESHOLD_MS = int(os.environ.get("FEISHU_THINKING_THRESHOLD_MS", "2500"))
MAX_INBOUND_IMAGE_MB = int(os.environ.get("FEISHU_MAX_INBOUND_IMAGE_MB", "12"))
MAX_INBOUND_FILE_MB = int(os.environ.get("FEISHU_MAX_INBOUND_FILE_MB", "40"))
MAX_ATTACHMENTS = int(os.environ.get("FEISHU_MAX_ATTACHMENTS", "4"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("FEISHU_RATE_LIMIT_PER_HOUR", "60"))
DEBUG = os.environ.get("FEISHU_BRIDGE_DEBUG", "") == "1"

if not FEISHU_APP_ID:
    print("Error: FEISHU_APP_ID not set. See bot/README.md for setup.")
    sys.exit(1)
if not FEISHU_APP_SECRET:
    print("Error: FEISHU_APP_SECRET not set. See bot/README.md for setup.")
    sys.exit(1)
if not LLM_API_KEY:
    print("Error: LLM_API_KEY not set. See bot/README.md for setup.")
    sys.exit(1)

from bot import core  # noqa: E402

core.init(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL or None,
    model=OMICSCLAW_MODEL,
    provider=LLM_PROVIDER,
)


# ---------------------------------------------------------------------------
# Main — thin launcher using FeishuChannel
# ---------------------------------------------------------------------------

def main():
    from bot.channels.feishu import FeishuChannel, FeishuConfig

    config = FeishuConfig(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        thinking_threshold_ms=THINKING_THRESHOLD_MS,
        max_inbound_image_mb=MAX_INBOUND_IMAGE_MB,
        max_inbound_file_mb=MAX_INBOUND_FILE_MB,
        max_attachments=MAX_ATTACHMENTS,
        rate_limit_per_hour=RATE_LIMIT_PER_HOUR,
        debug=DEBUG,
    )
    channel = FeishuChannel(config)
    channel.run_sync()


if __name__ == "__main__":
    main()
