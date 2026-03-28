"""Tests for connect_core.log_system — structlog integration."""

from __future__ import annotations

import io
import logging
import os
from unittest.mock import MagicMock, patch

import pytest
import structlog

from connect_core.log_system import (
    LogSystem,
    MCColorFormatter,
    configure_structlog,
)


@pytest.fixture(autouse=True)
def _reset_structlog():
    """在每个测试前后重置 structlog 配置。"""
    LogSystem.reset_structlog_configuration()
    yield
    LogSystem.reset_structlog_configuration()


@pytest.fixture()
def log_system(tmp_path):
    """创建一个带临时日志目录的 LogSystem 实例。"""
    with patch("connect_core.log_system.GlobalContext") as mock_ctx:
        mock_ctx.get_mcdr_core.return_value = None
        mock_ctx.is_debug_mode.return_value = False
        ls = LogSystem("test-sid", path=str(tmp_path / "logs"))
    return ls


# ── MCColorFormatter ──


class TestMCColorFormatter:
    def test_format_adds_ansi_color_for_info(self):
        formatter = MCColorFormatter(fmt="%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        # INFO 级别应映射到 §a → \x1b[92m
        assert "\x1b[92m" in formatted
        assert formatted.endswith("\x1b[0m")

    def test_format_replaces_mc_codes_in_message(self):
        formatter = MCColorFormatter(fmt="%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="§1blue§r normal",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert "\x1b[34m" in formatted  # §1 → blue
        assert "\x1b[0m" in formatted  # §r → reset

    def test_all_level_colors_mapped(self):
        for level_name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert level_name in MCColorFormatter.LEVEL_MC_MAP


# ── configure_structlog ──


class TestConfigureStructlog:
    def test_configure_non_mcdr(self):
        configure_structlog(is_mcdr=False)
        logger = structlog.get_logger("test-configure")
        assert logger is not None

    def test_configure_mcdr(self):
        configure_structlog(is_mcdr=True)
        logger = structlog.get_logger("test-configure-mcdr")
        assert logger is not None


# ── LogSystem ──


class TestLogSystem:
    def test_creates_log_directory(self, tmp_path):
        log_dir = tmp_path / "new_logs"
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = False
            LogSystem("test", path=str(log_dir))
        assert log_dir.exists()

    def test_creates_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = False
            LogSystem("test", filelog="test.log", path=str(log_dir))
        assert (log_dir / "test.log").exists()

    def test_logger_property_returns_stdlib_logger(self, log_system):
        assert isinstance(log_system.logger, logging.Logger)
        assert log_system.logger.name == "test-sid"

    def test_logger_property_returns_mcdr_logger_when_set(self, tmp_path):
        mock_mcdr = MagicMock()
        mock_mcdr.logger = MagicMock()
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = False
            ls = LogSystem("test", path=str(tmp_path / "logs"), mcdr_core=mock_mcdr)
        assert ls.logger is mock_mcdr.logger

    def test_struct_logger_returns_bound_logger(self, log_system):
        sl = log_system.struct_logger
        assert sl is not None
        # structlog bound loggers have bind() method
        assert callable(getattr(sl, "bind", None))

    def test_struct_logger_can_log(self, log_system):
        """验证 struct_logger 可以成功调用 info 方法而不报错。"""
        sl = log_system.struct_logger
        # 不应抛出异常
        sl.info("test.event", key="value")

    def test_debug_mode_sets_debug_level(self, tmp_path):
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = True
            ls = LogSystem("debug-test", path=str(tmp_path / "logs"))
        assert ls.logger.level == logging.DEBUG

    def test_info_mode_sets_info_level(self, log_system):
        assert log_system.logger.level == logging.INFO


# ── Stream redirection ──


class TestStreamRedirection:
    def test_set_console_stream(self, log_system):
        new_stream = io.StringIO()
        log_system.set_console_stream(new_stream)
        assert log_system.get_console_stream() is new_stream

    def test_restore_console_stream(self, log_system):
        original = log_system.get_console_stream()
        new_stream = io.StringIO()
        log_system.set_console_stream(new_stream)
        log_system.restore_console_stream()
        assert log_system.get_console_stream() is original

    def test_mcdr_mode_stream_noop(self, tmp_path):
        mock_mcdr = MagicMock()
        mock_mcdr.logger = MagicMock()
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = False
            ls = LogSystem("test", path=str(tmp_path / "logs"), mcdr_core=mock_mcdr)

        assert ls.get_console_stream() is None
        ls.set_console_stream(io.StringIO())  # should be no-op
        assert ls.get_console_stream() is None
        ls.restore_console_stream()  # should be no-op
        assert ls.get_console_stream() is None


# ── _log_msg ──


class TestLogMsg:
    def test_log_msg_info(self, log_system):
        with patch.object(log_system.logger, "info") as mock_info:
            log_system._log_msg("info", "hello ", "world")
            mock_info.assert_called_once_with("hello world")

    def test_log_msg_mcdr_debug_becomes_info(self, tmp_path):
        mock_mcdr = MagicMock()
        mock_logger = MagicMock()
        mock_mcdr.logger = mock_logger
        with patch("connect_core.log_system.GlobalContext") as mock_ctx:
            mock_ctx.get_mcdr_core.return_value = None
            mock_ctx.is_debug_mode.return_value = False
            ls = LogSystem("test", path=str(tmp_path / "logs"), mcdr_core=mock_mcdr)

        ls._log_msg("debug", "test message")
        mock_logger.info.assert_called_once_with("[§1DEBUG§r] test message")


# ── reset_structlog_configuration ──


class TestResetStructlog:
    def test_reset_clears_flag(self):
        LogSystem._structlog_configured = True
        LogSystem.reset_structlog_configuration()
        assert LogSystem._structlog_configured is False
