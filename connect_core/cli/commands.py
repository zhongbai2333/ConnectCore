from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connect_core.interface.control_interface import CoreControlInterface

class Command(object):
    def __init__(self, control_interface: "CoreControlInterface"):
        self._control_interface = control_interface
        self._completer_words = {}

    def _reg_commands(self):
        # Register commands here
        self._control_interface.add_command("help", self._handle_help)
        self._control_interface.add_command("list", self._handle_list)
        self._completer_words["help"] = None
        self._completer_words["list"] = None
        self._control_interface.set_completer_words(self._completer_words)
        self._control_interface.flush_cli()

    def _handle_help(self, args: list):
        if self._control_interface.is_server():
            self._control_interface.info(
                self._control_interface.tr("commands.server_help")
            )
        else:
            self._control_interface.info(
                self._control_interface.tr("commands.client_help")
            )

    def _handle_list(self, args: list):
        self._control_interface.info("==list==")
        for num, key in enumerate(self._control_interface.get_server_list()):
            self._control_interface.info(f"{num + 1}. {key}")


class ServerCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface"):
        super().__init__(control_interface)

        self._reg_commands()

    def _reg_server_commands(self):
        # Register commands here
        self._control_interface.add_command("getkey", self._handle_getkey)
        self._completer_words["getkey"] = None
        self._control_interface.set_completer_words(self._completer_words)
        self._control_interface.flush_cli()

    def _handle_getkey(self, args: list):
        from connect_core.account.register_system import get_password
        self._control_interface.info(
            self._control_interface.tr("cli.starting.welcome_password", get_password())
        )


class ClientCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface"):
        super().__init__(control_interface)

        self._reg_client_commands()
