from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from collections import deque
from concurrent.futures import Future
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING, Any, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol  # type: ignore[attr-defined]

from connect_core.aes_encrypt import aes_encrypt, aes_decrypt
from connect_core.account.register_system import get_register_password
from connect_core.context import GlobalContext
from connect_core.plugin.init_plugin import del_connect, websockets_started
from connect_core.websockets.data_packet import (
    ServerDataPacket,
    PacketType,
    DEFAULT_TEMP,
    DEFAULT_SERVER,
    DEFAULT_ALL,
)
from connect_core.tools.common import get_file_hash

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface

PING_INTERVAL = 20
PING_TIMEOUT = 20
SEND_FILES_DIR = "send_files"

_control_interface: Optional["CoreControlInterface"] = None
websocket_server: Optional["WebsocketServer"] = None


class SlidingWindowRateLimiter:
    """Simple per-key sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max(1, max_requests)
        self._window_seconds = max(0.1, window_seconds)
        self._events: Dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            cutoff = now - self._window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_requests:
                return False
            bucket.append(now)
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


class WebsocketServer:
    """异步 WebSocket 服务器，负责子服务器的注册、登录与数据转发。"""

    def __init__(self, control_interface: "CoreControlInterface") -> None:
        self._control = control_interface
        self._config = control_interface.config
        self._host: str = self._config.ip
        self._port: int = self._config.port
        self.finish_close = False

        self.websockets: Dict[str, WebSocketServerProtocol] = {}
        self.servers_info: Dict[str, Any] = {}
        self.last_send_packet: Dict[str, dict] = {}
        self.data_packet = ServerDataPacket(control_interface, self)

        self.loop = asyncio.new_event_loop()
        self.loop_thread: Optional[threading.Thread] = None
        self.server: Optional[websockets.server.Serve] = None  # type: ignore[name-defined]
        self._resend_task: Optional[asyncio.Task[None]] = None
        self._keepalive_task: Optional[asyncio.Task[None]] = None
        self._health_server: Optional[asyncio.base_events.Server] = None
        self._started_at = time.monotonic()

        self._account_lock = threading.Lock()
        self._account_file = self._prepare_account_file()
        self._send_files_path = self._prepare_send_files_dir()
        self._rate_limiter: Optional[SlidingWindowRateLimiter] = None
        if getattr(self._config, "rate_limit_enabled", True):
            self._rate_limiter = SlidingWindowRateLimiter(
                getattr(self._config, "rate_limit_max_requests", 120),
                getattr(self._config, "rate_limit_window_seconds", 60.0),
            )

    # ===== 生命周期 =====
    def start_server(self) -> None:
        """启动事件循环线程并调度主协程。"""

        self.loop_thread = threading.Thread(
            target=self._run_loop,
            name="WebsocketServerLoop",
            daemon=True,
        )
        self.loop_thread.start()
        asyncio.run_coroutine_threadsafe(self._main(), self.loop)

    def close_server(self) -> None:
        """优雅关闭服务器与所有连接。"""

        async def _shutdown() -> None:
            for task in (self._resend_task, self._keepalive_task):
                if task is not None:
                    task.cancel()
            if self._resend_task is not None or self._keepalive_task is not None:
                await asyncio.gather(
                    *(task for task in (self._resend_task, self._keepalive_task) if task is not None),
                    return_exceptions=True,
                )
            for server_id, ws in list(self.websockets.items()):
                try:
                    await ws.close(code=1000, reason="Server shutdown")
                except Exception:
                    pass
            if self._health_server is not None:
                self._health_server.close()
                await self._health_server.wait_closed()
            if self.server:
                self.server.close()
                await self.server.wait_closed()

        if self.loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
            try:
                fut.result(timeout=3)
            except Exception:
                pass

        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.loop_thread is not None:
            self.loop_thread.join(timeout=3)

        self.finish_close = True

    async def _main(self) -> None:
        """主协程：创建 websockets 服务并等待关闭。"""

        try:
            self.server = await websockets.serve(
                self._handler,
                self._host,
                self._port,
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
            )
            self._control.logger.info(
                self._control.tr("net_core.service.start_websocket")
            )
            websockets_started()
            self._resend_task = asyncio.create_task(self._resend_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            await self._start_healthcheck_server()
            await self.server.wait_closed()  # pyright: ignore[reportOptionalMemberAccess]
        except Exception as exc:  # pragma: no cover - log side effect
            self._control.log_system.logger.exception(
                self._control.tr("net_core.service.start_websocket_error")
            )
            self._control.logger.error(f"Websocket server failed: {exc}")
            self.finish_close = True

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    # ===== 连接处理 =====
    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        server_id = "-----"
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.close(code=1003, reason="Invalid JSON")
                    break

                self._control.debug(f"[WS][RAW] recv={raw!r}", level=3)

                if "account" not in msg:
                    await websocket.send(
                        json.dumps(
                            self.data_packet.get_data_packet(
                                PacketType.TEST_CONNECT,
                                DEFAULT_TEMP,
                                DEFAULT_TEMP,
                                None,
                            )[DEFAULT_TEMP[0]]
                        )
                    )
                    await websocket.close(code=1008, reason="Malformed handshake")
                    break

                server_id = msg["account"]
                self._control.debug(f"[WS][HANDSHAKE] account={server_id}", level=3)
                if self._rate_limiter is not None:
                    limit_key = self._resolve_rate_limit_key(server_id, websocket)
                    if not self._rate_limiter.allow(limit_key):
                        self._control.logger.warning(
                            f"Rate limit exceeded for {limit_key}"
                        )
                        await websocket.close(code=1008, reason="HTTP 429")
                        break
                await self._process_message(msg, websocket, server_id)
        except ConnectionClosed as closed:
            reason = getattr(closed, "reason", "")
            code = getattr(closed, "code", None)
            if code == 1008 and reason and "401" in reason:
                self._control.logger.warning(
                    self._control.tr("net_core.service.already_login_server", server_id)
                )
                return
        finally:
            if server_id != "-----":
                await self._close_connection(server_id, websocket)

    async def _process_message(
        self,
        msg: Dict[str, Any],
        websocket: WebSocketServerProtocol,
        server_id: str,
    ) -> None:
        accounts = self.read_accounts()
        try:
            payload = self._decrypt_message(msg, server_id, accounts)
            self._control.debug(
                f"[WS][DECODED] account={server_id} payload={payload}", level=3
            )
            await self.data_packet.parse_msg(payload, websocket)
        except ValueError as exc:
            self._control.logger.warning(
                f"Failed to process message from {server_id}: {exc}"
            )
            self._control.debug(f"Raw message: {msg}", level=3)
            await websocket.close(code=1008, reason="HTTP 400")
            await self._close_connection(server_id, websocket)
        except Exception as exc:
            self._control.logger.error(
                f"Unexpected error during message processing: {exc}"
            )
            if GlobalContext.get_debug_level() >= 3:
                self._control.logger.debug(f"Raw message: {msg}", exc_info=True)
            await websocket.close(code=1011, reason="Internal error")
            await self._close_connection(server_id, websocket)

    def _decrypt_message(
        self,
        msg: Dict[str, Any],
        account: str,
        accounts: Dict[str, str],
    ) -> Dict[str, Any]:
        if account not in accounts and account != "-----":
            raise ValueError(f"Unknown account: {account}")

        key = get_register_password() if account == "-----" else accounts[account]
        decrypted = aes_decrypt(msg.get("data"), key)  # type: ignore[arg-type]
        return json.loads(decrypted.decode())  # type: ignore[no-any-return]

    async def close_connect(
        self,
        server_id: str,
        reason: int,
        websocket: Optional[WebSocketServerProtocol] = None,
    ) -> None:
        if websocket is None:
            websocket = self.websockets.get(server_id)
        if websocket:
            try:
                await websocket.close(code=1008, reason=f"HTTP {reason}")
            except Exception:
                pass

    async def _close_connection(
        self, server_id: str, websocket: WebSocketServerProtocol
    ) -> None:
        if self._rate_limiter is not None:
            self._rate_limiter.clear(self._resolve_rate_limit_key(server_id, websocket))
        if server_id != "-----":
            self.websockets.pop(server_id, None)
            self.servers_info.pop(server_id, None)
            self.last_send_packet.pop(server_id, None)
            self.data_packet.del_server_id(server_id)
            del_connect(server_id)
            await self.broadcast(
                self.data_packet.get_data_packet(
                    PacketType.DEL_LOGIN,
                    DEFAULT_ALL,
                    DEFAULT_SERVER,
                    {"server_id": server_id},
                )
            )
            self._control.logger.info(
                self._control.tr(
                    "net_core.service.disconnect_from_sub_websocket", server_id
                )
            )
        else:
            self._control.logger.warning(
                self._control.tr("net_core.service.disconnect_from_unknown_websocket")
            )

    # ===== 数据收发 =====
    async def send(
        self, data: dict, websocket: WebSocketServerProtocol, account: str
    ) -> None:
        if data is None:
            if GlobalContext.get_debug_level() >= 2:
                self._control.debug(
                    f"[FLOW][SEND] skip empty payload for account={account}",
                    level=2,
                )
            return

        if (
            isinstance(data, dict)
            and account in data
            and isinstance(data[account], dict)
            and "sid" in data[account]
        ):
            packet = data[account]
        else:
            packet = data

        self._control.debug(
            f"[S][{packet['type']}][{packet['from']} -> {packet['to']}({account})][{packet['sid']}] {packet.get('payload')}",
            level=1,
        )

        accounts = self.read_accounts()
        try:
            if account == "-----":
                encrypted = aes_encrypt(
                    json.dumps(packet).encode(), get_register_password()
                )
                await websocket.send(encrypted)
            elif account in accounts:
                encrypted = aes_encrypt(json.dumps(packet).encode(), accounts[account])
                await websocket.send(encrypted)
            else:
                raise ValueError(f"Unknown account: {account}")
        except Exception as exc:
            self._control.logger.warning(
                f"Failed to send packet type={packet.get('type')} account={account}: {exc}"
            )

    async def broadcast(self, data: dict, except_id: Optional[list] = None) -> None:
        except_id = except_id or []
        for server_id, packet in data.items():
            if server_id in self.websockets and server_id not in except_id:
                await self.send(packet, self.websockets[server_id], server_id)

    async def send_data_to_other_server(
        self,
        f_server_id: str,
        f_plugin_id: str,
        t_server_id: str,
        t_plugin_id: str,
        data: dict,
        except_id: Optional[list] = None,
    ) -> None:
        except_id = except_id or []
        msg = self.data_packet.get_data_packet(
            PacketType.DATA_SEND,
            (t_server_id, t_plugin_id),
            (f_server_id, f_plugin_id),
            data,
        )
        if t_server_id == "all":
            for server in self.servers_info:
                self.last_send_packet[server] = msg
            await self.broadcast(msg, except_id)
        elif t_server_id not in self.websockets:
            self._control.log_system.logger.error(
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
        except_id: Optional[list] = None,
    ) -> None:
        except_id = except_id or []
        try:
            shutil.copy(file_path, self._send_files_path)
            file_hash = get_file_hash(file_path)
            target_save_path = (
                os.path.join(save_path, os.path.basename(file_path))
                if os.path.basename(file_path) != os.path.basename(save_path)
                else save_path
            )

            header_packet = self.data_packet.get_data_packet(
                PacketType.FILE_SEND,
                (t_server_id, t_plugin_id),
                (f_server_id, f_plugin_id),
                {
                    "file_name": os.path.basename(file_path),
                    "save_path": target_save_path,
                    "hash": file_hash,
                },
            )

            if t_server_id == "all":
                await self.broadcast(header_packet, except_id)
            elif t_server_id not in self.websockets:
                self._control.log_system.logger.error(
                    f"Unable to send data to server {t_server_id}"
                )
                return
            else:
                await self.send(
                    header_packet[t_server_id],
                    self.websockets[t_server_id],
                    t_server_id,
                )

            chunk_path = self._send_files_path / os.path.basename(file_path)
            with open(chunk_path, "rb") as fd:
                while chunk := fd.read(1024 * 1024):
                    body_packet = self.data_packet.get_data_packet(
                        PacketType.FILE_SENDING,
                        (t_server_id, t_plugin_id),
                        (f_server_id, f_plugin_id),
                        {"file": chunk.hex()},
                    )
                    if t_server_id == "all":
                        await self.broadcast(body_packet, except_id)
                    else:
                        await self.send(
                            body_packet[t_server_id],
                            self.websockets[t_server_id],
                            t_server_id,
                        )
                    await asyncio.sleep(0.1)

            tail_packet = self.data_packet.get_data_packet(
                PacketType.FILE_SENDOK,
                (t_server_id, t_plugin_id),
                (f_server_id, f_plugin_id),
                {
                    "file_name": os.path.basename(file_path),
                    "save_path": target_save_path,
                    "hash": file_hash,
                },
            )

            if t_server_id == "all":
                await self.broadcast(tail_packet, except_id)
            else:
                await self.send(
                    tail_packet[t_server_id],
                    self.websockets[t_server_id],
                    t_server_id,
                )
        except Exception as exc:
            self._control.logger.error(f"Send file error: {exc}")

    async def _resend(self) -> None:
        for server_id, packet in list(self.last_send_packet.items()):
            if server_id == "all":
                await self.broadcast(packet)
            elif server_id in self.websockets:
                await self.send(packet, self.websockets[server_id], server_id)

    async def _resend_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                await self._resend()
        except asyncio.CancelledError:
            return

    async def _send_keepalive(self) -> None:
        for server_id, ws in list(self.websockets.items()):
            try:
                pong_waiter = await ws.ping()
                await pong_waiter
            except Exception:
                await self.close_connect(server_id, 408, ws)
                await self._close_connection(server_id, ws)

    async def _keepalive_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                await self._send_keepalive()
        except asyncio.CancelledError:
            return

    async def _start_healthcheck_server(self) -> None:
        if not getattr(self._config, "healthcheck_enabled", True):
            return
        host = getattr(self._config, "healthcheck_host", self._host)
        port = getattr(self._config, "healthcheck_port", self._port + 1)
        self._health_server = await asyncio.start_server(
            self._handle_health_request,
            host,
            port,
        )
        self._control.logger.info(
            f"Health check endpoint listening on http://{host}:{port}/health"
        )

    async def _handle_health_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            request_line = raw.splitlines()[0].decode("ascii", errors="ignore")
            parts = request_line.split()
            method = parts[0] if len(parts) > 0 else ""
            path = parts[1] if len(parts) > 1 else "/"
            if method == "GET" and path == "/health":
                payload = self._health_payload()
                writer.write(self._http_json_response(200, "OK", payload))
            else:
                writer.write(
                    self._http_json_response(404, "Not Found", {"status": "not_found"})
                )
            await writer.drain()
        except Exception:
            writer.write(
                self._http_json_response(500, "Internal Server Error", {"status": "error"})
            )
            try:
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": round(time.monotonic() - self._started_at, 3),
            "connected_servers": len(self.websockets),
            "known_servers": sorted(self.servers_info.keys()),
            "rate_limit_enabled": self._rate_limiter is not None,
        }

    @staticmethod
    def _http_json_response(status_code: int, reason: str, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = [
            f"HTTP/1.1 {status_code} {reason}",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(body)}",
            "Connection: close",
            "",
            "",
        ]
        return "\r\n".join(headers).encode("ascii") + body

    @staticmethod
    def _resolve_rate_limit_key(
        server_id: str,
        websocket: WebSocketServerProtocol,
    ) -> str:
        if server_id and server_id != DEFAULT_TEMP[0]:
            return server_id
        remote = getattr(websocket, "remote_address", None)
        return f"temp:{remote or id(websocket)}"

    def get_history_data_packet(self, server_id: str) -> Optional[list]:
        if server_id in self.websockets:
            return self.data_packet.get_history_packet(server_id, 0)
        return None

    def get_recent_packets(
        self, limit: int = 20, server_id: Optional[str] = None
    ) -> list[dict]:
        return self.data_packet.get_recent_packets(limit, server_id)

    # ===== 账户文件 =====
    def read_accounts(self) -> Dict[str, str]:
        with self._account_lock:
            try:
                with self._account_file.open("r", encoding="utf-8") as fh:
                    return json.load(fh)  # type: ignore[no-any-return]
            except (json.JSONDecodeError, FileNotFoundError):
                return {}

    def write_accounts(self, accounts: Dict[str, str]) -> None:
        with self._account_lock:
            with self._account_file.open("w", encoding="utf-8") as fh:
                json.dump(accounts, fh, indent=4, ensure_ascii=False)

    def _prepare_account_file(self) -> Path:
        base_path = Path(GlobalContext.get_path())
        try:
            if base_path.exists() and not base_path.is_dir():
                base_path = base_path.parent
        except OSError:
            base_path = base_path.parent

        account_dir = base_path / "config" / "connect_core"
        account_dir.mkdir(parents=True, exist_ok=True)
        account_file = account_dir / "account.json"
        if not account_file.exists():
            account_file.write_text("{}", encoding="utf-8")
        return account_file

    def _prepare_send_files_dir(self) -> Path:
        base_path = Path(GlobalContext.get_path())
        try:
            if base_path.exists() and not base_path.is_dir():
                base_path = base_path.parent
        except OSError:
            base_path = base_path.parent

        send_files_dir = base_path / SEND_FILES_DIR
        send_files_dir.mkdir(parents=True, exist_ok=True)
        return send_files_dir


def websocket_server_main(control_interface: "CoreControlInterface") -> None:
    global _control_interface, websocket_server
    _control_interface = control_interface
    websocket_server = WebsocketServer(control_interface)
    websocket_server.start_server()


def websocket_server_stop() -> Optional[WebsocketServer]:
    if websocket_server is not None:
        websocket_server.close_server()
    return websocket_server


def _schedule_on_ws_loop(coro: Awaitable[Any]) -> Optional[Future]:
    if websocket_server is None:
        return None
    loop = websocket_server.loop
    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
    if _control_interface is not None:
        _control_interface.logger.error(
            "WebSocket event loop is not running; cannot schedule coroutine"
        )
    return None


def send_data(
    f_server_id: str,
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    data: dict,
) -> None:
    if websocket_server is None:
        return
    coro = websocket_server.send_data_to_other_server(
        f_server_id,
        f_plugin_id,
        t_server_id,
        t_plugin_id,
        data,
    )
    _schedule_on_ws_loop(coro)


def send_file(
    f_server_id: str,
    f_plugin_id: str,
    t_server_id: str,
    t_plugin_id: str,
    file_path: str,
    save_path: str,
) -> None:
    if websocket_server is None:
        return
    coro = websocket_server.send_file_to_other_server(
        f_server_id,
        f_plugin_id,
        t_server_id,
        t_plugin_id,
        file_path,
        save_path,
    )
    _schedule_on_ws_loop(coro)


def get_server_list() -> list:
    return list(websocket_server.servers_info.keys()) if websocket_server else []


def get_history_data_packet(server_id: str) -> Optional[list]:
    if websocket_server is None:
        return None
    return websocket_server.get_history_data_packet(server_id)


def get_recent_packets(limit: int = 20, server_id: Optional[str] = None) -> list[dict]:
    if websocket_server is None:
        return []
    return websocket_server.get_recent_packets(limit, server_id)
