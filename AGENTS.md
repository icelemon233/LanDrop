# LanDrop工程约定

这是 Windows 桌面软件，电脑端由 pywebview / WebView2 独立窗口承载，手机端扫码后使用浏览器。局域网 HTTP 服务在电脑上运行，不部署公网服务，不自动启动外部浏览器。

本工程属于 Cinna 系列，工程名与应用名均为 LanDrop、开发者 Cinna，统一记录在 project.json。应用界面使用业务名称；系列归属记录在工程元数据和文档中。

- 应用、安装器、卸载器、快捷方式、网页页签、系统窗口及 README 的品牌图标统一从 project.json 指定的原图导出，禁止逐处手工替换成不同版本。
- 更新品牌素材后运行 scripts/export_brand.py，再构建和检查真实 exe、安装器、快捷方式与浏览器资源；resources/brand/manifest.json 记录导出哈希。

- Python 3.12+；服务协议、文件目录、桌面平台调用分别位于 server.py、state.py、desktop_window.py；desktop.py 仅提供启动前提示与桌面宿主入口。持久化、会话、上传、启动与进程生命周期各有独立模块。
- 桌面主窗口在主线程启动。关闭窗口须清理服务和传输；重复启动只认证并激活原窗口。WebView2 仅导航本实例的回环页面，不向网页暴露 Python 文件或命令执行接口。
- 前端是严格 TypeScript，按 app / api / session / features / ui 划分，服务端是文件与连接状态的事实来源。
- 管理操作必须是本机管理员会话；手机通过二维码里的临时随机凭据建立会话。
- 不提供任意路径文件读取、命令执行或静态目录浏览。共享目录中的链接与隐藏路径不发布。
- 上传流式写入临时文件，完成后原子保存；取消与失败必须清理。原文件不会被移除共享操作删除。
- 检查：pnpm check、pnpm build、pnpm test、python -m unittest discover -s tests -v。
- 打包：python scripts/package.py（先完成前端构建）。构建产物、运行数据和测试数据不进入源码压缩包。
- 安装器：scripts/build_installer.py 使用经哈希校验的 NSIS 3.13。安装测试必须使用独立 QA 注册项、快捷方式和数据目录。升级仅请求正常退出，不能强制结束旧程序；卸载保留用户数据和安装目录内非应用文件。
- 版本只改 landrop/version.json。交付前比较 build/build-manifest.json 的源码摘要，记录 exe、安装器和源码包的 SHA-256。无 Git 仓库时不虚构 commit。
