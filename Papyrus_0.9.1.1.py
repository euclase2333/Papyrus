# -*- coding: utf-8 -*-
"""
Papyrus - 本地小说写作桌面软件
单文件版本：仅依赖 PySide6 + Python 标准库。

主要功能：
- 多作品管理 / 最近打开作品
- 无限层级大纲树
- 拖拽调整层级与顺序
- 自定义章节标题，不强制“第一章/第一节”
- 富文本编辑器
- 三套 QSS 主题
- 字体 / 字号 / 行高 / 段间距 / 编辑器宽度
- 自动保存 + 保存状态
- 今日 / 本章 / 全文统计
- 全局搜索
- 自动章节编号（可选、可关闭）
- TXT / EPUB 导出
- 单 JSON 数据文件
"""

import os
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from config import APP_NAME, LOGO_FILE
from main_window import NovelWriter


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("InkTree")
    # 界面统一字体：中文用微软雅黑（跟正文默认字体保持一致），英文优先用 Segoe UI。
    # 用 QFont.setFamilies() 给出一份"按字符回退"的字体列表，通过控件的正常字体
    # 继承机制作用到全部界面控件上——不依赖样式表。之前用 QSS 的
    # "*:not(QTextEdit)" 试图排除正文编辑器、只处理界面控件，但 Qt 的
    # 样式表并不支持对类型选择器使用 :not()，导致这条规则从未生效，
    # 界面里的中文就只能用 Segoe UI 里没有的字形，被系统换成了宋体。
    ui_font = QFont("Segoe UI", 12)
    ui_font.setFamilies(["Segoe UI", "Microsoft YaHei", "微软雅黑"])
    app.setFont(ui_font)

    # 设置程序 Logo：标题栏左上角 + 任务栏图标。
    # 找不到文件时（比如忘了把 assets/LOGO.png 放到 exe 旁边）就跳过，
    # 不会导致程序崩溃，只是没有图标显示。
    if os.path.exists(LOGO_FILE):
        app_icon = QIcon(LOGO_FILE)
        app.setWindowIcon(app_icon)
    else:
        app_icon = None
        print(f"[Papyrus] 找不到程序图标：{LOGO_FILE}")

    window = NovelWriter()
    if app_icon:
        window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
