# -*- coding: utf-8 -*-
"""Árbol de carpetas con líneas estilo XYplorer (punteadas, opcionalmente con el color de cada carpeta)."""

from PySide6.QtCore import Qt, QSize, QPointF, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QTreeView, QStyledItemDelegate, QStyleOptionViewItem

from .core import norm_key

LINE_GRAY = QColor("#4a4e56")


class FolderTreeDelegate(QStyledItemDelegate):
    """Ícono de carpeta con su color (manual o automático)."""

    def __init__(self, app, view):
        super().__init__(view)
        self.app = app

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.parent().isValid():
            c = self.app.dir_color(self.app.fs.filePath(index))
            option.icon = self.app.icons.folder_icon(c, 18)
            option.features |= QStyleOptionViewItem.HasDecoration
            option.decorationSize = QSize(16, 16)


class LinedTree(QTreeView):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setIndentation(16)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setItemDelegate(FolderTreeDelegate(app, self))
        self.setStyleSheet("QTreeView::branch { background: transparent; border-image: none; image: none; }")

    def _line_color(self, parent_index):
        if not self.app.cfg["tree_line_colors"] or not parent_index.isValid():
            return LINE_GRAY
        c = self.app.dir_color(self.model().filePath(parent_index))
        if not c:
            return LINE_GRAY
        q = QColor(c)
        q.setAlpha(200)
        return q

    def drawBranches(self, p, rect, index):
        model = self.model()
        ind = self.indentation()
        # cadena de ancestros: [raíz, ..., padre]
        chain = []
        a = index.parent()
        while a.isValid():
            chain.insert(0, a)
            a = a.parent()
        depth = len(chain)
        x0 = rect.right() - ind * (depth + 1) + 1
        cy = rect.center().y()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)

        def pen(col):
            pe = QPen(col, 1, Qt.DotLine)
            return pe

        def has_next(ix):
            par = ix.parent()
            return ix.row() < model.rowCount(par) - 1

        # líneas verticales de los ancestros que siguen teniendo hermanos abajo
        for lvl, anc in enumerate(chain[1:], start=1):
            if has_next(anc):
                x = x0 + lvl * ind + ind // 2 - ind
                p.setPen(pen(self._line_color(anc.parent())))
                p.drawLine(x, rect.top(), x, rect.bottom())
        # codo del ítem actual
        if depth > 0:
            x = x0 + depth * ind + ind // 2 - ind
            col = self._line_color(index.parent())
            p.setPen(pen(col))
            p.drawLine(x, rect.top(), x, cy if not has_next(index) else rect.bottom())
            p.drawLine(x, cy, x + ind // 2 + 2, cy)
        # triángulo de expandir
        if model.hasChildren(index):
            x = x0 + depth * ind + ind // 2
            open_ = self.isExpanded(index)
            p.setRenderHint(QPainter.Antialiasing, True)
            tri = QPainterPath()
            if open_:
                tri.moveTo(x - 4, cy - 2)
                tri.lineTo(x + 4, cy - 2)
                tri.lineTo(x, cy + 3)
            else:
                tri.moveTo(x - 2, cy - 4)
                tri.lineTo(x + 3, cy)
                tri.lineTo(x - 2, cy + 4)
            tri.closeSubpath()
            p.fillPath(tri, QColor("#c9ccd1") if open_ else QColor("#8b9099"))
            if depth > 0 and open_:
                pass
        p.restore()
