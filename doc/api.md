# API

本文档对应 `Project-Refactoring-Codespace` 当前实现，建议插件开发者统一从 `connect_core.api` 导入公开符号，而不是直接依赖内部模块路径。

```python
from connect_core.api import (
    PluginControlInterface,
    DataModel,
    PacketType,
    BaseConfig,
)
```

## 公开导出总览

`connect_core.api` 当前导出了以下能力：

- 控制接口：`CoreControlInterface`、`PluginControlInterface`
- 插件管理：`unload_plugin`、`reload_plugin`、`get_plugins`
- 加密：`aes_encrypt`、`aes_decrypt`
- 工具函数：`restart_program`、`check_file_exists`、`append_to_path`、`encode_base64`、`decode_base64`、`get_all_internal_ips`、`get_external_ip`、`new_thread`、`auto_trigger`
- 数据包协议：`DataModel`、`DataPacket`（兼容别名）、`PacketType`、`PacketStatus`、`StatusRegistry`、`status_registry`、`PROTOCOL_VERSION`
- 账号流程：`analyze_password`、`get_password`、`get_register_password`
- MCDR：`get_plugin_control_interface`
- 配置系统：`BaseConfig`、`ConfigError`、`ConfigTypeError`、`ConfigValidationError`、`Field`

---

## Account

### `analyze_password(key: str) -> dict`

解析初始化密钥，返回连接所需的信息字典。

**Args:**
- `key` *(str)*: 服务端生成的初始化密钥

**Returns:**
- `dict`: 包含连接所需信息的字典（如服务器地址、端口、加密参数等）

### `get_password() -> str`

获取当前服务端初始化密钥字符串。

**Returns:**
- `str`: 密钥字符串

### `get_register_password() -> str`

获取注册流程使用的临时密钥字符串。

**Returns:**
- `str`: 密钥字符串

---

## Config

当前 PRC 版本的配置系统已迁移到 **pydantic v2**，但保留了旧接口的大部分使用方式。

### `ConfigError`

配置相关异常基类。

### `ConfigTypeError`

配置字段类型错误时抛出。

### `ConfigValidationError`

配置验证失败异常类型，保留用于兼容旧 API。

### `Field(default=..., description="")`

向后兼容的字段工厂，内部委托给 `pydantic.Field`。

```python
from connect_core.api import BaseConfig, Field

class ExampleConfig(BaseConfig):
    enabled: bool = Field(True, "是否启用")
    endpoint: str = Field("127.0.0.1", "目标地址")
```

### `class BaseConfig`

基于 `pydantic.BaseModel` 的 YAML 配置基类。

#### 主要特性

- 使用 `__config_path__` 指定默认配置路径
- `load()` 在文件不存在时会自动创建默认配置
- `save()` 会输出带注释的 YAML
- 保留 `__fields__` 兼容视图，方便旧代码读取字段定义
- `update(**kwargs)` 支持批量更新并触发类型校验

#### 常用方法

##### `BaseConfig.load(config_path: str | PathLike | None = None) -> T`

从 YAML 加载配置；缺失字段会自动补全并写回文件。

##### `save(config_path: str | PathLike | None = None) -> None`

保存当前配置对象到 YAML。

##### `update(**kwargs) -> None`

批量更新配置值；如果字段不存在或类型不匹配，会抛出 `ConfigError` / `ConfigTypeError`。

---

## Data Packet / Protocol

> 当前重构版不再使用旧版的 `(数字 type, 数字 status)` 表示方式，而是统一使用字符串枚举 + `pydantic` 数据模型。

### `PacketType`

内置数据包类型枚举：

- `TEST_CONNECT`
- `PING`
- `PONG`
- `CONTROL_STOP`
- `CONTROL_RELOAD`
- `CONTROL_MAINTENANCE`
- `CONTROL_RESUME`
- `REGISTER`
- `REGISTERED`
- `REGISTER_ERROR`
- `LOGIN`
- `LOGINED`
- `NEW_LOGIN`
- `DEL_LOGIN`
- `LOGIN_ERROR`
- `DATA_SEND`
- `DATA_SENDOK`
- `DATA_ERROR`
- `FILE_SEND`
- `FILE_SENDING`
- `FILE_SENDOK`
- `FILE_ERROR`

### `PacketStatus`

内置状态枚举：

- `REQUEST`
- `OK`
- `ERROR`
- `SENDING`
- `NEW`
- `DEL`
- `STOP`
- `RELOAD`
- `MAINTENANCE`
- `RESUME`

> `DataModel.status` 实际允许任意字符串，因此第三方插件可以注册自定义状态。

### `PROTOCOL_VERSION: int = 1`

当前协议版本号。客户端在 `REGISTER` / `LOGIN` 握手时会携带该版本，服务端会校验版本一致性。

### `class DataModel`

统一的数据包模型；`DataPacket` 是它的兼容别名。

#### 模型结构

```python
{
    "type": "data_send",
    "status": "ok",
    "sid": 12,
    "to": ["target_server", "target_plugin"],
    "from": ["source_server", "source_plugin"],
    "payload": {"message": "hello"},
    "timestamp": 1710000000.0,
    "checksum": "..."
}
```

#### 字段说明

- `type`: `PacketType`
- `status`: `str | None`，可为空，也可自定义
- `sid`: 数据包序号
- `to`: `(server_id, plugin_id)`
- `from`: 序列化别名；在 Python 属性中为 `from_`
- `payload`: 业务数据
- `timestamp`: 时间戳
- `checksum`: 校验和；若 `payload` 存在且未提供，将自动生成 MD5

### `class StatusRegistry`

用于给指定 `PacketType` 注册自定义状态和处理器。

#### 常用方法

##### `register_status(packet_type: PacketType, status: str) -> None`

注册某个数据包类型下的自定义状态。

##### `register_handler(packet_type: PacketType, status: str, callback: Callable) -> None`

为 `(packet_type, status)` 注册回调。

- 回调参数：`callback(packet: DataModel)`
- 支持同步函数与异步协程函数

##### `unregister_handler(packet_type: PacketType, status: str, callback: Callable) -> None`

取消注册处理器。

##### `get_registered_statuses(packet_type: PacketType) -> set[str]`

获取指定类型已注册的自定义状态集合。

### `status_registry`

全局状态注册器实例。

```python
from connect_core.api import PacketType, status_registry

status_registry.register_status(PacketType.DATA_SEND, "my_status")
```

更实际的写法如下：

```python
from connect_core.api import PacketType, status_registry


def handle_custom(packet):
    print(packet.payload)

status_registry.register_status(PacketType.DATA_SEND, "plugin.custom")
status_registry.register_handler(PacketType.DATA_SEND, "plugin.custom", handle_custom)
```

---

## Interface

### `CoreControlInterface`

ConnectCore 核心控制接口，提供日志、配置、翻译、命令行与 WebSocket 查询能力。

### 常用属性

#### `logger -> logging.Logger`

标准日志接口。

#### `struct_logger -> structlog.stdlib.BoundLogger`

结构化日志接口。

#### `config -> ServerConfig | ClientConfig`

当前主配置对象。

### 常用方法

#### `get_config(key="all", default=None, config_path=None) -> Any`

读取配置。

> ⚠️ 如果配置文件不存在或为空，调用此方法**不会**自动写入到配置文件中。请先使用 `save_config` 进行初始化。

**Args:**
- `key` *(str)*: 配置键名，默认 `"all"` 返回完整配置
- `default` *(Any)*: 键不存在时的默认值
- `config_path` *(str, optional)*: 辅助配置文件路径

**Returns:**
- `Any`: 配置值或完整配置对象

- 不传 `config_path`：读取主配置模型
- 传入 `config_path`：读取 `config/connect_core/<filename>` 下的辅助 JSON 配置

#### `save_config(config_data, config_path=None) -> None`

保存配置。

- `config_data` 为 `BaseConfig` 实例时：直接保存 YAML
- `config_data` 为 `dict` 且提供 `config_path` 时：写入辅助 JSON 配置
- `config_data` 为 `dict` 且不提供 `config_path` 时：更新主配置字段并保存

#### `translate(key: str, *args) -> str`

读取翻译文本。

#### `tr(key: str, *args) -> str`

`translate` 的别名。

#### `info(msg) / warn(msg) / warning(msg) / error(msg)`

输出不同级别日志。

#### `debug(msg, level=1)`

输出调试日志，只有当 `GlobalContext` 的调试等级不低于 `level` 时才会真正打印。

#### `get_server_list() -> list`

获取当前已知服务器列表：

- 服务端模式：返回所有已连接子服 ID
- 客户端模式：返回服务端广播给当前客户端的服务器列表

#### `get_server_id() -> str`

客户端模式下返回当前客户端账号 / server_id；服务端模式固定返回 `"-----"`。

#### `get_history_data_packet(server_id: str | None = None) -> list`

读取历史数据包。

- 服务端模式：需要传入 `server_id`
- 客户端模式：忽略参数，返回本地历史记录

#### `get_recent_packets(limit: int = 20, server_id: str | None = None) -> list`

读取最近数据包，返回值中额外包含：

- `direction`: `sent` / `received`
- `server_id`: 数据包所属服务器

### `command_control`

命令控制器对象，提供以下方法：

- `bind_cli(cli)`
- `add_command(command, func, *, argument_specs=None, pass_context=False)`
- `remove_command(command)`
- `set_prompt(prompt)`
- `set_completer_words(words)`
- `remove_sid(target_sid)`
- `flush_cli()`

---

### `PluginControlInterface`

插件控制接口，继承自 `CoreControlInterface`，额外提供插件向网络发送数据/文件的能力。

### 构造参数

```python
PluginControlInterface(
    sid: str,
    self_path: str | None,
    config_file: BaseConfig | None,
    mcdr_core: PluginServerInterface | None = None,
)
```

### `send_data(server_id: str, plugin_id: str, data: dict) -> None`

向目标服务器上的目标插件发送 JSON 数据。

### `send_file(server_id: str, plugin_id: str, file_path: str, save_path: str) -> None`

向目标服务器上的目标插件发送文件。

---

## Plugin Management

### `unload_plugin(sid: str) -> None`

卸载插件。独立模式下会级联卸载依赖它的插件。

### `reload_plugin(sid: str) -> None`

重载插件。独立模式下会先按依赖顺序卸载，再按拓扑顺序重新加载。

### `get_plugins() -> dict[str, dict]`

获取当前已加载插件的 manifest 信息。

---

## Encryption

### `aes_encrypt(data: bytes | str, password: str | None = None) -> bytes`

对数据进行 AES 加密。若不显式传入密码，则使用当前全局密钥上下文。

### `aes_decrypt(data: bytes | str, password: str | None = None) -> bytes`

对数据进行 AES 解密。

---

## MCDR

### `get_plugin_control_interface(sid, enter_point, mcdr) -> PluginControlInterface | None`

为 MCDR 插件创建一个 `PluginControlInterface`。

```python
from mcdreforged.api.all import *
from connect_core.api import get_plugin_control_interface

_control = None


def on_load(server: PluginServerInterface, _):
    global _control
    _control = get_plugin_control_interface(
        "example_plugin",
        "example_plugin.mcdr.entry",
        server,
    )
```

> 当前 PRC 实现中，`enter_point` 主要用于兼容旧 API；MCDR 模式下 ConnectCore 不负责加载第三方 MCDR 插件归档，也不会像独立模式那样自动分发插件事件。

---

## Tools

### `new_thread(arg=None)`

线程装饰器。被装饰函数调用后会立即在线程中执行，并返回线程对象。

### `auto_trigger(interval: float, thread_name: str | None = None)`

定时触发装饰器，常用于自动心跳、自动重发等后台任务。

### `restart_program() -> None`

重启当前程序；在 MCDR 模式下会改为请求重载 `connect_core` 插件。

### `check_file_exists(file_path: str) -> bool`

检查文件是否存在。

### `append_to_path(path: str, filename: str) -> str`

若 `path` 是目录，则自动拼接文件名；否则原样返回。

### `encode_base64(data: str) -> str`

Base64 编码。

### `decode_base64(encoded_data: str) -> str`

Base64 解码。

### `get_all_internal_ips() -> list[str]`

获取所有网卡的 IPv4 内网地址。

### `get_external_ip() -> str`

通过外部服务查询当前公网 IP。

---

## 向后兼容说明

PRC 仓库为了兼容旧版插件，保留了以下关键兼容层：

- `DataPacket` 仍可导入，但其实际类型为 `DataModel`
- `BaseConfig.__fields__` 提供兼容视图
- `CoreControlInterface.get_config()` / `save_config()` 保留旧调用风格
- `get_plugin_control_interface()` 仍保留旧签名中的 `enter_point` 参数

如果你正在开发新插件，建议优先使用：

- `DataModel` 而不是 `DataPacket`
- `PacketType` / `PacketStatus` 而不是手写字符串常量
- `status_registry` 注册扩展状态与处理器
- `BaseConfig` + `Field` 定义强类型配置
