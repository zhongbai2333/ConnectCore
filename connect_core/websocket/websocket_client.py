import websockets, json, asyncio, threading
from mcdreforged.api.all import new_thread

from connect_core.log_system import info_print, warn_print, error_print, debug_print
from connect_core.get_config_translate import config, translate, is_mcdr
from connect_core.rsa_encrypt import rsa_encrypt, rsa_decrypt


def websocket_client_init():
    if is_mcdr():
        mcdr_start()
    else:
        websocket_client_thread = threading.Thread(target=cli_start)
        websocket_client_thread.daemon = True
        websocket_client_thread.start()


def cli_start():
    global group_server
    group_server = WebsocketClient()
    group_server.start_server()


@new_thread("Websocket_Server")
def mcdr_start():
    global group_server
    group_server = WebsocketClient()
    group_server.start_server()


class WebsocketClient:
    def __init__(self) -> None:
        self.finish_start = False
        self.finish_close = False
        self.host = config("ip")
        self.port = config("port")

    def start_server(self) -> None:
        asyncio.run(self.init_main())

    def stop_server(self) -> None:
        if self.receive_task:
            self.receive_task.cancel()
        else:
            self.finish_quit = True
            pass

    async def init_main(self) -> None:
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task
        except asyncio.CancelledError:
            info_print(translate("net_core.service.start_websocket"))

    async def main(self):
        while True:
            try:
                async with websockets.connect(
                    f"ws://{self.host}:{self.port}"
                ) as self.websocket:
                    self.finish_start = True
                    info_print(translate("net_core.service.connect_websocket"))
                    await self.receive()
                break
            except ConnectionRefusedError:
                self.finish_start = False
                await asyncio.sleep(1)

    async def receive(self):
        await self.send_msg(
            {
                "s": 1,
                "status": "Connect",
                "data": {},
            }
        )
        while True:
            self.receive_task = asyncio.create_task(self.get_recv())
            try:
                recv_data = await self.receive_task
                if recv_data:
                    recv_data = rsa_decrypt(recv_data).decode()
                    recv_data = json.loads(recv_data)
                    debug_print(f"已收到 子服务器 数据包：{recv_data}")
                    # TODO: MSG_PRASE Server
                else:
                    break
            except asyncio.CancelledError:
                info_print(translate("net_core.service.stop_receive"))
                self.finish_quit = True
                return None

    async def get_recv(self):
        while True:
            try:
                return await asyncio.wait_for(self.websocket.recv(), timeout=4)
            except asyncio.TimeoutError:
                pass
            except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK):
                info_print(translate("net_core.service.disconnect_websocket"))
                websocket_client_init()
                return None

    async def send_msg(self, msg: dict) -> None:
        await self.websocket.send(rsa_encrypt(json.dumps(msg).encode()))
