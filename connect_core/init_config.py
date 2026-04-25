from __future__ import annotations

import asyncio
import json
import re
from typing import NoReturn

import websockets

from connect_core.tools.base_config import BaseConfig, Field
from connect_core.context import GlobalContext
from connect_core.tools.self_read import YmlLanguage
from connect_core.account.login_system import analyze_password
from connect_core.aes_encrypt import aes_encrypt


class CliInitConfig(object):
    """初始化配置类"""

    _ANSI_MAP = {
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
    _RESET_CODE = "\x1b[0m"

    def __init__(self) -> None:
        if GlobalContext.get_config_path().exists():
            return
        try:
            self.lang = self._input("请输入语言 (zh_cn/en_us): ").strip()
            self.lang = self.lang if self.lang in ["zh_cn", "en_us"] else "en_us"
            self.language_file = YmlLanguage(
                path=GlobalContext.get_path(), sid="connect_core", lang=self.lang
            )
            self.server_mode = GlobalContext.is_server_mode()
            if self.server_mode:
                self._server_init()
            else:
                self._client_init()
        except KeyboardInterrupt:
            self._handle_keyboard_interrupt()

    def _server_init(self) -> None:
        """服务器模式的初始化配置"""
        self.ip, self.port = None, None
        while self.ip is None or self.port is None:
            if self.ip is None:
                self.ip = (
                    self._input(
                        self.language_file.translate(
                            "cli.initialization_config.enter_ip"
                        )
                    ).strip()
                    or "127.0.0.1"
                )
                if not re.match(
                    r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
                    self.ip,
                ):
                    self._print(
                        self.language_file.translate(
                            "cli.initialization_config.invalid_ip"
                        )
                    )
                    self.ip = None
                    continue
            if self.port is None:
                port_input = (
                    self._input(
                        self.language_file.translate(
                            "cli.initialization_config.enter_port"
                        )
                    ).strip()
                    or "23233"
                )
                if port_input.isdigit() and 0 <= int(port_input) <= 65535:
                    self.port = int(port_input)
                else:
                    self._print(
                        self.language_file.translate(
                            "cli.initialization_config.invalid_port"
                        )
                    )
                    self.port = None
                    continue
        self._save_config()

    def _client_init(self) -> None:
        """客户端模式的初始化配置"""
        self.last_ip, self.last_port = None, None
        while self.last_ip is None or self.last_port is None:
            key = self._input(
                self.language_file.translate("cli.initialization_config.enter_key")
            ).strip()
            data = analyze_password(key)
            if not data:
                self._print(
                    self.language_file.translate(
                        "cli.initialization_config.invalid_key"
                    )
                )
                continue
            ip_values = list(data["ip"].values())
            ip_list = [ip_values[0]]
            inside_ips = ip_values[1] if len(ip_values) > 1 else []
            if isinstance(inside_ips, (list, tuple)):
                ip_list.extend(inside_ips)
            ip_list.append(ip_values[-1])

            for candidate_ip in ip_list:
                url = f"ws://{candidate_ip}:{data['port']}"
                try:
                    reachable = asyncio.run(
                        self._check_websocket(url, data["password"])
                    )
                except KeyboardInterrupt:
                    self._handle_keyboard_interrupt()
                if reachable:
                    self.last_ip = candidate_ip
                    self.last_port = data["port"]
                    self.password = data["password"]
                    break

            if self.last_ip is not None:
                break

            self._print(
                self.language_file.translate(
                    "cli.initialization_config.cant_connect_iplist", ip_list
                )
            )
            ip = self._input(
                self.language_file.translate("cli.initialization_config.reenter_ip")
            ).strip()
            url = f"ws://{ip}:{data['port']}"
            try:
                reachable = asyncio.run(self._check_websocket(url, data["password"]))
            except KeyboardInterrupt:
                self._handle_keyboard_interrupt()
            if not reachable:
                self._print(
                    self.language_file.translate(
                        "cli.initialization_config.cant_connect_ip", ip
                    )
                )
                return
            self.last_ip = ip
            self.last_port = data["port"]
            self.password = data["password"]
        self._save_config()

    @staticmethod
    async def _check_websocket(server_uri: str, password: str | None = None) -> bool:
        """
        检查websocket服务器是否在线
        """
        from connect_core.websockets.data_packet import (
            PacketStore,
            PacketType,
            DEFAULT_TEMP,
        )

        try:
            async with websockets.connect(server_uri) as websocket:
                print(f"Connected to {server_uri} successfully!")
                if password:
                    packet_store = PacketStore()
                    packets = packet_store.create_packets(
                        PacketType.TEST_CONNECT,
                        DEFAULT_TEMP,
                        DEFAULT_TEMP,
                        None,
                    )
                    payload = packet_store.dump_mapping(packets)[DEFAULT_TEMP[0]]
                    encrypted = aes_encrypt(json.dumps(payload), password).decode()
                    message = json.dumps({"account": "-----", "data": encrypted})
                    await websocket.send(message)
                return True
        except Exception as e:
            print(f"Failed to connect to {server_uri}: {e}")
            return False

    def _save_config(self) -> None:
        """保存配置到文件"""
        config_path = GlobalContext.get_config_path()
        if self.server_mode:
            server_cfg = ServerConfig().load(config_path=config_path)
            server_cfg.language = self.lang
            assert self.ip is not None
            server_cfg.ip = self.ip
            assert self.port is not None
            server_cfg.port = self.port
            server_cfg.save()
        else:
            client_cfg = ClientConfig().load(config_path=config_path)
            client_cfg.language = self.lang
            assert self.last_ip is not None
            client_cfg.ip = self.last_ip
            assert self.last_port is not None
            client_cfg.port = self.last_port
            client_cfg.account = "-----"
            client_cfg.password = self.password
            client_cfg.save()
        self._print(self.language_file.translate("cli.initialization_config.finish"))

    def _print(self, message: str) -> None:
        print(self._colorize(message))

    def _input(self, prompt: str) -> str:
        try:
            return input(self._colorize(prompt))
        except KeyboardInterrupt:
            self._handle_keyboard_interrupt()
            raise  # unreachable but satisfies mypy

    def _colorize(self, text: str) -> str:
        if not isinstance(text, str) or "§" not in text:
            return text
        colored = text
        for code, ansi in self._ANSI_MAP.items():
            colored = colored.replace(code, ansi)
        if not colored.endswith(self._RESET_CODE):
            colored += self._RESET_CODE
        return colored

    def _handle_keyboard_interrupt(self) -> NoReturn:
        message = "\nInitialization cancelled by user."
        if hasattr(self, "language_file"):
            try:
                translated = self.language_file.translate(
                    "cli.initialization_config.cancelled"
                )
                if translated:
                    message = "\n" + translated
            except Exception:
                pass
        self._print(message)
        raise SystemExit(0)


class ServerConfig(BaseConfig):
    """服务器配置类"""

    language: str = Field("en_us", "语言 / Language [zh_cn/en_us]")
    ip: str = Field("127.0.0.1", "服务器IP地址 / Server IP Address")
    port: int = Field(23233, "服务器端口 / Server Port")
    rate_limit_enabled: bool = Field(True, "是否启用 WebSocket 消息速率限制 / Enable WebSocket rate limiting")
    rate_limit_max_requests: int = Field(120, "速率限制窗口内允许的最大消息数 / Max messages allowed per rate limit window")
    rate_limit_window_seconds: float = Field(60.0, "速率限制窗口秒数 / Rate limit window in seconds")
    healthcheck_enabled: bool = Field(True, "是否启用健康检查 HTTP 端点 / Enable HTTP health check endpoint")
    healthcheck_host: str = Field("127.0.0.1", "健康检查监听地址 / Health check bind host")
    healthcheck_port: int = Field(23234, "健康检查监听端口 / Health check bind port")
    plugin_sandbox_enabled: bool = Field(True, "是否启用插件导入沙箱 / Enable plugin import sandbox")
    max_packet_size: int = Field(
        64 * 1024 * 1024,
        "单个 WebSocket 消息最大字节数。0 表示不限制。默认 64 MiB。"
        " / Max bytes per WebSocket message; 0 means unlimited; default 64 MiB.",
    )


class ClientConfig(BaseConfig):
    """客户端配置类"""

    language: str = Field("en_us", "语言 / Language [zh_cn/en_us]")
    ip: str = Field("127.0.0.1", "服务器IP地址 / Server IP Address")
    port: int = Field(23233, "服务器端口 / Server Port")
    account: str = Field("", "账号 / Account")
    password: str = Field("", "密码 / Password")
    plugin_sandbox_enabled: bool = Field(True, "是否启用插件导入沙箱 / Enable plugin import sandbox")
    max_packet_size: int = Field(
        64 * 1024 * 1024,
        "单个 WebSocket 消息最大字节数。0 表示不限制。默认 64 MiB。"
        " / Max bytes per WebSocket message; 0 means unlimited; default 64 MiB.",
    )
