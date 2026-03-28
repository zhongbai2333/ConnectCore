from __future__ import annotations

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from connect_core.interface.control_interface import CoreControlInterface


def fetch_server_ids(control_interface: "CoreControlInterface") -> List[str]:
    """Return a list of known server identifiers for CLI tooling."""

    try:
        if control_interface.is_server:
            from connect_core.websockets.server import get_server_list
        else:
            from connect_core.websockets.client import get_server_list

        servers = get_server_list()
    except Exception as exc:  # pragma: no cover - defensive log
        control_interface.logger.debug(f"Failed to refresh server list for CLI: {exc}")
        return []

    result: List[str] = []
    seen: set[str] = set()
    for server in servers or []:
        server_id = str(server)
        if not server_id or server_id in seen:
            continue
        seen.add(server_id)
        result.append(server_id)
    return result
