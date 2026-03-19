"""
Base configuration for all channel implementations.

Provides common fields shared across channels, reducing duplication.
Channel-specific configs inherit from BaseChannelConfig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseChannelConfig:
    """Common configuration fields for all channels.

    Subclass this for channel-specific configs. Only add fields
    here that are used by multiple channels.
    """

    allowed_senders: set[str] | None = None
    text_chunk_limit: int = 4096
    proxy: str | None = None
    include_attachments: bool = True
    rate_limit_per_hour: int = 0    # 0 = no limit
