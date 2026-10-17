# 隔空传工程约定

这是 Windows 本地软件，浏览器是界面；局域网 HTTP 服务在电脑上运行，不部署公网服务。

本工程属于 Cinna 系列，工程名 LanDrop、应用名“隔空传”、开发者 Cinna，统一记录在 project.json。应用界面使用业务名称；系列归属记录在工程元数据和文档中。

- 应用、安装器、卸载器、快捷方式、网页页签、系统窗口及 README 的品牌图标统一从 project.json 指定的原图导出，禁止逐处手工替换成不同版本。
- 更新品牌素材后运行 scripts/export_brand.py，再构建和检查真实 exe、安装器、快捷方式与浏览器资源；resources/brand/manifest.json 记录导出哈希。

- Python 3.12+；服务协议、文件目录、桌面平台调用分别位于 server.py、state.py、desktop.py；持久化、会话、上传、启动与进程生命周期各有独立模块。
- 前端是严格 TypeScript，按 app / api / session / features / ui 划分，服务端是文件与连接状态的事实来源。
- 管理操作必须是本机管理员会话；手机通过二维码里的临时随机凭据建立会话。
- 不提供任意路径文件读取、命令执行或静态目录浏览。共享目录中的链接与隐藏路径不发布。
- 上传流式写入临时文件，完成后原子保存；取消与失败必须清理。原文件不会被移除共享操作删除。
- 检查：pnpm check、pnpm build、pnpm test、python -m unittest discover -s tests -v。
- 打包：python scripts/package.py（先完成前端构建）。构建产物、运行数据和测试数据不进入源码压缩包。
- 安装器：scripts/build_installer.py 使用经哈希校验的 NSIS 3.13。安装测试必须使用独立 QA 注册项、快捷方式和数据目录。升级仅请求正常退出，不能强制结束旧程序；卸载保留用户数据和安装目录内非应用文件。
- 版本只改 landrop/version.json。交付前比较 build/build-manifest.json 的源码摘要，记录 exe、安装器和源码包的 SHA-256。无 Git 仓库时不虚构 commit。
