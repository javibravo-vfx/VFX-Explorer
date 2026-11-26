# -*- coding: utf-8 -*-
"""Acceso rápido estilo Windows 11: filas cómodas, divisor entre las carpetas de Windows y las fijadas,
pin a la derecha, y soltar carpetas encima para fijarlas."""

import os

from PySide6.QtCore import Qt, QSize, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate, QAbstractItemView, QStyle, QToolButton

ROLE_PATH = Qt.UserRole
ROLE_SYS = Qt.UserRole + 1       # escritorio, descargas… (de Windows)
ROLE_SEP = Qt.UserRole + 2       # divisor
ROLE_HIDDEN = Qt.UserRole + 3    # oculto (se ve atenuado con el ojito prendido)


class QuickDelegate(QStyledItemDelegate):
    def __init__(self, view, pin_icon):
        super().__init__(view)
        self.pin = pin_icon

    def sizeHint(self, option, index):
        if index.data(ROLE_SEP):
            return QSize(10, 13)
        return QSize(10, 30)

    def paint(self, p, option, index):
        if index.data(ROLE_SEP):
            p.save()
            p.setPen(QPen(QColor("#3a3a3a"), 1))
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
            self.pin.paint(p, QRect(r.right() - 24, r.center().y() - 7, 14, 14))
            p.restore()


class QuickList(QListWidget):
    """Lista de acceso rápido. Se reordena arrastrando y acepta carpetas soltadas desde los árboles o el panel."""
    dropped = Signal(list)

    def __init__(self, pin_icon, accept_files=False):
        super().__init__()
        self.accept_files = accept_files            # Workspace Pins: también archivos
        self.setObjectName("quickList")
        self.setItemDelegate(QuickDelegate(self, pin_icon))
        self.setIconSize(QSize(18, 18))
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QListWidget::item{padding-left:6px;}")

    def _external_dirs(self, ev):
        if ev.source() is self or not ev.mimeData().hasUrls():
            return []
        return [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls()
                if u.isLocalFile() and (self.accept_files or os.path.isdir(u.toLocalFile()))]


    def dragEnterEvent(self, ev):
        if ev.source() is self:
            super().dragEnterEvent(ev)
        elif self._external_dirs(ev):
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if ev.source() is self:
            super().dragMoveEvent(ev)
        elif self._external_dirs(ev):
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
        else:
            ev.ignore()

    def dropEvent(self, ev):
        if ev.source() is self:
            super().dropEvent(ev)
            return
        dirs = self._external_dirs(ev)
        if dirs:
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            self.dropped.emit(dirs)
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
        md = ev.mimeData()
        if not md.hasUrls():
            return []
        return [os.path.normpath(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]

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
