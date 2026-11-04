<p align="center"><img src="./docs/assets/icon.png" alt="LanDrop 图标" width="96"></p>

<h1 align="center">LanDrop</h1>

<p align="center"><a href="./README.md">English</a> | 简体中文</p>

在局域网内，通过手机浏览器互传 Windows 电脑与安卓手机的文件。

[下载 Windows 版](https://github.com/icelemon233/LanDrop/releases/latest) · [从源码构建](./docs/development.md)

支持 Windows 10/11 x64，界面为简体中文。

<p>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./docs/readme/desktop-dark.png">
    <img src="./docs/readme/desktop-light.png" alt="LanDrop 电脑端的合成共享文件与已配对测试手机" width="72%">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./docs/readme/phone-dark.png">
    <img src="./docs/readme/phone-light.png" alt="已配对的手机浏览器，展示同一组合成文件" width="25%">
  </picture>
</p>

*电脑端与移动浏览器的配对测试，使用合成文件，连接信息已隐藏。*

## 文件传输

- 用手机扫描电脑上的二维码建立连接。
- 多文件上传支持进度显示与取消，单个文件最大 8 GB，同名文件另存。
- 观察安装包文件夹，自动共享其中的 APK、AAB、APKS 和 XAPK，包含子文件夹。AAB 不能直接安装。
- 选择原文件共享，或拖入窗口复制到待发送目录。移除共享保留原文件。

## 开始使用

1. 运行 Windows 安装程序并打开 **LanDrop**，无需安装 Python 或手机应用。缺少 WebView2 时，安装程序会安装运行库，这一步需要联网。
2. 电脑和手机连接同一局域网，然后在电脑上添加文件。
3. 用手机扫码，在系统浏览器中打开页面。选择文件下载，或点击“发送文件到电脑”上传。

关闭电脑窗口默认进入托盘，传输继续进行。选择“退出应用”会停止应用及未完成的传输。

## 连接与数据

文件通过局域网 HTTP 传输，请使用信任的网络。二维码包含临时配对凭据，点击“重置连接”会撤销已连接手机的访问。

手机无法连接时，检查访客 Wi-Fi 隔离、VPN 路由和 Windows 防火墙。电脑有多个网卡时，在二维码下方选择地址。微信扫码后，请在系统浏览器中打开链接。

升级和卸载保留收到的文件与共享文件夹设置。传输记录保留本次运行最近 100 条，外观偏好保存在当前设备。

Windows 安装包尚未签名。详细操作见[使用说明](./docs/使用说明.txt)，依赖许可证见[第三方声明](./THIRD_PARTY_NOTICES.txt)。
