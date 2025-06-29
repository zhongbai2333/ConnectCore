import websockets
import threading
import asyncio
import shutil
import json
import os
from connect_core.websocket.data_packet import ServerDataPacket
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.account.register_system import get_register_password
from connect_core.plugin.init_plugin import del_connect, websockets_started
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

        # 手动创建事件循环和线程
        self.loop = asyncio.new_event_loop()
        self.server = None
        self.loop_thread = None

    # =========== Control ===========
    def start_server(self) -> None:
        """启动 WebSocket 服务器：启动事件循环线程并调度主协程"""
        # 启动守护线程
        self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.loop_thread.start()
        # 在新循环中调度 _main
        asyncio.run_coroutine_threadsafe(self._main(), self.loop)

    def close_server(self) -> None:
        """
        关闭 WebSocket 服务器：优雅地 cancel 重发、关闭所有连接、
        停止 serve、停止 loop 并等待线程退出。
        """
        # 1. 停掉自动重发定时器
        self._start_resend.stop()

        # 2. 在事件循环中调度优雅关机协程，并等待它完成
        async def _graceful_shutdown():
            # 2.1 取消掉所有正在跑的任务（如果有存）
            #     （如果你自己存了 _main_task、_handler_task 等，也一并 cancel）
            # 2.2 优雅地 close 每一个客户端连接
            for ws in list(self.websockets.values()):
                try:
                    await ws.close(code=1000, reason="Server shutdown")
                except Exception:
                    pass
            # 2.3 关闭 serve 本身，停止接收新连接
            if self.server:
                self.server.close()
                await self.server.wait_closed()

        if self.loop.is_running():
            f = asyncio.run_coroutine_threadsafe(_graceful_shutdown(), self.loop)
            try:
                # 最多等 3 秒，防止卡住
                f.result(timeout=3)
            except Exception:
                pass

        # 3. 停掉事件循环
        self.loop.call_soon_threadsafe(self.loop.stop)
        # 4. 等线程退出
        if self.loop_thread:
            self.loop_thread.join(timeout=3)

        self.finish_close = True

    # ========== Core ==========
    async def _main(self) -> None:
        """初始化并启动主 WebSocket 服务协程"""
        try:
            # 不使用 async with，直接获取 server 对象
            self.server = await websockets.serve(self._handler, self._host, self._port)
            _control_interface.info(
                _control_interface.tr("net_core.service.start_websocket")
            )
            websockets_started()
            # 启动定时重发
            self._start_resend()
            # 等待服务器关闭
            await self.server.wait_closed()
        except Exception as e:
            _control_interface.log_system.error(
                _control_interface.tr("net_core.service.start_websocket_error")
            )
            self.finish_close = True

    def _run_loop(self) -> None:
        """事件循环线程入口"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    # ============ Connect ============
    async def _handler(self, websocket) -> None:
        """处理每个 WebSocket 连接的协程。"""
        try:
            while True:
                recv = await websocket.recv()
                _control_interface.log_system.debug("recv:" + str(recv))
                msg = json.loads(recv)
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
            code = getattr(e, "code", None)
            reason = getattr(e, "reason", "")
            # 重复登录 -> code=1008, reason 包含 "401"
            if code == 1008 and "401" in reason:
                _control_interface.error(_control_interface.tr("net_core.service.already_login_server", server_id))
                # 不走正常断开逻辑
                return
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
            accounts = _control_interface.get_config(config_path="account.json").copy()
            msg_data = self._decrypt_message(msg, server_id, accounts)
            self._parse_msg(msg_data, websocket)
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

    async def close_connect(self, server_id: str, reason: int, ws=None) -> None:
        """关闭与子服务器的连接并清理相关数据。"""
        if ws is None:
            ws = self.websockets.get(server_id)
        if ws:
            try:
                # 用 1008（policy violation）或者 1000（normal）等合法码，
                # 把 http_code 放到 reason 字符串里
                await ws.close(code=1008, reason=f"HTTP {reason}")
            except Exception as e:
                _control_interface.error(f"Close connect error for {server_id}: {e}")

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

            del_connect(server_id)

            await self.broadcast(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_DEL_LOGIN,
                    self.data_packet.DEFAULT_ALL,
                    self.data_packet.DEFAULT_SERVER,
                    {"server_id": server_id},
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

        accounts = _control_interface.get_config(config_path="account.json")
        try:
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
        except (websockets.exceptions.ConnectionClosedError) or (
            websockets.exceptions.ConnectionClosedOK
        ):
            pass

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
        elif t_server_id not in self.websockets.keys():
            _control_interface.log_system.error(
                f"Unable to send data to server {t_server_id}"
            )
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
            elif t_server_id not in self.websockets.keys():
                _control_interface.log_system.error(
                    f"Unable to send data to server {t_server_id}"
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
                    elif t_server_id not in self.websockets.keys():
                        _control_interface.log_system.error(
                            f"Unable to send data to server {t_server_id}"
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
            elif t_server_id not in self.websockets.keys():
                _control_interface.log_system.error(
                    f"Unable to send data to server {t_server_id}"
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
    @new_thread("Parse_Msg")
    def _parse_msg(self, data: dict, websocket) -> None:
        """解析并处理从子服务器接收到的消息。"""
        try:
            asyncio.run_coroutine_threadsafe(
                self.data_packet.parse_msg(data, websocket), self.loop
            )
        except Exception as e:
            _control_interface.error(f"Parse message error: {e}")

    # ========== Tools ==========
    @auto_trigger(interval=30, thread_name="resend")
    def _start_resend(self) -> None:
        """启动PING PONG数据包服务"""
        try:
            asyncio.run_coroutine_threadsafe(self._resend(), self.loop)
        except Exception as e:
            _control_interface.error(f"Resend scheduling error: {e}")

    def get_history_data_packet(self, server_id) -> list:
        """获取历史数据包"""
        if server_id in self.websockets.keys():
            return self.data_packet.get_history_packet(server_id, 0)


# public
@new_thread("websocket_server")
def websocket_server_main(control_interface: "CoreControlInterface"):
    global websocket_server, _control_interface
    _control_interface = control_interface
    websocket_server = WebsocketServer()
    websocket_server.start_server()


def websocket_server_stop() -> WebsocketServer | None:
    try:
        return websocket_server and websocket_server.close_server()
    except Exception:
        return None


def _schedule_on_ws_loop(coro):
    """
    将 coroutine 提交到 websocket_server.loop 并返回 concurrent.futures.Future，
    如果 loop 没在跑，会在日志里报错。
    """
    loop = websocket_server.loop
    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        _control_interface.error("WebSocket 事件循环未运行，无法调度协程")
        return None


def send_data(
    f_server_id: str, f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict
) -> None:
    """
    发送消息到指定的子服务器。不会阻塞当前线程，
    协程会在后台 loop 中执行。
    """
    try:
        coro = websocket_server.send_data_to_other_server(
            f_server_id, f_plugin_id, t_server_id, t_plugin_id, data
        )
        _schedule_on_ws_loop(coro)
    except NameError:
        pass


@new_thread("SendFile")
def send_file(
    f_server_id: str,
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    """
    与 send_data 类似，把文件传输的协程调度到后台 loop。
    """
    try:
        coro = websocket_server.send_file_to_other_server(
            f_server_id, f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
        )
        _schedule_on_ws_loop(coro)
    except NameError:
        pass


def get_server_list() -> list:
    """获取服务器列表"""
    return list(websocket_server.servers_info.keys())


def get_history_data_packet(server_id) -> list:
    """获取历史数据包"""
    return websocket_server.get_history_data_packet(server_id)
