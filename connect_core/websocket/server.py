import websockets
import asyncio
import shutil
import random
import string
import json
import os
from cryptography.fernet import Fernet
from connect_core.websocket.data_packet import DataPacket
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.account.register_system import get_register_password
from connect_core.plugin.init_plugin import (
    new_connect,
    del_connect,
    disconnected,
    recv_data,
    recv_file,
)
from connect_core.tools import new_thread, auto_trigger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

_control_interface = None


class WebsocketServer(object):
    """WebSocket 服务器的主类，负责管理 WebSocket 连接和通信。"""

    def __init__(self):
        self._config = _control_interface.get_config()
        self.finish_close = False
        self._host = self._config["ip"]
        self._port = self._config["port"]
        self.websockets = {}
        self.servers_info = {}
        self._wait_file_list = {}
        self._wait_register_connect = {}
        self.last_send_packet = {}
        self.data_packet = DataPacket()

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
            self._start_resend()
            await asyncio.Future()  # 阻塞以保持服务器运行

    # ============ Connect ============
    async def _handler(self, websocket) -> None:
        """处理每个 WebSocket 连接的协程。"""
        try:
            while True:
                msg = json.loads(await websocket.recv())
                if "account" in msg.keys():
                    server_id = msg["account"]
                    await self._process_message(msg, websocket, server_id)
                else:
                    await websocket.send(
                        json.dumps(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_TEST_CONNECT,
                                self.data_packet.DEFAULT_TO_FROM,
                                self.data_packet.DEFAULT_TO_FROM,
                                None,
                            )["-----"]
                        )
                    )
                    await websocket.close(reason="200")
        except websockets.exceptions.ConnectionClosed:
            if "account" in msg.keys():
                await self._close_connection(server_id, websocket)

    async def _process_message(self, msg: str, websocket, server_id: str) -> None:
        """处理接收到的消息并进行响应。"""
        accounts = _control_interface.get_config("account.json").copy()
        try:
            msg_data = self._decrypt_message(msg, server_id, accounts)
            await self._parse_msg(msg_data, websocket)
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

    async def _close_connection(self, server_id: str = None, websocket = None) -> None:
        """关闭与子服务器的连接并清理相关数据。"""
        if server_id != "-----" and websocket:
            if server_id in self.websockets:
                del self.websockets[server_id]
            if server_id in self.servers_info:
                del self.servers_info[server_id]

            self.data_packet.del_server_id(server_id)
            self._start_resend.stop()

            disconnected()
            del_connect(list(self.servers_info.keys()))

            await self._broadcast(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_DEL_LOGIN,
                    self.data_packet.DEFAULT_ALL,
                    self.data_packet.DEFAULT_SERVER,
                    {"server_list": list(self.servers_info.keys())},
                )
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
    async def _send(
        self, data: dict, websocket, account: str
    ) -> None:
        """向指定的 WebSocket 客户端发送消息。"""
        if account in data.keys():
            data = data[account]
        _control_interface.debug(
            f"[S][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )

        accounts = _control_interface.get_config("account.json")
        if account == "-----":
            await websocket.send(
                aes_encrypt(json.dumps(data).encode(), get_register_password())
            )
        elif account in accounts:
            await websocket.send(
                aes_encrypt(json.dumps(data).encode(), accounts[account])
            )
        else:
            raise ValueError(f"Unknown Account: {account}")

    async def _broadcast(self, data: dict, server_ids: list = []) -> None:
        """广播消息到所有已连接的子服务器。"""
        for server_id in self.websockets.keys():
            if server_id not in server_ids:
                await self._send(data[server_id], self.websockets[server_id], server_id)

    async def send_data_to_other_server(
        self,
        f_server_id: str,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: dict,
        except_id: list = [],
    ) -> None:
        """发送消息到指定的子服务器。"""
        msg = self.data_packet.get_data_packet(
            self.data_packet.TYPE_DATA_SEND,
            (t_server_id, t_plugin_id),
            (f_server_id, f_plugin_id),
            data,
        )
        if t_server_id == "all":
            self.last_send_packet[t_server_id] = msg
            await self._broadcast(msg, except_id)
        else:
            self.last_send_packet[t_server_id] = msg
            await self._send(
                msg[t_server_id], self.websockets[t_server_id], t_server_id
            )

    @new_thread("SendFile")
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
            file_hash = self.data_packet.get_file_hash(file_path)
            if os.path.basename(file_path) != os.path.basename(save_path):
                save_path = os.path.join(file_path, os.path.basename(file_path))
            # 向服务器发送请求，告诉服务端开始文件传输
            if t_server_id == "all":
                await self._broadcast(
                    self.data_packet.get_data_packet(
                        self.data_packet.TYPE_FILE_SEND,
                        (t_server_id, t_plugin_id),
                        (f_server_id, f_plugin_id),
                        {
                            "file_name": os.path.basename(file_path),
                            "save_path": save_path,
                            "hash": file_hash,
                        },
                    ),
                    except_id,
                )
            else:
                await self._send(
                    self.data_packet.get_data_packet(
                        self.data_packet.TYPE_FILE_SEND,
                        (t_server_id, t_plugin_id),
                        (f_server_id, f_plugin_id),
                        {
                            "file_name": os.path.basename(file_path),
                            "save_path": save_path,
                            "hash": file_hash,
                        },
                    ),
                    self.websockets[t_server_id],
                    t_server_id,
                )

            # 读取文件并分块发送数据
            with open(f"./send_files/{os.path.basename(file_path)}", "rb") as file:
                chunk_size = 1024 * 1024  # 每次发送 1 MB
                while chunk := file.read(chunk_size):
                    if t_server_id == "all":
                        await self._broadcast(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_SENDING,
                                (t_server_id, t_plugin_id),
                                (f_server_id, f_plugin_id),
                                {"file": chunk},
                            ),
                            except_id,
                        )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_SENDING,
                                (t_server_id, t_plugin_id),
                                (f_server_id, f_plugin_id),
                                {"file": chunk},
                            ),
                            self.websockets[t_server_id],
                            t_server_id,
                        )
                    await asyncio.sleep(0.1)  # 控制发送间隔（可选）

            # 发送结束标志
            if t_server_id == "all":
                await self._broadcast(
                    self.data_packet.get_data_packet(
                        self.data_packet.TYPE_FILE_SENDOK,
                        (t_server_id, t_plugin_id),
                        (f_server_id, f_plugin_id),
                        {
                            "file_name": os.path.basename(file_path),
                            "save_path": save_path,
                            "hash": file_hash,
                        },
                    ),
                    except_id,
                )
            else:
                await self._send(
                    self.data_packet.get_data_packet(
                        self.data_packet.TYPE_FILE_SENDOK,
                        (t_server_id, t_plugin_id),
                        (f_server_id, f_plugin_id),
                        {
                            "file_name": os.path.basename(file_path),
                            "save_path": save_path,
                            "hash": file_hash,
                        },
                    ),
                    self.websockets[t_server_id],
                    t_server_id,
                )
        except Exception as e:
            _control_interface.error(f"Send File Error: {e}")

    async def _resend(self) -> None:
        """定时重发数据包。"""
        for i in self.last_send_packet.keys():
            if i == "all":
                await self._broadcast(self.last_send_packet[i])
            else:
                await self._send(self.last_send_packet[i], self.websockets[i], i)

    # ============ Prase Data ============
    async def _parse_msg(self, data: dict, websocket) -> None:
        """解析并处理从子服务器接收到的消息。"""
        server_id = data["from"][0]
        to_server_id = data["to"][0]
        data_type = tuple(data["type"])
        self.data_packet.add_recv_packet(server_id, data)
        _control_interface.debug(
            f"[R][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )
        if to_server_id == "-----" or to_server_id == "all":
            if to_server_id == "all":
                await self._broadcast(data)
            match data_type:
                # PING 数据包
                case self.data_packet.TYPE_PING:
                    history_packet = self.data_packet.get_history_packet(
                        server_id, data["sid"]
                    )
                    if not history_packet:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_PONG,
                                (server_id, "system"),
                                self.data_packet.DEFAULT_SERVER,
                                None,
                            ),
                            websocket,
                            server_id,
                        )
                    else:
                        for i in history_packet:
                            await self._send(
                                i,
                                websocket,
                                server_id,
                            )

                # Control 数据包
                case self.data_packet.TYPE_CONTROL_STOP:  # 占位
                    pass  # TODO

                # Registar 数据包
                case self.data_packet.TYPE_REGISTER:
                    server_id = self._generate_random_id(5)
                    while server_id in self.websockets:
                        server_id = self._generate_random_id(5)
                    password = Fernet.generate_key().decode()
                    accounts = _control_interface.get_config("account.json")
                    accounts[server_id] = password
                    _control_interface.save_config(accounts, "account.json")
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_REGISTERED,
                            (server_id, "system"),
                            self.data_packet.DEFAULT_SERVER,
                            {"password": password},
                        )[server_id],
                        websocket,
                        "-----",
                    )
                case self.data_packet.TYPE_REGISTER_ERROR:
                    server_id = self._generate_random_id(5)
                    while server_id in self.websockets:
                        server_id = self._generate_random_id(5)
                    password = Fernet.generate_key().decode()
                    accounts = _control_interface.get_config("account.json")
                    del accounts[list(accounts.keys())[-1]]
                    accounts[server_id] = password
                    _control_interface.save_config(accounts, "account.json")
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_REGISTERED,
                            (server_id, "system"),
                            self.data_packet.DEFAULT_SERVER,
                            {"password": password},
                        )[server_id],
                        websocket,
                        "-----",
                    )

                # Login 数据包
                case self.data_packet.TYPE_LOGIN:
                    self.websockets[server_id] = websocket
                    self.servers_info[server_id] = data["data"]["payload"]
                    _control_interface.info(
                        _control_interface.tr(
                            "net_core.service.connect_websocket"
                        ).format(f"Server {server_id}")
                    )
                    await self._send(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_LOGINED,
                            (server_id, "system"),
                            self.data_packet.DEFAULT_SERVER,
                            None,
                        ),
                        websocket,
                        server_id,
                    )
                    new_connect(list(self.servers_info.keys()))
                    await self._broadcast(
                        self.data_packet.get_data_packet(
                            self.data_packet.TYPE_NEW_LOGIN,
                            self.data_packet.DEFAULT_ALL,
                            self.data_packet.DEFAULT_SERVER,
                            {"server_list": list(self.servers_info.keys())},
                        )
                    )

                # Data 数据包
                case self.data_packet.TYPE_DATA_SEND:
                    # 发送数据
                    if data["data"] and self.data_packet.verify_md5_checksum(
                        data["data"]["payload"], data["data"]["checksum"]
                    ):
                        if not data["data"]:
                            data["data"]["payload"] = {}
                        recv_data(data["from"][1], data["data"]["payload"])
                        self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_DATA_SENDOK,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                None,
                            ),
                            websocket,
                            server_id,
                        )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_DATA_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            ),
                            websocket,
                            server_id,
                        )
                case self.data_packet.TYPE_DATA_SENDOK:
                    # 接收数据
                    del self.last_send_packet[server_id]
                case self.data_packet.TYPE_DATA_ERROR:
                    # 数据错误
                    if server_id in self.last_send_packet.keys():
                        await self._send(
                            self.last_send_packet[server_id],
                            websocket,
                            server_id,
                        )

                # File 数据包
                case self.data_packet.TYPE_FILE_SEND:
                    if self.data_packet.verify_md5_checksum(
                        data["data"]["payload"], data["data"]["checksum"]
                    ):
                        self._wait_file_list[server_id] = open(
                            data["data"]["payload"]["save_path"], "wb"
                        )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            ),
                            websocket,
                            server_id,
                        )
                case self.data_packet.TYPE_FILE_SENDING:
                    if self.data_packet.verify_md5_checksum(
                        data["data"]["payload"], data["data"]["checksum"]
                    ):
                        if server_id in self._wait_file_list:
                            self._wait_file_list[server_id].write(
                                data["data"]["payload"]["file"]
                            )
                            self._wait_file_list[server_id].flush()
                        else:
                            await self._send(
                                self.data_packet.get_data_packet(
                                    self.data_packet.TYPE_FILE_ERROR,
                                    data["from"],
                                    self.data_packet.DEFAULT_SERVER,
                                    {"to": data["to"]},
                                ),
                                websocket,
                                server_id,
                            )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            ),
                            websocket,
                            server_id,
                        )
                case self.data_packet.TYPE_FILE_SENDOK:
                    if self.data_packet.verify_md5_checksum(
                        data["data"]["payload"], data["data"]["checksum"]
                    ):
                        if server_id in self._wait_file_list:
                            self._wait_file_list[server_id].close()
                            if self.data_packet.verify_file_hash(
                                data["data"]["payload"]["save_path"],
                                data["data"]["payload"]["hash"],
                            ):
                                recv_file(
                                    data["from"][1],
                                    data["data"]["payload"]["save_path"],
                                )
                            else:
                                await self._send(
                                    self.data_packet.get_data_packet(
                                        self.data_packet.TYPE_FILE_ERROR,
                                        data["from"],
                                        self.data_packet.DEFAULT_SERVER,
                                        {"to": data["to"]},
                                    ),
                                    websocket,
                                    server_id,
                                )
                        else:
                            await self._send(
                                self.data_packet.get_data_packet(
                                    self.data_packet.TYPE_FILE_ERROR,
                                    data["from"],
                                    self.data_packet.DEFAULT_SERVER,
                                    {"to": data["to"]},
                                ),
                                websocket,
                                server_id,
                            )
                    else:
                        await self._send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_ERROR,
                                data["from"],
                                self.data_packet.DEFAULT_SERVER,
                                {"to": data["to"]},
                            ),
                            websocket,
                            server_id,
                        )

                case _:
                    pass
        else:
            await self._send(data, self.websockets[to_server_id], to_server_id)

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

    @auto_trigger(interval=30, thread_name="resend")
    def _start_resend(self) -> None:
        """启动PING PONG数据包服务"""
        asyncio.run(self._resend())


# public
@new_thread("websocket_server")
def websocket_server_main(control_interface: "CoreControlInterface"):
    """初始化 WebSocket 服务器。根据环境选择启动 MCDR 多线程服务器或普通服务器。"""
    global websocket_server, _control_interface
    _control_interface = control_interface
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
