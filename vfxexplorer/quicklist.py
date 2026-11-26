# -*- coding: utf-8 -*-
"""Acceso rápido estilo Windows 11: filas cómodas, divisor entre las carpetas de Windows y las fijadas,
pin a la derecha, y soltar carpetas encima para fijarlas."""

import os

from PySide6.QtCore import Qt, QSize, QRect, Signal, QMimeData, QUrl
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate, QAbstractItemView, QStyle, QToolButton

ROLE_PATH = Qt.UserRole
ROLE_SYS = Qt.UserRole + 1       # escritorio, descargas… (de Windows)
ROLE_SEP = Qt.UserRole + 2       # divisor
ROLE_HIDDEN = Qt.UserRole + 3    # oculto (se ve atenuado con el ojito prendido)
ROLE_WSPIN = Qt.UserRole + 5     # Workspace Pin (mostrado en Quick access, después de la línea)
TAB_MIME = "application/x-vfxexplorer-path"   # una pestaña arrastrada (no lleva URLs: nadie copia nada)


def dropped_paths(md, accept_files=True):
    """Rutas de un arrastre: archivos/carpetas, o la carpeta de una pestaña arrastrada."""
    if md.hasFormat(TAB_MIME):
        p = bytes(md.data(TAB_MIME)).decode("utf-8", "replace")
        return [os.path.normpath(p)] if p and os.path.isdir(p) else []
    if not md.hasUrls():
        return []
    return [os.path.normpath(u.toLocalFile()) for u in md.urls()
            if u.isLocalFile() and (accept_files or os.path.isdir(u.toLocalFile()))]


def tab_mime(path):
    md = QMimeData()
    md.setData(TAB_MIME, path.encode("utf-8"))
    md.setText(path)
    return md


class QuickDelegate(QStyledItemDelegate):
    def __init__(self, view, pin_icon, wspin_icon=None):
        super().__init__(view)
        self.view = view
        self.pin = pin_icon
        self.wspin = wspin_icon or pin_icon

    def sizeHint(self, option, index):
        if index.data(ROLE_SEP):
            return QSize(10, 13)
        return QSize(10, 30)

    def paint(self, p, option, index):
        if index.data(ROLE_SEP):
            p.save()
            hot = index.data(ROLE_WSPIN) and getattr(self.view, "_pins_hot", False)
            p.setPen(QPen(QColor("#4cc2ff" if hot else "#3a3a3a"), 2 if hot else 1))
            y = option.rect.center().y()
            p.drawLine(option.rect.left() + 10, y, option.rect.right() - 10, y)
            p.restore()
            return
        if index.data(ROLE_HIDDEN):
            p.save()
            p.setOpacity(0.4)
        super().paint(p, option, index)
        if index.data(ROLE_HIDDEN):
            p.restore()
        if index.data(ROLE_PATH) and not index.data(ROLE_SYS) and not index.data(ROLE_HIDDEN):
            r = option.rect
            hover = option.state & QStyle.State_MouseOver
            p.save()
            p.setOpacity(1.0 if hover else 0.55)
            ws = index.data(ROLE_WSPIN) or getattr(self.view, "all_wspins", False)
            (self.wspin if ws else self.pin).paint(p, QRect(r.right() - 24, r.center().y() - 7, 14, 14))
            p.restore()


class QuickList(QListWidget):
    """Lista de acceso rápido. Se reordena arrastrando y acepta carpetas soltadas desde los árboles o el panel.
    En Quick access, la parte de los Workspace Pins (después de su línea) recibe carpetas y archivos para el
    workspace (dropped_pins)."""
    dropped = Signal(list)
    dropped_pins = Signal(list)

    def __init__(self, pin_icon, accept_files=False, wspin_icon=None, all_wspins=False):
        super().__init__()
        self.accept_files = accept_files            # Workspace Pins: también archivos
        self.all_wspins = all_wspins                # la lista entera son Workspace Pins (otro pin)
        self._pins_hot = False
        self.setObjectName("quickList")
        self.setItemDelegate(QuickDelegate(self, pin_icon, wspin_icon))
        self.setIconSize(QSize(18, 18))
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QListWidget::item{padding-left:6px;}")

    def _in_pins_zone(self, pos):
        """¿El mouse está sobre la parte de Workspace Pins (la línea y lo que sigue)?"""
        first = next((i for i in range(self.count()) if self.item(i).data(ROLE_WSPIN)), None)
        if first is None:
            return False
        it = self.itemAt(pos)
        if it is not None:
            return self.row(it) >= first
        return pos.y() >= self.visualItemRect(self.item(first)).top()

    def _external(self, ev):
        """(rutas, ¿va a Workspace Pins?)"""
        if ev.source() is self:
            return [], False
        zone = self._in_pins_zone(ev.position().toPoint())
        return dropped_paths(ev.mimeData(), self.accept_files or zone), zone

    def _hot(self, on):
        if on != self._pins_hot:
            self._pins_hot = on
            self.viewport().update()

    def dragEnterEvent(self, ev):
        if ev.source() is self:
            super().dragEnterEvent(ev)
            return
        paths, zone = self._external(ev)
        if paths:
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            self._hot(zone)
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if ev.source() is self:
            super().dragMoveEvent(ev)
            return
        paths, zone = self._external(ev)
        if paths:
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            self._hot(zone)
        else:
            self._hot(False)
            ev.ignore()

    def dragLeaveEvent(self, ev):
        self._hot(False)
        super().dragLeaveEvent(ev)

    def dropEvent(self, ev):
        self._hot(False)
        if ev.source() is self:
            super().dropEvent(ev)
            return
        paths, zone = self._external(ev)
        if paths:
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            (self.dropped_pins if zone else self.dropped).emit(paths)
        else:
            ev.ignore()


class DropTabButton(QToolButton):
    """Pestaña «WORKSPACE PINS»: se le pueden soltar carpetas o archivos aunque se esté viendo Quick access."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._hot = False

    def _paths(self, ev):
        return dropped_paths(ev.mimeData(), True)

    def _set_hot(self, on):
        if on != self._hot:
            self._hot = on
            self.setProperty("hot", on)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragEnterEvent(self, ev):
        if self.isEnabled() and self._paths(ev):
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            self._set_hot(True)
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if self.isEnabled() and self._paths(ev):
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev):
        self._set_hot(False)

    def dropEvent(self, ev):
        self._set_hot(False)
        paths = self._paths(ev)
        if paths:
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            self.dropped.emit(paths)
        else:
            ev.ignore()
