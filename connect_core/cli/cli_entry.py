import os
import re
import sys
import time
import json
import websockets
import asyncio
from connect_core.storage import YmlLanguage, JsonDataEditor
from connect_core.account.login_system import analyze_password
from connect_core.cli.cli_core import Server, Client
from connect_core.tools import restart_program
from connect_core.websocket.data_packet import DataPacket

_is_server = False


# Function
async def check_websocket(server_uri) -> bool:
    """
    检查websocket服务器是否在线
    """
    try:
        async with websockets.connect(server_uri) as websocket:
            print(f"Connected to {server_uri} successfully!")
            data_packet = DataPacket()
            # 可以发送和接收消息以进一步测试
            await websocket.send(
                json.dumps(
                    data_packet.get_data_packet(
                        data_packet.TYPE_TEST_CONNECT,
                        data_packet.DEFAULT_TO_FROM,
                        data_packet.DEFAULT_TO_FROM,
                        None,
                    )["-----"]
                )
            )
            response = await websocket.recv()
            if json.loads(response)["type"] == list(data_packet.TYPE_TEST_CONNECT):
                return True
            return False
    except Exception as e:
        print(f"Failed to connect to {server_uri}: {e}")
        return False


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
        while not re.match(r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", ip):
            if not ip:
                break
            print(translate_temp["connect_core"]["cli"]["initialization_config"]["invalid_ip"])
            ip = input(
                translate_temp["connect_core"]["cli"]["initialization_config"][
                    "enter_ip"
                ]
            )
        ip = ip if ip else "127.0.0.1"

        # 输入端口
        port = input(
            translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
        )
        while not (0 <= port <= 65535):
            if not port:
                break
            print(translate_temp["connect_core"]["cli"]["initialization_config"]["invalid_port"])
            port = input(
                translate_temp["connect_core"]["cli"]["initialization_config"]["enter_port"]
            )
        port = int(port) if port else 23233

        print(translate_temp["connect_core"]["cli"]["initialization_config"]["finish"])

        JsonDataEditor("config.json").write(
            {
                "language": lang,
                "ip": ip,
                "port": port,
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
            url = f"ws://{ip}:{data['port']}"
            if asyncio.run(check_websocket(url)):
                last_ip = ip
                break
        else:
            print(f"Error: Can't Visit Server! {ip_list}")
            ip = input("Please enter the correct IP address: ")
            url = f"ws://{ip}:{data['port']}"
            if not asyncio.run(check_websocket(url)):
                print(f"Error: Can't Visit Server! {ip}, please check the IP address.")
                return

        print(translate_temp["connect_core"]["cli"]["initialization_config"]["finish"])

        JsonDataEditor("config.json").write(
            {
                "language": lang,
                "ip": last_ip,
                "port": data["port"],
                "account": "-----",
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
    if not os.path.exists("config.json"):
        _initialization_config()
        restart_program()
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
