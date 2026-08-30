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

Papyrus 是一款基于 **Python + PySide6** 开发的本地小说写作桌面软件。不依赖云端账号、不联网同步，所有作品数据以 JSON 文件的形式保存在本地磁盘上，写作过程完全离线、完全自己掌控。

界面采用左右分栏：左侧是可折叠的书架 / 书籍 / 章节大纲树，右侧是 Chrome 风格的多章节标签页 + 富文本编辑器，标题栏下方是编辑工具栏，底部状态栏实时显示字数与保存状态。

### ✨ 功能特性

**作品管理**
- 书架 → 书籍 → 章节的无限层级大纲结构，支持任意深度嵌套
- 大纲树支持拖拽调整层级与顺序（内部拖放，实时预览插入位置）
- 章节标题完全自定义，不强制"第一章 / 第一节"这类格式，"序章：雨夜""Part I""沈城·旧案"都可以直接当标题用
- 大纲树右键菜单：新建同级 / 子节点、重命名、删除、上移 / 下移、复制标题，书架 / 书籍层级操作一致
- 左侧栏可一键折叠成细长条，腾出更多编辑区域，展开状态下可自由拖拽调整宽度

**多章节标签页**
- 类似浏览器的标签页设计，可同时打开多个章节来回切换
- 标签可拖拽排序，支持独立关闭按钮
- 删除书架 / 书籍 / 章节时会自动关闭对应的已打开标签页

**富文本编辑器**
- 加粗（Ctrl+B）、斜体（Ctrl+I）、下划线（Ctrl+U）
- 引用块、无序列表、有序列表
- 左对齐 / 居中 / 右对齐
- 清除字符格式
- 工具栏内直接选择字体（自动读取本机已安装字体）与字号
- 右键菜单支持撤销 / 重做、剪切 / 复制 / 粘贴、"粘贴且不使用任何格式"

**排版与写作设置**（独立设置弹窗，"应用"按钮即时预览）
- 字号（12–20pt）、行高（1.2–2.2 倍）、段落间距、正文宽度均可调节
- 自动章节编号开关，两种编号样式可选："第 1.1 级" 或 "1 / 1.1 / 1.1.1"，编号只是显示前缀，不会改写你写的原始标题

**主题**
- 白天 / 黑夜 / 护眼绿三套完整配色方案，一键切换
- 工具栏图标会跟随主题自动重新着色（而非固定黑色图标糊在深色背景上看不清）

**统计与自动保存**
- 状态栏实时显示：本章字数 · 今日新增字数 · 全文字数
- "今日新增"按当前会话的实际新增量计算，不会把历史旧稿重复计入
- 编辑内容变化后 1.5 秒自动保存，保存状态实时显示（"● 已保存 [时间]" / "● 未保存" / "● 保存失败"）
- 关闭程序时自动保存当前章节与全部数据

**全局搜索**
- 跨所有书籍搜索标题与正文内容
- 搜索结果显示所在书籍、层级路径，以及命中内容的预览片段
- 双击结果直接跳转到对应章节

**导出**
- 导出为 **TXT**：按大纲层级缩进导出全部章节标题与正文
- 导出为标准 **EPUB 3**：自动生成目录导航（nav.xhtml）、每章节独立 xhtml 文件，可直接在 Kindle / 微信读书等主流阅读器中打开

**数据存储**
- 单一 JSON 索引文件（`novel_data.json`）记录书架与书籍元信息
- 每本书的正文单独存为一个 JSON 文件，存放在 `novel_data/` 目录下，避免单文件过大、也方便单本备份或迁移

### 🖥️ 运行环境

- Python 3.9+
- [PySide6](https://pypi.org/project/PySide6/)

### 🚀 快速开始

**方式一：直接运行源码（开发环境）**

```bash
git clone https://github.com/euclase2333/Papyrus.git
cd Papyrus
pip install PySide6
python Papyrus.py
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
├─ Papyrus.py             # 主程序
├─ ui_icons.py            # SVG 图标管理模块
├─ assets/
│  ├─ icons/              # 工具栏 / 界面用到的 SVG 图标
│  └─ LOGO.png            # 程序 Logo（标题栏 / 任务栏图标）
├─ novel_data/             # 作品数据（运行时自动生成，不建议提交到仓库）
└─ novel_data.json         # 作品索引文件（运行时自动生成）
```

### 🔒 数据与隐私

所有写作数据保存在程序目录下的 `novel_data/` 文件夹和 `novel_data.json` 索引文件中，纯本地存储，不会上传到任何服务器。仓库自带的 `.gitignore` 已经排除了这两项，避免把个人作品内容误传到公开仓库。

### 🛠️ 自行打包 exe

项目支持用 [PyInstaller](https://pyinstaller.org/) 打包成免安装的文件夹版 exe：

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Papyrus_0.8.6.3" --icon "Papyrus.ico" Papyrus.py
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

Papyrus is a local desktop novel-writing application built with **Python + PySide6**. It requires no cloud account and no network sync — all of your work is stored locally as JSON files on disk, so writing stays fully offline and entirely under your control.

The interface is split into two panes: a collapsible bookshelf → book → chapter outline tree on the left, and Chrome-style multi-chapter tabs with a rich text editor on the right. An editing toolbar sits below the tab bar, and the status bar at the bottom shows live word counts and save status.

### ✨ Features

**Project Management**
- Unlimited-depth outline tree: bookshelf → book → chapter, nested as deeply as you like
- Drag-and-drop reordering and re-nesting within the outline tree, with a live drop-position indicator
- Fully custom chapter titles — no forced "Chapter 1 / Section 1" formatting; titles like "Prologue: Rainy Night", "Part I", or anything else work as-is
- Right-click menu on the tree: create sibling/child node, rename, delete, move up/down, copy title — consistent across bookshelf, book, and chapter levels
- The sidebar can be collapsed to a thin strip with one click to free up editing space, and can be freely resized when expanded

**Multi-Chapter Tabs**
- Browser-style tabs let you keep multiple chapters open and switch between them
- Tabs are reorderable via drag-and-drop, each with its own close button
- Deleting a bookshelf, book, or chapter automatically closes any open tabs for it

**Rich Text Editor**
- Bold (Ctrl+B), Italic (Ctrl+I), Underline (Ctrl+U)
- Blockquote, bullet list, numbered list
- Left / center / right text alignment
- Clear character formatting
- Font family (auto-populated from fonts installed on your machine) and font size selectable directly from the toolbar
- Right-click menu supports undo/redo, cut/copy/paste, and "paste without formatting"

**Typography & Writing Settings** (dedicated settings dialog with an "Apply" button for instant preview)
- Adjustable font size (12–20pt), line height (1.2–2.2x), paragraph spacing, and editor width
- Optional automatic chapter numbering with two styles: "Level 1.1" or "1 / 1.1 / 1.1.1" — the number is only a display prefix and never overwrites your actual chapter title

**Themes**
- Three complete color schemes: Day / Night / Eye-care Green, switchable with one click
- Toolbar icons automatically re-color to match the active theme, instead of staying fixed black and disappearing against a dark background

**Stats & Auto-Save**
- Status bar shows live word counts: current chapter · today's new words · total words in the book
- "Today's new words" is calculated from actual growth during the current session, so old drafts are never double-counted
- Changes auto-save 1.5 seconds after you stop typing, with a live save-status indicator ("● Saved [time]" / "● Unsaved" / "● Save failed")
- The current chapter and all data are saved automatically when the app closes

**Global Search**
- Searches titles and body text across all books at once
- Results show the book, the outline path, and a preview snippet of the match
- Double-click a result to jump straight to that chapter

**Export**
- Export to **TXT**: all chapter titles and body text, indented to reflect outline hierarchy
- Export to standard **EPUB 3**: auto-generated navigation (nav.xhtml) with each chapter as its own xhtml file, ready to open in Kindle, e-readers, or any EPUB-compatible app

**Data Storage**
- A single JSON index file (`novel_data.json`) stores bookshelf and book metadata
- Each book's content is stored as its own JSON file inside `novel_data/`, keeping individual files small and making per-book backup or migration easy

### 🖥️ Requirements

- Python 3.9+
- [PySide6](https://pypi.org/project/PySide6/)

### 🚀 Getting Started

**Option 1: Run from source (development)**

```bash
git clone https://github.com/euclase2333/Papyrus.git
cd Papyrus
pip install PySide6
python Papyrus.py
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
├─ Papyrus.py             # Main application
├─ ui_icons.py            # SVG icon management module
├─ assets/
│  ├─ icons/              # SVG icons used across the toolbar and UI
│  └─ LOGO.png            # App logo (titlebar / taskbar icon)
├─ novel_data/             # Writing data (auto-generated at runtime, not recommended to commit)
└─ novel_data.json         # Project index file (auto-generated at runtime)
```

### 🔒 Data & Privacy

All writing data is stored locally in the `novel_data/` folder and `novel_data.json` index file inside the app directory — nothing is ever uploaded to any server. The repo's `.gitignore` already excludes both, so you won't accidentally push your personal manuscripts to a public repository.

### 🛠️ Building the Executable Yourself

The project can be packaged as a portable, installer-free executable using [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Papyrus_0.8.6.3" --icon "Papyrus.ico" Papyrus.py
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
