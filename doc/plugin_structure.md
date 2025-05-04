# Plugin Structure

`MCDR模式`和`混合模式`(同时支持`MCDR模式`和`独立模式`)的插件可以上传至`MCDR`的`插件列表收集仓库`，这是符合规范的。

但是如果只支持`独立模式`就请勿上传，因为这不符合`插件列表收集仓库`的贡献标准，谢谢！

## 独立模式

独立模式下，**ConnectCore**读取`Plugins`内的`.mcdr`文件内的`connectcore.plugin.json`来获取入口点信息，并读取其ID，版本号等信息，为与MCDR统一，使用以下格式：

```json
{
    "id": "example_plugin",
    "version": "0.0.1",
    "name": "CliCore",
    "description": {
        "en_us": "An Example Plugin about ConnectCore",
        "zh_cn": "ConnectCore的实例插件"
    },
    "author": "zhongbai233",
    "link": "https://github.com/zhongbai2333/ExamplePlugin",
    "dependencies": {},
    "entrypoint": "example_plugin.connectcore.entry",
    "archive_name": "ExamplePlugin-v{version}.mcdr",
    "resources": [
        "lang",
        "LICENSE"
    ]
}
```

### `独立模式` 注意事项

- **ConnectCore**只接受以`.mcdr`为结尾的压缩包插件，否则无法正常加载。
- 如果你希望你的插件同时兼容**ConnectCore**的`独立模式`和`MCDR模式`，可以在根目录同时带有`mcdreforged.plugin.json`和`connectcore.plugin.json`文件
- **请注意**，如果使用`MCDR`模式，插件的加载和卸载是完全由`MCDR`来管理的，因此你需要确保你的插件在`MCDR`下正常工作。且`connectcore.plugin.json`完全不发挥作用，这就代表`MCDR模式`下可以无需`connectcore.plugin.json`文件
- 详细`MCDR模式`下插件如何工作请看下文的 [MCDR模式](#mcdr模式)
- 并且我也建议同时带有这两个文件，这样可以使用`python -m mcdreforged pack -o Path`命令来打包你的插件。
- **请注意**，如果你要使用`MCDReforged`的打包功能，你需要在`mcdreforged.plugin.json`文件中的`resources`配置项中添加以下配置项：

```json
"resources": [
    "lang",
    "connectcore.plugin.json",
    "LICENSE"
]
```

## 独立模式入口点

 1. **on_load**

    在插件启动时调用，传入控制接口对象。

    **Args:**
    > `control_interface`: 控制接口对象，包含插件的控制方法。

    ```python
    def on_load(control_interface):
        """加载"""
        global _control_interface
        _control_interface = control_interface
        _control_interface.info("Hello World! This is Plugin!!!!!!")
    ```

 2. **on_unload**

    在插件卸载时调用，无传参。

    ```python
    def on_unload():
        """卸载"""
        _control_interface.info("Bye!")
    ```

 3. **new_connect**

    在由新的子服务器连接时调用，传入子服务器ID。

    **Args:**
    > `server_list`: 子服务器ID。

    ```python
    def new_connect(server_id):
        """有新的连接"""
        _control_interface.info(server_id)
    ```

 4. **del_connect**

    在有子服务器断开连接时调用，传入子服务器ID。

    **Args:**
    > `server_list`: 子服务器ID。

    ```python
    def del_connect(server_id):
        """有断开连接"""
        _control_interface.info(server_id)
    ```

 5. **connected**

    子服务器与主服务器连接成功时调用，无传参

    ```python
    def connected():
        """连接成功"""
        _control_interface.info("Connected!")
    ```

 6. **disconnected**

    子服务器与主服务器断开连接时调用，无传参

    ```python
    def disconnected():
        """断开连接"""
        _control_interface.info("Disconnected!")
    ```

 7. **recv_data**

    接收子服务器发送的数据包时调用，传入子服务器ID和数据包。

    **Args:**
    > `server_id`: 子服务器的ID。
    > `data`: 数据包。

    ```python
    def recv_data(server_id: str, data: dict):
        """收到数据包"""
        _control_interface.info(data)
    ```

 8. **recv_file**

    接收子服务器发送的文件时调用，传入子服务器ID和文件保存路径。

    **Args:**
    > `server_id`: 子服务器的ID。
    > `file`: 文件保存路径。

    ```python
    def recv_file(server_id: str, file: str):
        """收到文件"""
        _control_interface.info(file)
    ```

## MCDR模式

`MCDR`模式下，**ConnectCore**插件是作为前置插件来工作的，所以无需`connectcore.plugin.json`，且`PluginControlInterface`是通过**ConnectCore**的API获取的，而不是通过`on_load`函数来传参

```json
{
    "id": "example_plugin",
    "version": "0.0.1",
    "name": "CliCore",
    "description": {
        "en_us": "An Example Plugin about ConnectCore",
        "zh_cn": "ConnectCore的实例插件"
    },
    "author": "zhongbai233",
    "link": "https://github.com/zhongbai2333/ExamplePlugin",
    "dependencies": {
        "connect_core": "*"
    },
    "entrypoint": "example_plugin.mcdr.entry",
    "archive_name": "ExamplePlugin-v{version}.mcdr",
    "resources": [
        "lang",
        "connectcore.plugin.json",
        "LICENSE"
    ]
}
```

### `MCDR模式` 注意事项

- 请注意要在`dependencies`内添加**ConnectCore**以确保不会出现加载错误
- `MCDR模式`下，**ConnectCore**和**你的插件**本质上是两个独立的插件，只是有依赖关系，所以你可以在开发完成后将其上传至`MCDR`的`插件列表收集仓库`

## MCDR模式入口点

 1. 获取插件控制接口

    `mcdr模式`下，你可以通过`get_plugin_control_interface`获取插件控制接口，然后通过这个接口来调用**ConnectCore**的方法

    **请注意**，在`mcdr模式`下，`PluginControlInterface`中的`info`、`warn`、`error`、`debug`实际调用的是你的插件下的`PluginServerInterface.logger.info`、`warn`、`error`、`debug`，所以你无需在`混合模式`下考虑是否需要同时支持`_control_interface.info`和`PluginServerInterface.logger.info`，他们是通用的

    `get_plugin_control_interface`需要传入参数：

    **Args:**
    >sid (str): 服务器ID
    >enter_point (str): 入口点
    >mcdr (PluginServerInterface): MCDR接口

    **Returns:**
    >PluginControlInterface: 插件控制接口

    ```python
    def get_plugin_control_interface(
        sid: str, enter_point: str, mcdr: PluginServerInterface
    ) -> PluginControlInterface:
        """
        获取插件控制接口

        Args:
            sid (str): 插件ID
            enter_point (str): 入口点
            mcdr (PluginServerInterface): MCDR接口
        Returns:
            PluginControlInterface: 插件控制接口
        """
    ```

    **请注意**，传入的入口点是你写的插件的入口点，而不是MCDR的入口点，只是在`MCDR模式`下**ConnectCore**不会去读取`on_load`和`on_unload`，所以入口点函数和`MCDR`的入口点函数是不同的，写一摸一样的一个不会发生冲突。

    ```python
    from mcdreforged.api.all import *
    from connect_core.api.mcdr import get_plugin_control_interface

    # MCDR Start point
    def on_load(server: PluginServerInterface,_):
        global __mcdr_server,_control_interface
        __mcdr_server = server
        _control_interface = get_plugin_control_interface(
            "example_plugin", 
            "example_plugin.mcdr.entry", 
            server)

        _control_interface.info("Hello")
    ```

### 接下来的入口点与`独立模式`相同

 1. **new_connect**

    在由新的子服务器连接时调用，传入子服务器列表。

    **Args:**
    > `server_list`: 子服务器列表，包含子服务器的ID。

    ```python
    def new_connect(server_list):
        """有新的连接"""
        _control_interface.info(server_list)
    ```

 2. **del_connect**

    在有子服务器断开连接时调用，传入子服务器列表。

    **Args:**
    > `server_list`: 子服务器列表，包含子服务器的ID。

    ```python
    def del_connect(server_list):
        """有断开连接"""
        _control_interface.info(server_list)
    ```

 3. **connected**

    子服务器与主服务器连接成功时调用，无传参

    ```python
    def connected():
        """连接成功"""
        _control_interface.info("Connected!")
    ```

 4. **disconnected**

    子服务器与主服务器断开连接时调用，无传参

    ```python
    def disconnected():
        """断开连接"""
        _control_interface.info("Disconnected!")
    ```

 5. **websockets_started**

    websocket启动/连接成功
    服务端为启动成功
    客户端为连接成功

    ```python
    def websockets_started():
        """
        websocket启动/连接成功
        服务端为启动成功
        客户端为连接成功
        """
        _control_interface.info("Websockets Started!")
    ```

 6. **recv_data**

    接收子服务器发送的数据包时调用，传入子服务器ID和数据包。

    **Args:**
    > `server_id`: 子服务器的ID。
    > `data`: 数据包。

    ```python
    def recv_data(server_id: str, data: dict):
        """收到数据包"""
        _control_interface.info(data)
    ```

 7. **recv_file**

    接收子服务器发送的文件时调用，传入子服务器ID和文件保存路径。

    **Args:**
    > `server_id`: 子服务器的ID。
    > `file`: 文件保存路径。

    ```python
    def recv_file(server_id: str, file: str):
        """收到文件"""
        _control_interface.info(file)
    ```
