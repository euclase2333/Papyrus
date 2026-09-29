# -*- coding: utf-8 -*-
"""Papyrus 数据模型：大纲节点、书、书架、数据管理器。"""

import os
import json
from datetime import datetime

from config import DATA_DIR, DATA_FILE, DEFAULT_SETTINGS, new_id


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
