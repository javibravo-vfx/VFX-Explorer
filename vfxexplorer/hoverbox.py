# -*- coding: utf-8 -*-
"""Hover box: al dejar el mouse quieto sobre un ítem aparece un preview grande al lado del cursor
(imagen / primer frame de la secuencia / video, texto, contenido de una carpeta)."""

import os

from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QObject
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QApplication, QAbstractItemView

from .core import human_size, fmt_time, reachable
from .models import ROLE_ENTRY

TEXT_EXTS = {".txt", ".ini", ".json", ".xml", ".yaml", ".yml", ".py", ".md", ".csv", ".log", ".nk", ".cfg",
             ".bat", ".cmd", ".ps1", ".mel", ".ma", ".usda", ".ocio", ".lut", ".cube", ".sh", ".toml", ".js",
             ".html", ".css", ".srt", ".edl", ".xmp"}
BOX_W = 380


class HoverBox(QFrame):
    def __init__(self, app):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.app = app
        self.setObjectName("hoverBox")
        self.setStyleSheet("#hoverBox{background:#202020; border:1px solid #3a3a3a; border-radius:6px;}"
                           "QLabel{color:#d6d6d6; background:transparent;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        self.text = QLabel()
        self.text.setTextFormat(Qt.PlainText)
        self.text.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace; font-size:8.5pt; color:#c8c8c8;")
        self.text.setWordWrap(False)
        self.text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.cap = QLabel()
        self.cap.setWordWrap(True)
        self.cap.setStyleSheet("font-size:8.5pt; color:#9d9d9d;")
        lay.addWidget(self.pic)
        lay.addWidget(self.text)
        lay.addWidget(self.cap)
        self.timer = QTimer(self, singleShot=True, interval=650, timeout=self._fire)
        self._view = None
        self._ix = None
        self._entry = None
        self._key = None
        app.thumbs.ready.connect(self._thumb_ready)
        self._watch = _Filter(self)

    # ---------------- enganche a las vistas
    def attach(self, view):
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self._watch)
        view.installEventFilter(self._watch)

    def enabled(self):
        return bool(self.app.cfg["hover_box"])

    def _event(self, obj, ev):
        t = ev.type()
        if t == QEvent.MouseMove:
            view = obj.parent() if isinstance(obj.parent(), QAbstractItemView) else None
            if view is None or not self.enabled() or QApplication.mouseButtons() != Qt.NoButton:
                self.hide_box()
                return
            ix = view.indexAt(ev.position().toPoint())
            if not ix.isValid():
                self.hide_box()
                return
            ix = ix.sibling(ix.row(), 0)
            if self.isVisible() and self._view is view and self._ix == ix:
                self._place()
                return
            self.hide_box(keep_timer=True)
            self._view, self._ix = view, ix
            self.timer.start()
        elif t in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.Wheel,
                   QEvent.KeyPress, QEvent.Hide, QEvent.FocusOut, QEvent.DragEnter):
            self.hide_box()

    def hide_box(self, keep_timer=False):
        if not keep_timer:
            self.timer.stop()
        self._entry = None
        self._key = None
        if self.isVisible():
            self.hide()

    # ---------------- contenido
    def _fire(self):
        view, ix = self._view, self._ix
        if view is None or ix is None or not ix.isValid() or not view.isVisible() \
                or not self.app.isActiveWindow() or QApplication.activePopupWidget() is not None:
            return
        e = ix.data(ROLE_ENTRY)
        if e is None or e.kind in ("header", "drive"):
            return
        self._entry = e
        self.pic.clear()
        self.pic.setMinimumSize(0, 0)
        self.pic.setMaximumSize(16777215, 16777215)
        self.pic.hide()
        self.text.hide()
        shown = False
        if e.kind == "dir":
            shown = self._folder(e)
        elif e.kind == "file" and e.ext in TEXT_EXTS:
            shown = self._textfile(e)
        if not shown:
            pm = self.app.thumbs.get(e) if self.app.thumbs.can_thumb(e) else None
            self._key = self.app.thumbs.key_for(e) if self.app.thumbs.can_thumb(e) else None
            if pm is None:
                pm = self.app.sys_icon(e, 96) or (self.app.icons.folder(self.app.dir_color(e.path), 96)
                                                  if e.kind == "dir" else None)
            if pm is not None:
                self._set_pic(pm)
            elif self._key:                          # el thumbnail se está generando: aparece solo
                self.pic.setText("<span style='color:#777'>loading preview…</span>")
                self.pic.setFixedSize(BOX_W, int(BOX_W * 0.56))
                self.pic.show()
            else:
                return
        self.cap.setText(self._caption(e))
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()

    def _set_pic(self, pm):
        w = BOX_W
        h = int(BOX_W * 0.75)
        if pm.width() > w or pm.height() > h:
            pm = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif pm.width() < w * 0.6 and pm.width() >= 64:       # thumbnails chicos: hasta 1.5x
            k = min(1.5, w / pm.width(), h / pm.height())
            pm = pm.scaled(int(pm.width() * k), int(pm.height() * k), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pic.setMinimumSize(0, 0)
        self.pic.setMaximumSize(16777215, 16777215)
        self.pic.setPixmap(pm)
        self.pic.show()

    def _thumb_ready(self, key):
        if self.isVisible() and self._key and key == self._key and self._entry is not None:
            pm = self.app.thumbs.get(self._entry)
            if pm is not None:
                self._set_pic(pm)
                self.adjustSize()
                self._place()

    def _textfile(self, e):
        if not reachable(e.path):
            return False
        try:
            with open(e.path, "rb") as f:
                raw = f.read(6000)
        except OSError:
            return False
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                txt = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        lines = txt.replace("\t", "    ").splitlines()[:22]
        lines = [(ln[:70] + "…") if len(ln) > 70 else ln for ln in lines]
        self.text.setText("\n".join(lines) or "(empty)")
        self.text.show()
        return True

    def _folder(self, e):
        if not reachable(e.path):
            return False
        try:
            with os.scandir(e.path) as it:
                items = []
                for d in it:
                    if d.name.startswith("."):
                        continue
                    items.append((not d.is_dir(), d.name.lower(), d.name, d.is_dir()))
                    if len(items) > 400:
                        break
        except OSError:
            return False
        items.sort()
        n = len(items)
        show = [("▸ " if isdir else "   ") + name for _, _, name, isdir in items[:18]]
        if n > 18:
            show.append(f"   … {n - 18} more")
        self.text.setText("\n".join(show) or "(empty folder)")
        self.text.show()
        return True

    def _caption(self, e):
        parts = [f"<b style='color:#e8e8e8'>{_esc(e.name)}</b>"]
        meta = []
        if e.kind == "seq":
            meta.append(f"{len(e.files)} frames · {e.frames[0]}-{e.frames[-1]}")
        if e.kind != "dir" and e.size:
            meta.append(human_size(e.size))
        if e.mtime:
            meta.append(fmt_time(e.mtime))
        if meta:
            parts.append(" · ".join(meta))
        self.cap.setTextFormat(Qt.RichText)
        return "<br>".join(parts)

    def _place(self):
        pos = QCursor.pos() + QPoint(18, 20)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        w, h = self.sizeHint().width(), self.sizeHint().height()
        x = min(pos.x(), g.right() - w - 4)
        y = pos.y() if pos.y() + h < g.bottom() else max(g.top(), QCursor.pos().y() - h - 12)
        if x < QCursor.pos().x() and y <= QCursor.pos().y() <= y + h:   # no tapar el cursor
            x = max(g.left(), QCursor.pos().x() - w - 18)
        self.move(x, y)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Filter(QObject):
    def __init__(self, box):
        super().__init__(box)
        self.box = box

    def eventFilter(self, obj, ev):
        try:
            self.box._event(obj, ev)
        except RuntimeError:
            pass
        return False
