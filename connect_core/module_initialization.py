from mcdreforged.api.all import PluginServerInterface


def module_initialization_main(mcdr_core: PluginServerInterface = None):
    from connect_core.api.cli_command import cli_core_init
    from connect_core.api.c_t import c_t_main
    from connect_core.api.rsa import rsa_main

    cli_core_init(mcdr_core)
    c_t_main(mcdr_core)
    rsa_main()
