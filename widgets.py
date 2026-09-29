# -*- coding: utf-8 -*-
"""Papyrus 自定义控件：圆角遮罩、圆角下拉框、字体下拉框。"""

import ui_icons

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QComboBox


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
