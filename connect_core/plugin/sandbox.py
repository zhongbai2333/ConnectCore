from __future__ import annotations

import threading
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec
from typing import Iterator

_ALLOWED_CONNECT_CORE_PREFIXES = (
    "connect_core.api",
    "connect_core.tools.base_config",
)

_BLOCKED_STDLIB_MODULES: frozenset[str] = frozenset({
    "os", "subprocess", "socket", "ctypes", "importlib",
    "builtins", "sys", "shutil", "pty", "signal",
    "resource", "code", "codeop", "pdb", "runpy",
})

_thread_state = threading.local()


@dataclass(frozen=True)
class PluginSandboxPolicy:
    plugin_id: str
    allowed_connect_core_prefixes: tuple[str, ...] = _ALLOWED_CONNECT_CORE_PREFIXES

    def allows_import(self, fullname: str) -> bool:
        if fullname == "connect_core":
            return True
        if not fullname.startswith("connect_core."):
            top = fullname.split(".")[0]
            if top in _BLOCKED_STDLIB_MODULES:
                return False
            return True
        return any(
            fullname == prefix or fullname.startswith(f"{prefix}.")
            for prefix in self.allowed_connect_core_prefixes
        )


class PluginSandboxFinder(MetaPathFinder):
    """Block plugin imports of non-public connect_core internals."""

    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: object | None = None,
    ) -> ModuleSpec | None:
        policy = getattr(_thread_state, "policy", None)
        if policy is None:
            return None
        if policy.allows_import(fullname):
            return None
        raise ImportError(
            f"Plugin '{policy.plugin_id}' is not allowed to import internal module '{fullname}'. "
            "Use 'connect_core.api' instead."
        )


_finder = PluginSandboxFinder()
if not any(isinstance(finder, PluginSandboxFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _finder)


def prime_plugin_sandbox() -> None:
    """Pre-import allowed facades so plugin code can access public APIs safely."""
    for module_name in _ALLOWED_CONNECT_CORE_PREFIXES:
        import_module(module_name)


@contextmanager
def plugin_sandbox(plugin_id: str, enabled: bool = True) -> Iterator[None]:
    if not enabled:
        yield
        return

    previous = getattr(_thread_state, "policy", None)
    _thread_state.policy = PluginSandboxPolicy(plugin_id)
    try:
        yield
    finally:
        _thread_state.policy = previous


__all__ = [
    "PluginSandboxPolicy",
    "PluginSandboxFinder",
    "plugin_sandbox",
    "prime_plugin_sandbox",
    "_BLOCKED_STDLIB_MODULES",
]
