import time
import threading
from connect_core.http.server import http_main
from connect_core.websocket.server import websocket_server_main
from connect_core.websocket.client import websocket_client_main
from connect_core.aes_encrypt import aes_main
from connect_core.plugin.init_plugin import init_plugin_main
from connect_core.plugin.init_plugin import get_plugins
from connect_core.interface.control_interface import CoreControlInterface
from connect_core.account.register_system import register_system_main, get_password

_control_interface = CoreControlInterface()
_config = _control_interface.get_config()


class Server(object):
    def __init__(self) -> None:
        _control_interface.info(_control_interface.tr("cli.starting.welcome"))
        register_system_main(_control_interface)
        init_plugin_main(_control_interface)

    def _running(self) -> None:
        """
        程序持续运行
        """
        try:
            _control_interface.info("Program is running. Press Ctrl+C to exit.")

            while True:
                if "cli_core" in get_plugins().keys():
                    time.sleep(1)
                else:
                    command = input()
                    if command == "getkey":

                        _control_interface.info(
                            _control_interface.tr(
                                "cli.starting.welcome_password"
                            ).format(get_password())
                        )
                    else:
                        _control_interface.error("Unkown Command!")
        except KeyboardInterrupt:
            _control_interface.info("\nCtrl+C detected. Exiting gracefully.")

    # Public
    def start_servers(self) -> None:
        """
        创建并启动HTTP和WebSocket服务器的线程。
        """

        aes_main(_control_interface)

        time.sleep(0.3)

        # 创建并启动HTTP服务器线程
        http_server_thread = threading.Thread(
            target=http_main, args=(_control_interface,)
        )
        http_server_thread.daemon = True

        # 创建并启动WebSocket服务器线程
        websocket_server_thread = threading.Thread(
            target=websocket_server_main, args=(_control_interface,)
        )
        websocket_server_thread.daemon = True

        http_server_thread.start()
        websocket_server_thread.start()

        self._running()


class Client(object):
    def __init__(self) -> None:
        _control_interface.info(
            _control_interface.tr("cli.starting.welcome_password").format(
                _config["password"]
            )
        )

        init_plugin_main(_control_interface)

    def _running(self) -> None:
        """
        程序持续运行
        """
        try:
            _control_interface.info("Program is running. Press Ctrl+C to exit.")
            while True:
                time.sleep(1)  # 模拟程序的持续运行
        except KeyboardInterrupt:
            _control_interface.info("\nCtrl+C detected. Exiting gracefully.")

    def start_server(self) -> None:
        """
        启动WebSocket客户端并初始化核心命令行程序。
        """

        aes_main(_control_interface, _control_interface.get_config()["password"])
        # 启动WebSocket客户端
        websocket_client_main(_control_interface)

        self._running()
