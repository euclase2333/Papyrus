# -*- coding: utf-8 -*-
"""Papyrus 自定义控件：圆角遮罩、圆角下拉框、字体下拉框。"""

import ui_icons

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPalette, QRegion, QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import QComboBox, QTextEdit, QTreeView


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


class NovelTreeView(QTreeView):
    """大纲树。

    Qt 默认的展开/收起箭头是由样式自己绘制的，完全不吃 QSS 的主题色，
    所以在黑夜 / 护眼主题下它始终是那个黑色小三角——和旁边已经跟着主题
    变色的书架 / 书籍 / 章节图标放在一起就很不协调。

    这里改成用 assets/icons 下的 chevron-down.svg（展开）和
    chevron-right.svg（收起），走跟其它图标完全相同的
    ui_icons.icon(name, color) 上色通道，所以切主题时它跟工具栏图标
    一起变色，用的还是同一份 SVG，不是另画的图标。
    """

    ARROW_SIZE = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arrow_color = "#222222"
        self._arrow_pixmaps = {}

    def set_arrow_color(self, color):
        if color == self._arrow_color and self._arrow_pixmaps:
            return
        self._arrow_color = color
        self._arrow_pixmaps = {}
        self.viewport().update()

    def _arrow_pixmap(self, expanded):
        pm = self._arrow_pixmaps.get(expanded)
        if pm is None:
            name = "chevron-down" if expanded else "chevron-right"
            # 按“物理像素”生成：14px 的逻辑尺寸在 125% / 150% 缩放下
            # 不是整数个物理像素，交给 QIcon 自己缩放会先取整再插值，
            # 箭头边缘就发虚。这里直接按 dpr 算出整数物理尺寸再画 1:1。
            dpr = self.devicePixelRatioF() or 1.0
            px = max(1, int(round(self.ARROW_SIZE * dpr)))
            pm = ui_icons.icon(name, self._arrow_color).pixmap(px, px)
            pm.setDevicePixelRatio(dpr)
            self._arrow_pixmaps[expanded] = pm
        return pm

    def drawBranches(self, painter, rect, index):
        # 不调用父类：父类画的正是那个不跟随主题的默认箭头。
        # 没有子节点的行本来就没有箭头，直接跳过。
        if not index.isValid() or self.model() is None:
            return
        if self.model().rowCount(index) == 0:
            return
        pm = self._arrow_pixmap(self.isExpanded(index))
        if pm is None or pm.isNull():
            return

        indent = self.indentation()
        dpr = pm.devicePixelRatio() or 1.0
        width = pm.width() / dpr
        height = pm.height() / dpr
        # 箭头画在这一行对应的缩进格里（Qt 默认也是画在这格），
        # rect 是整行从最左边到内容区左边缘的宽度。
        x = rect.right() - indent + (indent - width) / 2.0
        y = rect.top() + (rect.height() - height) / 2.0
        # 关键：把绘制位置对齐到整物理像素。否则在 125%/150% 这类缩放下，
        # 箭头会落在半个物理像素上被插值，看起来像被压扁/扭曲；而且这个
        # 偏移随滚动位置变化，所以同一行滚动后又会变正常。
        x = round(x * dpr) / dpr
        y = round(y * dpr) / dpr
        painter.drawPixmap(
            QRectF(x, y, width, height),
            pm,
            QRectF(0, 0, pm.width(), pm.height()),
        )


class NovelTextEdit(QTextEdit):
    """正文编辑器：给引用块画左侧竖条，并把引用文字调淡。

    Qt 的段落格式 QTextBlockFormat 只有背景和四边边距，没有边框属性
    （边框只在 QTextFrameFormat 上，而且是四边一起的框），所以 CSS 那种
    border-left 没法用格式表达，竖条只能在这里自己画。

    "哪一段是引用"沿用项目里既有的约定：左右边距 > 0。quote() 按钮、
    粘贴带引用的富文本设的都是这组边距，所以老稿不用迁移，加载出来就是
    新样式；也没有新增任何数据字段。
    """

    # 竖条用各主题的强调色（和页签顶部那条线同一个值）
    QUOTE_BAR_COLORS = {"day": "#3B6FE0", "night": "#5B8DEF", "green": "#3F7D3D"}
    # 引用文字用各主题的次要文字色（和对话框提示文字同一个值）
    QUOTE_TEXT_COLORS = {"day": "#6B7280", "night": "#AAB2C0", "green": "#4A5A4F"}

    BAR_X = 6
    BAR_WIDTH = 3

    # 引用段落使用的边距。这组数值同时是“这是引用”的标记，
    # quote() 按钮和“粘贴带引用的富文本”都用它。
    QUOTE_LEFT_MARGIN = 28
    QUOTE_RIGHT_MARGIN = 20
    QUOTE_TOP_MARGIN = 6
    QUOTE_BOTTOM_MARGIN = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "day"

    def set_theme(self, theme):
        if theme not in self.QUOTE_BAR_COLORS:
            theme = "day"
        if theme != self._theme:
            self._theme = theme
            self.viewport().update()

    @staticmethod
    def is_quote_block(block):
        fmt = block.blockFormat()
        return fmt.leftMargin() > 0 or fmt.rightMargin() > 0

    @staticmethod
    def selected_blocks(cursor):
        """光标所在（或跨选区）的所有段落。"""
        doc = cursor.document()
        start = doc.findBlock(cursor.selectionStart())
        end = doc.findBlock(cursor.selectionEnd())
        # 选区刚好停在下一段开头（比如选中了一整段的换行符）时，
        # 下一段不应该被算进来。
        if (cursor.hasSelection() and end.isValid() and end != start
                and end.position() == cursor.selectionEnd()):
            end = end.previous()
        blocks = []
        block = start
        while block.isValid():
            blocks.append(block)
            if block == end:
                break
            block = block.next()
        return blocks

    def set_quote(self, blocks, on):
        """把给定的段落设成引用 / 取消引用。

        边距是“这是引用”的唯一标记（竖条和淡色都由它推导），所以取消引用
        只要把边距归零、再把字符颜色清回默认即可。整段操作包在一个撤销块里，
        连续切换几次只算一步，不会在撤销栈里堆一堆。
        """
        color = QColor(self.QUOTE_TEXT_COLORS.get(self._theme, "#6B7280"))
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        try:
            for block in blocks:
                block_cursor = QTextCursor(block)
                fmt = block.blockFormat()
                if on:
                    fmt.setLeftMargin(self.QUOTE_LEFT_MARGIN)
                    fmt.setRightMargin(self.QUOTE_RIGHT_MARGIN)
                    fmt.setTopMargin(self.QUOTE_TOP_MARGIN)
                    fmt.setBottomMargin(self.QUOTE_BOTTOM_MARGIN)
                else:
                    fmt.setLeftMargin(0)
                    fmt.setRightMargin(0)
                    fmt.setTopMargin(0)
                    fmt.setBottomMargin(0)
                block_cursor.setBlockFormat(fmt)

                text_cursor = QTextCursor(block)
                text_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_fmt = QTextCharFormat()
                if on:
                    char_fmt.setForeground(color)
                else:
                    # 不能用 clearForeground()：mergeCharFormat 只合并“已设置”的
                    # 属性，清空前景色等于什么都不改，淡色会留在文字上。
                    # 这里显式写回当前主题的正文色，看上去就和普通段落一致了。
                    char_fmt.setForeground(self.palette().color(QPalette.ColorRole.Text))
                text_cursor.mergeCharFormat(char_fmt)
        finally:
            edit.endEditBlock()

    def apply_quote_style(self):
        """把引用段落里的文字调成当前主题的淡色。

        这个颜色是"渲染态"的，不写进正文：加载和切主题时都会重新套一遍，
        因为 load_node() 会把正文里所有 color 剥掉（那是为了让主题能生效）。
        """
        doc = self.document()
        color = QColor(self.QUOTE_TEXT_COLORS.get(self._theme, "#6B7280"))
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        try:
            block = doc.begin()
            while block.isValid():
                if self.is_quote_block(block):
                    block_cursor = QTextCursor(block)
                    block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                    fmt = QTextCharFormat()
                    fmt.setForeground(color)
                    block_cursor.mergeCharFormat(fmt)
                block = block.next()
        finally:
            cursor.endEditBlock()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        bar_color = QColor(self.QUOTE_BAR_COLORS.get(self._theme, "#3B6FE0"))
        scroll_y = self.verticalScrollBar().value()
        layout = self.document().documentLayout()
        viewport_height = self.viewport().height()

        # 从视口左上角所在的段落开始，只往下画到视口底部为止，
        # 不用遍历整篇文档。
        block = self.cursorForPosition(QPoint(1, 1)).block()
        while block.isValid():
            rect = layout.blockBoundingRect(block)
            top = rect.top() - scroll_y
            if top > viewport_height:
                break
            # 空段落不画竖条：删掉引用里的文字后，段落本身还留着，
            # 但已经没有内容可以“引用”了，留一条孤零零的竖线很怪。
            if (block.isVisible() and self.is_quote_block(block)
                    and block.text().strip() and rect.bottom() - scroll_y > 0):
                painter.fillRect(
                    QRectF(self.BAR_X, top + 3, self.BAR_WIDTH,
                           max(4.0, rect.height() - 6)),
                    bar_color,
                )
            block = block.next()
        painter.end()


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
