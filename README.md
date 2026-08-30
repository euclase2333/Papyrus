<div align="center">

<img src="assets/LOGO.png" width="120" alt="Papyrus logo" />

# Papyrus

**本地小说写作桌面软件 · Local Novel Writing Desktop App**

[简体中文](#简体中文) ｜ [English](#english)

</div>

---

## 简体中文

> 默认展示中文说明。需要英文版请点击下方 **English** 折叠块展开。

### 简介

Papyrus 是一款基于 **Python + PySide6** 开发的本地小说写作桌面软件。不依赖云端账号、不联网同步，所有作品数据以 JSON 文件的形式保存在本地，写作过程完全离线可控。

### ✨ 功能特性

- 📚 多作品管理，支持最近打开的作品快速切换
- 🌳 无限层级大纲树，书架 → 书籍 → 章节任意嵌套
- 🖱️ 拖拽调整章节层级与顺序
- ✍️ 自定义章节标题，不强制"第一章 / 第一节"这类固定格式
- 📝 富文本编辑器（加粗、斜体、下划线、引用块、有序 / 无序列表、对齐方式等）
- 🎨 三套内置主题：白天 / 黑夜 / 护眼绿，随时切换
- 🔤 可自定义字体、字号、行高、段间距、编辑器宽度
- 💾 自动保存，实时显示保存状态
- 📊 今日字数 / 本章字数 / 全文字数统计
- 🔍 全局搜索，快速定位内容
- 🔢 自动章节编号（可选，可随时关闭）
- 📤 支持导出为 **TXT** 和 **EPUB**
- 🗂️ 单 JSON 文件存储索引，每本书正文单独存档，结构清晰、便于备份

### 🖥️ 运行环境

- Python 3.9+
- [PySide6](https://pypi.org/project/PySide6/)

### 🚀 快速开始

**方式一：直接运行源码（开发环境）**

```bash
git clone https://github.com/euclase2333/Papyrus.git
cd Papyrus
pip install PySide6
python Papyrus_0.8.6.3.py
```

**方式二：使用打包好的 exe（Windows，无需安装 Python）**

前往 [Releases](https://github.com/euclase2333/Papyrus/releases) 页面下载压缩包，解压后运行：

```
Papyrus_0.8.6.3/
├─ Papyrus_0.8.6.3.exe   ← 双击运行
├─ assets/
├─ _internal/
└─ novel_data/            ← 你的作品数据（首次运行自动生成）
```

### 📁 项目结构

```
papyrus/
├─ Papyrus_0.8.6.3.py     # 主程序
├─ ui_icons.py            # SVG 图标管理模块
├─ assets/
│  ├─ icons/              # 工具栏 / 界面用到的 SVG 图标
│  └─ LOGO.png            # 程序 Logo（标题栏 / 任务栏图标）
├─ novel_data/             # 作品数据（运行时自动生成，不建议提交到仓库）
└─ novel_data.json         # 作品索引文件（运行时自动生成）
```

### 🔒 数据与隐私

所有写作数据保存在程序目录下的 `novel_data/` 文件夹和 `novel_data.json` 索引文件中，纯本地存储，不会上传到任何服务器。建议将 `novel_data/`、`novel_data.json` 加入 `.gitignore`，避免把个人作品内容误传到公开仓库。

### 🛠️ 自行打包 exe

项目支持用 [PyInstaller](https://pyinstaller.org/) 打包成免安装的文件夹版 exe：

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Papyrus_0.8.6.3" --icon "Papyrus.ico" Papyrus_0.8.6.3.py
```

打包完成后，把 `assets/` 文件夹手动复制到生成的 `dist/Papyrus_0.8.6.3/` 目录下（与 exe 平级），即可获得开箱即用的文件夹版发行包。

### 🗺️ Roadmap

- [ ] 自定义可跟随主题变色的标题栏
- [ ] 更多导出格式支持
- [ ] 跨平台打包（macOS / Linux）

### 🤝 贡献

欢迎提交 Issue 或 Pull Request。提交前请确保代码风格与现有代码保持一致。

### 📄 License

本项目基于 [MIT License](LICENSE) 开源。

---

<details>
<summary>🇬🇧 <strong>English</strong> (click to expand)</summary>

<a id="english"></a>

## English

> Chinese is shown by default above. Click here to read the English version.

### Introduction

Papyrus is a local desktop novel-writing application built with **Python + PySide6**. It requires no cloud account and no network sync — all of your work is stored locally as JSON files, so writing stays fully offline and under your control.

### ✨ Features

- 📚 Multi-project management with quick access to recently opened works
- 🌳 Unlimited-depth outline tree — bookshelf → book → chapter, nested freely
- 🖱️ Drag-and-drop reordering and re-nesting of chapters
- ✍️ Fully custom chapter titles — no forced "Chapter 1 / Section 1" formatting
- 📝 Rich text editor (bold, italic, underline, blockquote, ordered/unordered lists, text alignment, etc.)
- 🎨 Three built-in themes: Day / Night / Eye-care Green, switchable anytime
- 🔤 Customizable font, font size, line height, paragraph spacing, and editor width
- 💾 Auto-save with real-time save status indicator
- 📊 Word count stats for today / current chapter / entire work
- 🔍 Global search to quickly locate content
- 🔢 Optional automatic chapter numbering (can be toggled off)
- 📤 Export to **TXT** and **EPUB**
- 🗂️ A single JSON index file, with each book's content stored separately — clean structure, easy to back up

### 🖥️ Requirements

- Python 3.9+
- [PySide6](https://pypi.org/project/PySide6/)

### 🚀 Getting Started

**Option 1: Run from source (development)**

```bash
git clone https://github.com/euclase2333/Papyrus.git
cd Papyrus
pip install PySide6
python Papyrus_0.8.6.3.py
```

**Option 2: Use the packaged executable (Windows, no Python required)**

Download the archive from the [Releases](https://github.com/euclase2333/Papyrus/releases) page, extract it, and run:

```
Papyrus_0.8.6.3/
├─ Papyrus_0.8.6.3.exe   ← double-click to run
├─ assets/
├─ _internal/
└─ novel_data/            ← your writing data (auto-created on first run)
```

### 📁 Project Structure

```
papyrus/
├─ Papyrus_0.8.6.3.py     # Main application
├─ ui_icons.py            # SVG icon management module
├─ assets/
│  ├─ icons/              # SVG icons used across the toolbar and UI
│  └─ LOGO.png            # App logo (titlebar / taskbar icon)
├─ novel_data/             # Writing data (auto-generated at runtime, not recommended to commit)
└─ novel_data.json         # Project index file (auto-generated at runtime)
```

### 🔒 Data & Privacy

All writing data is stored locally in the `novel_data/` folder and `novel_data.json` index file inside the app directory — nothing is ever uploaded to any server. It's recommended to add `novel_data/` and `novel_data.json` to `.gitignore` to avoid accidentally pushing your personal manuscripts to a public repository.

### 🛠️ Building the Executable Yourself

The project can be packaged as a portable, installer-free executable using [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Papyrus_0.8.6.3" --icon "Papyrus.ico" Papyrus_0.8.6.3.py
```

After building, manually copy the `assets/` folder into the generated `dist/Papyrus_0.8.6.3/` directory (alongside the `.exe`) to get a ready-to-run distribution folder.

### 🗺️ Roadmap

- [ ] Custom titlebar that follows the app theme
- [ ] Additional export formats
- [ ] Cross-platform builds (macOS / Linux)

### 🤝 Contributing

Issues and Pull Requests are welcome. Please keep code style consistent with the existing codebase before submitting.

### 📄 License

This project is open-sourced under the [MIT License](LICENSE).

</details>
