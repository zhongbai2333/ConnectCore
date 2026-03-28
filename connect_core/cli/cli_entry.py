import sys
from time import sleep
from typing import Optional

from prompt_toolkit.patch_stdout import patch_stdout

from connect_core.context import GlobalContext
from connect_core.interface.control_interface import CoreControlInterface
from connect_core.init_config import CliInitConfig
from connect_core.tools.self_read import get_version
from connect_core.account.register_system import register_system_main
from connect_core.aes_encrypt import aes_main
from connect_core.plugin.init_plugin import init_plugin_main
from connect_core.websockets.server import (
    websocket_server_main,
    websocket_server_stop,
)
from connect_core.websockets.client import (
    websocket_client_main,
    websocket_client_stop,
)
from connect_core.cli.command_core import CommandLineInterface
from connect_core.cli.commands import ClientCommand, ServerCommand
from connect_core.cli.debug_tools import (
    MainThreadLogTester,
    register_debug_commands,
)
from typing import Callable, Any

cli = None  # type: Optional[CommandLineInterface]


def core_entry() -> None:
    global cli
    CliInitConfig()
    _control_interface = CoreControlInterface()
    aes_password = getattr(_control_interface.config, "password", None)
    if isinstance(aes_password, str) and aes_password:
        aes_main(_control_interface, aes_password)
    else:
        aes_main(_control_interface)
    cli = CommandLineInterface(_control_interface)
    _control_interface.command_control.bind_cli(cli)
    log_tester: Optional[MainThreadLogTester] = None
    stop_websocket: Callable[[], Any] | None = None

    if _control_interface.is_server:
        ServerCommand(_control_interface)
        register_system_main(_control_interface)
        stop_websocket = websocket_server_stop
    else:
        ClientCommand(_control_interface)
        stop_websocket = websocket_client_stop

    init_plugin_main(_control_interface)

    if _control_interface.is_server:
        websocket_server_main(_control_interface)  # pyright: ignore[reportCallIssue]
    else:
        websocket_client_main(_control_interface)  # pyright: ignore[reportCallIssue]

    if GlobalContext.is_debug_mode():
        log_tester = register_debug_commands(_control_interface)
    _control_interface.command_control.flush_cli()
    original_console_stream = _control_interface.log_system.get_console_stream()
    try:
        with patch_stdout(raw=True):
            _control_interface.log_system.set_console_stream(sys.stdout)
            cli_thread = cli.start()  # pyright: ignore[reportCallIssue]
            _control_interface.logger.info(
                _control_interface.translate("cli.starting.welcome", get_version())
            )
            if _control_interface.is_server:
                _control_interface.logger.info(
                    _control_interface.translate("cli.starting.get_password")
                )
            try:
                while cli_thread is not None and cli_thread.is_alive():
                    if log_tester is not None:
                        log_tester.maybe_log()
                    if not cli.running:
                        break
                    sleep(0.05)
            except KeyboardInterrupt:
                cli.running = False
            finally:
                if log_tester is not None:
                    log_tester.shutdown()
                if cli_thread is not None and cli_thread.is_alive():
                    cli.running = False
                    try:
                        cli.session.app.exit()
                    except Exception:
                        pass
                    cli_thread.join(timeout=1)
    finally:
        if stop_websocket is not None:
            try:
                stop_websocket()
            except Exception:
                pass
        if original_console_stream is not None:
            _control_interface.log_system.set_console_stream(original_console_stream)
        else:
            _control_interface.log_system.restore_console_stream()
