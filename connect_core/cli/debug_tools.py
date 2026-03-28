from __future__ import annotations

import time
from threading import Lock
from time import monotonic
from typing import Callable, Optional

from connect_core.interface.control_interface import CoreControlInterface


class MainThreadLogTester:
    def __init__(self, control_interface: CoreControlInterface) -> None:
        self._interface = control_interface
        self._lock = Lock()
        self._running = False
        self._interval = 0.5
        self._next_emit = monotonic()
        self._count = 0
        self._last_count = 0

    def start(self) -> None:
        with self._lock:
            if self._running:
                self._interface.logger.info(
                    self._interface.translate(
                        "cli.log_test.already_running", f"{self._interval:.2f}"
                    )
                )
                return
            self._running = True
            self._count = 0
            self._next_emit = monotonic()
        self._interface.logger.info(
            self._interface.translate("cli.log_test.started", f"{self._interval:.2f}")
        )

    def stop(self, silent: bool = False) -> None:
        with self._lock:
            if not self._running:
                running = False
                last = self._last_count
            else:
                running = True
                last = self._count
                self._last_count = self._count
                self._running = False
        if silent:
            return
        if running:
            self._interface.logger.info(
                self._interface.translate("cli.log_test.stopped", last)
            )
        else:
            self._interface.logger.info(
                self._interface.translate("cli.log_test.not_running")
            )

    def set_interval(self, value: str) -> None:
        try:
            seconds = float(value)
        except ValueError:
            self._interface.logger.warning(
                self._interface.translate("cli.log_test.interval_invalid", value)
            )
            return
        if seconds <= 0:
            self._interface.logger.warning(
                self._interface.translate("cli.log_test.interval_invalid", value)
            )
            return
        with self._lock:
            self._interval = seconds
            if self._running:
                self._next_emit = monotonic() + self._interval
        self._interface.logger.info(
            self._interface.translate("cli.log_test.interval_updated", f"{seconds:.2f}")
        )

    def status(self) -> None:
        with self._lock:
            running = self._running
            interval = self._interval
            count = self._count
            last = self._last_count
        if running:
            self._interface.logger.info(
                self._interface.translate(
                    "cli.log_test.status_running", f"{interval:.2f}", count
                )
            )
        else:
            self._interface.logger.info(
                self._interface.translate("cli.log_test.status_stopped", last)
            )

    def maybe_log(self) -> None:
        with self._lock:
            if not self._running:
                return
            now = monotonic()
            if now < self._next_emit:
                return
            self._next_emit = now + self._interval
            self._count += 1
            count = self._count
        self._interface.logger.info(
            self._interface.translate("cli.log_test.entry", count)
        )

    def shutdown(self) -> None:
        self.stop(silent=True)


def _wrap_action(action: Callable[[], None]) -> Callable[[], None]:
    def _wrapped() -> None:
        action()

    return _wrapped


def register_debug_commands(
    control_interface: CoreControlInterface,
) -> MainThreadLogTester:
    log_tester = MainThreadLogTester(control_interface)
    command_control = control_interface.command_control

    command_control.add_command("logtest start", _wrap_action(log_tester.start))
    command_control.add_command("logtest stop", _wrap_action(log_tester.stop))
    command_control.add_command("logtest status", _wrap_action(log_tester.status))

    def _set_interval(seconds: str) -> None:
        log_tester.set_interval(seconds)

    command_control.add_command("logtest set_interval <seconds>", _set_interval)

    def _get_server_id() -> Optional[str]:
        try:
            from connect_core.websockets.client import get_server_id

            return get_server_id()
        except Exception as exc:  # pragma: no cover - defensive log
            control_interface.logger.debug(f"Failed to fetch server id: {exc}")
            return None

    def _handle_debug_packet_send(*message_parts: str) -> None:
        payload_message = " ".join(message_parts).strip()
        if not payload_message:
            payload_message = f"debug-test-{int(time.time())}"

        payload = {
            "debug": True,
            "message": payload_message,
            "timestamp": time.time(),
        }

        if control_interface.is_server:
            try:
                from connect_core.websockets.server import send_data

                send_data("-----", "system", "all", "system", payload)
                control_interface.logger.info(
                    control_interface.tr(
                        "commands.debug_packet_sent_server",
                        payload_message,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive log
                control_interface.logger.warning(
                    control_interface.tr(
                        "commands.debug_packet_failed",
                        str(exc),
                    )
                )
        else:
            server_id = _get_server_id()
            if not server_id:
                control_interface.logger.warning(
                    control_interface.tr("commands.debug_packet_client_not_connected")
                )
                return

            try:
                from connect_core.websockets.client import send_data  # type: ignore[assignment]

                send_data("system", "-----", "system", payload)  # type: ignore[arg-type, call-arg]
                control_interface.logger.info(
                    control_interface.tr(
                        "commands.debug_packet_sent_client",
                        payload_message,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive log
                control_interface.logger.warning(
                    control_interface.tr(
                        "commands.debug_packet_failed",
                        str(exc),
                    )
                )

    def _handle_debug_sid_del(value: str) -> None:
        try:
            count = int(value)
        except ValueError:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_invalid", value)
            )
            return

        if control_interface.is_server:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_server_only")
            )
            return

        if count <= 0:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_invalid", value)
            )
            return

        try:
            from connect_core.websockets.client import delete_recent_sids

            state = delete_recent_sids(count)
        except RuntimeError as exc:
            control_interface.logger.warning(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive log
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_failed", str(exc))
            )
            return

        control_interface.logger.info(
            control_interface.tr(
                "commands.debug_sid_del_success",
                state.get("removed", 0),
                state.get("next_sid"),
                state.get("last_received"),
            )
        )

    def _handle_debug_sid_ack(value: str) -> None:
        try:
            ack_value = int(value)
        except ValueError:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_invalid", value)
            )
            return

        if control_interface.is_server:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_server_only")
            )
            return

        if ack_value < 0:
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_invalid", value)
            )
            return

        try:
            from connect_core.websockets.client import set_sid_state

            state = set_sid_state(last_received=ack_value)
        except RuntimeError as exc:
            control_interface.logger.warning(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive log
            control_interface.logger.warning(
                control_interface.tr("commands.debug_sid_failed", str(exc))
            )
            return

        control_interface.logger.info(
            control_interface.tr(
                "commands.debug_sid_ack_success",
                state.get("last_received"),
                state.get("next_sid"),
            )
        )

    command_control.add_command("debug packet send", _handle_debug_packet_send)
    command_control.add_command("debug sid del <count>", _handle_debug_sid_del)
    command_control.add_command("debug sid ack <value>", _handle_debug_sid_ack)
    return log_tester
