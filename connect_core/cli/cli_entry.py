import sys
import time
import requests
from connect_core.storage import YmlLanguage, JsonDataEditor
from connect_core.account.login_system import analyze_password
from connect_core.cli.cli_core import Server, Client

_is_server = False

# Function
def _initialization_config() -> None:
    """
    第一次启动时的配置初始化过程。
    收集用户输入的信息并生成初始配置字典。
    """

    # 选择语言
    lang = input("Choose language | 请选择语言: [EN_US/zh_cn] ")
    lang = lang if lang else "en_us"
    lang.lower()

    translate_temp = YmlLanguage(sys.argv[0], lang).translate

    if _is_server:
        # 输入IP地址
        ip = input(
            translate_temp["connect_core"]["cli"]["initialization_config"]["enter_ip"]
        )
        ip = ip if ip else "127.0.0.1"

        # 输入端口
        port = input(
            translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
        )
        port = int(port) if port else 23233

        # 输入HTTP端口
        http_port = input(
            translate_temp["connect_core"]["cli"]["initialization_config"][
                "enter_http_port"
            ]
        )
        http_port = int(http_port) if http_port else 4443

        print(translate_temp["connect_core"]["cli"]["initialization_config"]["finish"])

        JsonDataEditor("config.json").write(
            {
                "language": lang,
                "ip": ip,
                "port": port,
                "http_port": http_port,
                "debug": False,
            }
        )
        time.sleep(3)
    else:
        key = input(
            translate_temp["connect_core"]["cli"]["initialization_config"]["enter_key"]
        )
        data = analyze_password(key)
        ip_list = [list(data["ip"].values())[0]]
        for i in list(data["ip"].values())[1]:
            ip_list.append(i)
        ip_list.append(list(data["ip"].values())[-1])
        for ip in ip_list:
            url = f"http://{ip}:{data['http_port']}"
            r = requests.get(url, timeout=5)
            code = r.status_code
            if code == 404:
                last_ip = ip
                break
            else:
                print(f"Error: Can't Visit Server!{ip_list}")
                return

        print(translate_temp["connect_core"]["cli"]["initialization_config"]["finish"])

        JsonDataEditor("config.json").write(
            {
                "language": lang,
                "ip": last_ip,
                "port": data["port"],
                "http_port": data["http_port"],
                "account": "",
                "password": data["password"],
                "debug": False,
            }
        )
        time.sleep(3)


# Public
def core_entry_init(is_server: bool) -> None:
    """
    核心程序主程序
    """
    global _is_server
    _is_server = is_server
    # 初始化
    _initialization_config()
    # 获取控制接口
    if is_server:
        server = Server()
        server.start_servers()
    else:
        client = Client()
        client.start_server()

def get_is_server() -> bool:
    """
    获取服务器还是客户端

    :return: 布尔值
    """
    return _is_server
