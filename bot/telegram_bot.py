#!/usr/bin/env python3
"""
telegram_bot.py — OmicsClaw Telegram Bot (thin launcher)
========================================================
Telegram frontend for OmicsClaw multi-omics skills.
Uses the multi-channel abstraction (bot/channels/) and shared core engine
(bot/core.py) for LLM reasoning and skill execution.

Prerequisites:
    pip install -r bot/requirements.txt

Usage:
    python bot/telegram_bot.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``import bot.core`` works when
# this script is executed directly (``python bot/telegram_bot.py``).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_dotenv_candidates = [
    _PROJECT_ROOT / ".env",
    Path.cwd() / ".env",
]
for _p in _dotenv_candidates:
    if _p.exists():
        from dotenv import load_dotenv
        load_dotenv(str(_p))
        break

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0") or "0")
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
OMICSCLAW_MODEL = os.environ.get("OMICSCLAW_MODEL", os.environ.get("SPATIALCLAW_MODEL", ""))
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "10"))

if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not set. See bot/README.md for setup.")
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
# Main — thin launcher using TelegramChannel
# ---------------------------------------------------------------------------

def main():
    from bot.channels.telegram import TelegramChannel, TelegramConfig

    config = TelegramConfig(
        bot_token=TELEGRAM_BOT_TOKEN,
        admin_chat_id=ADMIN_CHAT_ID,
        rate_limit_per_hour=RATE_LIMIT_PER_HOUR,
    )
    channel = TelegramChannel(config)
    channel.run_polling()


if __name__ == "__main__":
    main()
