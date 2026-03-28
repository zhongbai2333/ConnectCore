from __future__ import annotations

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, TextIO

import structlog

try:
    from mcdreforged.api.all import PluginServerInterface
except ImportError:
    pass

from connect_core.context import GlobalContext


class MCColorFormatter(logging.Formatter):
    RESET_CODE = "\x1b[0m"
    ANSI_MAP = {
        "§0": "\x1b[30m",
        "§1": "\x1b[34m",
        "§2": "\x1b[32m",
        "§3": "\x1b[36m",
        "§4": "\x1b[31m",
        "§5": "\x1b[35m",
        "§6": "\x1b[33m",
        "§7": "\x1b[37m",
        "§8": "\x1b[90m",
        "§9": "\x1b[94m",
        "§a": "\x1b[92m",
        "§b": "\x1b[96m",
        "§c": "\x1b[91m",
        "§d": "\x1b[95m",
        "§e": "\x1b[93m",
        "§f": "\x1b[97m",
        "§r": "\x1b[0m",
    }
    LEVEL_MC_MAP = {
        "DEBUG": "§1",  # 深蓝
        "INFO": "§a",  # 绿
        "WARNING": "§e",  # 黄
        "ERROR": "§c",  # 红
        "CRITICAL": "§4",  # 深红
    }

    def format(self, record: logging.LogRecord) -> str:
        # 1) 给 levelname 加上 MC 颜色代码
        mc = self.LEVEL_MC_MAP.get(record.levelname, "")
        if mc:
            record.levelname = f"{mc}{record.levelname}§r"

        # 2) 用父类生成带占位符的字符串
        msg = super().format(record)

        # 3) 全文替换 MC 代码到 ANSI
        for mc_code, ansi in self.ANSI_MAP.items():
            msg = msg.replace(mc_code, ansi)
        # 确保以 RESET 结尾
        if not msg.endswith(self.RESET_CODE):
            msg += self.RESET_CODE
        return msg


def configure_structlog(*, is_mcdr: bool = False) -> None:
    """
    配置 structlog 处理器链，使其输出通过 stdlib logging 后端。

    在 MCDR 模式下使用简化的处理器链（MCDR 自行管理日志格式），
    否则使用完整的结构化处理器链。

    此函数是幂等的，可安全重复调用。
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_mcdr:
        # MCDR 拥有自己的日志格式化，仅做最小处理
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(
            colors=False
        )
    else:
        # 非 MCDR：通过 stdlib logging 输出，格式由 handler 控制
        renderer = structlog.stdlib.ProcessorFormatter.wrap_for_formatter

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class LogSystem:
    _structlog_configured: bool = False

    def __init__(
        self,
        sid: str,
        filelog: Optional[str] = None,
        path: str = "logs/",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        mcdr_core: Optional[PluginServerInterface] = None,
    ) -> None:
        """
        使用 structlog + Python 内置 logging，支持文件滚动与 Minecraft § 风格片段着色。
        """
        os.makedirs(path, exist_ok=True)

        if not filelog:
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
            filelog = f"{sid}-{timestamp}.log"
        logfile_path = os.path.join(path, filelog)

        self.mcdr_core = mcdr_core if mcdr_core else GlobalContext.get_mcdr_core()
        self.sid = sid
        level = logging.DEBUG if GlobalContext.is_debug_mode() else logging.INFO

        # ── 配置 structlog（仅首次） ──
        if not LogSystem._structlog_configured:
            configure_structlog(is_mcdr=bool(self.mcdr_core))
            LogSystem._structlog_configured = True

        # ── stdlib logger（文件 + 控制台） ──
        stdlib_logger = logging.getLogger(sid)
        stdlib_logger.setLevel(level)
        stdlib_logger.propagate = False

        file_handler = RotatingFileHandler(
            logfile_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        fmt = "(%(threadName)s) [%(asctime)s] [%(levelname)s] " "[%(name)s] %(message)s"
        datefmt = "%H:%M:%S"
        file_formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
        file_handler.setFormatter(file_formatter)

        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_formatter = MCColorFormatter(fmt=fmt, datefmt=datefmt)
        console_handler.setFormatter(console_formatter)

        self._console_handler: Optional[logging.StreamHandler] = console_handler
        self._initial_console_stream: Optional[TextIO] = sys.stdout
        self._console_stream: Optional[TextIO] = sys.stdout

        stdlib_logger.handlers.clear()
        stdlib_logger.addHandler(file_handler)
        stdlib_logger.addHandler(console_handler)

        self._logger = stdlib_logger

        # ── structlog bound logger ──
        self._bound_logger: structlog.stdlib.BoundLogger = structlog.get_logger(sid)

    @property
    def logger(self) -> logging.Logger:
        """
        根据 mcdr_core 的存在与否，返回对应的 logger。
        返回 stdlib Logger 以保持向后兼容。
        """
        if self.mcdr_core:
            return self.mcdr_core.logger
        else:
            return self._logger

    @property
    def struct_logger(self) -> structlog.stdlib.BoundLogger:
        """
        返回 structlog BoundLogger，支持结构化日志输出。

        使用示例::

            log = control_interface.struct_logger
            log.info("user.login", user_id="abc", ip="1.2.3.4")
        """
        return self._bound_logger

    def set_console_stream(self, stream: TextIO) -> None:
        """
        更新控制台日志输出流，用于与 prompt_toolkit 等重定向配合。

        Args:
            stream (TextIO): 新的输出流。
        """
        if self.mcdr_core:
            return
        if self._console_handler is not None:
            self._console_handler.setStream(stream)
            self._console_stream = stream

    def restore_console_stream(self) -> None:
        """
        恢复控制台日志输出流到初始化时的流。
        """
        if self.mcdr_core:
            return
        if (
            self._console_handler is not None
            and self._initial_console_stream is not None
        ):
            self._console_handler.setStream(self._initial_console_stream)
            self._console_stream = self._initial_console_stream

    def get_console_stream(self) -> Optional[TextIO]:
        if self.mcdr_core:
            return None
        return self._console_stream

    def _log_msg(self, level: str, *msg: str) -> None:
        text = "".join(msg)
        if self.mcdr_core:
            if level.upper() == "DEBUG":
                self.mcdr_core.logger.info(f"[§1DEBUG§r] {text}")
            else:
                getattr(self.mcdr_core.logger, level.lower())(text)
        else:
            getattr(self.logger, level.lower())(text)

    @classmethod
    def reset_structlog_configuration(cls) -> None:
        """重置 structlog 配置标记，仅用于测试。"""
        cls._structlog_configured = False
        structlog.reset_defaults()
