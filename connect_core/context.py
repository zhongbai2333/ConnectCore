from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from mcdreforged.api.all import PluginServerInterface
except ImportError:
    pass


@dataclass
class _ContextState:
    """内部数据类，持有所有运行时标志位。"""

    debug_mode: bool = False
    debug_level: int = 0
    server_mode: bool = False
    mcdr_mode: bool = False
    mcdr_core: Any = None


# 单例实例，由 GlobalContext.__init__ 写入
_state = _ContextState()


class GlobalContext(object):
    """全局上下文类

    内部状态由 _ContextState dataclass 持有，
    静态方法保持向后兼容，委托到 _state 实例。
    测试时可通过 GlobalContext.reset() 重置状态。
    """

    def __init__(
        self,
        debug: int | bool = False,
        server: bool = False,
        mcdr: bool = False,
        mcdr_interface: Optional[PluginServerInterface] = None,
    ):
        try:
            level = int(debug)
        except (TypeError, ValueError):
            level = 1 if debug else 0
        if isinstance(debug, bool):
            level = 1 if debug else 0
        if level < 0:
            level = 0

        _state.debug_level = level
        _state.debug_mode = level > 0
        _state.server_mode = server
        _state.mcdr_mode = mcdr
        _state.mcdr_core = mcdr_interface

    # ---- 测试辅助 ----
    @staticmethod
    def reset() -> None:
        """将全局状态重置为默认值（仅用于测试）。"""
        _state.debug_mode = False
        _state.debug_level = 0
        _state.server_mode = False
        _state.mcdr_mode = False
        _state.mcdr_core = None

    @staticmethod
    def get_state() -> _ContextState:
        """返回内部状态实例（仅用于测试或高级用途）。"""
        return _state

    # ---- 公共 API（静态方法，向后兼容） ----
    @staticmethod
    def is_debug_mode() -> bool:
        """检查是否处于调试模式"""
        return _state.debug_mode

    @staticmethod
    def get_debug_level() -> int:
        """获取调试等级，0 为关闭。"""
        return _state.debug_level

    @staticmethod
    def is_server_mode() -> bool:
        """检查是否处于服务器模式"""
        return _state.server_mode

    @staticmethod
    def is_mcdr_mode() -> bool:
        """检查是否处于MCDR模式"""
        return _state.mcdr_mode

    @staticmethod
    def get_mcdr_core() -> Any:
        """获取MCDR接口"""
        return _state.mcdr_core

    @staticmethod
    def get_path() -> Path:
        """获取当前脚本所在路径"""
        return Path(sys.path[0] if sys.path else "")

    @staticmethod
    def get_config_path() -> Path:
        """获取配置文件路径"""
        if GlobalContext.is_mcdr_mode():
            return Path(
                f"{GlobalContext.get_path().parent}/config/connect_core/config.yml"
            )
        else:
            return Path(f"{GlobalContext.get_path().parent}/config.yml")
