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

import sys
import os
import json
import uuid
import zipfile
import html
import re
from datetime import datetime, date

import ui_icons

from PySide6.QtCore import (
    Qt, QModelIndex, QAbstractItemModel, QMimeData,
    QTimer, QSize, QByteArray, QDateTime, QRectF,
    QVariantAnimation, QEasingCurve, QEvent
)
from PySide6.QtGui import (
    QAction, QFont, QTextCursor, QTextCharFormat,
    QTextBlockFormat, QTextListFormat, QKeySequence,
    QTextDocument, QColor, QPalette, QPainterPath, QRegion,
    QPainter, QFontDatabase, QIcon
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeView, QTextEdit, QToolBar, QLabel, QPushButton,
    QComboBox, QLineEdit, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QFileDialog, QInputDialog, QMenu, QStyle, QFrame,
    QStatusBar, QSpinBox, QCheckBox, QAbstractItemView, QScrollArea,
    QTabWidget, QTabBar, QListWidget, QListWidgetItem, QGroupBox, QSizePolicy,
    QToolButton
)

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


class NovelNode:
    def __init__(self, title="未命名", content="", node_id=None, parent=None,
                 created_at=None, updated_at=None):
        self.id = node_id or new_id()
        self.title = title
        self.content = content
        self.children = []
        self.parent = parent
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")
        self.updated_at = updated_at or self.created_at
        # 本章字数缓存：None 表示"还没算过/内容已变，需要重新算"。
        # 只在 content 真正被改写的地方（NovelWriter 里两处赋值）主动清空，
        # 避免每次统计全书字数时把没改过的章节也重新解析一遍 HTML。
        self._word_count_cache = None

    def add_child(self, node, row=None):
        node.parent = self
        if row is None:
            self.children.append(node)
        else:
            self.children.insert(row, node)

    def touch(self):
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def touch_chain(self):
        """标记自己和所有上级（章节 -> 书籍 -> 书架）都发生了更新。"""
        n = self
        while n is not None:
            n.touch()
            n = n.parent

    def root(self):
        n = self
        while n.parent is not None:
            n = n.parent
        return n

    def nearest_book(self):
        """从当前节点往上找，返回它所属的那本书（NovelBook）；书架/游离节点返回 None。"""
        n = self
        while n is not None and not isinstance(n, NovelBook):
            n = n.parent
        return n

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "children": [x.to_dict() for x in self.children],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data, parent=None):
        node = cls(
            title=data.get("title", "未命名"),
            content=data.get("content", ""),
            node_id=data.get("id"),
            parent=parent,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
        for child in data.get("children", []):
            node.children.append(NovelNode.from_dict(child, node))
        return node


class NovelBook(NovelNode):
    """一本书（原来的“作品”）。本身也是一个节点，可以和书架、章节显示在同一棵树里。"""

    def __init__(self, name="未命名书籍", book_id=None):
        super().__init__(title=name, node_id=book_id, parent=None)
        self.file = None  # 对应 novel_data/ 目录下的独立 json 文件名

    @property
    def name(self):
        return self.title

    @name.setter
    def name(self, value):
        self.title = value

    @property
    def tree(self):
        return self.children

    @tree.setter
    def tree(self, value):
        self.children = value

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "tree": [x.to_dict() for x in self.children],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data, book_id=None, file=None):
        book = cls(data.get("name", "未命名书籍"), book_id or data.get("id"))
        book.created_at = data.get("created_at", book.created_at)
        book.updated_at = data.get("updated_at", book.updated_at)
        book.children = [NovelNode.from_dict(x, book) for x in data.get("tree", [])]
        book.file = file
        return book


class NovelShelf(NovelNode):
    """书架：容纳多本书籍的顶层容器，本身永远没有上级。"""

    def __init__(self, name="未命名书架", shelf_id=None):
        super().__init__(title=name, node_id=shelf_id, parent=None)

    @property
    def name(self):
        return self.title

    @name.setter
    def name(self, value):
        self.title = value

    @property
    def books(self):
        return self.children

    def to_dict_index(self):
        """写进主索引文件 novel_data.json 里的书架信息：只存书籍的元数据和文件名，
        每本书真正的大纲/正文在各自的 novel_data/novel_data_xxx.json 里。"""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "books": [
                {"id": b.id, "name": b.name, "file": b.file}
                for b in self.children
            ],
        }


class DataManager:
    def __init__(self):
        self.shelves = []
        self.settings = dict(DEFAULT_SETTINGS)
        self._next_seq = 1
        self.load()

    # ---------- 书籍文件命名 ----------
    def reserve_book_file(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        while True:
            name = f"novel_data_{self._next_seq:03d}.json"
            self._next_seq += 1
            if not os.path.exists(os.path.join(DATA_DIR, name)):
                return name

    def create_default(self):
        shelf = NovelShelf("书架")
        book = NovelBook("我的第一部小说")
        book.parent = shelf
        chapter = NovelNode("开篇")
        chapter.parent = book
        book.children.append(chapter)
        book.file = self.reserve_book_file()
        shelf.children.append(book)
        self.shelves = [shelf]

    def load(self):
        if not os.path.exists(DATA_FILE):
            self.create_default()
            self.save()
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.settings.update(data.get("settings", {}))
            # 从旧版本迁移：避免原来的 Georgia / 13pt 继续覆盖新版默认排版。
            if self.settings.get("font") in (None, "", "Georgia"):
                self.settings["font"] = "Microsoft YaHei"
            try:
                if int(self.settings.get("font_size", 15)) < 12:
                    self.settings["font_size"] = 15
            except (TypeError, ValueError):
                self.settings["font_size"] = 15
            # 默认排版改回 15pt / 1.5 倍行距：把旧数据里残留的 18pt / 1.6 倍
            # 行距也一并迁移回来，避免旧存档一直覆盖新的默认值。
            try:
                if int(self.settings.get("font_size", 15)) == 18:
                    self.settings["font_size"] = 15
            except (TypeError, ValueError):
                pass
            try:
                if float(self.settings.get("line_height", 1.5)) == 1.6:
                    self.settings["line_height"] = 1.5
            except (TypeError, ValueError):
                pass

            self._next_seq = int(data.get("next_seq", 1))

            migrated = "shelves" not in data
            if not migrated:
                # 新格式：主文件只存“书架/书籍”索引，每本书的正文单独存一个文件。
                self.shelves = []
                for shelf_data in data.get("shelves", []):
                    shelf = NovelShelf(shelf_data.get("name", "未命名书架"), shelf_data.get("id"))
                    shelf.created_at = shelf_data.get("created_at", shelf.created_at)
                    shelf.updated_at = shelf_data.get("updated_at", shelf.updated_at)
                    for book_entry in shelf_data.get("books", []):
                        book = self._load_book_file(book_entry)
                        if book:
                            book.parent = shelf
                            shelf.children.append(book)
                    self.shelves.append(shelf)
            else:
                # 旧格式迁移（v8.1 及更早：只有一层“作品”，全部存在同一个文件里）。
                # 统一放进一个默认书架，并把每部作品拆分成独立文件。
                shelf = NovelShelf("书架")
                for wdata in data.get("works", []):
                    fname = self.reserve_book_file()
                    book = NovelBook.from_dict(wdata, file=fname)
                    book.parent = shelf
                    shelf.children.append(book)
                self.shelves = [shelf] if shelf.children else []

            if not self.shelves:
                self.create_default()
                migrated = True

            # 只有真的发生了格式迁移、或者因为没有任何书架而新建了默认数据时，
            # 才需要立即落盘——正常情况下（已经是新格式、书架也都在）每次
            # 启动都无条件把所有书籍的正文重新序列化再整个写回磁盘一遍，是
            # 纯浪费的开销：既没有任何内容变化，也没有東西需要迁移，等于每次
            # 打开软件都要多读一遍、再多写一遍全部书籍的 JSON，这正是
            # “第一次打开有点卡”的一部分来源。
            if migrated:
                self.save()
        except Exception:
            # 保留损坏文件，避免静默覆盖用户数据
            try:
                bad = DATA_FILE + ".broken-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                os.replace(DATA_FILE, bad)
            except Exception:
                pass
            self.settings = dict(DEFAULT_SETTINGS)
            self._next_seq = 1
            self.create_default()
            self.save()

    def _load_book_file(self, book_entry):
        fname = book_entry.get("file")
        if not fname:
            return None
        path = os.path.join(DATA_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                wdata = json.load(f)
            return NovelBook.from_dict(wdata, book_id=book_entry.get("id"), file=fname)
        except Exception:
            return None

    def save(self):
        ok = True
        for shelf in self.shelves:
            for book in shelf.children:
                if not book.file:
                    book.file = self.reserve_book_file()
                ok = self._save_book_file(book) and ok
        ok = self._save_index() and ok
        return ok

    def _save_book_file(self, book):
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, book.file)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(book.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    def _save_index(self):
        data = {
            "version": 4,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "next_seq": self._next_seq,
            "shelves": [shelf.to_dict_index() for shelf in self.shelves],
            "settings": self.settings,
        }
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
            return True
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    def forget_book_file(self, book):
        """删除书籍时，同时清掉它在 novel_data/ 里的独立文件。"""
        if book.file:
            path = os.path.join(DATA_DIR, book.file)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def all_books(self):
        out = []
        for shelf in self.shelves:
            out.extend(shelf.children)
        return out

    def find_book(self, book_id):
        return next((b for b in self.all_books() if b.id == book_id), None)

    def find_node(self, node_id):
        return self._find_in_nodes(self.shelves, node_id)

    def _find_in_nodes(self, nodes, node_id):
        for n in nodes:
            if n.id == node_id:
                return n
            found = self._find_in_nodes(n.children, node_id)
            if found:
                return found
        return None


def _rounded_region(width, height, radius):
    """生成一个圆角矩形的窗口遮罩：直接裁剪弹出窗口的形状，
    比 WA_TranslucentBackground（半透明合成）更可靠——
    半透明合成在部分环境下会把圆角外的区域画成纯黑，而不是透明。"""
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    return QRegion(path.toFillPolygon().toPolygon())


class RoundedComboBox(QComboBox):
    """展开的选项列表用窗口遮罩裁出圆角，避免黑角。"""
    POPUP_RADIUS = 6

    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        popup.setMask(_rounded_region(popup.width(), popup.height(), self.POPUP_RADIUS))


class FontComboBox(RoundedComboBox):
    """字体样式 / 字号下拉框：外观跟“搜索全部书架/书籍”输入框保持一致（由 QSS 按 objectName 控制），
    原生下拉箭头隐藏，改为在框内右侧手绘一个层级箭头风格的“向下小于号”，
    观感上跟大纲树的层级展开箭头统一。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arrow_color = "#222222"

    def set_arrow_color(self, color):
        self._arrow_color = color
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        arrow = ui_icons.icon("chevron-down", self._arrow_color).pixmap(12, 12)
        if arrow.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        x = self.width() - arrow.width() - 10
        y = (self.height() - arrow.height()) // 2
        painter.drawPixmap(x, y, arrow)
        painter.end()


class NovelTreeModel(QAbstractItemModel):
    """统一的三层大纲树：书架（NovelShelf）-> 书籍（NovelBook）-> 章节（NovelNode，可无限嵌套）。"""

    MIME = "application/x-inktree-node"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.roots = []          # list[NovelShelf]
        self.icon_color = None   # 由主窗口在切换主题时设置，用于给图标着色

    def set_roots(self, shelves):
        self.beginResetModel()
        self.roots = shelves
        self.endResetModel()

    def set_icon_color(self, color):
        self.icon_color = color
        # 只刷新图标颜色（DecorationRole），不做整体 model reset，
        # 避免主题切换时把用户已展开的层级重新收拢。
        def rec(parent_idx):
            rows = self.rowCount(parent_idx)
            if rows:
                top_left = self.index(0, 0, parent_idx)
                bottom_right = self.index(rows - 1, 0, parent_idx)
                self.dataChanged.emit(top_left, bottom_right, [Qt.DecorationRole])
                for r in range(rows):
                    rec(self.index(r, 0, parent_idx))
        rec(QModelIndex())

    def columnCount(self, parent=QModelIndex()):
        return 1

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            return len(self.roots)
        node = parent.internalPointer()
        return len(node.children) if isinstance(node, NovelNode) else 0

    def index(self, row, column, parent=QModelIndex()):
        if column != 0 or row < 0:
            return QModelIndex()
        if not parent.isValid():
            if row >= len(self.roots):
                return QModelIndex()
            return self.createIndex(row, 0, self.roots[row])
        p = parent.internalPointer()
        if not isinstance(p, NovelNode) or row >= len(p.children):
            return QModelIndex()
        return self.createIndex(row, 0, p.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if not isinstance(node, NovelNode) or node.parent is None:
            return QModelIndex()
        p = node.parent
        if p.parent is None:
            try:
                row = self.roots.index(p)
            except ValueError:
                return QModelIndex()
        else:
            row = p.parent.children.index(p)
        return self.createIndex(row, 0, p)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if not isinstance(node, NovelNode):
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return node.title
        if role == Qt.ToolTipRole:
            return node.title
        if role == Qt.DecorationRole:
            # 书架 / 书籍 / 顶层章节各自用专属图标；章节往下的层级只保留文字，不再要图标。
            if isinstance(node, NovelShelf):
                return ui_icons.icon("bookshelf", self.icon_color)
            if isinstance(node, NovelBook):
                return ui_icons.icon("book", self.icon_color)
            if isinstance(node.parent, NovelBook):
                return ui_icons.icon("paper", self.icon_color)
            return None
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        node = index.internalPointer()
        title = str(value).strip() or "未命名"
        node.title = title
        node.touch_chain()
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        return (
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable |
            Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        )

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [self.MIME]

    def mimeData(self, indexes):
        md = QMimeData()
        if indexes:
            node = indexes[0].internalPointer()
            if isinstance(node, NovelNode):
                md.setData(self.MIME, QByteArray(node.id.encode("utf-8")))
        return md

    def can_accept_drop(self, dragged, target_parent):
        # 书架：只能在最外层互相重新排序，不能被拖进任何节点内部。
        if isinstance(dragged, NovelShelf):
            return target_parent is None
        # 书籍：只能被拖到某个书架下面，不能置于最外层，也不能挂到别的书籍/章节下面。
        if isinstance(dragged, NovelBook):
            return isinstance(target_parent, NovelShelf)
        # 普通章节：不能被拖到最外层或书架下面，只能在某本书内部移动。
        if target_parent is None or isinstance(target_parent, NovelShelf):
            return False
        p = target_parent
        while p:
            if p is dragged:
                return False
            p = p.parent
        return True

    def dropMimeData(self, data, action, row, column, parent):
        if action != Qt.MoveAction or not data.hasFormat(self.MIME):
            return False
        try:
            node_id = bytes(data.data(self.MIME)).decode("utf-8")
        except Exception:
            return False
        dragged = self._find(node_id)
        if not dragged:
            return False

        target_parent = parent.internalPointer() if parent.isValid() else None
        if not self.can_accept_drop(dragged, target_parent):
            return False

        old_parent = dragged.parent
        old_list = self.roots if old_parent is None else old_parent.children
        old_row = old_list.index(dragged)

        # QTreeView 在 OnItem 情况下通常传 row=-1；此时作为目标子节点追加。
        if parent.isValid() and row < 0:
            new_list = target_parent.children
            new_parent = target_parent
            new_row = len(new_list)
        else:
            new_list = self.roots if target_parent is None else target_parent.children
            new_parent = target_parent
            new_row = len(new_list) if row < 0 else row

        if old_list is new_list and old_row < new_row:
            new_row -= 1

        if old_list is new_list and new_row == old_row:
            return False

        # 简化为 reset，避免复杂的 beginMoveRows 边界问题；
        # 数据规模为小说大纲时性能足够。
        self.beginResetModel()
        old_list.pop(old_row)
        if old_list is new_list and new_row > len(new_list):
            new_row = len(new_list)
        if new_list is old_list:
            new_row = max(0, min(new_row, len(new_list)))
        dragged.parent = new_parent
        new_list.insert(new_row, dragged)
        self.endResetModel()

        if new_parent is not None:
            new_parent.touch_chain()
        else:
            dragged.touch()
        return True

    def _find(self, node_id):
        def rec(nodes):
            for n in nodes:
                if n.id == node_id:
                    return n
                x = rec(n.children)
                if x:
                    return x
            return None
        return rec(self.roots)

    def index_for_node(self, node):
        if not node:
            return QModelIndex()
        if node.parent is None:
            try:
                row = self.roots.index(node)
            except ValueError:
                return QModelIndex()
            return self.createIndex(row, 0, node)
        try:
            row = node.parent.children.index(node)
        except ValueError:
            return QModelIndex()
        return self.createIndex(row, 0, node)

    def add_node_object(self, node, parent=None, row=None):
        """把一个已经构造好的节点（NovelShelf / NovelBook / NovelNode）插入树中。
        parent 为 None 表示插入到最外层（书架列表）。"""
        target = self.roots if parent is None else parent.children
        node.parent = parent
        if row is None:
            row = len(target)
        self.beginResetModel()
        target.insert(max(0, min(row, len(target))), node)
        self.endResetModel()
        if parent is not None:
            parent.touch_chain()
        return node

    def add_node(self, parent, title="未命名", row=None):
        """新建一个普通章节节点。parent 必须是一本书或另一个章节节点。"""
        return self.add_node_object(NovelNode(title), parent, row)

    def delete_node(self, node):
        p = node.parent
        target = self.roots if p is None else p.children
        if node not in target:
            return
        self.beginResetModel()
        target.remove(node)
        node.parent = None
        self.endResetModel()
        if p is not None:
            p.touch_chain()

    def move_node(self, node, direction):
        p = node.parent
        target = self.roots if p is None else p.children
        i = target.index(node)
        j = i + direction
        if j < 0 or j >= len(target):
            return False
        self.beginResetModel()
        target[i], target[j] = target[j], target[i]
        self.endResetModel()
        if p is not None:
            p.touch_chain()
        else:
            node.touch()
        return True

    def outdent_node(self, node):
        """把普通章节节点提升一级：变成其上级节点的同级节点，插入在
        上级节点之后。上级已经是书籍（即节点本身已是顶层章节）时无法
        再提升——这是弥补拖拽只能靠鼠标精确落点、拖成子层级后很难再
        拖回同级的问题，提供一个确定可靠的操作方式。"""
        p = node.parent
        if p is None or isinstance(p, (NovelBook, NovelShelf)):
            return False
        grandparent = p.parent
        old_list = p.children
        if node not in old_list:
            return False
        new_list = self.roots if grandparent is None else grandparent.children
        self.beginResetModel()
        old_list.remove(node)
        node.parent = grandparent
        new_list.insert(new_list.index(p) + 1, node)
        self.endResetModel()
        p.touch_chain()
        if grandparent is not None:
            grandparent.touch_chain()
        return True

    def indent_node(self, node):
        """把普通章节节点降低一级：变成它前一个同级节点的子节点（追加
        到其子节点末尾）。没有前一个同级节点时无法降级。"""
        p = node.parent
        if p is None:
            return False
        siblings = p.children
        if node not in siblings:
            return False
        i = siblings.index(node)
        if i == 0:
            return False
        new_parent = siblings[i - 1]
        self.beginResetModel()
        siblings.pop(i)
        node.parent = new_parent
        new_parent.children.append(node)
        self.endResetModel()
        p.touch_chain()
        new_parent.touch_chain()
        return True


class SettingsDialog(QDialog):
    """排版/写作设置。使用独立的“应用”按钮，避免用户误以为点击设置没有反应。"""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("InkTree 设置")
        self.setMinimumSize(620, 500)
        self.resize(680, 560)
        # 字体样式现在由工具栏的字体下拉框管理，这里只保留原值，避免点击"确定"时被覆盖回默认字体。
        self._font = settings.get("font", "Microsoft YaHei")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        title = QLabel("排版与写作设置")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # 排版
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(16)
        form.setHorizontalSpacing(22)

        self.size_combo = QComboBox()
        for x in [12, 13, 14, 15, 16, 17, 18, 20]:
            self.size_combo.addItem(f"{x} pt", x)
        idx = self.size_combo.findData(int(settings.get("font_size", 15)))
        self.size_combo.setCurrentIndex(max(0, idx))
        form.addRow("字号", self.size_combo)

        self.line_combo = QComboBox()
        for x in [1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2]:
            self.line_combo.addItem(f"{x:.1f} 倍", x)
        idx = self.line_combo.findData(float(settings.get("line_height", 1.5)))
        self.line_combo.setCurrentIndex(max(0, idx))
        form.addRow("行高", self.line_combo)

        self.spacing_combo = QComboBox()
        for x in [0, 4, 8, 12, 16, 20]:
            self.spacing_combo.addItem(f"{x} px", x)
        idx = self.spacing_combo.findData(int(settings.get("paragraph_spacing", 4)))
        self.spacing_combo.setCurrentIndex(max(0, idx))
        form.addRow("段落间距", self.spacing_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(600, 1800)
        self.width_spin.setSingleStep(40)
        self.width_spin.setValue(int(settings.get("editor_width", 1400)))
        self.width_spin.setSuffix(" px")
        form.addRow("正文宽度", self.width_spin)

        hint = QLabel("推荐：微软雅黑负责界面与正文；英文会优先使用 Segoe UI。")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        form.addRow("", hint)
        tabs.addTab(page, "排版")

        # 写作
        writing = QWidget()
        wf = QFormLayout(writing)
        wf.setContentsMargins(18, 18, 18, 18)
        wf.setVerticalSpacing(16)
        self.auto_number = QCheckBox("自动生成层级编号")
        self.auto_number.setChecked(bool(settings.get("auto_number", False)))
        wf.addRow("章节编号", self.auto_number)

        self.number_mode = QComboBox()
        self.number_mode.addItem("第 1 级 / 第 1.1 级", "chapter")
        self.number_mode.addItem("1 / 1.1 / 1.1.1", "numeric")
        idx = self.number_mode.findData(settings.get("number_mode", "chapter"))
        self.number_mode.setCurrentIndex(max(0, idx))
        wf.addRow("编号样式", self.number_mode)

        hint2 = QLabel("节点标题完全自由：可以写“序章：雨夜”“Part I”“Chapter Zero”“沈城·旧案”，不会被软件改写。")
        hint2.setWordWrap(True)
        hint2.setObjectName("DialogHint")
        wf.addRow("", hint2)
        tabs.addTab(writing, "写作")

        buttons = QDialogButtonBox()
        self.apply_btn = buttons.addButton("应用", QDialogButtonBox.ApplyRole)
        self.ok_btn = buttons.addButton("确定", QDialogButtonBox.AcceptRole)
        self.cancel_btn = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.apply_btn.clicked.connect(self._apply_preview)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        root.addWidget(buttons)

    def values(self):
        return {
            "font": self._font,
            "font_size": self.size_combo.currentData(),
            "line_height": self.line_combo.currentData(),
            "paragraph_spacing": self.spacing_combo.currentData(),
            "editor_width": self.width_spin.value(),
            "auto_number": self.auto_number.isChecked(),
            "number_mode": self.number_mode.currentData(),
        }

    def _apply_preview(self):
        # 由主窗口在接受对话框后统一应用；这里让“应用”按钮有明确反馈。
        QMessageBox.information(self, "设置已修改", "点击“确定”后会立即应用并自动保存。")


class GlobalSearchDialog(QDialog):
    def __init__(self, books, parent=None):
        super().__init__(parent)
        self.books = books
        self.setWindowTitle("全局搜索")
        self.resize(720, 520)
        root = QVBoxLayout(self)

        self.query = QLineEdit()
        self.query.setPlaceholderText("搜索所有书籍的标题和正文……")
        root.addWidget(self.query)

        self.results = QListWidget()
        root.addWidget(self.results, 1)

        self.query.textChanged.connect(self.search)
        self.results.itemDoubleClicked.connect(self.accept)
        self.search("")

    def search(self, text):
        self.results.clear()
        q = text.strip().lower()
        if not q:
            return

        for book in self.books:
            def rec(nodes, path):
                for node in nodes:
                    current_path = path + [node.title]
                    plain = html_to_plain(node.content)
                    hay = (node.title + "\n" + plain).lower()
                    if q in hay:
                        preview = plain.replace("\n", " ").strip()
                        if len(preview) > 100:
                            preview = preview[:100] + "…"
                        label = f"【{book.name}】  {' / '.join(current_path)}"
                        if preview:
                            label += f"\n    {preview}"
                        item = QListWidgetItem(label)
                        item.setData(Qt.UserRole, (book.id, node.id))
                        self.results.addItem(item)
                    rec(node.children, current_path)
            rec(book.tree, [])


def html_to_plain(content):
    if not content:
        return ""
    doc = QTextDocument()
    doc.setHtml(content)
    return doc.toPlainText()


_RICHTEXT_TAG_RE = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(/?)>')
_RICHTEXT_STYLE_ATTR_RE = re.compile(r'\sstyle="([^"]*)"')
_RICHTEXT_CLASS_ATTR_RE = re.compile(r'\sclass="([^"]*)"')


def compact_richtext_html(html_str):
    """把 QTextEdit.toHtml() 生成的富文本 HTML 瘦身后再保存。

    QTextEdit.toHtml() 会给几乎每一个 <p>/<span> 都重复内联一份完整的
    style="..."（字体、字号、颜色、行高、边距等），几万字的稿子里这些
    重复样式能占到文件体积的 80% 以上。这里把出现次数大于一次的 style
    字符串提取成共享的 CSS class（写进 <head> 的 <style> 里），元素上
    只留一个 class="cN" 引用；只出现一次的 style 保持原样内联，没必要
    额外建一个 class。元素本来就带的 class（例如勾选框列表项）会被保留，
    新 class 追加在后面。

    重新用 QTextEdit/QTextDocument.setHtml() 读回时，Qt 会把 class 解析
    成和原来完全一样的段落/字符格式，所以读写效果不受影响，只是保存到
    磁盘上的体积明显变小。"""
    if not html_str:
        return html_str

    freq = {}
    for m in _RICHTEXT_TAG_RE.finditer(html_str):
        sm = _RICHTEXT_STYLE_ATTR_RE.search(m.group(2))
        if sm:
            val = sm.group(1).strip()
            if val:
                freq[val] = freq.get(val, 0) + 1

    style_to_class = {}
    for val, count in freq.items():
        if count > 1:
            style_to_class[val] = f"c{len(style_to_class)}"

    if not style_to_class:
        return html_str

    def replace_tag(m):
        tag, attrs, selfclose = m.group(1), m.group(2), m.group(3)
        sm = _RICHTEXT_STYLE_ATTR_RE.search(attrs)
        if not sm:
            return m.group(0)
        cls = style_to_class.get(sm.group(1).strip())
        if cls is None:
            return m.group(0)
        new_attrs = attrs[:sm.start()] + attrs[sm.end():]
        cm = _RICHTEXT_CLASS_ATTR_RE.search(new_attrs)
        if cm:
            merged = f'{cm.group(1)} {cls}'.strip()
            new_attrs = new_attrs[:cm.start()] + f' class="{merged}"' + new_attrs[cm.end():]
        else:
            new_attrs = new_attrs + f' class="{cls}"'
        return f'<{tag}{new_attrs}{"/" if selfclose else ""}>'

    new_html = _RICHTEXT_TAG_RE.sub(replace_tag, html_str)

    css_rules = "\n".join(f".{cls} {{{val}}}" for val, cls in style_to_class.items())
    if "<style" in new_html:
        new_html = re.sub(
            r'(</style>)',
            lambda m: css_rules + "\n" + m.group(1),
            new_html, count=1,
        )
    elif "<head>" in new_html:
        new_html = new_html.replace(
            "<head>", f'<head><style type="text/css">\n{css_rules}\n</style>', 1
        )
    else:
        new_html = re.sub(
            r'(<html[^>]*>)',
            lambda m: m.group(1) + f'<head><style type="text/css">\n{css_rules}\n</style></head>',
            new_html, count=1,
        )
    return new_html


class NovelWriter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = DataManager()
        self.current_book = None
        self.current_node = None
        self.loading_content = False
        # 记录"这本书这次打开/切换后，是否已经完整跑过一遍全书字数统计"
        # ——见 update_all_stats() 里的说明。
        self._stats_warm_book_id = None
        self.dirty = False
        self.last_saved_at = None
        self.session_start_date = date.today().isoformat()
        self.session_start_words = 0

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1180, 760)
        self.resize(1680, 1000)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(1500)
        self.save_timer.timeout.connect(self.autosave_tick)
        self.save_timer.start()

        # editor_changed() 里“toHtml() 序列化 + 全书字数递归统计”这部分
        # 开销较大，每敲一个字都同步跑一遍会导致长文档打字卡顿。这里用
        # 300ms 防抖定时器把这部分延迟到停止输入后再执行；标记“未保存”
        # 这类轻量操作仍然立即完成，不受防抖影响。自动保存用独立的 1.5
        # 秒定时器，且落盘时会直接从编辑器重新取 toHtml()，不依赖这个
        # 防抖定时器是否已经跑过，所以不影响自动保存的及时性。
        self.editor_change_timer = QTimer(self)
        self.editor_change_timer.setSingleShot(True)
        self.editor_change_timer.setInterval(300)
        self.editor_change_timer.timeout.connect(self._apply_editor_changes)
        self._pending_stats_node = None

        self.build_ui()
        self.apply_theme()
        # 用 QTimer.singleShot(0, ...) 把"恢复上次的标签页/最近书籍"这一步
        # 延后到窗口真正显示出来之后再执行（0ms 也是延后一轮事件循环，
        # 不会有肉眼可见的延迟）。之前直接在 __init__ 里同步调用，标签页
        # 是在主窗口第一次显示之前就加到 QTabBar 上的——这样加出来的标签
        # 页会出现"加上了但画不出来，要等再开一个新标签页触发一次重新布局
        # 才会显示"的问题（这是 Qt 对"还没显示过的窗口"里控件的一个常见
        # 坑：内容加进去了，但要等窗口真正 show() 过一次、拿到有效的绘制
        # 上下文之后才会正常刷新）。延后到窗口显示之后再加标签页，就跟用户
        # 手动打开一个新标签页是同一种时机，不会再有这个问题。
        QTimer.singleShot(0, self.load_recent_book)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左右整体用一个水平分割器：左侧层级结构直接顶到窗口最上方，
        # 顶部工具条（导出 / 主题）只属于右侧编辑区域，不再横跨全宽、
        # 也就不会在层级结构上方留出大片空白。
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)
        self.main_splitter = splitter
        self.sidebar_collapsed = False
        self._sidebar_expanded_width = 380

        # ---------- 左侧：书架 / 书籍 / 章节层级 ----------
        self.side = QFrame()
        self.side.setObjectName("Sidebar")
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(12, 12, 12, 10)
        sl.setSpacing(10)

        self._themed_buttons = []

        # 折叠 / 展开层级结构的按钮，单独一行、固定在层级结构最上方，
        # 不和下面的树/搜索框放在同一个可隐藏容器里，
        # 这样无论展开还是折叠，按钮永远钉在顶端，不会被剩余空间挤到中间。
        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("SidebarToggle")
        self.sidebar_toggle_btn.setIconSize(QSize(20, 20))
        self.sidebar_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle_btn.clicked.connect(self.toggle_sidebar)
        sl.addWidget(self.sidebar_toggle_btn, 0, Qt.AlignLeft | Qt.AlignTop)

        # 树 + 搜索框整体放进一个容器里，折叠时一起隐藏；
        # 折叠按钮在这个容器之外，因此始终保持在最顶端。
        self.tree_content = QWidget()
        self.tree_content.setObjectName("SidebarTreeContent")
        tc = QVBoxLayout(self.tree_content)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(10)

        self.tree_model = NovelTreeModel(self)
        self.tree_model.set_roots(self.data.shelves)
        self.tree = QTreeView()
        self.tree.setModel(self.tree_model)
        # 拖拽等操作内部用 beginResetModel/endResetModel 刷新整棵树，
        # 会导致视图丢失展开状态、全部折叠收拢；这里在重置前后自动
        # 记录/恢复各节点的展开状态，操作后层级维持原本打开的样子。
        self.tree_model.modelAboutToBeReset.connect(self._snapshot_tree_expansion)
        self.tree_model.modelReset.connect(self._restore_tree_expansion)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(28)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        self.tree.selectionModel().currentChanged.connect(self.tree_selection)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        tc.addWidget(self.tree, 1)

        # “搜索全部书架/书籍”原来在最上方，现在挪到层级结构底部，
        # 原来底部的操作提示文字直接去掉。
        self.tree_search = QLineEdit()
        self.tree_search.setPlaceholderText("搜索全部书架/书籍…")
        self.tree_search.textChanged.connect(self.filter_tree)
        tc.addWidget(self.tree_search)

        sl.addWidget(self.tree_content, 1)

        # 折叠状态下层级栏最窄只收到这个宽度（正好容纳折叠按钮），
        # 展开时没有上限，可以随意拖拽分割条。
        self.side.setMinimumWidth(self.SIDEBAR_COLLAPSED_WIDTH)

        splitter.addWidget(self.side)

        # ---------- 右侧：顶部工具条 + 章节标签页 + 编辑器工具栏 + 正文 ----------
        editor_panel = QFrame()
        editor_panel.setObjectName("EditorPanel")
        ep = QVBoxLayout(editor_panel)
        ep.setContentsMargins(0, 0, 0, 0)
        ep.setSpacing(0)

        # 顶部只保留一栏：左边是章节标签页（Chrome / Edge 风格，
        # 可同时打开多个章节来回切换），右边是“导出 / 主题”按钮，
        # 和下面单独一行的编辑器工具栏一起，总共只有两栏。
        self.top = QFrame()
        self.top.setObjectName("TopBar")
        tl = QHBoxLayout(self.top)
        tl.setContentsMargins(6, 8, 14, 0)
        tl.setSpacing(10)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("ChapterTabBar")
        self.tab_bar.setExpanding(False)
        self.tab_bar.setTabsClosable(False)  # 关闭按钮改用自带 x.svg 图标的自定义按钮
        self.tab_bar.setMovable(True)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setElideMode(Qt.ElideRight)
        self.tab_bar.currentChanged.connect(self.tab_changed)
        tl.addWidget(self.tab_bar, 1, Qt.AlignBottom)

        # 书架 / 书籍的新建、重命名、删除都挪到了左侧大纲树里（跟章节一样右键操作），
        # 顶部栏只保留“导出”和“主题”。
        def top_button(text, slot, icon_name):
            b = QPushButton(text)
            b.setObjectName("ExportButton")
            b.setIcon(ui_icons.icon(icon_name, self._icon_color()))
            b.setIconSize(QSize(18, 18))
            b.clicked.connect(slot)
            tl.addWidget(b, 0, Qt.AlignVCenter)
            self._themed_buttons.append((b, icon_name))
            return b

        top_button("TXT", self.export_txt, "save")
        top_button("EPUB", self.export_epub, "save")

        self.theme_combo = RoundedComboBox()
        self.theme_combo.setIconSize(QSize(18, 18))
        self.theme_combo.addItem(ui_icons.icon("theme-day", self._icon_color()), "白天", "day")
        self.theme_combo.addItem(ui_icons.icon("theme-night", self._icon_color()), "黑夜", "night")
        self.theme_combo.addItem(ui_icons.icon("theme-green", self._icon_color()), "护眼", "green")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.data.settings.get("theme", "day"))))
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        tl.addWidget(self.theme_combo, 0, Qt.AlignVCenter)
        ep.addWidget(self.top)

        self.toolbar = QToolBar()
        self.toolbar.setObjectName("EditorToolbar")
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        ep.addWidget(self.toolbar)
        self.make_toolbar()

        paper = QFrame()
        paper.setObjectName("PaperArea")
        pl = QVBoxLayout(paper)
        pl.setContentsMargins(56, 28, 56, 36)
        self.editor_title = QLabel("未选择章节")
        self.editor_title.setObjectName("EditorTitle")
        pl.addWidget(self.editor_title)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setUndoRedoEnabled(True)
        self.editor.setPlaceholderText("开始写作……")
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self.show_editor_context_menu)
        self.editor.textChanged.connect(self.editor_changed)
        self.editor.cursorPositionChanged.connect(self.update_cursor)
        self.editor.cursorPositionChanged.connect(self.update_toolbar_state)
        self.editor.installEventFilter(self)
        self.editor.selectionChanged.connect(self.update_toolbar_state)
        self.editor.undoAvailable.connect(self.action_undo.setEnabled)
        self.editor.redoAvailable.connect(self.action_redo.setEnabled)
        self.action_undo.setEnabled(False)
        self.action_redo.setEnabled(False)
        pl.addWidget(self.editor, 1)
        ep.addWidget(paper, 1)
        splitter.addWidget(editor_panel)
        splitter.setSizes([380, 1300])
        splitter.setStretchFactor(1, 1)

        self._update_sidebar_toggle_icon()

        status = QStatusBar()
        self.setStatusBar(status)
        self.save_state = QLabel("● 已保存")
        self.word_label = QLabel("本章 0 · 今日 0 · 全文 0")
        self.node_status = QLabel("未选择节点")
        self.cursor_label = QLabel("行 1 · 列 1")
        status.addWidget(self.save_state)
        status.addWidget(self.word_label)
        status.addWidget(self.node_status)
        status.addPermanentWidget(self.cursor_label)

    # 主题名 -> 图标着色（跟随各主题 QSS 里工具栏文字/图标的颜色）
    THEME_ICON_COLORS = {
        "day": "#222222",
        "night": "#F3F4F6",
        "green": "#2C3E50",
    }

    # 层级结构收起后的细长条宽度
    SIDEBAR_COLLAPSED_WIDTH = 56

    def _icon_color(self):
        theme = self.data.settings.get("theme", "day")
        return self.THEME_ICON_COLORS.get(theme, "#222222")

    def _refresh_themed_icons(self):
        """主题切换后，重新给工具栏图标、顶部按钮、主题下拉框、大纲树图标上色。"""
        color = self._icon_color()
        for action, icon_name in getattr(self, "_toolbar_icon_actions", []):
            action.setIcon(ui_icons.icon(icon_name, color))
        for button, icon_name in getattr(self, "_themed_buttons", []):
            button.setIcon(ui_icons.icon(icon_name, color))
        for label, icon_name in getattr(self, "_themed_icon_labels", []):
            label.setPixmap(ui_icons.icon(icon_name, color).pixmap(18, 18))
        for combo in getattr(self, "_themed_combos", []):
            combo.set_arrow_color(color)
        theme_combo_icons = ["theme-day", "theme-night", "theme-green"]
        if hasattr(self, "theme_combo"):
            for i, icon_name in enumerate(theme_combo_icons):
                self.theme_combo.setItemIcon(i, ui_icons.icon(icon_name, color))
        if hasattr(self, "tree_model"):
            self.tree_model.set_icon_color(color)
        if hasattr(self, "sidebar_toggle_btn"):
            self._update_sidebar_toggle_icon()
        if hasattr(self, "tab_bar"):
            for i in range(self.tab_bar.count()):
                btn = self.tab_bar.tabButton(i, QTabBar.RightSide)
                if isinstance(btn, QToolButton):
                    btn.setIcon(ui_icons.icon("tab-close", color))

    # ---------- 层级结构折叠 / 展开 ----------
    def _update_sidebar_toggle_icon(self):
        color = self._icon_color()
        if self.sidebar_collapsed:
            self.sidebar_toggle_btn.setIcon(ui_icons.icon("sidebar-expand", color))
            self.sidebar_toggle_btn.setToolTip("展开层级结构")
        else:
            self.sidebar_toggle_btn.setIcon(ui_icons.icon("sidebar-collapse", color))
            self.sidebar_toggle_btn.setToolTip("收起层级结构")

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        sizes = self.main_splitter.sizes()
        start_width = sizes[0] if sizes else self.side.width()

        if self.sidebar_collapsed:
            if start_width > self.SIDEBAR_COLLAPSED_WIDTH:
                self._sidebar_expanded_width = start_width
            end_width = self.SIDEBAR_COLLAPSED_WIDTH
            # 收起时先把树/搜索框隐藏，避免在变窄的过程中被挤压变形；
            # 右侧编辑区域会随分割条宽度的动画一起自然左移填满空间。
            self.tree_content.setVisible(False)
        else:
            end_width = self._sidebar_expanded_width or 380

        self._animate_sidebar_width(start_width, end_width)
        self._update_sidebar_toggle_icon()

    def _animate_sidebar_width(self, start_width, end_width):
        """用一个宽度动画滑动分割条，制造侧栏收起/展开、右侧内容跟着滑入滑出的效果。"""
        anim = QVariantAnimation(self)
        anim.setStartValue(int(start_width))
        anim.setEndValue(int(end_width))
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def apply_width(value):
            w = int(value)
            total = max(1, self.main_splitter.width())
            self.main_splitter.setSizes([w, max(1, total - w)])

        def on_finished():
            if not self.sidebar_collapsed:
                self.tree_content.setVisible(True)
            self._sidebar_anim = None

        anim.valueChanged.connect(apply_width)
        anim.finished.connect(on_finished)
        # 持有引用，防止动画对象在播放过程中被垃圾回收。
        self._sidebar_anim = anim
        anim.start()

    def make_toolbar(self):
        self._toolbar_icon_actions = []

        def add_action(label, slot, icon_name, shortcut=None, tip=""):
            action = QAction(ui_icons.icon(icon_name, self._icon_color()), label, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.setToolTip(tip if tip else label)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
            self._toolbar_icon_actions.append((action, icon_name))
            return action

        self.action_bold = add_action("加粗", self.bold, "bold", QKeySequence.Bold, "加粗  Ctrl+B")
        self.action_italic = add_action("斜体", self.italic, "italic", QKeySequence.Italic, "斜体  Ctrl+I")
        self.action_underline = add_action("下划线", self.underline, "underline", QKeySequence.Underline, "下划线  Ctrl+U")
        self.toolbar.addSeparator()
        add_action("引用", self.quote, "quote", tip="引用块")
        add_action("无序列表", self.bullet, "bullet-list", tip="无序列表")
        add_action("有序列表", self.numbered, "number-list", tip="有序列表")

        self.toolbar.addSeparator()

        # 正文字体样式 / 字号：直接在工具栏选择，不再使用 H1/H2/H3。
        self._themed_icon_labels = getattr(self, "_themed_icon_labels", [])

        self.font_family_combo = FontComboBox()
        self.font_family_combo.setObjectName("FontFamilyCombo")
        self._populate_font_families()
        self.font_family_combo.setMinimumWidth(150)
        self.font_family_combo.setToolTip("字体")
        self.font_family_combo.currentTextChanged.connect(self.toolbar_font_family_changed)
        self.toolbar.addWidget(self.font_family_combo)
        self._themed_combos = getattr(self, "_themed_combos", [])
        self._themed_combos.append(self.font_family_combo)

        self.font_size_combo = FontComboBox()
        self.font_size_combo.setObjectName("FontSizeCombo")
        self.font_size_combo.addItems(["12", "13", "14", "15", "16", "17", "18", "20", "22", "24", "28", "32"])
        self.font_size_combo.setMinimumWidth(78)
        self.font_size_combo.setCurrentText(str(self.data.settings.get("font_size", 15)))
        self.font_size_combo.setToolTip("字号（pt）")
        self.font_size_combo.currentTextChanged.connect(self.toolbar_font_size_changed)
        self.toolbar.addWidget(self.font_size_combo)
        self._themed_combos.append(self.font_size_combo)

        self.line_height_combo = FontComboBox()
        self.line_height_combo.setObjectName("LineHeightCombo")
        self.line_height_combo.addItems(["1.2", "1.4", "1.5", "1.6", "1.8", "2.0", "2.2"])
        self.line_height_combo.setMinimumWidth(78)
        self.line_height_combo.setCurrentText(f'{float(self.data.settings.get("line_height", 1.5)):.1f}')
        self.line_height_combo.setToolTip("行间距（倍）")
        self.line_height_combo.currentTextChanged.connect(self.toolbar_line_height_changed)
        self.toolbar.addWidget(self.line_height_combo)
        self._themed_combos.append(self.line_height_combo)

        self.toolbar.addSeparator()
        add_action("左对齐", lambda: self.alignment(Qt.AlignLeft), "align-left", tip="左对齐")
        add_action("居中", lambda: self.alignment(Qt.AlignCenter), "align-center", tip="居中")
        add_action("右对齐", lambda: self.alignment(Qt.AlignRight), "align-right", tip="右对齐")
        self.toolbar.addSeparator()
        self.action_undo = add_action("撤销", lambda: self.editor.undo(), "undo", QKeySequence.Undo, "撤销  Ctrl+Z")
        self.action_redo = add_action("重做", lambda: self.editor.redo(), "redo", QKeySequence.Redo, "重做  Ctrl+Shift+Z")
        add_action("清除格式", self.clear_format, "clear-format", tip="清除字符格式")

        # 把全局搜索也放进同一行工具栏，紧贴最右边，和其它按钮一样只显示图标。
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer.setAttribute(Qt.WA_TranslucentBackground, True)
        spacer.setStyleSheet("background: transparent;")
        self.toolbar.addWidget(spacer)
        add_action("全局搜索", self.global_search, "search", tip="全局搜索")

    def _populate_font_families(self):
        """读取电脑本机安装的字体，填充到字体样式下拉框。"""
        families = QFontDatabase.families()
        current = self.data.settings.get("font", "Microsoft YaHei")
        self.font_family_combo.blockSignals(True)
        self.font_family_combo.addItems(families)
        idx = self.font_family_combo.findText(current)
        if idx < 0:
            idx = 0
        self.font_family_combo.setCurrentIndex(max(0, idx))
        self.font_family_combo.blockSignals(False)

    def apply_theme(self):
        theme = self.data.settings.get("theme", "day")
        if theme == "night":
            self.setStyleSheet(self.qss_night())
        elif theme == "green":
            self.setStyleSheet(self.qss_green())
        else:
            self.setStyleSheet(self.qss_day())
        self._refresh_themed_icons()
        self.apply_editor_settings()
        self._refresh_editor_text_colors()

    def qss_day(self):
        # 注意：Qt Style Sheet 的 :not() 只支持伪状态（如 :hover），不支持像
        # QTextEdit 这样的类型选择器；"*:not(QTextEdit)" 这条规则其实从来没有
        # 生效过（Qt 会直接忽略这条选择器无法解析的规则）。真正的界面中文字体
        # 现在改为在 main() 里用 app.setFont(...) 统一设置——用控件字体继承来做，
        # 不经过样式表，就不会跟正文编辑器自己维护的字体/字号打架。
        #
        # 重要提醒：上面这几行必须写在 return 语句之前、作为真正的 Python 注释。
        # 之前的版本把这段说明文字直接写在了 return """ 之后——那个位置属于
        # 三引号字符串内部，Python 不会把 "#..." 当注释处理，而是原样当成
        # QSS 文本传给 setStyleSheet()。这几行文字里带有中文冒号、括号等
        # 字符，会把 Qt 的 CSS 解析器搞坏，导致下面这条给工具栏下拉框单独
        # 设置字号的规则、乃至后续的样式规则全部失效——这正是"中文界面
        # 变成宋体"的真正原因（并非 app.setFont 没生效，而是 QSS 里一段
        # 伪装成注释的文字把解析器带偏了）。
        return """
        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo, #ExportButton { font-size:16px; }
        QMainWindow,QWidget { background:#FFFFFF; color:#222222; }
        #TopBar,#Sidebar,QToolBar,QStatusBar { background:#F7F8FA; }
        #TopBar { border-bottom:1px solid #E3E6EA; }
        #Sidebar { border-right:1px solid #E3E6EA; }
        #SidebarTreeContent { background:transparent; }
        #EditorPanel,#PaperArea { background:#FFFFFF; }
        #EditorTitle { color:#6B7280; font-size:32px; font-weight:700; padding:6px 0 16px 0; }
        QTreeView { background:#F7F8FA; border:none; outline:none; color:#4A4F58; font-size:16px; }
        QTreeView::item { height:44px; padding:6px 10px; border-radius:6px; }
        QTreeView::item:hover { background:#EEF1F5; }
        QTreeView::item:selected { background:#BFD3F2; color:#222222; }
        QLineEdit,QComboBox,QPushButton,QSpinBox {
            background:#FFFFFF; color:#222222; border:1px solid #D9DEE5;
            border-radius:7px; padding:8px 11px; min-height:22px;
        }
        QPushButton:hover,QToolButton:hover { background:#EEF1F5; }
        QToolBar { border:none; border-bottom:1px solid #E3E6EA; spacing:5px; padding:7px 12px; }
        QToolButton { background:transparent; color:#222222; border-radius:6px; padding:7px 9px; }
        QToolButton:hover { background:#E9EDF3; }
        QToolButton:checked { background:#BFD3F2; }
        QTextEdit { background:transparent; color:#222222; border:none;
            selection-background-color:#BFD3F2; selection-color:#222222;
        }
        #DialogTitle { font-size:22px; font-weight:650; }
        #DialogHint { color:#667085; line-height:1.5; }
        QTabWidget::pane { border:1px solid #E3E6EA; border-radius:7px; }
        QTabBar::tab { padding:9px 18px; }
        QTabBar::tab:selected { background:#E9EDF3; border-radius:6px; }
        QSplitter::handle { background:#E3E6EA; width:4px; }
        QMenu { background:#FFFFFF; color:#222222; border:1px solid #D9DEE5; border-radius:10px; }
        QMenu::item { padding:10px 30px 10px 18px; margin:2px 4px; border-radius:5px; }
        QMenu::item:selected { background:#BFD3F2; color:#222222; }

        QComboBox {
            background: transparent;
            border: 1px solid #D5D9E0;
            border-radius: 6px;
            padding: 6px 30px 6px 10px;
            min-height: 28px;
        }
        QComboBox:hover {
            border-color: #AEB7C5;
        }
        QComboBox:focus {
            border-color: #9AA9BF;
        }
        QComboBox::drop-down {
            width: 26px;
            border: none;
            background: transparent;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }
        QComboBox::down-arrow {
            width: 8px;
            height: 8px;
        }
        QComboBox QAbstractItemView {
            background: #FFFFFF;
            color: #222222;
            border: 1px solid #D5D9E0;
            border-radius: 6px;
            padding: 5px;
            outline: none;
            selection-background-color: #BFD3F2;
            selection-color: #222222;
        }

        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo {
            background:#FFFFFF; color:#222222; border:1px solid #D9DEE5;
            border-radius:7px; padding:8px 28px 8px 11px; min-height:22px;
        }
        #FontSizeCombo:hover, #LineHeightCombo:hover, #FontFamilyCombo:hover { border-color:#AEB7C5; }
        #FontSizeCombo:focus, #LineHeightCombo:focus, #FontFamilyCombo:focus { border-color:#9AA9BF; }
        #FontSizeCombo::drop-down, #LineHeightCombo::drop-down, #FontFamilyCombo::drop-down {
            width: 24px; border: none; background: transparent;
        }
        #FontSizeCombo::down-arrow, #LineHeightCombo::down-arrow, #FontFamilyCombo::down-arrow {
            width: 0px; height: 0px; image: none;
        }

        #SidebarToggle {
            background: transparent; border: none; border-radius:6px;
            padding: 6px; min-height:0; min-width:0;
        }
        #SidebarToggle:hover { background:#EEF1F5; }

        #ChapterTabBar { background:transparent; }
        #ChapterTabBar::tab {
            background:#E3E8EF; color:#4A4F58; border:1px solid transparent;
            border-top-left-radius:9px; border-top-right-radius:9px;
            padding:13px 10px 13px 16px; margin:6px 1px 0 1px;
            min-width:130px; max-width:240px; min-height:20px;
        }
        #ChapterTabBar::tab:!selected { border-right:1px solid #CBD3DD; }
        #ChapterTabBar::tab:selected {
            background:#FFFFFF; color:#151719;
            border:1px solid #D9DEE5; border-bottom:none;
            border-top:2px solid #3B6FE0; padding-top:12px;
        }
        #ChapterTabBar::tab:!selected:hover { background:#CFD8E4; border-right-color:transparent; }
        #ChapterTabBar::tab:selected:hover { background:#FFFFFF; }
        #TabCloseButton {
            background:transparent; border:none; border-radius:6px;
            padding:2px; margin-left:6px;
        }
        #TabCloseButton:hover { background:#C6D0DE; }
        #TabCloseButton:pressed { background:#AEBBCC; }

        QScrollBar:vertical { width:10px; background:#F7F8FA; }
        QScrollBar::handle:vertical { background:#C8CED8; border-radius:5px; min-height:30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px; width: 0px; background: none; border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none; border: none;
        }
        """

    def qss_night(self):
        # 见 qss_day() 开头的说明：这段文字必须是 Python 注释，不能写在
        # return """ 之后（那样会被当成 QSS 内容，破坏下面的样式解析）。
        return """
        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo, #ExportButton { font-size:16px; }
        QMainWindow,QWidget { background:#111318; color:#F3F4F6; }
        #TopBar,#Sidebar,QToolBar,QStatusBar { background:#171A21; }
        #TopBar { border-bottom:1px solid #2A303B; }
        #Sidebar { border-right:1px solid #2A303B; }
        #SidebarTreeContent { background:transparent; }
        #EditorPanel,#PaperArea { background:#111318; }
        #EditorTitle { color:#AAB2C0; font-size:32px; font-weight:700; padding:6px 0 16px 0; }
        QTreeView { background:#171A21; border:none; outline:none; color:#FFFFFF; font-size:16px; }
        QTreeView::item { height:44px; padding:6px 10px; border-radius:6px; }
        QTreeView::item:hover { background:#242A34; }
        QTreeView::item:selected { background:#4B566B; color:#FFFFFF; }
        QLineEdit,QComboBox,QPushButton,QSpinBox {
            background:#1C2028; color:#F3F4F6; border:1px solid #303744;
            border-radius:7px; padding:8px 11px; min-height:22px;
        }
        QPushButton:hover,QToolButton:hover { background:#282F3A; }
        QToolBar { border:none; border-bottom:1px solid #2A303B; spacing:5px; padding:7px 12px; }
        QToolButton { background:transparent; color:#F3F4F6; border-radius:6px; padding:7px 9px; }
        QToolButton:hover { background:#282F3A; }
        QToolButton:checked { background:#4B566B; }
        QTextEdit { background:transparent; color:#F3F4F6; border:none;
            selection-background-color:#4B566B; selection-color:#FFFFFF;
        }
        #DialogTitle { font-size:22px; font-weight:650; }
        #DialogHint { color:#AAB2C0; }
        QTabWidget::pane { border:1px solid #303744; border-radius:7px; }
        QTabBar::tab { padding:9px 18px; color:#DDE2EA; }
        QTabBar::tab:selected { background:#282F3A; border-radius:6px; }
        QSplitter::handle { background:#2A303B; width:4px; }
        QMenu { background:#171A21; color:#F3F4F6; border:1px solid #303744; border-radius:10px; }
        QMenu::item { padding:10px 30px 10px 18px; margin:2px 4px; border-radius:5px; }
        QMenu::item:selected { background:#4B566B; color:#FFFFFF; }

        QComboBox {
            background: transparent;
            border: 1px solid #D5D9E0;
            border-radius: 6px;
            padding: 6px 30px 6px 10px;
            min-height: 28px;
        }
        QComboBox:hover {
            border-color: #AEB7C5;
        }
        QComboBox:focus {
            border-color: #9AA9BF;
        }
        QComboBox::drop-down {
            width: 26px;
            border: none;
            background: transparent;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }
        QComboBox::down-arrow {
            width: 8px;
            height: 8px;
        }
        QComboBox QAbstractItemView {
            background: #171A21;
            color: #F3F4F6;
            border: 1px solid #303744;
            border-radius: 6px;
            padding: 5px;
            outline: none;
            selection-background-color: #4B566B;
            selection-color: #FFFFFF;
        }

        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo {
            background:#1C2028; color:#F3F4F6; border:1px solid #303744;
            border-radius:7px; padding:8px 28px 8px 11px; min-height:22px;
        }
        #FontSizeCombo:hover, #LineHeightCombo:hover, #FontFamilyCombo:hover { border-color:#AEB7C5; }
        #FontSizeCombo:focus, #LineHeightCombo:focus, #FontFamilyCombo:focus { border-color:#9AA9BF; }
        #FontSizeCombo::drop-down, #LineHeightCombo::drop-down, #FontFamilyCombo::drop-down {
            width: 24px; border: none; background: transparent;
        }
        #FontSizeCombo::down-arrow, #LineHeightCombo::down-arrow, #FontFamilyCombo::down-arrow {
            width: 0px; height: 0px; image: none;
        }

        #SidebarToggle {
            background: transparent; border: none; border-radius:6px;
            padding: 6px; min-height:0; min-width:0;
        }
        #SidebarToggle:hover { background:#282F3A; }

        #ChapterTabBar { background:transparent; }
        #ChapterTabBar::tab {
            background:#242A34; color:#AAB2C0; border:1px solid transparent;
            border-top-left-radius:9px; border-top-right-radius:9px;
            padding:13px 10px 13px 16px; margin:6px 1px 0 1px;
            min-width:130px; max-width:240px; min-height:20px;
        }
        #ChapterTabBar::tab:!selected { border-right:1px solid #333B48; }
        #ChapterTabBar::tab:selected {
            background:#111318; color:#F3F4F6;
            border:1px solid #2A303B; border-bottom:none;
            border-top:2px solid #5B8DEF; padding-top:12px;
        }
        #ChapterTabBar::tab:!selected:hover { background:#323A48; border-right-color:transparent; }
        #ChapterTabBar::tab:selected:hover { background:#111318; }
        #TabCloseButton {
            background:transparent; border:none; border-radius:6px;
            padding:2px; margin-left:6px;
        }
        #TabCloseButton:hover { background:#3A4351; }
        #TabCloseButton:pressed { background:#4C5766; }

        QScrollBar:vertical { width:10px; background:#171A21; }
        QScrollBar::handle:vertical { background:#414A5A; border-radius:5px; min-height:30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px; width: 0px; background: none; border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none; border: none;
        }
        """

    def qss_green(self):
        # 见 qss_day() 开头的说明：这段文字必须是 Python 注释，不能写在
        # return """ 之后（那样会被当成 QSS 内容，破坏下面的样式解析）。
        return """
        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo, #ExportButton { font-size:16px; }
        QMainWindow,QWidget { background:#E4F7DF; color:#2C3E50; }
        #TopBar,#Sidebar,QToolBar,QStatusBar { background:#E8F5E3; }
        #TopBar { border-bottom:1px solid #B8D9A8; }
        #Sidebar { border-right:1px solid #B8D9A8; }
        #SidebarTreeContent { background:transparent; }
        #EditorPanel,#PaperArea { background:#E4F7DF; }
        #EditorTitle { color:#4A5A4F; font-size:32px; font-weight:700; padding:6px 0 16px 0; }
        QTreeView { background:#E8F5E3; border:none; outline:none; color:#33493C; font-size:16px; }
        QTreeView::item { height:44px; padding:6px 10px; border-radius:6px; }
        QTreeView::item:hover { background:#D4EBCC; }
        QTreeView::item:selected { background:#B8D9A8; color:#1E3A2A; }
        QLineEdit,QComboBox,QPushButton,QSpinBox {
            background:#F0FAEA; color:#2C3E50; border:1px solid #B8D9A8;
            border-radius:7px; padding:8px 11px; min-height:22px;
        }
        QPushButton:hover,QToolButton:hover { background:#D4EBCC; }
        QToolBar { border:none; border-bottom:1px solid #B8D9A8; spacing:5px; padding:7px 12px; }
        QToolButton { background:transparent; color:#2C3E50; border-radius:6px; padding:7px 9px; }
        QToolButton:hover { background:#D4EBCC; }
        QToolButton:checked { background:#B8D9A8; }
        QTextEdit { background:transparent; color:#2C3E50; border:none;
            selection-background-color:#B8D9A8; selection-color:#1E3A2A;
        }
        #DialogTitle { font-size:22px; font-weight:650; color:#1E3A2A; }
        #DialogHint { color:#4A5A4F; }
        QTabWidget::pane { border:1px solid #B8D9A8; border-radius:7px; }
        QTabBar::tab { padding:9px 18px; color:#2C3E50; }
        QTabBar::tab:selected { background:#D4EBCC; border-radius:6px; }
        QSplitter::handle { background:#B8D9A8; width:4px; }
        QMenu { background:#F0FAEA; color:#2C3E50; border:1px solid #B8D9A8; border-radius:10px; }
        QMenu::item { padding:10px 30px 10px 18px; margin:2px 4px; border-radius:5px; }
        QMenu::item:selected { background:#B8D9A8; color:#1E3A2A; }

        QComboBox {
            background: transparent;
            border: 1px solid #D5D9E0;
            border-radius: 6px;
            padding: 6px 30px 6px 10px;
            min-height: 28px;
        }
        QComboBox:hover {
            border-color: #AEB7C5;
        }
        QComboBox:focus {
            border-color: #9AA9BF;
        }
        QComboBox::drop-down {
            width: 26px;
            border: none;
            background: transparent;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }
        QComboBox::down-arrow {
            width: 8px;
            height: 8px;
        }
        QComboBox QAbstractItemView {
            background: #F0FAEA;
            color: #2C3E50;
            border: 1px solid #B8D9A8;
            border-radius: 6px;
            padding: 5px;
            outline: none;
            selection-background-color: #B8D9A8;
            selection-color: #1E3A2A;
        }

        #FontSizeCombo, #LineHeightCombo, #FontFamilyCombo {
            background:#F0FAEA; color:#2C3E50; border:1px solid #B8D9A8;
            border-radius:7px; padding:8px 28px 8px 11px; min-height:22px;
        }
        #FontSizeCombo:hover, #LineHeightCombo:hover, #FontFamilyCombo:hover { border-color:#AEB7C5; }
        #FontSizeCombo:focus, #LineHeightCombo:focus, #FontFamilyCombo:focus { border-color:#9AA9BF; }
        #FontSizeCombo::drop-down, #LineHeightCombo::drop-down, #FontFamilyCombo::drop-down {
            width: 24px; border: none; background: transparent;
        }
        #FontSizeCombo::down-arrow, #LineHeightCombo::down-arrow, #FontFamilyCombo::down-arrow {
            width: 0px; height: 0px; image: none;
        }

        #SidebarToggle {
            background: transparent; border: none; border-radius:6px;
            padding: 6px; min-height:0; min-width:0;
        }
        #SidebarToggle:hover { background:#D4EBCC; }

        #ChapterTabBar { background:transparent; }
        #ChapterTabBar::tab {
            background:#CBE7BC; color:#3A4A3F; border:1px solid transparent;
            border-top-left-radius:9px; border-top-right-radius:9px;
            padding:13px 10px 13px 16px; margin:6px 1px 0 1px;
            min-width:130px; max-width:240px; min-height:20px;
        }
        #ChapterTabBar::tab:!selected { border-right:1px solid #A8CE96; }
        #ChapterTabBar::tab:selected {
            background:#E4F7DF; color:#1E3A2A;
            border:1px solid #B8D9A8; border-bottom:none;
            border-top:2px solid #3F7D3D; padding-top:12px;
        }
        #ChapterTabBar::tab:!selected:hover { background:#B7DDA3; border-right-color:transparent; }
        #ChapterTabBar::tab:selected:hover { background:#E4F7DF; }
        #TabCloseButton {
            background:transparent; border:none; border-radius:6px;
            padding:2px; margin-left:6px;
        }
        #TabCloseButton:hover { background:#A6CE92; }
        #TabCloseButton:pressed { background:#8FBE7A; }

        QScrollBar:vertical { width:10px; background:#E8F5E3; }
        QScrollBar::handle:vertical { background:#B8D9A8; border-radius:5px; min-height:30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px; width: 0px; background: none; border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none; border: none;
        }
        """

    def _apply_document_palette(self):
        theme = self.data.settings.get("theme", "day")
        if theme == "night":
            bg, fg, sel, sel_fg = "#111318", "#F3F4F6", "#4B566B", "#FFFFFF"
        elif theme == "green":
            bg, fg, sel, sel_fg = "#E4F7DF", "#2C3E50", "#B8D9A8", "#1E3A2A"
        else:
            bg, fg, sel, sel_fg = "#FFFFFF", "#222222", "#BFD3F2", "#222222"
        doc = self.editor.document()
        doc.setDefaultStyleSheet(
            f"body {{ background:{bg}; color:{fg}; }}"
            f"p, div, li, blockquote {{ background:transparent; color:{fg}; }}"
        )
        pal = self.editor.palette()
        pal.setColor(QPalette.Base, QColor(bg))
        pal.setColor(QPalette.Text, QColor(fg))
        pal.setColor(QPalette.Highlight, QColor(sel))
        pal.setColor(QPalette.HighlightedText, QColor(sel_fg))
        self.editor.setPalette(pal)
        # QTextEdit 的实际背景/文字绘制由内部 viewport 负责，
        # 只设置 self.editor 的 palette 在部分情况下不会立即生效，
        # 必须同时设置 viewport 的 palette，并强制重绘，
        # 否则要等下一次点击/交互触发重绘才会看到新颜色。
        self.editor.viewport().setPalette(pal)
        self.editor.viewport().update()
        self.editor.update()

    def _refresh_editor_text_colors(self):
        """
        根本原因：QTextDocument.setDefaultStyleSheet() 只对之后新解析（setHtml）的
        内容生效——正文里已经显示出来的文字，是在上一次 setHtml() 时就把当时主题的
        颜色“烘焙”进了每个字符的格式里，之后仅仅更新 palette / defaultStyleSheet
        并不会让这些已经存在的文字重新着色。这正是切换主题时，只有中间正文这一块
        颜色不会立刻刷新、必须切换一次标签页（因为切标签会触发 load_node 重新
        setHtml）才会跟着变化的原因。
        这里在主题切换后，把当前编辑器里已经加载的内容按新主题的样式表重新解析
        一遍，让正文立刻跟着刷新，不用再手动切换标签页。
        """
        if not hasattr(self, "editor") or self.current_node is None:
            return
        cursor_pos = self.editor.textCursor().position()
        scroll_value = self.editor.verticalScrollBar().value()
        html_content = self.editor.toHtml()
        # 和 load_node() 里一样，先清掉旧主题烘焙进去的显式颜色/背景，
        # 避免重新解析后又被旧颜色盖住。
        html_content = re.sub(r"background(?:-color)?\s*:\s*[^;\"}]+;?", "", html_content, flags=re.I)
        html_content = re.sub(r"color\s*:\s*[^;\"}]+;?", "", html_content, flags=re.I)
        html_content = re.sub(r"\s(?:bgcolor|color)\s*=\s*(['\"])[^'\"]*\1", "", html_content, flags=re.I)
        self.loading_content = True
        self.editor.blockSignals(True)
        self.editor.setHtml(html_content)
        self.editor.document().setDocumentMargin(0)
        self.editor.blockSignals(False)
        self.loading_content = False
        cursor = self.editor.textCursor()
        max_pos = max(0, self.editor.document().characterCount() - 1)
        cursor.setPosition(max(0, min(cursor_pos, max_pos)))
        self.editor.setTextCursor(cursor)
        self.editor.verticalScrollBar().setValue(scroll_value)

    def apply_editor_settings(self, reflow_paragraphs=True):
        if not hasattr(self, "editor"):
            return
        s = self.data.settings
        family = s.get("font", "Microsoft YaHei")
        size = int(s.get("font_size", 15))
        font = QFont(family, size)
        self.editor.document().setDefaultFont(font)
        self.editor.setFont(font)
        self.editor.setMaximumWidth(16777215)
        self.editor.setMinimumWidth(0)
        self._apply_document_palette()

        if reflow_paragraphs:
            self.apply_paragraph_format()

    def _paragraph_format_values(self):
        """返回当前设置对应的 (line_height, height_type, paragraph_spacing)，
        供 apply_paragraph_format() 和回车换段逻辑共用，避免重复算一遍。"""
        s = self.data.settings
        height = float(s.get("line_height", 1.5)) * 100
        enum_obj = QTextBlockFormat.ProportionalHeight
        try:
            height_type = enum_obj.value
        except AttributeError:
            height_type = int(enum_obj)
        margin = float(s.get("paragraph_spacing", 6))
        return height, height_type, margin

    def eventFilter(self, obj, event):
        if obj is getattr(self, "editor", None) and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                self._insert_paragraph_break()
                return True  # 换行逻辑完全自己接管，不再交给 Qt 默认处理
            # Ctrl+Shift+V：保留原始格式粘贴（旧的默认行为），放在标准
            # 粘贴快捷键前面判断，避免被下面 QKeySequence.Paste 的匹配
            # 抢先处理掉。
            if event.key() == Qt.Key_V and (event.modifiers() & Qt.ControlModifier) \
                    and (event.modifiers() & Qt.ShiftModifier):
                self.editor.paste()
                return True
            if event.matches(QKeySequence.Paste):
                self._paste_clean()
                return True
        return super().eventFilter(obj, event)

    def _insert_paragraph_break(self):
        """接管回车键的换段逻辑，替换掉 Qt 自带的默认处理。

        Qt 自带处理里有一个"连续在空段落上按回车，退出列表/引用格式"的
        功能（常见于富文本编辑器，连按两次回车跳出列表）。这个功能本身
        合理，但 Qt 的实现方式是把整段 blockFormat 粗暴地重置成一个全新
        的默认格式——连我们统一设置的行高、段间距也被一起清空，这就是
        "连续换行后行间距突然失效"的真正原因。而且它对"什么时候该新建
        段落、什么时候该原地重置"这套判断是不透明的内部状态机，之前尝试
        在它处理完之后再"补救"格式，会跟这套状态机自己的判断打架，反而
        导致"要连按好几次回车才能真正换行"。

        这里干脆完全不让 Qt 处理回车键，改成自己手动控制段落切分：
        - 光标在一个已经是空段落、且带有列表 / 引用缩进格式的段落上再按
          一次回车 → 退出列表/引用，变回普通段落（保留"连按两次跳出列
          表"这个用户习惯的操作），但普通段落的行高、段间距用当前设置
          重新写一份，不会被清空。
        - 其余所有情况 → 无条件新建一个段落，格式（含行高、段间距）
          完整复制自当前段落，绝不清空，也不存在"这次按了没反应"的
          不确定状态。"""
        if not hasattr(self, "editor"):
            return
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()

        block = cursor.block()
        at_empty_block = not block.text()
        text_list = block.textList()
        block_fmt = cursor.blockFormat()
        # quote() 会把左右 margin 设成非 0，以此识别"引用"格式
        in_quote = block_fmt.leftMargin() > 0 or block_fmt.rightMargin() > 0

        cursor.beginEditBlock()
        if at_empty_block and (text_list is not None or in_quote):
            if text_list is not None:
                text_list.remove(block)
            new_fmt = QTextBlockFormat()
            height, height_type, margin = self._paragraph_format_values()
            new_fmt.setLineHeight(height, height_type)
            new_fmt.setBottomMargin(margin)
            cursor.setBlockFormat(new_fmt)
            cursor.setCharFormat(QTextCharFormat())
        else:
            char_fmt = cursor.charFormat()
            cursor.insertBlock(block_fmt)
            cursor.setCharFormat(char_fmt)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def apply_paragraph_format(self):
        """按当前设置的行高 / 段间距，重新套用到文档中的每一个段落。
        这一步需要遍历全文所有 block，几万字的长文档开销较大，
        只应在切换章节、切换主题、修改行高/段间距设置这类
        "需要整篇重新排版"的场景调用；单纯改字号/字体时不要调用，
        否则每次都要整篇遍历一遍，长文档会明显卡顿甚至卡死。

        另外：editor.textChanged 连着 editor_changed()，而 editor_changed()
        每次都会把整篇正文重新序列化成 HTML、并递归统计全书字数——如果不
        屏蔽信号，下面循环里每改一个段落的格式都会各触发一次 textChanged，
        几千个段落就等于把这些开销重复了几千遍，是真正卡死的原因。这里在
        循环期间先屏蔽 editor 的信号，遍历结束后再统一触发一次即可。"""
        if not hasattr(self, "editor"):
            return
        doc = self.editor.document()
        height, height_type, margin = self._paragraph_format_values()
        self.editor.blockSignals(True)
        try:
            block = doc.begin()
            while block.isValid():
                cursor = QTextCursor(block)
                fmt = block.blockFormat()
                fmt.setLineHeight(height, height_type)
                fmt.setBottomMargin(margin)
                cursor.setBlockFormat(fmt)
                block = block.next()
        finally:
            self.editor.blockSignals(False)
        # 循环期间信号被屏蔽，textChanged 不会自动触发，这里手动补一次，
        # 保证正文内容同步保存、字数统计和撤销/重做按钮状态和之前一致。
        if hasattr(self, "action_undo") and hasattr(self, "action_redo"):
            self.action_undo.setEnabled(doc.isUndoAvailable())
            self.action_redo.setEnabled(doc.isRedoAvailable())
        self.editor_changed()


    # ---------- 书架 / 书籍 ----------
    def remember_recent(self, book):
        ids = [book.id]
        for rid in self.data.settings.get("recent_book_ids", []):
            if rid != book.id and self.data.find_book(rid):
                ids.append(rid)
        self.data.settings["recent_book_ids"] = ids[:8]

    def load_recent_book(self):
        self.tree.expandAll()
        if self._restore_open_tabs():
            return
        ids = self.data.settings.get("recent_book_ids", [])
        target = self.data.find_book(ids[0]) if ids else None
        if not target:
            self.select_first_available()
            return
        if target.tree:
            self.select_node(target.tree[0])
        else:
            self.select_node(target)

    def _restore_open_tabs(self):
        """启动时按上次关闭前记录的标签页列表，把当时打开的章节标签页
        原样恢复出来，并切换到当时正在看的那一个——章节内容本身随时都
        在，这里只是把标签页摆回去，效果类似浏览器"恢复上次的标签页"。
        返回 True 表示恢复成功，调用方据此决定还要不要再走原来那套
        "打开最近一本书的第一章"的默认逻辑（比如第一次启动、或者上次
        关闭时没有任何标签页打开）。"""
        ids = self.data.settings.get("open_tabs") or []
        nodes = []
        for nid in ids:
            node = self.data.find_node(nid)
            # find_node 是按 id 在整棵树（书架/书籍/章节）里找的，这里
            # 只要真正的章节，书架/书籍本身不会被开成标签页。
            if isinstance(node, NovelNode) and not isinstance(node, (NovelShelf, NovelBook)):
                nodes.append(node)
        if not nodes:
            return False
        for node in nodes:
            self._ensure_tab_for_node(node)
        active_id = self.data.settings.get("active_tab_id")
        active_node = self.data.find_node(active_id) if active_id else None
        self.select_node(active_node if active_node in nodes else nodes[-1])
        # 保险起见再显式强制刷新一次标签栏——上面 QTimer.singleShot(0, ...)
        # 已经把整个恢复流程挪到窗口显示之后执行，理论上不需要这一步，
        # 但不同环境下窗口管理器处理首次显示的时机可能有细微差异，这里
        # 加一道不依赖具体时机的保险，成本可以忽略。
        self.tab_bar.update()
        return True

    def select_first_available(self):
        if not self.data.shelves:
            self.editor.blockSignals(True)
            self.editor.clear()
            self.editor.blockSignals(False)
            self.editor_title.setText("未选择章节")
            self.current_book = None
            self.current_node = None
            self.update_all_stats()
            return
        shelf = self.data.shelves[0]
        if shelf.children:
            book = shelf.children[0]
            if book.tree:
                self.select_node(book.tree[0])
            else:
                self.select_node(book)
        else:
            self.select_node(shelf)

    def load_shelf_node(self, shelf):
        self.current_book = None
        self.current_node = None
        self.loading_content = True
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        self.loading_content = False
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("请选择或新建书籍……")
        self.editor_title.setText(shelf.name)
        self.set_dirty(False)
        self.update_all_stats()

    def load_book_node(self, book):
        self.current_book = book
        self.current_node = None
        self.remember_recent(book)
        self.loading_content = True
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        self.loading_content = False
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("请选择或新建章节开始写作……")
        self.editor_title.setText(book.name)
        self.set_dirty(False)
        self.update_all_stats()

    def new_shelf(self):
        name, ok = QInputDialog.getText(self, "新建书架", "书架名称：")
        if not ok or not name.strip():
            return
        self.save_current()
        shelf = NovelShelf(name.strip())
        self.tree_model.add_node_object(shelf, None)
        self.data.save()
        self.select_node(shelf)

    def rename_shelf(self, shelf):
        name, ok = QInputDialog.getText(self, "重命名书架", "书架名称：", text=shelf.name)
        if ok and name.strip():
            shelf.name = name.strip()
            shelf.touch()
            idx = self.tree_model.index_for_node(shelf)
            self.tree_model.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.EditRole])
            self.mark_dirty()

    def delete_shelf(self, shelf):
        if len(self.data.shelves) <= 1:
            QMessageBox.information(self, "无法删除", "至少保留一个书架。")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除书架《{shelf.name}》吗？其中所有书籍、正文和大纲都会删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.save_current()
        was_current = self.current_book is not None and self.current_book.parent is shelf
        self._close_tabs_for_nodes([shelf])
        for book in list(shelf.children):
            self.data.forget_book_file(book)
        self.tree_model.delete_node(shelf)
        self.data.settings["recent_book_ids"] = [
            x for x in self.data.settings.get("recent_book_ids", []) if self.data.find_book(x)
        ]
        self.data.save()
        if was_current:
            self.current_book = None
            self.current_node = None
        self.select_first_available()

    def new_book(self, shelf):
        name, ok = QInputDialog.getText(self, "新建书籍", "书籍名称：")
        if not ok or not name.strip():
            return
        self.save_current()
        book = NovelBook(name.strip())
        book.file = self.data.reserve_book_file()
        self.tree_model.add_node_object(book, shelf)
        self.data.save()
        self.select_node(book)

    def rename_book(self, book):
        name, ok = QInputDialog.getText(self, "重命名书籍", "书籍名称：", text=book.name)
        if ok and name.strip():
            book.name = name.strip()
            book.touch()
            idx = self.tree_model.index_for_node(book)
            self.tree_model.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.EditRole])
            if self.current_book is book and not self.current_node:
                self.editor_title.setText(book.name)
            self.mark_dirty()

    def delete_book(self, book):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除《{book.name}》吗？所有正文和大纲都会删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.save_current()
        was_current = self.current_book is book
        self._close_tabs_for_nodes([book])
        self.data.forget_book_file(book)
        self.tree_model.delete_node(book)
        self.data.settings["recent_book_ids"] = [
            x for x in self.data.settings.get("recent_book_ids", []) if x != book.id
        ]
        self.data.save()
        if was_current:
            self.current_book = None
            self.current_node = None
        self.select_first_available()

    # ---------- 树 ----------
    def select_node(self, node):
        if not node:
            return
        idx = self.tree_model.index_for_node(node)
        p = node.parent
        ancestors = []
        while p:
            ancestors.append(p)
            p = p.parent
        for a in reversed(ancestors):
            self.tree.expand(self.tree_model.index_for_node(a))
        self.tree.setCurrentIndex(idx)
        self.tree.scrollTo(idx)

    def _exec_menu(self, menu, global_pos):
        """右键菜单：用窗口遮罩裁出圆角再显示。
        之前用 WA_TranslucentBackground（半透明合成）实现圆角，
        但在当前环境下合成失败，圆角外的区域会整块显示成黑色；
        遮罩是硬裁剪窗口形状，不依赖透明合成，不会有这个问题。
        系统本身也会给弹出菜单加一层很淡的原生阴影。"""
        menu.adjustSize()
        menu.setMask(_rounded_region(menu.width(), menu.height(), 10))
        return menu.exec(global_pos)

    def show_editor_context_menu(self, pos):
        menu = QMenu(self.editor)
        menu.setMinimumWidth(250)
        menu.setStyleSheet("""
            QMenu { padding: 7px; }
            QMenu::item { padding: 9px 24px 9px 18px; margin: 2px 0; border-radius: 5px; }
            QMenu::separator { height: 1px; margin: 6px 10px; }
        """)
        cursor = self.editor.textCursor()
        has_selection = cursor.hasSelection()

        def add(label, callback, enabled=True):
            action = menu.addAction(label)
            action.setEnabled(enabled)
            action.triggered.connect(callback)
            return action

        add("撤销", self.editor.undo, self.editor.document().isUndoAvailable())
        add("重做", self.editor.redo, self.editor.document().isRedoAvailable())
        menu.addSeparator()
        add("剪切", self.editor.cut, has_selection)
        add("复制", self.editor.copy, has_selection)
        add("粘贴", self._paste_clean,
            bool(QApplication.clipboard().mimeData().hasHtml() or QApplication.clipboard().mimeData().hasText()))
        add("粘贴且不使用任何格式", self._paste_plain,
            bool(QApplication.clipboard().mimeData().hasText()))
        add("粘贴并保留原始格式  Ctrl+Shift+V", self.editor.paste,
            bool(QApplication.clipboard().mimeData().hasText()))
        menu.addSeparator()
        add("清除格式" + ("" if has_selection else "（全文）"),
            self.clear_selection_format, True)
        menu.addSeparator()
        add("全选", self.editor.selectAll)
        self._exec_menu(menu, self.editor.mapToGlobal(pos))

    def clear_selection_format(self):
        """清除选区（没有选区时清除全文）里残留的外部格式，重置回当前
        文档默认的字体/字号 + 统一的行高/段间距设置。

        从 Word / 网页 / Google Docs 等地方粘贴进来的富文本（尤其是用了
        "粘贴并保留原始格式"的情况），经常带着来源自己的字体、字号、
        固定行高等格式；这些格式一来会跟本地的字号/字体調整"看起来没
        反应"（其实是新设置盖在了这层残留格式上面，没有真正替换掉它），
        二来因为跟文档其它地方的格式不一样、没法被 compact_richtext_html
        识别成"重复出现、可以共享"的样式，也是保存下来的文件体积异常
        偏大的常见原因。这里提供一个手动"洗格式"的办法：把选中的文字
        清成跟其它正文一样的干净格式，处理完之后再保存，这部分内容占的
        体积也会跟着降下来。"""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.Document)
        if not cursor.hasSelection():
            return

        cursor.beginEditBlock()
        try:
            char_fmt = QTextCharFormat()
            char_fmt.setFont(self.editor.document().defaultFont())
            cursor.setCharFormat(char_fmt)  # setCharFormat 是整个替换掉，不是叠加合并

            height, height_type, margin = self._paragraph_format_values()
            doc = self.editor.document()
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            block = start_block
            while block.isValid():
                block_cursor = QTextCursor(block)
                fmt = QTextBlockFormat()
                fmt.setLineHeight(height, height_type)
                fmt.setBottomMargin(margin)
                block_cursor.setBlockFormat(fmt)
                if block == end_block:
                    break
                block = block.next()
        finally:
            cursor.endEditBlock()

        self.save_current()
        self.set_dirty(True)

    def _paste_clean(self):
        """默认的粘贴行为：保留来源里"加粗 / 斜体 / 下划线 / 删除线"这几个
        工具栏本身就能控制的基础格式，但不带入字体、字号、颜色、行高、
        段间距这些——这些正是导致"粘贴进来的文字改不了格式"（其实不是
        改不动，是新设置盖在了这层残留格式上面，没有真正替换掉它）和
        文件体积异常偏大的东西。段落统一套用当前文档的行高/段间距设置，
        不沿用来源自己的 margin / line-height。

        需要完全不带任何格式的话，用右键菜单"粘贴且不使用任何格式"；
        需要连字体颜色行高都原样保留的话，用"粘贴并保留原始格式"
        （或 Ctrl+Shift+V）。"""
        mime = QApplication.clipboard().mimeData()
        if mime.hasHtml():
            source_doc = QTextDocument()
            source_doc.setHtml(mime.html())
            self._insert_matched_format(source_doc)
        elif mime.hasText():
            self.editor.textCursor().insertText(mime.text())

    def _insert_matched_format(self, source_doc):
        """把 source_doc（剪贴板 HTML 解析出来的临时文档）的内容插入到
        编辑器里：
        - 字符格式：逐个格式片段（fragment）只保留加粗/斜体/下划线/
          删除线这几个属性，字体、字号、颜色等一律不带。
        - 段落格式：普通段落统一用当前文档的行高/段间距设置，不沿用
          来源自己的段落格式；引用（有缩进、但不在列表里的段落，对应
          <blockquote>）套用跟工具栏"引用"按钮（quote()）一致的缩进；
          无序/有序列表按来源的列表样式重新建一份列表（不沿用来源
          自己的列表 css，只区分"有序/无序"这一种语义），连续的列表项
          会加进同一个列表对象，不会拆成一堆各自一项的列表。"""
        # 跟 quote() 按钮用的是同一组数值，保持"手动点引用按钮"和
        # "粘贴进来的引用"视觉效果一致。
        QUOTE_MARGINS = dict(left=28, right=20, top=6, bottom=6)
        ORDERED_LIST_STYLES = (
            QTextListFormat.ListDecimal, QTextListFormat.ListLowerAlpha,
            QTextListFormat.ListUpperAlpha, QTextListFormat.ListLowerRoman,
            QTextListFormat.ListUpperRoman,
        )

        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        try:
            if cursor.hasSelection():
                cursor.removeSelectedText()
            height, height_type, margin = self._paragraph_format_values()
            block = source_doc.begin()
            first_block = True
            prev_source_list = None
            dest_list = None
            while block.isValid():
                src_bf = block.blockFormat()
                src_list = block.textList()
                is_quote = src_list is None and (src_bf.leftMargin() > 0 or src_bf.rightMargin() > 0)

                if not first_block:
                    block_fmt = QTextBlockFormat()
                    block_fmt.setLineHeight(height, height_type)
                    block_fmt.setBottomMargin(margin)
                    if is_quote:
                        block_fmt.setLeftMargin(QUOTE_MARGINS["left"])
                        block_fmt.setRightMargin(QUOTE_MARGINS["right"])
                        block_fmt.setTopMargin(QUOTE_MARGINS["top"])
                        block_fmt.setBottomMargin(QUOTE_MARGINS["bottom"])
                    cursor.insertBlock(block_fmt)
                elif is_quote:
                    # 粘贴的第一段是引用：直接把光标当前所在的段落改成
                    # 引用样式，不需要先插入新段落。
                    block_fmt = cursor.blockFormat()
                    block_fmt.setLeftMargin(QUOTE_MARGINS["left"])
                    block_fmt.setRightMargin(QUOTE_MARGINS["right"])
                    block_fmt.setTopMargin(QUOTE_MARGINS["top"])
                    block_fmt.setBottomMargin(QUOTE_MARGINS["bottom"])
                    cursor.setBlockFormat(block_fmt)
                first_block = False

                if src_list is not None:
                    if src_list is prev_source_list and dest_list is not None:
                        # 跟上一段是来源里同一个列表，加进同一个目标列表，
                        # 不要每段各建一个新列表。
                        dest_list.add(cursor.block())
                    else:
                        is_ordered = src_list.format().style() in ORDERED_LIST_STYLES
                        list_style = QTextListFormat.ListDecimal if is_ordered else QTextListFormat.ListDisc
                        dest_list = cursor.createList(list_style)
                else:
                    dest_list = None
                prev_source_list = src_list

                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.text():
                        src_fmt = frag.charFormat()
                        clean_fmt = QTextCharFormat()
                        clean_fmt.setFontWeight(QFont.Bold if src_fmt.fontWeight() >= QFont.Bold else QFont.Normal)
                        clean_fmt.setFontItalic(src_fmt.fontItalic())
                        clean_fmt.setFontUnderline(src_fmt.fontUnderline())
                        clean_fmt.setFontStrikeOut(src_fmt.fontStrikeOut())
                        cursor.insertText(frag.text(), clean_fmt)
                    it += 1
                block = block.next()
        finally:
            cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def _paste_plain(self):
        """粘贴且不使用任何格式：只取剪贴板里的纯文本，格式完全交给光标
        当前位置的格式决定，跟旧版本行为一致。"""
        mime = QApplication.clipboard().mimeData()
        if mime.hasText():
            self.editor.textCursor().insertText(mime.text())

    def tree_selection(self, current, previous):
        if self.loading_content or not current.isValid():
            return
        self.save_current()
        node = current.internalPointer()
        if isinstance(node, NovelShelf):
            self.load_shelf_node(node)
        elif isinstance(node, NovelBook):
            self.load_book_node(node)
        elif isinstance(node, NovelNode):
            self.current_book = node.nearest_book()
            if self.current_book:
                self.remember_recent(self.current_book)
            self.load_node(node)

    def load_node(self, node):
        self.current_node = node
        self.loading_content = True
        self.editor.blockSignals(True)
        self.editor.setReadOnly(False)
        html_content = node.content or ""
        # 清理旧版本产生的白色背景/黑色文字样式，避免暗色和护眼主题出现“每行白框”。
        html_content = re.sub(r"background(?:-color)?\s*:\s*[^;\"}]+;?", "", html_content, flags=re.I)
        html_content = re.sub(r"color\s*:\s*[^;\"}]+;?", "", html_content, flags=re.I)
        html_content = re.sub(r"\s(?:bgcolor|color)\s*=\s*(['\"])[^'\"]*\1", "", html_content, flags=re.I)
        self.editor.setHtml(html_content)
        self.editor.document().setDocumentMargin(0)
        self.editor.blockSignals(False)
        self.loading_content = False
        self.editor_title.setText(self.display_title(node))
        self.apply_editor_settings()

        # 修复"切换/新建章节后，打字字号莫名其妙沿用上一章节"的根本问题：
        # QTextEdit 内部维护着一个"接下来打字要用的字符格式"
        # （currentCharFormat，跟光标当前位置实际的字符格式是两回事），
        # setHtml() 切换整篇文档内容时 Qt 并不会自动重置这个状态——哪怕
        # 切到了一篇全新的空白章节，只要之前在别的章节里通过工具栏改过
        # 字号/字体（尤其是全选后改，或者光标停在文档末尾时改的那次），
        # 这个"打字格式"就会原样带过来，表现为："新建章节明明没设过格式，
        # 一打字字号却很小/很奇怪，选中了改字号看起来又没反应"——其实不是
        # 改不动，而是每次新打的字都被这个残留状态接管了。这里用一个*不
        # 应用到编辑器上*的独立游标去读取文档开头真实解析出来的格式（而
        # 不是随便写死一个值），重置"打字格式"，顺带清掉上一章节可能
        # 残留的粗体/斜体等状态；用独立游标是为了不影响下面要恢复的
        # 光标位置和滚动条位置——以前这里直接 setTextCursor() 把光标
        # 移到开头，代价是每次切换标签页都会跳回文档最顶部。
        probe_cursor = QTextCursor(self.editor.document())
        probe_cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setCurrentCharFormat(probe_cursor.charFormat())

        # 恢复上次切换走时停留的光标位置和滚动条位置（第一次打开这一章节
        # 则都还没记录过，默认停在开头），实现"切换标签页时停留在原来的
        # 位置"，跟浏览器标签页的体验保持一致。
        cursor = self.editor.textCursor()
        max_pos = max(0, self.editor.document().characterCount() - 1)
        saved_pos = min(getattr(node, "_cursor_pos", 0), max_pos)
        cursor.setPosition(max(0, saved_pos))
        self.editor.setTextCursor(cursor)
        self.editor.verticalScrollBar().setValue(getattr(node, "_scroll_value", 0))

        self.set_dirty(False)
        self.update_all_stats()
        self._activate_tab_for_node(node)
        self.update_toolbar_state()

    # ---------- 章节标签页（Chrome / Edge 风格，可同时打开多个章节） ----------
    def _find_tab_index(self, node):
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabData(i) is node:
                return i
        return -1

    def _ensure_tab_for_node(self, node):
        i = self._find_tab_index(node)
        if i >= 0:
            return i
        i = self.tab_bar.count()
        self.tab_bar.blockSignals(True)
        self.tab_bar.addTab(self.display_title(node))
        self.tab_bar.setTabData(i, node)
        self.tab_bar.setTabToolTip(i, self.display_title(node))

        # 每个标签页右侧放一个 x.svg 关闭按钮，点击即可关闭该标签页；
        # 图标大小和其他工具栏图标保持一致，同时把按钮本身做大一圈，方便点击。
        close_btn = QToolButton()
        close_btn.setObjectName("TabCloseButton")
        close_btn.setIcon(ui_icons.icon("tab-close", self._icon_color()))
        close_btn.setIconSize(QSize(18, 18))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setAutoRaise(True)
        close_btn.setToolTip("关闭标签页")
        close_btn.clicked.connect(lambda _checked=False, btn=close_btn: self._close_tab_by_button(btn))
        self.tab_bar.setTabButton(i, QTabBar.RightSide, close_btn)

        self.tab_bar.blockSignals(False)
        return i

    def _close_tab_by_button(self, btn):
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabButton(i, QTabBar.RightSide) is btn:
                self.tab_close_requested(i)
                return

    def _activate_tab_for_node(self, node):
        i = self._ensure_tab_for_node(node)
        if self.tab_bar.currentIndex() != i:
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(i)
            self.tab_bar.blockSignals(False)

    def tab_changed(self, index):
        if index < 0:
            return
        node = self.tab_bar.tabData(index)
        if node is None or node is self.current_node:
            return
        self.select_node(node)

    def tab_close_requested(self, index):
        was_current = index == self.tab_bar.currentIndex()
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self.tab_bar.blockSignals(False)
        if not was_current:
            return
        if self.tab_bar.count():
            new_index = min(index, self.tab_bar.count() - 1)
            new_node = self.tab_bar.tabData(new_index)
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(new_index)
            self.tab_bar.blockSignals(False)
            self.select_node(new_node)
        else:
            self.save_current()
            self.current_node = None
            self.editor.blockSignals(True)
            self.editor.clear()
            self.editor.blockSignals(False)
            self.editor.setReadOnly(True)
            self.editor.setPlaceholderText("请选择或新建章节开始写作……")
            self.editor_title.setText("未选择章节")
            self.set_dirty(False)
            self.update_all_stats()

    def _close_tabs_for_nodes(self, nodes):
        """删除章节 / 书籍 / 书架时，一并关掉它们（含所有子节点）对应的标签页。"""
        doomed = set()

        def collect(n):
            doomed.add(n)
            for c in n.children:
                collect(c)

        for n in nodes:
            collect(n)
        for i in reversed(range(self.tab_bar.count())):
            if self.tab_bar.tabData(i) in doomed:
                self.tab_bar.blockSignals(True)
                self.tab_bar.removeTab(i)
                self.tab_bar.blockSignals(False)

    def _sync_tab_titles(self):
        for i in range(self.tab_bar.count()):
            node = self.tab_bar.tabData(i)
            if node is not None:
                title = self.display_title(node)
                self.tab_bar.setTabText(i, title)
                self.tab_bar.setTabToolTip(i, title)

    def display_title(self, node):
        if not self.data.settings.get("auto_number", False):
            return node.title
        nums = []
        x = node
        while not isinstance(x, NovelBook) and x.parent is not None:
            p = x.parent
            nums.append(p.children.index(x) + 1)
            x = p
        nums.reverse()
        mode = self.data.settings.get("number_mode", "chapter")
        if mode == "numeric":
            prefix = ".".join(map(str, nums))
        else:
            # 保持用户标题原样，只把自动编号显示在标题前
            prefix = "第 " + ".".join(map(str, nums)) + " 级"
        return prefix + " · " + node.title

    def create_node(self, mode, node=None):
        title, ok = QInputDialog.getText(
            self, "新建大纲节点", "标题（完全自定义）：", text=""
        )
        if not ok:
            return
        title = title.strip()
        if not title:
            return
        self.save_current()

        if mode == "child":
            new = self.tree_model.add_node(node, title)
            self.tree.expand(self.tree_model.index_for_node(node))
        else:  # sibling：只会在普通章节节点上触发，node.parent 必定是书籍或另一个章节
            p = node.parent
            row = p.children.index(node) + 1
            new = self.tree_model.add_node(p, title, row)

        self.data.save()
        self.select_node(new)

    def rename_node(self, node):
        name, ok = QInputDialog.getText(
            self, "重命名", "标题：", text=node.title
        )
        if ok and name.strip():
            node.title = name.strip()
            node.touch_chain()
            idx = self.tree_model.index_for_node(node)
            self.tree_model.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.EditRole])
            if node is self.current_node:
                self.editor_title.setText(self.display_title(node))
            self._sync_tab_titles()
            self.mark_dirty()

    def delete_node(self, node):
        reply = QMessageBox.question(
            self, "确认删除",
            f"删除“{node.title}”及其所有子节点？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        p = node.parent
        siblings = p.children
        i = siblings.index(node)
        replacement = siblings[i + 1] if i + 1 < len(siblings) else (siblings[i - 1] if i > 0 else p)
        self._close_tabs_for_nodes([node])
        self.tree_model.delete_node(node)
        self.data.save()
        self.current_node = None
        self.select_node(replacement)

    def move_node(self, node, direction):
        self.save_current()
        if self.tree_model.move_node(node, direction):
            self.data.save()
            self.select_node(node)
            self.refresh_auto_titles()

    def outdent_node(self, node):
        self.save_current()
        if self.tree_model.outdent_node(node):
            self.data.save()
            self.tree.expand(self.tree_model.index_for_node(node.parent) if node.parent else QModelIndex())
            self.select_node(node)
            self.refresh_auto_titles()

    def indent_node(self, node):
        self.save_current()
        if self.tree_model.indent_node(node):
            self.data.save()
            self.tree.expand(self.tree_model.index_for_node(node.parent))
            self.select_node(node)
            self.refresh_auto_titles()

    def _snapshot_tree_expansion(self):
        """在 tree_model 被 reset 之前，记录当前哪些节点是展开状态。"""
        self._expanded_node_ids = set()

        def rec(nodes):
            for n in nodes:
                idx = self.tree_model.index_for_node(n)
                if idx.isValid() and self.tree.isExpanded(idx):
                    self._expanded_node_ids.add(n.id)
                rec(n.children)
        rec(self.tree_model.roots)

    def _restore_tree_expansion(self):
        """tree_model reset 完成后，把之前记录的展开状态还原回去。"""
        ids = getattr(self, "_expanded_node_ids", None)
        if not ids:
            return

        def rec(nodes):
            for n in nodes:
                if n.id in ids:
                    idx = self.tree_model.index_for_node(n)
                    if idx.isValid():
                        self.tree.expand(idx)
                rec(n.children)
        rec(self.tree_model.roots)

    def tree_menu(self, pos):
        idx = self.tree.indexAt(pos)
        menu = QMenu(self)
        if idx.isValid():
            node = idx.internalPointer()
            if isinstance(node, NovelShelf):
                a1 = menu.addAction("新建书籍…")
                menu.addSeparator()
                a3 = menu.addAction("重命名书架…")
                a4 = menu.addAction("删除书架")
                menu.addSeparator()
                a5 = menu.addAction("上移")
                a6 = menu.addAction("下移")
                menu.addSeparator()
                a7 = menu.addAction("复制书架名")
                chosen = self._exec_menu(menu, self.tree.viewport().mapToGlobal(pos))
                if chosen == a1: self.new_book(node)
                elif chosen == a3: self.rename_shelf(node)
                elif chosen == a4: self.delete_shelf(node)
                elif chosen == a5: self.move_node(node, -1)
                elif chosen == a6: self.move_node(node, 1)
                elif chosen == a7: QApplication.clipboard().setText(node.name)
            elif isinstance(node, NovelBook):
                a1 = menu.addAction("新建章节…")
                menu.addSeparator()
                a3 = menu.addAction("重命名书籍…")
                a4 = menu.addAction("删除书籍")
                menu.addSeparator()
                a5 = menu.addAction("上移")
                a6 = menu.addAction("下移")
                menu.addSeparator()
                a7 = menu.addAction("复制书籍名")
                chosen = self._exec_menu(menu, self.tree.viewport().mapToGlobal(pos))
                if chosen == a1: self.create_node("child", node)
                elif chosen == a3: self.rename_book(node)
                elif chosen == a4: self.delete_book(node)
                elif chosen == a5: self.move_node(node, -1)
                elif chosen == a6: self.move_node(node, 1)
                elif chosen == a7: QApplication.clipboard().setText(node.name)
            else:
                a1 = menu.addAction("新建子节点…")
                a2 = menu.addAction("新建同级节点…")
                menu.addSeparator()
                a3 = menu.addAction("重命名…")
                a4 = menu.addAction("删除")
                menu.addSeparator()
                a5 = menu.addAction("上移")
                a6 = menu.addAction("下移")
                a8 = menu.addAction("提升层级（变为上级的同级）")
                a9 = menu.addAction("降低层级（变为上一节点的子级）")
                menu.addSeparator()
                a7 = menu.addAction("复制标题")
                chosen = self._exec_menu(menu, self.tree.viewport().mapToGlobal(pos))
                if chosen == a1: self.create_node("child", node)
                elif chosen == a2: self.create_node("sibling", node)
                elif chosen == a3: self.rename_node(node)
                elif chosen == a4: self.delete_node(node)
                elif chosen == a5: self.move_node(node, -1)
                elif chosen == a6: self.move_node(node, 1)
                elif chosen == a8: self.outdent_node(node)
                elif chosen == a9: self.indent_node(node)
                elif chosen == a7: QApplication.clipboard().setText(node.title)
        else:
            a = menu.addAction("新建书架…")
            if self._exec_menu(menu, self.tree.viewport().mapToGlobal(pos)) == a:
                self.new_shelf()

    def refresh_auto_titles(self):
        if self.current_node:
            self.editor_title.setText(self.display_title(self.current_node))
        self._sync_tab_titles()

    def filter_tree(self, text):
        q = text.strip().lower()
        if not q:
            self.restore_visibility()
            return
        self.restore_visibility()
        def rec(node, idx):
            own = q in node.title.lower() or q in html_to_plain(node.content).lower()
            child = False
            for r, c in enumerate(node.children):
                ci = self.tree_model.index(r, 0, idx)
                child = rec(c, ci) or child
            visible = own or child
            self.tree.setRowHidden(idx.row(), idx.parent(), not visible)
            if child:
                self.tree.expand(idx)
            return visible
        for r, n in enumerate(self.tree_model.roots):
            rec(n, self.tree_model.index(r, 0, QModelIndex()))

    def restore_visibility(self):
        def rec(parent_idx):
            for r in range(self.tree_model.rowCount(parent_idx)):
                self.tree.setRowHidden(r, parent_idx, False)
                rec(self.tree_model.index(r, 0, parent_idx))
        rec(QModelIndex())

    # ---------- 全局搜索 ----------
    def global_search(self):
        dlg = GlobalSearchDialog(self.data.all_books(), self)
        if dlg.exec() == QDialog.Accepted:
            item = dlg.results.currentItem()
            if not item:
                return
            _, nid = item.data(Qt.UserRole)
            node = self.data.find_node(nid)
            if node:
                self.select_node(node)

    # ---------- 编辑 ----------
    def editor_changed(self):
        if self.loading_content or not self.current_node:
            return
        # 轻量操作：立即执行，敲字时不应有延迟。
        self.mark_dirty()
        # 重量操作（toHtml() 序列化 + 全书字数递归统计）：防抖延迟执行，
        # 避免每敲一个字都同步跑一遍导致长文档打字卡顿。
        self._pending_stats_node = self.current_node
        self.editor_change_timer.start()

    def _apply_editor_changes(self):
        node = self._pending_stats_node
        # 防抖等待期间可能已经切换到了别的节点（虽然切换前 save_current()
        # 已经同步落过一次内容），保险起见这里仍做一次一致性检查，避免把
        # 当前编辑器内容误写回一个已经不在编辑的旧节点。
        if not node or node is not self.current_node:
            return
        self.current_node.content = self.editor.toHtml()
        self.current_node._word_count_cache = None
        self.current_node.touch_chain()
        self.update_all_stats()

    def save_current(self):
        if not self.current_node:
            return
        # 记录离开这一章节时光标和滚动条停在哪，切回这个标签页时能恢复到
        # 原来的浏览位置，而不是每次都跳回顶部——体验上和浏览器标签页
        # 保持一致。这两个值只在内存里，不写入 JSON，重启后不需要保留。
        self.current_node._cursor_pos = self.editor.textCursor().position()
        self.current_node._scroll_value = self.editor.verticalScrollBar().value()
        # 只在真正落盘保存时瘦身 HTML；editor_changed() 里的内存态赋值
        # 每次按键都会触发，不做瘦身处理，避免增加输入时的开销。
        self.current_node.content = compact_richtext_html(self.editor.toHtml())
        self.current_node._word_count_cache = None
        self.current_node.touch_chain()
        # 这里已经把最新内容同步落到 current_node 上了，防抖定时器里
        # 待执行的那次同步（如果还没到点）就不需要再跑一遍。
        self.editor_change_timer.stop()
        self._pending_stats_node = None
        self._save_now()

    def mark_dirty(self):
        self.dirty = True
        self.save_state.setText("● 未保存")
        self.save_state.setToolTip("修改将在短时间内自动保存")

    def set_dirty(self, value):
        self.dirty = value
        if value:
            self.save_state.setText("● 未保存")
        else:
            stamp = self.last_saved_at or now_string()
            self.save_state.setText(f"● 已保存 {stamp}")

    def _save_now(self):
        self._save_open_tabs()
        if self.data.save():
            self.dirty = False
            self.last_saved_at = now_string()
            self.save_state.setText(f"● 已保存 {self.last_saved_at}")
        else:
            self.dirty = True
            self.save_state.setText("● 保存失败")

    def _save_open_tabs(self):
        """记录当前打开的所有标签页和正在看的那一个，下次启动时据此原样
        恢复出来，效果类似浏览器"恢复上次的标签页"。放在 _save_now() 里
        （落盘保存、含自动保存、退出前保存）而不是只在退出时存一次，是
        为了万一程序被强制结束（比如崩溃、断电），标签页列表也基本是
        最新的，不会因为没走到正常退出流程就丢失。这两个只是节点 id 的
        列表，读写开销可以忽略。"""
        self.data.settings["open_tabs"] = [
            self.tab_bar.tabData(i).id
            for i in range(self.tab_bar.count())
            if self.tab_bar.tabData(i) is not None
        ]
        self.data.settings["active_tab_id"] = self.current_node.id if self.current_node else None

    def autosave_tick(self):
        if self.dirty:
            self.save_current()

    # ---------- 格式 ----------
    def merge_char(self, fmt):
        c = self.editor.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.WordUnderCursor)
        c.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)

    def bold(self):
        f = QTextCharFormat()
        f.setFontWeight(QFont.Normal if self.editor.textCursor().charFormat().fontWeight() == QFont.Bold else QFont.Bold)
        self.merge_char(f)

    def italic(self):
        f = QTextCharFormat()
        f.setFontItalic(not self.editor.textCursor().charFormat().fontItalic())
        self.merge_char(f)

    def underline(self):
        f = QTextCharFormat()
        f.setFontUnderline(not self.editor.textCursor().charFormat().fontUnderline())
        self.merge_char(f)

    def quote(self):
        c = self.editor.textCursor()
        fmt = c.blockFormat()
        fmt.setLeftMargin(28)
        fmt.setRightMargin(20)
        fmt.setTopMargin(6)
        fmt.setBottomMargin(6)
        c.setBlockFormat(fmt)
        f = QTextCharFormat()
        f.setFontItalic(True)
        c.mergeCharFormat(f)

    def bullet(self):
        self.editor.textCursor().createList(QTextListFormat.ListDisc)

    def numbered(self):
        self.editor.textCursor().createList(QTextListFormat.ListDecimal)

    def heading_changed(self, index):
        if self.loading_content:
            return
        level = self.heading.itemData(index)
        c = self.editor.textCursor()
        bf = c.blockFormat()
        bf.setHeadingLevel(level)
        c.setBlockFormat(bf)
        if level:
            f = QTextCharFormat()
            f.setFontWeight(QFont.Bold)
            f.setFontPointSize({1: 26, 2: 22, 3: 19}.get(level, 18))
            c.mergeCharFormat(f)
        else:
            f = QTextCharFormat()
            f.setFontWeight(QFont.Normal)
            f.setFontPointSize(float(self.data.settings.get("font_size", 15)))
            c.mergeCharFormat(f)
        self.editor.setFocus()

    def alignment(self, align):
        self.editor.setAlignment(align)

    def clear_format(self):
        c = self.editor.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.WordUnderCursor)
        f = QTextCharFormat()
        f.setFontWeight(QFont.Normal)
        f.setFontItalic(False)
        f.setFontUnderline(False)
        f.setFontStrikeOut(False)
        f.setFontFamily(self.data.settings.get("font", "Microsoft YaHei"))
        f.setFontPointSize(float(self.data.settings.get("font_size", 15)))
        c.mergeCharFormat(f)
        bf = c.blockFormat()
        bf.setHeadingLevel(0)
        c.setBlockFormat(bf)

    def toolbar_font_family_changed(self, value):
        family = value.strip()
        if not family:
            return

        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)

        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.editor.mergeCurrentCharFormat(fmt)

        # 注意：这里不能把 family 写回 self.data.settings["font"]，也不能调用
        # apply_editor_settings()。原因有两层：
        # 1) apply_editor_settings() 内部会执行 self.editor.document().setDefaultFont(...)
        #    / self.editor.setFont(...)，这两个调用作用于整篇文档而不是当前选区，会把
        #    选区之外、原本依赖"文档默认字体"渲染的文字也一起改掉字体。
        # 2) self.data.settings["font"] 是"新建正文"的全局默认值。之前的版本会在这里
        #    顺手把它改成当前选区的字体，看似方便，实际效果是：只要在任意一篇文章里
        #    改过一次选区字体，之后新建的所有章节都会莫名其妙变成那次顺手选的字体/
        #    很小的字号——这正是"新建文本字体很小、改了又改不动"那个 bug 的根源
        #    （其实字体是能改的，只是"新建正文的默认字体"被不知不觉带偏了）。
        # 改字体只应该影响当前选区（或没有选区时，影响接下来要输入的文字），
        # 不应该影响文档默认字体，也不应该影响"新建正文"的全局默认设置——
        # 全局默认字体/字号只应该由（目前隐藏的）设置面板来改。
        self.save_current()
        self.set_dirty(True)

    def toolbar_font_size_changed(self, value):
        try:
            size = int(value)
        except (TypeError, ValueError):
            return

        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)

        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.editor.mergeCurrentCharFormat(fmt)

        # 同上（见 toolbar_font_family_changed 的注释）：这里既不能调用
        # apply_editor_settings()，也不能把 size 写回 self.data.settings["font_size"]，
        # 否则会把"新建正文"的全局默认字号悄悄改成这次选区临时用的字号，导致下次
        # 新建的章节继承一个意料之外（可能很小）的默认字号。改字号只应该作用于
        # 选区（或没有选区时，作用于接下来要输入的文字），全局默认字号只应该由
        # （目前隐藏的）设置面板来改。
        self.save_current()
        self.set_dirty(True)

    def toolbar_line_height_changed(self, value):
        try:
            height = float(value)
        except (TypeError, ValueError):
            return

        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            # 有选区：只改选区覆盖到的段落，不动全局默认行高、也不影响
            # 选区之外的其它段落——跟上面改字号/字体是同一个道理（见
            # toolbar_font_size_changed 的注释）：不能把这次选区的临时
            # 调整，顺手写回"新建正文"的全局默认设置。
            self._apply_line_height_to_selection(cursor, height)
        else:
            # 没有选区：维持原来的行为，工具栏行间距同时作为新的默认
            # 正文行高，直接套用到整篇文档。
            self.data.settings["line_height"] = height
            self.apply_editor_settings()
        self.save_current()
        self.set_dirty(True)

    def _apply_line_height_to_selection(self, cursor, height):
        """把行高只应用到选区覆盖到的段落（含首尾两端不完整选中的段落），
        用 beginEditBlock/endEditBlock 包起来，撤销时是一步到位，不会
        选区跨了 5 个段落却要按 5 次撤销。"""
        height_type = QTextBlockFormat.ProportionalHeight
        try:
            height_type = height_type.value
        except AttributeError:
            height_type = int(height_type)

        doc = self.editor.document()
        start_block = doc.findBlock(cursor.selectionStart())
        end_block = doc.findBlock(cursor.selectionEnd())

        edit_cursor = QTextCursor(doc)
        edit_cursor.beginEditBlock()
        try:
            block = start_block
            while block.isValid():
                block_cursor = QTextCursor(block)
                fmt = block.blockFormat()
                fmt.setLineHeight(height * 100, height_type)
                block_cursor.setBlockFormat(fmt)
                if block == end_block:
                    break
                block = block.next()
        finally:
            edit_cursor.endEditBlock()

    def _selection_char_format_values(self, cursor):
        """收集选区（无选区时为光标所在处）内出现过的字号 / 字体集合。
        按格式片段（fragment）遍历而不是逐字符遍历，几万字的选区也不会
        变慢；一旦字号和字体都已经出现分歧，立刻提前结束，不用扫完整个
        选区。"""
        if not cursor.hasSelection():
            font = cursor.charFormat().font()
            return {round(font.pointSizeF(), 1)}, {font.family()}

        doc = self.editor.document()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        sizes, families = set(), set()
        block = doc.findBlock(start)
        last_block = doc.findBlock(max(start, end - 1))
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    frag_start = frag.position()
                    frag_end = frag_start + frag.length()
                    if frag_end > start and frag_start < end:
                        font = frag.charFormat().font()
                        sizes.add(round(font.pointSizeF(), 1))
                        families.add(font.family())
                        if len(sizes) > 1 and len(families) > 1:
                            return sizes, families
                it += 1
            if block == last_block:
                break
            block = block.next()
        return sizes, families

    def _selection_line_heights(self, cursor):
        """收集选区跨越的所有段落的行高（按段落/block 遍历，段落数通常
        远小于字符数，不会有性能问题）。"""
        doc = self.editor.document()
        if not cursor.hasSelection():
            lh = cursor.blockFormat().lineHeight()
            return {round(lh / 100.0, 2) if lh else None}
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        block = doc.findBlock(start)
        last_block = doc.findBlock(max(start, end - 1))
        heights = set()
        while block.isValid():
            lh = block.blockFormat().lineHeight()
            heights.add(round(lh / 100.0, 2) if lh else None)
            if len(heights) > 1:
                return heights
            if block == last_block:
                break
            block = block.next()
        return heights

    def update_toolbar_state(self):
        """让工具栏的字体 / 字号 / 行间距下拉框实时显示当前选区（或光标
        所在处）的实际格式，效果类似 Word：如果选区内存在多种不同的
        值，则对应下拉框显示为空白，而不是随便显示其中一种。"""
        if not hasattr(self, "editor") or not hasattr(self, "font_size_combo"):
            return
        cursor = self.editor.textCursor()

        sizes, families = self._selection_char_format_values(cursor)
        heights = self._selection_line_heights(cursor)

        self.font_size_combo.blockSignals(True)
        if len(sizes) == 1:
            size = next(iter(sizes))
            text = str(int(size)) if size == int(size) else f"{size:g}"
            self.font_size_combo.setCurrentIndex(self.font_size_combo.findText(text))
        else:
            self.font_size_combo.setCurrentIndex(-1)
        self.font_size_combo.blockSignals(False)

        self.font_family_combo.blockSignals(True)
        if len(families) == 1:
            family = next(iter(families))
            self.font_family_combo.setCurrentIndex(self.font_family_combo.findText(family))
        else:
            self.font_family_combo.setCurrentIndex(-1)
        self.font_family_combo.blockSignals(False)

        self.line_height_combo.blockSignals(True)
        if len(heights) == 1 and next(iter(heights)) is not None:
            text = f"{next(iter(heights)):.1f}"
            self.line_height_combo.setCurrentIndex(self.line_height_combo.findText(text))
        else:
            self.line_height_combo.setCurrentIndex(-1)
        self.line_height_combo.blockSignals(False)

    # ---------- 设置 ----------
    def open_settings(self):
        dlg = SettingsDialog(self.data.settings, self)
        dlg.setWindowModality(Qt.ApplicationModal)
        result = dlg.exec()
        if result == QDialog.Accepted:
            self.data.settings.update(dlg.values())
            self.apply_theme()
            self.refresh_auto_titles()
            self.update_all_stats()
            self.mark_dirty()
            self._save_now()
        elif result == QDialog.Rejected:
            # 取消不保存。
            pass

    def change_theme(self, index):
        theme = self.theme_combo.itemData(index)
        if not theme:
            return
        self.data.settings["theme"] = theme
        self.apply_theme()
        self._save_now()

    # ---------- 统计 ----------
    def count_text(self, text):
        return len("".join(text.split()))

    def node_words(self, node):
        # 全书字数统计 book_words() 会对树上每个节点都调用一次这个方法；
        # 之前每次都用 QTextDocument 重新解析一遍 HTML，即使这一章内容
        # 根本没变过。几百 KB、几百章的书，每次统计全书字数（切换章节、
        # 甚至打字停顿 300ms 后都会触发一次）就要把全书 HTML 重新解析一
        # 遍，这才是"打开/使用越用越慢"的真正原因。这里按章节缓存字数，
        # 只有 content 真正被改写时才会失效重新算（见 _word_count_cache
        # 的清空位置），没改过的章节直接用缓存，全书统计从 O(全书字数)
        # 降到只需重新算"真正变过的那一小部分"。
        if node._word_count_cache is None:
            node._word_count_cache = self.count_text(html_to_plain(node.content))
        return node._word_count_cache

    def book_words(self):
        total = 0
        def rec(nodes):
            nonlocal total
            for n in nodes:
                total += self.node_words(n)
                rec(n.children)
        if self.current_book:
            rec(self.current_book.tree)
        return total

    def update_all_stats(self):
        chapter = self.node_words(self.current_node) if self.current_node else 0

        book_id = self.current_book.id if self.current_book else None
        if book_id is not None and self._stats_warm_book_id != book_id:
            # 这本书这次打开/切换后，还没完整跑过一遍全书字数统计——每一章
            # 都要真的用 QTextDocument 解析一遍 HTML 才能拿到字数（之后就会
            # 命中每章各自的缓存，只有真正改过内容的章节才会重新解析，见
            # node_words() 的说明），这一整遍集中发生在刚打开/切换书籍的
            # 那一下，章节多、单章内容大（尤其是历史上粘贴进来、格式比较
            # 重的章节）就会觉得"刚打开有点卡"。这里先把当前章节的字数、
            # 状态栏正常显示出来，全书总字数改成放到下一轮事件循环里再
            # 算——不会卡住这次调用，用户能立刻看到内容和光标，全书总字数
            # 会在几乎感觉不到的延迟后自动补上。
            self._stats_warm_book_id = book_id
            self.word_label.setText(f"本章 {chapter:,}  ·  全文统计中…")
            if self.current_node:
                self.node_status.setText(f"当前：{self.display_title(self.current_node)}")
            else:
                self.node_status.setText("未选择节点")
            QTimer.singleShot(0, self.update_all_stats)
            return

        total = self.book_words() if self.current_book else 0

        settings = self.data.settings
        today_key = date.today().isoformat()
        if settings.get("today_date") != today_key:
            settings["today_date"] = today_key
            settings["today_words"] = 0

        # 今日字数采用“本次会话新增字数 + 存档的历史今日字数”。
        # 启动时以当前书籍总字数作为基准，避免把旧稿重复算入今日。
        if not hasattr(self, "_today_baseline"):
            self._today_baseline = total
            self._today_book_id = self.current_book.id if self.current_book else None

        if self.current_book and self._today_book_id == self.current_book.id:
            today_new = max(0, total - self._today_baseline)
        else:
            self._today_baseline = total
            self._today_book_id = self.current_book.id if self.current_book else None
            today_new = 0

        self.word_label.setText(
            f"本章 {chapter:,}  ·  今日新增 {today_new:,}  ·  全文 {total:,}"
        )
        if self.current_node:
            self.node_status.setText(f"当前：{self.display_title(self.current_node)}")
        else:
            self.node_status.setText("未选择节点")

    def update_cursor(self):
        c = self.editor.textCursor()
        self.cursor_label.setText(
            f"行 {c.blockNumber()+1} · 列 {c.positionInBlock()+1}"
        )

    # ---------- 导出 ----------
    def all_nodes(self):
        out = []
        def rec(nodes, level=0):
            for n in nodes:
                out.append((n, level))
                rec(n.children, level + 1)
        rec(self.current_book.tree if self.current_book else [])
        return out

    def export_txt(self):
        if not self.current_book:
            return
        self.save_current()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 TXT",
            os.path.join(APP_DIR, self.current_book.name + ".txt"),
            "TXT 文件 (*.txt)"
        )
        if not path:
            return
        lines = [self.current_book.name, "========", ""]
        for node, level in self.all_nodes():
            indent = "  " * level
            lines.append(indent + node.title)
            lines.append(indent + "-" * max(10, len(node.title)))
            text = html_to_plain(node.content).strip()
            if text:
                lines.extend(indent + x for x in text.splitlines())
            lines.append("")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出完成", f"TXT 已保存：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def export_epub(self):
        if not self.current_book:
            return
        self.save_current()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 EPUB",
            os.path.join(APP_DIR, self.current_book.name + ".epub"),
            "EPUB 文件 (*.epub)"
        )
        if not path:
            return
        try:
            nodes_levels = self.all_nodes()
            nodes = [n for n, _ in nodes_levels]
            if not nodes:
                nodes = [NovelNode("正文")]
                nodes_levels = [(nodes[0], 0)]
            book_id = new_id()
            manifest = []
            spine = []
            nav = []
            cur_level = -1
            for i, (n, level) in enumerate(nodes_levels, 1):
                href = f"text/chapter{i}.xhtml"
                manifest.append(
                    f'<item id="chapter{i}" href="{href}" media-type="application/xhtml+xml"/>'
                )
                spine.append(f'<itemref idref="chapter{i}"/>')
                if level > cur_level:
                    nav.append("<ol>" * (level - cur_level))
                elif level == cur_level:
                    nav.append("</li>")
                else:
                    nav.append("</li>" + "</ol></li>" * (cur_level - level))
                nav.append(f'<li><a href="{href}">{html.escape(n.title)}</a>')
                cur_level = level
            if cur_level >= 0:
                nav.append("</li>" + "</ol></li>" * cur_level + "</ol>")

            opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{book_id}</dc:identifier>
<dc:title>{html.escape(self.current_book.name)}</dc:title>
<dc:language>zh-CN</dc:language>
<meta property="dcterms:modified">{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
{''.join(manifest)}
</manifest>
<spine>{''.join(spine)}</spine>
</package>"""

            nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{html.escape(self.current_book.name)}</title></head>
<body><nav epub:type="toc"><h1>目录</h1>{''.join(nav)}</nav></body>
</html>"""

            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
                z.writestr(
                    "META-INF/container.xml",
                    """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
                )
                z.writestr("OEBPS/content.opf", opf)
                z.writestr("OEBPS/nav.xhtml", nav_xhtml)
                for i, n in enumerate(nodes, 1):
                    body = n.content or "<p></p>"
                    xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{html.escape(n.title)}</title>
<style>body{{font-family:Georgia,"Noto Serif CJK SC",serif;line-height:1.6;margin:5%;}}
p{{margin:0 0 .8em 0;}}</style></head>
<body><h1>{html.escape(n.title)}</h1>{body}</body></html>"""
                    z.writestr(f"OEBPS/text/chapter{i}.xhtml", xhtml)
            QMessageBox.information(self, "导出完成", f"EPUB 已保存：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def closeEvent(self, event):
        self.save_current()
        self.data.save()
        event.accept()


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
