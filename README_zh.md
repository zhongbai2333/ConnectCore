# ConnetCore

 这是一个MCDReforged的前置插件，也可以独立使用，用于将你的服务器建立成插件控制群组，主要用于子服务器间插件的通信，比如为跨服聊天提供API和通信支持。拥有较高的安全性和简易的配置，适合各种服务器环境。

 [English](README.md) | 简中

## 使用方法

### 独立使用

 1. 将`ConnectCore.pyz`文件放在一个空文件夹内。
 2. 在命令行中运行以下命令：
    `python ConnectCore.pyz server` 或者 `python ConnectCore.pyz client` 以启服务端或客户端。
 3. 根据提示进行配置。

### 作为MCDR插件使用

 1. 将`ConnectCore.pyz`文件放在MCDR的插件目录内（通常是`plugins`文件夹）。
 2. 启动MCDR服务器，然后使用`!!connectcore init`命令来启用初始化程序。
 3. 根据提示进行配置。

## 注意事项

- 确保你的服务器和客户端能够正确连接到网络。
- 一组服务器只有一个服务端，可以有多个客户端
- 如果你遇到任何问题，请查看插件的[WIKI](https://github.com/zhongbai2333/ConnectCore/wiki)或联系开发者。
