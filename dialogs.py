# -*- coding: utf-8 -*-
"""Papyrus 对话框：设置对话框、全局搜索对话框。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QSpinBox, QCheckBox, QComboBox, QTabWidget,
    QListWidget, QListWidgetItem
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
