import websockets, json, asyncio, random, string
from mcdreforged.api.all import new_thread

from connect_core.log_system import info_print, warn_print, error_print, debug_print
from connect_core.get_config_translate import config, translate, is_mcdr
from connect_core.rsa_encrypt import rsa_encrypt, rsa_decrypt

global websocket_server


def websocket_server_init():
    if is_mcdr():
        mcdr_start()
    else:
        global websocket_server
        websocket_server = WebsocketServer()
        websocket_server.start_server()


def get_server_list() -> dict:
    if websocket_server:
        return websocket_server.servers_info


@new_thread("Websocket_Server")
def mcdr_start():
    global websocket_server
    websocket_server = WebsocketServer()
    websocket_server.start_server()


class WebsocketServer:
    def __init__(self) -> None:
        self.finish_close = False
        self.host = config("ip")
        self.port = config("port")
        self.websockets = {}
        self.broadcast_websockets = set()
        self.servers_info = {}

    def start_server(self) -> None:
        asyncio.run(self.init_main())

    def close_server(self) -> None:
        self.main_task.cancel()

    def create_string_number(self, n):
        m = random.randint(1, n)
        a = "".join([str(random.randint(0, 9)) for _ in range(m)])
        b = "".join([random.choice(string.ascii_letters) for _ in range(n - m)])
        return ''.join(random.sample(list(a + b), n))

    # 导入主服务器 task
    async def init_main(self) -> None:
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task  # 运行主服务器
        except asyncio.CancelledError:
            info_print(translate("net_core.service.stop_websocket"))
            self.finish_close = True

    # 主服务监听
    async def main(self):
        async with websockets.serve(self.handler, self.host, self.port):
            info_print(translate("net_core.service.start_websocket"))
            await asyncio.Future()  # run forever

    # 主服务器管理
    async def handler(self, websocket):
        server_id = None
        while True:
            try:
                msg = await websocket.recv()
                try:
                    msg = rsa_decrypt(msg).decode()
                    msg = json.loads(msg)
                    debug_print("已收到子服务器数据包：" + str(msg))
                    if msg['s'] == 1:
                        server_id = self.create_string_number(5)
                        while server_id in self.websockets.keys():
                            server_id = self.create_string_number(5)
                        self.websockets[server_id] = websocket
                        self.broadcast_websockets.add(websocket)
                        self.servers_info[server_id] = msg['data']
                        info_print(translate("net_core.service.connect_websocket").format(f"Server {server_id}"))
                        await self.send_msg(websocket,
                            {
                                "s": 1,
                                "id": server_id,
                                "status": "Succeed",
                                "data": {},
                            }
                        )
                except Exception as e:
                    debug_print(f"子服务器连接错误：{e}")
                    await websocket.close(reason="400")  # 密码错误关闭连接
                    self.close_connect()
                    break
            except (
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ):
                self.close_connect(server_id, websocket)
                break

    # 断开连接并删除记录
    def close_connect(self, server_id=None, websocket=None):
        if server_id is not None and websocket is not None:
            del self.websockets[server_id]
            del self.servers_info[server_id]
            self.broadcast_websockets.remove(websocket)
            info_print(translate("net_core.service.disconnect_from_sub_websocket").format(server_id))
        else:
            warn_print(translate("net_core.service.disconnect_from_unknown_websocket"))

    async def send_msg(self, websocket, msg: dict) -> None:
        await websocket.send(rsa_encrypt(json.dumps(msg).encode()))

    def get_msg_dict(self, s: int, s_to_id: str, s_from_id: str, data: dict) -> dict:
        return {"s": s, "id": s_to_id, "from": s_from_id, "data": data}

    # 广播
    def broadcast(self, msg: dict):
        websockets.broadcast(
            self.broadcast_websockets, rsa_encrypt(json.dumps(msg).encode())
        )
