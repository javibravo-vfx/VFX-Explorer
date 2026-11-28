# -*- coding: utf-8 -*-
"""Slots del player de la VFX Library: Ctrl+1…4 (o clic derecho en el circulito) guardan lo seleccionado
(video, secuencia, imagen, sonido…) en un canal; 1…4 (o clic en el circulito) saltan a eso, en su carpeta y
reproduciéndose desde donde estaba."""

import os

from PySide6.QtCore import Qt, QRectF, QEvent, QObject
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget

N_SLOTS = 4
D = 19          # diámetro de cada circulito
GAP = 6


class SlotBar(QWidget):
    """Cuatro circulitos verticales a la izquierda del viewport del player."""

    def __init__(self, canvas, ctl):
        super().__init__(canvas)
        self.ctl = ctl
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._hover = -1
        self.setFixedSize(D + 8, N_SLOTS * D + (N_SLOTS - 1) * GAP + 8)
        canvas.installEventFilter(self)
        self._place()

    def _place(self):
        c = self.parentWidget()
        self.move(10, max(4, (c.height() - self.height()) // 2))
        self.raise_()

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self._place()
        return False

    def _rect(self, i):
        return QRectF(4, 4 + i * (D + GAP), D, D)

    def _hit(self, pos):
        for i in range(N_SLOTS):
            if self._rect(i).adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, ev):
        h = self._hit(ev.position())
        if h != self._hover:
            self._hover = h
            s = self.ctl.slots()[h] if h >= 0 else None
            self.setToolTip(
                (f"{h + 1}: {s['name']}\n{s['dir']}\nClick or {h + 1}: go · right-click: put the selected item "
                 f"here (or clear it if it's the same) · Ctrl+{h + 1}: put the selected item here") if s else
                (f"Slot {h + 1} empty — right-click or Ctrl+{h + 1} puts the selected item here"
                 if h >= 0 else ""))
            self.update()

    def leaveEvent(self, ev):
        self._hover = -1
        self.update()

    def mousePressEvent(self, ev):
        i = self._hit(ev.position())
        if i < 0:
            return
        if ev.button() == Qt.RightButton:
            self.ctl.toggle(i)
        else:
            self.ctl.go(i)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPointSizeF(7.2)
        f.setBold(True)
        p.setFont(f)
        slots = self.ctl.slots()
        cur = self.ctl.current_slot()
        for i in range(N_SLOTS):
            r = self._rect(i)
            used = bool(slots[i])
            hov = i == self._hover
            if i == cur:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(76, 194, 255, 230))
                txt = QColor("#0b1a22")
            elif used:
                p.setPen(QPen(QColor(255, 255, 255, 200 if hov else 150), 1.4))
                p.setBrush(QColor(20, 20, 20, 170))
                txt = QColor(255, 255, 255, 230 if hov else 190)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 90 if hov else 45), 1.2))
                p.setBrush(QColor(20, 20, 20, 70))
                txt = QColor(255, 255, 255, 110 if hov else 60)
            p.drawEllipse(r)
            p.setPen(txt)
            p.drawText(r, Qt.AlignCenter, str(i + 1))
        p.end()


class SlotController(QObject):
    def __init__(self, app, libpage):
        super().__init__(libpage)
        self.app, self.page = app, libpage
        self.viewer = libpage.viewer
        self.bar = SlotBar(self.viewer.canvas, self)

    def slots(self):
        s = list(self.app.cfg["lib_slots"] or [])
        return (s + [None] * N_SLOTS)[:N_SLOTS]

    def _selected(self):
        """Lo seleccionado en la librería (video, secuencia, imagen, sonido…); si no, lo que muestra el player."""
        ents = self.app.libpane.selected_entries() if self.app.libpane.tabs else []
        if len(ents) == 1 and ents[0].kind in ("file", "seq"):
            return ents[0]
        e = self.viewer.entry
        return e if (e is not None and e.kind in ("file", "seq")) else None

    def current_slot(self):
        e = self._selected()
        if e is None:
            return -1
        for i, s in enumerate(self.slots()):
            if s and s.get("path") == e.path:
                return i
        return -1

    def toggle(self, i):
        """Clic derecho: pone ahí lo seleccionado; si ya estaba en ese slot, lo saca."""
        e = self._selected()
        s = self.slots()[i]
        if s and (e is None or s.get("path") == e.path):
            self.clear(i)
            self.app.status.setText(f"Slot {i + 1} cleared")
        else:
            self.assign(i)

    def assign(self, i):
        e = self._selected()
        if e is None:
            self.app.status.setText("Select a video, sequence, image or sound in the VFX Library first")
            return
        s = self.slots()
        s = [x if not (x and x.get("path") == e.path) else None for x in s]   # un video, un solo canal
        s[i] = {"path": e.path, "dir": e.dirpath, "name": e.name}
        self.app.cfg["lib_slots"] = s
        self.app.cfg.save()
        self.app.status.setText(f"Slot {i + 1}: {e.name}")
        self.bar.update()

    def clear(self, i):
        s = self.slots()
        s[i] = None
        self.app.cfg["lib_slots"] = s
        self.app.cfg.save()
        self.bar.update()

    def go(self, i):
        s = self.slots()[i]
        if not s:
            self.app.status.setText(f"Slot {i + 1} is empty — Ctrl+{i + 1} puts the current video there")
            return
        if self.app.mode() != "library":
            self.app.set_mode("library")
        L = self.app.libpane
        cur = L.current_dir()
        L._f7_resume = True                         # sigue desde el frame donde estaba
        if cur and os.path.normcase(os.path.normpath(cur)) == os.path.normcase(os.path.normpath(s["dir"])):
            L.pending_select = [s["name"]]
            L._select_pending()
        else:
            from .core import net_root
            if not net_root(s["dir"]) and not os.path.isdir(s["dir"]):
                L._f7_resume = False
                self.app.status.setText(f"Slot {i + 1}: the folder is not available ({s['dir']})")
                return
            L.navigate(s["dir"])
            L.pending_select = [s["name"]]
        self.bar.update()

    def refresh(self):
        self.bar.update()
