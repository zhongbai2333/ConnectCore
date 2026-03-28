from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import Future
from typing import Any, Awaitable, Dict, Optional, TYPE_CHECKING

import websockets
from websockets.client import WebSocketClientProtocol  # type: ignore[attr-defined]
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
)

from connect_core.aes_encrypt import aes_decrypt, aes_encrypt
from connect_core.plugin.init_plugin import disconnected, websockets_started
from connect_core.tools.common import get_file_hash
from connect_core.websockets.data_packet import (
    ClientDataPacket,
    PacketType,
    PROTOCOL_VERSION,
    DEFAULT_SERVER,
    DEFAULT_TEMP,
)

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface


_control_interface: Optional["CoreControlInterface"] = None
websocket_client: Optional["WebsocketClient"] = None


class WebsocketClient:
    """WebSocket 客户端，实现子服务器与主服务器之间的数据通讯。"""

    def __init__(self, control_interface: "CoreControlInterface") -> None:
        self._control = control_interface
        raw_config = control_interface.get_config()
        if not isinstance(raw_config, dict):
            raw_config = {}
        self.config = {
            "ip": raw_config.get("ip", "127.0.0.1"),
            "port": raw_config.get("port", 23233),
            "account": raw_config.get("account", "-----"),
            "password": raw_config.get("password", ""),
        }
        self.finish_start = False
        self.finish_close = False

        self.host: str = self.config["ip"]
        self.port: int = self.config["port"]

        self.websocket: Optional[WebSocketClientProtocol] = None
        self._main_task: Optional[asyncio.Task[Any]] = None
        self._receive_task: Optional[asyncio.Task[Any]] = None
        self._keepalive_task: Optional[asyncio.Task[None]] = None

        self.server_id: Optional[str] = None
        self.last_data_packet: Optional[Dict[str, Dict[str, Any]]] = None
        self.data_packet = ClientDataPacket(control_interface, self)

        self.loop = asyncio.new_event_loop()
        self.loop_thread: Optional[threading.Thread] = None
        self._keepalive_started = False

    # ===== 生命周期 =====
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_server(self) -> None:
        self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.loop_thread.start()
        asyncio.run_coroutine_threadsafe(self._init_main(), self.loop)

    def stop_server(self) -> None:
        self._keepalive_started = False

        async def _graceful_shutdown() -> None:
            if self._keepalive_task:
                self._keepalive_task.cancel()
            if self._receive_task:
                self._receive_task.cancel()
            if self._main_task:
                self._main_task.cancel()
            if self._keepalive_task:
                await asyncio.gather(self._keepalive_task, return_exceptions=True)
            if self.websocket and not self.websocket.closed:
                try:
                    await self.websocket.close(code=1000, reason="Client shutdown")
                except Exception:
                    pass

        loop_running = self.loop.is_running()
        in_loop_thread = (
            self.loop_thread is not None
            and threading.current_thread() is self.loop_thread
        )

        if loop_running:
            if in_loop_thread:
                shutdown_task = asyncio.create_task(_graceful_shutdown())

                def _stop_after_shutdown(_: asyncio.Future) -> None:
                    self.loop.call_soon(self.loop.stop)

                shutdown_task.add_done_callback(_stop_after_shutdown)
            else:
                fut = asyncio.run_coroutine_threadsafe(_graceful_shutdown(), self.loop)
                try:
                    fut.result(timeout=3)
                except Exception:
                    pass
                self.loop.call_soon_threadsafe(self.loop.stop)

        if self.loop_thread and not in_loop_thread:
            self.loop_thread.join(timeout=3)

        self.finish_close = True

    async def _init_main(self) -> None:
        self._main_task = asyncio.current_task()
        try:
            while True:
                try:
                    uri = f"ws://{self.host}:{self.port}"
                    self.websocket = await websockets.connect(uri)
                    self.finish_start = True
                    self._control.info(
                        self._control.tr("net_core.service.connect_websocket", "")
                    )
                    websockets_started()
                    await self._receive()
                    break
                except (ConnectionRefusedError, OSError):
                    self.finish_start = False
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.finish_close = True
            self._control.info(self._control.tr("net_core.service.stop_websocket"))

    # ===== 接收数据 =====
    async def _get_recv(self) -> Optional[bytes]:
        while True:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=4)  # type: ignore[union-attr]
                return message if isinstance(message, bytes) else message.encode()
            except asyncio.TimeoutError:
                continue
            except ConnectionClosed as closed:
                code = getattr(closed, "code", None)
                reason = getattr(closed, "reason", "")
                if code == 1008 and "401" in reason:
                    self._control.error(
                        self._control.tr("net_core.service.already_login")
                    )
                    self.stop_server()
                    return None
                if code == 1008 and "400" in reason:
                    self._control.error(
                        self._control.tr("net_core.service.error_password")
                    )
                    self.stop_server()
                    return None

                self._control.info(
                    self._control.tr("net_core.service.disconnect_websocket")
                    + f" code={code} reason={reason}"
                )
                self._keepalive_started = False
                disconnected()
                if _control_interface is not None:
                    websocket_client_main(_control_interface)
                return None

    async def _receive(self) -> None:
        if not self.websocket:
            return

        if self.config["account"] != "-----":
            await self.start_login(reason="initial")
        else:
            self._control.debug("[FLOW][REGISTER] start", level=2)
            register_packet = self.data_packet.get_data_packet(
                PacketType.REGISTER,
                DEFAULT_SERVER,
                DEFAULT_TEMP,
                {"path": sys.argv[0], "protocol_version": PROTOCOL_VERSION},
            )
            self._control.debug("[WS][HANDSHAKE] account=-----", level=3)
            await self.send(register_packet)

        while True:
            self._receive_task = asyncio.create_task(self._get_recv())
            try:
                raw = await self._receive_task
                if raw is None:
                    break

                self._control.debug(f"[WS][RAW] recv={raw!r}", level=3)

                payload = await self._decode_payload(raw)
                if payload is None:
                    continue
                if isinstance(payload, dict):
                    self._control.debug(
                        f"[WS][DECODED] account={self.config.get('account')} payload={payload}",
                        level=3,
                    )
                await self.data_packet.parse_msg(payload)
            except asyncio.CancelledError:
                self._control.info(self._control.tr("net_core.service.stop_receive"))
                self.finish_close = True
                return

    async def start_login(self, *, reason: str = "manual") -> None:
        account = self.config.get("account", "-----")
        if not account or account == "-----":
            self._control.debug(
                f"[FLOW][LOGIN] skip account={account} reason={reason}",
                level=2,
            )
            return

        self._control.debug(
            f"[FLOW][LOGIN] start account={account} reason={reason}", level=2
        )
        login_packet = self.data_packet.get_data_packet(
            PacketType.LOGIN,
            DEFAULT_SERVER,
            (account, "system"),
            {"path": sys.argv[0], "protocol_version": PROTOCOL_VERSION},
        )
        self._control.debug(f"[WS][HANDSHAKE] account={account}", level=3)
        await self.send(login_packet)

    async def _decode_payload(self, raw: bytes) -> Optional[Dict[str, Any]]:
        try:
            decoded = raw.decode()
            if decoded.startswith("{"):
                return json.loads(decoded)  # type: ignore[no-any-return]
        except UnicodeDecodeError:
            pass

        try:
            decrypted = aes_decrypt(raw)
            return json.loads(decrypted.decode())  # type: ignore[no-any-return]
        except Exception as exc:
            self._control.logger.error(f"Failed to decode payload: {exc}")
            return None

    # ===== 发送数据 =====
    async def send(
        self,
        data: Dict[str, Dict[str, Any]] | Dict[str, Any],
        account: Optional[str] = None,
    ) -> None:
        if not self.websocket:
            return

        if (
            isinstance(data, dict)
            and DEFAULT_TEMP[0] in data
            and isinstance(data[DEFAULT_TEMP[0]], dict)
        ):
            packet = data[DEFAULT_TEMP[0]]
        else:
            packet = data  # type: ignore[assignment]

        if not isinstance(packet, dict):
            return

        account = account or self.config.get("account", "")
        self._control.debug(
            f"[S][{packet['type']}][{packet['from']} -> {packet['to']}({account})][{packet['sid']}] {packet.get('payload')}",
            level=1,
        )

        try:
            encrypted = aes_encrypt(json.dumps(packet).encode()).decode()
            message = json.dumps({"account": account, "data": encrypted})
            self._control.debug(f"[WS][RAW] send={message!r}", level=3)
            await self.websocket.send(message)
        except (ConnectionClosedError, ConnectionClosedOK):
            pass

    async def _trigger_websocket_client(self) -> None:
        if self.last_data_packet:
            await self.send(self.last_data_packet)
        if self.server_id:
            await self.send(
                self.data_packet.get_data_packet(
                    PacketType.PING,
                    DEFAULT_SERVER,
                    (self.server_id, "system"),
                    None,
                )
            )

    def start_keepalive(self) -> None:
        if not self._keepalive_started:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            self._keepalive_started = True

    # ===== 对外调用 =====
    async def send_data_to_other_server(
        self,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: Dict[str, Any],
    ) -> None:
        if not self.server_id:
            return
        if (
            t_server_id not in {"all", "-----"}
            and t_server_id not in self.data_packet.server_list
        ):
            self._control.log_system.logger.error(
                f"Unable to send data to server {t_server_id}"
            )
            return

        packet = self.data_packet.get_data_packet(
            PacketType.DATA_SEND,
            (t_server_id, t_plugin_id),
            (self.server_id, f_plugin_id),
            data,
        )
        self.last_data_packet = packet
        await self.send(packet)

    async def send_file_to_other_server(
        self,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        file_path: str,
        save_path: str,
    ) -> None:
        if not self.server_id:
            return
        if (
            t_server_id not in {"all", "-----"}
            and t_server_id not in self.data_packet.server_list
        ):
            self._control.log_system.logger.error(
                f"Unable to send data to server {t_server_id}"
            )
            return

        try:
            file_hash = get_file_hash(file_path)
            if file_hash is None:
                raise FileNotFoundError(f"Unable to read file: {file_path}")

            target_save_path = (
                os.path.join(save_path, os.path.basename(file_path))
                if os.path.basename(file_path) != os.path.basename(save_path)
                else save_path
            )

            header_packet = self.data_packet.get_data_packet(
                PacketType.FILE_SEND,
                (t_server_id, t_plugin_id),
                (self.server_id, f_plugin_id),
                {
                    "file_name": os.path.basename(file_path),
                    "save_path": target_save_path,
                    "hash": file_hash,
                },
            )
            await self.send(header_packet)

            with open(file_path, "rb") as handle:
                chunk_size = 1024 * 1024
                while chunk := handle.read(chunk_size):
                    body_packet = self.data_packet.get_data_packet(
                        PacketType.FILE_SENDING,
                        (t_server_id, t_plugin_id),
                        (self.server_id, f_plugin_id),
                        {"file": chunk.hex()},
                    )
                    await self.send(body_packet)
                    await asyncio.sleep(0.1)

            tail_packet = self.data_packet.get_data_packet(
                PacketType.FILE_SENDOK,
                (t_server_id, t_plugin_id),
                (self.server_id, f_plugin_id),
                {
                    "file_name": os.path.basename(file_path),
                    "save_path": target_save_path,
                    "hash": file_hash,
                },
            )
            await self.send(tail_packet)
        except Exception as exc:
            self._control.error(f"Send File Error: {exc}")

    def get_history_data_packet(self) -> list[Dict[str, Any]]:
        return self.data_packet.get_history_packet(DEFAULT_TEMP[0], 0)

    def get_recent_packets(
        self, limit: int = 20, server_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        return self.data_packet.get_recent_packets(limit, server_id)

    # ===== 自动任务 =====
    async def _keepalive_loop(self) -> None:
        try:
            first_round = True
            while True:
                await asyncio.sleep(5 if first_round else 30)
                first_round = False
                await self._trigger_websocket_client()
        except asyncio.CancelledError:
            return


# ===== 全局方法 =====
def websocket_client_main(control_interface: "CoreControlInterface") -> None:
    global _control_interface, websocket_client

    _control_interface = control_interface
    websocket_client = WebsocketClient(control_interface)
    websocket_client.start_server()


def websocket_client_stop() -> Optional[WebsocketClient]:
    if websocket_client is None:
        return None
    try:
        websocket_client.stop_server()
        return websocket_client
    except Exception:
        return None


def _schedule_on_client_loop(coro: Awaitable[Any]) -> Optional[Future[Any]]:
    if websocket_client is None:
        return None
    loop = websocket_client.loop
    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
    if _control_interface is not None:
        _control_interface.error("WebSocket 客户端事件循环未运行，无法调度协程")
    return None


def send_data(
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    data: Dict[str, Any],
) -> None:
    if websocket_client is None:
        return
    try:
        coro = websocket_client.send_data_to_other_server(
            f_plugin_id, t_server_id, t_plugin_id, data
        )
        _schedule_on_client_loop(coro)
    except NameError:
        pass


def send_file(
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    if websocket_client is None:
        return
    try:
        coro = websocket_client.send_file_to_other_server(
            f_plugin_id, t_server_id, t_plugin_id, file_path, save_path
        )
        _schedule_on_client_loop(coro)
    except NameError:
        pass


def get_server_id() -> Optional[str]:
    return websocket_client.server_id if websocket_client else None


def get_server_list() -> list[str]:
    if websocket_client is None:
        return []
    return list(websocket_client.data_packet.server_list)


def get_history_data_packet() -> list[Dict[str, Any]]:
    if websocket_client is None:
        return []
    return websocket_client.get_history_data_packet()


def get_recent_packets(
    limit: int = 20, server_id: Optional[str] = None
) -> list[Dict[str, Any]]:
    if websocket_client is None:
        return []
    return websocket_client.get_recent_packets(limit, server_id)


def set_sid_state(
    *,
    next_sid: Optional[int] = None,
    last_received: Optional[int] = None,
) -> Dict[str, int]:
    if websocket_client is None:
        raise RuntimeError("WebSocket client is not running; cannot adjust SID state")
    return websocket_client.data_packet.set_sid_state(
        next_sid=next_sid,
        last_received=last_received,
    )


def delete_recent_sids(count: int) -> Dict[str, int]:
    if websocket_client is None:
        raise RuntimeError("WebSocket client is not running; cannot adjust SID state")
    return websocket_client.data_packet.delete_recent_sids(count)
