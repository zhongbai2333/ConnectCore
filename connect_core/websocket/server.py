import websockets
import asyncio
import shutil
import json
import os
from connect_core.websocket.data_packet import ServerDataPacket
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.account.register_system import get_register_password
from connect_core.plugin.init_plugin import del_connect, disconnected
from connect_core.tools import new_thread, auto_trigger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

_control_interface, websocket_server = None, None


class WebsocketServer(object):
    """WebSocket 服务器的主类，负责管理 WebSocket 连接和通信。"""

    def __init__(self):
        self._config = _control_interface.get_config()
        self.finish_close = False
        self._host = self._config["ip"]
        self._port = self._config["port"]
        self.websockets = {}
        self.servers_info = {}
        self.last_send_packet = {}
        self.data_packet = ServerDataPacket(_control_interface, self)

    # =========== Control ===========
    def start_server(self) -> None:
        """启动 WebSocket 服务器。"""
        asyncio.run(self._init_main())

    def close_server(self) -> None:
        """关闭 WebSocket 服务器。"""
        self._start_resend.stop()
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
        except websockets.exceptions.ConnectionClosed as e:
            if str(e) == "sent 1000 (OK) 401; then received 1000 (OK) 401":
                pass
            else:
                if "account" in msg.keys():
                    await self._close_connection(server_id, websocket)

    async def _process_message(self, msg: str, websocket, server_id: str) -> None:
        """处理接收到的消息并进行响应。

        Args:
            msg (str): 收到的原始消息。
            websocket: WebSocket 对象。
            server_id (str): 消息对应的服务器 ID。
        """
        try:
            accounts = _control_interface.get_config("account.json").copy()
            msg_data = self._decrypt_message(msg, server_id, accounts)
            await self._parse_msg(msg_data, websocket)
        except ValueError as ve:
            _control_interface.warn(
                f"Failed to process message from server {server_id}: {ve}"
            )
            await websocket.close(reason="400")
            await self._close_connection(server_id, websocket)
        except Exception as e:
            _control_interface.error(f"Unexpected error during message processing: {e}")
            await websocket.close(reason="500")
            await self._close_connection(server_id, websocket)

    def _decrypt_message(self, msg: dict, account: str, accounts: dict) -> dict:
        """解密消息并返回解密后的数据。

        Args:
            msg (dict): 接收到的原始消息。
            account (str): 当前账户名。
            accounts (dict): 配置中所有账户。

        Returns:
            dict: 解密后的消息内容。

        Raises:
            ValueError: 如果账户未知或消息解密失败。
        """
        if account not in accounts and account != "-----":
            raise ValueError(f"Unknown account: {account}")

        key = get_register_password() if account == "-----" else accounts[account]
        try:
            return json.loads(aes_decrypt(msg["data"], key))
        except Exception as e:
            raise ValueError(f"Failed to decrypt message for account {account}: {e}")

    async def _close_connection(self, server_id: str = None, websocket=None) -> None:
        """关闭与子服务器的连接并清理相关数据。"""
        if server_id != "-----" and websocket:
            if server_id in self.websockets.keys():
                del self.websockets[server_id]
            if server_id in self.servers_info.keys():
                del self.servers_info[server_id]
            if server_id in self.last_send_packet.keys():
                del self.last_send_packet[server_id]

            self.data_packet.del_server_id(server_id)

            disconnected()
            del_connect(list(self.servers_info.keys()))

            await self.broadcast(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_DEL_LOGIN,
                    self.data_packet.DEFAULT_ALL,
                    self.data_packet.DEFAULT_SERVER,
                    {"server_list": list(self.servers_info.keys())},
                )
            )
            _control_interface.info(
                _control_interface.tr(
                    "net_core.service.disconnect_from_sub_websocket", server_id
                )
            )
        else:
            _control_interface.warn(
                _control_interface.tr(
                    "net_core.service.disconnect_from_unknown_websocket"
                )
            )

    # ============ Send Data ============
    async def send(self, data: dict, websocket, account: str) -> None:
        """向指定的 WebSocket 客户端发送消息。"""
        if data is None:
            return
        if account in data.keys():
            data = data[account]
        _control_interface.debug(
            f"[S][{data['type']}][{data['from']} -> {data['to']}({account})][{data['sid']}] {data['data']}"
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

    async def broadcast(self, data: dict, except_id: list = []) -> None:
        """广播消息到所有已连接的子服务器。"""
        for server_id in data.keys():
            if server_id not in except_id:
                await self.send(data[server_id], self.websockets[server_id], server_id)

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
            for i in self.servers_info.keys():
                self.last_send_packet[i] = msg
            await self.broadcast(msg, except_id)
        else:
            self.last_send_packet[t_server_id] = msg
            await self.send(msg[t_server_id], self.websockets[t_server_id], t_server_id)

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
                await self.broadcast(
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
                await self.send(
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
                        await self.broadcast(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_SENDING,
                                (t_server_id, t_plugin_id),
                                (f_server_id, f_plugin_id),
                                {"file": chunk.hex()},
                            ),
                            except_id,
                        )
                    else:
                        await self.send(
                            self.data_packet.get_data_packet(
                                self.data_packet.TYPE_FILE_SENDING,
                                (t_server_id, t_plugin_id),
                                (f_server_id, f_plugin_id),
                                {"file": chunk.hex()},
                            ),
                            self.websockets[t_server_id],
                            t_server_id,
                        )
                    await asyncio.sleep(0.1)  # 控制发送间隔（可选）

            # 发送结束标志
            if t_server_id == "all":
                await self.broadcast(
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
                await self.send(
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
                await self.broadcast(self.last_send_packet[i])
            else:
                await self.send(self.last_send_packet[i], self.websockets[i], i)

    # ============ Prase Data ============
    async def _parse_msg(self, data: dict, websocket) -> None:
        """解析并处理从子服务器接收到的消息。"""
        await self.data_packet.parse_msg(data, websocket)

    # ========== Tools ==========
    @auto_trigger(interval=30, thread_name="resend")
    def _start_resend(self) -> None:
        """启动PING PONG数据包服务"""
        asyncio.run(self._resend())

    def get_history_data_packet(self, server_id) -> list:
        """获取历史数据包"""
        if server_id in self.websockets.keys():
            return self.data_packet.get_history_packet(server_id, 0)


# public
@new_thread("websocket_server")
def websocket_server_main(control_interface: "CoreControlInterface"):
    """初始化 WebSocket 服务器。根据环境选择启动 MCDR 多线程服务器或普通服务器。"""
    global websocket_server, _control_interface
    _control_interface = control_interface
    websocket_server = WebsocketServer()
    websocket_server.start_server()


def websocket_server_stop() -> None:
    """停止 WebSocket 服务器。"""
    if websocket_server is not None:
        websocket_server.close_server()


def send_data(
    f_server_id: str, f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict
) -> None:
    """发送消息到指定的子服务器。"""
    asyncio.run(
        websocket_server.send_data_to_other_server(
            f_server_id, f_plugin_id, t_server_id, t_plugin_id, data
        )
    )


@new_thread("SendFile")
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


def get_history_data_packet(server_id) -> list:
    """获取历史数据包"""
    return websocket_server.get_history_data_packet(server_id)
