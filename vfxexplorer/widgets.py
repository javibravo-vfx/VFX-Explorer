# -*- coding: utf-8 -*-
"""Íconos dibujados, delegate de la grilla, breadcrumb, diálogos y tema oscuro."""

import os
import math

from PySide6.QtCore import Qt, Signal, QSize, QRect, QRectF, QPointF, QTimer
from PySide6.QtGui import (QPixmap, QPainter, QColor, QIcon, QPainterPath, QFont, QPen, QPalette,
                           QFontMetrics)
from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QWidget, QHBoxLayout, QToolButton, QLineEdit,
                               QMenu, QStackedLayout, QDialog, QFormLayout, QVBoxLayout, QLabel, QListWidget,
                               QDialogButtonBox, QComboBox, QSpinBox, QPushButton, QFileDialog, QCheckBox,
                               QTabWidget, QCompleter, QSizePolicy)

from .core import IS_WIN, human_size, fwd, find_tool
from .imaging import COLORSPACES
from .models import ROLE_ENTRY
from .fileops import split_head, valid_name

CAT_COLORS = {
    "dir": "#8a96a8", "seq": "#4ea1ff", "exr": "#ff9f43", "video": "#b072ff",
    "image": "#3ecf8e", "model": "#f06595", "other": "#7d8590",
}
TAG_COLORS = [
    ("Rojo", "#e5484d"), ("Naranja", "#f76b15"), ("Amarillo", "#f5d90a"), ("Verde", "#30a46c"),
    ("Celeste", "#0ac5f5"), ("Azul", "#3e63dd"), ("Violeta", "#8e4ec6"), ("Rosa", "#e93d82"),
    ("Gris", "#8b8d98"),
]
ACCENT = "#4cc2ff"          # acento de Windows 11 (modo oscuro)


def cat_color(e):
    return CAT_COLORS["exr"] if e.ext == ".exr" else CAT_COLORS.get(e.cat, CAT_COLORS["other"])


# ----------------------------------------------------------------------------
# Íconos
# ----------------------------------------------------------------------------

FOLDER_COLORS = {"yellow": "#f4c443", "blue": "#8a96a8"}


class Icons:
    def __init__(self):
        self._c = {}
        self.default_folder = FOLDER_COLORS["yellow"]

    def set_default_folder(self, name_or_hex):
        self.default_folder = FOLDER_COLORS.get(name_or_hex, name_or_hex) or FOLDER_COLORS["yellow"]
        self._c.clear()

    def drive(self, kind="local", size=48):
        key = ("drv", kind, size)
        if key in self._c:
            return self._c[key]
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        s = size
        body = QRectF(s * .08, s * .40, s * .84, s * .34)
        top = QPainterPath()
        top.moveTo(s * .18, s * .40)
        top.lineTo(s * .28, s * .24)
        top.lineTo(s * .72, s * .24)
        top.lineTo(s * .82, s * .40)
        top.closeSubpath()
        p.fillPath(top, QColor("#d9d9d9"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#9a9a9a"))
        p.drawRoundedRect(body, s * .05, s * .05)
        p.setBrush(QColor("#5f5f5f"))
        p.drawRoundedRect(body.adjusted(s * .03, s * .03, -s * .03, -s * .03), s * .04, s * .04)
        p.setBrush(QColor("#46d160"))
        p.drawEllipse(QPointF(s * .2, s * .57), s * .035, s * .035)
        if kind == "network":
            p.setBrush(QColor("#46d160"))
            p.drawRoundedRect(QRectF(s * .14, s * .80, s * .72, s * .08), 2, 2)
        elif kind == "removable":
            p.setBrush(QColor("#4cc2ff"))
            p.drawRoundedRect(QRectF(s * .40, s * .80, s * .20, s * .08), 2, 2)
        p.end()
        self._c[key] = pm
        return pm

    def drive_icon(self, kind="local", size=18):
        key = ("drvi", kind, size)
        if key not in self._c:
            self._c[key] = QIcon(self.drive(kind, max(size, 18)))
        return self._c[key]

    def folder(self, color=None, size=20):
        key = ("f", color, size)
        if key in self._c:
            return self._c[key]
        base = QColor(color or self.default_folder)
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        s = size
        back = QPainterPath()
        back.addRoundedRect(QRectF(s * .06, s * .16, s * .40, s * .20), s * .05, s * .05)
        back.addRoundedRect(QRectF(s * .06, s * .24, s * .88, s * .62), s * .08, s * .08)
        p.fillPath(back, base.darker(140))
        front = QPainterPath()
        front.addRoundedRect(QRectF(s * .06, s * .34, s * .88, s * .52), s * .08, s * .08)
        p.fillPath(front, base)
        p.end()
        self._c[key] = pm
        return pm

    def folder_icon(self, color=None, size=20):
        key = ("fi", color, size)
        if key not in self._c:
            self._c[key] = QIcon(self.folder(color, size))
        return self._c[key]

    def badge(self, e, size=18):
        cat, color = e.cat, cat_color(e)
        key = ("b", cat, color, size)
        if key in self._c:
            return self._c[key]
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        c = QColor(color)
        r = QRectF(size * .12, size * .1, size * .76, size * .8)
        if cat == "seq":
            p.setBrush(c.darker(170))
            p.drawRoundedRect(r.adjusted(size * .16, -size * .04, size * .04, -size * .16), 2, 2)
            p.setBrush(c.darker(130))
            p.drawRoundedRect(r.adjusted(size * .08, 0, 0, -size * .08), 2, 2)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(0, size * .1, -size * .1, 0), 2, 2)
        elif cat == "video":
            p.setBrush(c)
            p.drawRoundedRect(r, 3, 3)
            tri = QPainterPath()
            cx, cy = size / 2, size / 2
            tri.moveTo(cx - size * .12, cy - size * .17)
            tri.lineTo(cx + size * .18, cy)
            tri.lineTo(cx - size * .12, cy + size * .17)
            tri.closeSubpath()
            p.fillPath(tri, QColor("#1e1f22"))
        elif cat == "model":
            p.setBrush(c)
            cube = QPainterPath()
            s = size
            cube.moveTo(s * .5, s * .1)
            cube.lineTo(s * .88, s * .3)
            cube.lineTo(s * .88, s * .72)
            cube.lineTo(s * .5, s * .92)
            cube.lineTo(s * .12, s * .72)
            cube.lineTo(s * .12, s * .3)
            cube.closeSubpath()
            p.drawPath(cube)
        else:
            p.setBrush(c)
            p.drawRoundedRect(r, 3, 3)
        p.end()
        self._c[key] = QIcon(pm)
        return self._c[key]

    def swatch(self, color, size=14):
        key = ("sw", color, size)
        if key not in self._c:
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 3, 3)
            p.end()
            self._c[key] = QIcon(pm)
        return self._c[key]

    def glyph(self, kind, size=20, color="#c9ccd1"):
        key = ("g", kind, size, color)
        if key in self._c:
            return self._c[key]
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), size * .1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        s = size
        path = QPainterPath()
        if kind == "back":
            path.moveTo(s * .78, s * .5); path.lineTo(s * .22, s * .5)
            path.moveTo(s * .45, s * .26); path.lineTo(s * .22, s * .5); path.lineTo(s * .45, s * .74)
        elif kind == "fwd":
            path.moveTo(s * .22, s * .5); path.lineTo(s * .78, s * .5)
            path.moveTo(s * .55, s * .26); path.lineTo(s * .78, s * .5); path.lineTo(s * .55, s * .74)
        elif kind == "up":
            path.moveTo(s * .5, s * .8); path.lineTo(s * .5, s * .22)
            path.moveTo(s * .26, s * .45); path.lineTo(s * .5, s * .22); path.lineTo(s * .74, s * .45)
        elif kind == "reload":
            p.drawArc(QRectF(s * .2, s * .2, s * .6, s * .6), 40 * 16, 290 * 16)
            path.moveTo(s * .80, s * .18); path.lineTo(s * .80, s * .40); path.lineTo(s * .58, s * .40)
        elif kind == "gear":
            p.drawEllipse(QPointF(s / 2, s / 2), s * .16, s * .16)
            for i in range(8):
                a = i * math.pi / 4
                p.drawLine(QPointF(s / 2 + math.cos(a) * s * .26, s / 2 + math.sin(a) * s * .26),
                           QPointF(s / 2 + math.cos(a) * s * .38, s / 2 + math.sin(a) * s * .38))
        elif kind == "dual":
            p.drawRoundedRect(QRectF(s * .12, s * .2, s * .76, s * .6), 2, 2)
            path.moveTo(s * .5, s * .2); path.lineTo(s * .5, s * .8)
        elif kind == "grid":
            for x in (.18, .54):
                for y in (.18, .54):
                    p.drawRect(QRectF(s * x, s * y, s * .28, s * .28))
        elif kind == "list":
            for y in (.28, .5, .72):
                path.moveTo(s * .18, s * y); path.lineTo(s * .82, s * y)
        elif kind == "plus":
            path.moveTo(s * .5, s * .22); path.lineTo(s * .5, s * .78)
            path.moveTo(s * .22, s * .5); path.lineTo(s * .78, s * .5)
        elif kind == "pc":
            p.drawRoundedRect(QRectF(s * .12, s * .18, s * .76, s * .50), 2, 2)
            path.moveTo(s * .5, s * .68); path.lineTo(s * .5, s * .80)
            path.moveTo(s * .32, s * .82); path.lineTo(s * .68, s * .82)
        elif kind == "branch":
            path.moveTo(s * .25, s * .18); path.lineTo(s * .25, s * .82)
            path.moveTo(s * .25, s * .40); path.lineTo(s * .55, s * .40)
            path.moveTo(s * .25, s * .70); path.lineTo(s * .55, s * .70)
            p.drawEllipse(QPointF(s * .68, s * .40), s * .09, s * .09)
            p.drawEllipse(QPointF(s * .68, s * .70), s * .09, s * .09)
        elif kind == "play":
            p.setBrush(QColor(color))
            path.moveTo(s * .3, s * .2); path.lineTo(s * .8, s * .5); path.lineTo(s * .3, s * .8); path.closeSubpath()
        elif kind == "pause":
            p.setBrush(QColor(color))
            p.drawRect(QRectF(s * .28, s * .22, s * .14, s * .56)); p.drawRect(QRectF(s * .58, s * .22, s * .14, s * .56))
        elif kind == "prev":
            path.moveTo(s * .25, s * .22); path.lineTo(s * .25, s * .78)
            path.moveTo(s * .75, s * .22); path.lineTo(s * .38, s * .5); path.lineTo(s * .75, s * .78)
        elif kind == "next":
            path.moveTo(s * .75, s * .22); path.lineTo(s * .75, s * .78)
            path.moveTo(s * .25, s * .22); path.lineTo(s * .62, s * .5); path.lineTo(s * .25, s * .78)
        elif kind == "loop":
            p.drawArc(QRectF(s * .16, s * .26, s * .68, s * .48), 30 * 16, 300 * 16)
            path.moveTo(s * .70, s * .16); path.lineTo(s * .80, s * .30); path.lineTo(s * .64, s * .36)
        elif kind == "library":
            for i, x in enumerate((.18, .36, .54)):
                p.drawRect(QRectF(s * x, s * (.22 + (i == 2) * .06), s * .12, s * .58))
            path.moveTo(s * .70, s * .26); path.lineTo(s * .84, s * .78)
        elif kind == "cut":
            p.drawEllipse(QPointF(s * .32, s * .72), s * .12, s * .12)
            p.drawEllipse(QPointF(s * .68, s * .72), s * .12, s * .12)
            path.moveTo(s * .40, s * .63); path.lineTo(s * .68, s * .16)
            path.moveTo(s * .60, s * .63); path.lineTo(s * .32, s * .16)
        elif kind == "copy":
            p.drawRoundedRect(QRectF(s * .34, s * .30, s * .44, s * .52), 2, 2)
            path.moveTo(s * .24, s * .70); path.lineTo(s * .24, s * .22); path.quadTo(s * .24, s * .16, s * .30, s * .16)
            path.lineTo(s * .62, s * .16)
        elif kind == "paste":
            p.drawRoundedRect(QRectF(s * .22, s * .22, s * .56, s * .62), 2, 2)
            p.drawRoundedRect(QRectF(s * .38, s * .14, s * .24, s * .14), 1.5, 1.5)
        elif kind == "rename":
            p.drawRoundedRect(QRectF(s * .14, s * .32, s * .72, s * .36), 2, 2)
            path.moveTo(s * .62, s * .22); path.lineTo(s * .62, s * .78)
            path.moveTo(s * .54, s * .22); path.lineTo(s * .70, s * .22)
            path.moveTo(s * .54, s * .78); path.lineTo(s * .70, s * .78)
        elif kind == "trash":
            path.moveTo(s * .20, s * .28); path.lineTo(s * .80, s * .28)
            path.moveTo(s * .40, s * .28); path.lineTo(s * .42, s * .18); path.lineTo(s * .58, s * .18)
            path.lineTo(s * .60, s * .28)
            path.moveTo(s * .27, s * .28); path.lineTo(s * .32, s * .82); path.lineTo(s * .68, s * .82)
            path.lineTo(s * .73, s * .28)
        elif kind == "newfolder":
            path.moveTo(s * .12, s * .28); path.lineTo(s * .38, s * .28); path.lineTo(s * .46, s * .36)
            path.lineTo(s * .86, s * .36); path.lineTo(s * .86, s * .50)
            path.moveTo(s * .50, s * .78); path.lineTo(s * .12, s * .78); path.lineTo(s * .12, s * .28)
            path.moveTo(s * .72, s * .56); path.lineTo(s * .72, s * .88)
            path.moveTo(s * .56, s * .72); path.lineTo(s * .88, s * .72)
        elif kind == "sort":
            path.moveTo(s * .32, s * .82); path.lineTo(s * .32, s * .18)
            path.moveTo(s * .18, s * .32); path.lineTo(s * .32, s * .18); path.lineTo(s * .46, s * .32)
            path.moveTo(s * .68, s * .18); path.lineTo(s * .68, s * .82)
            path.moveTo(s * .54, s * .68); path.lineTo(s * .68, s * .82); path.lineTo(s * .82, s * .68)
        elif kind == "filter":
            path.moveTo(s * .16, s * .22); path.lineTo(s * .84, s * .22); path.lineTo(s * .58, s * .52)
            path.lineTo(s * .58, s * .80); path.lineTo(s * .42, s * .72); path.lineTo(s * .42, s * .52)
            path.closeSubpath()
        elif kind == "more":
            p.setBrush(QColor(color))
            for x in (.25, .5, .75):
                p.drawEllipse(QPointF(s * x, s * .5), s * .06, s * .06)
        elif kind == "details":
            p.drawRoundedRect(QRectF(s * .14, s * .2, s * .72, s * .6), 2, 2)
            path.moveTo(s * .58, s * .2); path.lineTo(s * .58, s * .8)
        elif kind == "search":
            p.drawEllipse(QPointF(s * .44, s * .42), s * .22, s * .22)
            path.moveTo(s * .60, s * .58); path.lineTo(s * .82, s * .80)
        elif kind == "chevdown":
            path.moveTo(s * .30, s * .40); path.lineTo(s * .50, s * .60); path.lineTo(s * .70, s * .40)
        elif kind == "pin":
            path.moveTo(s * .5, s * .62); path.lineTo(s * .5, s * .88)
            path.moveTo(s * .3, s * .62); path.lineTo(s * .7, s * .62)
            path.moveTo(s * .38, s * .62); path.lineTo(s * .40, s * .16); path.lineTo(s * .60, s * .16)
            path.lineTo(s * .62, s * .62)
        elif kind == "home":
            path.moveTo(s * .16, s * .48); path.lineTo(s * .5, s * .18); path.lineTo(s * .84, s * .48)
            path.moveTo(s * .26, s * .40); path.lineTo(s * .26, s * .82); path.lineTo(s * .74, s * .82)
            path.lineTo(s * .74, s * .40)
        elif kind == "folder":
            path.moveTo(s * .14, s * .3); path.lineTo(s * .4, s * .3); path.lineTo(s * .48, s * .38)
            path.lineTo(s * .86, s * .38); path.lineTo(s * .86, s * .76); path.lineTo(s * .14, s * .76)
            path.closeSubpath()
        p.drawPath(path)
        p.end()
        self._c[key] = QIcon(pm)
        return self._c[key]

    def app_icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i, col in enumerate(("#1f6feb", "#3b8cff", "#6db1ff")):
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(8 + i * 7, 22 - i * 7, 36, 30), 5, 5)
        p.setBrush(QColor("#ff9f43"))
        p.drawEllipse(QPointF(46, 46), 9, 9)
        p.end()
        return QIcon(pm)


# ----------------------------------------------------------------------------
# Delegate de la grilla
# ----------------------------------------------------------------------------

class GridDelegate(QStyledItemDelegate):
    TEXT_H = 50

    def __init__(self, app, view):
        super().__init__(view)
        self.app, self.view = app, view

    def sizeHint(self, option, index):
        e = index.data(ROLE_ENTRY)
        if e is not None and e.kind == "header":
            return QSize(max(200, self.view.viewport().width() - 10), 34)
        if e is not None and e.kind == "drive":
            return QSize(380, 92)
        ts = self.view.iconSize().width()
        return QSize(ts + 16, int(ts * 9 / 16) + 16 + self.TEXT_H)

    def paint_drive(self, p, opt, e):
        """Tarjeta de disco como la de «Este equipo» de Windows 11: ícono, nombre, barra de uso y libre/total."""
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(4, 4, -4, -4)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            p.setPen(QPen(QColor("#5a5a5a"), 1) if sel else Qt.NoPen)
            p.setBrush(QColor("#333333") if sel else QColor("#262626"))
            p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        ic = self.app.icons.drive(getattr(e, "drive_kind", "local"), 56)
        p.drawPixmap(r.x() + 6, r.y() + (r.height() - 56) // 2, ic)
        x = r.x() + 74
        w = r.right() - x - 8
        f = QFont(opt.font)
        f.setPointSizeF(9.5)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(QColor("#f3f3f3"))
        p.drawText(QRect(x, r.y() + 10, w, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(e.name, Qt.ElideMiddle, w))
        total, free = e.size or 0, getattr(e, "free", 0) or 0
        used = (total - free) / total if total else 0
        bar = QRectF(x, r.y() + 14 + fm.height(), w, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e6e6e6"))
        p.drawRect(bar)
        p.setBrush(QColor("#da3b3b") if used > 0.9 else QColor("#2a8de8"))
        p.drawRect(QRectF(bar.x(), bar.y(), bar.width() * used, bar.height()))
        f2 = QFont(opt.font)
        f2.setPointSizeF(8.6)
        p.setFont(f2)
        p.setPen(QColor("#c5c5c5"))
        txt = f"{human_size(free)} libres de {human_size(total)}" if total else "sin acceso"
        p.drawText(QRect(x, int(bar.bottom()) + 4, w, 18), Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.restore()

    def paint_header(self, p, opt, e):
        r = opt.rect.adjusted(6, 6, -6, -2)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(opt.font)
        f.setPointSizeF(9.5)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        fp = self.app.icons.folder(None if e.name.startswith("(") else "#e8b84a", 16) \
            if self.view.model().sourceModel().group_mode == "folder" else None
        x = r.x()
        if fp is not None:
            p.drawPixmap(x, r.center().y() - 8, fp)
            x += 22
        p.setPen(QColor("#f3f3f3"))
        label = fm.elidedText(e.name, Qt.ElideLeft, r.width() - 200)
        p.drawText(QRect(x, r.y(), r.width(), r.height()), Qt.AlignLeft | Qt.AlignVCenter, label)
        x += fm.horizontalAdvance(label) + 10
        f2 = QFont(opt.font)
        f2.setPointSizeF(8.2)
        p.setFont(f2)
        p.setPen(QColor("#9d9d9d"))
        meta = f"{getattr(e, 'count', 0)} · {human_size(e.size)}"
        p.drawText(QRect(x, r.y(), 200, r.height()), Qt.AlignLeft | Qt.AlignVCenter, meta)
        x += QFontMetrics(f2).horizontalAdvance(meta) + 12
        p.setPen(QPen(QColor("#333333"), 1))
        p.drawLine(x, r.center().y(), r.right(), r.center().y())
        p.restore()

    def paint(self, p, opt, index):
        e = index.data(ROLE_ENTRY)
        if e is None:
            return
        if e.kind == "header":
            self.paint_header(p, opt, e)
            return
        if e.kind == "drive":
            self.paint_drive(p, opt, e)
            return
        app, lib = self.app, self.app.lib
        key = e.key()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(3, 3, -3, -3)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            p.setPen(QPen(QColor("#4f4f4f"), 1) if sel else Qt.NoPen)
            p.setBrush(QColor("#333333") if sel else QColor("#262626"))
            p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

        tag = app.entry_color(e)
        th = QRect(r.x() + 5, r.y() + 5, r.width() - 10, int((r.width() - 10) * 9 / 16))
        pm = app.thumbs.get(e, th.width(), th.height())
        scrub = getattr(self.view, "scrub", None)
        scrub_label = None
        if scrub and scrub[0] == index:
            spm, scrub_label = app.thumbs.get_scrub(e, scrub[1], th.width(), th.height())
            if spm is not None:
                pm = spm
        if e.kind == "dir" and pm is None:
            s = int(min(th.height(), th.width()) * .95)
            fp = app.icons.folder(tag, max(16, s))
            p.drawPixmap(th.x() + (th.width() - fp.width()) // 2, th.y() + (th.height() - fp.height()) // 2, fp)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#232323"))
            p.drawRoundedRect(QRectF(th), 4, 4)
            col = QColor(cat_color(e))
            if pm is not None:
                p.drawPixmap(th.x() + (th.width() - pm.width()) // 2, th.y() + (th.height() - pm.height()) // 2, pm)
            else:
                f = QFont(opt.font)
                f.setPointSizeF(max(8.0, th.height() / 6.5))
                f.setBold(True)
                p.setFont(f)
                c2 = QColor(col)
                c2.setAlpha(150)
                p.setPen(c2)
                p.drawText(th, Qt.AlignCenter, (e.ext[1:] or "?").upper())
            f = QFont(opt.font)
            f.setPointSizeF(7.0)
            f.setBold(True)
            p.setFont(f)
            fm = QFontMetrics(f)
            if e.kind == "dir":
                fp = app.icons.folder(tag, 22)
                p.drawPixmap(th.x() + 4, th.y() + 4, fp)
            else:
                label = e.ext[1:].upper() if e.ext else "FILE"
                if e.kind == "seq":
                    label += " SEQ"
                elif e.cat == "video":
                    label = "▶ " + label
                bw = fm.horizontalAdvance(label) + 10
                br = QRect(th.x() + 4, th.y() + 4, bw, fm.height() + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(br), 3, 3)
                p.setPen(QColor("#111"))
                p.drawText(br, Qt.AlignCenter, label)
            if scrub_label is not None:
                frac = min(1.0, max(0.0, scrub[1]))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 140))
                p.drawRect(QRectF(th.x(), th.bottom() - 3, th.width(), 3))
                p.setBrush(QColor(ACCENT))
                p.drawRect(QRectF(th.x(), th.bottom() - 3, th.width() * frac, 3))
                if scrub_label:
                    lw = fm.horizontalAdvance(scrub_label) + 10
                    lr = QRect(th.right() - lw - 4, th.bottom() - fm.height() - 9, lw, fm.height() + 2)
                    p.setBrush(QColor(0, 0, 0, 170))
                    p.drawRoundedRect(QRectF(lr), 3, 3)
                    p.setPen(QColor("#ffffff"))
                    p.drawText(lr, Qt.AlignCenter, scrub_label)
            if e.kind == "seq" and e.missing:
                warn = f"faltan {len(e.missing)}"
                bw2 = fm.horizontalAdvance(warn) + 10
                wr = QRect(th.right() - bw2 - 4, th.y() + 4, bw2, fm.height() + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#e5484d"))
                p.drawRoundedRect(QRectF(wr), 3, 3)
                p.setPen(QColor("#fff"))
                p.drawText(wr, Qt.AlignCenter, warn)

        if tag:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(tag))
            p.drawRoundedRect(QRectF(r.x() + 6, r.bottom() - 4, r.width() - 12, 3), 1.5, 1.5)

        # línea 1: nombre
        tr = QRect(r.x() + 6, th.bottom() + 4, r.width() - 12, 16)
        f = QFont(opt.font)
        f.setPointSizeF(9.0)
        p.setFont(f)
        p.setPen(QColor("#e8e8e8"))
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, QFontMetrics(f).elidedText(e.name, Qt.ElideMiddle, tr.width()))
        # línea 2: meta + rating
        mr = QRect(tr.x(), tr.bottom() + 1, tr.width(), 14)
        f2 = QFont(opt.font)
        f2.setPointSizeF(7.8)
        p.setFont(f2)
        fm2 = QFontMetrics(f2)
        feats = bool(app.cfg["library_features"])
        rating = lib.rating(key) if feats else 0
        stars = "★" * rating
        sw = fm2.horizontalAdvance(stars) + 4 if rating else 0
        if rating:
            p.setPen(QColor("#f5c542"))
            p.drawText(mr, Qt.AlignRight | Qt.AlignVCenter, stars)
        if e.kind == "seq":
            meta = f"{e.first}-{e.last}  ·  {len(e.frames)}f  ·  {human_size(e.size)}"
        elif e.kind == "dir":
            from .core import fmt_time
            meta = fmt_time(e.mtime)
            if e.size:
                meta = f"{human_size(e.size)}  ·  {meta}"
        else:
            meta = human_size(e.size)
        p.setPen(QColor("#9aa0a8"))
        mr2 = mr.adjusted(0, 0, -sw, 0)
        p.drawText(mr2, Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(meta, Qt.ElideMiddle, mr2.width()))
        # línea 3: subcarpeta (en búsquedas / vista de subcarpetas) o tags
        model = index.model().sourceModel() if hasattr(index.model(), "sourceModel") else None
        tg = QRect(tr.x(), mr.bottom() + 1, tr.width(), 14)
        if model is not None and model.virtual and model.group_mode != "folder":
            folder = model.folder_text(e) if model.root else e.dirpath
            folder = "(esta carpeta)" if folder == "." else "↳ " + folder
            p.setPen(QColor(ACCENT))
            p.drawText(tg, Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(folder, Qt.ElideLeft, tg.width()))
        elif feats:
            tags = lib.tags(key)
            if tags:
                p.setPen(QColor("#8fb3ff"))
                p.drawText(tg, Qt.AlignLeft | Qt.AlignVCenter,
                           fm2.elidedText("  ".join("#" + t for t in tags), Qt.ElideRight, tg.width()))
        p.restore()

    # --- renombrar en el lugar (F2)
    def name_rect(self, rect):
        ts = self.view.iconSize().width()
        r = rect.adjusted(3, 3, -3, -3)
        th_h = int((r.width() - 10) * 9 / 16)
        return QRect(r.x() + 3, r.y() + 5 + th_h + 2, r.width() - 6, 20)

    def createEditor(self, parent, option, index):
        return make_name_editor(parent)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(self.name_rect(option.rect))

    def setEditorData(self, editor, index):
        set_name_editor_data(editor, index.data(ROLE_ENTRY))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)


def make_name_editor(parent):
    ed = QLineEdit(parent)
    ed.setStyleSheet("QLineEdit{background:#0f1012;border:1px solid #4c9aff;border-radius:3px;padding:1px 4px;}")
    return ed


def set_name_editor_data(editor, e):
    """Pone el nombre y selecciona solo la parte "base" (sin frame ni extensión)."""
    if e is None:
        return
    editor.setText(e.name)
    if e.kind == "seq":
        base, _ = split_head(e.head)
        n = len(base)
    elif e.kind == "file":
        n = len(os.path.splitext(e.name)[0])
    else:
        n = len(e.name)
    QTimer.singleShot(0, lambda: editor.setSelection(0, n))


class ListNameDelegate(QStyledItemDelegate):
    """Delegate de la lista: solo personaliza la edición del nombre."""

    def createEditor(self, parent, option, index):
        return make_name_editor(parent)

    def setEditorData(self, editor, index):
        set_name_editor_data(editor, index.data(ROLE_ENTRY))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)


# ----------------------------------------------------------------------------
# Breadcrumb
# ----------------------------------------------------------------------------

def path_segments(path):
    """Lista de (etiqueta, ruta acumulada)."""
    path = os.path.normpath(path)
    segs = []
    if path.startswith("\\\\"):
        parts = [p for p in path.split("\\") if p]
        if len(parts) >= 2:
            root = "\\\\" + parts[0] + "\\" + parts[1]
            segs.append((f"\\\\{parts[0]}\\{parts[1]}", root + "\\"))
            cur = root
            for p in parts[2:]:
                cur = cur + "\\" + p
                segs.append((p, cur))
            return segs
    drive, rest = os.path.splitdrive(path)
    if drive:
        segs.append((drive, drive + os.sep))
        cur = drive + os.sep
    else:
        segs.append(("/", "/"))
        cur = "/"
    for p in [x for x in rest.replace("\\", "/").split("/") if x]:
        cur = os.path.join(cur, p)
        segs.append((p, cur))
    return segs


_FOLDER_PM = None
_ICONS = None


def _drive_icon_cache(e):
    global _ICONS
    if _ICONS is None:
        _ICONS = Icons()
    return _ICONS.drive_icon(getattr(e, "drive_kind", "local"), 16)


def _folder_pm():
    global _FOLDER_PM
    if _FOLDER_PM is None:
        _FOLDER_PM = Icons().folder("#e8b84a", 16)
    return _FOLDER_PM


class BreadcrumbBar(QWidget):
    navigate = Signal(str)

    def __init__(self, fs_model=None, parent=None):
        super().__init__(parent)
        self.path = ""
        self.virtual_title = ""
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.crumbs = QWidget()
        self.crumbs.setObjectName("crumbs")
        self.crumbs.mousePressEvent = lambda ev: self.start_edit()
        self.cl = QHBoxLayout(self.crumbs)
        self.cl.setContentsMargins(4, 0, 4, 0)
        self.cl.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.returnPressed.connect(self._commit)
        self.edit.editingFinished.connect(self._end_edit)
        self.edit.installEventFilter(self)
        if fs_model is not None:
            comp = QCompleter(fs_model, self)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            self.edit.setCompleter(comp)
        self.stack.addWidget(self.crumbs)
        self.stack.addWidget(self.edit)
        self.setStyleSheet("""
            #crumbs { background:#2d2d2d; border:1px solid #3a3a3a; border-radius:4px; }
            #crumbs QToolButton { border:none; padding:3px 6px; color:#f3f3f3; border-radius:4px; }
            #crumbs QToolButton:hover { background:#3d3d3d; }
            #crumbs QToolButton[arrow="true"] { color:#9d9d9d; padding:3px 2px; }
            #crumbs QToolButton::menu-indicator { image:none; width:0; }
        """)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.stack.setCurrentIndex(0)
            return True
        return False

    def set_path(self, path, virtual_title="", root=None):
        self.path = path or ""
        self.virtual_title = virtual_title
        self.root = root
        self._rebuild()

    def start_edit(self):
        self.edit.setText(self.path)
        self.stack.setCurrentIndex(1)
        self.edit.setFocus()
        self.edit.selectAll()

    def _commit(self):
        t = self.edit.text().strip()
        self.stack.setCurrentIndex(0)
        if t:
            self.navigate.emit(t)

    def _end_edit(self):
        QTimer.singleShot(0, lambda: self.stack.setCurrentIndex(0))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._rebuild()

    def _btn(self, text, tooltip=""):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tooltip)
        b.setAutoRaise(True)
        return b

    def _sub_menu(self, path, parent_btn):
        m = QMenu(parent_btn)

        def fill():
            m.clear()
            if path == "::thispc":
                from .core import list_drives
                for d in list_drives():
                    m.addAction(_drive_icon_cache(d), d.name, lambda p=d.path: self.navigate.emit(p))
                return
            try:
                with os.scandir(path) as it:
                    dirs = sorted((d.name for d in it if d.is_dir() and not d.name.startswith(".")), key=str.lower)
            except OSError:
                dirs = []
            if not dirs:
                m.addAction("(sin subcarpetas)").setEnabled(False)
            for d in dirs[:400]:
                full = os.path.join(path, d)
                m.addAction(d, lambda p=full: self.navigate.emit(p))
        m.aboutToShow.connect(fill)
        return m

    def _rebuild(self):
        while self.cl.count():
            it = self.cl.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if self.virtual_title:
            b = self._btn(self.virtual_title)
            b.setStyleSheet("color:#f5c542; font-weight:bold;")
            self.cl.addWidget(b)
            self.cl.addStretch(1)
            return
        if not self.path:
            self.cl.addStretch(1)
            return
        segs = path_segments(self.path)
        root = getattr(self, "root", None)
        if not root:
            segs = [("Este equipo", "::thispc")] + segs
        if root:
            from .core import same_path
            for i, (_, sp) in enumerate(segs):
                if same_path(sp, root):
                    segs = segs[i:]
                    break
        lead = QLabel()
        lead.setPixmap(_folder_pm())
        lead.setContentsMargins(4, 0, 2, 0)
        self.cl.addWidget(lead)
        fm = self.fontMetrics()
        avail = max(100, self.width() - 64)
        widths = [fm.horizontalAdvance(lbl) + 14 + 16 for lbl, _ in segs]
        start, total = len(segs), 0
        while start > 0 and total + widths[start - 1] < avail:
            start -= 1
            total += widths[start]
        start = min(start, len(segs) - 1)
        if start > 0:
            more = self._btn("«", "Carpetas anteriores")
            m = QMenu(more)
            for lbl, p in reversed(segs[:start]):
                m.addAction(lbl, lambda p=p: self.navigate.emit(p))
            more.setMenu(m)
            more.setPopupMode(QToolButton.InstantPopup)
            self.cl.addWidget(more)
        for lbl, p in segs[start:]:
            b = self._btn(lbl, p)
            b.clicked.connect(lambda c=False, p=p: self.navigate.emit(p))
            self.cl.addWidget(b)
            a = self._btn("›", "Subcarpetas")
            a.setProperty("arrow", True)
            a.setMenu(self._sub_menu(p, a))
            a.setPopupMode(QToolButton.InstantPopup)
            self.cl.addWidget(a)
        self.cl.addStretch(1)


# ----------------------------------------------------------------------------
# Diálogos
# ----------------------------------------------------------------------------

def _hint(text):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet("color:#8b9099; font-size:8pt;")
    return l


class TagDialog(QDialog):
    def __init__(self, common, all_tags, n_items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tags")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Tags para {n_items} elemento(s), separados por coma:"))
        self.edit = QLineEdit(", ".join(common))
        lay.addWidget(self.edit)
        if n_items > 1:
            lay.addWidget(_hint("Se muestran los tags que tienen todos. Los que agregues se suman a cada uno; "
                                "los que borres de esta lista se quitan de todos."))
        if all_tags:
            lay.addWidget(QLabel("Tags existentes (click para agregar):"))
            lst = QListWidget()
            lst.setMaximumHeight(160)
            for t, n in all_tags:
                lst.addItem(f"{t}  ({n})")
                lst.item(lst.count() - 1).setData(Qt.UserRole, t)
            lst.itemClicked.connect(lambda it: self._add(it.data(Qt.UserRole)))
            lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add(self, t):
        cur = self.tags()
        if t.lower() not in {x.lower() for x in cur}:
            cur.append(t)
        self.edit.setText(", ".join(cur))

    def tags(self):
        out = []
        for t in self.edit.text().replace("#", "").split(","):
            t = t.strip()
            if t and t.lower() not in {x.lower() for x in out}:
                out.append(t)
        return out


class RenameDialog(QDialog):
    def __init__(self, e, parent=None):
        super().__init__(parent)
        self.e = e
        self.setWindowTitle("Renombrar secuencia" if e.kind == "seq" else "Renombrar")
        self.setMinimumWidth(460)
        lay = QFormLayout(self)
        if e.kind == "seq":
            base, sep = split_head(e.head)
            self.name = QLineEdit(base)
            self.sep = QComboBox()
            for s, lbl in ((".", "punto  ."), ("_", "guión bajo  _"), ("-", "guión  -"), ("", "nada")):
                self.sep.addItem(lbl, s)
            self.sep.setCurrentIndex(max(0, self.sep.findData(sep)))
            self.start = QSpinBox()
            self.start.setRange(0, 99999999)
            self.start.setValue(e.first)
            lay.addRow("Nombre:", self.name)
            lay.addRow("Separador:", self.sep)
            lay.addRow("Primer frame:", self.start)
            self.preview = QLabel()
            self.preview.setStyleSheet("color:#8fb3ff;")
            lay.addRow("Resultado:", self.preview)
            lay.addRow("", _hint(f"{len(e.frames)} archivos. Cambiar el primer frame renumera toda la secuencia "
                                 f"(ej: 1 → 1001)."))
            for w in (self.name,):
                w.textChanged.connect(self._update)
            self.sep.currentIndexChanged.connect(self._update)
            self.start.valueChanged.connect(self._update)
            self._update()
        else:
            self.name = QLineEdit(e.name)
            lay.addRow("Nombre:", self.name)
            stem = os.path.splitext(e.name)[0] if e.kind == "file" else e.name
            QTimer.singleShot(0, lambda: self.name.setSelection(0, len(stem)))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _update(self):
        e = self.e
        last = self.start.value() + (e.last - e.first)
        pad = "#" * max(e.pad, 1)
        self.preview.setText(f"{self.name.text()}{self.sep.currentData()}{pad}{e.ext_real}   "
                             f"{self.start.value()}-{last}")

    def values(self):
        if self.e.kind == "seq":
            return self.name.text().strip(), self.start.value(), self.sep.currentData()
        return self.name.text().strip(), None, None


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        cfg = app.cfg
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(600)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)

        # --- General
        g = QWidget()
        lay = QFormLayout(g)
        exe_f = "Ejecutables (*.exe)" if IS_WIN else "Todos (*)"
        w, self.player = self._path_row(cfg["player"], "Reproductor (mrv2, DJV, RV…)", exe_f)
        lay.addRow("Reproductor:", w)
        lay.addRow("", _hint("Para abrir secuencias y videos con doble click. Vacío = programa por defecto."))
        w, self.ffmpeg = self._path_row(cfg["ffmpeg"], "ffmpeg.exe", exe_f)
        lay.addRow("ffmpeg:", w)
        found = find_tool(cfg["ffmpeg"], "ffmpeg")
        lay.addRow("", _hint(f"Thumbnails e info de videos. Detectado: {found or 'no encontrado'}. "
                             "También sirve poner ffmpeg.exe y ffprobe.exe en la carpeta <b>bin</b>."))
        self.cs = QComboBox()
        for label, key in COLORSPACES:
            self.cs.addItem(label, key)
        self.cs.setCurrentIndex(max(0, self.cs.findData(cfg["colorspace"])))
        lay.addRow("Espacio de color EXR:", self.cs)
        self.chroma = QCheckBox("Usar chromaticities del EXR si están en el header")
        self.chroma.setChecked(bool(cfg["use_chromaticities"]))
        lay.addRow("", self.chroma)
        self.sidecar = QCheckBox("Previews de modelos y carpetas (JPG/PNG con el mismo nombre, thumbnail.jpg…)")
        self.sidecar.setChecked(bool(cfg["sidecar_previews"]))
        lay.addRow("", self.sidecar)
        self.threads = QSpinBox()
        self.threads.setRange(1, 16)
        self.threads.setValue(int(cfg["threads"]))
        lay.addRow("Threads de thumbnails:", self.threads)
        self.hidden = QCheckBox("Mostrar archivos y carpetas ocultos")
        self.hidden.setChecked(bool(cfg["show_hidden"]))
        lay.addRow("", self.hidden)
        self.fsizes = QCheckBox("Calcular el tamaño de las carpetas (en segundo plano)")
        self.fsizes.setChecked(bool(cfg["folder_sizes"]))
        lay.addRow("", self.fsizes)
        self.feats = QCheckBox("Tags, rating y colecciones")
        self.feats.setChecked(bool(cfg["library_features"]))
        lay.addRow("", self.feats)
        clr = QPushButton(f"Borrar caché de thumbnails ({human_size(app.thumbs.disk_usage())})")
        clr.clicked.connect(lambda: (app.thumbs.clear_disk(), clr.setText("Caché borrada"), app.refresh_views()))
        lay.addRow("", clr)
        lay.addRow("", _hint(f"Datos portables en: {fwd(app.data_dir)}"))
        tabs.addTab(g, "General")

        # --- Pipeline
        pw = QWidget()
        pl = QFormLayout(pw)
        from .pipeline import STM_CONFIG
        self.use_stm = QCheckBox("Usar la configuración de Studio Toolbar")
        self.use_stm.setChecked(bool(cfg["pipeline_use_stm"]))
        pl.addRow("", self.use_stm)
        pl.addRow("", _hint(f"{fwd(STM_CONFIG)} — " + ("encontrado" if os.path.isfile(STM_CONFIG) else
                                                      "no encontrado: se usan los valores de abajo")))
        self.p_root = QLineEdit(cfg["pipeline_root"])
        self.p_prefix = QLineEdit(cfg["pipeline_prefix"])
        self.p_excl = QLineEdit(cfg["pipeline_seq_exclude"])
        pl.addRow("Raíz (unidad o UNC):", self.p_root)
        pl.addRow("Prefijo de proyecto:", self.p_prefix)
        pl.addRow("No son secuencias:", self.p_excl)
        pl.addRow("", _hint("Estructura: {raíz}\\{prefijo}{PROYECTO}\\{SEQ}\\{SHOT}\\{DEPTO}\\{TASK}\\…  "
                            "Las secuencias son carpetas que empiezan con un número; los shots empiezan con PROYECTO_. "
                            "Depto = carpetas al nivel de 3D (3D, Comp, DMP, 2D…)."))
        self.p_depts = QLineEdit(cfg["pipeline_depts"] or "")
        self.p_depts.setPlaceholderText("vacío = todas las carpetas del shot   (ej: 3D, Comp, DMP)")
        pl.addRow("Departamentos:", self.p_depts)
        self.p_loc = QComboBox()
        for label, key in (("Sobre el panel central", "center"), ("Panel izquierdo", "sidebar"), ("Oculta", "hidden")):
            self.p_loc.addItem(label, key)
        self.p_loc.setCurrentIndex(max(0, self.p_loc.findData(
            "center" if cfg["pipeline_location"] in (None, "top") else cfg["pipeline_location"])))
        pl.addRow("Mostrar los dropdowns en:", self.p_loc)
        tabs.addTab(pw, "Pipeline")

        # --- Colores
        from .colors import COLOR_MODES, DEFAULT_NAME_RULES
        cw = QWidget()
        cl = QFormLayout(cw)
        self.cmode = QComboBox()
        for label, key in COLOR_MODES:
            self.cmode.addItem(label, key)
        self.cmode.setCurrentIndex(max(0, self.cmode.findData(cfg["color_mode"])))
        cl.addRow("Colores automáticos:", self.cmode)
        cl.addRow("", _hint("Por proyecto: cada proyecto del pipeline tiene un color (o el que le pongas a mano) y "
                            "se aclara en secuencias y shots. Por nombre: las reglas de abajo. "
                            "El color manual siempre gana. También se cambia con el botón de colores del panel izquierdo."))
        self.fcolor = QComboBox()
        self.fcolor.addItem("Amarillo (como Windows)", "yellow")
        self.fcolor.addItem("Celeste", "blue")
        self.fcolor.setCurrentIndex(max(0, self.fcolor.findData(cfg["folder_color"] or "yellow")))
        cl.addRow("Color de las carpetas:", self.fcolor)
        self.tlines = QCheckBox("Líneas del árbol con el color de la carpeta")
        self.tlines.setChecked(bool(cfg["tree_line_colors"]))
        cl.addRow("", self.tlines)
        self.tstyle = QComboBox()
        self.tstyle.addItem("Sólidas (como XYplorer)", "solid")
        self.tstyle.addItem("Punteadas", "dotted")
        self.tstyle.setCurrentIndex(max(0, self.tstyle.findData(cfg["tree_lines_style"])))
        cl.addRow("Líneas del árbol:", self.tstyle)
        self.ttrace = QCheckBox("Tree Path Tracing: marcar el camino hasta la carpeta actual")
        self.ttrace.setChecked(bool(cfg["tree_trace"]))
        cl.addRow("", self.ttrace)
        self.twidth = QSpinBox()
        self.twidth.setRange(1, 6)
        self.twidth.setSuffix(" px")
        self.twidth.setValue(int(cfg["tree_trace_width"] or 2))
        cl.addRow("Grosor del trazo:", self.twidth)
        self.tcolor = QComboBox()
        self.tcolor.addItem("Color de acento", "accent")
        self.tcolor.addItem("Color de la carpeta actual", "folder")
        self.tcolor.setCurrentIndex(max(0, self.tcolor.findData(cfg["tree_trace_color"])))
        cl.addRow("Color del trazo:", self.tcolor)
        self.lcolor = QComboBox()
        for label, hexc in (("Violeta", "#8d6fd1"), ("Rosa", "#d16fa8"), ("Verde", "#3ecf8e"),
                            ("Naranja", "#ff9f43"), ("Celeste", "#4cc2ff"), ("Gris (como Carpetas)", "#5f6368")):
            self.lcolor.addItem(app.icons.swatch(hexc), label, hexc)
        i = self.lcolor.findData(cfg["lib_tree_line_color"])
        if i < 0:
            self.lcolor.addItem(app.icons.swatch(cfg["lib_tree_line_color"]), cfg["lib_tree_line_color"],
                                cfg["lib_tree_line_color"])
            i = self.lcolor.count() - 1
        self.lcolor.setCurrentIndex(i)
        cl.addRow("Líneas de VFX Library:", self.lcolor)
        from PySide6.QtWidgets import QPlainTextEdit
        self.rules = QPlainTextEdit(cfg["name_rules"] or DEFAULT_NAME_RULES)
        self.rules.setMinimumHeight(220)
        self.rules.setStyleSheet("font-family:Consolas,monospace; font-size:9pt;")
        cl.addRow("Reglas por nombre:", self.rules)
        rb = QPushButton("Restaurar reglas por defecto")
        rb.clicked.connect(lambda: self.rules.setPlainText(DEFAULT_NAME_RULES))
        cl.addRow("", rb)
        tabs.addTab(cw, "Colores")

        # --- VFX Library
        lw = QWidget()
        ll = QFormLayout(lw)
        self.vres = QComboBox()
        for v in ("960", "1280", "1920", "2560"):
            self.vres.addItem(f"{v} px", int(v))
        self.vres.setCurrentIndex(max(0, self.vres.findData(int(cfg["viewer_res"] or 1280))))
        ll.addRow("Resolución del viewer:", self.vres)
        self.vmem = QSpinBox()
        self.vmem.setRange(128, 32768)
        self.vmem.setSingleStep(256)
        self.vmem.setSuffix(" MB")
        self.vmem.setValue(int(cfg["viewer_mem"] or 1024))
        ll.addRow("Memoria para frames:", self.vmem)
        ll.addRow("", _hint("Cuántos frames decodificados se guardan para que el loop corra fluido. "
                            "1280 px ≈ 2,7 MB por frame → 1024 MB ≈ 370 frames."))
        self.vauto = QCheckBox("Reproducir automáticamente al seleccionar")
        self.vauto.setChecked(bool(cfg["viewer_autoplay"]))
        ll.addRow("", self.vauto)
        self.vloop = QCheckBox("Loop por defecto")
        self.vloop.setChecked(bool(cfg["viewer_loop"]))
        ll.addRow("", self.vloop)
        ll.addRow("", _hint("Las carpetas de la librería se agregan con el ＋ de «VFX LIBRARY» en el panel izquierdo. "
                            "Los videos se reproducen con el ffmpeg configurado en General."))
        tabs.addTab(lw, "VFX Library")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _path_row(self, value, title, filt):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        le = QLineEdit(value)
        b = QPushButton("…")
        b.setFixedWidth(32)

        def pick():
            f, _ = QFileDialog.getOpenFileName(self, title, os.path.dirname(le.text()) or "", filt)
            if f:
                le.setText(os.path.normpath(f))
        b.clicked.connect(pick)
        h.addWidget(le)
        h.addWidget(b)
        return w, le

    def apply(self):
        """Guarda. Devuelve (cambió_thumbs, cambió_listado, cambió_pipeline)."""
        cfg = self.app.cfg
        old_t = (cfg["colorspace"], cfg["use_chromaticities"], cfg["ffmpeg"], cfg["sidecar_previews"])
        old_p = (cfg["pipeline_use_stm"], cfg["pipeline_root"], cfg["pipeline_prefix"], cfg["pipeline_seq_exclude"],
                 cfg["pipeline_depts"])
        cfg["player"] = self.player.text().strip().strip('"')
        cfg["ffmpeg"] = self.ffmpeg.text().strip().strip('"')
        cfg["colorspace"] = self.cs.currentData()
        cfg["use_chromaticities"] = self.chroma.isChecked()
        cfg["sidecar_previews"] = self.sidecar.isChecked()
        cfg["threads"] = self.threads.value()
        hidden_changed = cfg["show_hidden"] != self.hidden.isChecked()
        cfg["show_hidden"] = self.hidden.isChecked()
        cfg["pipeline_use_stm"] = self.use_stm.isChecked()
        cfg["pipeline_root"] = self.p_root.text().strip()
        cfg["pipeline_prefix"] = self.p_prefix.text().strip()
        cfg["pipeline_seq_exclude"] = self.p_excl.text().strip()
        cfg.save()
        new_t = (cfg["colorspace"], cfg["use_chromaticities"], cfg["ffmpeg"], cfg["sidecar_previews"])
        cfg["pipeline_depts"] = self.p_depts.text().strip()
        cfg["pipeline_location"] = self.p_loc.currentData()
        new_p = (cfg["pipeline_use_stm"], cfg["pipeline_root"], cfg["pipeline_prefix"], cfg["pipeline_seq_exclude"],
                 cfg["pipeline_depts"])
        listing_changed = hidden_changed or cfg["folder_sizes"] != self.fsizes.isChecked()
        cfg["folder_sizes"] = self.fsizes.isChecked()
        cfg["library_features"] = self.feats.isChecked()
        cfg["color_mode"] = self.cmode.currentData()
        cfg["tree_line_colors"] = self.tlines.isChecked()
        cfg["folder_color"] = self.fcolor.currentData()
        cfg["tree_lines_style"] = self.tstyle.currentData()
        cfg["tree_trace"] = self.ttrace.isChecked()
        cfg["tree_trace_width"] = self.twidth.value()
        cfg["tree_trace_color"] = self.tcolor.currentData()
        cfg["lib_tree_line_color"] = self.lcolor.currentData()
        cfg["name_rules"] = self.rules.toPlainText()
        cfg["viewer_res"] = self.vres.currentData()
        cfg["viewer_mem"] = self.vmem.value()
        cfg["viewer_autoplay"] = self.vauto.isChecked()
        cfg["viewer_loop"] = self.vloop.isChecked()
        cfg.save()
        return {"thumbs": old_t != new_t, "listing": listing_changed, "pipeline": old_p != new_p}


# ----------------------------------------------------------------------------
# Tema
# ----------------------------------------------------------------------------

WIN11_FONT = "Segoe UI Variable Text"


def apply_dark(app):
    """Tema oscuro estilo Windows 11 (Explorador)."""
    app.setStyle("Fusion")
    from PySide6.QtGui import QFont, QFontDatabase
    fams = set(QFontDatabase.families())
    for fam in (WIN11_FONT, "Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans"):
        if fam in fams:
            f = QFont(fam, 9)
            app.setFont(f)
            break
    p = QPalette()
    c = {
        QPalette.Window: "#202020", QPalette.WindowText: "#f3f3f3", QPalette.Base: "#191919",
        QPalette.AlternateBase: "#1d1d1d", QPalette.ToolTipBase: "#2b2b2b", QPalette.ToolTipText: "#f3f3f3",
        QPalette.Text: "#f3f3f3", QPalette.Button: "#2d2d2d", QPalette.ButtonText: "#f3f3f3",
        QPalette.BrightText: "#ffffff", QPalette.Highlight: "#383838", QPalette.HighlightedText: "#ffffff",
        QPalette.Link: ACCENT, QPalette.PlaceholderText: "#8a8a8a", QPalette.Mid: "#3a3a3a",
    }
    for role, col in c.items():
        p.setColor(role, QColor(col))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#6a6a6a"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6a6a6a"))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#6a6a6a"))
    app.setPalette(p)
    app.setStyleSheet("""
        QWidget { color:#f3f3f3; }
        QToolTip { background:#2b2b2b; color:#f3f3f3; border:1px solid #454545; border-radius:4px; padding:4px 6px; }
        QToolBar { background:#202020; border:none; padding:4px 6px; spacing:2px; }
        QToolBar#cmdbar { background:#272727; border-bottom:1px solid #1a1a1a; padding:4px 8px; }
        QToolBar QToolButton, #cmdbar QToolButton { background:transparent; border:none; border-radius:4px;
                                                    padding:4px 7px; color:#f3f3f3; }
        QToolButton:hover { background:#383838; border-radius:4px; }
        QToolButton:pressed { background:#323232; }
        QToolButton:checked { background:#3d3d3d; border-radius:4px; }
        QToolButton::menu-indicator { image:none; width:0; }
        QToolButton[popupMode="2"] { padding-right:7px; }
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background:#2d2d2d; border:1px solid #3a3a3a;
                border-bottom:1px solid #8a8a8a; border-radius:4px; padding:4px 8px; selection-background-color:#0067c0; }
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { background:#1f1f1f; border-bottom:2px solid #4cc2ff; }
        QComboBox::drop-down { border:none; width:20px; }
        QComboBox QAbstractItemView { background:#2c2c2c; border:1px solid #454545; selection-background-color:#3d3d3d; }
        QTreeView, QListView, QListWidget, QTreeWidget { background:#191919; border:none; outline:0; }
        QTreeView::item, QListWidget::item, QTreeWidget::item { padding:2px 2px; border-radius:4px; }
        QTreeView::item:hover, QListWidget::item:hover, QTreeWidget::item:hover { background:#262626; }
        QTreeView::item:selected, QListWidget::item:selected, QTreeWidget::item:selected { background:#333333; color:#ffffff; }
        QTreeView::item:selected:hover, QListWidget::item:selected:hover { background:#3a3a3a; }
        QHeaderView::section { background:#191919; color:#c5c5c5; border:none; border-right:1px solid #2a2a2a;
                               padding:5px 8px; }
        QHeaderView::section:hover { background:#262626; }
        QSplitter::handle { background:#1a1a1a; }
        QSplitter::handle:horizontal { width:1px; }
        QSplitter::handle:vertical { height:1px; }
        QStatusBar { background:#191919; color:#c5c5c5; border-top:1px solid #262626; }
        QStatusBar QLabel { color:#c5c5c5; padding:0 6px; }
        QMenu { background:#2c2c2c; border:1px solid #454545; border-radius:8px; padding:4px; }
        QMenu::item { padding:6px 28px 6px 12px; border-radius:4px; }
        QMenu::item:selected { background:#383838; }
        QMenu::item:disabled { color:#6a6a6a; }
        QMenu::separator { height:1px; background:#454545; margin:4px 8px; }
        QMenu::icon { padding-left:8px; }
        QTabBar { background:transparent; }
        QTabBar::tab { background:transparent; color:#c5c5c5; padding:7px 14px; border:none;
                       border-top-left-radius:8px; border-top-right-radius:8px; margin-right:1px;
                       min-width:70px; max-width:240px; }
        QTabBar::tab:selected { background:#2b2b2b; color:#ffffff; }
        QTabBar::tab:hover:!selected { background:#262626; }
        QPushButton { background:#2d2d2d; border:1px solid #3a3a3a; border-radius:4px; padding:5px 14px; }
        QPushButton:hover { background:#323232; }
        QPushButton:default { background:#4cc2ff; color:#000000; border:none; }
        QCheckBox::indicator { width:16px; height:16px; border-radius:4px; border:1px solid #8a8a8a; background:#2d2d2d; }
        QCheckBox::indicator:checked { background:#4cc2ff; border-color:#4cc2ff; }
        QSlider::groove:horizontal { height:4px; background:#5a5a5a; border-radius:2px; }
        QSlider::sub-page:horizontal { background:#4cc2ff; border-radius:2px; }
        QSlider::handle:horizontal { background:#4cc2ff; border:4px solid #454545; width:12px; height:12px;
                                     margin:-8px 0; border-radius:10px; }
        QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
        QScrollBar::handle:vertical { background:#5a5a5a; border-radius:3px; min-height:30px; }
        QScrollBar::handle:vertical:hover { background:#8a8a8a; }
        QScrollBar:horizontal { background:transparent; height:10px; margin:2px; }
        QScrollBar::handle:horizontal { background:#5a5a5a; border-radius:3px; min-width:30px; }
        QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
        QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
        QProgressDialog { min-width:420px; }
        QDialog { background:#202020; }
        QTabWidget::pane { border:1px solid #2f2f2f; border-radius:6px; top:-1px; background:#1f1f1f; }
    """)


def win11_titlebar(widget):
    """Barra de título oscura del sistema (Windows 10 20H1+ / 11) con el mismo color que la ventana."""
    import sys
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))       # modo oscuro
        color = ctypes.c_int(0x00202020)                                                # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # color del caption (Win11)
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))  # esquinas redondeadas
    except Exception:
        pass
