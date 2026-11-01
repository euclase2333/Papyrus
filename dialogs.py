# -*- coding: utf-8 -*-
"""Papyrus 对话框：设置对话框、全局搜索对话框。"""

import ui_icons

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QSpinBox, QCheckBox, QComboBox, QTabWidget,
    QListWidget, QListWidgetItem, QPushButton, QButtonGroup, QSizePolicy
)

from html_utils import html_to_plain


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


SCOPE_ALL = "all"
SCOPE_CHAPTER = "chapter"


class _ScopeOption(QPushButton):
    """搜索范围里的一个选项：前面的“圆圈”用 circle-check / circle-check-big
    两个图标画——未选中是小对勾圆圈，选中后换成大对勾圆圈。用可勾选的
    QPushButton 而不是 QRadioButton，是为了不出现 Qt 自带的圆点标记，
    而且图标和文字之间的间距由按钮自己排，比 QToolButton 稳定。"""

    def __init__(self, text, color_off, color_on, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SearchScopeRow")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(20, 20))
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._color_off = color_off
        self._color_on = color_on
        self.toggled.connect(self._sync_icon)
        self._sync_icon(self.isChecked())

    def _sync_icon(self, checked):
        name = "circle-check-big" if checked else "circle-check"
        self.setIcon(ui_icons.icon(name, self._color_on if checked else self._color_off))


class GlobalSearchDialog(QDialog):
    """全局搜索。

    两种范围：
    - “搜索全部书籍”：行为跟以前完全一样，一条结果对应一个节点，
      双击切到该章节并关闭对话框；
    - “仅当前章节”：在当前编辑器的文档里逐处查找，结果一条对应一次
      命中（带行号和上下文），单击即跳到该位置并选中关键词，可以用
      “上一个 / 下一个”连续跳，对话框不关闭。
    """

    def __init__(self, books, host=None, parent=None):
        super().__init__(parent)
        self.books = books
        self.host = host
        self.matches = []          # 本页模式下：[(start, length, 行号, 片段), ...]
        self._syncing = False      # 填列表时抑制 currentItemChanged 的自动跳转
        self.setWindowTitle("全局搜索")
        self.resize(760, 540)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        self.query = QLineEdit()
        self.query.setPlaceholderText("搜索关键词……")
        self.query.returnPressed.connect(self._on_return_pressed)
        root.addWidget(self.query)

        # 搜索范围：两个选项排在同一排
        color_off, color_on = self._scope_colors()
        scope_row = QWidget()
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(4)

        self.opt_all = _ScopeOption("搜索全部书籍", color_off, color_on)
        self.opt_chapter = _ScopeOption("仅当前章节", color_off, color_on)
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        self.scope_group.addButton(self.opt_all)
        self.scope_group.addButton(self.opt_chapter)
        scope_layout.addWidget(self.opt_all)
        scope_layout.addWidget(self.opt_chapter)
        scope_layout.addStretch(1)
        root.addWidget(scope_row)

        self.results = QListWidget()
        self.results.itemActivated.connect(self._on_item_activated)
        self.results.currentItemChanged.connect(self._on_current_changed)
        root.addWidget(self.results, 1)

        bottom = QHBoxLayout()
        self.prev_btn = QPushButton("上一个")
        self.next_btn = QPushButton("下一个")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(self.prev_btn)
        bottom.addWidget(self.next_btn)
        bottom.addStretch(1)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        # “仅当前章节”在没打开章节时不可选（否则会是永远为空的结果列表）
        if not self._has_current_chapter():
            self.opt_chapter.setEnabled(False)
            self.opt_chapter.setToolTip("当前没有打开任何章节")

        # 默认选中“搜索全部书籍”
        self.opt_all.setChecked(True)
        self.scope_group.buttonToggled.connect(self._on_scope_toggled)
        self.query.textChanged.connect(self._refresh)
        self._refresh("")
        self.query.setFocus()

    # ---------- 范围 ----------
    def _scope_colors(self):
        """未选中 / 选中两种状态下圆圈图标的颜色，按当前主题取，
        强调色沿用各主题章节标签页顶部那条线的颜色。"""
        theme = "day"
        if self.host is not None and hasattr(self.host, "data"):
            theme = self.host.data.settings.get("theme", "day")
        return {
            "day": ("#4A4F58", "#3B6FE0"),
            "night": ("#AAB2C0", "#5B8DEF"),
            "green": ("#33493C", "#3F7D3D"),
        }.get(theme, ("#4A4F58", "#3B6FE0"))

    def _has_current_chapter(self):
        return getattr(self.host, "current_node", None) is not None

    @property
    def scope(self):
        return SCOPE_CHAPTER if self.opt_chapter.isChecked() else SCOPE_ALL

    def _on_scope_toggled(self, button, checked):
        if checked:
            self._refresh(self.query.text())

    # ---------- 结果列表 ----------
    def _refresh(self, text):
        self.results.clear()
        self.matches = []
        if self.scope == SCOPE_CHAPTER:
            self._search_chapter(text)
        else:
            self._search_all(text)
            if self.host is not None:          # 离开本页模式时清掉正文里的高亮
                self.host.clear_search_highlight()
        self._update_nav_enabled()

    def _search_all(self, text):
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

    def _search_chapter(self, text):
        q = text.strip()
        if not q or self.host is None:
            return
        self.matches = self.host.chapter_matches(q)
        for start, length, line_no, snippet in self.matches:
            item = QListWidgetItem(f"行 {line_no}　{snippet}")
            item.setData(Qt.UserRole, (start, length))
            self.results.addItem(item)
        self.host.highlight_search_matches(q)
        if self.matches:
            # 输入时就跟着跳到第一处，和 TXT 查找的行为一致；
            # 此时 _syncing 为真，避免 setCurrentRow 再触发一次重复跳转。
            self._syncing = True
            self.results.setCurrentRow(0)
            self._syncing = False
            self._jump_row(0)

    def _update_nav_enabled(self):
        usable = self.scope == SCOPE_CHAPTER and bool(self.matches)
        self.prev_btn.setEnabled(usable)
        self.next_btn.setEnabled(usable)

    # ---------- 跳转 ----------
    def _jump_row(self, row):
        if not (0 <= row < len(self.matches)) or self.host is None:
            return
        start, length = self.matches[row][0], self.matches[row][1]
        self.host.jump_to_match(start, length)

    def _on_current_changed(self, current, previous):
        if self._syncing or self.scope != SCOPE_CHAPTER or current is None:
            return
        self._jump_row(self.results.row(current))

    def _on_item_activated(self, item):
        if self.scope == SCOPE_CHAPTER:
            self._jump_row(self.results.row(item))
        else:
            # “搜索全部书籍”保持原样：双击选中结果即关闭，由主窗口切到该章节。
            self.accept()

    def _step(self, delta):
        if self.scope != SCOPE_CHAPTER or not self.matches:
            return
        row = self.results.currentRow()
        row = 0 if row < 0 else (row + delta) % len(self.matches)
        self.results.setCurrentRow(row)

    def _on_return_pressed(self):
        if self.scope == SCOPE_CHAPTER:
            self._step(1)
