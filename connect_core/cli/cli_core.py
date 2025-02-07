import time
from connect_core.websocket.server import websocket_server_main
from connect_core.websocket.client import websocket_client_main
from connect_core.aes_encrypt import aes_main
from connect_core.plugin.init_plugin import init_plugin_main
from connect_core.interface.control_interface import CoreControlInterface
from connect_core.account.register_system import register_system_main
from connect_core.cli.commands import ServerCommand, ClientCommand
from connect_core.cli.command_core import CommandLineInterface

command_core = None

class Server(object):
    def __init__(self) -> None:
        global command_core
        self._control_interface = CoreControlInterface()
        command_core = CommandLineInterface(self._control_interface)
        command_core.start()
        self._control_interface.info(self._control_interface.tr("cli.starting.welcome"))
        register_system_main(self._control_interface)
        init_plugin_main(self._control_interface)

    def _running(self) -> None:
        """
        程序持续运行
        """
        try:
            self._control_interface.info("Program is running. Press Ctrl+C to exit.")
            ServerCommand(self._control_interface)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._control_interface.info("\nCtrl+C detected. Exiting gracefully.")

    # Public
    def start_servers(self) -> None:
        """
        创建并启动HTTP和WebSocket服务器的线程。
        """

        aes_main(self._control_interface)

        time.sleep(0.3)

        # 启动WebSocket服务器
        websocket_server_main(self._control_interface)

        self._running()


class Client(object):
    def __init__(self) -> None:
        global command_core
        self._control_interface = CoreControlInterface()
        command_core = CommandLineInterface(self._control_interface)
        command_core.start()
        _config = self._control_interface.get_config()
        self._control_interface.info(
            self._control_interface.tr(
                "cli.starting.welcome_password", _config["password"]
            )
        )

        init_plugin_main(self._control_interface)

    def _running(self) -> None:
        """
        程序持续运行
        """
        try:
            self._control_interface.info("Program is running. Press Ctrl+C to exit.")
            ClientCommand(self._control_interface)
            while True:
                time.sleep(1)  # 模拟程序的持续运行
        except KeyboardInterrupt:
            self._control_interface.info("\nCtrl+C detected. Exiting gracefully.")

    def start_server(self) -> None:
        """
        启动WebSocket客户端并初始化核心命令行程序。
        """

        aes_main(
            self._control_interface, self._control_interface.get_config("password")
        )
        # 启动WebSocket客户端
        websocket_client_main(self._control_interface)

        self._running()
