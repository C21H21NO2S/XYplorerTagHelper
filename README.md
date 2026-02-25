# XYplorerTagHelper 🏷️

一个专为强大文件管理器 **XYplorer** 量身定制的高级标签辅助与过滤工具。
通过现代化的可视化界面，帮助你更高效地管理文件标签、生成复杂的搜索语法、并实现工作区的自由定制。

<img width="1100" height="960" alt="XYplorerTagHelper 1 2 2-Dark   Light" src="https://github.com/user-attachments/assets/a756e291-1d21-42f7-97cd-5285437fa03b" />


## ✨ 核心特性

* **🚀 可视化标签树**：告别繁琐的纯文本输入，支持无限层级的标签分组、自由拖拽排序。
* **🔍 智能过滤构建**：支持通过点击组合条件（路径、文件名、备注、标注、评分、大小、日期），自动生成并发送 XYplorer 的高级搜索语法。
* **🎨 现代原生 UI**：内置暗黑 (Dark) 与浅色 (Light) 双主题，支持自定义组件颜色、原生 Windows 11 标题栏沉浸式体验。
* **💼 多工作区管理**：根据不同的工作流（如“默认工作区”、“项目状态”等）隔离标签数据，支持快速切换。
* **⚡ 极速交互**：支持从剪贴板智能读取并激活标签、支持一键同步 XYplorer 原生批注 (Labels)。

## 📥 下载与安装 (非程序员推荐)

如果你只想直接使用该软件，无需配置任何代码环境：
1. 前往本项目的 [Releases 页面](https://github.com/C21H21NO2S/XYplorerTagHelper/releases)
2. 下载最新版本的 `XYplorerTagHelper_ver.7z`
3. 解压后，双击运行 `XYplorerTagHelper.exe` 即可使用。

## 💻 从源码运行 (开发者)

如果你安装了 Python 环境，可以按以下步骤运行或二次开发（requirements：pywebview≥4.0）：

```bash
# 克隆仓库
git clone https://github.com/C21H21NO2S/XYplorerTagHelper.git
cd 你的仓库名

# 安装依赖项 (核心依赖为 pywebview)
pip install -r requirements.txt

# 运行程序
python XYplorerTagHelper.py

## 🛠️ 配合 XYplorer 的使用准备

```
## 🛠️ 配合 XYplorer 的使用准备

为了让 Helper 顺利控制 XYplorer，请确保在软件设置（点击右上角齿轮图标 ⚙️）中：

* 正确配置了 **XYplorer 路径**（例如：`C:\XYplorer\XYplorer.exe` 或纯文件夹路径）。

## 🙋‍♂️ 关于作者与反馈

我是一个代码小白但充满热情的创作者！这个工具是为了解决我自己在使用 XYplorer 时的痛点而诞生的。

如果你在使用过程中遇到任何 Bug，或者有好的功能建议，欢迎在 GitHub 的 [Issues](https://github.com/C21H21NO2S/XYplorerTagHelper/issues) 中提出！

## 📄 开源协议

[MIT License](https://www.google.com/search?q=LICENSE)

