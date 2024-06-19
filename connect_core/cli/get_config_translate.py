from connect_core.cli.storage import JsonDataEditor, YmlLanguage


def config():
    return JsonDataEditor().read()


def translate():
    return YmlLanguage(config()["language"]).translate
