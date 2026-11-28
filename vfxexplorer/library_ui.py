# -*- coding: utf-8 -*-
"""VFX Library: página con viewer arriba y archivos abajo, y la sección del sidebar con las raíces de la librería."""

import os
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QToolButton, QLabel, QMenu, QFileDialog)

from .core import reachable
from .viewer import Viewer
from .pane import FilePane
from .tree import LibTree


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
        self._debounce = QTimer(self, singleShot=True, interval=30, timeout=self._load_selected)
        self.pane.selection_changed.connect(lambda *_: self._sel_changed())
        self._last_row = None
        self._dir = 1
        for w in (self.pane.grid, self.pane.list, self.viewer.canvas):
            QShortcut(QKeySequence(Qt.Key_Space), w, self.viewer.toggle, context=Qt.WidgetShortcut)
            QShortcut(QKeySequence(","), w, lambda: self.viewer.step(-1), context=Qt.WidgetShortcut)
            QShortcut(QKeySequence("."), w, lambda: self.viewer.step(1), context=Qt.WidgetShortcut)
            QShortcut(QKeySequence("Home"), w, lambda: self.viewer.seek(0), context=Qt.WidgetShortcut) \
                if w is self.viewer.canvas else None
        self._last = None

    def _sel_changed(self):
        """Lo que ya está en memoria se muestra al instante; si no, una espera mínima (30 ms) por si se pasa
        rápido por varias."""
        ents = self.pane.selected_entries()
        if len(ents) == 1 and self.viewer.cached_still(ents[0]):
            self._debounce.stop()
            self._load_selected()
        else:
            self._debounce.start()

    def _load_selected(self):
        ents = self.pane.selected_entries()
        e = ents[0] if len(ents) == 1 else None
        if e is None:
            return
        key = (e.kind, e.path, len(e.files))
        if key == self._last:
            return
        self._last = key
        start = 0
        if getattr(self.pane, "_f7_resume", False):        # volvió con F7: sigue desde donde estaba
            self.pane._f7_resume = False
            start = getattr(self.viewer, "_resume", {}).get(e.path, 0)
        self.viewer.load(e, start=start)
        if hasattr(self.app, "lib_slots"):
            self.app.lib_slots.refresh()
        QTimer.singleShot(0, lambda e=e: self._prefetch_around(e))

    def _prefetch_around(self, e):
        """Imágenes sueltas (fotos y HDRIs): las de al lado se leen de antemano (moverse con las flechas es instantáneo)."""
        if not self.viewer.is_still(e):
            return
        from .models import ROLE_ENTRY
        v = self.pane.view()
        m = v.model()
        ix = v.currentIndex()
        if not ix.isValid():
            return
        row = ix.row()
        if self._last_row is not None and row != self._last_row:
            self._dir = 1 if row > self._last_row else -1     # hacia dónde te movés
        self._last_row = row
        near = []
        dr = self._dir
        for d in (dr, -dr, 2 * dr, 3 * dr):                   # como el visor de fotos: +1, −1, +2, +3
            j = m.index(row + d, 0)
            x = j.data(ROLE_ENTRY) if j.isValid() else None
            if x is not None:
                near.append(x)
        self.viewer.prefetch(near)

    def shutdown(self):
        self.viewer.shutdown()


class LibrarySidebar(QWidget):
    """Árbol de las raíces de la librería (con sus subcarpetas), con líneas con líneas."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        from .asyncdir import AsyncLister
        self._lister = AsyncLister(self)
        self._lister.done.connect(self._listed)
        self.tree = LibTree(app, self._item, self._expand)
        self.tree.setIconSize(app.icons.folder(None, 18).size())
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemClicked.connect(lambda it, c: self.app.open_library(it.data(0, Qt.UserRole)))
        self._collapse_next = False
        self.tree.itemDoubleClicked.connect(self._double)
        app.hook_tree_keys(self.tree, self.app.open_library)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree)
        # abajo del árbol: auto colapsar · ordenar por nombre
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 2, 6, 4)
        bar.setSpacing(2)
        self.b_collapse = self._tbtn("collapse", "Auto collapse: close the folders outside the current path",
                                     "lib_tree_autocollapse", self._collapse_toggled)
        self.b_sort = self._tbtn("sortaz", "Sort library folders by name (off: in the order they were added)",
                                 "lib_tree_sort_name", lambda on: self.reload())
        bar.addWidget(self.b_collapse)
        bar.addWidget(self.b_sort)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.reload()

    def _tbtn(self, glyph, tip, key, fn):
        from PySide6.QtWidgets import QToolButton
        b = QToolButton()
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setChecked(bool(self.app.cfg[key]))
        b.setToolTip(tip)

        def paint(on):
            b.setIcon(self.app.icons.glyph(glyph, 16, "#4cc2ff" if on else "#8a8f96"))

        def toggled(on):
            self.app.cfg[key] = bool(on)
            self.app.cfg.save()
            paint(on)
            fn(on)
        paint(b.isChecked())
        b.toggled.connect(toggled)
        return b

    def _double(self, it, col):
        """Doble clic en una carpeta: entra y (con auto colapsar) cierra las que quedan fuera del camino."""
        p = it.data(0, Qt.UserRole)
        if not p:
            return
        self._collapse_next = True
        if self.app.libpane.current_dir() and os.path.normcase(os.path.normpath(
                self.app.libpane.current_dir())) == os.path.normcase(os.path.normpath(p)):
            self.sync(p)
        else:
            self.app.open_library(p)

    def _collapse_toggled(self, on):
        if on and self.tree._trace_path:
            self._collapse_next = True
            self.sync(self.tree._trace_path)

    def _auto_collapse(self, keep):
        """Cierra todo lo que no está en el camino hasta la carpeta actual."""
        chain = set()
        p = keep
        while p is not None:
            chain.add(id(p))
            p = p.parent()

        def close_all(it):                        # cerrada con todo lo de adentro (al reabrirla no aparece abierta)
            for i in range(it.childCount()):
                close_all(it.child(i))
            if it.isExpanded():
                it.setExpanded(False)

        def walk(it):
            for i in range(it.childCount()):
                c = it.child(i)
                if id(c) not in chain:
                    close_all(c)
                elif c is not keep:
                    walk(c)
        for i in range(self.tree.topLevelItemCount()):
            t = self.tree.topLevelItem(i)
            if id(t) not in chain:
                close_all(t)
            elif t is not keep:
                walk(t)

    def sync(self, path):
        """La carpeta de la pestaña activa queda marcada en el árbol (con su trazo)."""
        it = self.tree.item_for(path) if path else None
        if it is not None:
            p = it.parent()
            while p is not None:
                p.setExpanded(True)
                p = p.parent()
            if self.app.cfg["lib_tree_autocollapse"]:
                self._auto_collapse(it)                # en cada carpeta a la que se entra (árbol o panel)
            self._collapse_next = False
            self.tree._syncing = True
            self.tree.setCurrentItem(it)
            self.tree._syncing = False
            self.tree.scrollToItem(it)
        self.tree.set_trace_path(path if it is not None else "")

    def roots(self):
        return [r for r in (self.app.cfg["library_roots"] or []) if r]

    def reload(self):
        cur = self.tree._trace_path
        self.tree.clear()
        roots = self.roots()
        if not roots:
            it = QTreeWidgetItem(["＋ Choose your library folder…"])
            it.setForeground(0, Qt.gray)
            it.setData(0, Qt.UserRole, "")
            self.tree.addTopLevelItem(it)
            return
        if self.app.cfg["lib_tree_sort_name"]:
            roots = sorted(roots, key=lambda r: (os.path.basename(r.rstrip("\\/")) or r).lower())
        from .libicons import root_icon, folder_icon_for
        single = len(roots) == 1
        for r in roots:
            name = os.path.basename(r.rstrip("\\/")) or r
            is_drive = not os.path.basename(r.rstrip("\\/"))
            # un disco entero: «VFX Library» (como This PC) y sus carpetas llevan ícono según el nombre;
            # una carpeta elegida: su propio nombre (prolijo) con su ícono, y adentro carpetas comunes
            if is_drive:
                name = "VFX Library" if single else f"VFX Library ({r.rstrip(chr(92)).rstrip('/')})"
            if not reachable(r):                  # NAS apagado: se muestra, sin tocarlo, y se reintenta solo
                it = QTreeWidgetItem([name + "   (offline)"])
                it.setData(0, Qt.UserRole, r)
                it.setData(0, Qt.UserRole + 2, True)
                it.setForeground(0, Qt.gray)
                it.setIcon(0, self.app.icons.folder_icon(None, 18))
                it.setToolTip(0, r + "\nNot available right now — it shows up by itself when the network is back")
                it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
                self.tree.addTopLevelItem(it)
                continue
            it = self._item(r, name, pretty=not is_drive)
            it.setToolTip(0, r)
            if is_drive:
                it.setIcon(0, root_icon(18))
                it.setData(0, Qt.UserRole + 4, True)     # sus carpetas son las «principales»
            else:
                ic = folder_icon_for(os.path.basename(r.rstrip("\\/")), 18)
                if ic is not None:
                    it.setIcon(0, ic)
            self.tree.addTopLevelItem(it)
            it.setExpanded(len(roots) <= 3)      # las raíces arrancan abiertas
        if cur:
            self.sync(cur)

    def _item(self, path, label, pretty=True):
        if pretty and self.app.cfg["lib_pretty_names"]:
            from .core import pretty_name
            label = pretty_name(label)
        it = QTreeWidgetItem([label])
        it.setData(0, Qt.UserRole, path)
        it.setToolTip(0, path)
        it.setIcon(0, self.app.icons.folder_icon(self.app.dir_color(path) or self.app.LIB_FOLDER, 18))
        it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        return it

    def _expand(self, it):
        if it.data(0, Qt.UserRole + 1):
            return
        path = it.data(0, Qt.UserRole)
        if not reachable(path):
            return
        from .core import net_root
        if net_root(path):                        # red (NAS): se lee en otro hilo, sin trabar la ventana
            it.setData(0, Qt.UserRole + 1, True)
            if not it.childCount():
                ph = QTreeWidgetItem(["loading…"])
                ph.setForeground(0, Qt.gray)
                ph.setData(0, Qt.UserRole, "")
                it.addChild(ph)
            self._lister.request(path)
            return
        it.setData(0, Qt.UserRole + 1, True)
        try:
            with os.scandir(path) as sc:
                dirs = sorted((d.name for d in sc if d.is_dir() and not d.name.startswith(".")), key=str.lower)
        except OSError:
            dirs = []
        self._fill(it, path, dirs)

    def _fill(self, it, path, dirs):
        for i in reversed(range(it.childCount())):
            if not it.child(i).data(0, Qt.UserRole):          # «loading…»
                it.takeChild(i)
        if not dirs:
            it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
        main = bool(it.data(0, Qt.UserRole + 4))
        from .libicons import folder_icon_for
        for d in dirs:
            c = self._item(os.path.join(path, d), d)
            if main:                                  # carpetas principales: ícono según el nombre
                ic = folder_icon_for(d, 18)
                if ic is not None:
                    c.setIcon(0, ic)
            it.addChild(c)

    def _listed(self, path, dirs):
        it = self.tree.item_for(path, expand=False) if hasattr(self.tree, "item_for") else None
        if it is None or os.path.normcase(os.path.normpath(it.data(0, Qt.UserRole) or "")) != \
                os.path.normcase(os.path.normpath(path)):
            return
        self._fill(it, path, [d for d in dirs if not d.startswith(".")])
        cur = self.tree._trace_path
        if cur and os.path.normcase(cur).startswith(os.path.normcase(os.path.normpath(path))):
            self.sync(cur)                        # el camino actual pasaba por acá: completar el trazo

    def add_root(self):
        d = QFileDialog.getExistingDirectory(self, "VFX Library folder",
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
        m.addAction("Add folder to the library…", self.add_root)
        if it and it.data(0, Qt.UserRole):
            p = it.data(0, Qt.UserRole)
            m.addAction("Open in VFX Library", lambda: self.app.open_library(p))
            m.addAction("Open in new tab", lambda: (self.app.set_mode("library"),
                                                           self.app.libpane.add_tab(p)))
            m.addAction("Pin to Quick access", lambda: self.app.add_favorites([p], lib=True))
            m.addAction("Open in File Explorer (new tab)", lambda: self.app.open_in_explorer(p, new_tab=True))
            if it.parent() is None:
                def remove():
                    self.app.cfg["library_roots"] = [r for r in self.roots() if r != p]
                    self.app.cfg.save()
                    self.reload()
                m.addAction("Remove from library (files are kept)", remove)
        m.exec(self.tree.viewport().mapToGlobal(pos))
