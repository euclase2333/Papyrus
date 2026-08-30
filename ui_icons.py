import os
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer


# ============================================================
# InkTree Pro - 图标管理模块
# ============================================================
#
# 这个文件专门负责管理所有 SVG 图标。
#
# 主程序 inktree_pro_v8.py 不需要知道 SVG 文件的具体路径。
#
# 以后如果你想更换某个图标：
#     只需要替换 assets/icons/ 里面的 SVG
#
# 或者修改下面 ICONS 的对应关系。
#
# ============================================================


# 当前程序所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_icon_dir():
    """
    自动寻找 icons 文件夹，兼容几种常见的摆放方式，
    避免因为 ui_icons.py 具体放在哪一层而导致路径拼错、图标找不到：

    1）ui_icons.py 所在目录 / assets / icons        （推荐的标准结构）
    2）ui_icons.py 所在目录 / icons                  （ui_icons.py 已经在 assets 里）
    3）ui_icons.py 所在目录 / .. / assets / icons     （ui_icons.py 被多放进了一层子目录）
    """
    candidates = [
        os.path.join(BASE_DIR, "assets", "icons"),
        os.path.join(BASE_DIR, "icons"),
        os.path.join(BASE_DIR, "..", "assets", "icons"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.normpath(c)
    # 都没找到时，仍然返回默认位置；具体缺失哪个文件会在 icon() / check_icons() 里逐个打印出来
    return os.path.normpath(candidates[0])


# SVG 图标目录
ICON_DIR = _resolve_icon_dir()


# ============================================================
# 图标名称映射
# ============================================================

ICONS = {

    # --------------------------------------------------------
    # 编辑器
    # --------------------------------------------------------

    # 加粗
    "bold":
        "bold.svg",

    # 斜体
    "italic":
        "italic.svg",

    # 下划线
    "underline":
        "baseline.svg",

    # 引用块
    "quote":
        "quote.svg",

    # 无序列表
    "bullet-list":
        "list.svg",

    # 有序列表
    "number-list":
        "list-ordered.svg",


    # --------------------------------------------------------
    # 对齐
    # --------------------------------------------------------

    # 左对齐
    "align-left":
        "text-align-start.svg",

    # 居中
    "align-center":
        "text-align-center.svg",

    # 右对齐
    "align-right":
        "text-align-end.svg",


    # --------------------------------------------------------
    # 历史记录
    # --------------------------------------------------------

    # 撤销
    "undo":
        "undo-2.svg",

    # 重做
    "redo":
        "redo-2.svg",


    # --------------------------------------------------------
    # 格式
    # --------------------------------------------------------

    # 清除字符格式
    "clear-format":
        "brush-cleaning.svg",


    # --------------------------------------------------------
    # 搜索
    # --------------------------------------------------------

    "search":
        "search.svg",


    # --------------------------------------------------------
    # 主题
    # --------------------------------------------------------

    # 白天
    "theme-day":
        "sun.svg",

    # 黑夜
    "theme-night":
        "moon.svg",

    # 护眼绿
    "theme-green":
        "leafy-green.svg",


    # --------------------------------------------------------
    # 书架 / 书籍 / 大纲
    # --------------------------------------------------------

    # 书架（顶层容器）
    "bookshelf":
        "bookshelf.svg",

    # 书籍
    "book":
        "book.svg",

    # 正文 / 章节
    "paper":
        "paper.svg",


    # --------------------------------------------------------
    # 导出
    # --------------------------------------------------------

    # 保存 / 导出（TXT、EPUB 按钮共用）
    "save":
        "save.svg",


    # --------------------------------------------------------
    # 工具栏 · 下拉框
    # --------------------------------------------------------

    # 下拉框内部右侧的层级箭头（字号 / 字体样式下拉框共用）
    "chevron-down":
        "chevron-down.svg",


    # --------------------------------------------------------
    # 层级结构折叠 / 展开
    # --------------------------------------------------------

    # 展开层级结构（收起状态下显示）
    "sidebar-expand":
        "arrow-right-from-line.svg",

    # 收起层级结构（展开状态下显示）
    "sidebar-collapse":
        "arrow-left-to-line.svg",


    # --------------------------------------------------------
    # 章节标签页
    # --------------------------------------------------------

    # 标签页右侧的关闭按钮
    "tab-close":
        "x.svg",
}


# ============================================================
# 按主题颜色重新着色 SVG
# ============================================================
#
# 图标库（Lucide 风格）大多用 currentColor 作为描边颜色，
# 直接用 QIcon(path) 加载时没有颜色上下文，会显示成默认的黑色，
# 在黑夜 / 护眼模式的深色背景下几乎看不清。
# 这里直接把 SVG 源码里的颜色替换成目标颜色，再用 QSvgRenderer
# 画到一张透明背景的 QPixmap 上，生成对应颜色的 QIcon。
#
# ============================================================

def _colored_icon(path, color, size=64):

    with open(path, "r", encoding="utf-8") as f:
        svg_text = f.read()

    # currentColor 是 Lucide 图标默认写法
    svg_text = svg_text.replace("currentColor", color)

    # 少数图标可能直接写死了黑色，一并替换掉
    for black in ("#000000", "#000", "black"):
        svg_text = svg_text.replace(f'stroke="{black}"', f'stroke="{color}"')
        svg_text = svg_text.replace(f'fill="{black}"', f'fill="{color}"')

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


# ============================================================
# 获取图标
# ============================================================

def icon(name, color=None, size=64):
    """
    根据 InkTree 的内部名称返回 QIcon。

    例如：

        icon("bold")
        icon("italic")
        icon("quote")
        icon("align-center")
        icon("theme-night")

    主程序不需要知道 SVG 的真实文件名。

    color:
        可选，形如 "#F3F4F6" 的十六进制颜色。
        本项目的 SVG 图标大多使用 currentColor 描边（Lucide 风格），
        不传 color 时图标会按 SVG 文件里写死的颜色显示（通常是黑色），
        在黑夜 / 护眼等深色背景下会看不清。
        传入 color 后会返回一份按该颜色重新着色的图标，
        用于让工具栏图标跟随当前主题变色。
    """

    filename = ICONS.get(name)

    # 如果没有找到对应图标
    if not filename:
        return QIcon()

    path = os.path.join(
        ICON_DIR,
        filename
    )

    # 如果 SVG 文件不存在
    if not os.path.exists(path):
        print(
            f"[InkTree] 找不到图标：{path}"
        )
        return QIcon()

    if not color:
        return QIcon(path)

    return _colored_icon(path, color, size)


# ============================================================
# 检查所有图标
# ============================================================

def check_icons():
    """
    启动时可以调用这个函数检查图标是否完整。

    返回：
        True  = 全部存在
        False = 有图标缺失
    """

    success = True

    for name, filename in ICONS.items():

        path = os.path.join(
            ICON_DIR,
            filename
        )

        if not os.path.exists(path):

            print(
                f"[InkTree] 缺少图标：{name} -> {filename}"
            )

            success = False

    return success