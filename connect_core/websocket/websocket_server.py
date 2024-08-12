import websockets
import json
import asyncio
import random
import string
from mcdreforged.api.all import new_thread

from connect_core.api.log_system import info_print, warn_print, error_print, debug_print
from connect_core.api.c_t import config, translate, is_mcdr
from connect_core.api.rsa import rsa_encrypt, rsa_decrypt

global websocket_server


def websocket_server_init() -> None:
    """
    初始化 WebSocket 服务器。
    根据环境选择启动 MCDR 多线程服务器或普通服务器。
    """
    if is_mcdr():
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


def send_msg(server_id: str, msg: str) -> None:
    """
    向指定的子服务器发送消息。

    Args:
        server_id (str): 子服务器的唯一标识符。
        msg (str): 要发送的消息内容。
    """
    websocket_server.send_msg_to_sub_server(server_id, msg)


def flush_completer(server_list: list):
    """
    刷新服务器列表提示词，并更新命令行补全器。

    Args:
        server_list (list): 服务器列表

    Returns:
        completer (dict): 重制后的提示词
    """
    if is_mcdr():
        return None

    server_dict = {server: None for server in server_list}
    server_dict["all"] = None
    completer = {
        "list": None,
        "send": {"msg": server_dict, "file": server_dict},
        "exit": None,
        "help": None,
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
        self.finish_close = False
        self.host = config("ip")  # 服务器监听的 IP 地址
        self.port = config("port")  # 服务器监听的端口号
        self.websockets = {}  # 存储已连接的 WebSocket 客户端
        self.broadcast_websockets = set()  # 需要广播消息的 WebSocket 客户端集合
        self.servers_info = {}  # 存储已连接的子服务器的信息

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
            info_print(translate("net_core.service.stop_websocket"))
            self.finish_close = True

    async def main(self) -> None:
        """
        WebSocket 服务器的主循环，负责监听连接并处理通信。
        """
        async with websockets.serve(self.handler, self.host, self.port):
            info_print(translate("net_core.service.start_websocket"))
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
                    debug_print(f"Received data from sub-server: {msg}")

                    if msg["s"] == 1:
                        # 为新连接的子服务器生成唯一的 ID
                        server_id = self.generate_random_id(5)
                        while server_id in self.websockets:
                            server_id = self.generate_random_id(5)

                        self.websockets[server_id] = websocket
                        self.broadcast_websockets.add(websocket)
                        self.servers_info[server_id] = msg["data"]

                        from connect_core.cli_core import (
                            set_completer_words,
                            restart_cli_core,
                        )

                        completer = flush_completer(list(self.websockets.keys()))
                        set_completer_words(completer)
                        restart_cli_core()

                        info_print(
                            translate("net_core.service.connect_websocket").format(
                                f"Server {server_id}"
                            )
                        )

                        # 发送连接成功的确认消息
                        await self.send_msg(
                            websocket,
                            {"s": 1, "id": server_id, "status": "Succeed", "data": {}},
                        )

                except Exception as e:
                    # 处理解密或消息处理时发生的错误
                    debug_print(f"Error with sub-server connection: {e}")
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

            from connect_core.cli_core import set_completer_words, restart_cli_core

            completer = flush_completer(list(self.websockets.keys()))
            set_completer_words(completer)
            restart_cli_core()

            flush_completer(list(self.websockets.keys()))

            info_print(
                translate("net_core.service.disconnect_from_sub_websocket").format(
                    server_id
                )
            )
        else:
            warn_print(translate("net_core.service.disconnect_from_unknown_websocket"))

    async def send_msg(self, websocket, msg: dict) -> None:
        """
        向指定的 WebSocket 客户端发送消息。

        Args:
            websocket: 目标 WebSocket 客户端。
            msg (dict): 要发送的消息内容。
        """
        await websocket.send(rsa_encrypt(json.dumps(msg).encode()))

    def send_msg_to_sub_server(self, server_id: str, msg: str) -> None:
        """
        发送消息到指定的子服务器。

        Args:
            server_id (str): 子服务器的唯一标识符。
            msg (str): 要发送的消息内容。
        """
        msg = {
            "s": 0,
            "id": server_id,
            "from": "-----",
            "pluginid": "system",
            "data": {"msg": msg},
        }
        if server_id == "all":
            self.broadcast(msg)
        else:
            asyncio.run(self.send_msg(self.websockets[server_id], msg))

    def broadcast(self, msg: dict) -> None:
        """
        广播消息到所有已连接的子服务器。

        Args:
            msg (dict): 要广播的消息内容。
        """
        websockets.broadcast(
            self.broadcast_websockets, rsa_encrypt(json.dumps(msg).encode())
        )
