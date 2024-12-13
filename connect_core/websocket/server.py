import random
import string
import asyncio
import websockets
import json
import shutil
import os
from cryptography.fernet import Fernet
from mcdreforged.api.all import new_thread
from connect_core.mcdr.mcdr_entry import get_mcdr
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.tools import get_file_hash, verify_file_hash
from connect_core.account.register_system import get_register_password
from connect_core.plugin.init_plugin import (
    del_connect,
    disconnected,
    recv_data,
    recv_file,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

websocket_server, _control_interface = None, None


class WebsocketServer:
    """WebSocket 服务器的主类，负责管理 WebSocket 连接和通信。"""

    def __init__(self) -> None:
        """初始化 WebSocket 服务器的基本配置。"""
        self._config = _control_interface.get_config()
        self.finish_close = False
        self._host = self._config["ip"]
        self._port = self._config["port"]
        self.websockets = {}
        self.broadcast_websockets = set()
        self.servers_info = {}
        self._wait_file_list = {}
        self._wait_register_connect = {}

    # =========== Control ===========
    def start_server(self) -> None:
        """启动 WebSocket 服务器。"""
        asyncio.run(self._init_main())

    def close_server(self) -> None:
        """关闭 WebSocket 服务器。"""
        if hasattr(self, "main_task"):
            self.main_task.cancel()

    # ========== Core ==========
    async def _init_main(self) -> None:
        """初始化并启动主 WebSocket 服务器任务。"""
        self.main_task = asyncio.create_task(self._main())
        try:
            await self.main_task
        except asyncio.CancelledError:
            _control_interface.info(
                _control_interface.tr("net_core.service.stop_websocket")
            )
            self.finish_close = True

    async def _main(self) -> None:
        """WebSocket 服务器的主循环，负责监听连接并处理通信。"""
        async with websockets.serve(self._handler, self._host, self._port):
            _control_interface.info(
                _control_interface.tr("net_core.service.start_websocket")
            )
            await asyncio.Future()  # 阻塞以保持服务器运行

    # ============ Connect ============
    async def _handler(self, websocket) -> None:
        """处理每个 WebSocket 连接的协程。"""
        server_id = None
        try:
            while True:
                msg = await websocket.recv()
                await self._process_message(msg, websocket, server_id)

        except websockets.exceptions.ConnectionClosed:
            await self._close_connection(server_id, websocket)

    async def _process_message(self, msg: str, websocket, server_id: str) -> None:
        """处理接收到的消息并进行响应。"""
        try:
            msg = json.loads(msg)
            account = msg["account"]
            accounts = _control_interface.get_config("account.json").copy()
            msg_data = self._decrypt_message(msg, account, accounts)

            if msg_data["s"] == 1:
                await self._handle_connection(msg_data, websocket, account)
            else:
                await self._parse_msg(msg_data)

        except Exception as e:
            _control_interface.debug(f"Error with sub-server connection: {e}")
            await websocket.close(reason="400")
            await self._close_connection(server_id, websocket)

    def _decrypt_message(self, msg: dict, account: str, accounts: dict) -> dict:
        """解密消息并返回解密后的数据。"""
        if account == "-----":
            msg = json.loads(aes_decrypt(msg["data"], get_register_password()))
        elif account in accounts:
            msg = json.loads(aes_decrypt(msg["data"], accounts[account]))
        else:
            raise ValueError(f"Unknown Account: {account}")
        return msg

    async def _handle_connection(self, msg: dict, websocket, account: str) -> None:
        """处理新连接或注册请求。"""
        if msg["status"] == "Register":
            await self._register_account(websocket)
        elif msg["status"] == "Connect":
            await self._connect_account(websocket, account, msg)

    async def _register_account(self, websocket) -> None:
        """处理账户注册。"""
        await asyncio.sleep(0.3)
        await self._send(
            {"s": 1, "id": "", "from": "-----", "status": "ConnectOK", "data": {}},
            websocket,
        )

    async def _connect_account(self, websocket, account: str, msg: dict) -> None:
        """处理账户连接。"""
        if account == "-----":
            server_id = self._generate_random_id(5)
            while server_id in self.websockets:
                server_id = self._generate_random_id(5)
            password = Fernet.generate_key().decode()
            accounts = _control_interface.get_config("account.json")
            accounts[server_id] = password
            _control_interface.save_config(accounts, "account.json")
            await self._send(
                {
                    "s": 1,
                    "id": server_id,
                    "from": "-----",
                    "status": "Registered",
                    "data": {"password": password},
                },
                websocket,
                account,
            )
        else:
            server_id = account
            self.websockets[server_id] = websocket
            self.broadcast_websockets.add(websocket)
            self.servers_info[server_id] = msg["data"]
            _control_interface.info(
                _control_interface.tr("net_core.service.connect_websocket").format(
                    f"Server {server_id}"
                )
            )
            await self._send(
                {
                    "s": 1,
                    "id": server_id,
                    "from": "-----",
                    "status": "Connected",
                    "data": {},
                },
                websocket,
                server_id,
            )
            await self._broadcast(
                {
                    "s": 2,
                    "id": "all",
                    "from": "-----",
                    "status": "NewServer",
                    "data": {"server_list": list(self.servers_info.keys())},
                }
            )

    async def _close_connection(self, server_id: str = None, websocket=None) -> None:
        """关闭与子服务器的连接并清理相关数据。"""
        if server_id and websocket:
            if server_id in self.websockets:
                del self.websockets[server_id]
            if server_id in self.servers_info:
                del self.servers_info[server_id]
            if websocket in self.broadcast_websockets:
                self.broadcast_websockets.remove(websocket)

            disconnected()
            del_connect(list(self.servers_info.keys()))

            await self._broadcast(
                {
                    "s": 2,
                    "id": "all",
                    "from": "-----",
                    "status": "DelServer",
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

    # ============ Send Data ============
    async def _send(self, data: dict, websocket, account: str = None) -> None:
        """向指定的 WebSocket 客户端发送消息。"""
        accounts = _control_interface.get_config("account.json")
        if account in accounts:
            await websocket.send(
                aes_encrypt(json.dumps(data).encode(), accounts[account])
            )
        elif account == "-----":
            await websocket.send(
                aes_encrypt(json.dumps(data).encode(), get_register_password())
            )
        else:
            await websocket.send(json.dumps(data).encode())

    async def _broadcast(self, data: dict, server_ids: list = []) -> None:
        """广播消息到所有已连接的子服务器。"""
        for server_id in self.websockets.keys():
            if server_id not in server_ids:
                await self._send(data, self.websockets[server_id], server_id)

    async def send_data_to_other_server(
        self,
        f_server_id: str,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: dict,
    ) -> None:
        """发送消息到指定的子服务器。"""
        msg = {
            "s": 0,
            "to": {"id": t_server_id, "pluginid": t_plugin_id},
            "from": {"id": f_server_id, "pluginid": f_plugin_id},
            "status": "SendData",
            "data": data,
        }
        if t_server_id == "all":
            await self._broadcast(msg)
        else:
            await self._send(msg, self.websockets[t_server_id], t_server_id)

    async def send_file_to_other_server(
        self,
        f_server_id: str,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        file_path: str,
        save_path: str,
        except_id: list = [],
    ) -> None:
        """发送文件到指定的子服务器。"""
        try:
            shutil.copy(file_path, "./send_files/")
            file_hash = get_file_hash(file_path)
            msg = {
                "s": 0,
                "to": {"id": t_server_id, "pluginid": t_plugin_id},
                "from": {"id": f_server_id, "pluginid": f_plugin_id},
                "status": "SendFile",
                "file": {
                    "path": f"http://{self.config['ip']}:{self.config['http_port']}/send_files/{os.path.basename(file_path)}",
                    "file_path": os.path.basename(file_path),
                    "hash": file_hash,
                    "save_path": save_path,
                },
            }
            if t_server_id == "all":
                await self._broadcast(msg, except_id)
            else:
                await self._send(msg, self.websockets[t_server_id], t_server_id)
        except Exception as e:
            _control_interface.error(f"Send File Error: {e}")

    # ============= Parse Msg ============
    async def _parse_msg(self, data: dict):
        """解析并处理从子服务器接收到的消息。"""
        if data["s"] == 0:
            if data["status"] == "SendData":
                if data["to"]["id"] == "-----":
                    recv_data(data["to"]["pluginid"], data["data"])
                elif data["to"]["id"] == "all":
                    await self.send_data_to_other_server(
                        data["from"]["id"],
                        data["from"]["pluginid"],
                        "all",
                        data["to"]["pluginid"],
                        data["data"],
                    )
                    recv_data(data["to"]["pluginid"], data["data"])
                else:
                    await self.send_data_to_other_server(
                        data["from"]["id"],
                        data["from"]["pluginid"],
                        data["to"]["id"],
                        data["to"]["pluginid"],
                        data["data"],
                    )
            elif data["status"] == "RecvFile":
                file_hash = data["file"]["hash"]
                self._wait_file_list[file_hash][1].remove(data["from"]["id"])
                _control_interface.info(
                    _control_interface.tr(
                        "net_core.service.sub_server_download_finish"
                    ).format(data["from"]["id"])
                )
                if not self._wait_file_list[file_hash][1]:
                    os.remove(self._wait_file_list[file_hash][0])
                    del self._wait_file_list[file_hash]
            elif data["status"] == "RequestSendFile":
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
                    "status": "SendFileOK",
                    "file": {
                        "path": f"http://{self.config['ip']}:{self.config['http_port']}",
                        "file_path": data["file"]["file_path"],
                        "hash": data["file"]["hash"],
                        "save_path": data["file"]["save_path"],
                    },
                }
                await self._send(
                    msg, self.websockets[data["from"]["id"]], data["from"]["id"]
                )
            elif data["status"] == "SendFile":
                if data["to"]["id"] == "-----":
                    await self._recv_file(data)
                    recv_file(data["to"]["pluginid"], data["file"]["save_path"])
                elif data["to"]["id"] == "all":
                    await self._recv_file(data)
                    recv_file(data["to"]["pluginid"], data["file"]["save_path"])
                    await self.send_file_to_other_server(
                        data["from"]["id"],
                        data["from"]["pluginid"],
                        data["to"]["id"],
                        data["to"]["pluginid"],
                        data["file"]["save_path"],
                        data["file"]["save_path"],
                        [data["from"]["id"]],
                    )
                else:
                    await self.send_file_to_other_server(
                        data["from"]["id"],
                        data["from"]["pluginid"],
                        data["to"]["id"],
                        data["to"]["pluginid"],
                        f"received_files/{os.path.basename(data['file']['file_path'])}",
                        data["file"]["save_path"],
                    )
                    os.remove(
                        f"received_files/{os.path.basename(data['file']['file_path'])}"
                    )

    # ========== Tools ==========
    def _generate_random_id(self, n: int) -> str:
        """生成指定长度的随机字符串，包含字母和数字。"""
        numeric_part = "".join(
            [str(random.randint(0, 9)) for _ in range(random.randint(1, n))]
        )
        alpha_part = "".join(
            [random.choice(string.ascii_letters) for _ in range(n - len(numeric_part))]
        )
        return "".join(random.sample(list(numeric_part + alpha_part), n))

    async def _recv_file(self, data: dict):
        """服务器接收文件"""
        try:
            shutil.copy(
                f"received_files/{os.path.basename(data['file']['file_path'])}",
                data["file"]["save_path"],
            )
            if verify_file_hash(data["file"]["save_path"], data["file"]["hash"]):
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
                    "status": "RecvFile",
                    "file": {"hash": data["file"]["hash"]},
                }
                await self._send(
                    msg, self.websockets[data["from"]["id"]], data["from"]["id"]
                )
                os.remove(
                    f"received_files/{os.path.basename(data['file']['file_path'])}"
                )
            else:
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
                    "status": "SendFileOK",
                    "file": {
                        "path": f"http://{self.config['ip']}:{self.config['http_port']}",
                        "file_path": data["file"]["file_path"],
                        "hash": data["file"]["hash"],
                        "save_path": data["file"]["save_path"],
                    },
                }
                await self._send(
                    msg, self.websockets[data["from"]["id"]], data["from"]["id"]
                )
        except (IOError, OSError) as e:
            _control_interface.error(f"Copy Error: {e}")


@new_thread("Websocket_Server")
def start_mcdr_server() -> None:
    """启用 MCDR 多线程启动 WebSocket 服务器。仅在 MCDR 环境下调用。"""
    global websocket_server
    websocket_server = WebsocketServer()
    websocket_server.start_server()


# public
def websocket_server_main(control_interface: "CoreControlInterface"):
    """初始化 WebSocket 服务器。根据环境选择启动 MCDR 多线程服务器或普通服务器。"""
    global _control_interface
    _control_interface = control_interface
    if get_mcdr():
        start_mcdr_server()
    else:
        global websocket_server
        websocket_server = WebsocketServer()
        websocket_server.start_server()


def send_data(
    f_server_id: str, f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict
) -> None:
    """发送消息到指定的子服务器。"""
    asyncio.run(
        websocket_server.send_data_to_other_server(
            f_server_id, f_plugin_id, t_server_id, t_plugin_id, data
        )
    )


def send_file(
    f_server_id: str,
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    """发送文件到指定的子服务器。"""
    asyncio.run(
        websocket_server.send_file_to_other_server(
            f_server_id, f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
        )
    )
