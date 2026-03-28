from __future__ import annotations

import os
import time
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from connect_core.context import GlobalContext
from connect_core.aes_encrypt import aes_main
from connect_core.plugin.init_plugin import (
    connected,
    del_connect,
    new_connect,
    recv_data,
    recv_file,
)
from connect_core.tools.common import (
    generate_md5_checksum,
    generate_password,
    generate_random_id,
    verify_file_hash,
    verify_md5_checksum,
)

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface
    from connect_core.websockets.server import WebsocketServer
    from connect_core.websockets.client import WebsocketClient

DEFAULT_TEMP: Tuple[str, str] = ("-----", "-----")
DEFAULT_SERVER: Tuple[str, str] = ("-----", "system")
DEFAULT_ALL: Tuple[str, str] = ("all", "system")


# ===== 数据模型 =====
class PacketType(str, Enum):
    TEST_CONNECT = "test_connect"
    PING = "ping"
    PONG = "pong"
    CONTROL_STOP = "control_stop"
    CONTROL_RELOAD = "control_reload"
    CONTROL_MAINTENANCE = "control_maintenance"
    CONTROL_RESUME = "control_resume"
    REGISTER = "register"
    REGISTERED = "registered"
    REGISTER_ERROR = "register_error"
    LOGIN = "login"
    LOGINED = "logined"
    NEW_LOGIN = "new_login"
    DEL_LOGIN = "del_login"
    LOGIN_ERROR = "login_error"
    DATA_SEND = "data_send"
    DATA_SENDOK = "data_sendok"
    DATA_ERROR = "data_error"
    FILE_SEND = "file_send"
    FILE_SENDING = "file_sending"
    FILE_SENDOK = "file_sendok"
    FILE_ERROR = "file_error"


PERSISTENT_TYPES: set[PacketType] = {
    packet_type
    for packet_type in PacketType
    if packet_type not in {PacketType.TEST_CONNECT, PacketType.PING, PacketType.PONG}
}


class PacketStatus(str, Enum):
    """Built-in packet statuses. Custom statuses can use any string."""
    REQUEST = "request"
    OK = "ok"
    ERROR = "error"
    SENDING = "sending"
    NEW = "new"
    DEL = "del"
    STOP = "stop"
    RELOAD = "reload"
    MAINTENANCE = "maintenance"
    RESUME = "resume"


PROTOCOL_VERSION: int = 1


class StatusRegistry:
    """Registry for custom packet statuses and their handlers."""

    def __init__(self) -> None:
        self._custom_statuses: Dict[PacketType, set[str]] = {}
        self._handlers: Dict[Tuple[PacketType, str], List[Callable]] = {}

    def register_status(self, packet_type: PacketType, status: str) -> None:
        """Register a custom status for the given packet type."""
        self._custom_statuses.setdefault(packet_type, set()).add(status)

    def register_handler(
        self, packet_type: PacketType, status: str, callback: Callable
    ) -> None:
        """Register a callback for a specific (type, status) combination."""
        key = (packet_type, status)
        self._handlers.setdefault(key, []).append(callback)

    def unregister_handler(
        self, packet_type: PacketType, status: str, callback: Callable
    ) -> None:
        """Remove a previously registered callback."""
        key = (packet_type, status)
        handlers = self._handlers.get(key, [])
        if callback in handlers:
            handlers.remove(callback)

    def get_handlers(
        self, packet_type: PacketType, status: Optional[str]
    ) -> List[Callable]:
        """Get all registered handlers for a (type, status) pair."""
        if status is None:
            return []
        return list(self._handlers.get((packet_type, status), []))

    def get_registered_statuses(self, packet_type: PacketType) -> set[str]:
        """Get all custom statuses registered for a packet type."""
        return set(self._custom_statuses.get(packet_type, set()))


status_registry = StatusRegistry()


class DataModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: PacketType = Field(alias="type")
    status: Optional[str] = None
    sid: int
    to: Tuple[str, str]
    from_: Tuple[str, str] = Field(alias="from")
    payload: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)
    checksum: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_packet(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("checksum"):
            return values
        payload = values.get("payload")
        if payload is None:
            return values
        values["checksum"] = generate_md5_checksum(payload)
        return values


HistoryEntry = Tuple[int, DataModel | None, str]


class PacketStore:
    """负责管理已发送与接收的数据包，支持历史重放。"""

    def __init__(self) -> None:
        self._is_server = GlobalContext.is_server_mode()
        self._history: Dict[str, List[HistoryEntry]] = {}

    @staticmethod
    def _upsert_entry(bucket: List[HistoryEntry], sid: int, packet: DataModel | None, direction: str) -> None:
        for index, (existing_sid, _, _) in enumerate(bucket):
            if existing_sid == sid:
                bucket[index] = (sid, packet, direction)
                return
        bucket.append((sid, packet, direction))

    def create_packets(
        self,
        type_: PacketType,
        to: Tuple[str, str],
        from_: Tuple[str, str],
        payload: Optional[Dict[str, Any]] = None,
        *,
        status: Optional[str] = None,
        exclude: Optional[Iterable[str]] = None,
        record_history: Optional[bool] = None,
        known_targets: Optional[Iterable[str]] = None,
    ) -> Dict[str, DataModel]:
        """构建要发送的数据包集合。"""

        exclude_ids = set(exclude or [])
        record = PERSISTENT_TYPES.__contains__(type_) if record_history is None else record_history
        targets = self._resolve_targets(to[0], exclude_ids, bool(record), known_targets)
        packets: Dict[str, DataModel] = {}

        for dest, sid in targets.items():
            packet = DataModel(
                type=type_,
                sid=sid,
                to=to,
                from_=from_,  # type: ignore[call-arg]
                payload=payload,
                status=status,
            )
            if record and dest != DEFAULT_TEMP[0]:
                bucket = self._history.setdefault(dest, [])
                self._upsert_entry(bucket, sid, packet, "sent")
            packets[dest] = packet
        return packets

    def record_received(self, client_id: str, packet: DataModel) -> None:
        if packet.type in {PacketType.PING, PacketType.PONG}:
            return
        bucket = self._history.setdefault(client_id, [])
        self._upsert_entry(bucket, packet.sid, packet, "received")

    def history(self, server_id: str, since_sid: int) -> List[DataModel]:
        bucket = self._history.get(server_id, [])
        return [
            packet
            for sid, packet, direction in sorted(bucket, key=lambda item: item[0])
            if sid > since_sid and direction == "sent" and packet is not None
        ]

    def drop_server(self, server_id: str) -> None:
        self._history.pop(server_id, None)

    def max_sid(self, server_id: str) -> int:
        bucket = self._history.get(server_id, [])
        return max((sid for sid, _, _ in bucket), default=0)

    @staticmethod
    def dump_packet(packet: DataModel) -> Dict[str, Any]:
        return packet.model_dump(by_alias=True)

    @staticmethod
    def dump_mapping(packets: Dict[str, DataModel]) -> Dict[str, Dict[str, Any]]:
        return {sid: pkt.model_dump(by_alias=True) for sid, pkt in packets.items()}

    def recent_packets(
        self,
        limit: int = 20,
        server_id: Optional[str] = None,
    ) -> List[Tuple[DataModel, str, str]]:
        entries: List[Tuple[DataModel, str, str]] = []
        for owner_id, packets in self._history.items():
            if server_id is not None and owner_id != server_id:
                continue
            for sid, packet, direction in packets:
                if packet is None:
                    continue
                entries.append((packet, direction, owner_id))

        entries.sort(key=lambda item: item[0].timestamp)
        if limit > 0:
            return entries[-limit:]
        return entries

    def _resolve_targets(
        self,
        server_id: str,
        exclude: set[str],
        create_if_missing: bool,
        known_targets: Optional[Iterable[str]],
    ) -> Dict[str, int]:
        def _calculate_next_sid(dest: str, *, create: bool) -> int:
            bucket = self._history.get(dest)
            if bucket is None:
                if not create:
                    return 0
                bucket = []
                self._history[dest] = bucket
            highest = max((sid for sid, _, _ in bucket), default=0)
            return highest + 1 if create else highest

        if server_id == DEFAULT_ALL[0]:
            candidates = set(self._history.keys())
            if known_targets:
                candidates.update(str(target) for target in known_targets)
            targets = {}
            for dest in candidates:
                if dest in exclude:
                    continue
                next_sid = _calculate_next_sid(dest, create=create_if_missing)
                targets[dest] = next_sid
            return targets

        if server_id == DEFAULT_TEMP[0]:
            return {DEFAULT_TEMP[0]: 0}

        if create_if_missing or server_id in self._history:
            next_sid = _calculate_next_sid(server_id, create=create_if_missing)
            return {server_id: next_sid}
        return {}


class ServerDataPacket:
    """服务器端数据包调度与处理。"""

    def __init__(
        self,
        control_interface: "CoreControlInterface",
        websocket_server: "WebsocketServer",
    ) -> None:
        self._control = control_interface
        self._websocket_server = websocket_server
        self._store = PacketStore()
        self._wait_files: Dict[str, Any] = {}

    def get_data_packet(
        self,
        packet_type: PacketType,
        to_info: Tuple[str, str],
        from_info: Tuple[str, str],
        payload: Optional[Dict[str, Any]] = None,
        exclude_server_ids: Optional[Iterable[str]] = None,
        *,
        status: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """对外兼容旧接口，返回 JSON 可序列化的数据包映射。"""
        packets = self._store.create_packets(
            packet_type,
            to_info,
            from_info,
            payload,
            status=status,
            exclude=exclude_server_ids,
            known_targets=self._websocket_server.websockets.keys(),
        )
        return self._store.dump_mapping(packets)

    def add_recv_packet(self, server_id: str, packet: Dict[str, Any]) -> None:
        model = DataModel.model_validate(packet)
        self._store.record_received(server_id, model)

    def get_history_packet(self, server_id: str, old_sid: int) -> List[Dict[str, Any]]:
        return [
            self._store.dump_packet(packet)
            for packet in self._store.history(server_id, old_sid)
        ]

    def get_recent_packets(
        self,
        limit: int = 20,
        server_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        recent: List[Dict[str, Any]] = []
        for packet, direction, owner_id in self._store.recent_packets(limit, server_id):
            record = packet.model_dump(by_alias=True)
            record["direction"] = direction
            record["server_id"] = owner_id
            recent.append(record)
        return recent

    def del_server_id(self, server_id: str) -> None:
        self._store.drop_server(server_id)
        if server_id in self._wait_files:
            try:
                self._wait_files[server_id].close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            self._wait_files.pop(server_id, None)

    async def parse_msg(self, data: Dict[str, Any], websocket: Any) -> None:
        self._control.debug("[FLOW][DISPATCH] validating packet", level=4)
        try:
            packet = DataModel.model_validate(data)
        except ValidationError as exc:
            self._control.logger.error(f"Invalid packet received: {exc}")
            self._control.debug(f"[FLOW][DISPATCH] raw={data}", level=2)
            return

        try:
            server_id = packet.from_[0]
            self._control.debug(
                f"[FLOW][DISPATCH] record server_id={server_id}", level=2
            )
            self._store.record_received(server_id, packet)
            self._control.debug(
                f"[R][{packet.type}][{packet.from_} -> {packet.to}][{packet.sid}] {packet.payload}",
                level=1,
            )

            self._control.debug(
                f"[FLOW][DISPATCH] packet.to={packet.to!r} first={packet.to[0]!r}",
                level=2,
            )
            if packet.to[0] in {DEFAULT_TEMP[0], DEFAULT_ALL[0]}:
                await self._handle_broadcast_or_global(packet, websocket)
            else:
                await self._handle_direct_message(packet, websocket)
        except Exception as exc:
            self._control.logger.error(f"Failed to dispatch packet: {exc}")
            if GlobalContext.get_debug_level() >= 3:
                self._control.logger.exception("Dispatch stacktrace")

    async def _handle_broadcast_or_global(self, packet: DataModel, websocket: Any) -> None:
        if packet.to[0] == DEFAULT_ALL[0]:
            payload = packet.payload
            packets = self.get_data_packet(
                packet.type,
                packet.to,
                packet.from_,
                payload,
                exclude_server_ids=[packet.from_[0]],
            )
            if packet.type == PacketType.DATA_SEND:
                self._websocket_server.last_send_packet.update(packets)
            await self._websocket_server.broadcast(packets)

        try:
            packet_type = (
                packet.type
                if isinstance(packet.type, PacketType)
                else PacketType(packet.type)
            )
        except ValueError:
            self._control.debug(
                f"[FLOW][DISPATCH] unknown packet type={packet.type!r}",
                level=2,
            )
            return

        if packet_type is PacketType.PING:
            await self._handle_ping(packet, websocket)
        elif packet_type is PacketType.REGISTER:
            await self._handle_register(packet, websocket)
        elif packet_type is PacketType.REGISTER_ERROR:
            await self._handle_register_error(packet, websocket)
        elif packet_type is PacketType.LOGIN:
            await self._handle_login(packet, websocket)
        elif packet_type is PacketType.DATA_SEND:
            await self._handle_data_send(packet, websocket)
        elif packet_type is PacketType.DATA_SENDOK:
            await self._handle_data_sendok(packet)
        elif packet_type is PacketType.DATA_ERROR:
            await self._handle_data_error(packet, websocket)
        elif packet_type is PacketType.FILE_SEND:
            await self._handle_file_send(packet, websocket)
        elif packet_type is PacketType.FILE_SENDING:
            await self._handle_file_sending(packet, websocket)
        elif packet_type is PacketType.FILE_SENDOK:
            await self._handle_file_sendok(packet, websocket)
        elif packet_type is PacketType.FILE_ERROR:
            await self._send_file_error(packet.from_[0], websocket)
        else:
            handled = await self._dispatch_custom_handlers(packet)
            if not handled:
                self._control.debug(
                    f"[FLOW][DISPATCH] unhandled packet type={packet_type} status={packet.status}",
                    level=2,
                )

    async def _dispatch_custom_handlers(self, packet: DataModel) -> bool:
        """查找并执行 StatusRegistry 中注册的自定义处理器。"""
        handlers = status_registry.get_handlers(str(packet.type), packet.status)  # type: ignore[arg-type]
        if not handlers:
            return False
        for handler in handlers:
            try:
                import asyncio
                result = handler(packet)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._control.logger.error(
                    f"Custom handler error for type={packet.type} status={packet.status}: {exc}"
                )
        return True

    async def _handle_direct_message(self, packet: DataModel, websocket: Any) -> None:
        target_id = packet.to[0]
        payload = packet.payload
        packets = self.get_data_packet(packet.type, packet.to, packet.from_, payload)
        if packet.type == PacketType.DATA_SEND:
            self._websocket_server.last_send_packet[target_id] = packets
            await self._send_acknowledgement(packet.from_[0], websocket)
        to_websocket = self._websocket_server.websockets.get(target_id)
        if to_websocket is None:
            to_websocket = websocket
        if to_websocket:
            await self._websocket_server.send(
                packets.get(target_id),  # type: ignore[arg-type]
                to_websocket,
                target_id,
            )

    async def _handle_ping(self, packet: DataModel, websocket: Any) -> None:
        history_packets = [
            entry
            for entry in self.get_history_packet(packet.from_[0], packet.sid)
            if entry.get("type") not in {PacketType.PING, PacketType.PONG}
        ]
        highest_sid = self._store.max_sid(packet.from_[0])
        if history_packets:
            for history in history_packets:
                await self._websocket_server.send(history, websocket, packet.from_[0])
                sid_value = history.get("sid")
                if isinstance(sid_value, int):
                    highest_sid = max(highest_sid, sid_value)
        highest_sid = max(highest_sid, packet.sid)

        pong_packet = self.get_data_packet(
            PacketType.PONG,
            (packet.from_[0], "system"),
            DEFAULT_SERVER,
            None,
        )
        response = pong_packet.get(packet.from_[0])
        if response is None:
            self._control.debug(
                f"[FLOW][PING] missing pong payload for server_id={packet.from_[0]}",
                level=2,
            )
            return

        response["sid"] = highest_sid
        await self._websocket_server.send(response, websocket, packet.from_[0])

    async def _handle_register(self, packet: DataModel, websocket: Any) -> None:
        self._control.debug(
            "[FLOW][REGISTER] start", level=2
        )
        client_version = (packet.payload or {}).get("protocol_version")
        if client_version != PROTOCOL_VERSION:
            self._control.logger.warning(
                self._control.tr(
                    "net_core.service.protocol_mismatch",
                    client_version,
                    PROTOCOL_VERSION,
                )
            )
            error_packet = self.get_data_packet(
                PacketType.REGISTER_ERROR,
                DEFAULT_TEMP,
                DEFAULT_SERVER,
                {"error": f"Protocol version mismatch: client={client_version}, server={PROTOCOL_VERSION}"},
            )
            await self._websocket_server.send(
                error_packet.get(DEFAULT_TEMP[0]),  # type: ignore[arg-type]
                websocket, DEFAULT_TEMP[0]
            )
            await self._websocket_server.close_connect(DEFAULT_TEMP[0], 4001, websocket)
            return
        server_id, password = self._generate_server_credentials()
        self._save_credentials(server_id, password)
        response = self.get_data_packet(
            PacketType.REGISTERED,
            (server_id, "system"),
            DEFAULT_SERVER,
            {"password": password},
        )
        packet_payload = response.get(server_id)
        if packet_payload is None:
            self._control.debug(
                f"[FLOW][REGISTER] missing payload for server_id={server_id}",
                level=2,
            )
            return

        self._control.debug(
            f"[FLOW][REGISTER] issuing credentials server_id={server_id}",
            level=2,
        )
        await self._websocket_server.send(packet_payload, websocket, DEFAULT_TEMP[0])
        self._control.logger.info(
            self._control.tr("net_core.service.register_success", server_id)
        )
        self._control.debug(
            f"[FLOW][REGISTER] success server_id={server_id}", level=2
        )

    async def _handle_register_error(self, packet: DataModel, websocket: Any) -> None:
        self._control.debug(
            "[FLOW][REGISTER] retry last account", level=2
        )
        accounts = self._control.get_config(config_path="account.json")
        if accounts:
            accounts.pop(next(reversed(accounts)))
        self._control.save_config(accounts, "account.json")
        await self._handle_register(packet, websocket)

    async def _handle_login(self, packet: DataModel, websocket: Any) -> None:
        server_id = packet.from_[0]
        self._control.debug(
            f"[FLOW][LOGIN] start server_id={server_id}", level=2
        )
        client_version = (packet.payload or {}).get("protocol_version")
        if client_version != PROTOCOL_VERSION:
            self._control.logger.warning(
                self._control.tr(
                    "net_core.service.protocol_mismatch",
                    client_version,
                    PROTOCOL_VERSION,
                )
            )
            error_packet = self.get_data_packet(
                PacketType.LOGIN_ERROR,
                (server_id, "system"),
                DEFAULT_SERVER,
                {"error": f"Protocol version mismatch: client={client_version}, server={PROTOCOL_VERSION}"},
            )
            await self._websocket_server.send(
                error_packet.get(server_id),  # type: ignore[arg-type]
                websocket, server_id
            )
            await self._websocket_server.close_connect(server_id, 4001, websocket)
            return
        if server_id not in self._websocket_server.websockets:
            self._websocket_server.websockets[server_id] = websocket
            self._websocket_server.servers_info[server_id] = packet.payload or {}
            self._control.logger.info(self._control.tr("net_core.service.server_login", server_id))
            response = self.get_data_packet(
                PacketType.LOGINED,
                (server_id, "system"),
                DEFAULT_SERVER,
                None,
            )
            await self._websocket_server.send(response.get(server_id), websocket, server_id)  # type: ignore[arg-type]
            self._control.debug(
                f"[FLOW][LOGIN] success server_id={server_id}", level=2
            )
            new_connect(server_id)
            await self._broadcast_server_list(server_id)
        else:
            error_packet = self.get_data_packet(
                PacketType.LOGIN_ERROR,
                (server_id, "system"),
                DEFAULT_SERVER,
                {"error": "Already Login"},
            )
            await self._websocket_server.send(error_packet.get(server_id), websocket, server_id)  # type: ignore[arg-type]
            await self._websocket_server.close_connect(server_id, 401, websocket)
            self._control.debug(
                f"[FLOW][LOGIN] reject server_id={server_id}", level=2
            )

    async def _handle_data_send(self, packet: DataModel, websocket: Any) -> None:
        if verify_md5_checksum(packet.payload, packet.checksum):
            recv_data(packet.to[1], packet.from_[0], packet.payload)  # type: ignore[arg-type]
            await self._send_acknowledgement(packet.from_[0], websocket)
        else:
            await self._send_data_error(packet.from_[0], websocket)

    async def _handle_data_sendok(self, packet: DataModel) -> None:  # type: ignore[override]
        self._websocket_server.last_send_packet.pop(packet.from_[0], None)

    async def _handle_data_error(self, packet: DataModel, websocket: Any) -> None:
        await self._send_last_data_packet(packet.from_[0], websocket)

    async def _handle_file_send(self, packet: DataModel, websocket: Any) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum):
            await self._send_file_error(packet.from_[0], websocket)
            return

        save_path = payload.get("save_path")
        if not save_path:
            await self._send_file_error(packet.from_[0], websocket)
            return

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self._wait_files[packet.from_[0]] = open(save_path, "wb")

    async def _handle_file_sending(self, packet: DataModel, websocket: Any) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum):
            await self._send_file_error(packet.from_[0], websocket)
            return

        waiter = self._wait_files.get(packet.from_[0])
        if not waiter:
            await self._send_file_error(packet.from_[0], websocket)
            return

        try:
            waiter.write(bytes.fromhex(payload.get("file", "")))
            waiter.flush()
        except ValueError:
            await self._send_file_error(packet.from_[0], websocket)

    async def _handle_file_sendok(self, packet: DataModel, websocket: Any) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum):
            await self._send_file_error(packet.from_[0], websocket)
            return

        waiter = self._wait_files.pop(packet.from_[0], None)
        if not waiter:
            await self._send_file_error(packet.from_[0], websocket)
            return

        waiter.close()
        if verify_file_hash(payload.get("save_path", ""), payload.get("hash")):
            recv_file(packet.to[1], packet.from_[0], payload.get("save_path", ""))
        else:
            await self._send_file_error(packet.from_[0], websocket)

    async def _send_acknowledgement(self, server_id: str, websocket: Any) -> None:
        packet = self.get_data_packet(
            PacketType.DATA_SENDOK,
            (server_id, "system"),
            DEFAULT_SERVER,
            None,
        )
        await self._websocket_server.send(packet.get(server_id), websocket, server_id)  # type: ignore[arg-type]

    async def _send_data_error(self, server_id: str, websocket: Any) -> None:
        error_packet = self.get_data_packet(
            PacketType.DATA_ERROR,
            (server_id, "system"),
            DEFAULT_SERVER,
            None,
        )
        await self._websocket_server.send(error_packet.get(server_id), websocket, server_id)  # type: ignore[arg-type]

    async def _send_last_data_packet(self, server_id: str, websocket: Any) -> None:
        last_packet = self._websocket_server.last_send_packet.get(server_id)
        if last_packet:
            await self._websocket_server.send(last_packet.get(server_id), websocket, server_id)  # type: ignore[arg-type]

    async def _send_file_error(self, server_id: str, websocket: Any) -> None:
        error_packet = self.get_data_packet(
            PacketType.FILE_ERROR,
            (server_id, "system"),
            DEFAULT_SERVER,
            None,
        )
        await self._websocket_server.send(error_packet.get(server_id), websocket, server_id)  # type: ignore[arg-type]

    async def _broadcast_server_list(self, server_id: str) -> None:
        packet = self.get_data_packet(
            PacketType.NEW_LOGIN,
            DEFAULT_ALL,
            DEFAULT_SERVER,
            {"server_id": server_id},
        )
        await self._websocket_server.broadcast(packet)

    def _generate_server_credentials(self) -> Tuple[str, str]:
        server_id = generate_random_id(5)
        while server_id in self._websocket_server.websockets:
            server_id = generate_random_id(5)
        return server_id, generate_password()

    def _save_credentials(self, server_id: str, password: str) -> None:
        accounts = self._control.get_config(config_path="account.json")
        accounts[server_id] = password
        self._control.save_config(accounts, "account.json")


class ClientDataPacket:
    """客户端数据包处理逻辑，使用统一的数据模型和校验工具。"""

    def __init__(
        self,
        control_interface: "CoreControlInterface",
        websocket_client: "WebsocketClient",
    ) -> None:
        self._control = control_interface
        self._client = websocket_client
        self._history: Dict[str, List[HistoryEntry]] = {}
        self._recent_packets: List[Tuple[DataModel, str, str]] = []
        self._last_received_sid: int = 0
        self._last_sent_sid: int = 0
        self._wait_file: Optional[Any] = None
        self.server_list: List[str] = []

    @staticmethod
    def _upsert_history_entry(bucket: List[HistoryEntry], sid: int, packet: DataModel | None, direction: str) -> None:
        for index, (existing_sid, _, _) in enumerate(bucket):
            if existing_sid == sid:
                bucket[index] = (sid, packet, direction)
                return
        bucket.append((sid, packet, direction))

    def _history_bucket(self) -> List[HistoryEntry]:
        return self._history.setdefault(DEFAULT_TEMP[0], [])

    def _sort_history(self) -> None:
        bucket = self._history_bucket()
        bucket.sort(key=lambda entry: entry[0])

    def get_data_packet(
        self,
        packet_type: PacketType,
        to_info: Tuple[str, str],
        from_info: Tuple[str, str],
        payload: Optional[Dict[str, Any]] = None,
        *,
        status: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """构建客户端发送的数据包，保持向后兼容的返回结构。"""

        highest_known = self._highest_known_sid()
        if packet_type in PERSISTENT_TYPES:
            sid = highest_known + 1
        elif packet_type is PacketType.PING:
            sid = highest_known
        else:
            sid = highest_known
        packet = DataModel(
            type=packet_type,
            sid=sid,
            to=to_info,
            from_=from_info,  # type: ignore[call-arg]
            payload=payload,
            status=status,
        )
        if packet_type in PERSISTENT_TYPES:
            self._ensure_sid_continuity(sid, DEFAULT_TEMP[0])
            bucket = self._history_bucket()
            self._upsert_history_entry(bucket, sid, packet, "sent")
            self._last_sent_sid = max(self._last_sent_sid, sid)
            self._sort_history()
            self._record_recent(packet, "sent", DEFAULT_TEMP[0])
        return {DEFAULT_TEMP[0]: packet.model_dump(by_alias=True)}

    def get_history_packet(self, server_id: str, old_sid: int) -> List[Dict[str, Any]]:
        if server_id not in self._history:
            return []
        bucket = self._history[server_id]
        results: List[Dict[str, Any]] = []
        for sid, packet, direction in bucket:
            if sid <= old_sid or direction != "sent" or packet is None:
                continue
            results.append(packet.model_dump(by_alias=True))
        return results

    def get_recent_packets(
        self,
        limit: int = 20,
        server_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filtered_entries = [
            entry
            for entry in self._recent_packets
            if server_id is None or entry[2] == server_id
        ]
        entries = filtered_entries[-limit:] if limit > 0 else filtered_entries
        return [
            {
                **packet.model_dump(by_alias=True),
                "direction": direction,
                "server_id": owner_id,
            }
            for packet, direction, owner_id in entries
        ]

    async def parse_msg(self, data: Dict[str, Any]) -> None:
        packet = DataModel.model_validate(data)
        server_id = packet.from_[0]
        bucket = self._history.setdefault(server_id, [])
        self._upsert_history_entry(bucket, packet.sid, packet, "received")
        self._record_recent(packet, "received", server_id)
        if packet.type in PERSISTENT_TYPES:
            self._last_received_sid = max(self._last_received_sid, packet.sid)
        self._control.debug(
            f"[R][{packet.type}][{packet.from_} -> {packet.to}][{packet.sid}] {packet.payload}",
            level=1,
        )

        match packet.type:
            case PacketType.PONG:
                return
            case PacketType.REGISTERED:
                await self._handle_registered(packet)
            case PacketType.REGISTER_ERROR:
                await self._handle_register_error(packet)
            case PacketType.LOGINED:
                await self._handle_logined(packet)
            case PacketType.NEW_LOGIN:
                await self._handle_new_login(packet)
            case PacketType.DEL_LOGIN:
                await self._handle_del_login(packet)
            case PacketType.LOGIN_ERROR:
                await self._handle_login_error(packet)
            case PacketType.DATA_SEND:
                await self._handle_data_send(packet)
            case PacketType.DATA_SENDOK:
                await self._handle_data_sendok()
            case PacketType.DATA_ERROR:
                await self._handle_data_error()
            case PacketType.FILE_SEND:
                await self._handle_file_send(packet)
            case PacketType.FILE_SENDING:
                await self._handle_file_sending(packet)
            case PacketType.FILE_SENDOK:
                await self._handle_file_sendok(packet)
            case PacketType.FILE_ERROR:
                await self._handle_file_error()
            case _:
                handled = await self._dispatch_custom_handlers(packet)
                if not handled:
                    self._control.debug(
                        f"Unhandled client packet type: {packet.type} status={packet.status}",
                        level=3,
                    )

    async def _dispatch_custom_handlers(self, packet: DataModel) -> bool:
        """查找并执行 StatusRegistry 中注册的自定义处理器。"""
        handlers = status_registry.get_handlers(str(packet.type), packet.status)  # type: ignore[arg-type]
        if not handlers:
            return False
        for handler in handlers:
            try:
                import asyncio
                result = handler(packet)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._control.logger.error(
                    f"Custom handler error for type={packet.type} status={packet.status}: {exc}"
                )
        return True

    async def _handle_registered(self, packet: DataModel) -> None:
        self._control.debug(
            f"[FLOW][REGISTER] success server_id={packet.to[0]}", level=2
        )
        if not verify_md5_checksum(packet.payload, packet.checksum):
            await self._send_register_error()
            return

        payload = packet.payload or {}
        server_id = packet.to[0]
        password = payload.get("password", "")

        if not password:
            self._control.logger.error("Register payload missing password field")
            await self._send_register_error()
            return

        self._client.config["account"] = server_id
        self._client.config["password"] = password
        self._control.save_config(self._client.config)

        self._control.logger.info(
            self._control.tr("net_core.service.register_success_client", server_id)
        )
        aes_main(self._control, password)
        await self._client.start_login(reason="post-register")

    async def _handle_register_error(self, packet: DataModel) -> None:
        self._control.debug(
            f"[FLOW][REGISTER] error payload={packet.payload}", level=2
        )
        self._control.logger.error(f"Register Error: {packet.payload}")
        self._client.stop_server()

    async def _handle_logined(self, packet: DataModel) -> None:
        self._control.debug(
            f"[FLOW][LOGIN] success server_id={packet.to[0]}", level=2
        )
        self._client.server_id = packet.to[0]
        self._client.start_keepalive()
        connected()

    async def _handle_new_login(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        server_id = payload.get("server_id")
        if server_id and server_id not in self.server_list:
            self.server_list.append(server_id)
            new_connect(server_id)

    async def _handle_del_login(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        server_id = payload.get("server_id")
        if server_id:
            if server_id in self.server_list:
                self.server_list.remove(server_id)
            del_connect(server_id)

    async def _handle_login_error(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        self._control.debug(
            f"[FLOW][LOGIN] error info={payload.get('error')}", level=2
        )
        self._control.logger.error(f"Login Error: {payload.get('error')}")
        self._client.stop_server()

    async def _handle_data_send(self, packet: DataModel) -> None:
        if packet.payload is None or verify_md5_checksum(packet.payload, packet.checksum):
            recv_data(packet.to[1], packet.from_[0], packet.payload)  # type: ignore[arg-type]
            await self._send_data_response()
        else:
            await self._send_data_error()

    async def _handle_data_sendok(self) -> None:
        self._client.last_data_packet = None

    async def _handle_data_error(self) -> None:
        await self._send_last_data_packet()

    async def _handle_file_send(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum):
            await self._send_file_error()
            return

        save_path = payload.get("save_path")
        if not save_path:
            await self._send_file_error()
            return

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self._wait_file = open(save_path, "wb")

    async def _handle_file_sending(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum) or self._wait_file is None:
            await self._send_file_error()
            return

        try:
            self._wait_file.write(bytes.fromhex(payload.get("file", "")))
            self._wait_file.flush()
        except ValueError:
            await self._send_file_error()

    async def _handle_file_sendok(self, packet: DataModel) -> None:
        payload = packet.payload or {}
        if not verify_md5_checksum(payload, packet.checksum) or self._wait_file is None:
            await self._send_file_error()
            return

        self._wait_file.close()
        self._wait_file = None
        if verify_file_hash(payload.get("save_path", ""), payload.get("hash")):
            recv_file(packet.to[1], packet.from_[0], payload.get("save_path", ""))
        else:
            await self._send_file_error()

    async def _handle_file_error(self) -> None:
        if self._wait_file is not None:
            try:
                self._wait_file.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            self._wait_file = None

    def _record_recent(self, packet: DataModel, direction: str, server_id: str) -> None:
        if packet.type not in PERSISTENT_TYPES:
            return
        if direction == "received":
            self._last_received_sid = max(self._last_received_sid, packet.sid)
            self._ensure_sid_continuity(packet.sid, server_id)
            bucket = self._history.setdefault(server_id, [])
            self._upsert_history_entry(bucket, packet.sid, None, "received")
        else:
            self._ensure_sid_continuity(packet.sid, DEFAULT_TEMP[0])
            bucket = self._history_bucket()
            self._upsert_history_entry(bucket, packet.sid, packet, "sent")
            self._last_sent_sid = max(self._last_sent_sid, packet.sid)
        self._recent_packets.append((packet, direction, server_id))
        if len(self._recent_packets) > 100:
            self._recent_packets = self._recent_packets[-100:]

    def set_sid_state(
        self,
        *,
        next_sid: Optional[int] = None,
        last_received: Optional[int] = None,
    ) -> Dict[str, int]:
        if next_sid is not None:
            if next_sid < 1:
                for bucket in self._history.values():
                    bucket.clear()
                self._history.clear()
                self._last_sent_sid = 0
                if last_received is None:
                    self._last_received_sid = 0
            else:
                bucket = self._history_bucket()
                cutoff = next_sid
                self._history[DEFAULT_TEMP[0]] = [
                    entry
                    for entry in bucket
                    if entry[0] < cutoff
                ]
                self._ensure_sid_continuity(next_sid - 1, DEFAULT_TEMP[0])
                if next_sid > 1:
                    bucket = self._history_bucket()
                    self._upsert_history_entry(bucket, next_sid - 1, None, "sent")
                self._last_sent_sid = next_sid - 1
                if last_received is None and self._last_received_sid > self._last_sent_sid:
                    self._last_received_sid = self._last_sent_sid
        if last_received is not None:
            if last_received < 0:
                raise ValueError("last_received must be non-negative")
            self._last_received_sid = last_received
            if last_received > 0:
                self._ensure_sid_continuity(last_received, DEFAULT_TEMP[0])
                bucket = self._history.setdefault(DEFAULT_TEMP[0], [])
                self._upsert_history_entry(bucket, last_received, None, "sent")
        return {
            "next_sid": self._highest_known_sid() + 1,
            "last_received": self._last_received_sid,
        }

    def delete_recent_sids(self, count: int) -> Dict[str, int]:
        if count <= 0:
            raise ValueError("count must be positive")

        if DEFAULT_TEMP[0] not in self._history:
            return {
                "removed": 0,
                "next_sid": self._highest_known_sid() + 1,
                "last_received": self._last_received_sid,
            }
        bucket = self._history_bucket()
        if not bucket:
            return {
                "removed": 0,
                "next_sid": self._highest_known_sid() + 1,
                "last_received": self._last_received_sid,
            }

        removed: list[int] = []
        new_bucket: List[HistoryEntry] = []
        for sid, packet, direction in sorted(bucket, key=lambda item: item[0], reverse=True):
            if len(removed) < count:
                removed.append(sid)
                continue
            new_bucket.append((sid, packet, direction))
        new_bucket.sort(key=lambda item: item[0])
        self._history[DEFAULT_TEMP[0]] = new_bucket

        if not removed:
            return {
                "removed": 0,
                "next_sid": self._highest_known_sid() + 1,
                "last_received": self._last_received_sid,
            }

        removed_set = set(removed)
        self._recent_packets = [
            (packet, direction, server_id)
            for packet, direction, server_id in self._recent_packets
            if packet.sid not in removed_set or server_id != DEFAULT_TEMP[0]
        ]

        remaining_sent = [sid for sid, _, direction in new_bucket if direction == "sent"]
        self._last_sent_sid = max(remaining_sent, default=0)

        remaining_received = [sid for sid, _, direction in new_bucket if direction == "received"]
        self._last_received_sid = max(remaining_received, default=0)

        if self._last_sent_sid < self._last_received_sid:
            self._last_sent_sid = self._last_received_sid

        return {
            "removed": len(removed),
            "next_sid": self._highest_known_sid() + 1,
            "last_received": self._last_received_sid,
        }

    def _highest_sid(self) -> int:
        bucket = self._history.get(DEFAULT_TEMP[0], [])
        return max((sid for sid, _, _ in bucket), default=0)

    def _highest_known_sid(self) -> int:
        return max(self._highest_sid(), self._last_received_sid, self._last_sent_sid)

    def _ensure_sid_continuity(self, sid: int, server_id: str) -> None:
        if sid <= 0:
            return
        bucket = self._history.setdefault(server_id, [])
        existing_sids = {entry[0] for entry in bucket}
        current_max = max(existing_sids, default=0)
        if sid <= current_max + 1:
            return
        for missing in range(current_max + 1, sid):
            if missing not in existing_sids:
                bucket.append((missing, None, "sent"))
                existing_sids.add(missing)
        bucket.sort(key=lambda entry: entry[0])

    async def _send_register_error(self) -> None:
        await self._client.send(
            self.get_data_packet(
                PacketType.REGISTER_ERROR,
                DEFAULT_SERVER,
                DEFAULT_TEMP,
                None,
            )
        )

    async def _send_data_response(self) -> None:
        if not self._client.server_id:
            return
        await self._client.send(
            self.get_data_packet(
                PacketType.DATA_SENDOK,
                DEFAULT_SERVER,
                (self._client.server_id, "system"),
                None,
            )
        )

    async def _send_data_error(self) -> None:
        if not self._client.server_id:
            return
        await self._client.send(
            self.get_data_packet(
                PacketType.DATA_ERROR,
                DEFAULT_SERVER,
                (self._client.server_id, "system"),
                None,
            )
        )

    async def _send_last_data_packet(self) -> None:
        if self._client.last_data_packet:
            await self._client.send(self._client.last_data_packet)

    async def _send_file_error(self) -> None:
        if not self._client.server_id:
            return
        await self._client.send(
            self.get_data_packet(
                PacketType.FILE_ERROR,
                DEFAULT_SERVER,
                (self._client.server_id, "system"),
                None,
            )
        )
