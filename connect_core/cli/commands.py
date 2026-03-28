from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from connect_core.context import GlobalContext
from connect_core.cli.server_list import fetch_server_ids
from connect_core.cli.command_core import SimpleCommandBuilder
from connect_core.cli.arguments import GreedyTextArgument
from connect_core.plugin.init_plugin import (
    get_plugins,
    load_plugin,
    reload_plugin,
    unload_plugin,
)
from connect_core.tools.tools import auto_trigger

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface


CompleterTree = Dict[str, Optional[Dict[str, object]]]


class Command:
    def __init__(self, control_interface: "CoreControlInterface") -> None:
        self._control = control_interface
        self._command_control = control_interface.command_control
        self._completer_words: CompleterTree = {}
        self._server_id_cache: list[str] = []
        self._supports_dynamic_lists = hasattr(
            self._command_control, "register_dynamic_list"
        )
        if self._supports_dynamic_lists:
            self._command_control.register_dynamic_list(  # type: ignore[attr-defined]
                "server_ids", self._iter_server_ids_for_completer
            )
        self._plugin_dir = self._resolve_plugin_directory()
        self._register_common_commands()
        self._refresh_completer_words_once()
        self._start_completer_refresh()

    def _resolve_plugin_directory(self) -> Path:
        base_path = GlobalContext.get_path()
        try:
            return Path(base_path) / "plugins"
        except Exception:
            return Path("./plugins")

    def _register_common_commands(self) -> None:
        builder = SimpleCommandBuilder()
        builder.command("help", self._handle_help)
        builder.command("list", self._handle_list)
        builder.command("plugin load <path>", self._handle_plugin_load)
        builder.command("plugin reload <id>", self._handle_plugin_reload)
        builder.command("plugin unload <id>", self._handle_plugin_unload)
        builder.command("history packets", self._handle_history_packets)
        builder.arg("path", GreedyTextArgument)
        builder.register(self._command_control)
        history_completions: Dict[str, Optional[Dict[str, object]]] = {
            "all": None,
            "*": None,
        }
        if not self._control.is_server:
            history_completions["-----"] = None
        if self._supports_dynamic_lists:
            history_completions["[server_ids]"] = None
        else:
            fallback_servers = fetch_server_ids(self._control)
            for server_id in fallback_servers:
                history_completions[server_id] = None
            self._server_id_cache = list(fallback_servers)

        self._completer_words = {
            "help": None,
            "list": None,
            "plugin": {
                "load": {},
                "reload": {},
                "unload": {},
            },
            "history": {"packets": history_completions},
        }

        if GlobalContext.is_debug_mode():
            self._completer_words.update(
                {
                    "debug": {
                        "packet": {"send": None},
                        "sid": {
                            "del": {"<count>": None},
                            "ack": {"<value>": None},
                        },
                    },
                    "logtest": {
                        "start": None,
                        "stop": None,
                        "status": None,
                        "set_interval": None,
                    },
                }
            )
        self._command_control.set_completer_words(self._completer_words)
        self._command_control.flush_cli()

    def _handle_help(self, *_: str) -> None:
        if self._control.is_server:
            message = self._control.tr("commands.server_help")
        else:
            message = self._control.tr("commands.client_help")
        self._control.logger.info(message)

    def _handle_list(self, *_: str) -> None:
        self._control.logger.info("==list==")
        for index, server_id in enumerate(fetch_server_ids(self._control), start=1):
            self._control.logger.info(f"{index}. {server_id}")

    def _handle_plugin_load(self, path: str) -> None:
        load_plugin(path)

    def _handle_plugin_reload(self, plugin_id: str) -> None:
        reload_plugin(plugin_id)

    def _handle_plugin_unload(self, plugin_id: str) -> None:
        unload_plugin(plugin_id)

    def _handle_history_packets(self, *args: str) -> None:
        server_filter = args[0] if args else None
        if server_filter in {"*", "all", "<server_id>"}:
            server_filter = None
        self._control.logger.info(self._control.tr("commands.history_packets_header"))
        if server_filter:
            self._control.logger.info(
                self._control.tr("commands.history_packets_filter", server_filter)
            )

        entries = self._get_packet_history(server_filter)
        if not entries:
            self._control.logger.info(
                self._control.tr("commands.history_packets_empty")
            )
            return

        for index, packet in enumerate(entries, start=1):
            type_display = packet.get("type")
            sid_display = packet.get("sid")
            from_display = packet.get("from") or packet.get("from_")
            to_display = packet.get("to")
            summary = packet.get("payload")
            direction = self._direction_label(str(packet.get("direction", "")).lower())
            owner_display = packet.get("server_id", "?")
            self._control.logger.info(
                f"{index:>2}. [{direction}] server={owner_display} sid={sid_display} type={type_display} from={from_display} to={to_display} payload={summary}"
            )

    def _iter_server_ids_for_completer(self) -> list[str]:
        return list(self._server_id_cache)

    def _get_packet_history(self, server_filter: Optional[str] = None) -> list[dict]:
        if self._control.is_server:
            try:
                from connect_core.websockets.server import get_recent_packets

                packets = get_recent_packets(20, server_filter)
            except Exception as exc:  # pragma: no cover - defensive log
                self._control.logger.debug(
                    f"Failed to fetch server history packets: {exc}"
                )
                packets = []
        else:
            try:
                from connect_core.websockets.client import get_recent_packets

                packets = get_recent_packets(20, server_filter)
            except Exception as exc:  # pragma: no cover - defensive log
                self._control.logger.debug(
                    f"Failed to fetch client history packets: {exc}"
                )
                packets = []

        return packets

    def _direction_label(self, direction: str) -> str:
        if not direction:
            return "?"
        key = f"commands.history_packets_direction.{direction}"
        translated = self._control.tr(key)
        return translated if translated != key else direction

    def _refresh_completer_words_once(self) -> None:
        if self._update_completer_words():
            self._command_control.set_completer_words(self._completer_words)
            self._command_control.flush_cli()

    def _scan_plugin_directory(self) -> Dict[str, None]:
        if not self._plugin_dir.exists() or not self._plugin_dir.is_dir():
            return {}
        try:
            return {
                entry.name: None
                for entry in self._plugin_dir.iterdir()
                if not entry.name.startswith(".")
            }
        except OSError:
            return {}

    def _collect_plugin_ids(self) -> Dict[str, None]:
        try:
            return {plugin_id: None for plugin_id in get_plugins()}
        except RuntimeError:
            return {}
        except Exception as exc:  # pragma: no cover - defensive log
            self._control.logger.debug(f"Failed to list plugins: {exc}")
            return {}

    def _update_completer_words(self) -> bool:
        plugin_group = self._completer_words.setdefault(
            "plugin", {"load": {}, "reload": {}, "unload": {}}
        )
        assert isinstance(plugin_group, dict)
        file_options = self._scan_plugin_directory()
        plugin_ids = self._collect_plugin_ids()

        changed = False
        if plugin_group.get("load") != file_options:
            plugin_group["load"] = file_options
            changed = True
        if plugin_group.get("reload") != plugin_ids:
            plugin_group["reload"] = plugin_ids
            changed = True
        if plugin_group.get("unload") != plugin_ids:
            plugin_group["unload"] = plugin_ids
            changed = True

        latest_servers = fetch_server_ids(self._control)
        history_group = self._completer_words.setdefault("history", {})
        assert isinstance(history_group, dict)

        if self._supports_dynamic_lists:
            desired_history_template: Dict[str, Optional[Dict[str, object]]] = {
                "all": None,
                "*": None,
            }
            if not self._control.is_server:
                desired_history_template["-----"] = None
            desired_history_template["[server_ids]"] = None
            if history_group.get("packets") != desired_history_template:
                history_group["packets"] = desired_history_template
                changed = True

            if latest_servers != self._server_id_cache:
                self._server_id_cache = latest_servers
                changed = True
        else:
            fallback_mapping: Dict[str, Optional[Dict[str, object]]] = {
                "all": None,
                "*": None,
            }
            if not self._control.is_server:
                fallback_mapping["-----"] = None
            for server_id in latest_servers:
                fallback_mapping[server_id] = None
            if history_group.get("packets") != fallback_mapping:
                history_group["packets"] = fallback_mapping
                changed = True
            if latest_servers != self._server_id_cache:
                self._server_id_cache = latest_servers
                changed = True

        return changed

    @auto_trigger(5, "plugin_file_list")
    def _start_completer_refresh(self) -> None:
        if self._update_completer_words():
            self._command_control.set_completer_words(self._completer_words)
            self._command_control.flush_cli()


class ServerCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface") -> None:
        super().__init__(control_interface)
        self._register_server_commands()

    def _register_server_commands(self) -> None:
        builder = SimpleCommandBuilder()
        builder.command("getkey", self._handle_getkey)
        builder.register(self._command_control)
        self._completer_words["getkey"] = None
        self._command_control.set_completer_words(self._completer_words)
        self._command_control.flush_cli()

    def _handle_getkey(self, *_: str) -> None:
        from connect_core.account.register_system import get_password

        key = get_password()
        self._control.logger.info(self._control.tr("cli.starting.password", key))


class ClientCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface") -> None:
        super().__init__(control_interface)
        self._register_client_commands()

    def _register_client_commands(self) -> None:
        builder = SimpleCommandBuilder()
        builder.command("info", self._handle_info)
        builder.register(self._command_control)
        self._completer_words["info"] = None
        self._command_control.set_completer_words(self._completer_words)
        self._command_control.flush_cli()

    def _handle_info(self, *_: str) -> None:
        self._control.logger.info("==info==")
        server_id = self._get_server_id()
        if server_id:
            self._control.logger.info(f"Main Server Connected! Server ID: {server_id}")
        else:
            self._control.logger.info("Main Server Disconnected!")

    def _get_server_id(self) -> Optional[str]:
        try:
            from connect_core.websockets.client import get_server_id

            return get_server_id()
        except Exception as exc:  # pragma: no cover - defensive log
            self._control.logger.debug(f"Failed to fetch server id: {exc}")
            return None
