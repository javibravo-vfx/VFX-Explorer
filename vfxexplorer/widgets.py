# -*- coding: utf-8 -*-
"""Íconos dibujados, delegate de la grilla, breadcrumb, diálogos y tema oscuro."""

import os
import math
import json

from PySide6.QtCore import Qt, Signal, QSize, QRect, QRectF, QPointF, QTimer
from PySide6.QtGui import (QPixmap, QPainter, QColor, QIcon, QPainterPath, QFont, QPen, QPalette,
                           QFontMetrics)
from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QWidget, QHBoxLayout, QToolButton, QLineEdit,
                               QMenu, QStackedLayout, QDialog, QFormLayout, QVBoxLayout, QLabel, QListWidget,
                               QDialogButtonBox, QComboBox, QSpinBox, QPushButton, QFileDialog, QCheckBox,
                               QTabWidget, QCompleter, QSizePolicy, QPlainTextEdit, QTreeWidget, QTreeWidgetItem, QAbstractItemView)

from .core import IS_WIN, human_size, fwd, find_tool
from .imaging import COLORSPACES
from .models import ROLE_ENTRY
from .fileops import split_head, valid_name

CAT_COLORS = {
    "dir": "#8a96a8", "seq": "#4ea1ff", "exr": "#ff9f43", "video": "#b072ff",
    "image": "#3ecf8e", "model": "#f06595", "other": "#7d8590",
}
TAG_COLORS = [
    ("Red", "#e5484d"), ("Orange", "#f76b15"), ("Yellow", "#f5d90a"), ("Green", "#30a46c"),
    ("Light blue", "#0ac5f5"), ("Blue", "#3e63dd"), ("Violet", "#8e4ec6"), ("Pink", "#e93d82"),
    ("Gray", "#8b8d98"),
]
ACCENT = "#4cc2ff"          # acento de Windows 11 (modo oscuro)


def cat_color(e):
    return CAT_COLORS["exr"] if e.ext == ".exr" else CAT_COLORS.get(e.cat, CAT_COLORS["other"])


# ----------------------------------------------------------------------------
# Íconos
# ----------------------------------------------------------------------------

FOLDER_COLORS = {"yellow": "#f4c443", "blue": "#8a96a8"}


def icon_dpr():
    """Escala de la pantalla (125 % = 1.25…): los íconos se dibujan a esa resolución para que no se vean blandos."""
    try:
        from PySide6.QtGui import QGuiApplication
        return max([1.0] + [sc.devicePixelRatio() for sc in QGuiApplication.screens()])
    except Exception:
        return 1.0


def hi_pixmap(size):
    """Pixmap transparente de size×size lógicos dibujado a la resolución real de la pantalla (el QPainter que se
    abra encima trabaja en coordenadas lógicas)."""
    d = icon_dpr()
    n = max(1, int(round(size * d)))
    pm = QPixmap(n, n)
    pm.setDevicePixelRatio(n / float(size))
    pm.fill(Qt.transparent)
    return pm


def hi_scaled(pm, size):
    """Achica un dibujo grande (p. ej. de 64 px) al tamaño lógico, a resolución de pantalla."""
    d = icon_dpr()
    n = max(1, int(round(size * d)))
    out = pm.scaled(n, n, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(n / float(size))
    return out


def logical_size(pm):
    d = pm.devicePixelRatio() or 1.0
    return pm.width() / d, pm.height() / d


SYS_LINE_COLORS = {"desktop": "#4ca8f0", "documents": "#7aa2f7", "downloads": "#2ec4a0", "pictures": "#4ca8f0",
                   "videos": "#a78bfa", "onedrive": "#3b9ae8", "nuke": "#f5b81c"}


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
        pm = hi_pixmap(size)
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

    def folder(self, color=None, size=20, hi=False):
        key = ("f", color, size, hi)
        if key in self._c:
            return self._c[key]
        base = QColor(color or self.default_folder)
        if hi:
            pm = hi_pixmap(size)
        else:
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

    def sysfolder(self, kind, size=16):
        """Acceso rápido (Desktop, Documents, Downloads, Pictures, Videos, OneDrive, .nuke): íconos de líneas como
        los glifos de la app, cada uno con su color."""
        key = ("sys", kind, size)
        if key in self._c:
            return self._c[key]
        pm = hi_pixmap(size)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        u = size / 18.0
        p.setPen(QPen(QColor(SYS_LINE_COLORS.get(kind, "#c9ccd1")), 1.3 * max(1.0, u * .9), Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        P = lambda a, b: QPointF(a * u, b * u)
        R = lambda a, b, w, h: QRectF(a * u, b * u, w * u, h * u)
        if kind == "desktop":
            p.drawRoundedRect(R(2, 3, 14, 9.5), 1.6 * u, 1.6 * u)
            p.drawLine(P(9, 12.5), P(9, 15))
            p.drawLine(P(5.5, 15.2), P(12.5, 15.2))
        elif kind == "documents":
            d = QPainterPath()
            d.moveTo(P(4, 2)); d.lineTo(P(11, 2)); d.lineTo(P(14.5, 5.5)); d.lineTo(P(14.5, 16)); d.lineTo(P(4, 16))
            d.closeSubpath()
            p.drawPath(d)
            p.drawPolyline([P(11, 2), P(11, 5.5), P(14.5, 5.5)])
            p.drawLine(P(6.5, 8.5), P(12, 8.5))
            p.drawLine(P(6.5, 11), P(12, 11))
            p.drawLine(P(6.5, 13.5), P(10, 13.5))
        elif kind == "downloads":
            p.drawLine(P(9, 2.5), P(9, 11.5))
            p.drawPolyline([P(5, 7.8), P(9, 11.8), P(13, 7.8)])
            p.drawLine(P(3.5, 15.3), P(14.5, 15.3))
        elif kind == "pictures":
            p.drawRoundedRect(R(2, 3, 14, 12), 1.8 * u, 1.8 * u)
            p.drawPolyline([P(4, 13), P(7.5, 9), P(10, 11.5), P(11.8, 9.8), P(14.2, 12.5)])
            p.drawEllipse(P(12, 6.6), 1.2 * u, 1.2 * u)
        elif kind == "videos":
            p.drawRoundedRect(R(2, 3, 14, 12), 1.8 * u, 1.8 * u)
            t = QPainterPath()
            t.moveTo(P(7.5, 6.5)); t.lineTo(P(11.8, 9)); t.lineTo(P(7.5, 11.5)); t.closeSubpath()
            p.drawPath(t)
        elif kind == "onedrive":
            c = QPainterPath()
            c.moveTo(P(5, 14)); c.cubicTo(P(1.5, 14), P(1.5, 9), P(5, 9)); c.cubicTo(P(5.5, 5), P(11, 4), P(12.5, 7.8))
            c.cubicTo(P(16.5, 7.5), P(17.5, 14), P(13.5, 14)); c.closeSubpath()
            p.drawPath(c)
        elif kind == "nuke":                 # carpeta .nuke: dos círculos (ícono propio, no el logo)
            p.drawEllipse(P(9, 9), 6.8 * u, 6.8 * u)
            p.drawEllipse(P(9, 9), 2.8 * u, 2.8 * u)
        p.end()
        ic = QIcon(pm)
        self._c[key] = ic
        return ic

    def new_icon(self, size=18):
        """⊕ con el aro celeste, como el «New» del Explorador."""
        key = ("new", size)
        if key in self._c:
            return self._c[key]
        S = 64
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#4cc2ff"), 4.5))
        p.drawEllipse(QPointF(32, 32), 25, 25)
        p.setPen(QPen(QColor("#f3f3f3"), 4.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(32, 19, 32, 45)
        p.drawLine(19, 32, 45, 32)
        p.end()
        ic = QIcon(hi_scaled(pm, size))
        self._c[key] = ic
        return ic

    def eye(self, size=16, on=True, color="#c9ccd1"):
        key = ("eye", size, on, color)
        if key in self._c:
            return self._c[key]
        S = 64
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        e = QPainterPath()
        e.moveTo(6, 32); e.quadTo(32, 4, 58, 32); e.quadTo(32, 60, 6, 32)
        p.drawPath(e)
        p.drawEllipse(QPointF(32, 32), 8, 8)
        if not on:
            p.drawLine(12, 54, 52, 10)
        p.end()
        ic = QIcon(hi_scaled(pm, size))
        self._c[key] = ic
        return ic

    def folder_icon(self, color=None, size=20):
        key = ("fi", color, size)
        if key not in self._c:
            self._c[key] = QIcon(self.folder(color, size, hi=True))
        return self._c[key]

    def badge(self, e, size=18):
        cat, color = e.cat, cat_color(e)
        key = ("b", cat, color, size)
        if key in self._c:
            return self._c[key]
        pm = hi_pixmap(size)
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
            pm = hi_pixmap(size)
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
        pm = hi_pixmap(size)
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
            c = s / 2
            ro, ri = s * .42, s * .31
            pts = []
            for i in range(8):
                a = math.radians(i * 45)
                for da, r in ((-15, ri), (-9, ro), (9, ro), (15, ri)):
                    t = a + math.radians(da)
                    pts.append(QPointF(c + math.cos(t) * r, c + math.sin(t) * r))
            gear = QPainterPath()
            gear.moveTo(pts[0])
            for q in pts[1:]:
                gear.lineTo(q)
            gear.closeSubpath()
            p.drawPath(gear)
            p.drawEllipse(QPointF(c, c), s * .13, s * .13)
        elif kind == "dualv":
            p.drawRoundedRect(QRectF(s * .14, s * .14, s * .72, s * .72), 2, 2)
            path.moveTo(s * .14, s * .5); path.lineTo(s * .86, s * .5)
        elif kind == "colorfilter":
            for i, c in enumerate(("#ff5c5c", "#4cc2ff", "#3ecf8e")):
                p.save()
                p.setPen(QPen(QColor(c), max(1.2, s * .09), Qt.SolidLine, Qt.RoundCap))
                y = s * (.28 + i * .22)
                p.drawLine(QPointF(s * .18, y), QPointF(s * (.82 - i * .14), y))
                p.restore()
        elif kind == "dual":
            p.drawRoundedRect(QRectF(s * .12, s * .2, s * .76, s * .6), 2, 2)
            path.moveTo(s * .5, s * .2); path.lineTo(s * .5, s * .8)
        elif kind == "workspace":           # ventana con panel izquierdo y dos paneles (un layout guardado)
            p.drawRoundedRect(QRectF(s * .1, s * .18, s * .8, s * .64), 2, 2)
            path.moveTo(s * .36, s * .18); path.lineTo(s * .36, s * .82)
            path.moveTo(s * .36, s * .5); path.lineTo(s * .9, s * .5)
        elif kind == "collapse":            # dos flechas que se juntan hacia una línea
            path.moveTo(s * .3, s * .14); path.lineTo(s * .5, s * .34); path.lineTo(s * .7, s * .14)
            path.moveTo(s * .3, s * .86); path.lineTo(s * .5, s * .66); path.lineTo(s * .7, s * .86)
            path.moveTo(s * .16, s * .5); path.lineTo(s * .84, s * .5)
        elif kind == "sortaz":              # A sobre Z con flecha hacia abajo
            path.moveTo(s * .14, s * .44); path.lineTo(s * .27, s * .12); path.lineTo(s * .4, s * .44)
            path.moveTo(s * .19, s * .33); path.lineTo(s * .35, s * .33)
            path.moveTo(s * .15, s * .58); path.lineTo(s * .39, s * .58); path.lineTo(s * .15, s * .88)
            path.lineTo(s * .39, s * .88)
            path.moveTo(s * .7, s * .14); path.lineTo(s * .7, s * .86)
            path.moveTo(s * .58, s * .72); path.lineTo(s * .7, s * .86); path.lineTo(s * .82, s * .72)
        elif kind == "doc":                 # hoja con la esquina doblada y renglones
            path.moveTo(s * .22, s * .1); path.lineTo(s * .58, s * .1); path.lineTo(s * .78, s * .3)
            path.lineTo(s * .78, s * .9); path.lineTo(s * .22, s * .9); path.closeSubpath()
            path.moveTo(s * .58, s * .1); path.lineTo(s * .58, s * .3); path.lineTo(s * .78, s * .3)
            path.moveTo(s * .34, s * .5); path.lineTo(s * .66, s * .5)
            path.moveTo(s * .34, s * .64); path.lineTo(s * .66, s * .64)
            path.moveTo(s * .34, s * .78); path.lineTo(s * .56, s * .78)
        elif kind == "minitree":            # arbolito sintético: un nodo arriba y dos ramas
            p.drawRect(QRectF(s * .16, s * .14, s * .2, s * .2))
            path.moveTo(s * .26, s * .34); path.lineTo(s * .26, s * .8); path.lineTo(s * .56, s * .8)
            path.moveTo(s * .26, s * .55); path.lineTo(s * .56, s * .55)
            p.drawEllipse(QPointF(s * .7, s * .55), s * .1, s * .1)
            p.drawEllipse(QPointF(s * .7, s * .8), s * .1, s * .1)
        elif kind == "bonsai":              # Bonsai (árbol de lo visitado): maceta, tronco en S y copas planas
            u = s / 18.0
            P = lambda a_, b_: QPointF(a_ * u, b_ * u)
            p.setPen(QPen(QColor(color), max(1.1, 1.3 * u), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            pot = QPainterPath()
            pot.moveTo(P(4, 13.2)); pot.lineTo(P(14, 13.2)); pot.lineTo(P(12.8, 16.2)); pot.lineTo(P(5.2, 16.2))
            pot.closeSubpath()
            p.drawPath(pot)
            t = QPainterPath()
            t.moveTo(P(8.2, 13.2)); t.cubicTo(P(10.8, 11.5), P(5.5, 9.8), P(8.2, 7.6))
            t.cubicTo(P(9.6, 6.5), P(10.6, 5.8), P(9.6, 3.6))
            p.drawPath(t)
            p.drawLine(P(8.0, 8.0), P(4.2, 7.4))
            p.drawLine(P(9.4, 6.1), P(13.4, 5.6))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            for cx, cy, w, h in ((4.2, 8.0, 6.4, 2.2), (13.6, 6.2, 6.8, 2.3), (9.4, 3.9, 6.2, 2.4)):
                x0 = cx - w / 2
                pad = QPainterPath()
                pad.moveTo(P(x0, cy)); pad.cubicTo(P(x0, cy - h), P(cx - w * .15, cy - h * 1.15), P(cx, cy - h * .9))
                pad.cubicTo(P(cx + w * .2, cy - h * 1.2), P(x0 + w, cy - h * .9), P(x0 + w, cy))
                pad.closeSubpath()
                p.drawPath(pad)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(color), size * .1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        elif kind == "scissors":
            p.drawEllipse(QPointF(s * .3, s * .74), s * .13, s * .13)
            p.drawEllipse(QPointF(s * .7, s * .74), s * .13, s * .13)
            path.moveTo(s * .38, s * .63); path.lineTo(s * .74, s * .14)
            path.moveTo(s * .62, s * .63); path.lineTo(s * .26, s * .14)
        elif kind == "image":
            p.drawRoundedRect(QRectF(s * .14, s * .2, s * .72, s * .6), s * .08, s * .08)
            path.moveTo(s * .2, s * .72); path.lineTo(s * .42, s * .48); path.lineTo(s * .58, s * .62)
            path.lineTo(s * .66, s * .55); path.lineTo(s * .8, s * .72)
            p.drawEllipse(QPointF(s * .64, s * .36), s * .06, s * .06)
        elif kind == "seqstack":
            p.drawRoundedRect(QRectF(s * .3, s * .14, s * .56, s * .44), s * .06, s * .06)
            path.moveTo(s * .22, s * .3); path.lineTo(s * .22, s * .66); path.lineTo(s * .7, s * .66)
            path.moveTo(s * .14, s * .46); path.lineTo(s * .14, s * .82); path.lineTo(s * .62, s * .82)
        elif kind == "grid":
            for x in (.18, .54):
                for y in (.18, .54):
                    p.drawRect(QRectF(s * x, s * y, s * .28, s * .28))
        elif kind == "list":
            for y in (.28, .5, .72):
                path.moveTo(s * .18, s * y); path.lineTo(s * .82, s * y)
        elif kind == "group":
            path.moveTo(s * .16, s * .2); path.lineTo(s * .84, s * .2)
            for y in (.42, .62, .82):
                path.moveTo(s * .3, s * y); path.lineTo(s * .34, s * y)
                path.moveTo(s * .46, s * y); path.lineTo(s * .84, s * y)
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
        """Ícono de la app: dos carpetas amarillas con un tracking marker azul (= assets/icon.ico)."""
        icon = QIcon()
        for S in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(app_icon_pixmap(S))
        return icon


# ----------------------------------------------------------------------------
# Delegate de la grilla
# ----------------------------------------------------------------------------

APP_ICON_FOLDERS = ("#e6a820", "#ffcf48")     # atrás, adelante (el amarillo de las carpetas de Windows)
APP_ICON_FRONT_TOP = "#fbd976"
APP_ICON_MARKER = "#0a7bca"                    # el azul del ícono del Explorador


def app_icon_pixmap(S):
    """Carpeta grande (amarillo Windows) con el tracking marker azul y otra pegadita atrás."""
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    # el conjunto (carpeta de adelante 49×40 + la de atrás corrida 7, 7) ocupa casi todo el cuadro,
    # centrado, para que en la barra de tareas se vea del mismo tamaño que los demás íconos
    k = S / 64.0 * (62.0 / 56.0)
    ox, oy = (S - 56 * k) / 2, (S - 47 * k) / 2
    fx, fy, fw, fh = ox + 7 * k, oy, 49 * k, 40 * k          # carpeta de adelante
    r = 6 * k
    p.setBrush(QColor(APP_ICON_FOLDERS[0]))                    # la de atrás asoma apenas
    p.drawRoundedRect(QRectF(fx - 7 * k, fy + 7 * k, fw, fh), r, r)
    p.setBrush(QColor(APP_ICON_FOLDERS[1]))
    p.drawRoundedRect(QRectF(fx, fy, fw, fh), r, r)
    p.save()
    p.setClipRect(QRectF(fx, fy, fw, fh * .23))
    p.setBrush(QColor(APP_ICON_FRONT_TOP))
    p.drawRoundedRect(QRectF(fx, fy, fw, fh), r, r)
    p.restore()
    # tracking marker: cuatro esquinas tipo visor + cruz al centro
    col = QColor(APP_ICON_MARKER)
    p.setPen(QPen(col, max(1.0, fw * .072), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    x0, x1 = fx + fw * .172, fx + fw * .828
    y0, y1 = fy + fh * .2, fy + fh * .81
    ax, ay = fw * .19, fh * .19
    for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        path = QPainterPath()
        path.moveTo(x + dx * ax, y)
        path.lineTo(x, y)
        path.lineTo(x, y + dy * ay)
        p.drawPath(path)
    p.setPen(QPen(col, max(1.0, fw * .05), Qt.SolidLine, Qt.RoundCap))
    cx, cy, c = fx + fw * .5, fy + fh * .505, fw * .095
    p.drawLine(QPointF(cx - c, cy), QPointF(cx + c, cy))
    p.drawLine(QPointF(cx, cy - c), QPointF(cx, cy + c))
    p.end()
    return pm


def wrap_name(text, fm, width, max_lines=2):
    """Parte el nombre en hasta 2 líneas como el Explorador: corta en espacios, _ . - si puede, si no por letra;
    la última línea se recorta con … al medio (para no perder la extensión ni el ####)."""
    if fm.horizontalAdvance(text) <= width:
        return [text]
    lines, rest = [], text
    while rest and len(lines) < max_lines - 1:
        cut = 0
        for i in range(1, len(rest) + 1):
            if fm.horizontalAdvance(rest[:i]) > width:
                break
            cut = i
        cut = max(cut, 1)
        if cut >= len(rest):
            break
        soft = max((rest.rfind(ch, 0, cut) for ch in " _.-"), default=-1)
        if soft >= cut // 2:
            cut = soft + 1
        lines.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        lines.append(fm.elidedText(rest, Qt.ElideMiddle, width))
    return lines


class GridDelegate(QStyledItemDelegate):
    TEXT_H = 74

    def __init__(self, app, view):
        super().__init__(view)
        self.app, self.view = app, view

    def sizeHint(self, option, index):
        e = index.data(ROLE_ENTRY)
        if e is not None and e.kind == "header":
            return QSize(max(200, self.view.viewport().width() - 10), 34)
        if e is not None and e.kind == "drive":
            return QSize(262, 72)
        ts = self.view.iconSize().width()
        return QSize(ts + 16, int(ts * 9 / 16) + 16 + self.TEXT_H)

    def paint_drive(self, p, opt, e):
        """Tarjeta de disco como la de «Este equipo» de Windows 11: ícono, nombre, barra de uso y libre/total."""
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(3, 3, -3, -3)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            p.setPen(QPen(QColor("#5a5a5a"), 1) if sel else Qt.NoPen)
            p.setBrush(QColor("#333333") if sel else QColor("#262626"))
            p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        ic = self.app.icons.drive(getattr(e, "drive_kind", "local"), 44)
        p.drawPixmap(r.x() + 4, r.y() + (r.height() - 44) // 2, ic)
        x = r.x() + 56
        w = r.right() - x - 6
        f = QFont(opt.font)
        f.setPointSizeF(9.3)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(QColor("#f3f3f3"))
        p.drawText(QRect(x, r.y() + 3, w, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(e.name, Qt.ElideMiddle, w))
        total, free = e.size or 0, getattr(e, "free", 0) or 0
        used = (total - free) / total if total else 0
        bar = QRectF(x, r.y() + 6 + fm.height(), w, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e6e6e6"))
        p.drawRect(bar)
        p.setBrush(QColor("#da3b3b") if used > 0.9 else QColor("#2a8de8"))
        p.drawRect(QRectF(bar.x(), bar.y(), bar.width() * used, bar.height()))
        f2 = QFont(opt.font)
        f2.setPointSizeF(8.4)
        p.setFont(f2)
        p.setPen(QColor("#c5c5c5"))
        txt = f"{human_size(free)} free of {human_size(total)}" if total else "no access"
        p.drawText(QRect(x, int(bar.bottom()) + 2, w, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f2).elidedText(txt, Qt.ElideRight, w))
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
        fp = self.app.icons.folder(None if e.name.startswith("(") else "#e8b84a", 16, hi=True) \
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

        tag = app.entry_color(e, getattr(self.view, "lib_mode", False))
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
            fp = app.icons.folder(tag, max(16, s), hi=True)
            fw, fh = logical_size(fp)
            p.drawPixmap(QPointF(th.x() + (th.width() - fw) / 2, th.y() + (th.height() - fh) / 2), fp)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#232323"))
            p.drawRoundedRect(QRectF(th), 4, 4)
            col = QColor(cat_color(e))
            sysic = app.sys_icon(e, min(256, int(th.height() * .8))) if pm is None else None
            if pm is not None:
                p.drawPixmap(th.x() + (th.width() - pm.width()) // 2, th.y() + (th.height() - pm.height()) // 2, pm)
            elif sysic is not None:
                # ícono original del archivo (programa / documento), como en el Explorador
                p.setBrush(QColor("#1c1c1c") if not (sel or hov) else QColor("#333333" if sel else "#262626"))
                p.drawRoundedRect(QRectF(th), 4, 4)
                dpr = sysic.devicePixelRatio() or 1.0
                sw, sh = sysic.width() / dpr, sysic.height() / dpr          # tamaño lógico (pantallas con escala)
                p.drawPixmap(QRectF(th.x() + (th.width() - sw) / 2, th.y() + (th.height() - sh) / 2, sw, sh),
                             sysic, QRectF(sysic.rect()))
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
                fp = app.icons.folder(tag, 22, hi=True)
                p.drawPixmap(th.x() + 4, th.y() + 4, fp)
            elif sysic is not None:
                pass
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
                warn = f"missing {len(e.missing)}"
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

        # nombre: centrado, hasta 2 líneas (como el Explorador de Windows)
        f = QFont(opt.font)
        f.setPointSizeF(10.0)
        p.setFont(f)
        fm = QFontMetrics(f)
        cf = self.app.color_filter_for(e)
        src = index.model().sourceModel() if hasattr(index.model(), "sourceModel") else None
        shown = src.display_name(e) if src is not None and hasattr(src, "display_name") else e.name
        lines = wrap_name(shown, fm, r.width() - 12)
        lh = fm.height()
        y = th.bottom() + 4
        if cf and cf[1]:
            bw = max(fm.horizontalAdvance(x) for x in lines) + 10
            p.save()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cf[1]))
            p.drawRoundedRect(QRectF(r.center().x() - bw / 2, y - 1, bw, lh * len(lines) + 2), 3, 3)
            p.restore()
        p.setPen(QColor(cf[0]) if cf and cf[0] else QColor("#e8e8e8"))
        for line in lines:
            p.drawText(QRect(r.x() + 6, y, r.width() - 12, lh), Qt.AlignHCenter | Qt.AlignVCenter, line)
            y += lh
        tr = QRect(r.x() + 6, y - lh, r.width() - 12, lh)
        # meta + rating
        mr = QRect(tr.x(), tr.bottom() + 1, tr.width(), 16)
        f2 = QFont(opt.font)
        f2.setPointSizeF(8.8)
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
        mr2 = mr.adjusted(sw, 0, -sw, 0)
        p.drawText(mr2, Qt.AlignHCenter | Qt.AlignVCenter, fm2.elidedText(meta, Qt.ElideMiddle, mr2.width()))
        # línea 3: subcarpeta (en búsquedas / vista de subcarpetas) o tags
        model = index.model().sourceModel() if hasattr(index.model(), "sourceModel") else None
        tg = QRect(tr.x(), mr.bottom() + 1, tr.width(), 16)
        if model is not None and model.virtual and model.group_mode != "folder":
            folder = model.folder_text(e) if model.root else e.dirpath
            folder = "(this folder)" if folder == "." else "↳ " + folder
            p.setPen(QColor(ACCENT))
            p.drawText(tg, Qt.AlignHCenter | Qt.AlignVCenter, fm2.elidedText(folder, Qt.ElideLeft, tg.width()))
        elif feats:
            tags = lib.tags(key)
            if tags:
                p.setPen(QColor("#8fb3ff"))
                p.drawText(tg, Qt.AlignHCenter | Qt.AlignVCenter,
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
        _FOLDER_PM = Icons().folder("#e8b84a", 16, hi=True)
    return _FOLDER_PM


class SixKeyEdit(QLineEdit):
    """Barra de dirección con «6 Key Navigation»: se recorre todo con Ctrl, ←, →, ↑, ↓ y Enter.
    → al final de una carpeta agrega la barra y abre la lista de subcarpetas · Ctrl+← / Ctrl+→ saltan entre
    carpetas del camino · Ctrl+↓ abre la lista en el cursor (corta lo de la derecha) · ↑ ↓ eligen · Ctrl+↑ cierra
    · Enter va (un archivo: va a su carpeta y lo selecciona) · Ctrl+Enter al revés (abre el archivo / la carpeta
    en una pestaña nueva)."""
    go = Signal(str, bool)          # ruta, alternativo (Ctrl+Enter)

    def __init__(self):
        super().__init__()
        from PySide6.QtCore import QStringListModel
        self._model = QStringListModel(self)
        self.comp = QCompleter(self._model, self)
        self.comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.comp.setCompletionMode(QCompleter.PopupCompletion)
        self.comp.setMaxVisibleItems(16)
        self.comp.setWidget(self)
        self.comp.activated.connect(self._picked)
        self.comp.popup().installEventFilter(self)
        self._dir = None
        self.textEdited.connect(self._typed)

    @staticmethod
    def _seps():
        return "\\/"

    def _split(self, text):
        """(carpeta, lo que se está escribiendo del nombre)"""
        i = max(text.rfind("\\"), text.rfind("/"))
        if i < 0:
            return "", text
        return text[: i + 1], text[i + 1:]

    def _fill(self, folder):
        from .core import reachable
        if folder == self._dir:
            return
        self._dir = folder
        names = []
        if folder and reachable(folder):
            try:
                with os.scandir(folder) as it:
                    names = sorted((d.name for d in it if not d.name.startswith(".") and d.is_dir()), key=str.lower)
            except OSError:
                names = []
        self._model.setStringList([folder + n for n in names[:2000]])

    def open_list(self):
        text = self.text()
        folder, part = self._split(text)
        self._fill(folder)
        self.comp.setCompletionPrefix(text)
        if self.comp.completionCount():
            r = self.cursorRect()
            r.setWidth(max(320, self.width() - r.x()))
            self.comp.complete(r)
        else:
            self.comp.popup().hide()

    def _typed(self, _t):
        folder, _ = self._split(self.text())
        if folder:
            self.open_list()

    def _picked(self, text):
        self.setText(text)
        self.setCursorPosition(len(text))

    def _component_pos(self, forward):
        t, c = self.text(), self.cursorPosition()
        seps = [i + 1 for i, ch in enumerate(t) if ch in "\\/"]
        if forward:
            nxt = [p for p in seps if p > c]
            return nxt[0] if nxt else len(t)
        prv = [p for p in seps if p < c]
        return prv[-1] if prv else 0

    def eventFilter(self, obj, ev):
        if obj is self.comp.popup() and ev.type() == ev.Type.KeyPress:
            if ev.key() == Qt.Key_Up and ev.modifiers() & Qt.ControlModifier:
                self.comp.popup().hide()
                return True
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                ix = self.comp.popup().currentIndex()
                if ix.isValid():
                    self._picked(ix.data())
                self.comp.popup().hide()
                self._go(bool(ev.modifiers() & Qt.ControlModifier))
                return True
            if ev.key() == Qt.Key_Right:
                ix = self.comp.popup().currentIndex()
                if ix.isValid():
                    self._picked(ix.data())
                self.comp.popup().hide()
                self.keyPressEvent(ev)
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        k, ctrl = ev.key(), bool(ev.modifiers() & Qt.ControlModifier)
        t = self.text()
        if k == Qt.Key_Right and not ctrl and self.cursorPosition() == len(t) and not self.hasSelectedText():
            p = os.path.expandvars(t)
            if p and not p.endswith(("\\", "/")) and os.path.isdir(p):
                self.setText(t + os.sep)
                self.open_list()
                return
        if k in (Qt.Key_Left, Qt.Key_Right) and ctrl:
            self.setCursorPosition(self._component_pos(k == Qt.Key_Right))
            return
        if k == Qt.Key_Down and ctrl:
            c = self.cursorPosition()
            self.setText(t[:c])
            self.open_list()
            return
        if k == Qt.Key_Down and not self.comp.popup().isVisible():
            self.open_list()
            return
        if k == Qt.Key_Up and ctrl:
            self.comp.popup().hide()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self._go(ctrl)
            return
        super().keyPressEvent(ev)

    def _go(self, alt):
        t = self.text().strip()
        if t:
            self.go.emit(t, alt)


class CrumbArrow(QToolButton):
    """Flechita entre las carpetas de la dirección: dibujada del mismo tamaño y trazo que la de New / Sort / View;
    apunta a la derecha y, con el menú de subcarpetas abierto, hacia abajo (como Windows)."""

    def __init__(self, tooltip=""):
        super().__init__()
        self.setToolTip(tooltip)
        self.setAutoRaise(True)
        self.setFixedWidth(20)
        self.setPopupMode(QToolButton.InstantPopup)

    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3d3d3d"))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 3, -1, -3), 4, 4)
        p.setPen(QPen(QColor("#c5c5c5"), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy = self.width() / 2, self.height() / 2
        if self.isDown():
            p.drawLine(QPointF(cx - 3, cy - 1.5), QPointF(cx, cy + 1.5))
            p.drawLine(QPointF(cx, cy + 1.5), QPointF(cx + 3, cy - 1.5))
        else:
            p.drawLine(QPointF(cx - 1.5, cy - 3), QPointF(cx + 1.5, cy))
            p.drawLine(QPointF(cx + 1.5, cy), QPointF(cx - 1.5, cy + 3))
        p.end()


class BreadcrumbBar(QWidget):
    navigate = Signal(str)
    open_alt = Signal(str)          # Ctrl+Enter en la barra: abrir el archivo / la carpeta en una pestaña nueva

    def __init__(self, fs_model=None, parent=None):
        super().__init__(parent)
        self.path = ""
        self.virtual_title = ""
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.crumbs = QWidget()
        self.crumbs.setObjectName("crumbs")
        self.crumbs.mousePressEvent = lambda ev: self.start_edit()
        self.cl = QHBoxLayout(self.crumbs)
        self.cl.setContentsMargins(4, 0, 4, 0)
        self.cl.setSpacing(0)
        self.edit = SixKeyEdit()
        self.edit.go.connect(self._commit)
        self.edit.editingFinished.connect(self._end_edit)
        self.edit.installEventFilter(self)
        self.stack.addWidget(self.crumbs)
        self.stack.addWidget(self.edit)
        self.setStyleSheet("""
            #crumbs { background:#2d2d2d; border:1px solid #333333; border-radius:5px; }
            #crumbs QToolButton { border:none; padding:4px 9px; color:#f3f3f3; border-radius:4px; font-size:10.5pt; }
            #crumbs QToolButton:hover { background:#3d3d3d; }
            #crumbs QToolButton[arrow="true"] { color:#c5c5c5; padding:4px 5px; }
            QLineEdit { font-size:10.5pt; }
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

    def _commit(self, t=None, alt=False):
        t = (t if t is not None else self.edit.text()).strip()
        self.stack.setCurrentIndex(0)
        if t:
            (self.open_alt if alt else self.navigate).emit(t)

    def _end_edit(self):
        # con la lista de la 6 Key Navigation abierta el foco pasa al popup: no cerrar la edición
        if self.edit.comp.popup().isVisible():
            return
        QTimer.singleShot(0, lambda: (not self.edit.hasFocus() and not self.edit.comp.popup().isVisible())
                          and self.stack.setCurrentIndex(0))

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
            from .core import reachable
            try:
                if not reachable(path):
                    raise OSError("offline")
                with os.scandir(path) as it:
                    dirs = sorted((d.name for d in it if d.is_dir() and not d.name.startswith(".")), key=str.lower)
            except OSError:
                dirs = []
            if not dirs:
                m.addAction("(no subfolders)").setEnabled(False)
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
        if self.virtual_title and self.virtual_title != "This PC":
            b = self._btn(self.virtual_title)
            b.setStyleSheet("color:#f5c542; font-weight:bold;")
            self.cl.addWidget(b)
            self.cl.addStretch(1)
            return
        if not self.path:
            self.cl.addStretch(1)
            return
        segs = [] if self.virtual_title == "This PC" else path_segments(self.path)
        root = getattr(self, "root", None)
        if not root:
            segs = [("This PC", "::thispc")] + segs
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
            more = self._btn("«", "Parent folders")
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
            a = CrumbArrow("Subfolders")
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
        lay.addWidget(QLabel(f"Tags for {n_items} item(s), comma separated:"))
        self.edit = QLineEdit(", ".join(common))
        lay.addWidget(self.edit)
        if n_items > 1:
            lay.addWidget(_hint("Shows the tags they all have. Tags you add go to each one; "
                                "tags you delete from this list are removed from all of them."))
        if all_tags:
            lay.addWidget(QLabel("Existing tags (click to add):"))
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
        self.setWindowTitle("Rename sequence" if e.kind == "seq" else "Rename")
        self.setMinimumWidth(460)
        lay = QFormLayout(self)
        if e.kind == "seq":
            base, sep = split_head(e.head)
            self.name = QLineEdit(base)
            self.sep = QComboBox()
            for s, lbl in ((".", "dot  ."), ("_", "underscore  _"), ("-", "dash  -"), ("", "none")):
                self.sep.addItem(lbl, s)
            self.sep.setCurrentIndex(max(0, self.sep.findData(sep)))
            self.start = QSpinBox()
            self.start.setRange(0, 99999999)
            self.start.setValue(e.first)
            lay.addRow("Name:", self.name)
            lay.addRow("Separator:", self.sep)
            lay.addRow("First frame:", self.start)
            self.preview = QLabel()
            self.preview.setStyleSheet("color:#8fb3ff;")
            lay.addRow("Result:", self.preview)
            lay.addRow("", _hint(f"{len(e.frames)} files. Changing the first frame renumbers the whole sequence "
                                 f"(e.g. 1 → 1001)."))
            for w in (self.name,):
                w.textChanged.connect(self._update)
            self.sep.currentIndexChanged.connect(self._update)
            self.start.valueChanged.connect(self._update)
            self._update()
        else:
            self.name = QLineEdit(e.name)
            lay.addRow("Name:", self.name)
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


class DeptEditor(QWidget):
    """Departamentos del pipeline: lista a la izquierda (Department 1, 2…) y su definición a la derecha."""

    def __init__(self, deps):
        super().__init__()
        import copy
        from .pipeline import DEFAULT_DEPTS
        self._defaults = DEFAULT_DEPTS
        self.deps = copy.deepcopy(list(deps))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        left = QVBoxLayout()
        cap = QLabel("DEPARTMENTS")
        cap.setStyleSheet("color:#4cc2ff; font-weight:bold; font-size:8pt; letter-spacing:1px;")
        left.addWidget(cap)
        self.lst = QListWidget()
        self.lst.setFixedWidth(190)
        self.lst.currentRowChanged.connect(self._load)
        left.addWidget(self.lst, 1)
        bl = QHBoxLayout()
        for txt, tip, fn in (("＋", "Add a department", self._add), ("－", "Remove", self._remove),
                             ("▲", "Move up", lambda: self._move(-1)), ("▼", "Move down", lambda: self._move(1))):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bl.addWidget(b)
        bl.addStretch(1)
        rd = QToolButton()
        rd.setText("Defaults")
        rd.setToolTip("Back to 3D (tasks), DMP and Comp")
        rd.clicked.connect(self._reset)
        bl.addWidget(rd)
        left.addLayout(bl)
        lay.addLayout(left)
        self.form = QWidget()
        f = QFormLayout(self.form)
        f.setContentsMargins(8, 0, 0, 0)
        lw = self.fontMetrics().horizontalAdvance("Folders in each task:") + 12

        def lab(t):                       # ancho fijo: el campo no se achica al cambiar el texto
            lb = QLabel(t)
            lb.setFixedWidth(lw)
            return lb
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("Folder name inside the shot (3D, Comp, DMP…)")
        f.addRow(lab("Folder:"), self.f_name)
        self.f_has = QCheckBox("Has tasks  (Department › Task › folders)")
        f.addRow(lab(""), self.f_has)
        self.f_tasks = QPlainTextEdit()
        self.f_tasks.setPlaceholderText("One task per line; after «:» what goes inside its first folder\n"
                                        "1_matchmove: footage, textures\n7_fx: textures, cache")
        self.f_tasks.setMinimumHeight(130)
        f.addRow(lab("Tasks:"), self.f_tasks)
        self.f_folders = QLineEdit()
        self.f_folders.setPlaceholderText("1_projects, 2_review, 3_publish")
        self.l_folders = lab("Folders:")
        f.addRow(self.l_folders, self.f_folders)
        self.f_hint = _hint("")
        f.addRow(lab(""), self.f_hint)
        lay.addWidget(self.form, 1)
        self.f_name.textEdited.connect(self._store)
        self.f_has.toggled.connect(self._store)
        self.f_tasks.textChanged.connect(self._store)
        self.f_folders.textEdited.connect(self._store)
        self._loading = False
        self._fill()

    def _label(self, i, d):
        return f"Department {i + 1}:  {d.get('name') or '—'}" + ("   (tasks)" if d.get("has_tasks") else "")

    def _fill(self, row=0):
        self.lst.blockSignals(True)
        self.lst.clear()
        for i, d in enumerate(self.deps):
            self.lst.addItem(self._label(i, d))
        self.lst.blockSignals(False)
        if self.deps:
            self.lst.setCurrentRow(max(0, min(row, len(self.deps) - 1)))
        self._load(self.lst.currentRow())

    def _load(self, row):
        ok = 0 <= row < len(self.deps)
        self.form.setEnabled(ok)
        self._loading = True
        d = self.deps[row] if ok else {"name": "", "has_tasks": False, "tasks": "", "folders": ""}
        self.f_name.setText(d.get("name", ""))
        self.f_has.setChecked(bool(d.get("has_tasks")))
        self.f_tasks.setPlainText(d.get("tasks", ""))
        self.f_folders.setText(d.get("folders", ""))
        self._loading = False
        self._sync_ui()

    def _sync_ui(self):
        has = self.f_has.isChecked()
        self.f_tasks.setEnabled(has)
        self.l_folders.setText("Folders in each task:" if has else "Folders:")
        n = self.f_name.text().strip() or "Dept"
        fl = [x.strip() for x in self.f_folders.text().split(",") if x.strip()]
        if has:
            self.f_hint.setText(f"＋ › {n} task creates {n}\\<task>\\" + (", ".join(fl) or "…") +
                                (f"  (the task's extra folders go inside {fl[0]})" if fl else ""))
        else:
            self.f_hint.setText(f"＋ › {n} creates {n}\\" + (", ".join(fl) or "…") +
                                ". In the dropdowns the last one becomes «Stage».")

    def _store(self, *_):
        if self._loading:
            return
        row = self.lst.currentRow()
        if not 0 <= row < len(self.deps):
            return
        d = self.deps[row]
        d["name"] = self.f_name.text().strip()
        d["has_tasks"] = self.f_has.isChecked()
        d["tasks"] = self.f_tasks.toPlainText().strip()
        d["folders"] = self.f_folders.text().strip()
        self.lst.item(row).setText(self._label(row, d))
        self._sync_ui()

    def _add(self):
        self.deps.append({"name": "New", "has_tasks": False, "tasks": "", "folders": "1_projects, 2_review, 3_publish"})
        self._fill(len(self.deps) - 1)
        self.f_name.setFocus()
        self.f_name.selectAll()

    def _remove(self):
        row = self.lst.currentRow()
        if 0 <= row < len(self.deps):
            del self.deps[row]
            self._fill(row)

    def _move(self, k):
        row = self.lst.currentRow()
        j = row + k
        if 0 <= row < len(self.deps) and 0 <= j < len(self.deps):
            self.deps[row], self.deps[j] = self.deps[j], self.deps[row]
            self._fill(j)

    def _reset(self):
        import copy
        self.deps = copy.deepcopy(self._defaults)
        self._fill()

    def value(self):
        return [dict(d) for d in self.deps if d.get("name", "").strip()]


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        cfg = app.cfg
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)

        # --- General
        g = QWidget()
        lay = QFormLayout(g)
        exe_f = "Executables (*.exe)" if IS_WIN else "All (*)"
        w, self.player = self._path_row(cfg["player"], "Player (mrv2, DJV, RV…)", exe_f)
        lay.addRow("Player:", w)
        lay.addRow("", _hint("Opens sequences and videos on double click. Empty = default app."))
        w, self.img_viewer = self._path_row(cfg["image_viewer"], "Image viewer", exe_f)
        lay.addRow("Image viewer:", w)
        lay.addRow("", _hint("Opens images on double click. Empty = default app."))
        w, self.ffmpeg = self._path_row(cfg["ffmpeg"], "ffmpeg.exe", exe_f)
        lay.addRow("ffmpeg:", w)
        found = find_tool(cfg["ffmpeg"], "ffmpeg")
        lay.addRow("", _hint(f"Video thumbnails and info. Found: {found or 'not found'}. "
                             "You can also put ffmpeg.exe and ffprobe.exe in the <b>bin</b> folder."))
        self.cs = QComboBox()
        for label, key in COLORSPACES:
            self.cs.addItem(label, key)
        self.cs.setCurrentIndex(max(0, self.cs.findData(cfg["colorspace"])))
        lay.addRow("EXR color space:", self.cs)
        self.chroma = QCheckBox("Use EXR chromaticities when present in the header")
        self.chroma.setChecked(bool(cfg["use_chromaticities"]))
        lay.addRow("", self.chroma)
        self.sidecar = QCheckBox("Model and folder previews (JPG/PNG with the same name, thumbnail.jpg…)")
        self.sidecar.setChecked(bool(cfg["sidecar_previews"]))
        lay.addRow("", self.sidecar)
        self.threads = QSpinBox()
        self.threads.setRange(1, 16)
        self.threads.setValue(int(cfg["threads"]))
        lay.addRow("Thumbnail threads:", self.threads)
        self.hidden = QCheckBox("Show hidden files and folders")
        self.hidden.setChecked(bool(cfg["show_hidden"]))
        lay.addRow("", self.hidden)
        self.fsizes = QCheckBox("Calculate folder sizes (in the background)")
        self.fsizes.setChecked(bool(cfg["folder_sizes"]))
        lay.addRow("", self.fsizes)
        self.feats = QCheckBox("Tags, rating and collections")
        self.feats.setChecked(bool(cfg["library_features"]))
        lay.addRow("", self.feats)
        self.sysicons = QCheckBox("Show the original icon of programs and documents (not for images, video or audio)")
        self.sysicons.setChecked(bool(cfg["system_icons"]))
        lay.addRow("", self.sysicons)
        clr = QPushButton(f"Clear thumbnail cache ({human_size(app.thumbs.disk_usage())})")
        clr.clicked.connect(lambda: (app.thumbs.clear_disk(), clr.setText("Cache cleared"), app.refresh_views()))
        rst = QPushButton("Reset all…")
        rst.setToolTip("Clears the cache and every setting (Quick access, tabs, views, colors, tags…) "
                       "and restarts VFX Explorer as the first time")
        rst.setStyleSheet("QPushButton{color:#ff8a8a;}")
        rst.clicked.connect(lambda: app.reset_all(self))
        brow = QWidget()
        brl = QHBoxLayout(brow)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.addWidget(clr)
        brl.addWidget(rst)
        brl.addStretch(1)
        lay.addRow("", brow)
        lay.addRow("", _hint(f"Portable data in: {fwd(app.data_dir)}"))
        tabs.addTab(g, "General")

        # --- Pipeline
        pw = QWidget()
        pl = QFormLayout(pw)
        self.p_root = QLineEdit(cfg["pipeline_root"])
        self.p_prefix = QLineEdit(cfg["pipeline_prefix"])
        self.p_excl = QLineEdit(cfg["pipeline_seq_exclude"])
        pl.addRow("Root (drive or UNC):", self.p_root)
        pl.addRow("Project prefix:", self.p_prefix)
        pl.addRow("Not sequences:", self.p_excl)
        pl.addRow("", _hint("Structure: {root}\\{prefix}{PROJECT}\\{SEQ}\\{SHOT}\\{DEPARTMENT}\\…  "
                            "Sequences are folders starting with a number; shots start with PROJECT_."))
        self.p_deps = DeptEditor(app.pipeline.departments())
        pl.addRow(self.p_deps)
        self.p_input = QLineEdit(cfg["pipeline_input"] if cfg["pipeline_input"] is not None else "_input")
        self.p_input.setPlaceholderText("_input")
        self.p_input_subs = QLineEdit(cfg["pipeline_input_subs"] if cfg["pipeline_input_subs"] is not None
                                      else "plates, refs")
        irow = QWidget()
        il = QHBoxLayout(irow)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(self.p_input, 1)
        il.addWidget(QLabel("  with"))
        il.addWidget(self.p_input_subs, 2)
        pl.addRow("Plates / input folder:", irow)
        pl.addRow("", _hint("Folder inside the shot where the plates arrive (and its subfolders; the first one is "
                            "where the plates go). The ＋ creates it and the folder button jumps to the plates."))
        self.p_only = QCheckBox("Dept dropdown shows only these departments (otherwise every folder of the shot)")
        self.p_only.setChecked(app.pipeline.only_listed())
        pl.addRow("", self.p_only)
        self.p_loc = QComboBox()
        for label, key in (("Above the center pane", "center"), ("Left pane", "sidebar"), ("Hidden", "hidden")):
            self.p_loc.addItem(label, key)
        self.p_loc.setCurrentIndex(max(0, self.p_loc.findData(
            "center" if cfg["pipeline_location"] in (None, "top") else cfg["pipeline_location"])))
        pl.addRow("Show the dropdowns:", self.p_loc)
        tabs.addTab(pw, "Pipeline")

        # --- Colores
        from .colors import COLOR_MODES, DEFAULT_NAME_RULES
        cw = QWidget()
        cl = QFormLayout(cw)
        self.cmode = QComboBox()
        for label, key in COLOR_MODES:
            self.cmode.addItem(label, key)
        self.cmode.setCurrentIndex(max(0, self.cmode.findData(cfg["color_mode"])))
        cl.addRow("Automatic colors:", self.cmode)
        cl.addRow("", _hint("By project: each pipeline project gets a color (or the one you set by hand) and "
                            "it gets lighter on sequences and shots. By name: the rules below. "
                            "Manual color always wins. Also changed with the colors button in the left pane."))
        self.fcolor = QComboBox()
        self.fcolor.addItem("Yellow", "yellow")
        self.fcolor.addItem("Light blue", "blue")
        self.fcolor.setCurrentIndex(max(0, self.fcolor.findData(cfg["folder_color"] or "yellow")))
        cl.addRow("Folder color:", self.fcolor)
        self.tlines = QCheckBox("Tree lines take the folder color")
        self.tlines.setChecked(bool(cfg["tree_line_colors"]))
        cl.addRow("", self.tlines)
        self.tstyle = QComboBox()
        self.tstyle.addItem("Chevrons + path line", "chevron")
        self.tstyle.addItem("Solid lines with ⊞ boxes", "solid")
        self.tstyle.addItem("Dotted", "dotted")
        self.tstyle.setCurrentIndex(max(0, self.tstyle.findData(cfg["tree_lines_style"])))
        cl.addRow("Tree lines:", self.tstyle)
        self.ttrace = QCheckBox("Tree Path Tracing: mark the path to the current folder")
        self.ttrace.setChecked(bool(cfg["tree_trace"]))
        cl.addRow("", self.ttrace)
        self.twidth = QSpinBox()
        self.twidth.setRange(1, 6)
        self.twidth.setSuffix(" px")
        self.twidth.setValue(int(cfg["tree_trace_width"] or 2))
        cl.addRow("Trace width:", self.twidth)
        self.tcolor = QComboBox()
        self.tcolor.addItem("Accent color", "accent")
        self.tcolor.addItem("Current folder color", "folder")
        self.tcolor.setCurrentIndex(max(0, self.tcolor.findData(cfg["tree_trace_color"])))
        cl.addRow("Trace color:", self.tcolor)
        self.lcolor = QComboBox()
        for label, hexc in (("Yellow", "#ffcf48"), ("Light blue", "#4cc2ff"), ("Violet", "#8d6fd1"), ("Pink", "#d16fa8"), ("Green", "#3ecf8e"),
                            ("Orange", "#ff9f43"), ("Gray", "#5f6368")):
            self.lcolor.addItem(app.icons.swatch(hexc), label, hexc)
        i = self.lcolor.findData(cfg["lib_tree_line_color"])
        if i < 0:
            self.lcolor.addItem(app.icons.swatch(cfg["lib_tree_line_color"]), cfg["lib_tree_line_color"],
                                cfg["lib_tree_line_color"])
            i = self.lcolor.count() - 1
        self.lcolor.setCurrentIndex(i)
        cl.addRow("VFX Library lines:", self.lcolor)
        self.rules = QPlainTextEdit(cfg["name_rules"] or DEFAULT_NAME_RULES)
        self.rules.setMinimumHeight(220)
        self.rules.setStyleSheet("font-family:Consolas,monospace; font-size:9pt;")
        cl.addRow("Name rules:", self.rules)
        from .core import DEFAULT_COLOR_FILTERS
        cfv = cfg["color_filters"]
        self.cfilters = QPlainTextEdit(DEFAULT_COLOR_FILTERS if cfv is None else cfv)
        self.cfilters.setFont(QFont("Consolas", 9))
        self.cfilters.setMinimumHeight(120)
        rb = QPushButton("Restore default rules")
        rb.clicked.connect(lambda: self.rules.setPlainText(DEFAULT_NAME_RULES))
        cl.addRow("", rb)
        tabs.addTab(cw, "Colors")

        # --- Color filters (separados de las etiquetas de color de carpetas)
        fw = QWidget()
        fl = QFormLayout(fw)
        fl.addRow("", _hint("Paint file names by pattern. Turned on and off with the color filters button "
                            "next to the dual pane buttons."))
        self.cfilters.setMinimumHeight(260)
        fl.addRow("Rules:", self.cfilters)
        fl.addRow("", _hint("One rule per line:  pattern = text color   ·   pattern = text color, background\n"
                            "Several patterns with ;   ·   dir: only folders   ·   * and ? allowed   ·   # comment\n"
                            "e.g.  *.exe;*.msi = #ff5c5c     *.zip;*.rar = #ff9f43     dir:_input = #3ecf8e"))
        rf = QPushButton("Restore default filters")
        rf.clicked.connect(lambda: self.cfilters.setPlainText(DEFAULT_COLOR_FILTERS))
        fl.addRow("", rf)
        tabs.addTab(fw, "Color filters")

        # --- VFX Library
        lw = QWidget()
        ll = QFormLayout(lw)
        self.vres = QComboBox()
        for v in ("960", "1280", "1920", "2560"):
            self.vres.addItem(f"{v} px", int(v))
        self.vres.setCurrentIndex(max(0, self.vres.findData(int(cfg["viewer_res"] or 1280))))
        ll.addRow("Viewer resolution:", self.vres)
        self.vmem = QSpinBox()
        self.vmem.setRange(128, 32768)
        self.vmem.setSingleStep(256)
        self.vmem.setSuffix(" MB")
        self.vmem.setValue(int(cfg["viewer_mem"] or 1024))
        ll.addRow("Frame memory:", self.vmem)
        ll.addRow("", _hint("How many decoded frames are kept so the loop plays smoothly. "
                            "1280 px ≈ 2.7 MB per frame → 1024 MB ≈ 370 frames."))
        self.vauto = QCheckBox("Autoplay on selection")
        self.vauto.setChecked(bool(cfg["viewer_autoplay"]))
        ll.addRow("", self.vauto)
        self.vloop = QCheckBox("Loop by default")
        self.vloop.setChecked(bool(cfg["viewer_loop"]))
        ll.addRow("", self.vloop)
        self.lpretty = QCheckBox("Clean names: «01_assets_3d» shows as «Assets 3D» (F2 shows the real name)")
        self.lpretty.setChecked(bool(cfg["lib_pretty_names"]))
        ll.addRow("", self.lpretty)
        ll.addRow("", _hint("Library folders are added with the ＋ of «VFX LIBRARY» in the left pane. "
                            "Videos play with the ffmpeg set in General."))
        tabs.addTab(lw, "VFX Library")

        # --- Atajos (solo lectura)
        from .shortcuts import SHORTCUTS
        sw = QWidget()
        sl = QVBoxLayout(sw)
        st = QTreeWidget()
        st.setColumnCount(2)
        st.setHeaderLabels(["Keys", "Action"])
        st.setRootIsDecorated(False)
        st.setSelectionMode(QAbstractItemView.NoSelection)
        st.setFocusPolicy(Qt.NoFocus)
        for group, rows in SHORTCUTS:
            g = QTreeWidgetItem([group.upper(), ""])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setForeground(0, QColor("#4cc2ff"))
            g.setFirstColumnSpanned(True)
            st.addTopLevelItem(g)
            for keys, what in rows:
                it = QTreeWidgetItem(["   " + keys, what])
                it.setForeground(0, QColor("#e6e6e6"))
                it.setForeground(1, QColor("#b8b8b8"))
                st.addTopLevelItem(it)
        st.resizeColumnToContents(0)
        st.setColumnWidth(0, st.columnWidth(0) + 24)
        sl.addWidget(st)
        tabs.addTab(sw, "Shortcuts")
        self._shortcuts_tree = st

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        from . import VERSION
        credit = QLabel(f"VFX Explorer {VERSION} · Created by Javi Bravo · "
                        "<a href='https://github.com/javibravo-vfx' style='color:#4cc2ff; text-decoration:none'>"
                        "github.com/javibravo-vfx</a>")
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet("color:#7d8590; font-size:8pt;")
        foot = QHBoxLayout()
        foot.addWidget(credit)
        foot.addStretch(1)
        foot.addWidget(bb)
        outer.addLayout(foot)

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
        old_p = (cfg["pipeline_root"], cfg["pipeline_prefix"], cfg["pipeline_seq_exclude"],
                 json.dumps(cfg["pipeline_departments"]), cfg["pipeline_only_depts"])
        cfg["player"] = self.player.text().strip().strip('"')
        cfg["lib_pretty_names"] = self.lpretty.isChecked()
        cfg["image_viewer"] = self.img_viewer.text().strip().strip('"')
        cfg["ffmpeg"] = self.ffmpeg.text().strip().strip('"')
        cfg["colorspace"] = self.cs.currentData()
        cfg["use_chromaticities"] = self.chroma.isChecked()
        cfg["sidecar_previews"] = self.sidecar.isChecked()
        cfg["threads"] = self.threads.value()
        hidden_changed = cfg["show_hidden"] != self.hidden.isChecked()
        cfg["show_hidden"] = self.hidden.isChecked()
        cfg["pipeline_root"] = self.p_root.text().strip()
        cfg["pipeline_prefix"] = self.p_prefix.text().strip()
        cfg["pipeline_seq_exclude"] = self.p_excl.text().strip()
        cfg.save()
        new_t = (cfg["colorspace"], cfg["use_chromaticities"], cfg["ffmpeg"], cfg["sidecar_previews"])
        cfg["pipeline_departments"] = self.p_deps.value()
        cfg["pipeline_only_depts"] = self.p_only.isChecked()
        cfg["pipeline_input"] = self.p_input.text().strip().strip("\\/") or "_input"
        cfg["pipeline_input_subs"] = self.p_input_subs.text().strip()
        cfg["pipeline_location"] = self.p_loc.currentData()
        new_p = (cfg["pipeline_root"], cfg["pipeline_prefix"], cfg["pipeline_seq_exclude"],
                 json.dumps(cfg["pipeline_departments"]), cfg["pipeline_only_depts"])
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
        cfg["color_filters"] = self.cfilters.toPlainText()
        cfg["system_icons"] = self.sysicons.isChecked()
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
        color = ctypes.c_int(0x00191919)                                                # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # color del caption (Win11)
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))  # esquinas redondeadas
    except Exception:
        pass
