# -*- coding: utf-8 -*-
"""Papyrus HTML 工具：富文本转纯文本、富文本 HTML 精简。"""

import re

from PySide6.QtGui import QTextDocument


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
