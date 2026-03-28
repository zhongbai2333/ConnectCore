from __future__ import annotations

import json
import sys
import traceback
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from importlib import import_module, util
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from connect_core.context import GlobalContext
from connect_core.interface.control_interface import (
    CoreControlInterface,
    PluginControlInterface,
)
from connect_core.plugin.sandbox import plugin_sandbox, prime_plugin_sandbox
from connect_core.tools.base_config import BaseConfig


class PluginLoadError(Exception):
    """Raised when a plugin cannot be loaded successfully."""


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    entrypoint: str
    path: Path
    module: ModuleType
    info: Dict[str, Any]
    config_class: type[BaseConfig]
    sys_path_entry: Optional[str] = None
    dependencies: tuple[str, ...] = ()
    dependency_specs: Dict[str, SpecifierSet] = field(default_factory=dict)


class PluginLoader:
    """Load and manage ConnectCore plugins."""

    def __init__(
        self, control_interface: CoreControlInterface, plugin_dir: Path
    ) -> None:
        self._control = control_interface
        self._plugin_dir = plugin_dir
        self._plugins: Dict[str, PluginRecord] = {}
        self._sys_path_entries: Dict[str, int] = {}
        self._available: Dict[str, tuple[Path, Dict[str, Any]]] = {}
        self._dependency_graph: Dict[str, tuple[str, ...]] = {}
        self._dependency_requirements: Dict[str, Dict[str, SpecifierSet]] = {}
        self._active_dependents: Dict[str, set[str]] = defaultdict(set)
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

    def load_plugins(self) -> None:
        """Load all supported plugins in the plugin directory respecting dependencies."""

        self._discover_plugins()
        order = self._resolve_load_sequence(self._available.keys())
        self._load_sequence(order)

    def _discover_plugins(self) -> None:
        for candidate in sorted(self._plugin_dir.iterdir()):
            if candidate.name.startswith("."):
                continue
            if not (
                candidate.is_dir() or candidate.suffix.lower() in {".mcdr", ".pyz"}
            ):
                continue
            plugin_path = candidate.resolve()
            try:
                manifest = self._read_manifest(plugin_path)
            except PluginLoadError as exc:
                self._control.logger.error(str(exc))
                continue
            plugin_id = manifest.get("id")
            if not plugin_id:
                self._control.logger.error(
                    f"Plugin at {plugin_path} missing 'id' field"
                )
                continue
            self._register_candidate(plugin_id, plugin_path, manifest)

    def _register_candidate(
        self, plugin_id: str, plugin_path: Path, manifest: Dict[str, Any]
    ) -> None:
        dependencies, specifiers = self._sanitize_dependencies(
            plugin_id, manifest.get("dependencies")
        )
        existing = self._available.get(plugin_id)
        if existing and existing[0] != plugin_path:
            self._control.logger.warning(
                f"Duplicate plugin id '{plugin_id}' detected, using {plugin_path}"
            )
        self._available[plugin_id] = (plugin_path, manifest)
        self._dependency_graph[plugin_id] = dependencies
        self._dependency_requirements[plugin_id] = specifiers
        manifest["dependencies"] = self._snapshot_dependencies(dependencies, specifiers)

    def _sanitize_dependencies(
        self, plugin_id: str, raw: Any
    ) -> tuple[tuple[str, ...], Dict[str, SpecifierSet]]:
        if not raw:
            return (), {}

        seen: set[str] = set()
        ordered_ids: list[str] = []
        specifiers: Dict[str, SpecifierSet] = {}

        def register(dep_id: Optional[str], spec: Optional[SpecifierSet]) -> None:
            if not dep_id:
                return
            candidate = dep_id.strip()
            if not candidate or candidate == plugin_id:
                return
            if candidate not in seen:
                seen.add(candidate)
                ordered_ids.append(candidate)
            if spec and str(spec):
                existing = specifiers.get(candidate)
                if existing:
                    specifiers[candidate] = existing & spec
                else:
                    specifiers[candidate] = spec

        if isinstance(raw, dict):
            for dep_id, requirement in raw.items():
                if not isinstance(dep_id, str):
                    self._control.logger.warning(
                        f"[{plugin_id}] dependency key '{dep_id}' ignored (not a string)"
                    )
                    continue
                spec = self._parse_specifier(plugin_id, dep_id, requirement)
                register(dep_id, spec)
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, str):
                    dep_id, spec = self._parse_requirement_string(plugin_id, item)
                    register(dep_id, spec)
                elif isinstance(item, dict):
                    for dep_id, requirement in item.items():
                        if not isinstance(dep_id, str):
                            self._control.logger.warning(
                                f"[{plugin_id}] dependency key '{dep_id}' ignored (not a string)"
                            )
                            continue
                        spec = self._parse_specifier(plugin_id, dep_id, requirement)
                        register(dep_id, spec)
                else:
                    self._control.logger.warning(
                        f"[{plugin_id}] dependency entry '{item}' ignored (unsupported type)"
                    )
        else:
            self._control.logger.warning(
                f"[{plugin_id}] dependencies should be a dict or list"
            )

        return tuple(ordered_ids), specifiers

    def _parse_requirement_string(
        self, plugin_id: str, raw: str
    ) -> tuple[Optional[str], Optional[SpecifierSet]]:
        text = raw.strip()
        if not text:
            return None, None
        try:
            requirement = Requirement(text)
        except InvalidRequirement as exc:
            self._control.logger.warning(
                f"[{plugin_id}] dependency entry '{raw}' ignored: {exc}"
            )
            fallback = text.split()[0]
            return fallback, None
        if requirement.extras:
            self._control.logger.warning(
                f"[{plugin_id}] dependency '{requirement.name}' extras ignored"
            )
        spec = requirement.specifier if requirement.specifier else None
        return requirement.name, spec

    def _parse_specifier(
        self, plugin_id: str, dependency_id: str, raw: Any
    ) -> Optional[SpecifierSet]:
        if raw is None:
            return None
        if isinstance(raw, SpecifierSet):
            return raw
        if isinstance(raw, (list, tuple)):
            parts = [str(part).strip() for part in raw if str(part).strip()]
            text = ",".join(parts)
        else:
            text = str(raw).strip()
        text = text.replace(" ", "")
        if not text:
            return None
        try:
            return SpecifierSet(text)
        except InvalidSpecifier as exc:
            self._control.logger.warning(
                f"[{plugin_id}] dependency '{dependency_id}' has invalid version constraint '{raw}': {exc}"
            )
            return None

    def _snapshot_dependencies(
        self, dependencies: tuple[str, ...], specifiers: Dict[str, SpecifierSet]
    ) -> Dict[str, str]:
        snapshot: Dict[str, str] = {}
        for dependency in dependencies:
            spec = specifiers.get(dependency)
            snapshot[dependency] = str(spec) if spec is not None else ""
        return snapshot

    def _validate_dependency_versions(
        self, plugin_id: str, requirements: Dict[str, SpecifierSet]
    ) -> None:
        for dependency_id, specifier in requirements.items():
            if not str(specifier):
                continue
            record = self._plugins.get(dependency_id)
            if record is None:
                raise PluginLoadError(
                    self._safe_translate(
                        "plugin.dependency_missing", plugin_id, dependency_id
                    )
                )
            version_text = record.version
            try:
                Version(version_text)
            except InvalidVersion as exc:
                raise PluginLoadError(
                    f"[{plugin_id}] dependency '{dependency_id}' has invalid version '{version_text}': {exc}"
                ) from exc
            if not specifier.contains(version_text, prereleases=True):
                raise PluginLoadError(
                    f"[{plugin_id}] dependency '{dependency_id}' version '{version_text}' does not satisfy '{specifier}'"
                )

    def _resolve_load_sequence(self, targets: Any) -> list[str]:
        target_set = set(targets)
        order: list[str] = []
        state: Dict[str, int] = {}

        def visit(pid: str, chain: list[str]) -> bool:
            marker = state.get(pid)
            if marker == 2:
                return True
            if marker == 1:
                cycle = " -> ".join(chain + [pid])
                self._control.logger.error(
                    self._safe_translate("plugin.dependency_cycle", cycle)
                )
                return False
            state[pid] = 1
            success = True
            for dep in self._get_known_dependencies(pid):
                if dep not in self._plugins and dep not in self._available:
                    self._control.logger.error(
                        self._safe_translate("plugin.dependency_missing", pid, dep)
                    )
                    success = False
                    continue
                if dep not in self._plugins:
                    target_set.add(dep)
                if not visit(dep, chain + [pid]):
                    success = False
            state[pid] = 2
            if pid in target_set and success:
                order.append(pid)
            return success

        for pid in list(target_set):
            visit(pid, [])

        seen_order: set[str] = set()
        unique_order: list[str] = []
        for pid in order:
            if pid not in seen_order:
                seen_order.add(pid)
                unique_order.append(pid)

        return unique_order

    def _get_known_dependencies(self, plugin_id: str) -> tuple[str, ...]:
        if plugin_id in self._dependency_graph:
            return self._dependency_graph[plugin_id]
        if plugin_id in self._plugins:
            return self._plugins[plugin_id].dependencies
        return ()

    def _load_sequence(self, order: list[str]) -> None:
        for plugin_id in order:
            if plugin_id in self._plugins:
                continue
            candidate = self._available.get(plugin_id)
            if candidate is None:
                continue
            path, manifest = candidate
            try:
                self._perform_load(plugin_id, path, manifest)
            except PluginLoadError as exc:
                self._log_error("plugin.cant_load", plugin_id)
                self._control.logger.error(str(exc))

    def _perform_load(
        self, plugin_id: str, plugin_path: Path, manifest: Dict[str, Any]
    ) -> None:
        entrypoint = manifest.get("entrypoint")
        name = manifest.get("name", plugin_id)
        version = manifest.get("version", "0.0.0")
        dependencies = self._dependency_graph.get(plugin_id, ())
        specifiers = self._dependency_requirements.get(plugin_id, {})

        self._validate_dependency_versions(plugin_id, specifiers)

        sys_path_entry = self._ensure_sys_path(plugin_path)
        module: Optional[ModuleType] = None
        try:
            sandbox_enabled = getattr(self._control.config, "plugin_sandbox_enabled", True)
            prime_plugin_sandbox()
            with plugin_sandbox(plugin_id, enabled=sandbox_enabled):
                module = self._load_module(entrypoint)  # type: ignore[arg-type]
                config_class = self._resolve_config_class(plugin_id, manifest)
            plugin_control_interface = PluginControlInterface(
                plugin_id,
                str(plugin_path),
                config_class,  # type: ignore[arg-type]
                GlobalContext.get_mcdr_core(),
            )

            if hasattr(module, "on_load"):
                module.on_load(plugin_control_interface)

            record = PluginRecord(
                plugin_id=plugin_id,
                name=name,
                version=version,
                entrypoint=entrypoint,  # type: ignore[arg-type]
                path=plugin_path,
                module=module,
                info=manifest,
                config_class=config_class,
                dependencies=dependencies,
                dependency_specs=dict(specifiers),
                sys_path_entry=sys_path_entry,
            )
            self._plugins[plugin_id] = record
            for dep in dependencies:
                self._active_dependents[dep].add(plugin_id)
            self._active_dependents.setdefault(plugin_id, set())
            self._log_info("plugin.load_finish", name, version)
        except Exception as exc:
            self._release_sys_path(sys_path_entry)
            if module is not None:
                sys.modules.pop(entrypoint, None)  # type: ignore[arg-type]
            raise PluginLoadError(str(exc)) from exc

    def _load_with_dependencies(self, plugin_id: str) -> None:
        order = self._resolve_load_sequence([plugin_id])
        self._load_sequence(order)

    def _refresh_manifest(self, plugin_id: str) -> None:
        candidate = self._available.get(plugin_id)
        if candidate is None:
            return
        path, _ = candidate
        try:
            manifest = self._read_manifest(path)
        except PluginLoadError as exc:
            self._control.logger.error(str(exc))
            return
        self._register_candidate(plugin_id, path, manifest)

    def _collect_dependents(self, plugin_id: str) -> set[str]:
        result: set[str] = set()
        stack = [plugin_id]
        while stack:
            current = stack.pop()
            for dependent in self._active_dependents.get(current, set()):
                if dependent not in result:
                    result.add(dependent)
                    stack.append(dependent)
        return result

    def _topological_order_subset(self, subset: set[str]) -> list[str]:
        order: list[str] = []
        state: Dict[str, int] = {}

        def dfs(pid: str, chain: list[str]) -> bool:
            if pid not in subset:
                return True
            marker = state.get(pid)
            if marker == 2:
                return True
            if marker == 1:
                cycle = " -> ".join(chain + [pid])
                self._control.logger.error(
                    self._safe_translate("plugin.dependency_cycle", cycle)
                )
                return False
            state[pid] = 1
            success = True
            for dep in self._get_known_dependencies(pid):
                if dep not in subset:
                    continue
                if not dfs(dep, chain + [pid]):
                    success = False
            state[pid] = 2
            if success:
                order.append(pid)
            return success

        for pid in subset:
            dfs(pid, [])

        return order

    def load_plugin(self, plugin_source: str | Path) -> None:
        """Load a single plugin archive or reload an existing plugin with dependencies."""

        plugin_path = Path(plugin_source)
        if not plugin_path.is_absolute():
            plugin_path = self._plugin_dir / plugin_path
        plugin_path = plugin_path.resolve()

        try:
            manifest = self._read_manifest(plugin_path)
            plugin_id = manifest.get("id")
            if not plugin_id:
                raise PluginLoadError("Missing 'id' in connectcore.plugin.json")

            self._discover_plugins()
            self._register_candidate(plugin_id, plugin_path, manifest)

            if plugin_id in self._plugins:
                self.unload(plugin_id, cascade=False)

            order = self._resolve_load_sequence([plugin_id])
            self._load_sequence(order)
            if plugin_id not in self._plugins:
                self._control.logger.warning(
                    self._safe_translate("plugin.dependency_load_failed", plugin_id)
                )
        except PluginLoadError as exc:
            self._log_error("plugin.cant_load", plugin_path.stem)
            self._control.logger.error(str(exc))
        except Exception:
            self._log_error("plugin.cant_load", plugin_path.stem)
            self._control.logger.error(traceback.format_exc())

    def unload(self, plugin_id: str, cascade: bool = True) -> None:
        """Unload a plugin; optionally cascade to dependents."""

        if cascade:
            affected = self._collect_dependents(plugin_id)
            affected.add(plugin_id)
            loaded_subset = {pid for pid in affected if pid in self._plugins}
            if not loaded_subset:
                self._control.logger.warning(
                    self._safe_translate("plugin.cant_unload", plugin_id)
                )
                return
            order = self._topological_order_subset(loaded_subset)
            for pid in reversed(order):
                self._unload_single(pid)
        else:
            self._unload_single(plugin_id)

    def _unload_single(self, plugin_id: str) -> None:
        record = self._plugins.pop(plugin_id, None)
        if record is None:
            return

        try:
            if hasattr(record.module, "on_unload"):
                record.module.on_unload()
            self._log_info("plugin.unload_finish", record.name)
        except Exception:
            self._control.logger.error(f"[{plugin_id}] {traceback.format_exc()}")
        finally:
            self._release_sys_path(record.sys_path_entry)
            self._drop_module(record.entrypoint)
            for dep in record.dependencies:
                dependents = self._active_dependents.get(dep)
                if dependents is not None:
                    dependents.discard(plugin_id)
                    if not dependents:
                        self._active_dependents.pop(dep, None)
            self._active_dependents.pop(plugin_id, None)
            try:
                self._control.command_control.remove_sid(plugin_id)
            except RuntimeError as exc:
                self._control.logger.debug(
                    f"Skip removing commands for {plugin_id}: {exc}"
                )
            except AttributeError:
                self._control.logger.debug(
                    f"Command controller unavailable while removing commands for {plugin_id}"
                )
            except Exception:
                self._control.logger.exception(
                    f"Unexpected error while cleaning commands for plugin {plugin_id}"
                )

    def reload(self, plugin_id: str) -> None:
        """Reload a plugin and cascade reload to its dependents."""

        if plugin_id not in self._plugins and plugin_id not in self._available:
            self._control.logger.warning(
                self._safe_translate("plugin.unknown", plugin_id)
            )
            return

        affected = self._collect_dependents(plugin_id)
        affected.add(plugin_id)
        for pid in affected:
            self._refresh_manifest(pid)
        loaded_subset = {pid for pid in affected if pid in self._plugins}
        order = self._topological_order_subset(loaded_subset)

        for pid in reversed(order):
            self.unload(pid, cascade=False)

        for pid in order:
            self._load_with_dependencies(pid)

    def mcdr_add_entry_point(self, sid: str, entry_point: str) -> bool:
        """Expose an entry point from MCDR without an archive."""

        try:
            module = import_module(entry_point)
            record = PluginRecord(
                plugin_id=sid,
                name=sid,
                version="0.0.0",
                entrypoint=entry_point,
                path=(
                    Path(module.__file__).parent  # type: ignore[arg-type]
                    if getattr(module, "__file__", None)
                    else self._plugin_dir
                ),
                module=module,
                info={"id": sid, "entrypoint": entry_point},
                config_class=self._default_config_class(sid),
                dependencies=(),
            )
            self._plugins[sid] = record
            self._active_dependents.setdefault(sid, set())
            return True
        except ImportError as exc:
            self._control.logger.error(f"[{sid}] Import error: {exc}")
            return False
        except Exception as exc:
            self._control.logger.error(f"[{sid}] An error occurred: {exc}")
            return False

    # Event dispatcher -------------------------------------------------

    def handle_event(
        self, event: str, plugin_id: str | None = None, *args: Any
    ) -> None:
        """Dispatch an event to one or many plugins."""

        if plugin_id:
            record = self._plugins.get(plugin_id)
            if record is None:
                self._control.logger.error(f"Unknown plugin ID: {plugin_id}")
                return
            self._invoke_event(record, event, *args)
        else:
            for record in list(self._plugins.values()):
                self._invoke_event(record, event, *args)

    # Internal utilities -----------------------------------------------

    def _invoke_event(self, record: PluginRecord, event: str, *args: Any) -> None:
        handler = getattr(record.module, event, None)
        if handler is None:
            return
        try:
            handler(*args)
        except Exception:
            self._control.logger.error(
                f"Plugin {record.plugin_id} Error: \n{traceback.format_exc()}"
            )

    def _read_manifest(self, plugin_path: Path) -> Dict[str, Any]:
        if not plugin_path.exists():
            raise PluginLoadError(f"Plugin path not found: {plugin_path}")

        if plugin_path.is_dir():
            manifest_file = plugin_path / "connectcore.plugin.json"
            if not manifest_file.exists():
                raise PluginLoadError(
                    "connectcore.plugin.json not found in plugin directory"
                )
            try:
                with manifest_file.open("r", encoding="utf-8") as fh:
                    return json.load(fh)  # type: ignore[no-any-return]
            except json.JSONDecodeError as exc:
                raise PluginLoadError(
                    "Invalid JSON in connectcore.plugin.json"
                ) from exc

        suffix = plugin_path.suffix.lower()
        if suffix not in {".mcdr", ".pyz"}:
            raise PluginLoadError(f"Unsupported plugin format: {plugin_path.name}")

        try:
            with zipfile.ZipFile(plugin_path, "r") as archive:
                with archive.open("connectcore.plugin.json") as manifest_file:  # type: ignore[assignment]
                    return json.load(manifest_file)  # type: ignore[no-any-return, arg-type]
        except KeyError as exc:
            raise PluginLoadError(
                "connectcore.plugin.json not found in archive"
            ) from exc
        except json.JSONDecodeError as exc:
            raise PluginLoadError("Invalid JSON in connectcore.plugin.json") from exc

    def _resolve_config_class(
        self, plugin_id: str, manifest: Dict[str, Any]
    ) -> type[BaseConfig]:
        config_path = manifest.get("config_class")
        if config_path:
            try:
                module_name, class_name = config_path.rsplit(".", 1)
                module = import_module(module_name)
                config_cls = getattr(module, class_name)
                if not issubclass(config_cls, BaseConfig):
                    raise TypeError(f"{config_path} is not a subclass of BaseConfig")
                return config_cls  # type: ignore[no-any-return]
            except Exception as exc:
                self._control.logger.warning(
                    f"[{plugin_id}] Failed to load config class '{config_path}': {exc}"
                )

        config_file_path = manifest.get("config_path", f"config/{plugin_id}/config.yml")
        return self._default_config_class(plugin_id, config_file_path)

    def _default_config_class(
        self, plugin_id: str, config_path: str | None = None
    ) -> type[BaseConfig]:
        return type(
            f"{plugin_id.capitalize()}Config",
            (BaseConfig,),
            {"__config_path__": config_path or f"config/{plugin_id}/config.yml"},
        )

    def _load_module(self, entrypoint: str) -> ModuleType:
        if entrypoint in sys.modules:
            del sys.modules[entrypoint]

        spec = util.find_spec(entrypoint)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Module {entrypoint} not found")

        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _ensure_sys_path(self, plugin_path: Path) -> Optional[str]:
        path_entry = str(plugin_path)
        if path_entry not in self._sys_path_entries:
            sys.path.insert(0, path_entry)
            self._sys_path_entries[path_entry] = 1
        else:
            self._sys_path_entries[path_entry] += 1
        return path_entry

    def _release_sys_path(self, path_entry: Optional[str]) -> None:
        if not path_entry:
            return

        count = self._sys_path_entries.get(path_entry)
        if count is None:
            return

        if count <= 1:
            self._sys_path_entries.pop(path_entry, None)
            try:
                sys.path.remove(path_entry)
            except ValueError:
                pass
        else:
            self._sys_path_entries[path_entry] = count - 1

    def _drop_module(self, entrypoint: str) -> None:
        if entrypoint in sys.modules:
            del sys.modules[entrypoint]

    def _log_info(self, key: str, *args: Any) -> None:
        self._control.logger.info(self._safe_translate(key, *args))

    def _log_error(self, key: str, *args: Any) -> None:
        self._control.logger.error(self._safe_translate(key, *args))

    def _safe_translate(self, key: str, *args: Any) -> str:
        try:
            return self._control.translate(key, *args)
        except Exception:
            if args:
                return f"{key}: {' '.join(map(str, args))}"
            return key

    @property
    def plugins(self) -> Dict[str, PluginRecord]:
        return dict(self._plugins)


__all__ = [
    "PluginLoader",
    "PluginLoadError",
    "PluginRecord",
]
