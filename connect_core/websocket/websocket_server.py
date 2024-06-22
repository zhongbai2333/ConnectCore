import websockets, json, asyncio
from cryptography.fernet import Fernet

from connect_core.log_system import info_print, warn_print, error_print
from connect_core.cli.get_config_translate import config, translate

class WebsocketServer:
    def __init__(self) -> None:
        self.finish_close = False
        self.host = config()["ip"]
        self.port = config()["port"]
        self.fernet = Fernet(config()["password"].encode())

    def start_server(self) -> None:
        asyncio.run(self.init_main())

    def close_server(self) -> None:
        self.main_task.cancel()

    # 导入主服务器 task
    async def init_main(self) -> None:
        self.main_task = asyncio.create_task(self.main())
        try:
            await self.main_task  # 运行主服务器
        except asyncio.CancelledError:
            info_print("Group Websocket 已关闭！")
            self.finish_close = True

    # 主服务监听
    async def main(self):
        async with websockets.serve(self.handler, self.host, self.port):
            info_print("Group websocket 启动成功！")
            await asyncio.Future()  # run forever

    # 主服务器管理
    async def handler(self, websocket):
        server_id = None
        while True:
            try:
                msg = await websocket.recv()
                msg = self.fernet.decrypt(msg)
                msg = json.load(msg)
                info_print(msg)
            except (
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ):
                self.close_connect(server_id, websocket)
                break
