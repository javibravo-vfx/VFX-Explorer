# -*- coding: utf-8 -*-
"""Mouse Down Blow Up: manteniendo apretado el botón sobre la imagen del panel de detalles aparece la imagen
al 100 % (centrada en el punto donde se apretó); moviendo el mouse se panea, al soltar se va."""

import os

from PySide6.QtCore import Qt, QThread, Signal, QPoint, QPointF, QRect, QEvent, QObject
from PySide6.QtGui import QImage, QPainter, QColor, QGuiApplication, QCursor
from PySide6.QtWidgets import QWidget

from .imaging import (oiio_thumb, qt_thumb, video_thumb, pdf_render, HAS_OIIO, OIIO_EXTS, QT_FAST, VIDEO_EXTS)

FULL_MAX = 16384


def full_image(e, settings):
    src = e.thumb_source()
    ext = os.path.splitext(src)[1].lower()
    e2 = ext.lstrip(".")
    if e.cat == "video" or ext in VIDEO_EXTS:
        return video_thumb(src, settings["ffmpeg"], maxdim=FULL_MAX)
    if ext == ".pdf":
        return pdf_render(src, 0, 2400)
    if e2 in QT_FAST:
        return qt_thumb(src, FULL_MAX)
    if e2 in OIIO_EXTS and HAS_OIIO:
        return oiio_thumb(src, settings, maxdim=FULL_MAX)
    return QImage()


class _Loader(QThread):
    done = Signal(object, str)

    def __init__(self, e, settings):
        super().__init__()
        self.e, self.settings = e, settings

    def run(self):
        try:
            img = full_image(self.e, self.settings)
        except Exception:
            img = QImage()
        self.done.emit(img, self.e.path)


class BlowUp(QWidget):
    """Ventana sin bordes con la imagen al 100 %, del tamaño de la imagen (como mucho, la pantalla)."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.img = QImage()
        self.scale = 1.0              # >1 solo mientras se usa el thumbnail (todavía cargando)
        self.ox = self.oy = 0.0       # posición de la imagen dentro de la ventana
        self._W = self._H = 1
        self._anchor = (QPoint(), 0.0, 0.0)
        self.loading = False

    def set_image(self, img, fx, fy, cursor, provisional=False, full_size=None):
        """fx, fy: punto relativo (0-1) de la imagen que tiene que quedar bajo el cursor."""
        self.img = img
        W, H = full_size if full_size else (img.width(), img.height())
        self.scale = W / max(1, img.width())
        self.loading = provisional
        scr = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        w, h = min(W, g.width()), min(H, g.height())
        x = min(max(g.left(), cursor.x() - int(fx * w)), g.right() - w + 1)
        y = min(max(g.top(), cursor.y() - int(fy * h)), g.bottom() - h + 1)
        self.setGeometry(x, y, w, h)
        self._W, self._H = W, H
        # el punto (fx, fy) de la imagen queda bajo el cursor
        lx, ly = cursor.x() - x, cursor.y() - y
        self.ox = self._clampx(lx - fx * W)
        self.oy = self._clampy(ly - fy * H)
        self._anchor = (cursor, self.ox, self.oy)
        self.update()

    def _clampx(self, v):
        return min(0.0, max(self.width() - self._W, v)) if self._W > self.width() else (self.width() - self._W) / 2

    def _clampy(self, v):
        return min(0.0, max(self.height() - self._H, v)) if self._H > self.height() else (self.height() - self._H) / 2

    def pan_to(self, cursor):
        """Mover el mouse recorre la imagen: llevar el mouse de un borde al otro de la ventana alcanza
        para ver toda la imagen."""
        c0, ox0, oy0 = self._anchor
        kx = max(1.0, (self._W - self.width()) / max(1, self.width() / 2))
        ky = max(1.0, (self._H - self.height()) / max(1, self.height() / 2))
        self.ox = self._clampx(ox0 - (cursor.x() - c0.x()) * kx)
        self.oy = self._clampy(oy0 - (cursor.y() - c0.y()) * ky)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101010"))
        if not self.img.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform, self.scale != 1.0)
            p.drawImage(QRect(int(self.ox), int(self.oy), int(self._W), int(self._H)), self.img)
        p.setPen(QColor(255, 255, 255, 60))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self.loading:
            p.setPen(QColor("#d6d6d6"))
            p.drawText(self.rect().adjusted(10, 8, -10, -8), Qt.AlignLeft | Qt.AlignTop, "loading full resolution…")
        p.end()


class BlowUpController(QObject):
    """Engancha el QLabel de la vista previa: press → popup, move → panea, release → se va."""

    def __init__(self, app, label):
        super().__init__(label)
        self.app, self.label = app, label
        self.box = BlowUp()
        self.loader = None
        self.active = False
        self._fx = self._fy = 0.5
        self._cache = (None, None)         # (ruta, QImage) de la última imagen completa
        label.installEventFilter(self)
        label.setCursor(Qt.PointingHandCursor)
        label.setToolTip("Hold the mouse button on the image to see it at 100% (move to pan)")

    def _pix_rect(self):
        pm = self.label.pixmap()
        if pm is None or pm.isNull():
            return None
        r = self.label.contentsRect()
        dpr = pm.devicePixelRatio() or 1.0
        w, h = pm.width() / dpr, pm.height() / dpr
        return QRect(int(r.x() + (r.width() - w) / 2), int(r.y() + (r.height() - h) / 2), int(w), int(h))

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            e = getattr(self.app, "_info_entry", None)
            pr = self._pix_rect()
            if e is None or pr is None or e.kind not in ("file", "seq") or e.kind == "file" and \
                    e.cat not in ("image", "video") and e.ext != ".pdf":
                return False
            pos = ev.position().toPoint()
            if not pr.contains(pos):
                return False
            self._fx = (pos.x() - pr.x()) / max(1, pr.width())
            self._fy = (pos.y() - pr.y()) / max(1, pr.height())
            self.active = True
            self.label.setCursor(Qt.BlankCursor)
            cur = QCursor.pos()
            if self._cache[0] == e.path and not self._cache[1].isNull():
                self.box.set_image(self._cache[1], self._fx, self._fy, cur)
            else:
                thumb = self.label.pixmap().toImage()
                ratio = thumb.width() / max(1, thumb.height())
                guess = (max(thumb.width() * 3, 1280), int(max(thumb.width() * 3, 1280) / ratio))
                self.box.set_image(thumb, self._fx, self._fy, cur, provisional=True, full_size=guess)
                self.loader = _Loader(e, self.app.thumbs.settings)
                self.loader.done.connect(self._loaded)
                self.loader.start()
            self.box.show()
            return True
        if t == QEvent.MouseMove and self.active:
            self.box.pan_to(QCursor.pos())
            return True
        if t == QEvent.MouseButtonRelease and self.active:
            self.active = False
            self.label.setCursor(Qt.PointingHandCursor)
            self.box.hide()
            return True
        return False

    def _loaded(self, img, path):
        if not img.isNull():
            self._cache = (path, img)
        if self.active and not img.isNull():
            # mantiene el mismo punto de la imagen bajo el cursor que estaba mirando
            fx = (QCursor.pos().x() - self.box.x() - self.box.ox) / max(1, self.box._W)
            fy = (QCursor.pos().y() - self.box.y() - self.box.oy) / max(1, self.box._H)
            self.box.set_image(img, min(1, max(0, fx)), min(1, max(0, fy)), QCursor.pos())
