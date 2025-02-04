import re
import json
import asyncio
import websockets
from mcdreforged.api.all import *
from typing import TYPE_CHECKING

from connect_core.tools import restart_program
from connect_core.account.login_system import analyze_password
from connect_core.websocket.data_packet import DataPacket
from connect_core.tools import new_thread

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface


class CommandActions(object):
    def __init__(
        self, mcdr: PluginServerInterface, control_interface: "CoreControlInterface"
    ):
        self.__mcdr_server = mcdr
        self._control_interface = control_interface
        self.ip = None
        self.port = None
        self.key = None
        self.is_server = None
        self.password = None
        self.builder = SimpleCommandBuilder()
        if not self._control_interface.get_config():
            self.create_init_command()
        else:
            self.create_normal_command()

    def create_init_command(self):
        self.builder.command("!!connectcore", self._handle_init)
        self.builder.command("!!connectcore init", self._handle_init)
        self.builder.command("!!connectcore mode <server|client>", self._handle_mode)

        self.builder.command("!!connectcore ip <ip>", self._handle_ip)
        self.builder.command("!!connectcore port <port>", self._handle_port)

        self.builder.command("!!connectcore key <key>", self._handle_key)

        self.builder.arg("ip", Text)
        self.builder.arg("port", Integer)

        self.builder.arg("key", Text)

        self.builder.arg("server|client", Text)

        self.builder.register(self.__mcdr_server)

        self.__mcdr_server.register_help_message(
            "!!connectcore init", "初始化ConnectCore插件"
        )

    def create_normal_command(self):
        self._control_interface.debug("Creating normal command")
        self.builder.command("!!connectcore", self._handle_help)
        self.builder.command("!!connectcore help", self._handle_help)
        self.builder.command("!!connectcore list", self._handle_list)

        if self._control_interface.is_server():
            self.builder.command("!!connectcore getkey", self._handle_getkey)
        else:
            self.builder.command("!!connectcore info", self._handle_info)

        self.builder.register(self.__mcdr_server)

        self.__mcdr_server.register_help_message(
            "!!connectcore", "初始化ConnectCore插件"
        )

    def _handle_init(self, source: CommandSource, context: CommandContext):
        self._control_interface.info(
            self._control_interface.tr("mcdr.enter_server_or_client")
        )

    def _handle_help(self, source: CommandSource, context: CommandContext):
        if self._control_interface.is_server():
            self._control_interface.info(self._control_interface.tr("commands.server_help"))
        else:
            self._control_interface.info(self._control_interface.tr("commands.client_help"))

    def _handle_list(self, source: CommandSource, context: CommandContext):
        self._control_interface.info("==list==")
        for num, key in enumerate(self._control_interface.get_server_list()):
            self._control_interface.info(f"{num + 1}. {key}")

    def _handle_getkey(self, source: CommandSource, context: CommandContext):
        from connect_core.account.register_system import get_password

        self._control_interface.info(
            self._control_interface.tr("cli.starting.welcome_password", get_password())
        )

    def _handle_info(self, source: CommandSource, context: CommandContext):
        self._control_interface.info("==info==")
        server_id = self._control_interface.get_server_id()
        if server_id:
            self._control_interface.info(f"Main Server Connected! Server ID: {server_id}")
        else:
            self._control_interface.info("Main Server Disconnected!")

    def _handle_mode(self, source: CommandSource, context: CommandContext):
        if str(context["server|client"]).lower() == "server":
            self._control_interface.info(self._control_interface.tr("mcdr.enter_ip"))
            self.is_server = True
        elif str(context["server|client"]).lower() == "client":
            self._control_interface.info(self._control_interface.tr("mcdr.enter_key"))
            self.is_server = False
        else:
            self.is_server = None
            self._control_interface.error(
                self._control_interface.tr(
                    "mcdr.command_not_found", str(context["server|client"])
                )
            )

    def _handle_ip(self, source: CommandSource, context: CommandContext):
        if self.is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return
        if self.is_server:
            self.ip = str(context["ip"])
            if not re.match(
                r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
                self.ip,
            ):
                self._control_interface.error(
                    self._control_interface.tr("mcdr.invalid_ip")
                )
                self.ip = None
                return
            self._control_interface.info(self._control_interface.tr("mcdr.enter_port"))
        elif not self.is_server and self.port:
            self.ip = str(context["ip"])
            if not re.match(
                r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
                self.ip,
            ):
                self._control_interface.error(
                    self._control_interface.tr("mcdr.invalid_ip")
                )
                self.ip = None
                return
            url = f"ws://{self.ip}:{self.port}"
            if not asyncio.run(self.check_websocket(url)):
                print(
                    f"Error: Can't Visit Server! {self.ip}, please check the IP address."
                )
                return
            config = {
                "is_server": self.is_server,
                "account": "-----",
                "password": self.password,
                "ip": self.ip,
                "port": self.port,
                "debug": False,
            }
            self._control_interface.save_config(config)
            self._control_interface.info(self._control_interface.tr("mcdr.finish"))
            restart_program()
        else:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_key_frist")
            )

    def _handle_port(self, source: CommandSource, context: CommandContext):
        if self.is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return
        if not self.ip:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_ip_first")
            )
            return
        self.port = int(context["port"])
        if not (0 <= self.port <= 65535):
            self._control_interface.error(
                self._control_interface.tr("mcdr.invalid_port")
            )
            self.port = None
            return
        config = {
            "is_server": self.is_server,
            "ip": self.ip,
            "port": self.port,
            "debug": False,
        }
        self._control_interface.save_config(config)
        self._control_interface.info(self._control_interface.tr("mcdr.finish"))
        restart_program()

    @new_thread("Check Key")
    def _handle_key(self, source: CommandSource, context: CommandContext):
        if self.is_server is None:
            self._control_interface.warn(
                self._control_interface.tr("mcdr.enter_server_or_client_first")
            )
            return
        self.key = context["key"]
        data = analyze_password(self.key)
        ip_list = [list(data["ip"].values())[0]]
        for i in list(data["ip"].values())[1]:
            ip_list.append(i)
        ip_list.append(list(data["ip"].values())[-1])
        for ip in ip_list:
            url = f"ws://{ip}:{data['port']}"
            if asyncio.run(self.check_websocket(url)):
                last_ip = ip
                break
        else:
            print(f"Error: Can't Visit Server! {ip_list}")
            self.port = data["port"]
            self.password = data["password"]
            self._control_interface.info(self._control_interface.tr("mcdr.enter_ip"))
            return
        config = {
            "is_server": self.is_server,
            "account": "-----",
            "password": data["password"],
            "ip": last_ip,
            "port": data["port"],
            "debug": False,
        }
        self._control_interface.save_config(config)
        self._control_interface.info(self._control_interface.tr("mcdr.finish"))
        restart_program()

    async def check_websocket(self, server_uri) -> bool:
        """
        检查websocket服务器是否在线
        """
        try:
            async with websockets.connect(server_uri) as websocket:
                print(f"Connected to {server_uri} successfully!")
                data_packet = DataPacket()
                # 可以发送和接收消息以进一步测试
                await websocket.send(
                    json.dumps(
                        data_packet.get_data_packet(
                            data_packet.TYPE_TEST_CONNECT,
                            data_packet.DEFAULT_TO_FROM,
                            data_packet.DEFAULT_TO_FROM,
                            None,
                        )["-----"]
                    )
                )
                response = await websocket.recv()
                if json.loads(response)["type"] == list(data_packet.TYPE_TEST_CONNECT):
                    return True
                return False
        except Exception as e:
            print(f"Failed to connect to {server_uri}: {e}")
            return False
