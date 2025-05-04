import os
import sys
import time
import json
import asyncio
import threading
import websockets
from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.tools import new_thread, auto_trigger
from connect_core.websocket.data_packet import ClientDataPacket
from connect_core.plugin.init_plugin import disconnected, websockets_started

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

_control_interface = None


class WebsocketClient(object):
    """
    WebSocket 客户端的主类，负责与服务器建立连接、发送和接收消息。
    """

    def __init__(self):
        self.config = _control_interface.get_config()
        self.finish_start = False
        self.finish_close = False
        self.host = self.config["ip"]
        self.port = self.config["port"]
        self.websocket = None
        self._main_task = None
        self._receive_task = None
        self.server_id = None
        self.last_data_packet = None
        self.data_packet = ClientDataPacket(_control_interface, self)

        # 创建独立事件循环和线程
        self.loop = asyncio.new_event_loop()
        self.loop_thread = None

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_server(self) -> None:
        """
        启动 WebSocket 客户端：在独立线程运行事件循环，并调度主协程。
        """
        self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.loop_thread.start()
        asyncio.run_coroutine_threadsafe(self._init_main(), self.loop)

    def stop_server(self) -> None:
        """
        停止 WebSocket 客户端：取消任务，停止循环并等待线程退出。
        """
        self._start_trigger_websocket_client.stop()
        if self._receive_task:
            self.loop.call_soon_threadsafe(self._receive_task.cancel)
        elif self._main_task:
            self.loop.call_soon_threadsafe(self._main_task.cancel)
        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.loop_thread:
            self.loop_thread.join()
        self.finish_close = True

    async def _init_main(self) -> None:
        """
        初始化并运行主连接循环，支持重试机制。
        """
        self._main_task = asyncio.current_task(loop=self.loop)
        try:
            while True:
                try:
                    uri = f"ws://{self.host}:{self.port}"
                    self.websocket = await websockets.connect(uri)
                    self.finish_start = True
                    _control_interface.info(
                        _control_interface.tr("net_core.service.connect_websocket", "")
                    )
                    websockets_started()
                    await self._receive()
                    break
                except (ConnectionRefusedError, OSError):
                    self.finish_start = False
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.finish_close = True
            _control_interface.info(
                _control_interface.tr("net_core.service.stop_websocket")
            )

    # ========
    #   recv
    # ========
    async def _get_recv(self) -> str | None:
        """
        从服务器收消息；如果是超时就继续等待，
        如果是 401（重复登录）就停掉客户端并返回 None，
        其它情况才走断线重连逻辑。
        """
        while True:
            try:
                return await asyncio.wait_for(self.websocket.recv(), timeout=4)
            except asyncio.TimeoutError:
                # 只是超时，继续等
                continue
            except websockets.ConnectionClosed as e:
                code = getattr(e, "code", None)
                reason = getattr(e, "reason", "")
                # —— 重复登录（Already Login），服务器发 code=1008, reason 包含 "401"
                if code == 1008 and "401" in reason:
                    _control_interface.error(
                        _control_interface.tr("net_core.service.already_login")
                    )
                    # 停掉自己，不再重连
                    self.stop_server()
                    return None

                # —— 密码错误分支，如果你也用 1008+HTTP 400
                if code == 1008 and "400" in reason:
                    _control_interface.error(
                        _control_interface.tr("net_core.service.error_password")
                    )
                    self.stop_server()
                    return None

                # —— 其他任何关闭，都走断线重连
                _control_interface.info(
                    _control_interface.tr("net_core.service.disconnect_websocket")
                    + f" code={code} reason={reason}"
                )
                # 停了定时器，触发上层重连逻辑
                self._start_trigger_websocket_client.stop()
                disconnected()
                websocket_client_main(_control_interface)
                return None

    async def _receive(self) -> None:
        """
        接收并处理从服务器发送的消息。
        初始连接时会向服务器发送连接状态消息。
        """
        if self.config["account"] != "-----":
            await self.send(
                self.data_packet.get_data_packet(
                    self.data_packet.TYPE_LOGIN,
                    self.data_packet.DEFAULT_SERVER,
                    (self.config["account"], "system"),
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
                    self._parse_msg(recv_data)
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
    async def send(self, data: dict, account: str = None) -> None:
        """
        向服务器发送消息。

        Args:
            data (dict): 要发送的消息内容。
            account (str): 账号, 默认为None
        """
        data = data["-----"]
        if account is None:
            account = self.config["account"]
        _control_interface.debug(
            f"[S][{data['type']}][{data['from']} -> {data['to']}][{data['sid']}] {data['data']}"
        )
        try:
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
        except (websockets.exceptions.ConnectionClosedError) or (
            websockets.exceptions.ConnectionClosedOK
        ):
            pass

    async def _trigger_websocket_client(self) -> None:
        # 如果有上一个数据包，则发送上一个数据包
        await asyncio.sleep(5)
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
        if t_server_id != "all" and t_server_id != "-----" and t_server_id not in self.data_packet.server_list:
            _control_interface.log_system.error(
                f"Unable to send data to server {t_server_id}"
            )
            return
        msg = self.data_packet.get_data_packet(
            self.data_packet.TYPE_DATA_SEND,
            (t_server_id, t_plugin_id),
            (self.server_id, f_plugin_id),
            data,
        )
        self.last_data_packet = msg
        await self.send(msg)

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
        if t_server_id != "all" and t_server_id != "-----" and t_server_id not in self.data_packet.server_list:
            _control_interface.log_system.error(
                f"Unable to send data to server {t_server_id}"
            )
            return
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
                )
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
                            {"file": chunk.hex()},
                        )
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
                )
            )
        except Exception as e:
            _control_interface.error(f"Send File Error: {e}")

    # =============
    #   Parse Msg
    # =============
    @new_thread("Prase_Msg")
    def _parse_msg(self, data: dict) -> None:
        """
        解析并处理从服务器接收到的消息。
        如果消息中包含服务器 ID，则更新客户端的服务器 ID。

        Args:
            data (dict): 从服务器接收到的消息内容。
        """
        asyncio.run(self.data_packet.parse_msg(data))

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


def websocket_client_stop() -> WebsocketClient | None:
    """停止 WebSocket 客户端"""
    try:
        websocket_client.stop_server()
        return websocket_client
    except Exception:
        return None


def _schedule_on_client_loop(coro):
    """
    将 coroutine 提交到 websocket_client.loop 并返回 concurrent.futures.Future。
    如果 loop 没有运行，会记录一条错误日志。
    """
    loop = websocket_client.loop
    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        _control_interface.error("WebSocket 客户端事件循环未运行，无法调度协程")
        return None


def send_data(f_plugin_id: str, t_server_id: str, t_plugin_id: str, data: dict) -> None:
    """
    发送消息到指定的子服务器，不再使用 asyncio.run，而是提交到后台 loop。
    """
    coro = websocket_client.send_data_to_other_server(
        f_plugin_id, t_server_id, t_plugin_id, data
    )
    _schedule_on_client_loop(coro)


@new_thread("SendFile")
def send_file(
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    """
    发送文件到指定的子服务器，同样使用线程安全的协程调度。
    """
    coro = websocket_client.send_file_to_other_server(
        f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
    )
    _schedule_on_client_loop(coro)


def get_server_id() -> str:
    """
    获取客户端ID

    Returns:
        str: 服务器ID
    """
    return websocket_client.server_id


def get_server_list() -> list:
    """
    获取子服务器列表
    Returns:
        list: 子服务器列表
    """
    return websocket_client.data_packet.server_list


def get_history_data_packet() -> list:
    """获取历史数据包"""
    return websocket_client.get_history_data_packet()
