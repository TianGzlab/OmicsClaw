"""Unit tests for the multi-channel abstraction layer (Phase 1-4)."""

import sys
from pathlib import Path

# Ensure project root is on path  
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import asyncio
import pytest


# ═══════════════ Phase 1: Core Abstractions ═══════════════


class TestChunkText:
    """Test the chunk_text utility function."""

    def test_short_text_no_split(self):
        from bot.channels.base import chunk_text
        assert chunk_text("Hello", 100) == ["Hello"]

    def test_empty_text(self):
        from bot.channels.base import chunk_text
        assert chunk_text("", 100) == []

    def test_long_text_splits(self):
        from bot.channels.base import chunk_text
        text = "Hello world " * 100
        chunks = chunk_text(text, 100)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 120  # Allow small overhead for code fences

    def test_splits_at_paragraph(self):
        from bot.channels.base import chunk_text
        text = "Part one\n\nPart two\n\nPart three"
        chunks = chunk_text(text, 20)
        assert len(chunks) >= 2


class TestDedupCache:
    """Test the dedup cache."""

    def test_first_seen_not_duplicate(self):
        from bot.channels.base import DedupCache
        cache = DedupCache()
        assert not cache.is_duplicate("msg1")

    def test_second_seen_is_duplicate(self):
        from bot.channels.base import DedupCache
        cache = DedupCache()
        cache.is_duplicate("msg1")
        assert cache.is_duplicate("msg1")

    def test_empty_id_not_duplicate(self):
        from bot.channels.base import DedupCache
        cache = DedupCache()
        assert not cache.is_duplicate("")

    def test_different_ids_not_duplicate(self):
        from bot.channels.base import DedupCache
        cache = DedupCache()
        cache.is_duplicate("msg1")
        assert not cache.is_duplicate("msg2")


class TestRateLimiter:
    """Test the rate limiter."""

    def test_under_limit(self):
        from bot.channels.base import RateLimiter
        limiter = RateLimiter(max_per_hour=5)
        for _ in range(5):
            assert limiter.check("user1")

    def test_over_limit(self):
        from bot.channels.base import RateLimiter
        limiter = RateLimiter(max_per_hour=2)
        limiter.check("user1")
        limiter.check("user1")
        assert not limiter.check("user1")

    def test_zero_limit_allows_all(self):
        from bot.channels.base import RateLimiter
        limiter = RateLimiter(max_per_hour=0)
        for _ in range(100):
            assert limiter.check("user1")


class TestChannelCapabilities:
    """Test channel capability profiles."""

    def test_telegram_caps(self):
        from bot.channels.capabilities import TELEGRAM
        assert TELEGRAM.format_type == "html"
        assert TELEGRAM.max_text_length == 4000
        assert TELEGRAM.typing is True
        assert TELEGRAM.media_send is True
        assert TELEGRAM.html is True

    def test_feishu_caps(self):
        from bot.channels.capabilities import FEISHU
        assert FEISHU.format_type == "markdown"
        assert FEISHU.typing is False
        assert FEISHU.markdown is True

    def test_discord_caps(self):
        from bot.channels.capabilities import DISCORD
        assert DISCORD.max_text_length == 2000
        assert DISCORD.typing is True

    def test_supports_method(self):
        from bot.channels.capabilities import TELEGRAM, FEISHU
        assert TELEGRAM.supports("typing") is True
        assert FEISHU.supports("typing") is False
        assert TELEGRAM.supports("nonexistent") is False

    def test_frozen(self):
        from bot.channels.capabilities import TELEGRAM
        with pytest.raises(AttributeError):
            TELEGRAM.typing = False


class TestBaseConfig:
    """Test base channel configuration."""

    def test_default_values(self):
        from bot.channels.config import BaseChannelConfig
        config = BaseChannelConfig()
        assert config.allowed_senders is None
        assert config.text_chunk_limit == 4096
        assert config.proxy is None
        assert config.rate_limit_per_hour == 0

    def test_custom_values(self):
        from bot.channels.config import BaseChannelConfig
        config = BaseChannelConfig(
            rate_limit_per_hour=10,
            text_chunk_limit=2000,
        )
        assert config.rate_limit_per_hour == 10
        assert config.text_chunk_limit == 2000


# ═══════════════ Phase 2: Channel Imports ═══════════════


class TestChannelImports:
    """Test that channel subclasses can be imported."""

    def test_telegram_channel_importable(self):
        from bot.channels.telegram import TelegramChannel, TelegramConfig
        config = TelegramConfig(bot_token="test_token")
        channel = TelegramChannel(config)
        assert channel.name == "telegram"
        assert channel.capabilities.format_type == "html"

    def test_feishu_channel_importable(self):
        from bot.channels.feishu import FeishuChannel, FeishuConfig
        config = FeishuConfig(app_id="test", app_secret="test")
        channel = FeishuChannel(config)
        assert channel.name == "feishu"
        assert channel.capabilities.format_type == "markdown"

    def test_channel_registry(self):
        from bot.channels import CHANNEL_REGISTRY
        assert "telegram" in CHANNEL_REGISTRY
        assert "feishu" in CHANNEL_REGISTRY


class TestChannelManagerImport:
    """Test that ChannelManager can be imported."""

    def test_manager_importable(self):
        from bot.channels.manager import ChannelHealth, ChannelManager
        manager = ChannelManager()
        assert manager.enabled_channels == []
        assert manager.running_channels() == []

    def test_health_tracking(self):
        from bot.channels.manager import ChannelHealth
        health = ChannelHealth()
        assert health.consecutive_failures == 0
        health.record_failure("test error")
        assert health.consecutive_failures == 1
        assert health.total_errors == 1
        health.record_success()
        assert health.consecutive_failures == 0

    def test_get_health(self):
        from bot.channels.manager import ChannelManager
        manager = ChannelManager()
        health = manager.get_health()
        assert health["status"] == "degraded"  # No channels running
        assert health["channels"]["registered"] == []
        assert health["channels"]["running"] == []


class TestRunnerImport:
    """Test that the unified runner can be imported."""

    def test_runner_importable(self):
        from bot.run import CHANNEL_BUILDERS
        assert "telegram" in CHANNEL_BUILDERS
        assert "feishu" in CHANNEL_BUILDERS

    def test_all_six_channels_in_builders(self):
        from bot.run import CHANNEL_BUILDERS
        # Updated to reflect all 9 channels (6 original + qq, email, imessage)
        expected = {
            "telegram", "feishu", "dingtalk", "discord", "slack", "wechat",
            "qq", "email", "imessage",
        }
        assert expected == set(CHANNEL_BUILDERS.keys())


# ═══════════════ Phase 5: New Channel Plugins ═══════════════


class TestDingTalkChannel:
    """Test DingTalk channel import and instantiation."""

    def test_import_and_create(self):
        from bot.channels.dingtalk import DingTalkChannel, DingTalkConfig
        config = DingTalkConfig(client_id="test_id", client_secret="test_secret")
        channel = DingTalkChannel(config)
        assert channel.name == "dingtalk"
        assert channel.capabilities.format_type == "markdown"

    def test_default_config(self):
        from bot.channels.dingtalk import DingTalkConfig
        cfg = DingTalkConfig()
        assert cfg.client_id == ""
        assert cfg.client_secret == ""
        assert cfg.text_chunk_limit == 4096


class TestDiscordChannel:
    """Test Discord channel import and instantiation."""

    def test_import_and_create(self):
        from bot.channels.discord import DiscordChannel, DiscordConfig
        config = DiscordConfig(bot_token="test_token")
        channel = DiscordChannel(config)
        assert channel.name == "discord"
        assert channel.capabilities.max_text_length == 2000

    def test_default_config(self):
        from bot.channels.discord import DiscordConfig
        cfg = DiscordConfig()
        assert cfg.bot_token == ""
        assert cfg.text_chunk_limit == 2000


class TestSlackChannel:
    """Test Slack channel import and instantiation."""

    def test_import_and_create(self):
        from bot.channels.slack import SlackChannel, SlackConfig
        config = SlackConfig(bot_token="xoxb-test", app_token="xapp-test")
        channel = SlackChannel(config)
        assert channel.name == "slack"
        # Slack uses its own mrkdwn format (not standard Markdown),
        # so format_type='plain' and markdown=False is intentional.
        assert channel.capabilities.format_type == "plain"
        assert channel.capabilities.reactions is True
        assert channel.capabilities.media_send is True

    def test_default_config(self):
        from bot.channels.slack import SlackConfig
        cfg = SlackConfig()
        assert cfg.bot_token == ""
        assert cfg.app_token == ""
        assert cfg.text_chunk_limit == 4096


class TestWeChatChannel:
    """Test WeChat channel import and instantiation."""

    def test_wecom_import_and_create(self):
        from bot.channels.wechat import WeChatChannel, WeComConfig
        config = WeComConfig(corp_id="corp", agent_id="1", secret="s")
        channel = WeChatChannel(config, backend="wecom")
        assert channel.name == "wechat"
        assert channel._backend == "wecom"

    def test_mp_import_and_create(self):
        from bot.channels.wechat import WeChatChannel, WeChatMPConfig
        config = WeChatMPConfig(app_id="app", app_secret="sec")
        channel = WeChatChannel(config, backend="wechatmp")
        assert channel.name == "wechat"
        assert channel._backend == "wechatmp"

    def test_xml_parser(self):
        from bot.channels.wechat import _parse_xml
        xml = (
            "<xml>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Hello]]></Content>"
            "<FromUserName><![CDATA[user1]]></FromUserName>"
            "</xml>"
        )
        result = _parse_xml(xml)
        assert result["MsgType"] == "text"
        assert result["Content"] == "Hello"
        assert result["FromUserName"] == "user1"

    def test_strip_markdown(self):
        from bot.channels.wechat import _strip_markdown
        assert _strip_markdown("**bold**") == "bold"
        assert _strip_markdown("`code`") == "code"
        assert "Title" in _strip_markdown("## Title")

    def test_default_wecom_config(self):
        from bot.channels.wechat import WeComConfig
        cfg = WeComConfig()
        assert cfg.corp_id == ""
        assert cfg.webhook_port == 9001



class TestChannelRegistryComplete:
    """Verify the channel registry has all 9 channels."""

    def test_registry_has_all_channels(self):
        from bot.channels import CHANNEL_REGISTRY
        expected = {
            "telegram", "feishu", "dingtalk", "discord", "slack", "wechat",
            "qq", "email", "imessage",
        }
        assert expected == set(CHANNEL_REGISTRY.keys()), (
            f"Registry mismatch. Got: {set(CHANNEL_REGISTRY.keys())}"
        )

    def test_dynamic_import_new_channels(self):
        from bot.channels import get_channel_class
        # Phase 5 channels
        assert get_channel_class("dingtalk").__name__ == "DingTalkChannel"
        assert get_channel_class("discord").__name__ == "DiscordChannel"
        assert get_channel_class("slack").__name__ == "SlackChannel"
        assert get_channel_class("wechat").__name__ == "WeChatChannel"
        # Phase 6 channels
        assert get_channel_class("qq").__name__ == "QQChannel"
        assert get_channel_class("email").__name__ == "EmailChannel"
        assert get_channel_class("imessage").__name__ == "IMessageChannel"

    def test_unknown_channel_raises(self):
        from bot.channels import get_channel_class
        with pytest.raises(KeyError, match="Unknown channel"):
            get_channel_class("nonexistent")


class TestRunnerParity:
    """Verify run.py CHANNEL_BUILDERS matches CHANNEL_REGISTRY."""

    def test_builders_match_registry(self):
        from bot.channels import CHANNEL_REGISTRY
        from bot.run import CHANNEL_BUILDERS
        assert set(CHANNEL_BUILDERS.keys()) == set(CHANNEL_REGISTRY.keys()), (
            "CHANNEL_BUILDERS and CHANNEL_REGISTRY are out of sync!"
        )


# ── Phase 6: QQ, Email, iMessage ─────────────────────────────────────


class TestQQChannel:
    """Tests for the QQ channel implementation."""

    def test_import_and_create(self):
        from bot.channels.qq import QQChannel, QQConfig
        config = QQConfig(app_id="test_id", app_secret="test_secret")
        channel = QQChannel(config)
        assert channel.name == "qq"
        assert channel.capabilities.format_type == "plain"
        assert channel.capabilities.groups is True
        assert channel.capabilities.media_send is True

    def test_default_config(self):
        from bot.channels.qq import QQConfig
        cfg = QQConfig()
        assert cfg.app_id == ""
        assert cfg.app_secret == ""
        assert cfg.text_chunk_limit == 4096

    def test_strip_markdown(self):
        from bot.channels.qq import _strip_markdown
        assert _strip_markdown("**bold**") == "bold"
        assert _strip_markdown("`code`") == "code"
        assert "Title" in _strip_markdown("## Title")

    def test_msg_seq_counter(self):
        from bot.channels.qq import QQChannel, QQConfig
        channel = QQChannel(QQConfig(app_id="x", app_secret="y"))
        # First call should return 1
        assert channel._next_msg_seq("msg1") == 1
        # Second call with same msg_id should increment
        assert channel._next_msg_seq("msg1") == 2
        # Different msg_id starts at 1 again
        assert channel._next_msg_seq("msg2") == 1


class TestEmailChannel:
    """Tests for the Email channel implementation."""

    def test_import_and_create(self):
        from bot.channels.email import EmailChannel, EmailConfig
        config = EmailConfig(
            imap_host="imap.gmail.com",
            imap_username="test@gmail.com",
            imap_password="apppassword",
            smtp_host="smtp.gmail.com",
            smtp_username="test@gmail.com",
            smtp_password="apppassword",
        )
        channel = EmailChannel(config)
        assert channel.name == "email"
        assert channel.capabilities.html is True
        assert channel.capabilities.media_send is True

    def test_default_config(self):
        from bot.channels.email import EmailConfig
        cfg = EmailConfig()
        assert cfg.imap_host == ""
        assert cfg.imap_port == 993
        assert cfg.smtp_port == 587
        assert cfg.smtp_starttls is True
        assert cfg.poll_interval == 30
        assert cfg.mark_seen is True
        assert cfg.max_body_chars == 12000

    def test_strip_html(self):
        from bot.channels.email import _strip_html
        html = "<p>Hello <b>world</b></p><br/>Line 2"
        plain = _strip_html(html)
        assert "Hello" in plain
        assert "world" in plain
        assert "<" not in plain

    def test_decode_hdr(self):
        from bot.channels.email import _decode_hdr
        # Basic passthrough for ASCII headers
        assert _decode_hdr("Hello World") == "Hello World"
        # Empty string
        assert _decode_hdr("") == ""

    def test_build_subject(self):
        from bot.channels.email import EmailChannel, EmailConfig
        ch = EmailChannel(EmailConfig(smtp_host="smtp.gmail.com", smtp_username="x@x.com"))
        assert ch._build_subject("") == "OmicsClaw Reply"
        assert ch._build_subject("My Analysis").startswith("Re: ")
        # Already has Re: prefix → pass through
        result = ch._build_subject("Re: Old Subject")
        assert result == "Re: Old Subject"


class TestIMessageChannel:
    """Tests for the iMessage channel implementation."""

    def test_import_and_create(self):
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        config = IMessageConfig(cli_path="imsg")
        channel = IMessageChannel(config)
        assert channel.name == "imessage"
        assert channel.capabilities.format_type == "plain"
        assert channel.capabilities.media_send is True
        assert channel.capabilities.voice is True

    def test_default_config(self):
        from bot.channels.imessage import IMessageConfig
        cfg = IMessageConfig()
        assert cfg.cli_path == "imsg"
        assert cfg.service == "auto"
        assert cfg.region == "US"
        assert cfg.text_chunk_limit == 4096

    def test_normalize_handle(self):
        from bot.channels.imessage import _normalize_handle
        # Full E.164 number passes through unchanged
        assert _normalize_handle("+16505551234") == "+16505551234"
        # Local US number: digits-only result contains the area code digits
        # (650) 555-1234  →  digits=6505551234  →  +6505551234
        result = _normalize_handle("(650) 555-1234")
        assert "650" in result
        assert "5551234" in result
        # Email lowercased
        assert _normalize_handle("User@iCloud.com") == "user@icloud.com"

    def test_is_sender_allowed_open(self):
        """Empty allowed_senders means allow all."""
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        ch = IMessageChannel(IMessageConfig(allowed_senders=None))
        assert ch._is_sender_allowed("+16505551234") is True

    def test_is_sender_allowed_wildcard(self):
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        ch = IMessageChannel(IMessageConfig(allowed_senders={"*"}))
        assert ch._is_sender_allowed("anyone@anywhere.com") is True

    def test_is_sender_blocked(self):
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        ch = IMessageChannel(IMessageConfig(allowed_senders={"+16505550001"}))
        assert ch._is_sender_allowed("+16505559999") is False

    def test_resolve_target_from_metadata(self):
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        ch = IMessageChannel(IMessageConfig())
        target = ch._resolve_target("fallback", {"chat_id": 42})
        assert target == {"chat_id": 42}

    def test_resolve_target_fallback(self):
        from bot.channels.imessage import IMessageChannel, IMessageConfig
        ch = IMessageChannel(IMessageConfig())
        target = ch._resolve_target("+16505551234", {})
        assert target == {"to": "+16505551234"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
