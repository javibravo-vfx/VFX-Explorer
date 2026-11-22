# -*- coding: utf-8 -*-
"""Panel de archivos: pestañas, breadcrumb, búsqueda, grilla/lista y drag & drop."""

import os

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent, QItemSelectionModel
from PySide6.QtGui import QKeySequence, QShortcut, QCursor
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QTabBar, QToolButton, QLineEdit, QComboBox,
                               QCheckBox, QListView, QTreeView, QStackedWidget, QAbstractItemView, QHeaderView,
                               QLabel, QMenu, QWidget)

from .core import IS_WIN, FILTERS, parse_query, norm_key, same_path
from .models import (EntryModel, EntryProxy, ScanWorker, SearchWorker, ResolveWorker, ROLE_ENTRY, COLS,
                     C_FOLDER, C_TAGS, C_RATING)
from .widgets import GridDelegate, BreadcrumbBar


class _ViewMixin:
    def _setup(self, pane):
        self.pane = pane
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        self.dragEnterEvent(ev)

    def dropEvent(self, ev):
        paths = [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
        ix = self.indexAt(ev.position().toPoint())
        target = None
        if ix.isValid():
            e = ix.data(ROLE_ENTRY)
            if e is not None and e.kind == "dir":
                target = e.path
        if target is None:
            target = self.pane.current_dir()
        mods = ev.modifiers()
        ev.setDropAction(Qt.CopyAction)
        ev.accept()
        if target and paths:
            pos = QCursor.pos()
            QTimer.singleShot(0, lambda: self.pane.app.handle_drop(self.pane, paths, target, mods, pos))

    def startDrag(self, actions):
        super().startDrag(Qt.CopyAction)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            ix = self.indexAt(ev.position().toPoint())
            e = ix.data(ROLE_ENTRY) if ix.isValid() else None
            if e is not None and e.kind == "dir":
                self.pane.add_tab(e.path, activate=False)
            return
        super().mouseReleaseEvent(ev)

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self.pane.focused.emit(self.pane)

    def mousePressEvent(self, ev):
        self.pane.focused.emit(self.pane)
        if ev.button() in (Qt.BackButton, Qt.XButton1):
            self.pane.go_back()
            return
        if ev.button() in (Qt.ForwardButton, Qt.XButton2):
            self.pane.go_forward()
            return
        super().mousePressEvent(ev)


class GridView(_ViewMixin, QListView):
    pass


class ListView(_ViewMixin, QTreeView):
    pass


class FilePane(QFrame):
    focused = Signal(object)
    selection_changed = Signal(object)
    location_changed = Signal(object)
    status_changed = Signal(object)

    def __init__(self, app, name):
        super().__init__()
        self.app = app
        self.name = name
        self.setObjectName("pane")
        self.model = EntryModel(app)
        self.proxy = EntryProxy(app)
        self.proxy.setSourceModel(self.model)
        app.thumbs.ready.connect(self.model.thumb_ready)
        self.gen = 0
        self.workers = set()
        self.search_worker = None
        self.pending_select = None
        self.tabs = []
        self.ti = -1
        self.view_mode = "grid"
        self.status_text = ""
        self.search_timer = QTimer(self, singleShot=True, interval=450, timeout=self._apply_search)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        ic = self.app.icons
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("paneHeader")
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(4, 3, 4, 4)
        hl.setSpacing(3)

        trow = QHBoxLayout()
        trow.setSpacing(3)
        self.tabbar = QTabBar()
        self.tabbar.setTabsClosable(False)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setElideMode(Qt.ElideMiddle)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setMinimumWidth(80)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabMoved.connect(self._tab_moved)
        self.tabbar.installEventFilter(self)
        self.tabbar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabbar.customContextMenuRequested.connect(self._tab_menu)
        trow.addWidget(self.tabbar, 1)

        def tb(glyph, tip, slot, row):
            b = QToolButton()
            b.setIcon(ic.glyph(glyph, 18))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            row.addWidget(b)
            return b
        tb("plus", "Pestaña nueva (Ctrl+T)", lambda: self.add_tab(self.current_dir() or self.tab_path()), trow)
        hl.addLayout(trow)

        nrow = QHBoxLayout()
        nrow.setSpacing(3)
        self.b_back = tb("back", "Atrás (Alt+←)", self.go_back, nrow)
        self.b_fwd = tb("fwd", "Adelante (Alt+→)", self.go_forward, nrow)
        tb("up", "Subir (Backspace)", self.go_up, nrow)
        tb("reload", "Refrescar (F5)", self.refresh, nrow)
        self.crumb = BreadcrumbBar(self.app.fs)
        self.crumb.setMinimumWidth(120)
        self.crumb.navigate.connect(self.navigate)
        nrow.addWidget(self.crumb, 3)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar…  #tag  ★3")
        self.search.setToolTip("Nombre o parte · *comodines* · #tag · ★3 (rating mínimo) · Ctrl+F · Esc limpia")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(110)
        self.search.setMaximumWidth(230)
        self.search.textChanged.connect(self._on_search_text)
        self.search.returnPressed.connect(self._apply_search)
        nrow.addWidget(self.search, 1)
        self.filter = QComboBox()
        for label, key in FILTERS:
            self.filter.addItem(label, key)
        self.filter.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.filter.setMinimumContentsLength(5)
        self.filter.setToolTip("Filtrar por tipo")
        self.filter.currentIndexChanged.connect(self._apply_search)
        nrow.addWidget(self.filter)
        self.rec = QToolButton()
        self.rec.setText("Sub")
        self.rec.setCheckable(True)
        self.rec.setAutoRaise(True)
        self.rec.setToolTip("Buscar también en todas las subcarpetas")
        self.rec.toggled.connect(self._apply_search)
        nrow.addWidget(self.rec)
        self.b_grid = tb("grid", "Grilla (Ctrl+1)", lambda: self.set_view("grid"), nrow)
        self.b_list = tb("list", "Lista (Ctrl+2)", lambda: self.set_view("list"), nrow)
        for b in (self.b_grid, self.b_list):
            b.setCheckable(True)
        hl.addLayout(nrow)
        lay.addWidget(self.header)

        # vistas
        self.grid = GridView()
        self.grid._setup(self)
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(2)
        self.grid.setWrapping(True)
        self.grid.setMouseTracking(True)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.grid.verticalScrollBar().setSingleStep(24)
        self.grid.setModel(self.proxy)
        self.grid.setItemDelegate(GridDelegate(self.app, self.grid))
        ts = int(self.app.cfg["thumb_size"])
        self.grid.setIconSize(QSize(ts, ts))

        self.list = ListView()
        self.list._setup(self)
        self.list.setModel(self.proxy)
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setSortingEnabled(True)
        self.list.setAlternatingRowColors(True)
        self.list.setIconSize(QSize(18, 18))
        hd = self.list.header()
        hd.setStretchLastSection(True)
        hd.setSectionResizeMode(QHeaderView.Interactive)
        hd.resizeSection(0, 320)
        for c, w in zip(range(1, len(COLS)), (120, 90, 55, 50, 75, 115, 60, 130, 200)):
            hd.resizeSection(c, w)
        self.list.sortByColumn(0, Qt.AscendingOrder)
        self.list.setColumnHidden(C_FOLDER, True)
        hd.sortIndicatorChanged.connect(lambda c, o: self.proxy.sort(c, o))

        for v in (self.grid, self.list):
            v.activated.connect(self._activate)
            if not IS_WIN:
                v.doubleClicked.connect(self._activate)
            v.customContextMenuRequested.connect(lambda pos, v=v: self.app.item_menu(self, v, pos))
            v.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed.emit(self))
            self._view_shortcuts(v)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.list)
        lay.addWidget(self.stack, 1)

        self.footer = QLabel()
        self.footer.setObjectName("paneFooter")
        lay.addWidget(self.footer)

        self._pane_shortcuts()
        self.set_view("grid", emit=False)
        for w in (self.search, self.filter, self.rec, self.crumb.edit):
            w.installEventFilter(self)

    def _view_shortcuts(self, v):
        a = self.app

        def sc(keys, fn):
            QShortcut(QKeySequence(keys), v, fn, context=Qt.WidgetShortcut)
        sc(Qt.Key_Backspace, self.go_up)
        sc(QKeySequence.Delete, lambda: a.op_trash(self))
        sc("F2", lambda: a.op_rename(self))
        sc("Ctrl+C", lambda: a.op_clip(self, cut=False))
        sc("Ctrl+X", lambda: a.op_clip(self, cut=True))
        sc("Ctrl+V", lambda: a.op_paste(self))
        sc("Ctrl+Shift+C", lambda: a.copy_paths(self, "hash"))
        sc("Ctrl+Alt+C", lambda: a.copy_paths(self, "nuke"))
        sc("Ctrl+Shift+N", lambda: a.op_new_folder(self))
        sc("Ctrl+E", lambda: a.op_tags(self))
        for n in range(6):
            sc(f"Ctrl+{n}", lambda n=n: a.op_rating(self, n))

    def _pane_shortcuts(self):
        def sc(keys, fn):
            QShortcut(QKeySequence(keys), self, fn, context=Qt.WidgetWithChildrenShortcut)
        sc("Alt+Left", self.go_back)
        sc("Alt+Right", self.go_forward)
        sc("Alt+Up", self.go_up)
        sc("F5", self.refresh)
        sc("Ctrl+T", lambda: self.add_tab(self.current_dir() or self.tab_path()))
        sc("Ctrl+W", lambda: self.close_tab(self.ti))
        sc("Ctrl+Tab", lambda: self.tabbar.setCurrentIndex((self.ti + 1) % max(1, len(self.tabs))))
        sc("Ctrl+Shift+Tab", lambda: self.tabbar.setCurrentIndex((self.ti - 1) % max(1, len(self.tabs))))
        sc("Ctrl+L", self.crumb.start_edit)
        sc("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll()))
        sc("Ctrl+1", lambda: self.set_view("grid"))
        sc("Ctrl+2", lambda: self.set_view("list"))

    def eventFilter(self, obj, ev):
        if obj is self.tabbar and ev.type() == QEvent.MouseButtonRelease and ev.button() == Qt.MiddleButton:
            i = self.tabbar.tabAt(ev.position().toPoint())
            if i >= 0:
                self.close_tab(i)
                return True
        if ev.type() == QEvent.FocusIn:
            self.focused.emit(self)
        if obj is getattr(self, "search", None) and ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self.search.clear()
            self.view().setFocus()
            return True
        return super().eventFilter(obj, ev)

    def set_active(self, active):
        self.setProperty("active", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)

    def view(self):
        return self.grid if self.stack.currentIndex() == 0 else self.list

    def set_view(self, mode, emit=True):
        self.view_mode = mode
        self.stack.setCurrentIndex(0 if mode == "grid" else 1)
        self.b_grid.setChecked(mode == "grid")
        self.b_list.setChecked(mode != "grid")
        if emit:
            self.app.save_soon()

    def set_thumb_size(self, v):
        self.grid.setIconSize(QSize(v, v))

    # ------------------------------------------------------------------ pestañas
    def tab(self):
        return self.tabs[self.ti] if 0 <= self.ti < len(self.tabs) else None

    def tab_path(self):
        t = self.tab()
        return t["path"] if t else ""

    def add_tab(self, path, activate=True):
        path = path or os.path.expanduser("~")
        t = {"path": os.path.normpath(path), "history": [os.path.normpath(path)], "hpos": 0, "virtual": None}
        self.tabs.append(t)
        self.tabbar.blockSignals(True)
        i = self.tabbar.addTab(self._tab_title(t))
        self.tabbar.setTabToolTip(i, t["path"])
        close = QToolButton()
        close.setText("×")
        close.setAutoRaise(True)
        close.setFixedSize(16, 16)
        close.setToolTip("Cerrar pestaña (Ctrl+W · click del medio)")
        close.setStyleSheet("QToolButton{border:none;color:#7d8590;font-size:12pt;padding:0 0 2px 0;}"
                            "QToolButton:hover{color:#fff;background:#4a4d55;border-radius:3px;}")
        close.clicked.connect(lambda c=False, b=close: self._close_by_button(b))
        self.tabbar.setTabButton(i, QTabBar.RightSide, close)
        self.tabbar.blockSignals(False)
        if activate or len(self.tabs) == 1:
            self.tabbar.setCurrentIndex(i)
            if self.ti != i:
                self._tab_changed(i)
        self.app.save_soon()

    def close_tab(self, i):
        if len(self.tabs) <= 1 or not (0 <= i < len(self.tabs)):
            return
        self.tabs.pop(i)
        self.tabbar.blockSignals(True)
        self.tabbar.removeTab(i)
        self.tabbar.blockSignals(False)
        self.ti = -1
        self._tab_changed(self.tabbar.currentIndex())
        self.app.save_soon()

    def _close_by_button(self, b):
        for i in range(self.tabbar.count()):
            if self.tabbar.tabButton(i, QTabBar.RightSide) is b:
                self.close_tab(i)
                return

    def _tab_moved(self, frm, to):
        self.tabs.insert(to, self.tabs.pop(frm))
        self.ti = self.tabbar.currentIndex()
        self.app.save_soon()

    def _tab_changed(self, i):
        if i < 0 or i >= len(self.tabs) or i == self.ti:
            return
        self.ti = i
        t = self.tab()
        if t["virtual"]:
            self._load_virtual()
        else:
            self._show_location()
            self._load()

    def _tab_title(self, t):
        if t.get("virtual"):
            return t["virtual"]["title"]
        p = t["path"].rstrip("\\/")
        return os.path.basename(p) or t["path"]

    def _update_tab(self):
        t = self.tab()
        if t:
            self.tabbar.setTabText(self.ti, self._tab_title(t))
            self.tabbar.setTabToolTip(self.ti, t["virtual"]["title"] if t["virtual"] else t["path"])

    def _tab_menu(self, pos):
        i = self.tabbar.tabAt(pos)
        if i < 0:
            return
        m = QMenu(self)
        m.addAction("Duplicar pestaña", lambda: self.add_tab(self.tabs[i]["path"]))
        m.addAction("Cerrar", lambda: self.close_tab(i)).setEnabled(len(self.tabs) > 1)

        def close_others():
            keep = self.tabs[i]
            for j in reversed(range(len(self.tabs))):
                if self.tabs[j] is not keep:
                    self.close_tab(j)
        m.addAction("Cerrar las otras", close_others).setEnabled(len(self.tabs) > 1)
        m.exec(self.tabbar.mapToGlobal(pos))

    def state(self):
        return {"tabs": [{"path": t["path"]} for t in self.tabs], "current": self.ti, "view": self.view_mode}

    def restore(self, st, fallback):
        tabs = [t.get("path") for t in (st or {}).get("tabs", []) if t.get("path")]
        tabs = [p for p in tabs if os.path.isdir(p)] or [fallback]
        for p in tabs:
            self.add_tab(p, activate=False)
        self.set_view((st or {}).get("view", "grid"), emit=False)
        cur = min(max(0, int((st or {}).get("current", 0))), len(self.tabs) - 1)
        if self.tabbar.currentIndex() == cur and self.ti != cur:
            self._tab_changed(cur)
        self.tabbar.setCurrentIndex(cur)
        if self.ti < 0:
            self._tab_changed(cur)

    # ------------------------------------------------------------------ navegación
    def current_dir(self):
        t = self.tab()
        return None if (t is None or t["virtual"]) else t["path"]

    def navigate(self, path, add_history=True, select=None, new_tab=False):
        path = (path or "").strip().strip('"').strip("'")
        if not path:
            return
        path = os.path.expandvars(os.path.expanduser(path))
        if os.path.isfile(path):
            select = os.path.basename(path)
            path = os.path.dirname(path)
        if not os.path.isdir(path):
            self._set_status(f"No existe la carpeta: {path}")
            self.crumb.set_path(self.tab_path())
            return
        path = os.path.normpath(os.path.abspath(path))
        if IS_WIN and len(path) == 2 and path[1] == ":":
            path += "\\"
        if new_tab:
            self.add_tab(path)
            return
        t = self.tab()
        if t is None:
            self.add_tab(path)
            return
        was_virtual = t["virtual"] is not None
        t["virtual"] = None
        if add_history and (was_virtual or not same_path(t["history"][t["hpos"]], path)):
            t["history"] = t["history"][: t["hpos"] + 1]
            t["history"].append(path)
            t["hpos"] = len(t["history"]) - 1
        t["path"] = path
        self.pending_select = select
        self._show_location()
        self._load()
        self.app.save_soon()

    def _show_location(self):
        t = self.tab()
        if not t:
            return
        self.crumb.set_path(t["path"], t["virtual"]["title"] if t["virtual"] else "")
        self.b_back.setEnabled(t["hpos"] > 0 or bool(t["virtual"]))
        self.b_fwd.setEnabled(t["hpos"] < len(t["history"]) - 1)
        self._update_tab()
        self.location_changed.emit(self)

    def go_back(self):
        t = self.tab()
        if not t:
            return
        if t["virtual"]:
            self.navigate(t["path"], add_history=False)
            return
        if t["hpos"] > 0:
            t["hpos"] -= 1
            self.navigate(t["history"][t["hpos"]], add_history=False)

    def go_forward(self):
        t = self.tab()
        if t and t["hpos"] < len(t["history"]) - 1:
            t["hpos"] += 1
            self.navigate(t["history"][t["hpos"]], add_history=False)

    def go_up(self):
        t = self.tab()
        if not t:
            return
        if t["virtual"]:
            self.navigate(t["path"], add_history=False)
            return
        cur = t["path"]
        parent = os.path.dirname(cur.rstrip("\\/"))
        if parent and not same_path(parent, cur):
            if IS_WIN and len(parent) == 2 and parent[1] == ":":
                parent += "\\"
            self.navigate(parent, select=os.path.basename(cur.rstrip("\\/")))

    def refresh(self):
        self.app.thumbs.failed.clear()
        self.app.thumbs.index.clear()
        t = self.tab()
        if t and t["virtual"]:
            self._load_virtual()
        else:
            self._load()

    # ------------------------------------------------------------------ carga
    def _recursive_active(self):
        return self.rec.isChecked() and (self.search.text().strip() or self.filter.currentData() != "all")

    def _load(self):
        self.app.thumbs.cancel_pending()
        if self._recursive_active():
            self._start_search()
            return
        self._stop_search()
        self.gen += 1
        self._set_status("Leyendo…")
        w = ScanWorker(self.gen, self.tab_path(), bool(self.app.cfg["show_hidden"]))
        w.done.connect(self._scan_done)
        self._track(w)
        w.start()

    def _track(self, w):
        self.workers.add(w)
        w.finished.connect(lambda w=w: self.workers.discard(w))

    def _scan_done(self, gen, path, entries, err):
        if gen != self.gen:
            return
        self.model.set_entries(entries, path, virtual=False)
        self.list.setColumnHidden(C_FOLDER, True)
        self.proxy.set_filter(parse_query(self.search.text()), self.filter.currentData())
        self._sort()
        self._update_status(f"Error: {err}" if err else None)
        self._select_pending()

    def _sort(self):
        hd = self.list.header()
        self.proxy.sort(hd.sortIndicatorSection(), hd.sortIndicatorOrder())

    def _select_pending(self):
        names = self.pending_select
        self.pending_select = None
        if not names:
            return
        if isinstance(names, str):
            names = [names]
        v = self.view()
        first = None
        sel = v.selectionModel()
        sel.clearSelection()
        for r, e in enumerate(self.model.entries):
            if e.name in names or any(n in e.files for n in names):
                pix = self.proxy.mapFromSource(self.model.index(r, 0))
                if pix.isValid():
                    sel.select(pix, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                    first = first or pix
        if first is not None:
            sel.setCurrentIndex(first, QItemSelectionModel.NoUpdate)
            v.scrollTo(first)

    # ------------------------------------------------------------------ búsqueda
    def _on_search_text(self, _):
        if self.rec.isChecked() or (self.tab() and self.tab()["virtual"]):
            self.search_timer.start()
        else:
            self._apply_search()

    def _apply_search(self):
        self.search_timer.stop()
        t = self.tab()
        if t and t["virtual"]:
            self.proxy.set_filter(parse_query(self.search.text()), self.filter.currentData())
            self._update_status()
            return
        if self._recursive_active():
            self._start_search()
        elif self.model.virtual:
            self._load()
        else:
            self.proxy.set_filter(parse_query(self.search.text()), self.filter.currentData())
            self._update_status()

    def _stop_search(self):
        if self.search_worker:
            self.search_worker.cancelled = True
            self.search_worker = None

    def _start_search(self):
        self._stop_search()
        self.app.thumbs.cancel_pending()
        self.gen += 1
        self.model.set_entries([], self.tab_path(), virtual=True)
        self.list.setColumnHidden(C_FOLDER, False)
        self.proxy.set_filter(parse_query(""), "all")
        w = SearchWorker(self.gen, self.tab_path(), parse_query(self.search.text()), self.filter.currentData(),
                         bool(self.app.cfg["show_hidden"]), self.app.lib.snapshot())
        w.batch.connect(self._search_batch)
        w.progress.connect(self._search_progress)
        w.finished_search.connect(self._search_done)
        self._track(w)
        self.search_worker = w
        self._set_status("Buscando…")
        w.start()

    def _search_batch(self, gen, entries):
        if gen == self.gen:
            self.model.append_entries(entries)

    def _search_progress(self, gen, scanned, d):
        if gen == self.gen:
            self._set_status(f"Buscando… {len(self.model.entries)} resultados · {scanned} carpetas")

    def _search_done(self, gen, found, capped):
        if gen != self.gen:
            return
        self.search_worker = None
        self._sort()
        extra = f" (límite de {SearchWorker.MAX_RESULTS})" if capped else ""
        self._update_status(f"Subcarpetas: {found} resultados{extra}")

    # ------------------------------------------------------------------ vistas virtuales (tags, colecciones)
    def show_virtual(self, title, kind, name, new_tab=False):
        if new_tab:
            self.add_tab(self.current_dir() or self.tab_path())
        t = self.tab()
        t["virtual"] = {"title": title, "kind": kind, "name": name}
        self._show_location()
        self._load_virtual()

    def _load_virtual(self):
        self._stop_search()
        self.app.thumbs.cancel_pending()
        t = self.tab()
        v = t["virtual"]
        refs = self.app.refs_for(v["kind"], v["name"])
        self.gen += 1
        self.model.set_entries([], "", virtual=True)
        self.list.setColumnHidden(C_FOLDER, False)
        self._show_location()
        self._set_status("Buscando en la librería…")
        w = ResolveWorker(self.gen, refs)
        w.done.connect(self._virtual_done)
        self._track(w)
        w.start()

    def _virtual_done(self, gen, entries, n_missing):
        if gen != self.gen:
            return
        self.model.set_entries(entries, "", virtual=True)
        self.proxy.set_filter(parse_query(self.search.text()), self.filter.currentData())
        self._sort()
        extra = f" · {n_missing} no encontrados (movidos o borrados)" if n_missing else ""
        self._update_status(f"{self.tab()['virtual']['title']}{extra}")

    def is_virtual(self):
        t = self.tab()
        return bool(t and t["virtual"])

    def virtual_info(self):
        t = self.tab()
        return t["virtual"] if t else None

    # ------------------------------------------------------------------ selección / abrir
    def selected_entries(self):
        v = self.view()
        rows = v.selectionModel().selectedRows(0) if v is self.list else v.selectionModel().selectedIndexes()
        out, seen = [], set()
        for ix in rows:
            e = ix.data(ROLE_ENTRY)
            if e is not None and id(e) not in seen:
                seen.add(id(e))
                out.append(e)
        return out

    def _activate(self, ix):
        e = ix.data(ROLE_ENTRY)
        if e is None:
            return
        if e.kind == "dir":
            self.navigate(e.path)
        else:
            self.app.open_entry(e)

    # ------------------------------------------------------------------ estado
    def _set_status(self, text):
        self.status_text = text
        self.footer.setText(text)
        self.status_changed.emit(self)

    def _update_status(self, prefix=None):
        counts = {}
        for r in range(self.proxy.rowCount()):
            e = self.proxy.mapToSource(self.proxy.index(r, 0)).data(ROLE_ENTRY)
            counts[e.cat] = counts.get(e.cat, 0) + 1
        parts = []
        for k, lbl in (("dir", "carpetas"), ("seq", "secuencias"), ("video", "videos"), ("image", "imágenes"),
                       ("model", "escenas/modelos"), ("other", "otros")):
            if counts.get(k):
                parts.append(f"{counts[k]} {lbl}")
        txt = " · ".join(parts) or "vacío"
        self._set_status(f"{prefix} — {txt}" if prefix else txt)
