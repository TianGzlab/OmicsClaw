"""Unit tests for bot/core.py security helpers and utilities."""

import time
import pytest


# --- sanitize_filename ---

class TestSanitizeFilename:
    @pytest.fixture(autouse=True)
    def _import_core(self):
        """Lazy import to work with pytest importlib mode."""
        import bot.core as _core
        self.core = _core
        self.sanitize_filename = _core.sanitize_filename

    def test_normal_filename(self):
        assert self.sanitize_filename("data.h5ad") == "data.h5ad"

    def test_removes_directory_traversal(self):
        result = self.sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_removes_null_bytes(self):
        result = self.sanitize_filename("file\x00name.txt")
        assert "\x00" not in result

    def test_removes_backslashes(self):
        result = self.sanitize_filename("dir\\file.txt")
        assert "\\" not in result

    def test_empty_becomes_unnamed(self):
        assert self.sanitize_filename("") == "unnamed_file"

    def test_absolute_path_takes_basename(self):
        result = self.sanitize_filename("/absolute/path/file.h5ad")
        assert result == "file.h5ad"

    def test_preserves_extension(self):
        assert self.sanitize_filename("report.md").endswith(".md")


# --- validate_path ---

class TestValidatePath:
    @pytest.fixture(autouse=True)
    def _import_core(self):
        import bot.core as _core
        self.validate_path = _core.validate_path

    def test_valid_path(self, tmp_path):
        child = tmp_path / "subdir" / "file.txt"
        assert self.validate_path(child, tmp_path) is True

    def test_escape_blocked(self, tmp_path):
        outside = tmp_path / ".." / "escape"
        assert self.validate_path(outside, tmp_path) is False


# --- check_rate_limit ---

class TestRateLimit:
    @pytest.fixture(autouse=True)
    def _import_core(self):
        import bot.core as _core
        self.core = _core
        self.check_rate_limit = _core.check_rate_limit

    def test_allows_within_limit(self):
        old_limit = self.core.RATE_LIMIT_PER_HOUR
        self.core.RATE_LIMIT_PER_HOUR = 5
        self.core._rate_buckets.clear()
        try:
            for _ in range(5):
                assert self.check_rate_limit("test_user_rl") is True
            assert self.check_rate_limit("test_user_rl") is False
        finally:
            self.core.RATE_LIMIT_PER_HOUR = old_limit
            self.core._rate_buckets.pop("test_user_rl", None)

    def test_disabled_when_zero(self):
        old_limit = self.core.RATE_LIMIT_PER_HOUR
        self.core.RATE_LIMIT_PER_HOUR = 0
        try:
            assert self.check_rate_limit("any_user") is True
        finally:
            self.core.RATE_LIMIT_PER_HOUR = old_limit

    def test_admin_bypasses(self):
        old_limit = self.core.RATE_LIMIT_PER_HOUR
        self.core.RATE_LIMIT_PER_HOUR = 1
        self.core._rate_buckets.clear()
        try:
            assert self.check_rate_limit("admin1", admin_id="admin1") is True
            assert self.check_rate_limit("admin1", admin_id="admin1") is True
        finally:
            self.core.RATE_LIMIT_PER_HOUR = old_limit
            self.core._rate_buckets.pop("admin1", None)


# --- LRU conversation eviction ---

class TestConversationLRU:
    @pytest.fixture(autouse=True)
    def _import_core(self):
        import bot.core as _core
        self.core = _core
        self._evict_lru_conversations = _core._evict_lru_conversations

    def test_eviction_when_over_limit(self):
        orig_convs = dict(self.core.conversations)
        orig_access = dict(self.core._conversation_access)
        orig_max = self.core.MAX_CONVERSATIONS

        try:
            self.core.conversations.clear()
            self.core._conversation_access.clear()
            self.core.MAX_CONVERSATIONS = 3

            for i in range(5):
                self.core.conversations[f"chat_{i}"] = [{"role": "user", "content": "hi"}]
                self.core._conversation_access[f"chat_{i}"] = time.time() + i * 0.01

            self._evict_lru_conversations()

            assert len(self.core.conversations) == 3
            assert "chat_0" not in self.core.conversations
            assert "chat_1" not in self.core.conversations
            assert "chat_4" in self.core.conversations
        finally:
            self.core.conversations.clear()
            self.core.conversations.update(orig_convs)
            self.core._conversation_access.clear()
            self.core._conversation_access.update(orig_access)
            self.core.MAX_CONVERSATIONS = orig_max
