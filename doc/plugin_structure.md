# Plugin Structure

本文档描述 `Project-Refactoring-Codespace` 当前版本的插件组织方式、manifest 规范、加载行为与模式差异。

> ⚠️ `MCDR模式`和`混合模式`下的插件可以上传至 MCDR 的[插件列表收集仓库](https://github.com/MCDReforged/PluginCatalogue)，但如果只支持`独立模式`就**请勿上传**，因为不符合 MCDR 插件收录标准。

---

## 运行模式概览

ConnectCore 当前有两种主要使用方式：

1. **独立模式**
   - ConnectCore 自己加载并管理插件
   - 会扫描插件目录中的目录插件、`.mcdr` 插件包和 `.pyz` 插件包
   - 支持依赖分析、拓扑加载、级联卸载 / 重载

2. **MCDR 模式**
   - ConnectCore 本身作为 MCDR 插件运行
   - 第三方 MCDR 插件由 **MCDR** 管理，而不是由 ConnectCore 插件加载器管理
   - 你可以通过 `get_plugin_control_interface()` 获取网络发送能力

> 如果你的插件同时想兼容独立模式和 MCDR 模式，可以采用“混合模式”打包：同时提供 `connectcore.plugin.json` 和 `mcdreforged.plugin.json`。

---

## 独立模式

### 支持的插件载体

独立模式下，插件加载器会扫描 `plugins/` 目录，并接受以下三类插件：

- **目录插件**
- **`.mcdr` 压缩包插件**
- **`.pyz` 压缩包插件**

每个插件都必须提供 `connectcore.plugin.json`。

### manifest 示例

```json
{
    "id": "example_plugin",
    "version": "0.1.0",
    "name": "Example Plugin",
    "description": {
        "en_us": "Example plugin for ConnectCore",
        "zh_cn": "ConnectCore 示例插件"
    },
    "author": "your_name",
    "link": "https://github.com/your/repo",
    "dependencies": {
        "base_library": ">=1.0,<2.0"
    },
    "entrypoint": "example_plugin.connectcore.entry",
    "config_path": "config/example_plugin/config.yml",
    "config_class": "example_plugin.config.ExampleConfig",
    "archive_name": "ExamplePlugin-v{version}.mcdr",
    "resources": [
        "lang",
        "LICENSE"
    ]
}
```

### 必填字段

- `id`: 插件唯一标识
- `entrypoint`: 插件入口模块路径

### 常用字段

- `version`: 插件版本号
- `name`: 显示名称
- `description`: 多语言描述
- `author`: 作者
- `link`: 项目链接
- `dependencies`: 依赖声明
- `config_path`: 插件默认配置路径
- `config_class`: 自定义配置类路径，需继承 `BaseConfig`
- `archive_name`: 打包文件名模板
- `resources`: 打包时携带的附加资源

### `dependencies` 写法

加载器当前支持以下格式：

#### 字典形式（推荐）

```json
{
    "dependencies": {
        "base_library": ">=1.0,<2.0",
        "other_plugin": "*"
    }
}
```

#### 列表形式

```json
{
    "dependencies": [
        "base_library>=1.0,<2.0",
        "other_plugin"
    ]
}
```

### 依赖加载规则

- 启动时先扫描所有候选插件
- 根据依赖关系执行拓扑排序
- 缺失依赖会阻止插件加载
- 检测到依赖环时会报错
- `reload_plugin()` 会联动重载依赖它的插件
- `unload_plugin()` 默认会级联卸载依赖它的插件

这让插件系统比旧版更像一个“轻量插件包管理器”，不再只是简单地按文件名遍历导入。
### 独立模式注意事项

1. 独立模式只接受**目录插件**、`.mcdr` 压缩包或 `.pyz` 压缩包。
2. 如果需要同时支持混合模式，请确保同时提供 `connectcore.plugin.json` 和 `mcdreforged.plugin.json`。
3. MCDR 模式下**不会**读取 `connectcore.plugin.json` 来加载插件，详见下方 MCDR 模式章节。
4. 打包插件时可以使用 `python -m mcdreforged pack -o <输出目录>` 命令。
5. 打包时务必在 `mcdreforged.plugin.json` 的 `resources` 字段中加入 `"connectcore.plugin.json"`，否则混合模式下独立模式侧无法识别该插件。
---

## 独立模式入口点

以下回调由 ConnectCore 的插件加载器自动分发。

### `on_load(control_interface)`

插件加载时调用。

```python
from connect_core.api import PluginControlInterface

_control: PluginControlInterface | None = None


def on_load(control_interface: PluginControlInterface):
    global _control
    _control = control_interface
    _control.info("Plugin loaded")
```

### `on_unload()`

插件卸载时调用。

```python
def on_unload():
    if _control is not None:
        _control.info("Plugin unloaded")
```

### `new_connect(server_id: str)`

有新的子服务器登录时调用。

### `del_connect(server_id: str)`

有子服务器断开连接时调用。

### `websockets_started()`

WebSocket 已启动（服务端）或已连接成功（客户端）时调用。

### `connected()`

客户端登录成功后调用。

### `disconnected()`

客户端与服务端断开后调用。

### `recv_data(from_server_id: str, data: dict)`

插件收到发往自己插件 ID 的数据时调用。

> 与旧文档相比，这个回调在当前实现里**不会**再把目标插件 ID 作为参数传入，因为插件分发已经在加载器层完成了。

### `recv_file(from_server_id: str, file_path: str)`

插件收到发往自己插件 ID 的文件时调用。

---

## 独立模式目录建议

### 目录插件示例

```text
example_plugin/
├─ connectcore.plugin.json
├─ LICENSE
├─ lang/
│  ├─ en_us.yml
│  └─ zh_cn.yml
├─ example_plugin/
│  ├─ __init__.py
│  ├─ connectcore/
│  │  └─ entry.py
│  └─ config.py
```

### 推荐做法

- 入口点模块尽量保持轻量，只做初始化
- 配置类单独放到 `config.py`
- 语言文件放在 `lang/`
- 发送文件时自己保证路径可读且目标路径合理
- 使用 `BaseConfig` 而不是手写 YAML/JSON 解析

---

## MCDR 模式

MCDR 模式下，ConnectCore 作为前置插件运行。第三方插件应由 MCDR 自己加载，并在需要时获取 `PluginControlInterface`。

### `mcdreforged.plugin.json` 示例

```json
{
    "id": "example_plugin",
    "version": "0.1.0",
    "name": "Example Plugin",
    "description": {
        "en_us": "Example plugin for ConnectCore",
        "zh_cn": "ConnectCore 示例插件"
    },
    "author": "your_name",
    "link": "https://github.com/your/repo",
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

### 获取控制接口

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
    if _control is not None:
        _control.info("ConnectCore interface ready")
```

> ℹ️ 传入的 `entrypoint` 参数是你插件的**独立模式**入口点，并非 MCDR 的入口点。即使两边使用了同名的函数也不会发生覆盖或冲突。

### MCDR 模式注意事项

1. `mcdreforged.plugin.json` 的 `dependencies` 中**必须**添加 `"connect_core": "*"`（或指定版本范围），确保 ConnectCore 先于你的插件加载。
2. MCDR 模式下，你的插件和 ConnectCore 是两个独立的 MCDR 插件，满足 MCDR 贡献标准后可上传至[插件列表收集仓库](https://github.com/MCDReforged/PluginCatalogue)。

### 当前实现与旧版的差异

在当前 PRC 版本中：

- ConnectCore 在 `MCDR` 模式下**不会启用独立插件加载器**
- `connectcore.plugin.json` 不会用于自动加载 MCDR 插件
- `get_plugin_control_interface()` 主要作用是返回一个可发送数据 / 文件、可读取配置与日志的接口对象
- 第三方 MCDR 插件的生命周期仍由 MCDR 本身管理

因此，旧文档中“后续回调与独立模式相同”的说法，在 PRC 当前实现里**不再适合作为保证**。
> ℹ️ 在 MCDR 模式下，`PluginControlInterface` 中的 `info`、`warn`、`error`、`debug` 实际调用的是你插件的 `PluginServerInterface.logger` 对应方法。因此在混合模式下无需同时适配 `_control.info` 和 `PluginServerInterface.logger.info`——它们是统一的。
---

## 混合模式建议

如果你希望一个插件同时支持 ConnectCore 独立模式与 MCDR 模式，建议：

- 同时保留 `connectcore.plugin.json` 与 `mcdreforged.plugin.json`
- 将公共逻辑抽到共享模块
- 分别提供：
  - `example_plugin.connectcore.entry`
  - `example_plugin.mcdr.entry`
- 避免在两个入口点中复制业务逻辑

---

## 配置类

如果 manifest 中指定了 `config_class`，ConnectCore 会尝试动态导入该类，并要求它继承 `BaseConfig`。

```python
from connect_core.api import BaseConfig, Field

class ExampleConfig(BaseConfig):
    __config_path__ = "config/example_plugin/config.yml"

    enabled: bool = Field(True, "是否启用")
    channel: str = Field("default", "频道名")
```

如果没有指定 `config_class`，加载器会自动生成一个默认配置类，并使用：

- manifest 中的 `config_path`
- 或默认路径 `config/<plugin_id>/config.yml`

---

## 卸载与重载行为

PRC 新版插件系统在卸载时会做更多清理工作：

- 调用插件的 `on_unload()`
- 移除导入模块
- 释放 `sys.path` 注入项
- 清理该插件注册的命令与补全词典
- 更新依赖关系图

这比旧版实现更安全，能减少“插件卸载了但命令还挂着”的残留问题。

---

## 最佳实践

- 所有插件对外能力统一通过 `connect_core.api` 导入
- 不要依赖 `connect_core` 内部私有模块路径
- `id` 一旦发布就尽量不要改
- 依赖约束尽量写清楚版本范围
- 自定义配置请使用 `BaseConfig`
- 网络通信请使用 `PluginControlInterface.send_data()` / `send_file()`
- 需要扩展协议时，优先使用 `status_registry` 注册自定义状态，而不是硬改内置协议
