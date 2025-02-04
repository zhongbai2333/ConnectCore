import os
from typing import TYPE_CHECKING
from connect_core.tools import auto_trigger
from connect_core.plugin.init_plugin import load_plugin, reload_plugin, unload_plugin, get_plugins

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
        self._control_interface.add_command(
            "plugin load <Path>", self._handle_plugin_load
        )
        self._control_interface.add_command(
            "plugin reload <ID>", self._handle_plugin_reload
        )
        self._control_interface.add_command(
            "plugin unload <ID>", self._handle_plugin_unload
        )
        self._completer_words["help"] = None
        self._completer_words["list"] = None
        self._completer_words["plugin"] = {
            "load": None,
            "reload": None,
            "unload": None,
        }
        self._get_file_list()
        self._reload_completer()

    def _handle_help(self, *_):
        if self._control_interface.is_server():
            self._control_interface.info(
                self._control_interface.tr("commands.server_help")
            )
        else:
            self._control_interface.info(
                self._control_interface.tr("commands.client_help")
            )

    def _handle_list(self, *_):
        self._control_interface.info("==list==")
        for num, key in enumerate(self._control_interface.get_server_list()):
            self._control_interface.info(f"{num + 1}. {key}")

    def _handle_plugin_load(self, path: str):
        # Implement plugin loading logic here
        load_plugin(path)

    def _handle_plugin_reload(self, id: str):
        # Implement plugin reloading logic here
        reload_plugin(id)

    def _handle_plugin_unload(self, id: str):
        # Implement plugin unload logic here
        unload_plugin(id)

    @auto_trigger(5, "plugin_file_list")
    def _get_file_list(self):
        file_list = {}
        id_list = {}
        for i in os.listdir("./plugins/"):
            file_list[i] = None
        for i in get_plugins():
            id_list[i] = None
        if self._completer_words["plugin"]["load"] != file_list:
            self._completer_words["plugin"]["load"] = file_list
            self._reload_completer()
        if self._completer_words["plugin"]["reload"] != id_list:
            self._completer_words["plugin"]["reload"] = id_list
            self._completer_words["plugin"]["unload"] = id_list
            self._reload_completer()

    def _reload_completer(self):
        self._control_interface.set_completer_words(self._completer_words)
        self._control_interface.flush_cli()


class ServerCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface"):
        super().__init__(control_interface)

        self._reg_commands()
        self._reg_server_commands()

    def _reg_server_commands(self):
        # Register commands here
        self._control_interface.add_command("getkey", self._handle_getkey)
        self._completer_words["getkey"] = None
        self._reload_completer()

    def _handle_getkey(self, *_):
        from connect_core.account.register_system import get_password

        self._control_interface.info(
            self._control_interface.tr("cli.starting.welcome_password", get_password())
        )


class ClientCommand(Command):
    def __init__(self, control_interface: "CoreControlInterface"):
        super().__init__(control_interface)

        self._reg_commands()
        self._reg_client_commands()

    def _reg_client_commands(self):
        self._control_interface.add_command("info", self._handle_info)
        self._completer_words["info"] = None
        self._reload_completer()

    def _handle_info(self, *_):
        """
        显示主服务器信息。
        """
        self._control_interface.info("==info==")
        server_id = self._control_interface.get_server_id()
        if server_id:
            self._control_interface.info(
                f"Main Server Connected! Server ID: {server_id}"
            )
        else:
            self._control_interface.info("Main Server Disconnected!")
