def start_cli():
    from connect_core.cli.cli_entry import main
    from connect_core.cli.log_system import log_main

    log_main()
    main()


if __name__ == "__main__":
    start_cli()
