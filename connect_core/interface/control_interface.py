from __future__ import annotations

import json
from pathlib import Path
from logging import Logger
from typing import Any, Callable, Optional, TYPE_CHECKING

import structlog

try:
    from mcdreforged.api.all import PluginServerInterface
except ImportError:
    pass

from connect_core.log_system import LogSystem
from connect_core.context import GlobalContext
from connect_core.init_config import ServerConfig, ClientConfig
from connect_core.tools.base_config import BaseConfig
from connect_core.tools.self_read import YmlLanguage

if TYPE_CHECKING:
    from connect_core.cli.arguments import ArgumentSpec
    from connect_core.cli.command_core import CommandLineInterface


class CoreControlInterface(object):
    """核心控制接口"""

    def __init__(self) -> None:
        self.sid = "connect_core"

        self.self_path = GlobalContext.get_path()
        self.is_mcdr = GlobalContext.is_mcdr_mode()
        self.is_server = GlobalContext.is_server_mode()

        self.config_file = (
            ServerConfig.load(config_path=GlobalContext.get_config_path())
            if self.is_server
            else ClientConfig.load(config_path=GlobalContext.get_config_path())
        )
        self.language_file = YmlLanguage(
            path=self.self_path, sid=self.sid, lang=self.config_file.language
        )
        self.log_system = LogSystem(self.sid)
        self.command_control = self.CommandControl(self.sid)

    # ===== LogSystem =====
    @property
    def logger(self) -> Logger:
        """
        日志系统

        Returns:
            Logger: 日志控制器
        """
        return self.log_system.logger

    @property
    def struct_logger(self) -> structlog.stdlib.BoundLogger:
        """
        结构化日志系统

        Returns:
            structlog.stdlib.BoundLogger: 结构化日志控制器
        """
        return self.log_system.struct_logger

    # ===== Config =====
    @property
    def config(self) -> ServerConfig | ClientConfig:
        """
        配置文件

        Returns:
            ServerConfig | ClientConfig: 日志接口
        """
        return self.config_file

    def get_config(
        self,
        key: str = "all",
        default: Any | None = None,
        config_path: str | None = None,
    ) -> Any:
        """向后兼容旧版接口，返回主配置或辅助 JSON 配置文件。"""

        if config_path:
            target = self._resolve_auxiliary_config_path(config_path)
            if not target.exists():
                return {} if key in {"all", None} else default
            try:
                with target.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except json.JSONDecodeError:
                return {} if key in {"all", None} else default
            if key in {"all", None}:
                return data
            return data.get(key, default)

        config_model = self.config_file
        if key in {"all", None}:
            return {
                field: getattr(config_model, field) for field in config_model.__fields__
            }
        return getattr(config_model, key, default)

    def save_config(
        self,
        config_data: dict | BaseConfig,
        config_path: str | None = None,
    ) -> None:
        """保存主配置或辅助 JSON 配置。"""

        if isinstance(config_data, BaseConfig):
            config_data.save()
            return

        if config_path:
            target = self._resolve_auxiliary_config_path(config_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as fh:
                json.dump(config_data, fh, indent=4, ensure_ascii=False)
            return

        # 更新主配置字段
        for field in self.config_file.__fields__:
            if field in config_data:
                setattr(self.config_file, field, config_data[field])
        self.config_file.save()

    def info(self, msg: Any) -> None:
        self.logger.info(str(msg))

    def warn(self, msg: Any) -> None:
        self.logger.warning(str(msg))

    def warning(self, msg: Any) -> None:
        self.logger.warning(str(msg))

    def error(self, msg: Any) -> None:
        self.logger.error(str(msg))

    def debug(self, msg: Any, *, level: int = 1) -> None:
        if GlobalContext.get_debug_level() >= level:
            self.logger.debug(str(msg))

    def _resolve_auxiliary_config_path(self, filename: str) -> Path:
        base = Path(GlobalContext.get_path())
        try:
            if base.exists() and not base.is_dir():
                base = base.parent
        except OSError:
            base = base.parent
        return (base / "config" / "connect_core" / filename).resolve()

    # ===== Translate =====
    def translate(self, key: str, *args: Any) -> str:
        """
        获取翻译项

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
        return self.language_file.translate(key, *args)

    def tr(self, key: str, *args: Any) -> str:
        """
        获取翻译项 | `translate函数的别称`

        Args:
            key (str): 翻译文件关键字
            *args (tuple): 字段插入内容

        Returns:
            str: 翻译文本
        """
        return self.translate(key, *args)

    # ===== WebSocket =====
    def get_server_list(self) -> list:
        """
        获取服务器列表

        Returns:
            list: 服务器列表
        """
        if self.is_server:
            from connect_core.websockets.server import get_server_list

            return get_server_list()
        else:
            from connect_core.websockets.client import get_server_list

            return get_server_list()

    def get_server_id(self) -> str:
        """
        客户端反馈服务器ID

        Returns:
            str: 服务器ID
        """
        if self.is_server:
            return "-----"
        from connect_core.websockets.client import get_server_id

        return get_server_id() or "-----"

    def get_history_data_packet(self, server_id: str | None = None) -> list[Any]:
        """
        获取历史数据包

        Args:
            server_id: 服务器ID (服务端模式必填)

        Returns:
            list: 历史数据包列表
        """
        if self.is_server:
            from connect_core.websockets.server import get_history_data_packet

            return get_history_data_packet(server_id) if server_id else []  # type: ignore[return-value]
        else:
            from connect_core.websockets.client import get_history_data_packet  # type: ignore[assignment]

            return get_history_data_packet()  # type: ignore[return-value, call-arg]

    def get_recent_packets(self, limit: int = 20, server_id: str | None = None) -> list:
        """
        获取最近的数据包

        Args:
            limit: 返回数量上限
            server_id: 可选服务器ID筛选

        Returns:
            list: 数据包列表
        """
        if self.is_server:
            from connect_core.websockets.server import get_recent_packets

            return get_recent_packets(limit, server_id)
        else:
            from connect_core.websockets.client import get_recent_packets

            return get_recent_packets(limit, server_id)

    # ===== Command =====
    class CommandControl(object):
        def __init__(self, sid: str) -> None:
            self.sid = sid
            self._cli: CommandLineInterface | None = None

        def bind_cli(self, cli: CommandLineInterface) -> None:
            self._cli = cli

        def _ensure_cli(self) -> CommandLineInterface:
            if self._cli is None:
                raise RuntimeError("Command line interface is not initialized")
            return self._cli

        def add_command(
            self,
            command: str,
            func: Callable[..., None],
            *,
            argument_specs: Optional[list[ArgumentSpec]] = None,
            pass_context: bool = False,
        ) -> None:
            """
            添加命令到命令行界面中。

            Args:
                command (str): 命令名称。
                func (callable): 命令对应的函数。
            """
            self._ensure_cli().add_command(
                self.sid,
                command,
                func,
                argument_specs=argument_specs,
                pass_context=pass_context,
            )

        def remove_command(self, command: str) -> None:
            """
            移除命令从命令行界面中。

            Args:
                command (str): 命令名称。
            """
            self._ensure_cli().remove_command(self.sid, command)

        def set_prompt(self, prompt: str) -> None:
            """
            设置命令行提示符。

            Args:
                prompt (str): 命令行提示符内容。
            """
            self._ensure_cli().set_prompt(prompt)

        def set_completer_words(self, words: dict) -> None:
            """
            设置命令行补全词典。

            Args:
                words (dict): 命令行补全词典内容。
            """
            self._ensure_cli().set_completer_words(self.sid, words)

        def remove_sid(self, target_sid: str) -> None:
            """移除指定 sid 的所有命令及补全，并刷新终端。"""
            cli = self._ensure_cli()
            cli.remove_sid(target_sid)
            cli.flush_cli()

        def flush_cli(self) -> None:
            """
            刷新命令行补全词典。
            """
            self._ensure_cli().flush_cli()


class PluginControlInterface(CoreControlInterface):
    """插件控制接口"""

    def __init__(
        self,
        sid: str,
        self_path: str | None,
        config_file: BaseConfig | None,
        mcdr_core: PluginServerInterface | None = None,
    ) -> None:
        super().__init__()
        self.sid = sid
        self.self_path: Path | str = self_path or GlobalContext.get_path()  # type: ignore[assignment]
        self.config_file: ServerConfig | ClientConfig | BaseConfig = config_file or BaseConfig()  # type: ignore[assignment]
        self.mcdr_core = mcdr_core
        self.log_system = LogSystem(self.sid)
        # 兼容 config_file 既可能是 BaseConfig 实例（含 language 字段），也可能是
        # 未实例化的配置类或没有 language 字段的 BaseConfig 子类。
        plugin_lang = getattr(self.config_file, "language", None) or "en_us"
        self.language_file = YmlLanguage(path=self.self_path, sid=self.sid, lang=plugin_lang)
        self.command_control = self.CommandControl(self.sid)

    def send_data(self, server_id: str, plugin_id: str, data: dict) -> None:
        """
        向指定的服务器发送消息。

        Args:
            server_id: 目标服务器ID
            plugin_id: 目标插件ID
            data: 要发送的数据
        """
        if self.is_server:
            from connect_core.websockets.server import send_data as server_send_data

            server_send_data("-----", self.sid, server_id, plugin_id, data)
        else:
            from connect_core.websockets.client import send_data as client_send_data

            client_send_data(self.sid, server_id, plugin_id, data)

    def send_file(
        self, server_id: str, plugin_id: str, file_path: str, save_path: str
    ) -> None:
        """
        向指定的服务器发送文件。

        Args:
            server_id: 目标服务器ID
            plugin_id: 目标插件ID
            file_path: 要发送的文件路径
            save_path: 保存位置
        """
        if self.is_server:
            from connect_core.websockets.server import send_file as server_send_file

            server_send_file(
                "-----", self.sid, server_id, plugin_id, file_path, save_path
            )  # pyright: ignore[reportCallIssue]
        else:
            from connect_core.websockets.client import send_file as client_send_file

            client_send_file(
                self.sid, server_id, plugin_id, file_path, save_path
            )  # pyright: ignore[reportCallIssue]
