# -*- coding: utf-8 -*-
"""Íconos de las carpetas principales de la VFX Library, elegidos por las palabras del nombre
(«01_assets_3d» → cubo, «lighting» / «hdri» → lamparita…). Celestes, como las carpetas de la librería."""

import re

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF, QIcon, QPainterPath, QFont

ACCENT = "#4cc2ff"

# (palabras, ícono) — gana la primera que aparezca en el nombre
RULES = [
    (("3d", "asset", "assets", "model", "models", "modelos", "kitbash", "props", "geo", "geometry"), "cube"),
    (("texture", "textures", "texturas", "surface", "surfaces", "material", "materials", "shader", "shaders",
      "pbr", "megascans"), "texture"),
    (("hdri", "hdr", "light", "lights", "lighting", "iluminacion", "ies", "luces"), "light"),
    (("vdb", "sim", "sims", "simulation", "simulations", "simulaciones", "volume", "volumes", "smoke",
      "clouds"), "cloud"),
    (("mocap", "motion", "animation", "animations", "anim", "rig", "rigs"), "mocap"),
    (("vfx", "stock", "element", "elements", "fx", "elementos", "footage"), "spark"),
    (("reference", "references", "ref", "refs", "referencias", "moodboard", "inspiration"), "photo"),
    (("pipeline", "tool", "tools", "script", "scripts", "plugin", "plugins", "software", "apps"), "wrench"),
    (("learning", "tutorial", "tutorials", "course", "courses", "training", "cursos", "docs", "books",
      "education"), "cap"),
    (("admin", "administration", "business", "invoices", "contracts", "legal"), "briefcase"),
    (("incoming", "inbox", "downloads", "download", "temp", "tmp", "entrada"), "inbox"),
    (("personal", "private", "me", "mine"), "person"),
    (("archive", "archives", "archivo", "old", "backup", "backups", "projects", "proyectos"), "archive"),
    (("library", "libraries", "biblioteca"), "books"),
    (("audio", "sound", "sounds", "sfx", "music", "musica"), "note"),
    (("font", "fonts", "typography", "tipografias"), "font"),
    (("video", "videos", "plates", "film"), "film"),
]


def kind_for(name):
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w and not w.isdigit()]
    for keys, kind in RULES:
        if any(w in keys for w in words):
            return kind
    return None


def cube_pixmap(size, color=ACCENT, dpr=2):
    """Cubo isométrico (axonométrico de verdad: ángulos de 30°), tres caras con luz distinta."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    s = float(size)
    cx, cy, r = s / 2, s / 2, s * .46
    k = 0.8660254 * r                          # cos 30°
    top, bot = QPointF(cx, cy - r), QPointF(cx, cy + r)
    ur, lr = QPointF(cx + k, cy - r / 2), QPointF(cx + k, cy + r / 2)
    ul, ll = QPointF(cx - k, cy - r / 2), QPointF(cx - k, cy + r / 2)
    mid = QPointF(cx, cy)
    p.setPen(QPen(c.darker(230), max(0.5, s / 40)))
    p.setBrush(c.lighter(155))
    p.drawPolygon(QPolygonF([top, ur, mid, ul]))
    p.setBrush(c)
    p.drawPolygon(QPolygonF([ul, mid, bot, ll]))
    p.setBrush(c.darker(165))
    p.drawPolygon(QPolygonF([mid, ur, lr, bot]))
    p.end()
    return pm


def icon_pixmap(kind, size, color=ACCENT, dpr=2):
    if kind == "cube":
        return cube_pixmap(size, color, dpr)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    s = float(size)
    pen = QPen(c, s * .085, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    fill = QColor(c)
    fill.setAlpha(90)
    if kind == "texture":                      # tablero
        cell = s * .26
        x0, y0 = s * .11, s * .11
        for i in range(3):
            for j in range(3):
                if (i + j) % 2 == 0:
                    p.fillRect(QRectF(x0 + i * cell, y0 + j * cell, cell, cell), c)
        p.drawRect(QRectF(x0, y0, cell * 3, cell * 3))
    elif kind == "light":                      # lamparita
        p.setBrush(fill)
        p.drawEllipse(QPointF(s * .5, s * .4), s * .26, s * .26)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * .4, s * .76), QPointF(s * .6, s * .76))
        p.drawLine(QPointF(s * .42, s * .88), QPointF(s * .58, s * .88))
    elif kind == "cloud":                      # nube / volumen
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        path.addEllipse(QPointF(s * .34, s * .58), s * .18, s * .17)
        path.addEllipse(QPointF(s * .55, s * .44), s * .22, s * .22)
        path.addEllipse(QPointF(s * .74, s * .6), s * .15, s * .14)
        path.addRoundedRect(QRectF(s * .18, s * .58, s * .7, s * .17), s * .08, s * .08)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawPath(path.simplified())
    elif kind == "mocap":                      # figura con marcadores
        p.drawEllipse(QPointF(s * .5, s * .18), s * .1, s * .1)
        p.drawLine(QPointF(s * .5, s * .3), QPointF(s * .5, s * .6))
        p.drawLine(QPointF(s * .22, s * .42), QPointF(s * .78, s * .42))
        p.drawLine(QPointF(s * .5, s * .6), QPointF(s * .3, s * .9))
        p.drawLine(QPointF(s * .5, s * .6), QPointF(s * .7, s * .9))
        p.setBrush(c)
        for pt in ((.22, .42), (.78, .42), (.3, .9), (.7, .9)):
            p.drawEllipse(QPointF(s * pt[0], s * pt[1]), s * .06, s * .06)
    elif kind == "spark":                      # destello de 4 puntas
        path = QPainterPath()
        cx, cy = s * .46, s * .54
        path.moveTo(cx, cy - s * .4)
        path.quadTo(cx, cy, cx + s * .38, cy)
        path.quadTo(cx, cy, cx, cy + s * .4)
        path.quadTo(cx, cy, cx - s * .38, cy)
        path.quadTo(cx, cy, cx, cy - s * .4)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        p.drawEllipse(QPointF(s * .8, s * .2), s * .07, s * .07)
    elif kind == "photo":                      # foto
        p.drawRoundedRect(QRectF(s * .1, s * .2, s * .8, s * .62), s * .08, s * .08)
        path = QPainterPath()
        path.moveTo(s * .16, s * .76); path.lineTo(s * .4, s * .5); path.lineTo(s * .56, s * .64)
        path.lineTo(s * .66, s * .56); path.lineTo(s * .84, s * .76); path.closeSubpath()
        p.fillPath(path, c)
        p.setBrush(c)
        p.drawEllipse(QPointF(s * .68, s * .36), s * .06, s * .06)
    elif kind == "wrench":                     # llave
        p.save()
        p.translate(s * .5, s * .5)
        p.rotate(45)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(-s * .07, -s * .12, s * .14, s * .5), s * .05, s * .05)
        p.drawEllipse(QPointF(0, -s * .24), s * .18, s * .18)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.drawRect(QRectF(-s * .06, -s * .44, s * .12, s * .2))
        p.restore()
    elif kind == "cap":                        # birrete
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * .5, s * .2), QPointF(s * .94, s * .4), QPointF(s * .5, s * .6),
                                 QPointF(s * .06, s * .4)]))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(s * .26, s * .4, s * .48, s * .4), 180 * 16, 180 * 16)
        p.drawLine(QPointF(s * .86, s * .44), QPointF(s * .86, s * .7))
    elif kind == "briefcase":
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(s * .1, s * .32, s * .8, s * .52), s * .07, s * .07)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * .36, s * .16, s * .28, s * .16), s * .04, s * .04)
        p.drawLine(QPointF(s * .1, s * .54), QPointF(s * .9, s * .54))
    elif kind == "inbox":                      # bandeja con flecha
        p.drawLine(QPointF(s * .5, s * .1), QPointF(s * .5, s * .5))
        p.drawPolyline(QPolygonF([QPointF(s * .34, s * .36), QPointF(s * .5, s * .52), QPointF(s * .66, s * .36)]))
        p.drawPolyline(QPolygonF([QPointF(s * .1, s * .58), QPointF(s * .1, s * .88), QPointF(s * .9, s * .88),
                                  QPointF(s * .9, s * .58)]))
        p.drawPolyline(QPolygonF([QPointF(s * .1, s * .62), QPointF(s * .32, s * .62), QPointF(s * .38, s * .72),
                                  QPointF(s * .62, s * .72), QPointF(s * .68, s * .62), QPointF(s * .9, s * .62)]))
    elif kind == "person":
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(s * .5, s * .3), s * .17, s * .17)
        p.drawChord(QRectF(s * .16, s * .54, s * .68, s * .6), 0, 180 * 16)
    elif kind == "archive":                    # caja de archivo
        p.setBrush(fill)
        p.drawRect(QRectF(s * .1, s * .16, s * .8, s * .2))
        p.drawRect(QRectF(s * .16, s * .36, s * .68, s * .5))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * .4, s * .52), QPointF(s * .6, s * .52))
    elif kind == "books":                      # libros en un estante
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(s * .14, s * .2, s * .14, s * .64))
        p.drawRect(QRectF(s * .32, s * .14, s * .14, s * .7))
        p.save()
        p.translate(s * .62, s * .84)
        p.rotate(-16)
        p.drawRect(QRectF(0, -s * .66, s * .14, s * .66))
        p.restore()
        p.drawRect(QRectF(s * .08, s * .86, s * .84, s * .06))
    elif kind == "note":                       # nota musical
        p.setBrush(c)
        p.drawEllipse(QPointF(s * .32, s * .74), s * .14, s * .11)
        p.drawEllipse(QPointF(s * .72, s * .64), s * .14, s * .11)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * .45, s * .72), QPointF(s * .45, s * .16))
        p.drawLine(QPointF(s * .85, s * .62), QPointF(s * .85, s * .1))
        p.drawLine(QPointF(s * .45, s * .16), QPointF(s * .85, s * .1))
    elif kind == "font":
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(s * .78))
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "Aa")
    elif kind == "film":                       # tira de película
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(s * .14, s * .1, s * .72, s * .8), s * .06, s * .06)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        for y in (.18, .38, .58, .78):
            p.drawRect(QRectF(s * .19, s * y - s * .04, s * .08, s * .08))
            p.drawRect(QRectF(s * .73, s * y - s * .04, s * .08, s * .08))
    elif kind == "vfxlib":                     # raíz «VFX Library»: estante con un destello
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(s * .1, s * .24, s * .13, s * .62))
        p.drawRect(QRectF(s * .28, s * .3, s * .13, s * .56))
        p.drawRect(QRectF(s * .08, s * .86, s * .84, s * .06))
        path = QPainterPath()
        cx, cy = s * .7, s * .5
        path.moveTo(cx, cy - s * .3)
        path.quadTo(cx, cy, cx + s * .24, cy)
        path.quadTo(cx, cy, cx, cy + s * .3)
        path.quadTo(cx, cy, cx - s * .24, cy)
        path.quadTo(cx, cy, cx, cy - s * .3)
        p.drawPath(path)
    p.end()
    return pm


_CACHE = {}


def folder_icon_for(name, size=18):
    kind = kind_for(name)
    if not kind:
        return None
    key = (kind, size)
    if key not in _CACHE:
        _CACHE[key] = QIcon(icon_pixmap(kind, size))
    return _CACHE[key]


def root_icon(size=18):
    key = ("vfxlib", size)
    if key not in _CACHE:
        _CACHE[key] = QIcon(icon_pixmap("vfxlib", size))
    return _CACHE[key]
