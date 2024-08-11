from mcdreforged.api.all import PluginServerInterface


def module_initialization_main(mcdr_core: PluginServerInterface = None):
    from connect_core.cli_core import cli_core_init
    from connect_core.get_config_translate import c_t_main
    from connect_core.rsa_encrypt import rsa_main

    cli_core_init(mcdr_core)
    c_t_main(mcdr_core)
    rsa_main()
