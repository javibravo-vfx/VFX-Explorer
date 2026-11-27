# -*- coding: utf-8 -*-
"""Árbol de carpetas con líneas:
- líneas finas (sólidas o punteadas) que unen cada carpeta con su padre,
- cajitas ⊞/⊟ para expandir,
- "Tree Path Tracing": una línea de color más gruesa que va desde la raíz hasta la carpeta actual,
- opcional: las líneas de los hijos con el color de la carpeta padre."""

import os

from PySide6.QtCore import Qt, QSize, QRect, QPersistentModelIndex, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QCursor
from PySide6.QtWidgets import QTreeView, QTreeWidget, QTreeWidgetItem, QStyledItemDelegate, QStyleOptionViewItem

LINE_GRAY = QColor("#5f6368")
BOX_FILL = QColor("#2a2a2a")
BOX_EDGE = QColor("#7a7e85")
SIGN = QColor("#c8c8c8")


class FolderTreeDelegate(QStyledItemDelegate):
    """Ícono de carpeta con su color (manual o automático) y filas con altura cómoda."""

    def __init__(self, app, view):
        super().__init__(view)
        self.app = app

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if not index.parent().isValid():
            hidden = self.app.cfg["hidden_drives"] or []
            if hidden:
                from .core import norm_key
                if norm_key(self.app.fs.filePath(index)) in {norm_key(x) for x in hidden}:
                    option.palette.setColor(option.palette.ColorRole.Text, QColor("#6a6a6a"))
        if index.parent().isValid():
            c = self.app.dir_color(self.app.fs.filePath(index))
            option.icon = self.app.icons.folder_icon(c, 18)
            option.features |= QStyleOptionViewItem.HasDecoration
            option.decorationSize = QSize(16, 16)

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 24))


class _LinedMixin:
    """Dibujo de líneas con líneas + path tracing + destino de drag & drop (copiar/mover a la carpeta)."""

    def _lined_init(self, app):
        self.app = app
        self.setObjectName("sideTree")
        self.setIndentation(18)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setStyleSheet("QTreeView::branch { background: transparent; border-image: none; image: none; }")
        self._trace = []          # [QPersistentModelIndex] raíz → carpeta actual
        self._trace_path = ""
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self._drop_ix = None
        self._expand_timer = QTimer(self, singleShot=True, interval=750, timeout=self._drag_expand)

    # a implementar
    def path_of(self, index):
        raise NotImplementedError

    def index_of(self, path):
        raise NotImplementedError

    # ---------------- path tracing
    def set_trace_path(self, path):
        """Marca el camino raíz → carpeta actual ."""
        chain = []
        ix = self.index_of(path) if path else None
        while ix is not None and ix.isValid():
            chain.insert(0, QPersistentModelIndex(ix))
            ix = ix.parent()
        self._trace = chain
        self._trace_path = path or ""
        self.viewport().update()
        return chain[-1] if chain else None

    # ---------------- drop: soltar archivos sobre una carpeta del árbol
    def _drop_target(self, ev):
        ix = self.indexAt(ev.position().toPoint())
        p = self.path_of(ix) if ix.isValid() else ""
        return ix, (p if p and os.path.isdir(p) else "")

    def mouseDoubleClickEvent(self, ev):
        """Doble click en el espacio vacío del árbol: subir un nivel en el panel correspondiente."""
        if ev.button() == Qt.LeftButton and not self.indexAt(ev.position().toPoint()).isValid():
            pane = self.app.libpane if isinstance(self, QTreeWidget) else self.app.explorer_active
            if isinstance(self, QTreeWidget) or self.app.mode() == "explorer":
                pane.go_up()
            return
        super().mouseDoubleClickEvent(ev)

    def startDrag(self, actions):
        # solo "copiar" para Qt: así nunca saca filas del árbol; mover o copiar lo decide el destino
        super().startDrag(Qt.CopyAction)
        self.app.drag_finished()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        ix, p = self._drop_target(ev)
        if not p:
            self._set_drop(None)
            ev.ignore()
            return
        if self._drop_ix is None or QPersistentModelIndex(ix) != self._drop_ix:
            self._set_drop(ix)
            self._expand_timer.start()
        ev.setDropAction(Qt.CopyAction)
        ev.accept()

    def dragLeaveEvent(self, ev):
        self._set_drop(None)

    def _set_drop(self, ix):
        self._drop_ix = QPersistentModelIndex(ix) if ix is not None else None
        if ix is None:
            self._expand_timer.stop()
        self.viewport().update()

    def _drag_expand(self):
        if self._drop_ix is not None and self._drop_ix.isValid():
            self.expand(self.model().index(self._drop_ix.row(), 0, self._drop_ix.parent()))

    def dropEvent(self, ev):
        ix, target = self._drop_target(ev)
        self._set_drop(None)
        paths = [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
        mods = ev.modifiers()
        ev.setDropAction(Qt.CopyAction)
        ev.accept()
        if target and paths:
            pos = QCursor.pos()
            QTimer.singleShot(0, lambda: self.app.handle_drop(None, paths, target, mods, pos))

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._drop_ix is not None and self._drop_ix.isValid():
            r = self.visualRect(self.model().index(self._drop_ix.row(), 0, self._drop_ix.parent()))
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.Antialiasing)
            c = QColor(self.app.accent())
            p.setPen(QPen(c, 1.5))
            c.setAlpha(45)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(1, 1, -2, -1), 4, 4)
            p.end()

    def _box_edge(self):
        return BOX_EDGE

    def _cfg(self, k, default=None):
        v = self.app.cfg[k]
        return default if v is None else v

    def _trace_color(self):
        if self._cfg("tree_trace_color", "accent") == "folder" and self._trace_path:
            c = self.app.dir_color(self._trace_path)
            if c:
                return QColor(c)
        return QColor(self.app.accent())

    # ---------------- dibujo
    def _line_color(self, parent_index):
        if not self._cfg("tree_line_colors", True) or not parent_index.isValid():
            return LINE_GRAY
        c = self.app.dir_color(self.path_of(parent_index))
        if not c:
            return LINE_GRAY
        q = QColor(c)
        q.setAlpha(210)
        return q

    def drawBranches(self, p, rect, index):
        model = self.model()
        ind = self.indentation()
        chain = []
        a = index.parent()
        while a.isValid():
            chain.insert(0, a)
            a = a.parent()
        depth = len(chain)
        x0 = rect.right() - ind * (depth + 1) + 1
        cy = rect.center().y()
        top, bot = rect.top(), rect.bottom() + 1
        style = self._cfg("tree_lines_style", "chevron")
        plain = getattr(self, "plain", False)      # modo Windows: solo › / ⌄, sin líneas ni camino
        if plain:
            style = "chevron"
        dotted = style == "dotted"
        chev = style == "chevron"          # chevrons › y solo la línea del camino
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)

        def col_x(level):
            return x0 + level * ind + ind // 2

        def pen(col, w=1):
            return QPen(col, w, Qt.DotLine if (dotted and w == 1) else Qt.SolidLine, Qt.FlatCap)

        def has_next(ix):
            return ix.row() < model.rowCount(ix.parent()) - 1

        has_kids = model.hasChildren(index)
        stub = col_x(depth) - (5 if has_kids else -4)   # hasta la cajita, o hasta el ícono si no hay cajita
        if chev:
            stub = col_x(depth) - (6 if has_kids else -6)

        # 1) líneas normales
        for lvl, anc in enumerate([] if chev else chain[1:], start=1):
            if has_next(anc):
                x = col_x(lvl - 1)
                p.setPen(pen(self._line_color(anc.parent())))
                p.drawLine(x, top, x, bot)
        if depth > 0 and not chev:
            x = col_x(depth - 1)
            p.setPen(pen(self._line_color(index.parent())))
            p.drawLine(x, top, x, bot if has_next(index) else cy)
            p.drawLine(x, cy, stub, cy)

        # 2) tree path tracing (por encima de las líneas)
        tr = self._trace
        tracing = bool(self._cfg("tree_trace", True)) and len(tr) > 1 and not plain
        if tracing:
            tw = 1 if chev else max(1, int(self._cfg("tree_trace_width", 2)))
            p.setPen(QPen(self._trace_color(), tw, Qt.SolidLine, Qt.FlatCap))
            path = [QPersistentModelIndex(c) for c in chain] + [QPersistentModelIndex(index)]
            for k in range(len(tr) - 1):
                if k >= len(path) or path[k] != tr[k]:
                    break                       # la fila no está dentro del subárbol de trace[k]
                x = col_x(k)
                if len(path) == k + 1:          # la fila ES trace[k]: la serpiente baja desde su cajita
                    if self.isExpanded(index):
                        p.drawLine(x, cy + (7 if chev else 5), x, bot)
                    break
                mine, nxt = path[k + 1], tr[k + 1]
                if mine == nxt:
                    if len(path) == k + 2:      # la fila ES trace[k+1]: codo hacia su cajita
                        p.drawLine(x, top, x, cy)
                        p.drawLine(x, cy, stub, cy)
                    continue
                if mine.row() < nxt.row():      # hermano anterior: la línea pasa de largo
                    p.drawLine(x, top, x, bot)
                break

        # 3) chevron › / ⌄ (con líneas)
        if has_kids and chev:
            x = col_x(depth)
            on_path = tracing and QPersistentModelIndex(index) in tr
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(self._trace_color() if on_path else QColor("#c5c5c5"), 1.3, Qt.SolidLine, Qt.RoundCap,
                          Qt.RoundJoin))
            if self.isExpanded(index):
                p.drawPolyline([QPointF(x - 4, cy - 2), QPointF(x, cy + 2), QPointF(x + 4, cy - 2)])
            else:
                p.drawPolyline([QPointF(x - 2, cy - 4), QPointF(x + 2, cy), QPointF(x - 2, cy + 4)])
        # 3) cajita ⊞/⊟
        elif has_kids:
            x = col_x(depth)
            box = QRect(x - 4, cy - 4, 9, 9)
            pix = QPersistentModelIndex(index)
            on_path = tracing and pix in tr
            p.setPen(QPen(self._trace_color() if on_path else self._box_edge(), 1))
            p.setBrush(BOX_FILL)
            p.drawRect(box.adjusted(0, 0, -1, -1))
            p.setPen(QPen(SIGN, 1))
            p.drawLine(box.left() + 2, cy, box.right() - 2, cy)
            if not self.isExpanded(index):
                p.drawLine(x, box.top() + 2, x, box.bottom() - 2)
        p.restore()


class LinedTree(_LinedMixin, QTreeView):
    """Árbol de carpetas del explorador (QFileSystemModel)."""

    def __init__(self, app):
        super().__init__()
        self._lined_init(app)
        self.setItemDelegate(FolderTreeDelegate(app, self))

    def path_of(self, index):
        return self.model().filePath(index)

    def index_of(self, path):
        return self.model().index(path)


class _LibDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 24))


class LibTree(_LinedMixin, QTreeWidget):
    """Árbol de la VFX Library: mismas líneas que el de carpetas pero con su propio color (violeta)."""

    def __init__(self, app, make_item, expand_item):
        super().__init__()
        self._lined_init(app)
        self._make_item, self._expand_item = make_item, expand_item
        self.setItemDelegate(_LibDelegate(self))
        self.setHeaderHidden(True)
        self.setDragEnabled(True)

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, items):
        from PySide6.QtCore import QMimeData, QUrl
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(it.data(0, Qt.UserRole)) for it in items if it.data(0, Qt.UserRole)])
        return md

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def path_of(self, index):
        return index.data(Qt.UserRole) or "" if index.isValid() else ""

    def index_of(self, path):
        it = self.item_for(path, expand=False)
        return self.indexFromItem(it) if it is not None else None

    def item_for(self, path, expand=True):
        """Busca (y si hace falta carga) el ítem de una carpeta dentro de las raíces de la librería."""
        if not path:
            return None
        key = os.path.normcase(os.path.normpath(path))
        best = None
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            r = it.data(0, Qt.UserRole)
            if not r:
                continue
            rk = os.path.normcase(os.path.normpath(r))
            if key == rk or key.startswith(rk.rstrip("\\/") + os.sep):
                if best is None or len(rk) > len(os.path.normcase(best.data(0, Qt.UserRole))):
                    best = it
        if best is None:
            return None
        rel = os.path.relpath(os.path.normpath(path), os.path.normpath(best.data(0, Qt.UserRole)))
        it = best
        if rel in (".", ""):
            return it
        for part in rel.split(os.sep):
            if not expand and not it.data(0, Qt.UserRole + 1):
                return it
            self._expand_item(it)
            nxt = None
            for j in range(it.childCount()):
                c = it.child(j)
                if os.path.normcase(os.path.basename(c.data(0, Qt.UserRole))) == os.path.normcase(part):
                    nxt = c
                    break
            if nxt is None:
                return it
            it = nxt
        return it

    def _line_color(self, parent_index):
        c = QColor(self._cfg("lib_tree_line_color", "#8d6fd1"))
        c.setAlpha(200)
        return c

    def _box_edge(self):
        return QColor(self._cfg("lib_tree_line_color", "#8d6fd1"))

    def _trace_color(self):
        return QColor(self._cfg("lib_tree_line_color", "#4cc2ff"))



THISPC_KEY = "::thispc"


class FolderTree(_LinedMixin, QTreeWidget):
    """Árbol de File Explorer con «This PC» como raíz (la línea del camino sale de ahí, como en Windows).
    Completo: los discos y, al abrir una carpeta, sus subcarpetas (las de red solo si el servidor responde).
    Mini (mini=True): solo las carpetas que visitaste, armado con las rutas guardadas, sin leer el disco."""

    MAX = 400

    def __init__(self, app, mini=False):
        super().__init__()
        self._lined_init(app)
        self.mini = mini
        self.setItemDelegate(_LibDelegate(self))
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setIconSize(QSize(18, 18))
        self.setExpandsOnDoubleClick(False)
        self._items = {}            # norm_key -> item
        self.drives = []            # Entries de list_drives (cuando llegan)
        self.root = None
        self.itemExpanded.connect(self._on_expand)
        self._make_root()
        if mini:
            self.rebuild()

    def mouseDoubleClickEvent(self, ev):
        """Doble click en una carpeta: la despliega; otro doble click la vuelve a plegar."""
        if ev.button() == Qt.LeftButton:
            it = self.itemAt(ev.position().toPoint())
            if it is not None and (it.childCount() or it.childIndicatorPolicy() == QTreeWidgetItem.ShowIndicator):
                it.setExpanded(not it.isExpanded())
                ev.accept()
                return
        super().mouseDoubleClickEvent(ev)

    # ---------------- util
    @staticmethod
    def _key(p):
        if p == THISPC_KEY:
            return p
        return os.path.normcase(os.path.normpath(p))

    def _make_root(self):
        self.clear()
        self._items = {}
        self.root = QTreeWidgetItem(["This PC"])
        self.root.setData(0, Qt.UserRole, THISPC_KEY)
        self.root.setIcon(0, self.app.icons.glyph("pc", 18, "#4cc2ff"))
        self.root.setToolTip(0, "Drives and network locations")
        self.root.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        self.addTopLevelItem(self.root)
        self._items[THISPC_KEY] = self.root
        self.root.setExpanded(True)

    def _drive_label(self, root_path):
        k = self._key(root_path)
        for d in self.drives:
            if self._key(d.path) == k:
                return d.name
        return root_path.rstrip("\\") or root_path

    def _drive_kind(self, root_path):
        k = self._key(root_path)
        for d in self.drives:
            if self._key(d.path) == k:
                return getattr(d, "drive_kind", "local")
        return "network" if root_path.startswith(("\\\\", "//")) else "local"

    def _drive_root(self, path):
        """Raíz (disco / share / punto de montaje) que contiene la ruta."""
        p = os.path.normpath(path)
        best = None
        for d in self.drives:
            r = os.path.normpath(d.path)
            rk, pk = self._key(r), self._key(p)
            if pk == rk or pk.startswith(rk.rstrip("\\/") + os.sep):
                if best is None or len(r) > len(best):
                    best = r
        if best:
            return best
        drive, _ = os.path.splitdrive(p)
        if drive:
            return drive + (os.sep if not drive.startswith(("\\\\", "//")) else "")
        return os.sep

    def _new_item(self, parent, path, label, drive=False):
        it = QTreeWidgetItem([label])
        it.setData(0, Qt.UserRole, path)
        it.setToolTip(0, path)
        if drive:
            it.setIcon(0, self.app.icons.drive_icon(self._drive_kind(path), 18))
        else:
            it.setIcon(0, self.app.icons.folder_icon(self.app.dir_color(path), 18))
        it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless if self.mini
                                   else QTreeWidgetItem.ShowIndicator)
        self._insert_sorted(parent, it, drive)
        self._items[self._key(path)] = it
        return it

    def _insert_sorted(self, parent, it, drive=False):
        name = (it.data(0, Qt.UserRole) if drive else it.text(0)).lower()
        n = parent.childCount()
        pos = n
        for i in range(n):
            c = parent.child(i)
            cn = (c.data(0, Qt.UserRole) if drive else c.text(0)).lower()
            if cn > name:
                pos = i
                break
        parent.insertChild(pos, it)

    # ---------------- discos
    def set_drives(self, drives):
        self.drives = list(drives or [])
        if self.mini:
            for i in range(self.root.childCount()):        # el mini tree solo cambia los nombres
                c = self.root.child(i)
                c.setText(0, self._drive_label(c.data(0, Qt.UserRole)))
                c.setIcon(0, self.app.icons.drive_icon(self._drive_kind(c.data(0, Qt.UserRole)), 18))
        else:
            have = {self._key(self.root.child(i).data(0, Qt.UserRole)): self.root.child(i)
                    for i in range(self.root.childCount())}
            want = {self._key(d.path): d for d in self.drives}
            for k, it in have.items():
                if k not in want:
                    self.root.removeChild(it)
                    self._forget(it)
            for k, d in want.items():
                if k not in have:
                    self._new_item(self.root, d.path, d.name, drive=True)
                else:
                    have[k].setText(0, d.name)
        self.apply_hidden()
        if self._trace_path:
            self.sync(self._trace_path)

    def apply_hidden(self):
        hidden = {self._key(p) for p in (self.app.cfg["hidden_drives"] or [])}
        show = bool(self.app.cfg["show_hidden_drives"])
        for i in range(self.root.childCount()):
            c = self.root.child(i)
            hid = self._key(c.data(0, Qt.UserRole)) in hidden
            c.setHidden(hid and not show and not self.mini)
            c.setForeground(0, QColor("#6a6a6a") if hid else QColor("#e6e6e6"))

    def _forget(self, it):
        self._items.pop(self._key(it.data(0, Qt.UserRole)), None)
        for i in range(it.childCount()):
            self._forget(it.child(i))

    # ---------------- carga perezosa (árbol completo)
    def _on_expand(self, it):
        if self.mini or it is self.root:
            return
        self._load(it)

    def _list_dirs(self, path):
        from .core import reachable
        if not reachable(path):
            return None
        show_hidden = bool(self.app.cfg["show_hidden"])
        out = []
        try:
            with os.scandir(path) as sc:
                for d in sc:
                    try:
                        if not d.is_dir():
                            continue
                        if not show_hidden:
                            if d.name.startswith((".", "$")):
                                continue
                            attrs = getattr(d.stat(follow_symlinks=False), "st_file_attributes", 0)
                            if attrs & 0x6:            # oculto o de sistema (Windows)
                                continue
                    except OSError:
                        continue
                    out.append(d.name)
        except OSError:
            return []
        return sorted(out, key=str.lower)

    def _has_subdirs(self, path):
        try:
            with os.scandir(path) as sc:
                for d in sc:
                    try:
                        if d.is_dir() and not d.name.startswith((".", "$")):
                            return True
                    except OSError:
                        continue
        except OSError:
            pass
        return False

    def _load(self, it, force=False):
        if it.data(0, Qt.UserRole + 1) and not force:
            return
        path = it.data(0, Qt.UserRole)
        from .core import net_root, reachable
        if net_root(path):                          # red: en otro hilo (un NAS despertando no traba nada)
            if not reachable(path):
                return
            if not hasattr(self, "_lister"):
                from .asyncdir import AsyncLister
                self._lister = AsyncLister(self)
                self._lister.done.connect(self._net_listed)
            self._lister.request(path, bool(self.app.cfg["show_hidden"]))
            return
        names = self._list_dirs(path)
        self._apply_names(it, path, names)

    def _net_listed(self, path, names):
        it = self._items.get(self._key(path))
        if it is None:
            return
        self._apply_names(it, path, names)
        # la carpeta a la que había que llegar (en red se lee de a un nivel, en otro hilo): seguir bajando
        target = self._trace_path or getattr(self, "_pending_sync", "")
        if target and self._key(target).startswith(self._key(path)):
            self.sync(target)
            if self._key(self._trace_path or "") == self._key(target):
                cb = getattr(self.app, "tree_synced", None)
                if cb:
                    cb(self)

    def _apply_names(self, it, path, names):
        if names is None:                          # servidor caído: se reintenta al volver a abrir
            it.setData(0, Qt.UserRole + 1, False)
            return
        it.setData(0, Qt.UserRole + 1, True)
        it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)
        old = {it.child(i).text(0).lower(): it.child(i) for i in range(it.childCount())}
        new = {n.lower(): n for n in names}
        for k, c in old.items():
            if k not in new:
                it.removeChild(c)
                self._forget(c)
        from .core import net_root
        peek = net_root(path) is None and len(names) <= 300     # local: solo con flechita si tiene carpetas
        for k, n in new.items():
            if k in old:
                continue
            full = os.path.join(path, n)
            c = self._new_item(it, full, n)
            if peek and not self._has_subdirs(full):
                c.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)

    def refresh_dir(self, path):
        """Después de crear / borrar / mover: la carpeta ya abierta en el árbol vuelve a leer sus hijos."""
        if self.mini or not path:
            return
        it = self._items.get(self._key(path))
        if it is not None and it.data(0, Qt.UserRole + 1):
            self._load(it, force=True)

    # ---------------- buscar el ítem de una ruta
    def item_for(self, path, load=True):
        if not path:
            return None
        if path == THISPC_KEY:
            return self.root
        it = self._items.get(self._key(path))
        if it is not None or self.mini:
            return it
        if not load:
            return None
        from .core import reachable
        root = self._drive_root(path)
        cur = self._items.get(self._key(root))
        if cur is None:
            return None
        rel = os.path.relpath(os.path.normpath(path), root)
        if rel in (".", ""):
            return cur
        if not reachable(path):
            return cur
        for part in rel.split(os.sep):
            self._load(cur)
            nxt = self._items.get(self._key(os.path.join(cur.data(0, Qt.UserRole), part)))
            if nxt is None:
                return cur
            cur = nxt
        return cur

    def sync(self, path):
        """Marca la ubicación actual (con el camino celeste desde This PC); si no está, no queda nada marcado."""
        it = self.item_for(path) if path else None
        exact = it is not None and (path == THISPC_KEY or self._key(it.data(0, Qt.UserRole)) == self._key(path))
        if exact:
            p = it.parent()
            while p is not None:
                p.setExpanded(True)
                p = p.parent()
            self._syncing = True
            self.setCurrentItem(it)
            self._syncing = False
            self.scrollToItem(it)
            self.set_trace_path(path)
            self._pending_sync = ""
        else:
            # todavía no está (una carpeta de red que se está leyendo): se recuerda y se marca al llegar
            self._pending_sync = path or ""
            self._syncing = True
            self.clearSelection()
            self.setCurrentItem(None)
            self._syncing = False
            self.set_trace_path("")

    def refresh_colors(self):
        for k, it in self._items.items():
            if k != THISPC_KEY and it.parent() is not self.root:
                it.setIcon(0, self.app.icons.folder_icon(self.app.dir_color(it.data(0, Qt.UserRole)), 18))
        self.viewport().update()

    # ---------------- mini tree
    def paths(self):
        return list(self.app.cfg["mini_tree"] or [])

    def add(self, path):
        if not self.mini or not path or path.startswith("::"):
            return
        p = os.path.normpath(path)
        lst = [x for x in self.paths() if self._key(x) != self._key(p)]
        lst.insert(0, p)
        self._set_paths(lst[: self.MAX])
        if self._key(p) not in self._items:
            self._ensure(p)

    def _set_paths(self, lst):
        self.app.cfg["mini_tree"] = lst

    def _ensure(self, path):
        root = self._drive_root(path)
        parent = self._items.get(self._key(root))
        if parent is None:
            parent = self._new_item(self.root, root, self._drive_label(root), drive=True)
        self.root.setExpanded(True)
        rel = os.path.relpath(os.path.normpath(path), root)
        cur_path = root
        if rel not in (".", ""):
            for part in rel.split(os.sep):
                cur_path = os.path.join(cur_path, part)
                it = self._items.get(self._key(cur_path))
                if it is None:
                    it = self._new_item(parent, cur_path, part)
                parent.setExpanded(True)
                parent = it
        return parent

    def remove(self, path):
        k = self._key(path)
        self._set_paths([x for x in self.paths()
                         if self._key(x) != k and not self._key(x).startswith(k.rstrip("\\/") + os.sep)])
        self.app.cfg.save()
        self.rebuild()

    def clear_all(self):
        self._set_paths([])
        self.app.cfg.save()
        self.rebuild()

    def rebuild(self):
        cur = self._trace_path
        self._make_root()
        for p in reversed(self.paths()):
            self._ensure(p)
        self.expandAll()
        if cur:
            self.sync(cur)

    # ---------------- _LinedMixin / drag
    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, items):
        from PySide6.QtCore import QMimeData, QUrl
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(it.data(0, Qt.UserRole)) for it in items
                    if it.data(0, Qt.UserRole) and it.data(0, Qt.UserRole) != THISPC_KEY])
        return md

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def path_of(self, index):
        p = index.data(Qt.UserRole) if index.isValid() else ""
        return "" if (not p or p == THISPC_KEY) else p

    def index_of(self, path):
        it = self.item_for(path, load=False) if path else None
        return self.indexFromItem(it) if it is not None else None


def MiniTree(app):
    return FolderTree(app, mini=True)


class _WinQuickMixin:
    """Modo Windows del panel izquierdo: arriba Quick access (y los Workspace Pins), una línea y después el árbol,
    todo en un solo árbol que scrollea entero. Lo usan el árbol tipo Windows y el Bonsai."""

    ROLE_SEP = Qt.UserRole + 9
    ROLE_QUICK = Qt.UserRole + 10
    ROLE_ISFILE = Qt.UserRole + 6
    ROLE_PIN = Qt.UserRole + 11          # "pin" / "wspin": el clavito a la derecha
    ROLE_SYS = Qt.UserRole + 12          # escritorio, descargas… (de Windows)
    ROLE_REAL = Qt.UserRole + 13         # el nombre real de la carpeta (si se renombró aquí)
    ROLE_PH = Qt.UserRole + 14           # «Drop Workspace Pins here» (el lugar, sin pins todavía)
    ROLE_HIDDEN = Qt.UserRole + 15       # carpeta de Windows oculta (con el ojito prendido se ve atenuada)

    def __init__(self, app, **kw):
        self._quick_specs = []
        self._win_path = ""
        self._quick_hold = ""                     # se eligió un acceso de arriba: la marca queda ahí (no baja al árbol)
        super().__init__(app, **kw)
        self.currentItemChanged.connect(self._quick_current)
        self.itemClicked.connect(lambda it, c: self._quick_current(it, None))

    def _quick_current(self, it, _prev):
        if getattr(self, "_syncing", False) or it is None:
            return
        self._quick_hold = it.data(0, Qt.UserRole) if (it.data(0, self.ROLE_QUICK) and
                                                       not it.data(0, self.ROLE_ISFILE)) else ""

    def _held_item(self, path):
        """El acceso de arriba elegido, si la carpeta abierta es la suya."""
        if not self._quick_hold or not path or self._key(path) != self._key(self._quick_hold):
            return None
        for i in range(self.topLevelItemCount()):
            q = self.topLevelItem(i)
            if q.data(0, self.ROLE_QUICK) and self._key(q.data(0, Qt.UserRole) or "") == self._key(path):
                return q
        return None

    def scrollTo(self, index, hint=QTreeWidget.EnsureVisible):
        if getattr(self, "_hold_scroll", False):  # se está en un acceso de arriba: el árbol no se lleva la vista
            return
        super().scrollTo(index, hint)

    def scrollToItem(self, it, hint=QTreeWidget.EnsureVisible):
        if getattr(self, "_hold_scroll", False):  # (QTreeWidget.scrollToItem no pasa por scrollTo)
            return
        super().scrollToItem(it, hint)

    def _release_scroll(self, v):
        self.verticalScrollBar().setValue(v)
        self._hold_scroll = False

    def _keep_on_quick(self, path):
        """Después de marcar la carpeta: si se llegó desde un acceso de arriba, el foco vuelve a ese acceso."""
        q = self._held_item(path)
        if q is None:
            if path and self._quick_hold and self._key(path) != self._key(self._quick_hold):
                self._quick_hold = ""
            return
        self._syncing = True
        self.setCurrentItem(q)
        self._syncing = False
        self.scrollToItem(q)

    def _make_root(self):
        super()._make_root()
        self._fill_quick_items()

    # ---------------- Quick access arriba
    def set_quick(self, specs):
        """specs: lista de dicts {text, icon, path, isfile, pin} o None = línea divisoria."""
        self._quick_specs = list(specs)
        self._fill_quick_items()
        if hasattr(self, "_resync"):
            self._resync()

    def _fill_quick_items(self):
        if self.root is None:
            return
        while self.topLevelItemCount() and self.topLevelItem(0) is not self.root:
            self.takeTopLevelItem(0)
        items = []
        for sp in self._quick_specs + [None]:          # al final, la línea antes de This PC
            if sp is None:
                if not items or items[-1].data(0, self.ROLE_SEP):
                    continue
                it = QTreeWidgetItem([""])
                it.setData(0, self.ROLE_SEP, True)
                it.setFlags(Qt.NoItemFlags)
                it.setSizeHint(0, QSize(10, 11))
            elif sp.get("placeholder"):
                it = QTreeWidgetItem([sp["text"]])
                it.setData(0, self.ROLE_PH, True)
                it.setData(0, self.ROLE_PIN, "wspin")
                it.setFlags(Qt.ItemIsEnabled)
                it.setForeground(0, QColor("#6b7178"))
                it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
            else:
                it = QTreeWidgetItem([sp["text"]])
                it.setIcon(0, sp["icon"])
                it.setData(0, self.ROLE_SYS, sp.get("sys") or "")
                it.setData(0, self.ROLE_REAL, sp.get("real") or "")
                it.setData(0, Qt.UserRole, sp["path"])
                it.setData(0, self.ROLE_QUICK, True)
                it.setData(0, self.ROLE_ISFILE, bool(sp.get("isfile")))
                it.setData(0, self.ROLE_PIN, sp.get("pin") or "")
                it.setToolTip(0, sp["path"])
                it.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
                if sp.get("hidden"):                    # oculto (se ve atenuado con el ojito prendido)
                    it.setForeground(0, QColor("#6b7178"))
                    it.setData(0, self.ROLE_HIDDEN, True)
            items.append(it)
        for i, it in enumerate(items):
            self.insertTopLevelItem(i, it)

    def drawRow(self, p, opt, index):
        if index.data(self.ROLE_SEP):
            y = opt.rect.center().y()
            p.save()
            p.setPen(QPen(QColor("#3a3a3a"), 1))
            p.drawLine(opt.rect.left() + 12, y, opt.rect.right() - 12, y)
            p.restore()
            return
        if index.data(self.ROLE_HIDDEN):
            p.save()
            p.setOpacity(0.45)
            super().drawRow(p, opt, index)
            p.restore()
        else:
            super().drawRow(p, opt, index)
        pin = index.data(self.ROLE_PIN)
        if pin and not index.data(self.ROLE_PH):
            g = self.app.icons.glyph("wspin" if pin == "wspin" else "pin", 14,
                                     "#4cc2ff" if pin == "wspin" else "#9d9d9d")
            r = opt.rect
            p.drawPixmap(self.viewport().width() - 24, r.center().y() - 7, g.pixmap(14, 14))

    # ---------------- soltar carpetas / pestañas arriba: Quick access (entre los que ya están)
    _qdrop = None                 # (zona "quick" | "wspin", y de la rayita, índice en Quick access)

    def _quick_rows(self):
        out = []
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it is self.root:
                break
            out.append(it)
        return out

    def _quick_zone_at(self, pos):
        it = self.itemAt(pos)
        rows = self._quick_rows()
        if it is not None:
            return it in rows
        if rows:                                   # entre filas / arriba de todo
            return pos.y() <= self.visualItemRect(rows[-1]).bottom()
        return False

    def _quick_target(self, pos):
        rows = self._quick_rows()
        y = pos.y()
        ws = [r for r in rows if r.data(0, self.ROLE_PIN) == "wspin"]
        if ws and y >= self.visualItemRect(ws[0]).top() - 2:
            r0 = self.visualItemRect(ws[0])
            return "wspin", None, 0, r0.top(), self.visualItemRect(ws[-1]).bottom()
        pins = [r for r in rows if r.data(0, self.ROLE_PIN) == "pin"]
        idx = sum(1 for r in pins if self.visualItemRect(r).center().y() < y)
        if pins:
            ly = self.visualItemRect(pins[idx - 1]).bottom() if idx else self.visualItemRect(pins[0]).top()
        else:
            q = [r for r in rows if r.data(0, self.ROLE_QUICK)]
            ly = self.visualItemRect(q[-1]).bottom() if q else 2
        top = self.visualItemRect(rows[0]).top()
        bottom = self.visualItemRect(ws[0]).top() - 1 if ws else self.visualItemRect(rows[-1]).bottom()
        return "quick", ly, idx, top, bottom

    def _drop_paths(self, ev, files):
        from .quicklist import dropped_paths
        return dropped_paths(ev.mimeData(), files)

    def dragEnterEvent(self, ev):
        from .quicklist import TAB_MIME
        if ev.mimeData().hasUrls() or ev.mimeData().hasFormat(TAB_MIME):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        pos = ev.position().toPoint()
        over = self.itemAt(pos)
        if over is not None and over.data(0, self.ROLE_SYS):
            # Desktop, Documents, Downloads…: ahí no se meten accesos de otro lado
            if self._qdrop is not None:
                self._qdrop = None
                self.viewport().update()
            self._set_drop(None)
            ev.ignore()
            return
        if self._quick_zone_at(pos):
            zone, ly, idx, top, bottom = self._quick_target(pos)
            if self._drop_paths(ev, zone == "wspin"):
                self._set_drop(None)
                self._qdrop = (zone, ly, idx, top, bottom)
                self.viewport().update()
                ev.setDropAction(Qt.LinkAction)
                ev.accept()
                return
        if self._qdrop is not None:
            self._qdrop = None
            self.viewport().update()
        if not ev.mimeData().hasUrls():            # una pestaña sobre el árbol: nada que copiar
            ev.ignore()
            return
        super().dragMoveEvent(ev)

    def dragLeaveEvent(self, ev):
        self._qdrop = None
        super().dragLeaveEvent(ev)

    def dropEvent(self, ev):
        q, self._qdrop = self._qdrop, None
        self.viewport().update()
        if q is not None:
            zone, _ly, idx, _t, _b = q
            paths = self._drop_paths(ev, zone == "wspin")
            ev.setDropAction(Qt.LinkAction)
            ev.accept()
            if paths:
                if zone == "wspin":
                    QTimer.singleShot(0, lambda: self.app.add_wpins(paths))
                else:
                    QTimer.singleShot(0, lambda: self.app.insert_favorites(paths, idx))
            return
        if not ev.mimeData().hasUrls():
            ev.ignore()
            return
        super().dropEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._qdrop is None:
            return
        zone, ly, idx, top, bottom = self._qdrop
        p = QPainter(self.viewport())
        c = QColor(self.app.accent())
        c.setAlpha(34)
        p.fillRect(QRect(0, top, self.viewport().width(), bottom - top + 1), c)   # la zona, celeste
        if ly is not None:
            p.setPen(QPen(QColor(self.app.accent()), 2))
            p.drawLine(8, ly, self.viewport().width() - 8, ly)                   # dónde va a quedar
        p.end()


class WinNavTree(_WinQuickMixin, FolderTree):
    """Como en Windows: This PC cerrado, no se abre solo al entrar en carpetas; queda marcada la carpeta actual
    si se ve, o el último nivel abierto de su camino. Sin líneas: solo › / ⌄."""
    plain = True

    def __init__(self, app):
        super().__init__(app)
        self.itemExpanded.connect(lambda it: QTimer.singleShot(0, self._resync))
        self.itemCollapsed.connect(lambda it: QTimer.singleShot(0, self._resync))

    def _make_root(self):
        super()._make_root()
        self.root.setExpanded(False)              # This PC cerrado, como en Windows

    # ---------------- dónde estamos (sin abrir nada)
    def _shown(self, it):
        p = it.parent()
        while p is not None:
            if not p.isExpanded() or p.isHidden():
                return False
            p = p.parent()
        return not it.isHidden()

    def _resync(self):
        self.sync(self._win_path)

    def sync(self, path):
        self._win_path = path or ""
        target = None
        if path == THISPC_KEY:
            target = self.root
        elif path:
            p = os.path.normpath(path)
            while True:
                it = self._items.get(self._key(p))
                if it is not None and self._shown(it):
                    target = it
                    break
                up = os.path.dirname(p)
                if up == p or not up:
                    break
                p = up
            exact = target is not None and self._key(target.data(0, Qt.UserRole)) == self._key(path)
            if not exact:                          # la carpeta es un acceso de Quick access: ese
                k = self._key(path)
                for i in range(self.topLevelItemCount()):
                    q = self.topLevelItem(i)
                    if q.data(0, self.ROLE_QUICK) and not q.data(0, self.ROLE_ISFILE) and \
                            self._key(q.data(0, Qt.UserRole) or "") == k:
                        target = q
                        break
            if target is None:
                target = self.root
        held = self._held_item(path) is not None
        self._hold_scroll = held                  # desde un acceso de arriba: la vista no baja al árbol
        self._syncing = True
        if target is None:
            self.clearSelection()
            self.setCurrentItem(None)
        else:
            self.setCurrentItem(target)
        self._syncing = False
        self._hold_scroll = False
        self._trace = []
        self._trace_path = ""
        self._keep_on_quick(path)
        self.viewport().update()

    def _apply_names(self, it, path, names):
        super()._apply_names(it, path, names)
        QTimer.singleShot(0, self._resync)        # (en red llega después: la marca baja si corresponde)



class WinBonsaiTree(_WinQuickMixin, FolderTree):
    """Modo Windows con el Bonsai: el mismo panel único (Quick access arriba), y abajo solo las carpetas visitadas,
    con sus líneas y el camino marcado."""

    def __init__(self, app):
        super().__init__(app, mini=True)

    # cada pestaña de File Explorer tiene su Bonsai (una no toca a la otra)
    _cur_tab = None                               # la pestaña que se está mostrando (la fija la ventana)

    def _tab(self):
        if self._cur_tab is not None:
            return self._cur_tab
        pane = getattr(self.app, "explorer_active", None)
        return pane.tab() if pane is not None else None

    def paths(self):
        t = self._tab()
        if t is not None and "bonsai" in t:
            return list(t["bonsai"] or [])
        return list(self.app.cfg["mini_tree"] or [])      # (pestañas de antes: el Bonsai que había)

    def _set_paths(self, lst):
        t = self._tab()
        if t is not None:
            t["bonsai"] = list(lst)
        else:
            self.app.cfg["mini_tree"] = list(lst)

    def sync(self, path):
        held = self._held_item(path) is not None
        if held:                                  # desde un acceso de arriba: la vista queda donde está
            v = self.verticalScrollBar().value()
            self._hold_scroll = True
        super().sync(path)                        # el camino queda marcado abajo, sin llevarse el foco
        self._keep_on_quick(path)
        if held:
            q = self._held_item(path)
            self._hold_scroll = False
            if q is not None:
                self.scrollToItem(q)              # solo lo justo para que el acceso se vea
            v2 = self.verticalScrollBar().value()
            self._hold_scroll = True              # (lo que Qt quiera desplazar después de abrir las ramas, no)
            QTimer.singleShot(120, lambda v2=v2: self._release_scroll(v2))
