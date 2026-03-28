"""Tests for data_packet: DataModel, PacketType, PacketStatus, StatusRegistry."""

from __future__ import annotations

import time
from typing import Dict

import pytest
from pydantic import ValidationError

from connect_core.websockets.data_packet import (
    PROTOCOL_VERSION,
    DataModel,
    PacketStatus,
    PacketType,
    StatusRegistry,
)


class TestPacketType:
    def test_all_values_are_strings(self):
        for pt in PacketType:
            assert isinstance(pt.value, str)

    def test_expected_members_exist(self):
        names = {m.name for m in PacketType}
        for expected in ("PING", "PONG", "LOGIN", "DATA_SEND", "FILE_SEND"):
            assert expected in names


class TestPacketStatus:
    def test_all_values_are_strings(self):
        for ps in PacketStatus:
            assert isinstance(ps.value, str)

    def test_request_ok_error_exist(self):
        assert PacketStatus.REQUEST.value == "request"
        assert PacketStatus.OK.value == "ok"
        assert PacketStatus.ERROR.value == "error"


class TestProtocolVersion:
    def test_version_is_positive_int(self):
        assert isinstance(PROTOCOL_VERSION, int)
        assert PROTOCOL_VERSION >= 1


class TestStatusRegistry:
    @pytest.fixture()
    def registry(self) -> StatusRegistry:
        return StatusRegistry()

    def test_register_and_get_statuses(self, registry: StatusRegistry):
        registry.register_status(PacketType.DATA_SEND, "custom_ack")
        statuses = registry.get_registered_statuses(PacketType.DATA_SEND)
        assert "custom_ack" in statuses

    def test_register_handler(self, registry: StatusRegistry):
        called = []
        handler = lambda: called.append(True)
        registry.register_handler(PacketType.DATA_SEND, "custom_ack", handler)
        handlers = registry.get_handlers(PacketType.DATA_SEND, "custom_ack")
        assert handler in handlers

    def test_unregister_handler(self, registry: StatusRegistry):
        handler = lambda: None
        registry.register_handler(PacketType.PING, "ok", handler)
        registry.unregister_handler(PacketType.PING, "ok", handler)
        assert handler not in registry.get_handlers(PacketType.PING, "ok")

    def test_get_handlers_none_status(self, registry: StatusRegistry):
        assert registry.get_handlers(PacketType.PING, None) == []

    def test_get_handlers_empty(self, registry: StatusRegistry):
        assert registry.get_handlers(PacketType.LOGIN, "nonexistent") == []

    def test_get_registered_statuses_empty(self, registry: StatusRegistry):
        assert registry.get_registered_statuses(PacketType.PONG) == set()


class TestDataModel:
    def _base_data(self, **overrides) -> Dict:
        data = {
            "type": PacketType.DATA_SEND.value,
            "status": PacketStatus.REQUEST.value,
            "sid": 1,
            "to": ("server_a", "plugin_x"),
            "from": ("client_b", "plugin_y"),
            "payload": {"key": "value"},
        }
        data.update(overrides)
        return data

    def test_create_valid(self):
        m = DataModel(**self._base_data())
        assert m.type == PacketType.DATA_SEND
        assert m.from_ == ("client_b", "plugin_y")
        assert m.payload == {"key": "value"}
        assert m.checksum is not None

    def test_timestamp_auto(self):
        before = time.time()
        m = DataModel(**self._base_data())
        after = time.time()
        assert before <= m.timestamp <= after

    def test_checksum_generated(self):
        m = DataModel(**self._base_data())
        assert isinstance(m.checksum, str)
        assert len(m.checksum) > 0

    def test_no_payload_no_checksum(self):
        m = DataModel(**self._base_data(payload=None))
        assert m.checksum is None

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            DataModel(type=PacketType.PING.value, sid=1)
