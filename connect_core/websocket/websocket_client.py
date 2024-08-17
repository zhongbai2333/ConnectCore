import websockets
import json
import asyncio
import threading
import sys, os
from time import sleep
from mcdreforged.api.all import new_thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.api.server_interface import ConnectCoreServerInterface

from connect_core.api.rsa import rsa_encrypt, rsa_decrypt
from connect_core.api.tools import verify_file_hash
from connect_core.api.http import download_file

global websocket_client, _connect_interface


# Public
def websocket_client_init(connect_interface: 'ConnectCoreServerInterface') -> None:
    """
    初始化 WebSocket 客户端。
    根据运行环境选择启动 MCDR 多线程客户端或 CLI 线程客户端。
    """
    global _connect_interface

    _connect_interface = connect_interface
    sleep(0.3)
    if connect_interface.is_mcdr():
        start_mcdr_server()
    else:
        websocket_client_thread = threading.Thread(target=start_cli_server)
        websocket_client_thread.daemon = True
        websocket_client_thread.start()


def get_server_id() -> str:
    """
    获取当前连接的服务器 ID。

    Returns:
        str: 服务器 ID，如果客户端未启动则返回 None。
    """
    return websocket_client.server_id if websocket_client else None


def get_server_list() -> list:
    """
    获取服务器列表

    Returns:
        list: 服务器列表
    """
    return websocket_client.server_list if websocket_client else None


def send_msg(server_id: str, msg: str) -> None:
    """
    向指定的子服务器发送消息。

    Args:
        server_id (str): 子服务器的唯一标识符。
        msg (str): 要发送的消息内容。
    """
    websocket_client.send_msg_to_other_server(server_id, msg)


def send_file(server_id: str, file_path: str, save_path: str) -> None:
    """
    向指定的子服务器发送文件。

    Args:
        server_id (str): 子服务器的唯一标识符。
        file_path (str): 要发送的文件目录。
        save_path (str): 要保存的位置。
    """
    websocket_client.send_file_to_sub_server(server_id, file_path, save_path)


# Private
def get_new_completer(server_list: list):
    """
    刷新服务器列表提示词，并更新命令行补全器。

    Args:
        server_list (list): 服务器列表

    Returns:
        completer (dict): 重制后的提示词
    """
    if _connect_interface.is_mcdr():
        return None

    server_dict = {server: None for server in server_list}
    server_dict["all"] = None
    server_dict["-----"] = None
    completer = {
        "help": None,
        "info": None,
        "list": None,
        "send": {"msg": server_dict, "file": server_dict},
        "reload": None,
        "exit": None,
    }
    return completer


def start_cli_server() -> None:
    """
    启动客户端。
    """
    global websocket_client
    websocket_client = WebsocketClient()
    websocket_client.start_server()


@new_thread("Websocket_Server")
def start_mcdr_server() -> None:
    """
    启用 MCDR 多线程启动 WebSocket 客户端。
    仅在 MCDR 环境下调用。
    """
    global websocket_client
    websocket_client = WebsocketClient()
    websocket_client.start_server()


class WebsocketClient:
    """
    WebSocket 客户端的主类，负责与服务器建立连接、发送和接收消息。
    """

    def __init__(self) -> None:
        """
        初始化 WebSocket 客户端的基本配置。
        """
        config = _connect_interface.get_config()
        self.finish_start = False
        self.finish_close = False
        self.host = config["ip"]  # 服务器 IP 地址
        self.port = config["port"]  # 服务器端口
        self.main_task = None  # 主任务协程
        self.receive_task = None  # 接收任务协程
        self.server_id = None  # 服务器 ID
        self.server_list = []  # 服务器列表

    def start_server(self) -> None:
        """
        启动 WebSocket 客户端并运行主循环。
        """
        asyncio.run(self.init_main())

    def stop_server(self) -> None:
        """
        停止 WebSocket 客户端。
        如果接收任务正在运行，则取消该任务，否则取消主任务。
        """
        if self.receive_task:
            self.receive_task.cancel()
        else:
            self.main_task.cancel()
            self.finish_close = True

    async def init_main(self) -> None:
        """
        初始化并启动主 WebSocket 客户端任务。
        """
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task
            _connect_interface.info(_connect_interface.tr("net_core.service.stop_websocket"))
        except asyncio.CancelledError:
            _connect_interface.info(_connect_interface.tr("net_core.service.stop_websocket"))

    async def main(self) -> None:
        """
        WebSocket 客户端的主循环，负责尝试与服务器连接。
        如果连接失败，会每隔一段时间重试。
        """
        while True:
            try:
                async with websockets.connect(
                    f"ws://{self.host}:{self.port}"
                ) as self.websocket:
                    self.finish_start = True
                    _connect_interface.info(
                        _connect_interface.tr("net_core.service.connect_websocket").format("")
                    )
                    await self.receive()
                break
            except ConnectionRefusedError:
                self.finish_start = False
                await asyncio.sleep(1)

    async def receive(self) -> None:
        """
        接收并处理从服务器发送的消息。
        初始连接时会向服务器发送连接状态消息。
        """
        await self.send_msg(
            {"s": 1, "status": "Connect", "data": {"path": sys.argv[0]}}
        )
        while True:
            self.receive_task = asyncio.create_task(self.get_recv())
            try:
                recv_data = await self.receive_task
                if recv_data:
                    recv_data = rsa_decrypt(recv_data).decode()
                    recv_data = json.loads(recv_data)
                    _connect_interface.debug(f"Received data from main server: {recv_data}")
                    await self.parse_message(recv_data)
                else:
                    break
            except asyncio.CancelledError:
                _connect_interface.info(_connect_interface.tr("net_core.service.stop_receive"))
                self.finish_close = True
                return

    async def get_recv(self) -> None:
        """
        从 WebSocket 服务器接收消息。
        如果接收超时或连接关闭，将重新初始化客户端。

        Returns:
            str: 接收到的消息内容。
        """
        while True:
            try:
                return await asyncio.wait_for(self.websocket.recv(), timeout=4)
            except asyncio.TimeoutError:
                pass
            except (
                websockets.ConnectionClosedError,
                websockets.ConnectionClosedOK,
            ) as e:
                if str(e) != "received 1000 (OK) 400; then sent 1000 (OK) 400":
                    _connect_interface.info(
                        _connect_interface.tr("net_core.service.disconnect_websocket") + str(e)
                    )
                    os.system(f"title ConnectCore Client")
                    websocket_client_init(_connect_interface)
                    return
                else:
                    _connect_interface.error(_connect_interface.tr("net_core.service.error_password"))
                    self.stop_server()
                    return

    async def send_msg(self, msg: dict) -> None:
        """
        向服务器发送消息。

        Args:
            msg (dict): 要发送的消息内容。
        """
        await self.websocket.send(rsa_encrypt(json.dumps(msg).encode()))

    def send_msg_to_other_server(self, to_server_id: str, msg: str) -> None:
        """
        发送消息到指定的子服务器。

        Args:
            server_id (str): 子服务器的唯一标识符。
            msg (str): 要发送的消息内容。
        """
        msg = {
            "s": 0,
            "id": to_server_id,
            "from": self.server_id,
            "pluginid": "system",
            "data": {"msg": msg},
        }
        asyncio.run(self.send_msg(msg))

    async def parse_message(self, msg: dict) -> None:
        """
        解析并处理从服务器接收到的消息。
        如果消息中包含服务器 ID，则更新客户端的服务器 ID。

        Args:
            msg (dict): 从服务器接收到的消息内容。
        """
        if msg["s"] == 1:
            os.system(f"title ConnectCore Client {msg["id"]}")
            self.server_id = msg["id"]
        elif msg["s"] == 0:
            if msg["pluginid"] == "system":
                data = msg["data"]
                if "server_list" in data.keys():
                    self.server_list = data["server_list"]

                    from connect_core.cli.client.commands import _command_interface

                    new_server_list = self.server_list.copy()
                    new_server_list.remove(self.server_id)

                    completer = get_new_completer(new_server_list)
                    _command_interface.set_completer_words(completer)
                    _command_interface.flush_cli()
                if "msg" in data.keys():
                    if _connect_interface.is_mcdr():
                        pass # TODO
                    else:
                        _connect_interface.info(data["msg"])
                if "file" in data.keys():
                    data = data["file"]
                    download_file(_connect_interface, data["path"], data["save_path"])
                    while not verify_file_hash(data["save_path"], data["hash"]):
                        download_file(_connect_interface, data["path"], data["save_path"])
                    wait_send_msg = {
                        "s": 0,
                        "id": "-----",
                        "from": self.server_id,
                        "pluginid": "system",
                        "data": {
                            "file": {
                                "hash": data["hash"]
                            }
                        },
                    }
                    await self.send_msg(wait_send_msg)
                    _connect_interface.info(_connect_interface.tr("net_core.service.file_download_finish_from_other").format(msg["from"]))
