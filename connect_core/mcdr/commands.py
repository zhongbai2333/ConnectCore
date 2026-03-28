import re
import json
import asyncio
import websockets
from mcdreforged.api.all import (
    SimpleCommandBuilder,
    PluginServerInterface,
    CommandSource,
    CommandContext,
    Text,
    Integer,
)
from typing import TYPE_CHECKING

from connect_core.context import GlobalContext
from connect_core.tools.tools import new_thread, restart_program
from connect_core.account.login_system import analyze_password
from connect_core.aes_encrypt import aes_encrypt

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface


class CommandActions(object):
    def __init__(
        self, mcdr: PluginServerInterface, control_interface: "CoreControlInterface"
    ):
        self.__mcdr_server = mcdr
        self._control_interface = control_interface
        self.ip: str | None = None
        self.port: int | None = None
        self.key: str | None = None
        self._is_server: bool | None = None
        self.password: str | None = None
        self.builder = SimpleCommandBuilder()

        if not GlobalContext.get_config_path().exists():
            self.create_init_command()
        else:
            self.permission = self._control_interface.get_config("permission", {})
            self.create_normal_command()

    def create_init_command(self) -> None:
        self.builder.command("!!connectcore", self._handle_init)
        self.builder.command("!!connectcore init", self._handle_init)
        self.builder.command("!!connectcore mode <server|client>", self._handle_mode)

        self.builder.command("!!connectcore ip <ip>", self._handle_ip)
        self.builder.command("!!connectcore port <port>", self._handle_port)

        self.builder.command(
            "!!connectcore key <key>",
            self._handle_key,  # pyright: ignore[reportArgumentType]
        )

        self.builder.arg("ip", Text)
        self.builder.arg("port", Integer)
        self.builder.arg("key", Text)
        self.builder.arg("server|client", Text)

        self.builder.register(self.__mcdr_server)

        self.__mcdr_server.register_help_message(
            "!!connectcore init", "初始化ConnectCore插件"
        )

    def create_normal_command(self) -> None:
        self._control_interface.debug("Creating normal command")
        self.builder.command("!!connectcore", self._handle_help)
        self.builder.command("!!connectcore help", self._handle_help)
        self.builder.command("!!connectcore list", self._handle_list)

        if self._control_interface.is_server:
            self.builder.command("!!connectcore getkey", self._handle_getkey)
        else:
            self.builder.command("!!connectcore info", self._handle_info)

        self.builder.register(self.__mcdr_server)

        self.__mcdr_server.register_help_message("!!connectcore", "ConnectCore插件")

    # ===== Init Command Handlers =====

    def _handle_init(self, source: CommandSource, context: CommandContext) -> None:
        self._control_interface.info(
            self._control_interface.tr("mcdr.enter_server_or_client")
        )

    def _handle_mode(self, source: CommandSource, context: CommandContext) -> None:
        mode = str(context["server|client"]).lower()
        if mode == "server":
            self._is_server = True
            self._control_interface.info(self._control_interface.tr("mcdr.enter_ip"))
        elif mode == "client":
            self._is_server = False
            self._control_interface.info(self._control_interface.tr("mcdr.enter_key"))
        else:
            self._is_server = None
            self._control_interface.error(
                self._control_interface.tr("mcdr.command_not_found", mode)
            )

    def _handle_ip(self, source: CommandSource, context: CommandContext) -> None:
        if self._is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return

        ip = str(context["ip"])
        if not re.match(
            r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
            r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
            ip,
        ):
            self._control_interface.error(self._control_interface.tr("mcdr.invalid_ip"))
            return

        if self._is_server:
            self.ip = ip
            self._control_interface.info(self._control_interface.tr("mcdr.enter_port"))
        elif self.port:
            # 客户端模式：已有端口，尝试连接
            url = f"ws://{ip}:{self.port}"
            if not asyncio.run(self._check_websocket(url, self.password)):
                self._control_interface.error(f"Error: Can't visit server at {ip}!")
                return
            self.ip = ip
            self._save_client_config()
            self._control_interface.info(self._control_interface.tr("mcdr.finish"))
            restart_program()
        else:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_key_first")
            )

    def _handle_port(self, source: CommandSource, context: CommandContext) -> None:
        if self._is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return
        if not self.ip:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_ip_first")
            )
            return

        port = int(context["port"])
        if not (0 <= port <= 65535):
            self._control_interface.error(
                self._control_interface.tr("mcdr.invalid_port")
            )
            return

        self.port = port
        self._save_server_config()
        self._control_interface.info(self._control_interface.tr("mcdr.finish"))
        restart_program()

    @new_thread("Check Key")
    def _handle_key(self, source: CommandSource, context: CommandContext) -> None:
        if self._is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return

        self.key = context["key"]
        data = analyze_password(self.key)  # pyright: ignore[reportArgumentType]
        if data is None:
            self._control_interface.error("Failed to analyze password")
            return

        ip_list = [list(data["ip"].values())[0]]
        for i in list(data["ip"].values())[1]:
            ip_list.append(i)
        ip_list.append(list(data["ip"].values())[-1])

        last_ip = None
        for ip in ip_list:
            url = f"ws://{ip}:{data['port']}"
            if asyncio.run(self._check_websocket(url, data["password"])):
                last_ip = ip
                break

        if last_ip is None:
            self._control_interface.error(
                f"Error: Can't visit server! Tried: {ip_list}"
            )
            self.port = data["port"]
            self.password = data["password"]
            self._control_interface.info(self._control_interface.tr("mcdr.enter_ip"))
            return

        self.ip = last_ip
        self.port = data["port"]
        self.password = data["password"]
        self._save_client_config()
        self._control_interface.info(self._control_interface.tr("mcdr.finish"))
        restart_program()

    # ===== Normal Command Handlers =====

    def _handle_help(self, source: CommandSource, context: CommandContext) -> None:
        if not source.has_permission_higher_than(self.permission.get("help", 0)):
            source.reply(
                self._control_interface.tr(
                    "commands.need_permission", self.permission.get("help", 0)
                )
            )
            return
        if self._control_interface.is_server:
            source.reply(self._control_interface.tr("commands.server_help"))
        else:
            source.reply(self._control_interface.tr("commands.client_help"))

    def _handle_list(self, source: CommandSource, context: CommandContext) -> None:
        if not source.has_permission_higher_than(self.permission.get("list", 0)):
            source.reply(
                self._control_interface.tr(
                    "commands.need_permission", self.permission.get("list", 0)
                )
            )
            return
        source.reply("==list==")
        try:
            for num, key in enumerate(self._control_interface.get_server_list()):
                source.reply(f"{num + 1}. {key}")
        except AttributeError:
            source.reply("Server list not available yet.")

    def _handle_getkey(self, source: CommandSource, context: CommandContext) -> None:
        if not source.has_permission_higher_than(self.permission.get("getkey", 0)):
            source.reply(
                self._control_interface.tr(
                    "commands.need_permission", self.permission.get("getkey", 0)
                )
            )
            return
        from connect_core.account.register_system import get_password

        source.reply(
            self._control_interface.tr("cli.starting.password", get_password())
        )

    def _handle_info(self, source: CommandSource, context: CommandContext) -> None:
        if not source.has_permission_higher_than(self.permission.get("info", 0)):
            source.reply(
                self._control_interface.tr(
                    "commands.need_permission", self.permission.get("info", 0)
                )
            )
            return
        source.reply("==info==")
        try:
            server_id = self._control_interface.get_server_id()
            if server_id:
                source.reply(f"Main Server Connected! Server ID: {server_id}")
            else:
                source.reply("Main Server Disconnected!")
        except AttributeError:
            source.reply("Server info not available yet.")

    # ===== Utility Methods =====

    @staticmethod
    async def _check_websocket(server_uri: str, password: str | None = None) -> bool:
        from connect_core.websockets.data_packet import (
            PacketStore,
            PacketType,
            DEFAULT_TEMP,
        )

        try:
            async with websockets.connect(server_uri) as websocket:
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

    def _save_server_config(self) -> None:
        from connect_core.init_config import ServerConfig

        config_path = GlobalContext.get_config_path()
        config = ServerConfig().load(config_path=config_path)
        config.language = "zh_cn"
        config.ip = self.ip  # type: ignore[assignment]
        config.port = self.port  # type: ignore[assignment]
        config.save()

        # 保存权限配置到辅助文件
        self._control_interface.save_config(
            {"permission": {"help": 0, "list": 2, "getkey": 3}},
            config_path="permission.json",
        )

    def _save_client_config(self) -> None:
        from connect_core.init_config import ClientConfig

        config_path = GlobalContext.get_config_path()
        config = ClientConfig().load(config_path=config_path)
        config.language = "zh_cn"
        config.ip = self.ip  # type: ignore[assignment]
        config.port = self.port  # type: ignore[assignment]
        config.account = "-----"
        config.password = self.password  # type: ignore[assignment]
        config.save()

        # 保存权限配置到辅助文件
        self._control_interface.save_config(
            {"permission": {"help": 0, "list": 2, "info": 2}},
            config_path="permission.json",
        )
