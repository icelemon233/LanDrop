# Cinna 系列归属与图标

工程名为 LanDrop，应用名为“LanDrop”，属于 Cinna 系列，开发者为 Cinna。`project.json` 是工程归属和素材入口的统一来源。应用界面保留业务名称，系列归属记录在工程与文档中。

本版沿用最新 Cinna 系列应用图标中的人物、近景构图和画风，将道具替换为显示双向文件箭头的手机。生成使用 imagegen；人物参考、系列参考和生成原图分别保留，尺寸与圆角通过本地导出。

| 文件 | 使用位置 |
| --- | --- |
| `resources/brand/landrop-source.png` | 生成原图 |
| `resources/icon-master.png` | 1024px 方形母版 |
| `resources/app.ico` | exe、安装器、卸载器、系统应用入口和快捷方式 |
| `resources/installer-sidebar.bmp`、`installer-header.bmp` | 安装向导侧栏、安装及卸载页头 |
| `frontend/assets/cinna-icon.png` | 界面标识、空状态和系统窗口 |
| `frontend/assets/favicon-16.png`、`favicon-32.png`、`favicon-48.png` | 浏览器页签 |
| `frontend/assets/apple-touch-icon.png` | 浏览器添加到主屏幕使用的图标 |
| `docs/assets/icon.png` | README 的 512px 透明圆角图标 |

运行 `python scripts/export_brand.py` 统一导出。需要 Pillow。`resources/brand/manifest.json` 记录原图与全部导出文件的 SHA-256；原图更新后必须重新导出，再构建前端和安装包。

Windows ICO 包含 16、20、24、32、40、48、64、96、128、256px 图层。快捷方式显式引用安装目录中的 `app.ico`，安装时通知 Windows 刷新图标。系统窗口使用共用的图标入口；浏览器本身的任务栏标识由浏览器管理。
