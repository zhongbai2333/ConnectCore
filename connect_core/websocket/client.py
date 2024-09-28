import os
import sys
import time
import json
import asyncio
import threading
from typing import TYPE_CHECKING

import websockets
from mcdreforged.api.all import new_thread

from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.tools import verify_file_hash, get_file_hash, restart_program
from connect_core.http.client import download_file, upload_file
from connect_core.mcdr.mcdr_entry import get_mcdr
from connect_core.plugin.init_plugin import (
    new_connect,
    del_connect,
    connected,
    disconnected,
    recv_data,
    recv_file,
)

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface


class WebsocketClient:
    """
    WebSocket 客户端的主类，负责与服务器建立连接、发送和接收消息。
    """

    def __init__(self) -> None:
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
        self.server_list = []  # 服务器列表

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
        if self._config["account"]:
            await self._send( 
                {"s": 1, "id": "-----", "status": "Connect", "data": {"path": sys.argv[0]}}
            )
        else:
            await self._send(
                {"s": 1, "id": "-----", "status": "Register", "data": {"path": sys.argv[0]}}
            )
        while True:
            self._receive_task = asyncio.create_task(self._get_recv())
            try:
                recv_data = await self._receive_task
                if recv_data:
                    if str(recv_data.decode())[0] != "{":
                        recv_data = aes_decrypt(recv_data).decode()
                    recv_data = json.loads(recv_data)
                    _control_interface.debug(
                        f"Received data from main server: {recv_data}"
                    )
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
    async def _send(self, data: dict, account: str = None) -> None:
        """
        向服务器发送消息。

        Args:
            data (dict): 要发送的消息内容。
            account (str): 账号, 默认为None
        """
        if account is None:
            account = self._config["account"]
        if account:
            await self.websocket.send(json.dumps({
                "account": account,
                "data": aes_encrypt(json.dumps(data).encode()).decode()
            }).encode())
        else:
            await self.websocket.send(json.dumps({
                "account": account,
                "data": data
            }).encode())

    # ======================
    #   Send Data to Other
    # ======================
    def send_data_to_other_server(
        self,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: dict,
    ) -> None:
        """
        发送消息到指定的子服务器。

        Args:
            f_server_id (str): 服务器的唯一标识符
            f_plugin_id (str): 插件的唯一标识符
            t_server_id (str): 子服务器的唯一标识符
            t_plugin_id (str): 子服务器插件的唯一标识符
            data (dict): 要发送的消息内容。
        """
        msg = {
            "s": 0,
            "to": {"id": t_server_id, "pluginid": t_plugin_id},
            "from": {"id": self.server_id, "pluginid": f_plugin_id},
            "status": "SendData",
            "data": data,
        }
        asyncio.run(self._send(msg))

    def send_file_to_other_server(
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
            f_server_id (str): 服务器的唯一标识符
            f_plugin_id (str): 插件的唯一标识符
            t_server_id (str): 子服务器的唯一标识符
            t_plugin_id (str): 子服务器插件的唯一标识符
            file_path (str): 要发送的文件目录。
            save_path (str): 要保存的位置。
        """
        file_hash = get_file_hash(file_path)
        msg = {
            "s": 0,
            "to": {"id": t_server_id, "pluginid": t_plugin_id},
            "from": {"id": self.server_id, "pluginid": f_plugin_id},
            "status": "RequestSendFile",
            "file": {"hash": file_hash, "file_path": file_path, "save_path": save_path},
        }
        asyncio.run(self._send(msg))


    # =============
    #   Parse Msg
    # =============
    async def _parse_msg(self, data: dict) -> None:
        """
        解析并处理从服务器接收到的消息。
        如果消息中包含服务器 ID，则更新客户端的服务器 ID。

        Args:
            msg (dict): 从服务器接收到的消息内容。
        """
        if data["s"] == 1:
            if data["status"] == "ConnectOK":
                if self._config["account"] == "":
                    await self._send({
                    "s": 1,
                    "id": "-----",
                    "status": "Connect",
                    "data": {"path": sys.argv[0]}
                }, "-----")
                else:
                    await self._send({
                        "s": 1,
                        "id": "-----",
                        "status": "Connect",
                        "data": {"path": sys.argv[0]}
                    })
            elif data["status"] == "Registered":
                self._config["account"] = data["id"]
                self._config["password"] = data["data"]["password"]
                _control_interface.save_config(self._config)
                restart_program()
            elif data["status"] == "Connected":
                os.system(f"title ConnectCore Client {data["id"]}")
                self.server_id = data["id"]
        elif data["s"] == 2:
            if data["status"] == "NewServer":
                new_connect(data["data"]["server_list"])
            else:
                del_connect(data["data"]["server_list"])
        elif data["s"] == 0:
            if data["status"] == "SendData":
                recv_data(data["to"]["pluginid"], data["data"])
            elif data["status"] == "SendFile":
                download_file(_control_interface, data["file"]["path"], data["file"]["save_path"])
                while not verify_file_hash(data["file"]["save_path"], data["file"]["hash"]):
                    download_file(_control_interface, data["file"]["path"], data["file"]["save_path"])
                wait_send_msg = {
                    "s": 0,
                    "to": {"id": "-----", "pluginid": data["from"]["pluginid"]},
                    "from": {"id": self.server_id, "pluginid": data["to"]["pluginid"]},
                    "status": "RecvFile",
                    "file": {
                        "hash": data["file"]["hash"]
                    },
                }
                await self._send(wait_send_msg)
                _control_interface.info(_control_interface.tr("net_core.service.file_download_finish_from_other").format(data["from"]["id"], data["file"]["save_path"]))
                recv_file(data["to"]["pluginid"], data["file"]["save_path"])
            elif data["status"] == "SendFileOK":
                upload_file(_control_interface, data["file"]["path"], data["file"]["file_path"], self.server_id)
                msg = {
                    "s": 0,
                    "to": {
                        "id": data["from"]["id"],
                        "pluginid": data["from"]["pluginid"],
                    },
                    "from": {
                        "id": data["to"]["id"],
                        "pluginid": data["to"]["pluginid"],
                    },
                    "status": "SendFile",
                    "file": {"hash": data["file"]["hash"], "file_path": data["file"]["file_path"], "save_path": data["file"]["save_path"]},
                }
                await self._send(msg)


def start_client() -> None:
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


# Public
def websocket_client_main(control_interface: "CoreControlInterface") -> None:
    """
    初始化 WebSocket 客户端。
    根据运行环境选择启动 MCDR 多线程客户端或 CLI 线程客户端。
    """
    global _control_interface

    _control_interface = control_interface
    time.sleep(0.3)
    if get_mcdr():
        start_mcdr_server()
    else:
        websocket_client_thread = threading.Thread(target=start_client)
        websocket_client_thread.daemon = True
        websocket_client_thread.start()


def send_data(
    f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict
) -> None:
    """
    发送消息到指定的子服务器。

    Args:
        f_plugin_id (str): 插件的唯一标识符
        t_server_id (str): 子服务器的唯一标识符
        t_plugin_id (str): 子服务器插件的唯一标识符
        data (dict): 要发送的消息内容。
    """
    websocket_client.send_data_to_other_server(
        f_plugin_id, t_server_id, t_plugin_id, data
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
    websocket_client.send_file_to_other_server(
        f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
    )


def get_server_id() -> str:
    """
    获取客户端ID

    Returns:
        str: 服务器ID
    """
    return websocket_client.server_id
