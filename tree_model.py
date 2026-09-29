# -*- coding: utf-8 -*-
"""Papyrus 大纲树模型。"""

import ui_icons

from PySide6.QtCore import (
    Qt, QModelIndex, QAbstractItemModel, QMimeData, QByteArray
)

from models import NovelBook, NovelNode, NovelShelf


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
