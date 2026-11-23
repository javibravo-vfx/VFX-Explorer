# -*- coding: utf-8 -*-
"""VFX Library: página con viewer arriba y archivos abajo, y la sección del sidebar con las raíces de la librería."""

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QToolButton, QLabel, QMenu, QFileDialog)

from .viewer import Viewer
from .pane import FilePane


class LibraryPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.viewer = Viewer(app)
        self.pane = FilePane(app, "L")
        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(self.viewer)
        self.split.addWidget(self.pane)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setSizes([520, 380])
        lay.addWidget(self.split)
        self._debounce = QTimer(self, singleShot=True, interval=140, timeout=self._load_selected)
        self.pane.selection_changed.connect(lambda *_: self._debounce.start())
        for w in (self.pane.grid, self.pane.list, self.viewer.canvas):
            QShortcut(QKeySequence(Qt.Key_Space), w, self.viewer.toggle, context=Qt.WidgetShortcut)
            QShortcut(QKeySequence(","), w, lambda: self.viewer.step(-1), context=Qt.WidgetShortcut)
            QShortcut(QKeySequence("."), w, lambda: self.viewer.step(1), context=Qt.WidgetShortcut)
            QShortcut(QKeySequence("Home"), w, lambda: self.viewer.seek(0), context=Qt.WidgetShortcut) \
                if w is self.viewer.canvas else None
        self._last = None

    def _load_selected(self):
        ents = self.pane.selected_entries()
        e = ents[0] if len(ents) == 1 else None
        if e is None:
            return
        key = (e.kind, e.path, len(e.files))
        if key == self._last:
            return
        self._last = key
        self.viewer.load(e)

    def shutdown(self):
        self.viewer.shutdown()


class LibrarySidebar(QWidget):
    """Lista de raíces de la librería (con sus subcarpetas)."""

    def __init__(self, app, section_label):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 4, 0)
        head.addWidget(section_label, 1)
        add = QToolButton()
        add.setIcon(app.icons.glyph("plus", 14))
        add.setAutoRaise(True)
        add.setToolTip("Agregar carpeta a la VFX Library")
        add.clicked.connect(self.add_root)
        head.addWidget(add)
        lay.addLayout(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(app.icons.folder(None, 16).size())
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemClicked.connect(lambda it, c: self.app.open_library(it.data(0, Qt.UserRole)))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree)
        self.reload()

    def roots(self):
        return [r for r in (self.app.cfg["library_roots"] or []) if r]

    def reload(self):
        self.tree.clear()
        roots = self.roots()
        if not roots:
            it = QTreeWidgetItem(["＋ Elegí la carpeta de tu librería…"])
            it.setForeground(0, Qt.gray)
            it.setData(0, Qt.UserRole, "")
            self.tree.addTopLevelItem(it)
            return
        for r in roots:
            it = self._item(r, os.path.basename(r.rstrip("\\/")) or r)
            it.setToolTip(0, r)
            self.tree.addTopLevelItem(it)

    def _item(self, path, label):
        it = QTreeWidgetItem([label])
        it.setData(0, Qt.UserRole, path)
        it.setIcon(0, self.app.icons.folder_icon(self.app.dir_color(path), 16))
        it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        return it

    def _expand(self, it):
        if it.data(0, Qt.UserRole + 1):
            return
        it.setData(0, Qt.UserRole + 1, True)
        path = it.data(0, Qt.UserRole)
        try:
            with os.scandir(path) as sc:
                dirs = sorted((d.name for d in sc if d.is_dir() and not d.name.startswith(".")), key=str.lower)
        except OSError:
            dirs = []
        if not dirs:
            it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
        for d in dirs:
            it.addChild(self._item(os.path.join(path, d), d))

    def add_root(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de la VFX Library",
                                             (self.roots() or [os.path.expanduser("~")])[0])
        if not d:
            return
        d = os.path.normpath(d)
        roots = self.roots()
        if d not in roots:
            roots.append(d)
        self.app.cfg["library_roots"] = roots
        self.app.cfg.save()
        self.reload()
        self.app.open_library(d)

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        m.addAction("Agregar carpeta a la librería…", self.add_root)
        if it and it.data(0, Qt.UserRole):
            p = it.data(0, Qt.UserRole)
            m.addAction("Abrir en VFX Library", lambda: self.app.open_library(p))
            m.addAction("Abrir en el Explorador (pestaña nueva)", lambda: self.app.open_in_explorer(p, new_tab=True))
            if it.parent() is None:
                def remove():
                    self.app.cfg["library_roots"] = [r for r in self.roots() if r != p]
                    self.app.cfg.save()
                    self.reload()
                m.addAction("Quitar de la librería (no borra archivos)", remove)
        m.exec(self.tree.viewport().mapToGlobal(pos))
