from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from connect_core.context import GlobalContext
from connect_core.plugin.loader import PluginLoader
from connect_core.plugin.sandbox import plugin_sandbox, prime_plugin_sandbox
from connect_core.websockets.server import SlidingWindowRateLimiter, WebsocketServer


class _DummyLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: object, *args: object, **kwargs: object) -> None:
        self.messages.append(str(message))

    def warning(self, message: object, *args: object, **kwargs: object) -> None:
        self.messages.append(str(message))

    def error(self, message: object, *args: object, **kwargs: object) -> None:
        self.messages.append(str(message))

    def debug(self, message: object, *args: object, **kwargs: object) -> None:
        self.messages.append(str(message))

    def exception(self, message: object, *args: object, **kwargs: object) -> None:
        self.messages.append(str(message))


class _DummyControl:
    def __init__(self) -> None:
        self.logger = _DummyLogger()
        self.log_system = SimpleNamespace(logger=self.logger)
        self.config = SimpleNamespace(
            ip="127.0.0.1",
            port=23233,
            rate_limit_enabled=True,
            rate_limit_max_requests=2,
            rate_limit_window_seconds=10.0,
            healthcheck_enabled=False,
            healthcheck_host="127.0.0.1",
            healthcheck_port=23234,
            plugin_sandbox_enabled=True,
        )
        self.command_control = SimpleNamespace(remove_sid=lambda target_sid: None)

    def tr(self, key: str, *args: object) -> str:
        suffix = " ".join(map(str, args)).strip()
        return f"{key}{(' ' + suffix) if suffix else ''}"

    def translate(self, key: str, *args: object) -> str:
        return self.tr(key, *args)

    def get_config(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {}

    def save_config(self, *args: object, **kwargs: object) -> None:
        return None

    def debug(self, message: object, *, level: int = 1) -> None:
        self.logger.debug(message)


class _DummyStreamWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


@pytest.fixture()
def dummy_control() -> _DummyControl:
    return _DummyControl()


class TestRateLimiter:
    def test_sliding_window_limiter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        timestamps = iter([0.0, 1.0, 2.0, 12.0])
        monkeypatch.setattr(
            "connect_core.websockets.server.time.monotonic",
            lambda: next(timestamps),
        )
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10.0)

        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is False
        assert limiter.allow("client-a") is True


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_request_returns_ok(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dummy_control: _DummyControl,
    ) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        GlobalContext.reset()
        GlobalContext(server=True)
        monkeypatch.setattr(GlobalContext, "get_path", staticmethod(lambda: workspace))

        server = WebsocketServer(dummy_control)
        server.servers_info["alpha"] = {"path": "a"}

        reader = asyncio.StreamReader()
        reader.feed_data(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        reader.feed_eof()
        writer = _DummyStreamWriter()

        await server._handle_health_request(reader, writer)

        response = bytes(writer.buffer)
        assert response.startswith(b"HTTP/1.1 200 OK")
        payload = json.loads(response.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
        assert payload["status"] == "ok"
        assert payload["connected_servers"] == 0
        assert payload["known_servers"] == ["alpha"]


class TestPluginSandbox:
    def test_sandbox_blocks_internal_connect_core_imports(self) -> None:
        prime_plugin_sandbox()
        sys.modules.pop("connect_core.cli.debug_tools", None)

        with pytest.raises(ImportError, match="not allowed to import internal module"):
            with plugin_sandbox("demo-plugin"):
                importlib.import_module("connect_core.cli.debug_tools")

    def test_sandbox_allows_public_api_imports(self) -> None:
        prime_plugin_sandbox()
        with plugin_sandbox("demo-plugin"):
            module = importlib.import_module("connect_core.api")
        assert module is not None

    def test_plugin_loader_rejects_plugin_using_internal_module(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dummy_control: _DummyControl,
    ) -> None:
        workspace = tmp_path / "workspace"
        plugin_root = workspace / "plugins"
        plugin_dir = plugin_root / "bad_plugin"
        package_dir = plugin_dir / "bad_plugin"
        package_dir.mkdir(parents=True)
        workspace.mkdir(exist_ok=True)
        GlobalContext.reset()
        GlobalContext(server=True)
        monkeypatch.setattr(GlobalContext, "get_path", staticmethod(lambda: workspace))

        (plugin_dir / "connectcore.plugin.json").write_text(
            json.dumps(
                {
                    "id": "bad_plugin",
                    "name": "Bad Plugin",
                    "version": "0.1.0",
                    "entrypoint": "bad_plugin.entry",
                }
            ),
            encoding="utf-8",
        )
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "entry.py").write_text(
            "import connect_core.cli.debug_tools\n\n"
            "def on_load(control_interface):\n"
            "    return None\n",
            encoding="utf-8",
        )

        loader = PluginLoader(dummy_control, plugin_root)
        loader.load_plugins()

        assert "bad_plugin" not in loader.plugins
        assert any("not allowed to import internal module" in msg for msg in dummy_control.logger.messages)
