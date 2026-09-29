# -*- coding: utf-8 -*-
"""Papyrus 配置：常量、路径、默认设置、两个通用小函数。"""

import os
import sys
import uuid
from datetime import datetime

APP_NAME = "Papyrus"
APP_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
DATA_FILE = os.path.join(APP_DIR, "novel_data.json")
# 每本书的正文单独存一个 json，统一放在这个子目录里，
# 命名格式为 novel_data_001.json / novel_data_002.json / ……
DATA_DIR = os.path.join(APP_DIR, "novel_data")

# 程序 Logo（标题栏 / 任务栏图标），放在 assets 目录下，跟 icons/ 平级。
# exe 文件本身的图标（资源管理器里看到的那个）是打包时用 --icon 参数
# 单独嵌进 exe 的，跟这里加载的 png 是两回事，互不影响。
LOGO_FILE = os.path.join(APP_DIR, "assets", "LOGO.png")

DEFAULT_SETTINGS = {
    "theme": "day",
    "font": "Microsoft YaHei",
    "font_size": 15,
    "line_height": 1.5,
    "paragraph_spacing": 4,
    "editor_width": 860,
    "auto_number": False,
    "number_mode": "chapter",
    "recent_book_ids": [],
    "open_tabs": [],
    "active_tab_id": None,
    "today_date": "",
    "today_words": 0,
}


def now_string():
    return datetime.now().strftime("%H:%M:%S")


def new_id():
    return str(uuid.uuid4())
