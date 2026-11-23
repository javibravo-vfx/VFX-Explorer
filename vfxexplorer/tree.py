# -*- coding: utf-8 -*-
"""Árbol de carpetas estilo XYplorer:
- líneas finas (sólidas o punteadas) que unen cada carpeta con su padre,
- cajitas ⊞/⊟ para expandir,
- "Tree Path Tracing": una línea de color más gruesa que va desde la raíz hasta la carpeta actual,
- opcional: las líneas de los hijos con el color de la carpeta padre."""

from PySide6.QtCore import Qt, QSize, QRect, QPersistentModelIndex
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QTreeView, QStyledItemDelegate, QStyleOptionViewItem

LINE_GRAY = QColor("#5f6368")
BOX_FILL = QColor("#2a2a2a")
BOX_EDGE = QColor("#7a7e85")
SIGN = QColor("#c8c8c8")


class FolderTreeDelegate(QStyledItemDelegate):
    """Ícono de carpeta con su color (manual o automático) y filas con altura cómoda."""

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

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 24))


class LinedTree(QTreeView):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setIndentation(18)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setItemDelegate(FolderTreeDelegate(app, self))
        self.setStyleSheet("QTreeView::branch { background: transparent; border-image: none; image: none; }")
        self._trace = []          # [QPersistentModelIndex] raíz → carpeta actual
        self._trace_path = ""

    # ---------------- path tracing
    def set_trace_path(self, path):
        """Marca el camino raíz → carpeta actual (como el Tree Path Tracing de XYplorer)."""
        chain = []
        ix = self.model().index(path) if path else None
        while ix is not None and ix.isValid():
            chain.insert(0, QPersistentModelIndex(ix))
            ix = ix.parent()
        self._trace = chain
        self._trace_path = path or ""
        self.viewport().update()

    def _cfg(self, k, default=None):
        v = self.app.cfg[k]
        return default if v is None else v

    def _trace_color(self):
        if self._cfg("tree_trace_color", "accent") == "folder" and self._trace_path:
            c = self.app.dir_color(self._trace_path)
            if c:
                return QColor(c)
        return QColor(self.app.accent())

    # ---------------- dibujo
    def _line_color(self, parent_index):
        if not self._cfg("tree_line_colors", True) or not parent_index.isValid():
            return LINE_GRAY
        c = self.app.dir_color(self.model().filePath(parent_index))
        if not c:
            return LINE_GRAY
        q = QColor(c)
        q.setAlpha(210)
        return q

    def drawBranches(self, p, rect, index):
        model = self.model()
        ind = self.indentation()
        chain = []
        a = index.parent()
        while a.isValid():
            chain.insert(0, a)
            a = a.parent()
        depth = len(chain)
        x0 = rect.right() - ind * (depth + 1) + 1
        cy = rect.center().y()
        top, bot = rect.top(), rect.bottom() + 1
        dotted = self._cfg("tree_lines_style", "solid") == "dotted"
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)

        def col_x(level):
            return x0 + level * ind + ind // 2

        def pen(col, w=1):
            return QPen(col, w, Qt.DotLine if (dotted and w == 1) else Qt.SolidLine, Qt.FlatCap)

        def has_next(ix):
            return ix.row() < model.rowCount(ix.parent()) - 1

        has_kids = model.hasChildren(index)
        stub = col_x(depth) - (5 if has_kids else -4)   # hasta la cajita, o hasta el ícono si no hay cajita

        # 1) líneas normales
        for lvl, anc in enumerate(chain[1:], start=1):
            if has_next(anc):
                x = col_x(lvl - 1)
                p.setPen(pen(self._line_color(anc.parent())))
                p.drawLine(x, top, x, bot)
        if depth > 0:
            x = col_x(depth - 1)
            p.setPen(pen(self._line_color(index.parent())))
            p.drawLine(x, top, x, bot if has_next(index) else cy)
            p.drawLine(x, cy, stub, cy)

        # 2) tree path tracing (por encima de las líneas)
        tr = self._trace
        tracing = bool(self._cfg("tree_trace", True)) and len(tr) > 1
        if tracing:
            tw = max(1, int(self._cfg("tree_trace_width", 2)))
            p.setPen(QPen(self._trace_color(), tw, Qt.SolidLine, Qt.FlatCap))
            path = [QPersistentModelIndex(c) for c in chain] + [QPersistentModelIndex(index)]
            for k in range(len(tr) - 1):
                if k >= len(path) or path[k] != tr[k]:
                    break                       # la fila no está dentro del subárbol de trace[k]
                x = col_x(k)
                if len(path) == k + 1:          # la fila ES trace[k]: la serpiente baja desde su cajita
                    if self.isExpanded(index):
                        p.drawLine(x, cy + 5, x, bot)
                    break
                mine, nxt = path[k + 1], tr[k + 1]
                if mine == nxt:
                    if len(path) == k + 2:      # la fila ES trace[k+1]: codo hacia su cajita
                        p.drawLine(x, top, x, cy)
                        p.drawLine(x, cy, stub, cy)
                    continue
                if mine.row() < nxt.row():      # hermano anterior: la línea pasa de largo
                    p.drawLine(x, top, x, bot)
                break

        # 3) cajita ⊞/⊟
        if has_kids:
            x = col_x(depth)
            box = QRect(x - 4, cy - 4, 9, 9)
            pix = QPersistentModelIndex(index)
            on_path = tracing and pix in tr
            p.setPen(QPen(QColor(self.app.accent()) if on_path else BOX_EDGE, 1))
            p.setBrush(BOX_FILL)
            p.drawRect(box.adjusted(0, 0, -1, -1))
            p.setPen(QPen(SIGN, 1))
            p.drawLine(box.left() + 2, cy, box.right() - 2, cy)
            if not self.isExpanded(index):
                p.drawLine(x, box.top() + 2, x, box.bottom() - 2)
        p.restore()
