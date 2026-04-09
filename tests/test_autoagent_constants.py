"""Tests for omicsclaw.autoagent.constants — shared utilities."""

from __future__ import annotations

import pytest

from omicsclaw.autoagent.constants import parse_bool, param_to_cli_flag


class TestParseBool:
    """parse_bool correctly handles string representations."""

    @pytest.mark.parametrize("value", [True, 1, "true", "True", "yes", "1", "on"])
    def test_truthy_values(self, value):
        assert parse_bool(value) is True

    @pytest.mark.parametrize("value", [False, 0, "false", "False", "no", "0", "off", "none", ""])
    def test_falsy_values(self, value):
        assert parse_bool(value) is False

    def test_non_empty_string_truthy(self):
        assert parse_bool("anything") is True

    def test_whitespace_stripped(self):
        assert parse_bool("  false  ") is False
        assert parse_bool("  true  ") is True


class TestParamToCliFlag:
    """param_to_cli_flag converts underscore names to CLI flags."""

    def test_basic_conversion(self):
        assert param_to_cli_flag("harmony_theta") == "--harmony-theta"

    def test_single_word(self):
        assert param_to_cli_flag("theta") == "--theta"

    def test_multiple_underscores(self):
        assert param_to_cli_flag("max_mt_pct") == "--max-mt-pct"

    def test_no_underscore(self):
        assert param_to_cli_flag("resolution") == "--resolution"
