import os
import sys
import time
import json
import asyncio
import websockets
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.tools import new_thread, auto_trigger
from connect_core.websocket.data_packet import ClientDataPacket
from connect_core.plugin.init_plugin import connected, disconnected

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

_control_interface = None


class WebsocketClient(object):
    """
    WebSocket 客户端的主类，负责与服务器建立连接、发送和接收消息。
    """

    def __init__(self):
        """
        初始化 WebSocket 客户端的基本配置。
        """
        self._config = _control_interface.get_config()
        self.finish_start = False
        self.finish_close = False
        self.host = self._config["ip"]  # 服务器 IP 地址
        self.port = self._config["port"]  # 服务器端口
        self._main_task = None  # 主任务协程
        self._receive_task = None  # 接收任务协程
        self.server_id = None  # 服务器 ID
        self.last_data_packet = None  # 上一个发送的一个数据包
        self.data_packet = ClientDataPacket(_control_interface, self)  # 数据包处理类

    # ===========
    #   Control
    # ===========
    def start_server(self) -> None:
        """
        启动 WebSocket 客户端并运行主循环。
        """
        asyncio.run(self._init_main())

    def stop_server(self) -> None:
        """
        停止 WebSocket 客户端。
        如果接收任务正在运行，则取消该任务，否则取消主任务。
        """
        self._start_trigger_websocket_client.stop()
        if self._receive_task:
            self._receive_task.cancel()
        else:
            self._main_task.cancel()
            self.finish_close = True

    # ========
    #   Core
    # ========
    async def _init_main(self) -> None:
        """
        初始化并启动主 WebSocket 客户端任务。
        """
        self._main_task = asyncio.create_task(self._main())
        try:
            await self._main_task
            _control_interface.info(
                _control_interface.tr("net_core.service.stop_websocket")
            )
        except asyncio.CancelledError:
            _control_interface.info(
                _control_interface.tr("net_core.service.stop_websocket")
            )

    async def _main(self) -> None:
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
                    _control_interface.info(
                        _control_interface.tr(
                            "net_core.service.connect_websocket"
                        ).format("")
                    )
                    connected()
                    await self._receive()
                break
            except ConnectionRefusedError:
                self.finish_start = False
                await asyncio.sleep(1)

    # ========
    #   recv
    # ========
    async def _get_recv(self) -> None:
        """
        从 WebSocket 服务器接收消息。
        如果接收超时或连接关闭，将重新初始化客户端。
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
                if str(e) == "received 1000 (OK) 401; then sent 1000 (OK) 401":
                    _control_interface.error(
                        _control_interface.tr("net_core.service.already_login")
                    )
                    self.stop_server()
                    return
                elif str(e) != "received 1000 (OK) 400; then sent 1000 (OK) 400":
                    _control_interface.info(
                        _control_interface.tr("net_core.service.disconnect_websocket")
                        + str(e)
                    )
                    os.system(f"title ConnectCore Client")
                    disconnected()
                    websocket_client_main(_control_interface)
                    return
                else:
                    _control_interface.error(
                        _control_interface.tr("net_core.service.error_password")
                    )
                    self.stop_server()
                    return

    async def _receive(self) -> None:
        """
        接收并处理从服务器发送的消息。
        初始连接时会向服务器发送连接状态消息。
        """
        if self._config["account"] != "-----":
            await self.send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_LOGIN,
                    self.data_packet.DEFAULT_SERVER,
                    (self._config["account"], "system"),
                    {"path": sys.argv[0]},
                )
            )
        else:
            await self.send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_REGISTER,
                    self.data_packet.DEFAULT_SERVER,
                    self.data_packet.DEFAULT_TO_FROM,
                    {"path": sys.argv[0]},
                )
            )
        while True:
            self._receive_task = asyncio.create_task(self._get_recv())
            try:
                recv_data = await self._receive_task
                if recv_data:
                    if str(recv_data.decode())[0] != "{":
                        recv_data = aes_decrypt(recv_data).decode()
                    recv_data = json.loads(recv_data)
                    await self._parse_msg(recv_data)
                else:
                    break
            except asyncio.CancelledError:
                _control_interface.info(
                    _control_interface.tr("net_core.service.stop_receive")
                )
                self.finish_close = True
                return

    # ============
    #   Send Msg
    # ============
    async def send(
        self, data: dict, account: str = None
    ) -> None:
        """
        向服务器发送消息。

        Args:
            data (dict): 要发送的消息内容。
            account (str): 账号, 默认为None
        """
        data = data["-----"]
        if account is None:
            account = self._config["account"]
        _control_interface.debug(
            f"[S][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )
        if account:
            await self.websocket.send(
                json.dumps(
                    {
                        "account": account,
                        "data": aes_encrypt(json.dumps(data).encode()).decode(),
                    }
                ).encode()
            )
        else:
            await self.websocket.send(
                json.dumps({"account": account, "data": data}).encode()
            )

    async def _trigger_websocket_client(self) -> None:
        # 如果有上一个数据包，则发送上一个数据包
        if self.last_data_packet:
            await self.send(self.last_data_packet)
        await self.send(
            self.data_packet.get_data_packet(
                self.data_packet.TYPE_PING,
                self.data_packet.DEFAULT_SERVER,
                (self.server_id, "system"),
                None,
            )
        )
        await asyncio.sleep(30)

    # ======================
    #   Send Data to Other
    # ======================
    async def send_data_to_other_server(
        self,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: dict,
    ) -> None:
        """
        发送消息到指定的子服务器。

        Args:
            f_plugin_id (str): 插件的唯一标识符
            t_server_id (str): 子服务器的唯一标识符
            t_plugin_id (str): 子服务器插件的唯一标识符
            data (dict): 要发送的消息内容。
        """
        msg = self.data_packet.get_data_packet(
            self.data_packet.TYPE_DATA_SEND,
            (t_server_id, t_plugin_id),
            (self.server_id, f_plugin_id),
            data,
        )
        self.last_data_packet = msg
        await self.send(msg)

    @new_thread("SendFile")
    async def send_file_to_other_server(
        self,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        file_path: str,
        save_path: str,
    ) -> None:
        """
        发送文件到指定的子服务器。

        Args:
            f_plugin_id (str): 插件的唯一标识符
            t_server_id (str): 子服务器的唯一标识符
            t_plugin_id (str): 子服务器插件的唯一标识符
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
        try:
            file_hash = self.data_packet.get_file_hash(file_path)
            if os.path.basename(file_path) != os.path.basename(save_path):
                save_path = os.path.join(file_path, os.path.basename(file_path))
            await self.send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_FILE_SEND,
                    (t_server_id, t_plugin_id),
                    (self.server_id, f_plugin_id),
                    {
                        "file_name": file_path,
                        "save_path": save_path,
                        "hash": file_hash,
                    },
                ),
                self.websockets[t_server_id],
                t_server_id,
            )
            # 读取文件并分块发送数据
            with open(file_path, "rb") as file:
                chunk_size = 1024 * 1024  # 每次发送 1 MB
                while chunk := file.read(chunk_size):
                    await self.send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_FILE_SENDING,
                            (t_server_id, t_plugin_id),
                            (self.server_id, f_plugin_id),
                            {"file": chunk},
                        ),
                        self.websockets[t_server_id],
                        t_server_id,
                    )
                    await asyncio.sleep(0.1)  # 控制发送间隔（可选）
            await self.send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_FILE_SENDOK,
                    (t_server_id, t_plugin_id),
                    (self.server_id, f_plugin_id),
                    {
                        "file_name": file_path,
                        "save_path": save_path,
                        "hash": file_hash,
                    },
                ),
                self.websockets[t_server_id],
                t_server_id,
            )
        except Exception as e:
            _control_interface.error(f"Send File Error: {e}")

    # =============
    #   Parse Msg
    # =============
    async def _parse_msg(self, data: dict) -> None:
        """
        解析并处理从服务器接收到的消息。
        如果消息中包含服务器 ID，则更新客户端的服务器 ID。

        Args:
            data (dict): 从服务器接收到的消息内容。
        """
        await self.data_packet.parse_msg(data)

    # =========
    #   Tools
    # =========
    @auto_trigger(interval=30, thread_name="trigger_websocket_client")
    def _start_trigger_websocket_client(self) -> None:
        """启动PING PONG数据包服务"""
        asyncio.run(self._trigger_websocket_client())

    def get_history_data_packet(self) -> list:
        """获取历史数据包"""
        return self.data_packet.get_history_packet("-----", 0)


# Public
@new_thread("Websocket_Client")
def websocket_client_main(control_interface: "CoreControlInterface") -> None:
    """
    初始化 WebSocket 客户端。
    根据运行环境选择启动 MCDR 多线程客户端或 CLI 线程客户端。
    """
    global _control_interface

    _control_interface = control_interface
    time.sleep(0.3)
    global websocket_client
    websocket_client = WebsocketClient()
    websocket_client.start_server()


def send_data(f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict) -> None:
    """
    发送消息到指定的子服务器。

    Args:
        f_plugin_id (str): 插件的唯一标识符
        t_server_id (str): 子服务器的唯一标识符
        t_plugin_id (str): 子服务器插件的唯一标识符
        data (dict): 要发送的消息内容。
    """
    asyncio.run(
        websocket_client.send_data_to_other_server(
            f_plugin_id, t_server_id, t_plugin_id, data
        )
    )


def send_file(
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    """
    发送文件到指定的子服务器。

    Args:
        f_plugin_id (str): 插件的唯一标识符
        t_server_id (str): 子服务器的唯一标识符
        t_plugin_id (str): 子服务器插件的唯一标识符
        file_path (str): 要发送的文件目录。
        save_path (str): 要保存的位置。
    """
    asyncio.run(
        websocket_client.send_file_to_other_server(
            f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
        )
    )


def get_server_id() -> str:
    """
    获取客户端ID

    Returns:
        str: 服务器ID
    """
    return websocket_client.server_id


def get_history_data_packet() -> list:
    """获取历史数据包"""
    return websocket_client.get_history_data_packet()
