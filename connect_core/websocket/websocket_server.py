import websockets
import json
import asyncio
import random
import string
import shutil
import os
from mcdreforged.api.all import new_thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.contol_interface import ControlInterface

from connect_core.rsa_encrypt import rsa_encrypt, rsa_decrypt
from connect_core.cli.tools import get_file_hash
from connect_core.mcdr.mcdr_entry import get_mcdr

websocket_server = None
global _control_interface


# Public
def websocket_server_init(control_interface: "ControlInterface") -> None:
    """
    初始化 WebSocket 服务器。
    根据环境选择启动 MCDR 多线程服务器或普通服务器。
    """
    global _control_interface

    _control_interface = control_interface
    if get_mcdr():
        start_mcdr_server()
    else:
        global websocket_server
        websocket_server = WebsocketServer()
        websocket_server.start_server()


def get_servers_info() -> dict:
    """
    获取已连接的子服务器信息。

    Returns:
        dict: 包含子服务器信息的字典。
    """
    return websocket_server.servers_info if websocket_server else {}


def send_data(pluginid: str, server_id: str, data: str) -> None:
    """
    向指定的子服务器发送消息。

    Args:
        pluginid (str): 插件的唯一标识符
        server_id (str): 子服务器的唯一标识符。
        data (str): 要发送的数据。
    """
    websocket_server.send_data_to_sub_server(pluginid, server_id, data)


def send_file(pluginid: str, server_id: str, file_path: str, save_path: str) -> None:
    """
    向指定的子服务器发送文件。

    Args:
        pluginid (str): 插件的唯一标识符
        server_id (str): 子服务器的唯一标识符。
        file_path (str): 要发送的文件目录。
        save_path (str): 要保存的位置。
    """
    websocket_server.send_file_to_sub_server(pluginid, server_id, file_path, save_path)


# Private
def get_new_completer(server_list: list):
    """
    刷新服务器列表提示词，并更新命令行补全器。

    Args:
        server_list (list): 服务器列表

    Returns:
        completer (dict): 重制后的提示词
    """
    if get_mcdr():
        return None

    server_dict = {server: None for server in server_list}
    server_dict["all"] = None
    completer = {
        "help": None,
        "list": None,
        "send": {"msg": server_dict, "file": server_dict},
        "reload": None,
        "exit": None,
    }
    return completer


@new_thread("Websocket_Server")
def start_mcdr_server() -> None:
    """
    启用 MCDR 多线程启动 WebSocket 服务器。
    仅在 MCDR 环境下调用。
    """
    global websocket_server
    websocket_server = WebsocketServer()
    websocket_server.start_server()


class WebsocketServer:
    """
    WebSocket 服务器的主类，负责管理 WebSocket 连接和通信。
    """

    def __init__(self) -> None:
        """
        初始化 WebSocket 服务器的基本配置。
        """
        config = _control_interface.get_config()
        self.finish_close = False
        self.host = config["ip"]  # 服务器监听的 IP 地址
        self.port = config["port"]  # 服务器监听的端口号
        self.websockets = {}  # 存储已连接的 WebSocket 客户端
        self.broadcast_websockets = set()  # 需要广播消息的 WebSocket 客户端集合
        self.servers_info = {}  # 存储已连接的子服务器的信息
        self.wait_flie_list = {}  # 存储等待下载的文件信息

    def start_server(self) -> None:
        """
        启动 WebSocket 服务器。
        """
        asyncio.run(self.init_main())

    def close_server(self) -> None:
        """
        关闭 WebSocket 服务器。
        取消主任务以停止服务器。
        """
        if hasattr(self, "main_task"):
            self.main_task.cancel()

    def generate_random_id(self, n: int) -> str:
        """
        生成指定长度的随机字符串，包含字母和数字。

        Args:
            n (int): 生成的字符串长度。

        Returns:
            str: 生成的随机字符串。
        """
        numeric_part = "".join(
            [str(random.randint(0, 9)) for _ in range(random.randint(1, n))]
        )
        alpha_part = "".join(
            [random.choice(string.ascii_letters) for _ in range(n - len(numeric_part))]
        )
        return "".join(random.sample(list(numeric_part + alpha_part), n))

    async def init_main(self) -> None:
        """
        初始化并启动主 WebSocket 服务器任务。
        """
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task
        except asyncio.CancelledError:
            _control_interface.info(
                _control_interface.tr("net_core.service.stop_websocket")
            )
            self.finish_close = True

    async def main(self) -> None:
        """
        WebSocket 服务器的主循环，负责监听连接并处理通信。
        """
        async with websockets.serve(self.handler, self.host, self.port):
            _control_interface.info(
                _control_interface.tr("net_core.service.start_websocket")
            )
            await asyncio.Future()  # 阻塞以保持服务器运行

    async def handler(self, websocket) -> None:
        """
        处理每个 WebSocket 连接的协程，管理消息的接收和响应。

        Args:
            websocket: 当前连接的 WebSocket 对象。
        """
        server_id = None
        try:
            while True:
                msg = await websocket.recv()
                try:
                    # 解密并解析收到的消息
                    msg = rsa_decrypt(msg).decode()
                    msg = json.loads(msg)
                    _control_interface.debug(f"Received data from sub-server: {msg}")

                    if msg["s"] == 1:
                        # 为新连接的子服务器生成唯一的 ID
                        server_id = self.generate_random_id(5)
                        while server_id in self.websockets:
                            server_id = self.generate_random_id(5)

                        self.websockets[server_id] = websocket
                        self.broadcast_websockets.add(websocket)
                        self.servers_info[server_id] = msg["data"]

                        completer = get_new_completer(list(self.websockets.keys()))
                        _control_interface.cli_core.set_completer_words(completer)
                        _control_interface.cli_core.flush_cli()

                        _control_interface.info(
                            _control_interface.tr(
                                "net_core.service.connect_websocket"
                            ).format(f"Server {server_id}")
                        )

                        # 发送连接成功的确认消息
                        await self.send_msg(
                            websocket,
                            {"s": 1, "id": server_id, "status": "Succeed", "data": {}},
                        )

                        self.broadcast(
                            {
                                "s": 0,
                                "id": "all",
                                "from": "-----",
                                "pluginid": "system",
                                "data": {"server_list": list(self.servers_info.keys())},
                            }
                        )

                    else:
                        await self.parse_msg(msg)

                except Exception as e:
                    # 处理解密或消息处理时发生的错误
                    _control_interface.debug(f"Error with sub-server connection: {e}")
                    await websocket.close(reason="400")
                    self.close_connection(server_id, websocket)
                    break

        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,
        ):
            # 处理连接关闭的情况
            self.close_connection(server_id, websocket)

    def close_connection(self, server_id: str = None, websocket=None) -> None:
        """
        关闭与子服务器的连接并清理相关数据。

        Args:
            server_id (str, optional): 要关闭的子服务器 ID。默认为 None。
            websocket (optional): 要关闭的 WebSocket 对象。默认为 None。
        """
        if server_id and websocket:
            if server_id in self.websockets:
                del self.websockets[server_id]
            if server_id in self.servers_info:
                del self.servers_info[server_id]
            if websocket in self.broadcast_websockets:
                self.broadcast_websockets.remove(websocket)

            completer = get_new_completer(list(self.websockets.keys()))
            _control_interface.cli_core.set_completer_words(completer)
            _control_interface.cli_core.flush_cli()

            get_new_completer(list(self.websockets.keys()))

            self.broadcast(
                {
                    "s": 0,
                    "id": "all",
                    "from": "-----",
                    "pluginid": "system",
                    "data": {"server_list": list(self.servers_info.keys())},
                }
            )

            _control_interface.info(
                _control_interface.tr(
                    "net_core.service.disconnect_from_sub_websocket"
                ).format(server_id)
            )
        else:
            _control_interface.warn(
                _control_interface.tr(
                    "net_core.service.disconnect_from_unknown_websocket"
                )
            )

    async def send_msg(self, websocket, msg: dict) -> None:
        """
        向指定的 WebSocket 客户端发送消息。

        Args:
            websocket: 目标 WebSocket 客户端。
            msg (dict): 要发送的消息内容。
        """
        await websocket.send(rsa_encrypt(json.dumps(msg).encode()))

    def send_data_to_sub_server(self, pluginid: str, server_id: str, data: dict) -> None:
        """
        发送消息到指定的子服务器。

        Args:
            pluginid (str): 插件的唯一标识符
            server_id (str): 子服务器的唯一标识符。
            data (dict): 要发送的数据。
        """
        msg = {
            "s": 0,
            "id": server_id,
            "from": "-----",
            "pluginid": pluginid,
            "data": data,
        }
        if server_id == "all":
            self.broadcast(msg)
        else:
            asyncio.run(self.send_msg(self.websockets[server_id], msg))

    def send_file_to_sub_server(self, pluginid: str, server_id: str, file_path: str, save_path: str) -> None:
        """
        发送文件到指定的子服务器。

        Args:
            pluginid (str): 插件的唯一标识符
            server_id (str): 子服务器的唯一标识符。
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
        try:
            # 复制文件
            shutil.copy(file_path, "./send_files/")
            file_hash = get_file_hash(file_path)
            config = _control_interface.get_config()
            msg = {
                "s": 0,
                "id": server_id,
                "from": "-----",
                "pluginid": pluginid,
                "data": {
                    "file": {
                        "path": f"http://{config['ip']}:{config['http_port']}/send_files/{os.path.basename(file_path)}",
                        "hash": file_hash,
                        "save_path": save_path,
                    }
                },
            }
            if server_id == "all":
                self.wait_flie_list[file_hash] = [
                    f"./send_files/{os.path.basename(file_path)}",
                    list(self.servers_info.keys()),
                ]
                self.broadcast(msg)
            else:
                self.wait_flie_list[file_hash] = [
                    f"./send_files/{os.path.basename(file_path)}",
                    [server_id],
                ]
                asyncio.run(self.send_msg(self.websockets[server_id], msg))
        except (IOError, OSError) as e:
            _control_interface.error(f"Copy Error: {e}")

    def broadcast(self, msg: dict, server_ids: list = []) -> None:
        """
        广播消息到所有已连接的子服务器。

        Args:
            msg (dict): 要广播的消息内容。
            server_ids (list): 过滤的服务器ID, 默认为 []。
        """
        websocket_list = self.broadcast_websockets.copy()
        for i in server_ids:
            websocket_list.remove(self.websockets[i])
        websockets.broadcast(websocket_list, rsa_encrypt(json.dumps(msg).encode()))

    async def parse_msg(self, msg: dict):
        """
        解析并处理从子服务器接收到的消息。

        Args:
            msg (dict): 从服务器接收到的消息内容。
        """
        if msg["s"] == 0:
            if "msg" in msg["data"].keys():
                if msg["id"] == "-----":
                    if get_mcdr():
                        pass # TODO
                    else:
                        _control_interface.info(msg["data"]["msg"])
                elif msg["id"] == "all":
                    msg = {
                        "s": 0,
                        "id": msg["id"],
                        "from": msg["from"],
                        "pluginid": msg["pluginid"],
                        "data": msg["data"],
                    }
                    self.broadcast(msg, [msg["from"]])
                    if get_mcdr():
                        pass # TODO
                    else:
                        _control_interface.info(msg["data"]["msg"])
                else:
                    msg = {
                        "s": 0,
                        "id": msg["id"],
                        "from": msg["from"],
                        "pluginid": msg["pluginid"],
                        "data": msg["data"],
                    }
                    await self.send_msg(self.websockets[msg["id"]], msg)
            if "file" in msg["data"].keys():
                file_hash = msg["data"]["file"]["hash"]
                self.wait_flie_list[file_hash][1].remove(msg["from"])
                if not self.wait_flie_list[file_hash][1]:
                    os.remove(self.wait_flie_list[file_hash][0])
                    del self.wait_flie_list[file_hash]
                    _control_interface.info(
                        _control_interface.tr(
                            "net_core.service.sub_server_download_finish"
                        ).format(msg["from"])
                    )
