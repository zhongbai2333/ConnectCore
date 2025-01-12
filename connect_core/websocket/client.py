import os
import sys
import time
import json
import asyncio
import websockets
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.tools import restart_program, new_thread, auto_trigger
from connect_core.websocket.data_packet import DataPacket
from connect_core.plugin.init_plugin import (
    new_connect,
    del_connect,
    connected,
    disconnected,
    recv_data,
    recv_file,
)
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
        self.sid = 2  # 数据包编号
        self.server_list = []  # 服务器列表
        self.last_data_packet = None  # 上一个发送的一个数据包
        self.data_packet = DataPacket()  # 数据包处理类
        self._wait_file = None  # 等待接收的文件

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
                if str(e) != "received 1000 (OK) 400; then sent 1000 (OK) 400":
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
            await self._send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_LOGIN,
                    self.data_packet.DEFAULT_SERVER,
                    (self._config["account"], "system"),
                    {"path": sys.argv[0]},
                )
            )
        else:
            await self._send(
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
    async def _send(
        self, data: dict, from_data_pack: bool = True, account: str = None
    ) -> None:
        """
        向服务器发送消息。

        Args:
            data (dict): 要发送的消息内容。
            account (str): 账号, 默认为None
        """
        if from_data_pack:
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
            await self._send(self.last_data_packet, False)
        await self._send(
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
        await self._send(msg)

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
            await self._send(
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
                    await self._send(
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
            await self._send(
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
        data_type = tuple(data["type"])
        self.data_packet.add_recv_packet("-----", data)
        _control_interface.debug(
            f"[R][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )
        match data_type:
            # Control 数据包
            case self.data_packet.TYPE_CONTROL_STOP:
                pass

            # Register 数据包
            case self.data_packet.TYPE_REGISTERED:
                if self.data_packet.verify_md5_checksum(
                    data["data"]["payload"], data["data"]["checksum"]
                ):
                    self._config["account"] = data["to"][0]
                    self._config["password"] = data["data"]["payload"]["password"]
                    _control_interface.save_config(self._config)
                    restart_program()
                else:
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_REGISTER_ERROR,
                            self.data_packet.DEFAULT_SERVER,
                            self.data_packet.DEFAULT_TO_FROM,
                            None,
                        )
                    )
            case self.data_packet.TYPE_REGISTER_ERROR:
                _control_interface.error(f"Register Error: {data["data"]["payload"]}")
                self.stop_server()

            # Login 数据包
            case self.data_packet.TYPE_LOGINED:
                os.system(f"title ConnectCore Client {data["to"][0]}")
                self.server_id = data["to"][0]
                self._start_trigger_websocket_client()
            case self.data_packet.TYPE_NEW_LOGIN:
                # NewLogin 数据包
                new_connect(data["data"]["payload"]["server_list"])
            case self.data_packet.TYPE_DEL_LOGIN:
                # DelLogin 数据包
                del_connect(data["data"]["payload"]["server_list"])
            case self.data_packet.TYPE_LOGIN_ERROR:
                _control_interface.error(f"Login Error: {data["data"]["payload"]}")
                self.stop_server()

            # Data 数据包
            case self.data_packet.TYPE_DATA_SEND:
                # Send 数据包
                if data["data"] and self.data_packet.verify_md5_checksum(
                    data["data"]["payload"], data["data"]["checksum"]
                ):
                    if not data["data"]:
                        data["data"]["payload"] = {}
                    recv_data(data["to"][1], data["data"]["payload"])
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_DATA_SENDOK,
                            self.data_packet.DEFAULT_SERVER,
                            (self.server_id, data["to"][1]),
                            None,
                        )
                    )
                else:
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_DATA_ERROR,
                            self.data_packet.DEFAULT_SERVER,
                            (self.server_id, data["to"][1]),
                            {"to": data["to"]},
                        )
                    )
            case self.data_packet.TYPE_DATA_SENDOK:
                # SendOK 数据包
                self.last_data_packet = None
            case self.data_packet.TYPE_DATA_ERROR:
                # Error 数据包
                await self._send(self.last_data_packet, False)

            # File 数据包
            case self.data_packet.TYPE_FILE_SEND:
                if self.data_packet.verify_md5_checksum(
                    data["data"]["payload"], data["data"]["checksum"]
                ):
                    self._wait_file = open(data["data"]["payload"]["save_path"], "wb")
                else:
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_FILE_ERROR,
                            data["from"],
                            self.data_packet.DEFAULT_SERVER,
                            {"to": data["to"]},
                        )
                    )
            case self.data_packet.TYPE_FILE_SENDING:
                if self.data_packet.verify_md5_checksum(
                    data["data"]["payload"], data["data"]["checksum"]
                ):
                    if self._wait_file:
                        self._wait_file_list.write(data["data"]["payload"]["file"])
                        self._wait_file_list.flush()
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            )
                        )
                else:
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_FILE_ERROR,
                            data["from"],
                            self.data_packet.DEFAULT_SERVER,
                            {"to": data["to"]},
                        )
                    )
            case self.data_packet.TYPE_FILE_SENDOK:
                if self.data_packet.verify_md5_checksum(
                    data["data"]["payload"], data["data"]["checksum"]
                ):
                    if self._wait_file_list:
                        self._wait_file_list.close()
                        if self.data_packet.verify_file_hash(
                            data["data"]["payload"]["save_path"],
                            data["data"]["payload"]["hash"],
                        ):
                            recv_file(
                                    data["from"][1], data["data"]["payload"]["save_path"]
                                )
                        else:
                            await self._send(
                                self.data_packet.get_data_packet(
                                    self.data_packet.TYPE_FILE_ERROR,
                                    data["from"],
                                    self.data_packet.DEFAULT_SERVER,
                                    {"to": data["to"]},
                                )
                            )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            )
                        )
                else:
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_FILE_ERROR,
                            data["from"],
                            self.data_packet.DEFAULT_SERVER,
                            {"to": data["to"]},
                        )
                    )

            case _:
                pass

    # =========
    #   Tools
    # =========
    @auto_trigger(interval=30, thread_name="trigger_websocket_client")
    def _start_trigger_websocket_client(self) -> None:
        """启动PING PONG数据包服务"""
        asyncio.run(self._trigger_websocket_client())


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
