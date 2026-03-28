from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from connect_core.context import GlobalContext
from connect_core.interface.control_interface import CoreControlInterface

from .loader import PluginLoader, PluginLoadError

__all__ = [
    "PluginLoadError",
    "PluginLoader",
    "init_plugin_main",
    "mcdr_add_entry_point",
    "new_connect",
    "del_connect",
    "connected",
    "disconnected",
    "websockets_started",
    "recv_data",
    "recv_file",
    "load_plugin",
    "unload_plugin",
    "reload_plugin",
    "get_plugins",
]


_plugin_loader: Optional[PluginLoader] = None


def init_plugin_main(control_interface: CoreControlInterface) -> None:
    """Initialize plugin loader and load non-MCDR plugins."""

    global _plugin_loader

    if GlobalContext.is_mcdr_mode():
        _plugin_loader = None
        control_interface.logger.debug(
            "Plugin loader disabled: management delegated to MCDR"
        )
        return

    plugin_dir = _resolve_plugin_directory(control_interface)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    _plugin_loader = PluginLoader(control_interface, plugin_dir)
    _plugin_loader.load_plugins()


def mcdr_add_entry_point(sid: str, entry_point: str) -> bool:
    loader = _require_loader()
    return loader.mcdr_add_entry_point(sid, entry_point)


def new_connect(server_id: str) -> None:
    loader = _require_loader()
    loader.handle_event("new_connect", None, server_id)


def del_connect(server_id: str) -> None:
    loader = _require_loader()
    loader.handle_event("del_connect", None, server_id)


def connected() -> None:
    loader = _require_loader()
    loader.handle_event("connected")


def disconnected() -> None:
    loader = _require_loader()
    loader.handle_event("disconnected")


def websockets_started() -> None:
    loader = _require_loader()
    loader.handle_event("websockets_started")


def recv_data(sid: str, from_server_id: str, data: dict) -> None:
    loader = _require_loader()
    loader.handle_event("recv_data", sid, from_server_id, data)


def recv_file(sid: str, from_server_id: str, file_path: str) -> None:
    loader = _require_loader()
    loader.handle_event("recv_file", sid, from_server_id, file_path)


def load_plugin(plugin_file: str | Path) -> None:
    loader = _require_loader()
    loader.load_plugin(plugin_file)


def unload_plugin(sid: str) -> None:
    loader = _require_loader()
    loader.unload(sid)


def reload_plugin(sid: str) -> None:
    loader = _require_loader()
    loader.reload(sid)


def get_plugins() -> Dict[str, Dict[str, Any]]:
    loader = _require_loader()
    return {pid: record.info for pid, record in loader.plugins.items()}


def _require_loader() -> PluginLoader:
    if _plugin_loader is None:
        if GlobalContext.is_mcdr_mode():
            raise RuntimeError("Plugin loader is disabled when running in MCDR mode")
        raise RuntimeError("Plugin loader has not been initialized")
    return _plugin_loader


def _resolve_plugin_directory(control_interface: CoreControlInterface) -> Path:
    mcdr_core = GlobalContext.get_mcdr_core()
    if mcdr_core is not None:
        try:
            plugin_file = mcdr_core.get_plugin_file_path(control_interface.sid)
            plugin_dir = Path(plugin_file).parent
            return plugin_dir
        except Exception:
            control_interface.logger.warning(
                "Failed to obtain plugin directory from MCDR, falling back to local plugins/ folder"
            )

    base_path = GlobalContext.get_path()
    # 当以 .pyz 或其他归档文件运行时，get_path 可能指向文件本身；此时使用其父目录。
    try:
        if base_path.exists() and not base_path.is_dir():
            base_path = base_path.parent
    except OSError:
        # 在特定平台上 is_dir/is_file 可能抛出异常，退回父目录以保证可写路径。
        base_path = base_path.parent

    return (base_path / "plugins").resolve()
