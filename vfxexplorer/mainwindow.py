# -*- coding: utf-8 -*-
"""Ventana principal: barra de pipeline, sidebar (favoritos, colecciones, tags, carpetas), paneles e info."""

import os
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QByteArray, QDir, QUrl, QEvent, Signal, QRectF, QPointF
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices, QCursor, QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView,
                               QListWidget, QListWidgetItem, QComboBox, QSlider, QToolBar, QLabel, QMenu,
                               QFileSystemModel, QAbstractItemView, QToolButton, QScrollArea, QFrame,
                               QMessageBox, QInputDialog, QProgressDialog, QStyledItemDelegate, QSizePolicy, QStyleOptionViewItem,
                               QTabBar, QStackedWidget, QTabWidget)

from . import APP_NAME, VERSION
from .core import (Config, IS_WIN, data_dir, norm_key, fwd, human_size, fmt_time, compress_ranges, find_tool,
                   same_path, Entry, FILTERS)
from .library import Library, dir_target
from .pipeline import Pipeline
from .imaging import ThumbManager, InfoTask, Signals, init_formats
from .widgets import Icons, TAG_COLORS, TagDialog, RenameDialog, SettingsDialog, ACCENT
from .pane import FilePane
from .colors import ColorEngine, COLOR_MODES, DEFAULT_NAME_RULES
from .tree import LinedTree
from .dirsize import DirSizeManager
from .library_ui import LibraryPage, LibrarySidebar
from .pipebar import PipelineBar
from .quicklist import QuickList
from .tagbar import QuickTagBar
from . import fileops


# ----------------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------------

class ChevronButton(QToolButton):
    """Botón con ícono, texto y flechita hacia abajo, como New / Sort / View del Explorador de Windows 11."""

    def __init__(self, icon, text, menu, tip=""):
        super().__init__()
        self.setIcon(icon)
        self.setIconSize(QSize(18, 18))
        self.setText(text)
        self.setToolTip(tip or text)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setMenu(menu)
        self.setAutoRaise(True)
        self.setFixedHeight(32)
        self._full_text = text
        self.set_active(False)

    def set_active(self, on):
        """Resaltado (para el filtro activo)."""
        bg = "background:#0f3a55; border:1px solid #2f7fb0;" if on else "border:none;"
        self.setStyleSheet("QToolButton{" + bg + " border-radius:4px; padding:4px 22px 4px 8px; font-size:10pt;}"
                           "QToolButton:hover{background:" + ("#164a6b" if on else "#2d2d2d") + ";}"
                           "QToolButton:pressed{background:#333;}"
                           "QToolButton::menu-indicator{image:none; width:0px;}")

    def set_compact(self, compact):
        """Si no entra, queda solo el ícono (con su flechita)."""
        self.setToolButtonStyle(Qt.ToolButtonIconOnly if compact or not self.text() else Qt.ToolButtonTextBesideIcon)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        from PySide6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#c5c5c5"), 1.3))
        x, y = self.width() - 14, self.height() // 2
        p.drawLine(x - 3, y - 1, x, y + 2)
        p.drawLine(x, y + 2, x + 3, y - 1)
        p.end()


class SubfolderSwitch(QWidget):
    """Interruptor de subcarpetas como el de Found: apagado · 1 nivel · toda la rama."""
    changed = Signal(int)
    LABELS = ("Subfolders: off", "Subfolders: 1 level", "Subfolders: all")

    def __init__(self):
        super().__init__()
        self.v = 0
        self.setFixedSize(132, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Subfolders (Ctrl+B)\nOff · 1 = this folder and its subfolders · 2 = the whole branch\n"
                        "Click a position, or click to step through them.")

    def set_value(self, v, emit=True):
        v = max(0, min(2, int(v)))
        if v != self.v:
            self.v = v
            self.update()
            if emit:
                self.changed.emit(v)

    def _track(self):
        return QRectF(self.width() - 58, 4, 54, 16)

    def mousePressEvent(self, ev):
        t = self._track()
        x = ev.position().x()
        if x >= t.left() - 4:
            self.set_value(int(round((x - t.left() - 8) / max(1.0, (t.width() - 16) / 2))))
        else:
            self.set_value((self.v + 1) % 3)

    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter, QColor, QPen, QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.v > 0
        en = self.isEnabled()
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QColor(ACCENT if on and en else "#9d9d9d"))
        txt = ("Subfolders " + ("1" if self.v == 1 else "all")) if on else "Subfolders"
        p.drawText(QRectF(0, 0, self.width() - 62, self.height()), Qt.AlignRight | Qt.AlignVCenter, txt)
        t = self._track()
        p.setPen(QPen(QColor(ACCENT if on else "#5f5f5f"), 1))
        p.setBrush(QColor("#0f3a55" if on else "#202020"))
        p.drawRoundedRect(t, 8, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3a3a3a"))
        for i in range(3):                       # marcas de las 3 posiciones
            p.drawEllipse(QPointF(t.left() + 8 + i * (t.width() - 16) / 2, t.center().y()), 1.5, 1.5)
        kx = t.left() + 8 + self.v * (t.width() - 16) / 2
        p.setBrush(QColor(ACCENT if on else "#c5c5c5") if en else QColor("#555"))
        p.drawEllipse(QPointF(kx, t.center().y()), 6, 6)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        init_formats()
        self.data_dir = data_dir()
        self.cfg = Config(os.path.join(self.data_dir, "config.json"))
        self.lib = Library(os.path.join(self.data_dir, "library.json"))
        if self.cfg.get("colors"):
            self.lib.migrate_colors(self.cfg.data.pop("colors"))
            self.lib.save()
        self.pipeline = Pipeline(self.cfg)
        if self.cfg["name_rules"] is None:
            self.cfg["name_rules"] = DEFAULT_NAME_RULES
        self.colors = ColorEngine(self)
        self.dirsizes = DirSizeManager()
        self.dirsizes.ready.connect(self._dir_size_ready)
        self.icons = Icons()
        self.icons.set_default_folder(self.cfg["folder_color"] or "yellow")
        self.thumbs = ThumbManager(self.cfg, self.data_dir)
        self.fs = QFileSystemModel()
        self.fs.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)
        self.fs.setRootPath("")
        self.info_signals = Signals()
        self.info_signals.info.connect(self._info_ready)
        self.thumbs.ready.connect(self._thumb_for_info)
        self.info_token = 0
        self._info_entry = None
        self._info_base = ""
        self.clip_entries = []
        self.op_worker = None
        self.save_timer = QTimer(self, singleShot=True, interval=800, timeout=self._save_now)

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setWindowIcon(self.icons.app_icon())
        self._build()
        self._restore(start_path)

    # ------------------------------------------------------------------ UI
    def _build(self):
        ic = self.icons
        # --- selector de modo: va arriba a la derecha, en la fila de pestañas
        self.modebar = QTabBar()
        self.modebar.setObjectName("modebar")
        self.modebar.setDocumentMode(True)
        self.modebar.setDrawBase(False)
        self.modebar.setExpanding(False)
        self.modebar.setUsesScrollButtons(False)
        self.modebar.setElideMode(Qt.ElideNone)
        self.modebar.addTab(ic.glyph("folder", 16), "File Explorer")
        self.modebar.addTab(ic.glyph("library", 16, "#4cc2ff"), "VFX Library")
        self.modebar.setTabToolTip(0, "File Explorer (Ctrl+Shift+E)")
        self.modebar.setTabToolTip(1, "VFX Library: viewer on top, elements below (Ctrl+Shift+L)")
        self.modebar.currentChanged.connect(lambda i: self.set_mode("library" if i == 1 else "explorer"))

        # --- fila de herramientas: ＋ | pipeline (Carpetas) o tags rápidos (VFX Library) | doble panel, detalles, ⚙
        self.pipebar_top = PipelineBar(self, vertical=False)
        self.tagbar = QuickTagBar(self)
        self.ctx_stack = QStackedWidget()
        pw = QWidget()
        pwl = QHBoxLayout(pw)
        pwl.setContentsMargins(0, 0, 0, 0)
        pwl.setContentsMargins(8, 0, 8, 0)
        pwl.addWidget(self.pipebar_top, 1)
        self.ctx_stack.addWidget(pw)
        self.ctx_stack.addWidget(self.tagbar)
        self.ctx_stack.addWidget(QWidget())
        self.ctx_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ctx_stack.setFixedHeight(34)
        self.pipe_frame = self.ctx_stack

        cmd = QFrame()
        cmd.setObjectName("cmdrow")
        self.cmdrow = cmd
        ch = QHBoxLayout(cmd)
        ch.setContentsMargins(0, 3, 0, 3)
        ch.setSpacing(0)
        # izquierda (ancho del panel izquierdo): New, View, Filter, ⋯
        self.cmd_left = QWidget()
        cll = QHBoxLayout(self.cmd_left)
        cll.setContentsMargins(6, 0, 6, 0)
        cll.setSpacing(2)
        self.m_new = QMenu(self)
        self.m_new.aboutToShow.connect(self._fill_new_menu)
        self.b_new = ChevronButton(ic.new_icon(18), "New", self.m_new, "New: folder, tab…")
        cll.addWidget(self.b_new)
        self.m_sort = QMenu(self)                      # el botón Sort está en cada barra de dirección
        self.m_sort.aboutToShow.connect(self._fill_sort_menu)
        self.m_view = QMenu(self)
        self.m_view.aboutToShow.connect(self._fill_view_menu)
        self.b_view = ChevronButton(ic.glyph("list", 18), "View", self.m_view, "View: icon size, details, hidden items…")
        cll.addWidget(self.b_view)
        self.m_filter = QMenu(self)
        self.m_filter.aboutToShow.connect(self._fill_filter_menu)
        self.b_filter = ChevronButton(ic.glyph("filter", 18), "", self.m_filter, "Filter: show only one file type")
        cll.addWidget(self.b_filter)
        self.m_more = QMenu(self)
        self.m_more.aboutToShow.connect(self._fill_more_menu)
        b_more = QToolButton()
        b_more.setIcon(ic.glyph("more", 18))
        b_more.setIconSize(QSize(18, 18))
        b_more.setToolTip("More: select, copy path…")
        b_more.setMenu(self.m_more)
        b_more.setPopupMode(QToolButton.InstantPopup)
        self._popfix(b_more)
        b_more.setFixedSize(34, 32)
        cll.addWidget(b_more)
        cll.addStretch(1)
        self.chev_buttons = (self.b_new, self.b_view)

        def vsep():
            f = QFrame()
            f.setFixedWidth(1)
            f.setStyleSheet("background:#2e2e2e;")
            return f
        ch.addWidget(self.cmd_left)
        ch.addWidget(vsep())          # divisor alineado con el borde del panel izquierdo
        ch.addWidget(self.ctx_stack, 1)
        ch.addWidget(vsep())          # divisor alineado con el panel de detalles

        def tool(action):
            b = QToolButton()
            b.setDefaultAction(action)
            b.setAutoRaise(True)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if action.text() else Qt.ToolButtonIconOnly)
            return b
        self.act_dual = QAction(ic.glyph("dual", 16, ACCENT), "Dual pane", self)
        self.act_dual.triggered.connect(lambda: self.toggle_dual())
        self.act_dual.setCheckable(True)
        self.act_dual.setToolTip("Dual pane (F9) · F6 switches pane")
        self.act_details = QAction(ic.glyph("details", 16, ACCENT), "Details", self)
        self.act_details.triggered.connect(lambda: self.toggle_details())
        self.act_details.setCheckable(True)
        self.act_details.setToolTip("Details pane (Alt+Shift+P)")
        a_set = QAction(ic.glyph("gear", 18), "", self)
        a_set.setToolTip("Settings")
        a_set.triggered.connect(lambda: self.open_settings())
        self.cmd_right = QWidget()
        crr = QHBoxLayout(self.cmd_right)
        crr.setContentsMargins(6, 0, 6, 0)
        crr.setSpacing(2)
        crr.addStretch(1)
        for a in (self.act_dual, self.act_details, a_set):
            crr.addWidget(tool(a))
        ch.addWidget(self.cmd_right)

        # --- sidebar: ACCESO RÁPIDO (de cada modo) arriba, y abajo los tabs CARPETAS / VFX LIBRARY
        pin = ic.glyph("pin", 14, "#c9ccd1")
        self.favs = QuickList(pin)
        self.lib_favs = QuickList(pin)
        for w, menu_fn, click_fn, lib in (
                (self.favs, self._favs_menu, lambda it: it.data(Qt.UserRole) and self.open_in_explorer(it.data(Qt.UserRole)), False),
                (self.lib_favs, self._lib_favs_menu, lambda it: it.data(Qt.UserRole) and self.open_library(it.data(Qt.UserRole)), True)):
            w.setContextMenuPolicy(Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(lambda pos, w=w, f=menu_fn: f(w, pos))
            w.itemClicked.connect(click_fn)
            w.model().rowsMoved.connect(self._favs_reordered)
            w.dropped.connect(lambda dirs, lib=lib: self._quick_dropped(dirs, lib))
        self.colls = self._mk_list(self._colls_menu, lambda it: self.open_collection(it.data(Qt.UserRole)))
        self.tagl = self._mk_list(self._tags_menu, lambda it: self.open_tag(it.data(Qt.UserRole)))

        self.tree = LinedTree(self)
        self.tree.setModel(self.fs)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeMode.ResizeToContents)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.clicked.connect(lambda ix: self.open_in_explorer(self.fs.filePath(ix)))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.setDragEnabled(True)            # arrastrar carpetas a Acceso rápido / a otros paneles
        self.fs.rowsInserted.connect(lambda parent, *_: (not parent.isValid()) and
                                     QTimer.singleShot(0, self._apply_hidden_drives))

        self.libside = LibrarySidebar(self)
        self.pipebar_side = PipelineBar(self, vertical=True)
        self.pipebars = [self.pipebar_top, self.pipebar_side]
        self.side_boxes = {}

        def boxed(title, w):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(1)
            if title:
                bl.addWidget(self._section(title))
            bl.addWidget(w, 1)
            return box

        self.quick_stack = QStackedWidget()
        self.quick_stack.addWidget(self.favs)
        self.quick_stack.addWidget(self.lib_favs)
        self.quick_title = self._section("QUICK ACCESS")
        quick = QWidget()
        quick.setObjectName("quickBox")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(1)
        qh = QHBoxLayout()
        qh.setContentsMargins(0, 0, 4, 0)
        qh.setSpacing(0)
        qh.addWidget(self.quick_title, 1)
        self.b_eye = self._eye_button("show_hidden_quick", "Show hidden Quick access items\n"
                                      "(hide them with right-click › Hide)", self._reload_sidebar)
        self.b_quick_add = QToolButton()
        self.b_quick_add.setIcon(ic.glyph("plus", 14))
        self.b_quick_add.setAutoRaise(True)
        self.b_quick_add.setToolTip("Pin the current folder to Quick access")
        self.b_quick_add.clicked.connect(self._quick_add)
        self._popfix(self.b_quick_add)
        qh.addWidget(self.b_eye)
        qh.addWidget(self.b_quick_add)
        ql.addLayout(qh)
        ql.addWidget(self.quick_stack, 1)
        self.side_boxes["favs"] = quick

        # tab CARPETAS: (pipeline vertical) + Este equipo + árbol
        self.thispc = self._mk_list(lambda w, pos: None, lambda it: self.open_in_explorer("::thispc"))
        it = QListWidgetItem(ic.glyph("pc", 18, "#4cc2ff"), "This PC")
        it.setToolTip("Drives and network locations")
        self.thispc.addItem(it)
        self.thispc.setFixedHeight(34)
        self.thispc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        folders_page = QWidget()
        fpl = QVBoxLayout(folders_page)
        fpl.setContentsMargins(0, 0, 0, 0)
        fpl.setSpacing(0)
        self.side_boxes["pipeline"] = boxed("PIPELINE", self.pipebar_side)
        fpl.addWidget(self.side_boxes["pipeline"])
        fpl.addWidget(self.thispc)
        fpl.addWidget(self.tree, 1)
        self.side_boxes["tree"] = folders_page

        # tab VFX LIBRARY: árbol de la librería (+ colecciones y tags si están activados)
        lib_page = QSplitter(Qt.Vertical)
        lib_page.addWidget(self.libside)
        self.side_boxes["colls"] = boxed("COLLECTIONS", self.colls)
        self.side_boxes["tags"] = boxed("TAGS", self.tagl)
        lib_page.addWidget(self.side_boxes["colls"])
        lib_page.addWidget(self.side_boxes["tags"])
        lib_page.setSizes([500, 90, 110])
        self.side_boxes["library"] = lib_page

        self.sidetabs = QTabWidget()
        self.sidetabs.setObjectName("sidetabs")
        self.sidetabs.setDocumentMode(True)
        self.sidetabs.tabBar().setDrawBase(False)
        self.sidetabs.addTab(folders_page, "FILE EXPLORER")
        self.sidetabs.addTab(lib_page, "VFX LIBRARY")
        self.sidetabs.setTabToolTip(0, "File Explorer: This PC and the folder tree")
        self.sidetabs.setTabToolTip(1, "VFX Library: your element folders.\n"
                                       "Drag files over a tab to show its tree and drop them there.")
        corner = QWidget()
        crl = QHBoxLayout(corner)
        crl.setContentsMargins(0, 0, 2, 0)
        crl.setSpacing(0)
        self.b_colors = QToolButton()
        self.b_colors.setIcon(self._palette_icon())
        self.b_colors.setAutoRaise(True)
        self.b_colors.setPopupMode(QToolButton.InstantPopup)
        self._popfix(self.b_colors)
        self.m_colors = QMenu(self)
        self.m_colors.aboutToShow.connect(self._fill_colors_menu)
        self.b_colors.setMenu(self.m_colors)
        self.b_colors.setToolTip("Automatic folder colors (by project, by name…)")
        self.b_side_add = QToolButton()
        self.b_side_add.setIcon(ic.glyph("plus", 14))
        self.b_side_add.setAutoRaise(True)
        self.b_side_add.clicked.connect(self._side_add)
        self.b_side_add.setToolTip("Add folder to the VFX Library")
        self._popfix(self.b_side_add)
        self.b_eye_tree = self._eye_button("show_hidden_drives", "Show hidden drives\n"
                                           "(hide a drive with right-click › Hide drive)", self._apply_hidden_drives)
        crl.addWidget(self.b_eye_tree)
        crl.addWidget(self.b_colors)
        crl.addWidget(self.b_side_add)
        self.sidetabs.setCornerWidget(corner, Qt.TopRightCorner)
        self._peek = False
        self.sidetabs.currentChanged.connect(self._sidetab_changed)
        tb = self.sidetabs.tabBar()
        tb.setAcceptDrops(True)
        tb.installEventFilter(self)
        self.peek_timer = QTimer(self, interval=300, timeout=self._peek_check)
        self.peek_delay = QTimer(self, singleShot=True, interval=600, timeout=self._peek_fire)
        self._peek_prev = None
        self._peek_want = None

        left = QSplitter(Qt.Vertical)
        left.addWidget(quick)
        left.addWidget(self.sidetabs)
        left.setStretchFactor(1, 1)
        left.setSizes([300, 600])
        left.setCollapsible(1, False)
        left.setMinimumWidth(200)
        self.left_split = left

        # --- paneles
        self.paneA = FilePane(self, "A")
        self.paneB = FilePane(self, "B")
        self.panes = [self.paneA, self.paneB]
        for p in self.panes:
            p.focused.connect(self.set_active)
            p.selection_changed.connect(self._sel_changed)
            p.location_changed.connect(self._location_changed)
            p.status_changed.connect(self._pane_status)
        self.active = self.paneA
        self.pane_split = QSplitter(Qt.Horizontal)
        self.pane_split.addWidget(self.paneA)
        self.pane_split.addWidget(self.paneB)
        self.paneB.hide()

        self.libpage = LibraryPage(self)
        self.libpane = self.libpage.pane
        lp = self.libpane
        lp.root_lock = lambda: [r for r in (self.cfg["library_roots"] or []) if os.path.isdir(r)]
        lp.focused.connect(self.set_active)
        lp.selection_changed.connect(self._sel_changed)
        lp.location_changed.connect(self._location_changed)
        lp.status_changed.connect(self._pane_status)
        self.all_panes = [self.paneA, self.paneB, lp]
        self.explorer_active = self.paneA
        self.tagbar.changed.connect(lambda labels, kws: self.libpane.set_pills(labels, kws))

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.pane_split)
        self.center_stack.addWidget(self.libpage)

        # --- detalles
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(170)
        self.preview.setStyleSheet("background:#17181a; border-radius:6px;")
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.info.setTextFormat(Qt.RichText)
        iw = QWidget()
        il = QVBoxLayout(iw)
        il.setContentsMargins(8, 8, 8, 8)
        il.addWidget(self.preview)
        il.addWidget(self.info)
        il.addStretch(1)
        sa = QScrollArea()
        self.info_area = sa
        sa.setWidget(iw)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setMinimumWidth(240)

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.center_stack)
        main.addWidget(sa)
        main.setStretchFactor(1, 1)
        main.setSizes([280, 940, 300])
        main.setCollapsible(0, False)
        main.splitterMoved.connect(lambda *_: self._sync_cmd_left())
        self.pane_split.splitterMoved.connect(lambda *_: self._sync_cmd_left())
        for sp in (main, left, self.pane_split, self.libpage.split, lib_page):
            sp.setObjectName("softSplit")
            sp.setHandleWidth(3)
        self.main_split = main

        # --- arriba: pestañas + dirección (del panel visible) a todo el ancho, después la fila de herramientas
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.head_host = QWidget()
        self.head_host.setObjectName("headHost")
        hh = QHBoxLayout(self.head_host)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.setSpacing(0)
        rl.addWidget(self.head_host)
        rl.addWidget(cmd)
        rl.addWidget(main, 1)
        self.setCentralWidget(root)

        # --- barra de estado: cantidad | subcarpetas, filtro, ordenar, ver, ⋯ | selección, tamaño, vistas
        sb = self.statusBar()
        self.status = QLabel()
        sb.addWidget(self.status, 1)

        def sbtn(glyph, tip, slot=None, checkable=False):
            b = QToolButton()
            b.setIcon(ic.glyph(glyph, 16))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setCheckable(checkable)
            if slot:
                b.clicked.connect(slot)
            srl.addWidget(b)
            return b
        self.sub_switch = SubfolderSwitch()
        self.sub_switch.changed.connect(lambda v: self.active.set_rec_level(v))
        sb.addPermanentWidget(self.sub_switch)
        self.sb_right = QWidget()             # alineado con el panel de detalles
        srl = QHBoxLayout(self.sb_right)
        srl.setContentsMargins(10, 0, 4, 0)
        srl.setSpacing(2)
        sb.addPermanentWidget(self.sb_right)
        self.status_right = QLabel()
        self.status_right.setMaximumWidth(260)
        srl.addWidget(self.status_right, 1)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(96, 320)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Icon size")
        self.size_slider.setValue(int(self.cfg["thumb_size"]))
        self.size_slider.valueChanged.connect(self._on_thumb_size)
        srl.addWidget(self.size_slider)
        self.sb_list = sbtn("list", "Details (Ctrl+2)", slot=lambda: self.active.set_view("list"), checkable=True)
        self.sb_grid = sbtn("grid", "Large icons (Ctrl+1)", slot=lambda: self.active.set_view("grid"),
                            checkable=True)
        sb.setSizeGripEnabled(False)

        self.setStyleSheet(f"""
            #pane {{ border:none; }}
            #paneNav[active="true"] {{ border-bottom:2px solid {ACCENT}; }}
            #paneHeader {{ background:#191919; }}
            #paneTabs {{ background:#191919; }}
            #paneNav {{ background:#2b2b2b; border-bottom:1px solid #232323; }}
            #cmdrow {{ background:#1f1f1f; border-bottom:1px solid #2a2a2a; }}
            #cmdrow QToolButton {{ padding:4px 8px; border-radius:4px; }}
            #cmdrow QToolButton:hover {{ background:#2d2d2d; }}
            #cmdrow QToolButton:checked {{ background:#2d2d2d; }}
            #sidetabs::pane {{ border:none; }}
            #sidetabs QTabBar::tab {{ padding:5px 8px; border-radius:4px; margin:4px 2px 2px 4px;
                                      color:#7d8590; font-size:7.5pt; font-weight:bold; letter-spacing:1px; }}
            #sidetabs QTabBar::tab:selected {{ background:#2d2d2d; color:#ffffff; }}
            #sidetabs QTabBar::tab:hover:!selected {{ color:#c9ccd1; }}
            #paneSearch {{ border-radius:4px; }}
            #paneFooter {{ color:#9d9d9d; font-size:8pt; padding:3px 10px; background:#191919;
                           border-top:1px solid #232323; }}
            #paneBanner {{ background:#0f3a55; color:#e6f6ff; padding:5px 12px; font-size:8.5pt;
                           border-bottom:1px solid #1a5c86; }}
            #viewerBar {{ background:#202020; border-top:1px solid #2a2a2a; }}
            #modebar::tab {{ padding:5px 16px; min-width:100px; border-radius:6px; margin:0 2px 2px 2px; }}
            #modebar::tab:selected {{ background:#2d2d2d; color:#ffffff; }}
            QStatusBar QToolButton {{ padding:2px; }}
            #fileList {{ padding:6px 6px 0 14px; background:#191919; border:none; }}
            #fileList::item {{ min-height:26px; }}
            #fileGrid {{ padding:8px 6px 0 14px; background:#191919; border:none; }}
            #sideTree, #quickList {{ padding:2px 2px 2px 6px; }}
            #paneTabs QTabBar::tab {{ padding:6px 10px; margin:4px 1px 0 1px; min-width:0; max-width:1000px; }}
            #paneTabs QTabBar::tab:selected {{ font-weight:bold; }}
            #softSplit::handle {{ background:#1c1c1c; }}
            #softSplit::handle:horizontal {{ border-left:1px solid #2c2c2c; }}
            #softSplit::handle:vertical {{ border-top:1px solid #2c2c2c; }}
            #cmdrow {{ border-top:1px solid #2a2a2a; }}
            QStatusBar {{ border-top:1px solid #2a2a2a; }}
            QListWidget, QTreeWidget, QTreeView {{ background:#191919; }}
        """)
        QShortcut(QKeySequence("F9"), self, self.toggle_dual)
        QShortcut(QKeySequence("F6"), self, self.switch_pane)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, lambda: self.set_mode("explorer"))
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, lambda: self.set_mode("library"))
        QShortcut(QKeySequence("Alt+Shift+P"), self, self.toggle_details)
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(0, self._apply_hidden_drives)
        self._sidetab_changed(self.sidetabs.currentIndex())
        self._sidetab_changed(self.sidetabs.currentIndex())
        self._reload_sidebar()
        self.apply_features()
        self._place_headers()
        self.apply_pipeline_location()

    # ------------------------------------------------------------------ cabeceras / sidebar
    def _place_headers(self):
        """Las pestañas y la dirección de Carpetas van siempre arriba, a todo el ancho (como el Explorador de
        Windows 11); en doble panel, una al lado de la otra, alineadas con cada panel. La VFX Library tiene sus
        pestañas en el centro, entre el viewer y los elementos. El selector de modo va a la derecha."""
        dual = bool(self.cfg["dual"]) if self.mode() == "library" else self.paneB.isVisible()
        hl = self.head_host.layout()
        for p in self.panes:
            if p.header.parent() is not self.head_host:
                p.layout().removeWidget(p.header)
                hl.addWidget(p.header)
        hl.setStretch(0, 0 if dual else 1)
        hl.setStretch(1, 1)
        self.paneB.header.setVisible(dual)
        self.paneA.header.show()
        lp = self.libpane
        if lp.header.parent() is not lp:
            lp.layout().insertWidget(0, lp.header)
        (self.paneB if dual else self.paneA).corner.addWidget(self.modebar)
        for p in self.all_panes:
            p.footer.setVisible(dual and p is not lp)
        self.modebar.ensurePolished()
        QTimer.singleShot(0, lambda: self.modebar.setMinimumWidth(
            sum(self.modebar.tabRect(i).width() for i in range(self.modebar.count())) + 8))
        QTimer.singleShot(0, self._sync_cmd_left)

    def _sync_cmd_left(self):
        """Alinea la fila de herramientas y las cabeceras con las columnas de abajo."""
        s = self.main_split.sizes()
        hw = self.main_split.handleWidth()
        if not s or s[0] <= 0:
            return
        lw = s[0] + hw
        lay = self.cmd_left.layout()

        def need():
            m = lay.contentsMargins()
            ws = [lay.itemAt(i).widget() for i in range(lay.count())]
            ws = [x for x in ws if x is not None]
            return m.left() + m.right() + sum(x.sizeHint().width() for x in ws) + lay.spacing() * len(ws)
        for b in self.chev_buttons:
            b.set_compact(False)
        self.b_filter.set_compact(False)
        if need() > lw:                    # no entra: New / View quedan solo con ícono
            for b in self.chev_buttons:
                b.set_compact(True)
        if need() > lw:
            self.b_filter.set_compact(True)
        self.cmd_left.setFixedWidth(lw - 1)
        rw = (s[2] + hw) if (self.info_area.isVisible() and s[2] > 0) else 0
        self.cmd_right.setFixedWidth(max(self.cmd_right.layout().sizeHint().width(), rw))
        self.sb_right.setFixedWidth(max(self.sb_right.layout().sizeHint().width(), rw))
        if self.paneB.header.isVisible():
            ps = self.pane_split.sizes()
            if ps and ps[0] > 0:
                self.paneA.header.setFixedWidth(s[0] + hw + ps[0] + self.pane_split.handleWidth() // 2)
        else:
            self.paneA.header.setMinimumWidth(0)
            self.paneA.header.setMaximumWidth(16777215)

    def _popfix(self, b):
        """Botones de ícono que no se corren al pasar el mouse."""
        b.setStyleSheet("QToolButton{border:none;padding:3px;border-radius:4px;}"
                        "QToolButton:hover{background:#2d2d2d;} QToolButton:checked{background:#383838;}"
                        "QToolButton::menu-indicator{image:none;width:0px;}")
        b.setFixedSize(28, 26)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._sync_cmd_left)

    def _palette_icon(self):
        from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon
        pm = QPixmap(16, 16)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for (x, y), c in zip(((1, 1), (9, 1), (1, 9), (9, 9)), ("#f4c443", "#4ea1ff", "#ff6b6b", "#3ecf8e")):
            p.setBrush(QColor(c))
            p.drawRoundedRect(x, y, 6, 6, 2, 2)
        p.end()
        return QIcon(pm)

    def _fill_colors_menu(self):
        m = self.m_colors
        m.clear()
        m.addSection("Automatic colors")
        cur = self.cfg["color_mode"]
        for label, key in COLOR_MODES:
            a = m.addAction(label, lambda k=key: self.set_color_mode(k))
            a.setCheckable(True)
            a.setChecked(cur == key)
        m.addSeparator()
        m.addAction("Manual color (right-click › Color label) always wins").setEnabled(False)
        m.addAction(self.icons.glyph("gear", 16), "Colors and lines settings…", lambda: self.open_settings("Colors"))

    def set_color_mode(self, key):
        self.cfg["color_mode"] = key
        self.colors.reload()
        self.save_soon()
        self.refresh_views()
        self._reload_sidebar()

    def _side_add(self):
        self.libside.add_root()

    def _quick_add(self):
        lib = self.quick_stack.currentIndex() == 1
        d = (self.libpane if lib else self.explorer_active).current_dir()
        if d:
            self.add_favorites([d], lib=lib)

    SYS_FOLDERS = (("desktop", "Desktop"), ("documents", "Documents"), ("downloads", "Downloads"), ("pictures", "Pictures"),
                   ("videos", "Videos"))

    def _sys_path(self, kind):
        from PySide6.QtCore import QStandardPaths as SP
        loc = {"desktop": SP.DesktopLocation, "documents": SP.DocumentsLocation, "downloads": SP.DownloadLocation,
               "pictures": SP.PicturesLocation, "videos": SP.MoviesLocation}[kind]
        p = SP.writableLocation(loc)
        return os.path.normpath(p) if p and os.path.isdir(p) else ""

    def _eye_button(self, key, tip, on_change):
        b = QToolButton()
        b.setCheckable(True)
        b.setChecked(bool(self.cfg[key]))
        b.setAutoRaise(True)
        b.setToolTip(tip)
        self._popfix(b)

        def upd(on):
            b.setIcon(self.icons.eye(16, on=on, color="#4cc2ff" if on else "#9d9d9d"))
        upd(b.isChecked())

        def toggled(on):
            upd(on)
            self.cfg[key] = on
            self.cfg.save()
            on_change()
        b.toggled.connect(toggled)
        return b

    def _quick_dropped(self, dirs, lib):
        if lib:
            dirs = [d for d in dirs if self.libpane.allowed(d)]
            if not dirs:
                self.status.setText("Only VFX Library folders can be pinned here")
                return
        self.add_favorites(dirs, lib=lib)

    def _apply_hidden_drives(self):
        """Oculta en el árbol de Carpetas los discos marcados (salvo con el ojito prendido)."""
        from PySide6.QtCore import QModelIndex
        hidden = {norm_key(p) for p in (self.cfg["hidden_drives"] or [])}
        show = bool(self.cfg["show_hidden_drives"])
        root = QModelIndex()
        for r in range(self.fs.rowCount(root)):
            ix = self.fs.index(r, 0, root)
            self.tree.setRowHidden(r, root, (not show) and norm_key(self.fs.filePath(ix)) in hidden)
        self.tree.viewport().update()

    def _toggle_drive(self, path):
        hidden = list(self.cfg["hidden_drives"] or [])
        k = norm_key(path)
        if k in {norm_key(x) for x in hidden}:
            hidden = [x for x in hidden if norm_key(x) != k]
        else:
            hidden.append(path)
        self.cfg["hidden_drives"] = hidden
        self.cfg.save()
        self._apply_hidden_drives()

    def _toggle_sys(self, kind):
        hidden = list(self.cfg["hidden_sys"] or [])
        if kind in hidden:
            hidden.remove(kind)
        else:
            hidden.append(kind)
        self.cfg["hidden_sys"] = hidden
        self.cfg.save()
        self._reload_sidebar()

    def _side_tooltip(self, i):
        self.b_side_add.setVisible(i == 1)
        self.b_eye.setVisible(i == 0)
        self.b_eye_tree.setVisible(i == 0)

    def _sidetab_changed(self, i):
        """Los tabs del panel izquierdo solo cambian el árbol (y el acceso rápido): el modo del centro cambia
        recién al hacer click en una carpeta."""
        self._side_tooltip(i)
        if not self._peek:
            self.quick_stack.setCurrentIndex(i)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonPress and isinstance(obj, QWidget) and hasattr(self, "panes"):
            self._header_press(obj)
        if hasattr(self, "sidetabs") and obj is self.sidetabs.tabBar():
            t = ev.type()
            if t == QEvent.DragEnter:
                ev.accept()
                return True
            if t == QEvent.DragMove:
                i = obj.tabAt(ev.position().toPoint())
                if i >= 0 and i != self.sidetabs.currentIndex():
                    if getattr(self, "_peek_want", None) != i:      # hay que quedarse un momento encima
                        self._peek_want = i
                        self.peek_delay.start()
                else:
                    self._peek_want = None
                    self.peek_delay.stop()
                ev.ignore()
                return True
            if t == QEvent.DragLeave:
                self._peek_want = None
                self.peek_delay.stop()
            if t == QEvent.Drop:
                ev.ignore()
                return True
        return super().eventFilter(obj, ev)

    def _header_press(self, w):
        """Click en las pestañas o la dirección de un panel de Carpetas: activa ese panel (y si estamos en la
        VFX Library, vuelve a Carpetas). El selector de modo queda afuera."""
        x = w
        while x is not None:
            if x is self.modebar:
                return
            for p in self.panes:
                if x is p.header:
                    if self.mode() == "library":
                        self.set_mode("explorer")
                    if p is not self.active:
                        self.set_active(p)
                    return
            if x is self:
                return
            x = x.parentWidget()

    def _peek_side(self, i):
        """Mientras se arrastra, mostrar el árbol del otro tab (sin tocar el modo ni el acceso rápido, para
        poder seguir soltando ahí); al terminar el arrastre vuelve como estaba."""
        if self._peek_prev is None:
            self._peek_prev = self.sidetabs.currentIndex()
        self._peek = True
        self.sidetabs.setCurrentIndex(i)
        self._peek = False
        self.peek_timer.start()

    def _peek_fire(self):
        if getattr(self, "_peek_want", None) is not None:
            self._peek_side(self._peek_want)

    def _peek_check(self):
        if QApplication.mouseButtons() == Qt.NoButton:
            self.end_peek()

    def end_peek(self):
        self.peek_timer.stop()
        self.peek_delay.stop()
        self._peek_want = None
        if self._peek_prev is not None:
            prev, self._peek_prev = self._peek_prev, None
            self._peek = True
            self.sidetabs.setCurrentIndex(prev)
            self._peek = False

    def _fill_new_menu(self):
        m = self.m_new
        m.clear()
        pane = self.active
        m.addAction(self.icons.glyph("newfolder", 16), "Folder\tCtrl+Shift+N",
                    lambda: self.op_new_folder(pane)).setEnabled(bool(pane.current_dir()))
        m.addAction(self.icons.glyph("plus", 16), "Tab\tCtrl+T",
                    pane.new_tab)
        m.addSeparator()
        if self.mode() == "library":
            m.addAction(self.icons.glyph("library", 16, "#4cc2ff"), "Folder in the VFX Library…",
                        self.libside.add_root)
        if pane.current_dir():
            m.addAction(self.icons.glyph("pin", 16), "Pin this folder to Quick access",
                        lambda: self.add_favorites([pane.current_dir()]))

    def _mk_list(self, menu_fn, click_fn):
        w = QListWidget()
        w.setIconSize(QSize(16, 16))
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(lambda pos, w=w: menu_fn(w, pos))
        w.itemClicked.connect(click_fn)
        return w

    def _section(self, text):
        l = QLabel(text)
        l.setStyleSheet("color:#7d8590; font-size:7.5pt; font-weight:bold; padding:4px 6px 0 6px; letter-spacing:1px;")
        return l

    def _restore(self, start_path):
        g = self.cfg["geometry"]
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))
        else:
            self.resize(1560, 920)
        for k, sp in (("splitter", self.main_split), ("splitter_left3", self.left_split),
                      ("splitter_panes", self.pane_split), ("splitter_library", self.libpage.split)):
            if self.cfg[k]:
                sp.restoreState(QByteArray.fromBase64(self.cfg[k].encode()))
        states = self.cfg["panes"] or []
        home = QDir.homePath()
        from .core import THISPC
        fallback = start_path if start_path and os.path.isdir(start_path) else (THISPC if IS_WIN else home)
        a_state = states[0] if states else None
        if start_path and os.path.isdir(start_path):
            a_state = {"tabs": [{"path": start_path}], "current": 0, "view": (a_state or {}).get("view", "grid")}
        self.paneA.restore(a_state, fallback)
        self.paneB.restore(states[1] if len(states) > 1 else None, fallback)
        if self.cfg["dual"]:
            self.toggle_dual(force=True)
        roots = self.libpane.root_lock()
        lst = self.cfg["library_pane"] or None
        if lst:
            lst = dict(lst, tabs=[t for t in lst.get("tabs", []) if self.libpane.allowed(t.get("path", ""))])
        if roots:
            self.libpane.restore(lst, roots[0])
        if not lst:
            self.libpane.set_view("grid", emit=False)
        self.set_active(self.paneA)
        if self.cfg["mode"] == "library" and not start_path:
            self.set_mode("library")
        self.toggle_details(self.cfg.get("details_visible", True))
        self.sync_commandbar(self.active)

    def showEvent(self, ev):
        super().showEvent(ev)
        if not getattr(self, "_titlebar_done", False):
            self._titlebar_done = True
            from .widgets import win11_titlebar
            win11_titlebar(self)

    def _save_now(self):
        self.cfg["panes"] = [p.state() for p in self.panes]
        self.cfg["library_pane"] = self.libpane.state()
        self.cfg["dual"] = self.paneB.isVisible()
        self.cfg.save()
        self.lib.save()

    def save_soon(self):
        self.save_timer.start()

    def closeEvent(self, ev):
        self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.cfg["splitter"] = bytes(self.main_split.saveState().toBase64()).decode()
        self.cfg["splitter_left3"] = bytes(self.left_split.saveState().toBase64()).decode()
        self.cfg["splitter_panes"] = bytes(self.pane_split.saveState().toBase64()).decode()
        self.cfg["splitter_library"] = bytes(self.libpage.split.saveState().toBase64()).decode()
        self._save_now()
        for p in self.all_panes:
            p._stop_search()
        self.thumbs.cancel_pending()
        self.dirsizes.clear()
        self.libpage.shutdown()
        super().closeEvent(ev)

    # ------------------------------------------------------------------ barra de comandos (Windows 11)
    def accent(self):
        return ACCENT

    def toggle_details(self, force=None, remember=True):
        show = (not self.info_area.isVisible()) if force is None else bool(force)
        changed = show != self.info_area.isVisible()
        self.info_area.setVisible(show)
        self.act_details.setChecked(show)
        QTimer.singleShot(0, self._sync_cmd_left)
        self.cfg["details_visible"] = show
        if remember and changed and getattr(self, "active", None) is not None:
            self.active._save_folder_view()            # el panel de detalles también se recuerda por carpeta
        self.save_soon()

    def sync_commandbar(self, pane=None):
        """Refleja en la barra de comandos y en la barra de estado el estado del panel activo."""
        pane = pane or self.active
        if pane is not getattr(self, "active", None) or not hasattr(self, "sub_switch"):
            return
        self.sub_switch.set_value(pane.rec_value(), emit=False)
        self.sub_switch.setEnabled(not pane.is_virtual())
        cat = pane.filter.currentData()
        label = next((l for l, k in FILTERS if k == cat), "Filter")
        on = cat != "all"
        self.b_filter.setIcon(self.icons.glyph("filter", 18, ACCENT if on else "#c9ccd1"))
        self.b_filter.setText(label if on else "")      # con filtro: se ve cuál (resaltado)
        self.b_filter.set_active(on)
        self.b_filter.setToolTip("Filter: show only one file type" if not on else
                                 f"Filter on: {label} · click › All to clear")
        QTimer.singleShot(0, self._sync_cmd_left)
        self.sb_grid.setChecked(pane.view_mode == "grid")
        self.sb_list.setChecked(pane.view_mode != "grid")

    def _fill_sort_menu(self, m=None, with_group=True):
        m = m if m is not None else self.m_sort
        m.clear()
        pane = self.active
        hd = pane.list.header()
        cur, order = hd.sortIndicatorSection(), hd.sortIndicatorOrder()
        from .models import C_NAME, C_MTIME, C_TYPE, C_SIZE, C_FRAMES, C_RANGE
        for label, col in (("Name", C_NAME), ("Date modified", C_MTIME), ("Type", C_TYPE),
                           ("Size", C_SIZE), ("Frame count", C_FRAMES), ("First frame", C_RANGE)):
            a = m.addAction(label, lambda c=col: pane.list.sortByColumn(c, order))
            a.setCheckable(True)
            a.setChecked(cur == col)
        m.addSeparator()
        for label, o in (("Ascending", Qt.AscendingOrder), ("Descending", Qt.DescendingOrder)):
            a = m.addAction(label, lambda o=o: pane.list.sortByColumn(cur, o))
            a.setCheckable(True)
            a.setChecked(order == o)
        if with_group:
            m.addSeparator()
            self._fill_group_menu(m.addMenu(self.icons.glyph("group", 16, ACCENT), "Group by"))

    def _fill_group_menu(self, g):
        pane = self.active
        for label, key in (("Date modified", "date"), ("Type", "type"), ("Folder", "folder"), (None, None),
                           ("(None)", "none"), ("Automatic (folder in Subfolders)", "auto")):
            if label is None:
                g.addSeparator()
                continue
            a = g.addAction(label, lambda k=key: pane.set_group(k))
            a.setCheckable(True)
            a.setChecked(pane.group_mode == key)

    def _fill_view_menu(self, m=None, full=True):
        m = m if m is not None else self.m_view
        m.clear()
        pane = self.active
        ts = int(self.cfg["thumb_size"])
        for label, size in (("Extra large icons", 320), ("Large icons", 240), ("Medium icons", 180),
                            ("Small icons", 120)):
            a = m.addAction(self.icons.glyph("grid", 16), label,
                            lambda sz=size: (pane.set_view("grid"), self.size_slider.setValue(sz)))
            a.setCheckable(True)
            a.setChecked(pane.view_mode == "grid" and abs(ts - size) < 30)
        a = m.addAction(self.icons.glyph("list", 16), "Details\tCtrl+2", lambda: pane.set_view("list"))
        a.setCheckable(True)
        a.setChecked(pane.view_mode != "grid")
        if pane.view_mode != "grid":
            m.addAction("Size all columns to fit", pane.fit_columns)
            a = m.addAction("Row numbers", self._toggle_row_numbers)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg["list_row_numbers"]))
        m.addSeparator()
        m.addAction("Apply this view to all folders", lambda: (
            pane.apply_view_to_all(), self.status.setText("This view is now the default for every folder")))
        if not full:
            return
        m.addSeparator()
        a = m.addAction("Details pane\tAlt+Shift+P", self.toggle_details)
        a.setCheckable(True)
        a.setChecked(self.info_area.isVisible())
        a = m.addAction("Dual pane\tF9", self.toggle_dual)
        a.setCheckable(True)
        a.setChecked(self.paneB.isVisible())
        m.addSeparator()

        def toggle_hidden():
            self.cfg["show_hidden"] = not self.cfg["show_hidden"]
            self.cfg.save()
            for p in self.all_panes:
                p.refresh()
        a = m.addAction("Hidden items", toggle_hidden)
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["show_hidden"]))

        def toggle_sizes():
            self.cfg["folder_sizes"] = not self.cfg["folder_sizes"]
            self.cfg.save()
            if not self.cfg["folder_sizes"]:
                self.dirsizes.clear()
            for p in self.all_panes:
                p.refresh()
        a = m.addAction("Folder sizes", toggle_sizes)
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["folder_sizes"]))

    def _fill_filter_menu(self):
        m = self.m_filter
        m.clear()
        pane = self.active
        cur = pane.filter.currentData()
        for label, key in FILTERS:
            a = m.addAction(label, lambda k=key: pane.filter.setCurrentIndex(pane.filter.findData(k)))
            a.setCheckable(True)
            a.setChecked(cur == key)

    def _fill_more_menu(self):
        m = self.m_more
        m.clear()
        pane = self.active
        v = pane.view()
        m.addAction("Select all\tCtrl+A", v.selectAll)
        m.addAction("Select none", v.clearSelection)

        def invert():
            sel = v.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            for r in range(pane.proxy.rowCount()):
                sel.select(pane.proxy.index(r, 0), QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
        m.addAction("Invert selection", invert)
        m.addSeparator()
        m.addAction("Copy path  (####)\tCtrl+Shift+C", lambda: self.copy_paths(pane, "hash"))
        m.addAction("Copy Nuke path\tCtrl+Alt+C", lambda: self.copy_paths(pane, "nuke"))
        if pane.current_dir():
            m.addAction("Open in Windows Explorer", lambda: self.open_default(pane.current_dir()))
            m.addAction("Pin to Quick access", lambda: self.add_favorites([pane.current_dir()]))
        m.addSeparator()
        m.addAction(self.icons.glyph("gear", 16), "Options…", self.open_settings)

    # ------------------------------------------------------------------ modos: Explorador / VFX Library
    def mode(self):
        return "library" if self.center_stack.currentIndex() == 1 else "explorer"

    def set_mode(self, mode):
        lib = mode == "library"
        if self.modebar.currentIndex() != (1 if lib else 0):
            self.modebar.blockSignals(True)
            self.modebar.setCurrentIndex(1 if lib else 0)
            self.modebar.blockSignals(False)
        self.center_stack.setCurrentIndex(1 if lib else 0)
        self.sidetabs.setCurrentIndex(1 if lib else 0)
        self._sidetab_changed(1 if lib else 0)
        self.act_dual.setEnabled(not lib)
        self._place_headers()
        self.apply_pipeline_location()
        if lib:
            roots = self.libpane.root_lock()
            if not self.libpane.tabs and roots:
                self.libpane.add_tab(roots[0])
            self.set_active(self.libpane)
            self.libpane.view().setFocus()
            if not self.cfg["library_roots"]:
                self.libpage.viewer.show_message("Choose your VFX library folder with the ＋ next to the "
                                                 "«VFX LIBRARY» tab in the left pane (videos, sequences, "
                                                 "images, HDRIs…).")
        else:
            self.libpage.viewer.pause()
            self.set_active(self.explorer_active)
        self.cfg["mode"] = mode
        self.save_soon()

    def open_library(self, path):
        if not path:
            self.libside.add_root()
            return
        if not self.libpane.allowed(path):
            self.add_library_root(path)
        self.set_mode("library")
        if not self.libpane.tabs:
            self.libpane.add_tab(path)
        else:
            self.libpane.navigate(path)

    def add_library_root(self, path):
        roots = [r for r in (self.cfg["library_roots"] or []) if r]
        path = os.path.normpath(path)
        if path not in roots:
            roots.append(path)
        self.cfg["library_roots"] = roots
        self.cfg.save()
        self.libside.reload()

    def open_in_explorer(self, path, new_tab=False):
        if self.mode() != "explorer":
            self.set_mode("explorer")
        self.explorer_active.navigate(path, new_tab=new_tab)

    # ------------------------------------------------------------------ colores / tamaños / opciones
    def dir_color(self, path):
        return self.colors.dir_color(path)

    def entry_color(self, e):
        return self.colors.dir_color(e.path) if e.kind == "dir" else self.lib.color(e.key())

    def apply_pipeline_location(self):
        loc = self.cfg["pipeline_location"] or "center"
        if loc == "top":
            loc = "center"
        if self.mode() == "library":
            self.ctx_stack.setCurrentIndex(1)
        else:
            self.ctx_stack.setCurrentIndex(0 if loc == "center" else 2)
        self.side_boxes["pipeline"].setVisible(loc == "sidebar")

    def clear_pills(self):
        self.tagbar.clear()

    def drag_finished(self):
        QTimer.singleShot(0, self.end_peek)

    def apply_features(self):
        on = bool(self.cfg["library_features"])
        self.side_boxes["colls"].setVisible(on)
        self.side_boxes["tags"].setVisible(on)
        for p in self.all_panes:
            p.apply_features()

    def request_dir_sizes(self, pane, entries):
        if not self.cfg["folder_sizes"]:
            return
        for e in entries:
            if e.kind == "dir":
                size = self.dirsizes.get(e.path)
                if size is None:
                    self.dirsizes.request(e.path)
                else:
                    e.size = size

    def _dir_size_ready(self, path, size):
        for p in self.all_panes:
            if p.model.dir_size_ready(path, size):
                p.grid.viewport().update()

    def start_inline_rename(self, pane, view=None):
        view = view or pane.view()
        ix = view.currentIndex()
        if ix.isValid():
            view.edit(ix.sibling(ix.row(), 0))

    def rename_inline(self, e, text):
        """Renombrado en el lugar (F2). Para secuencias renombra todos los frames."""
        try:
            if e.kind == "seq":
                pairs = fileops.seq_rename_from_text(e, text)
            else:
                pairs = fileops.rename_plan(e, text)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                fileops.apply_renames(pairs)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"Could not rename:\n{ex}")
            return False
        if e.kind == "seq":
            head = fileops.SEQ_TOKEN_RE.match(text)
            from .core import split_frame
            sp = split_frame(os.path.basename(pairs[0][1]))
            nd = Entry(kind="seq", dirpath=e.dirpath, name="", path=pairs[0][1], ext=e.ext,
                       head=sp[0] if sp else e.head, pad=e.pad)
            nd.files = [os.path.basename(b) for _, b in pairs]
            new_name = os.path.basename(pairs[0][1])
        else:
            nd = Entry(kind=e.kind, dirpath=e.dirpath, name=os.path.basename(pairs[0][1]), path=pairs[0][1], ext=e.ext)
            new_name = nd.name
        self.lib.path_moved(e.key(), nd.key(), nd.ref())
        self.colors.invalidate()
        self.save_soon()
        for p in self.all_panes:
            if p.current_dir() and same_path(p.current_dir(), e.dirpath) or p.model.virtual:
                if p is self.active:
                    p.pending_select = new_name
                QTimer.singleShot(0, p.refresh)
        self.status.setText(f"Renamed: {e.name} → {text}")
        return True

    # ------------------------------------------------------------------ paneles
    def set_active(self, pane):
        if pane in self.panes:
            self.explorer_active = pane
        if hasattr(self, "sub_switch"):
            QTimer.singleShot(0, lambda p=pane: self.sync_commandbar(p))
        if pane is not self.active or not pane.property("active"):
            self.active = pane
            for p in self.panes:
                p.set_active(p is pane and self.paneB.isVisible())
            self._location_changed(pane)
            self._sel_changed(pane)
            self._pane_status(pane)

    def other(self, pane):
        if not self.paneB.isVisible() or pane not in self.panes or self.mode() != "explorer":
            return None
        return self.paneB if pane is self.paneA else self.paneA

    def toggle_dual(self, force=None):
        if force is None and self.mode() != "explorer":
            self.set_mode("explorer")
        show = (not self.paneB.isVisible()) if force is None else force
        self.paneB.setVisible(show)
        self.act_dual.setChecked(show)
        if not show and self.active is self.paneB:
            self.set_active(self.paneA)
        for p in self.panes:
            p.set_active(p is self.active and show)
        self._place_headers()
        if show and sum(self.pane_split.sizes()) and min(self.pane_split.sizes()) < 50:
            w = sum(self.pane_split.sizes())
            self.pane_split.setSizes([w // 2, w // 2])
        self.save_soon()

    def close_pane(self, pane):
        """Cerrar la única pestaña de un panel en doble panel cierra ese panel."""
        if pane not in self.panes or not self.paneB.isVisible():
            return
        if pane is self.paneA:
            st = self.paneB.state()
            self.paneA.clear_tabs()
            self.paneA.restore(st, self.paneB.tab_path() or os.path.expanduser("~"))
        self.toggle_dual(False)
        self.set_active(self.paneA)

    def switch_pane(self):
        o = self.other(self.active)
        if o:
            self.set_active(o)
            o.view().setFocus()

    def _location_changed(self, pane):
        if pane is not self.active:
            return
        d = pane.current_dir()
        if pane is self.libpane:
            self.libside.sync(d or "")
            if d:
                self.setWindowTitle(f"{os.path.basename(d.rstrip(chr(92) + '/')) or d} — {APP_NAME} {VERSION}")
            return
        self.tree.set_trace_path(d or "")
        if not d:
            for pb in self.pipebars:
                pb.clear()
        if d:
            ix = self.fs.index(d)
            if ix.isValid():
                self.tree.setCurrentIndex(ix)
                self.tree.scrollTo(ix)
            for pb in self.pipebars:
                pb.sync(d)
            self.setWindowTitle(f"{os.path.basename(d.rstrip(chr(92) + '/')) or d} — {APP_NAME} {VERSION}")

    def _pane_status(self, pane):
        if pane is self.active:
            self.status.setText(pane.status_text)

    def _on_thumb_size(self, v):
        for p in self.all_panes:
            p.set_thumb_size(v)
        self.thumbs.scaled.clear()
        self.cfg["thumb_size"] = v
        self.save_soon()

    def refresh_views(self):
        self.colors.invalidate()
        for p in self.all_panes:
            p.model.refresh_all()
            p.grid.viewport().update()
            p.list.viewport().update()
        self.tree.viewport().update()

    def refresh_dirs(self, dirs):
        keys = {norm_key(d) for d in dirs if d}
        for p in self.all_panes:
            if p.isVisible() or p is self.paneA or p is self.libpane:
                cur = p.current_dir()
                if p.is_virtual() or (cur and norm_key(cur) in keys) or not keys:
                    p.refresh()

    # ------------------------------------------------------------------ info de selección
    def _sel_changed(self, pane):
        if pane is not self.active:
            return
        ents = pane.selected_entries()
        self.info_token += 1
        self._info_entry = None
        if not ents:
            self.preview.clear()
            self.info.setText("")
            self.status_right.setText("")
            return
        if len(ents) > 1:
            tot = sum(e.size for e in ents)
            n_files = sum(len(e.files) if e.kind == "seq" else 1 for e in ents)
            self.preview.clear()
            self.info.setText(f"<b>{len(ents)} items</b><br>{n_files} files · {human_size(tot)}")
            self.status_right.setText(f"{len(ents)} selected · {human_size(tot)}")
            return
        self._show_info(ents[0])

    def _set_preview(self, e):
        pm = self.thumbs.get(e)
        if pm is None and e.kind == "dir":
            pm = self.icons.folder(self.lib.color(e.key()), 120)
        if pm is not None:
            w = max(100, self.preview.width() - 8)
            self.preview.setPixmap(pm.scaled(w, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("<span style='color:#666'>no preview</span>")

    def _show_info(self, e):
        self._info_entry = e
        self._set_preview(e)
        rows = [("Type", e.type_label())]
        if e.kind == "seq":
            rows.append(("Range", f"{e.first} – {e.last}"))
            rows.append(("Frames", f"{len(e.frames)}"))
            if e.missing:
                rows.append(("Missing", f"<span style='color:#ff6b6b'><b>{len(e.missing)}</b>: "
                                       f"{compress_ranges(e.missing)[:600]}</span>"))
            elif "," in compress_ranges(e.frames):
                rows.append(("Ranges", compress_ranges(e.frames)))
        if e.kind != "dir":
            rows.append(("Size", human_size(e.size)))
        rows.append(("Modified", fmt_time(e.mtime)))
        rows.append(("Folder", fwd(e.dirpath)))
        r = self.lib.rating(e.key())
        if r:
            rows.append(("Rating", f"<span style='color:#f5c542'>{'★' * r}</span>"))
        tags = self.lib.tags(e.key())
        if tags:
            rows.append(("Tags", "<span style='color:#8fb3ff'>" + "  ".join("#" + t for t in tags) + "</span>"))
        colls = [n for n, keys in self.lib.collections.items() if e.key() in keys]
        if colls:
            rows.append(("Collections", ", ".join(colls)))
        self._info_base = (
            "<style>td{padding:1px 6px 1px 0; vertical-align:top;} td.k{color:#8b9099; white-space:nowrap;}</style>"
            f"<div style='font-size:10pt; font-weight:bold; color:#eee;'>{e.name}</div><table>"
            + "".join(f"<tr><td class='k'>{k}</td><td>{v}</td></tr>" for k, v in rows))
        self.info.setText(self._info_base + "</table>")
        self.status_right.setText(fwd(e.pattern_path("hash")))
        ffprobe = find_tool(self.cfg["ffmpeg"], "ffprobe")
        self.thumbs.pool.start(InfoTask(self.info_token, e, ffprobe, self.thumbs.index,
                                        bool(self.cfg["sidecar_previews"]), self.info_signals))

    def _thumb_for_info(self, key):
        e = self._info_entry
        if e is not None and self.thumbs.key_for(e) == key:
            self._set_preview(e)

    def _info_ready(self, token, html):
        if token != self.info_token:
            return
        if html:
            self.info.setText(self._info_base + "<tr><td colspan=2><hr></td></tr>" + html + "</table>")

    # ------------------------------------------------------------------ abrir
    def open_entry(self, e, with_player=True):
        player = self.cfg["player"]
        if with_player and player and os.path.isfile(player) and e.cat in ("seq", "video", "image"):
            try:
                subprocess.Popen([player, e.path])
                return
            except Exception as ex:
                self.status.setText(f"Could not open the player: {ex}")
        self.open_default(e.path)

    def open_default(self, path):
        if IS_WIN:
            try:
                os.startfile(path)
            except OSError as ex:
                self.status.setText(str(ex))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def reveal(self, e):
        if IS_WIN:
            subprocess.Popen(f'explorer /select,"{os.path.normpath(e.path)}"')
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(e.dirpath))

    def copy_paths(self, pane, style):
        ents = pane.selected_entries()
        if not ents:
            d = pane.current_dir()
            if d:
                QApplication.clipboard().setText(fwd(d))
            return
        lines = []
        for e in ents:
            if style == "hash":
                lines.append(fwd(e.pattern_path("hash")))
            elif style == "nuke":
                lines.append(f"{fwd(e.pattern_path('printf'))} {e.first}-{e.last}" if e.kind == "seq" else fwd(e.path))
            elif style == "win":
                lines.append(os.path.normpath(e.pattern_path("hash")))
            elif style == "first":
                lines.append(fwd(e.path))
            elif style == "dir":
                lines.append(fwd(e.dirpath if e.kind != "dir" else e.path))
            elif style == "name":
                lines.append(e.name)
        QApplication.clipboard().setText("\n".join(lines))
        self.status.setText(f"Copied: {lines[0]}" + (f"  (+{len(lines) - 1})" if len(lines) > 1 else ""))

    # ------------------------------------------------------------------ operaciones de archivo
    def _ask(self, title, text, buttons, default=None):
        mb = QMessageBox(self)
        mb.setWindowTitle(title)
        mb.setText(text)
        btns = {}
        for label, role in buttons:
            btns[label] = mb.addButton(label, role)
        if default:
            mb.setDefaultButton(btns[default])
        mb.exec()
        for label, b in btns.items():
            if mb.clickedButton() is b:
                return label
        return None

    def op_clip(self, pane, cut=False):
        ents = pane.selected_entries()
        if not ents:
            return
        paths = [p for e in ents for p in e.all_paths()]
        QApplication.clipboard().setMimeData(fileops.make_clip_mime(paths, cut))
        self.clip_entries = ents
        n = len(ents)
        self.status.setText(f"{'Cut' if cut else 'Copied'}: {n} item(s) — Ctrl+V to paste"
                            f" (also in Windows Explorer)")

    def op_paste(self, pane, target=None):
        target = target or pane.current_dir()
        if not target:
            return
        paths, cut = fileops.read_clip_mime(QApplication.clipboard().mimeData())
        if not paths:
            self.status.setText("No files on the clipboard")
            return
        ents = self.clip_entries if self.clip_entries and \
            {norm_key(p) for e in self.clip_entries for p in e.all_paths()} == {norm_key(p) for p in paths} else None
        self.start_transfer("move" if cut else "copy", paths, target, ents)
        if cut:
            QApplication.clipboard().clear()
            self.clip_entries = []

    def handle_drop(self, pane, paths, target, mods, pos):
        if all(same_path(os.path.dirname(p), target) for p in paths):
            return
        from_lib = all(self.libpane.allowed(p) for p in paths) and not self.libpane.allowed(target)
        if mods & Qt.ShiftModifier:
            op = "move"
        elif mods & Qt.ControlModifier or from_lib:
            op = "copy"               # de la VFX Library a una carpeta: siempre copia, sin preguntar
        else:
            m = QMenu(self)
            a_copy = m.addAction(f"Copy here  ({len(paths)} file(s))")
            a_move = m.addAction("Move here")
            m.addSeparator()
            m.addAction("Cancel")
            a = m.exec(pos)
            if a is a_copy:
                op = "copy"
            elif a is a_move:
                op = "move"
            else:
                return
        src_pane = None
        ents = None
        for p in self.all_panes:
            sel = p.selected_entries()
            if sel and {norm_key(x) for e in sel for x in e.all_paths()} == {norm_key(x) for x in paths}:
                ents = sel
                break
        self.start_transfer(op, paths, target, ents)

    def transfer_to_other(self, pane, op):
        o = self.other(pane)
        if not o or not o.current_dir():
            return
        ents = pane.selected_entries()
        if ents:
            self.start_transfer(op, [p for e in ents for p in e.all_paths()], o.current_dir(), ents)

    def start_transfer(self, op, paths, dest, entries=None):
        if self.op_worker is not None:
            QMessageBox.information(self, APP_NAME, "Another operation is already running.")
            return
        err = fileops.validate_transfer(paths, dest, op)
        if err:
            QMessageBox.warning(self, APP_NAME, err)
            return
        conflicts = fileops.plan_conflicts(paths, dest)
        overwrite = False
        if conflicts:
            names = "\n".join(os.path.basename(c) for c in conflicts[:8]) + ("\n…" if len(conflicts) > 8 else "")
            ans = self._ask("Existing files",
                            f"{len(conflicts)} file(s) already exist at the destination:\n\n{names}",
                            [("Replace", QMessageBox.DestructiveRole), ("Skip existing", QMessageBox.AcceptRole),
                             ("Cancel", QMessageBox.RejectRole)], default="Skip existing")
            if ans in (None, "Cancel"):
                return
            overwrite = ans == "Replace"
        verb = "Copying" if op == "copy" else "Moving"
        dlg = QProgressDialog(f"{verb}…", "Cancel", 0, 1000, self)
        dlg.setWindowTitle(f"{verb} a {os.path.basename(dest.rstrip(chr(92) + '/')) or dest}")
        dlg.setMinimumDuration(400)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        w = fileops.FileOpWorker(op, paths, dest, overwrite)
        self.op_worker = w

        def prog(done, total, name):
            dlg.setValue(int(1000 * min(1.0, done / max(1, total))))
            dlg.setLabelText(f"{verb}  {name}\n{human_size(done)} of {human_size(total)}")

        def fin(ok, errors, cancelled):
            dlg.close()
            self.op_worker = None
            if op == "move" and entries:
                for e in entries:
                    nd = Entry(**{**e.__dict__, "dirpath": dest, "path": os.path.join(dest, os.path.basename(e.path)),
                                  "_missing": None})
                    self.lib.path_moved(e.key(), nd.key(), nd.ref())
                self.save_soon()
            srcs = {os.path.dirname(p) for p in paths}
            self.refresh_dirs(srcs | {dest})
            msg = f"{'Copied' if op == 'copy' else 'Moved'} {ok} file(s)"
            if cancelled:
                msg += " — cancelled"
            self.status.setText(msg)
            if errors:
                QMessageBox.warning(self, APP_NAME, f"{len(errors)} error(s):\n\n" + "\n".join(errors[:15]))

        w.progress.connect(prog)
        w.done.connect(fin)
        dlg.canceled.connect(lambda: setattr(w, "cancelled", True))
        w.start()

    def op_trash(self, pane):
        ents = pane.selected_entries()
        if not ents or self.op_worker is not None:
            return
        paths = [p for e in ents for p in e.all_paths()]
        net = any(fileops.is_network_path(p) for p in paths[:1])
        n_files = len(paths)
        desc = ents[0].name if len(ents) == 1 else f"{len(ents)} items"
        text = f"Send to the Recycle Bin: {desc}?" + (f"\n({n_files} files)" if n_files > 1 else "")
        if net:
            text += ("\n\n⚠ It's on a network drive: Windows deletes it PERMANENTLY "
                     "(unless the NAS recycle bin is enabled for that shared folder).")
        ans = self._ask("Send to Recycle Bin", text,
                        [("Delete" if net else "Send to Recycle Bin", QMessageBox.DestructiveRole),
                         ("Cancel", QMessageBox.RejectRole)], default="Cancel")
        if ans in (None, "Cancel"):
            return
        w = fileops.TrashWorker(paths)
        self.op_worker = w
        self.status.setText("Deleting…")

        def fin(errors):
            self.op_worker = None
            self.refresh_dirs({e.dirpath for e in ents})
            self.status.setText(f"{desc}: sent to the Recycle Bin" if not errors else "Delete error")
            if errors:
                QMessageBox.warning(self, APP_NAME, "\n".join(errors[:10]))
        w.done.connect(fin)
        w.start()

    def op_rename(self, pane):
        ents = pane.selected_entries()
        if len(ents) != 1:
            return
        e = ents[0]
        dlg = RenameDialog(e, self)
        if not dlg.exec():
            return
        name, start, sep = dlg.values()
        try:
            pairs = fileops.rename_plan(e, name, start_frame=start, sep=sep)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                fileops.apply_renames(pairs)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"Could not rename:\n{ex}")
            return
        new_name = os.path.basename(pairs[0][1])
        if e.kind == "seq":
            nd = Entry(kind="seq", dirpath=e.dirpath, name="", path=pairs[0][1], ext=e.ext,
                       head=f"{name}{sep}", pad=e.pad)
            nd.name = f"{nd.head}{nd.hashes()}{e.ext_real}"
            self.lib.path_moved(e.key(), nd.key(), nd.ref())
            new_name = nd.name
        else:
            nd = Entry(kind=e.kind, dirpath=e.dirpath, name=new_name, path=pairs[0][1], ext=e.ext)
            self.lib.path_moved(e.key(), nd.key(), nd.ref())
        self.save_soon()
        pane.pending_select = new_name
        pane.refresh()
        o = self.other(pane)
        if o and same_path(o.current_dir(), pane.current_dir()):
            o.refresh()

    def op_new_folder(self, pane):
        d = pane.current_dir()
        if not d:
            return
        name, ok = QInputDialog.getText(self, "New folder", "Name:", text="New folder")
        if not ok or not name.strip():
            return
        try:
            fileops.new_folder(d, name)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        pane.pending_select = name.strip()
        pane.refresh()

    # ------------------------------------------------------------------ librería: color / rating / tags / colecciones
    def _targets(self, ents):
        return [(e.key(), e.ref()) for e in ents]

    def _lib_changed(self):
        self.save_soon()
        self.refresh_views()
        self._reload_sidebar()
        if self._info_entry is not None:
            self._show_info(self._info_entry)

    def set_color(self, targets, color):
        self.lib.set_color(targets, color)
        self.colors.invalidate()
        self._lib_changed()

    def op_rating(self, pane, n):
        if not self.cfg["library_features"]:
            return
        ents = pane.selected_entries()
        if ents:
            self.lib.set_rating(self._targets(ents), n)
            self._lib_changed()
            self.status.setText(f"Rating {'★' * n if n else 'removed'} · {len(ents)} item(s)")

    def op_tags(self, pane):
        if not self.cfg["library_features"]:
            return
        ents = pane.selected_entries()
        if not ents:
            return
        sets = [set(t.lower() for t in self.lib.tags(e.key())) for e in ents]
        common_low = set.intersection(*sets) if sets else set()
        common = [t for t in self.lib.tags(ents[0].key()) if t.lower() in common_low]
        dlg = TagDialog(common, self.lib.all_tags(), len(ents), self)
        if dlg.exec():
            self.lib.edit_tags(self._targets(ents), dlg.tags(), common)
            self._lib_changed()

    def add_to_collection(self, ents, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, "New collection", "Collection name:")
            if not ok or not name.strip():
                return
            name = name.strip()
        self.lib.add_to_collection(name, self._targets(ents))
        self._lib_changed()
        self.status.setText(f"{len(ents)} item(s) added to «{name}»")

    def refs_for(self, kind, name):
        if kind == "tag":
            return self.lib.refs_with_tag(name)
        if kind == "collection":
            return self.lib.refs_in_collection(name)
        if kind == "rating":
            return self.lib.refs_with_rating(int(name))
        return []

    def open_collection(self, name, new_tab=False):
        self.active.show_virtual(f"Collection: {name}", "collection", name, new_tab)

    def open_tag(self, tag, new_tab=False):
        if tag.startswith("★"):
            n = len(tag)
            self.active.show_virtual(f"Rating ≥ {'★' * n}", "rating", n, new_tab)
        else:
            self.active.show_virtual(f"#{tag}", "tag", tag, new_tab)

    # ------------------------------------------------------------------ sidebar
    def _reload_sidebar(self):
        show_hidden = bool(self.cfg["show_hidden_quick"])
        for w, key in ((self.favs, "favorites"), (self.lib_favs, "lib_favorites")):
            w.clear()
            if w is self.favs:
                hidden = set(self.cfg["hidden_sys"] or [])
                n_sys = 0
                for kind, label in self.SYS_FOLDERS:
                    sp = self._sys_path(kind)
                    if not sp or (kind in hidden and not show_hidden):
                        continue
                    it = QListWidgetItem(self.icons.sysfolder(kind, 18), label)
                    it.setData(Qt.UserRole, sp)
                    it.setData(Qt.UserRole + 1, kind)
                    it.setData(Qt.UserRole + 3, kind in hidden)
                    it.setToolTip(sp)
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    w.addItem(it)
                    n_sys += 1
                if n_sys and self.cfg[key]:
                    sep = QListWidgetItem("")
                    sep.setData(Qt.UserRole + 2, True)
                    sep.setFlags(Qt.NoItemFlags)
                    w.addItem(sep)
            for p in self.cfg[key] or []:
                name = os.path.basename(p.rstrip("\\/")) or p
                it = QListWidgetItem(self.icons.folder_icon(self.dir_color(p), 18), name)
                it.setData(Qt.UserRole, p)
                it.setToolTip(p + "\nPinned · drag to reorder")
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                w.addItem(it)
        if not self.cfg["lib_favorites"]:
            it = QListWidgetItem("Drag a folder here to pin it")
            it.setForeground(Qt.gray)
            it.setFlags(Qt.NoItemFlags)
            self.lib_favs.addItem(it)
        self.colls.clear()
        for name, keys in self.lib.collections.items():
            it = QListWidgetItem(self.icons.glyph("grid", 16, "#4cc2ff"), f"{name}  ({len(keys)})")
            it.setData(Qt.UserRole, name)
            self.colls.addItem(it)
        self.tagl.clear()
        rated = sum(1 for v in self.lib.items.values() if v.get("rating"))
        if rated:
            for n in (5, 4, 3):
                c = sum(1 for v in self.lib.items.values() if int(v.get("rating", 0)) >= n)
                if c:
                    it = QListWidgetItem(f"{'★' * n}  ({c})")
                    it.setForeground(Qt.yellow)
                    it.setData(Qt.UserRole, "★" * n)
                    self.tagl.addItem(it)
        for t, n in self.lib.all_tags():
            it = QListWidgetItem(f"#{t}  ({n})")
            it.setData(Qt.UserRole, t)
            self.tagl.addItem(it)
        self.tree.viewport().update()
        if hasattr(self, "libside"):
            self.libside.reload()

    def add_favorites(self, paths, lib=None):
        """Acceso rápido: cada modo tiene el suyo (Carpetas / VFX Library)."""
        if lib is None:
            lib = self.mode() == "library"
        key = "lib_favorites" if lib else "favorites"
        favs = list(self.cfg[key] or [])
        for p in paths:
            if p and norm_key(p) not in {norm_key(x) for x in favs}:
                favs.append(os.path.normpath(p))
        self.cfg[key] = favs
        self.cfg.save()
        self._reload_sidebar()
        self.status.setText(f"Pinned to Quick access of {'VFX Library' if lib else 'File Explorer'}")

    def _favs_reordered(self, *_):
        for w, key in ((self.favs, "favorites"), (self.lib_favs, "lib_favorites")):
            vals = [w.item(i).data(Qt.UserRole) for i in range(w.count())
                    if not w.item(i).data(Qt.UserRole + 1) and not w.item(i).data(Qt.UserRole + 2)]
            vals = [v for v in vals if v]
            if vals or key == "favorites":
                self.cfg[key] = vals
        self.cfg.save()

    def _lib_favs_menu(self, w, pos):
        it = w.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        p = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Open", lambda: self.open_library(p))
        m.addAction("Open in new tab", lambda: (self.set_mode("library"), self.libpane.add_tab(p)))
        m.addAction("Open in File Explorer", lambda: self.open_in_explorer(p, new_tab=True))
        self._color_menu(m, [dir_target(p)])
        m.addSeparator()

        def remove():
            self.cfg["lib_favorites"] = [x for x in self.cfg["lib_favorites"] if norm_key(x) != norm_key(p)]
            self.cfg.save()
            self._reload_sidebar()
        m.addAction("Unpin from Quick access", remove)
        m.exec(w.viewport().mapToGlobal(pos))

    def _color_menu(self, menu, targets):
        cm = menu.addMenu("Color label")
        for name, hexc in TAG_COLORS:
            cm.addAction(self.icons.swatch(hexc), name, lambda h=hexc: self.set_color(targets, h))
        cm.addSeparator()
        cm.addAction("Remove color", lambda: self.set_color(targets, None))

    def _favs_menu(self, w, pos):
        it = w.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        p = it.data(Qt.UserRole)
        sysk = it.data(Qt.UserRole + 1)
        m = QMenu(self)
        m.addAction("Open", lambda: self.open_in_explorer(p))
        m.addAction("Open in new tab", lambda: self.open_in_explorer(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Open in the other pane", lambda: (self.set_mode("explorer"),
                                                           self.other(self.explorer_active).navigate(p)))
        self._color_menu(m, [dir_target(p)])
        m.addSeparator()

        def remove():
            self.cfg["favorites"] = [x for x in self.cfg["favorites"] if norm_key(x) != norm_key(p)]
            self.cfg.save()
            self._reload_sidebar()
        if sysk:
            hid = sysk in (self.cfg["hidden_sys"] or [])
            m.addAction(self.icons.eye(16, on=hid), "Show" if hid else "Hide", lambda: self._toggle_sys(sysk))
        else:
            m.addAction("Unpin from Quick access", remove)
        m.exec(w.viewport().mapToGlobal(pos))

    def _colls_menu(self, w, pos):
        it = w.itemAt(pos)
        m = QMenu(self)
        if it:
            name = it.data(Qt.UserRole)
            m.addAction("Open", lambda: self.open_collection(name))
            m.addAction("Open in new tab", lambda: self.open_collection(name, new_tab=True))

            def rename():
                new, ok = QInputDialog.getText(self, "Rename collection", "Name:", text=name)
                if ok and new.strip():
                    self.lib.rename_collection(name, new.strip())
                    self._lib_changed()

            def delete():
                if self._ask("Delete collection", f"Delete the collection «{name}»? (files are not touched)",
                             [("Delete", QMessageBox.DestructiveRole), ("Cancel", QMessageBox.RejectRole)],
                             default="Cancel") == "Delete":
                    self.lib.delete_collection(name)
                    self._lib_changed()
            m.addAction("Rename…", rename)
            m.addAction("Delete collection", delete)
        else:
            m.addAction("Select files and right-click › Add to collection").setEnabled(False)
        m.exec(w.viewport().mapToGlobal(pos))

    def _tags_menu(self, w, pos):
        it = w.itemAt(pos)
        if not it:
            return
        tag = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("View", lambda: self.open_tag(tag))
        m.addAction("View in new tab", lambda: self.open_tag(tag, new_tab=True))
        if not tag.startswith("★"):
            def rename():
                new, ok = QInputDialog.getText(self, "Rename tag", "New name:", text=tag)
                if ok and new.strip():
                    self.lib.rename_tag(tag, new.strip().lstrip("#"))
                    self._lib_changed()
            m.addAction("Rename tag…", rename)
        m.exec(w.viewport().mapToGlobal(pos))

    def _tree_menu(self, pos):
        ix = self.tree.indexAt(pos)
        if not ix.isValid():
            return
        p = self.fs.filePath(ix)
        m = QMenu(self)
        m.addAction("Open", lambda: self.open_in_explorer(p))
        if not ix.parent().isValid():          # disco: se puede ocultar del árbol
            hid = norm_key(p) in {norm_key(x) for x in (self.cfg["hidden_drives"] or [])}
            m.addAction(self.icons.eye(16, on=hid), "Show drive" if hid else "Hide drive",
                        lambda: self._toggle_drive(p))
            m.addSeparator()
        m.addAction("Open in new tab", lambda: self.open_in_explorer(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Open in the other pane", lambda: (self.set_mode("explorer"),
                                                           self.other(self.explorer_active).navigate(p)))
        m.addAction("Pin to Quick access", lambda: self.add_favorites([p], lib=False))
        if self.libpane.allowed(p):
            m.addAction("View in VFX Library", lambda: self.open_library(p))
        else:
            m.addAction("Add to the VFX Library", lambda: self.open_library(p))
        self._color_menu(m, [dir_target(p)])
        m.addAction("Open in Windows Explorer", lambda: self.open_default(p))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ menú contextual de ítems
    def _toggle_row_numbers(self):
        self.cfg["list_row_numbers"] = not self.cfg["list_row_numbers"]
        self.cfg.save()
        for p in self.all_panes:
            p.list.apply_numbers()

    def background_menu(self, pane, view, pos):
        """Clic derecho en el fondo, como en Windows 11: View, Sort by, Group by, Paste, New, Properties…"""
        ic = self.icons
        m = QMenu(self)
        cur = pane.current_dir()
        self._fill_view_menu(m.addMenu(ic.glyph("grid", 16, ACCENT), "View"), full=False)
        self._fill_sort_menu(m.addMenu(ic.glyph("sort", 16, ACCENT), "Sort by"), with_group=False)
        self._fill_group_menu(m.addMenu(ic.glyph("group", 16, ACCENT), "Group by"))
        m.addSeparator()
        m.addAction(ic.glyph("reload", 16), "Refresh\tF5", pane.refresh)
        clip_paths, _ = fileops.read_clip_mime(QApplication.clipboard().mimeData())
        if cur:
            a = m.addAction(ic.glyph("paste", 16), f"Paste ({len(clip_paths)} file(s))\tCtrl+V" if clip_paths
                            else "Paste\tCtrl+V", lambda: self.op_paste(pane))
            a.setEnabled(bool(clip_paths))
            nm = m.addMenu(ic.new_icon(16), "New")
            nm.addAction(ic.glyph("newfolder", 16), "Folder\tCtrl+Shift+N", lambda: self.op_new_folder(pane))
            nm.addAction(ic.glyph("plus", 16), "Tab\tCtrl+T", pane.new_tab)
            m.addSeparator()
            m.addAction(ic.glyph("pin", 16), "Pin this folder to Quick access", lambda: self.add_favorites([cur]))
            if self.mode() == "explorer":
                m.addAction(ic.glyph("library", 16, "#4cc2ff"),
                            "View in VFX Library" if self.libpane.allowed(cur) else "Add this folder to the VFX Library",
                            lambda: self.open_library(cur))
            m.addAction(ic.glyph("copy", 16), "Copy folder path", lambda: QApplication.clipboard().setText(cur))
            m.addAction(ic.glyph("folder", 16), "Open in Windows Explorer", lambda: self.open_default(cur))
            if IS_WIN:
                m.addSeparator()
                m.addAction(ic.glyph("details", 16), "Properties\tAlt+Enter", lambda: self.show_properties(cur))
        m.exec(view.viewport().mapToGlobal(pos))

    def show_properties(self, path):
        """Abre la ventana de Propiedades de Windows."""
        try:
            import ctypes
            from ctypes import wintypes

            class SHELLEXECUTEINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                            ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                            ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
            sei = SHELLEXECUTEINFO()
            sei.cbSize = ctypes.sizeof(sei)
            sei.fMask = 0x0000000C        # SEE_MASK_INVOKEIDLIST
            sei.lpVerb = "properties"
            sei.lpFile = os.path.normpath(path)
            sei.nShow = 1
            ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        except Exception as ex:
            self.status.setText(f"Could not open Properties: {ex}")

    def item_menu(self, pane, view, pos):
        self.set_active(pane)
        ix = view.indexAt(pos)
        from PySide6.QtCore import QModelIndex
        from .models import ROLE_ENTRY
        if ix.isValid() and ix.data(ROLE_ENTRY) is not None and ix.data(ROLE_ENTRY).kind == "header":
            ix = QModelIndex()
        if ix.isValid() and not view.selectionModel().isSelected(ix):
            view.setCurrentIndex(ix)
        if not ix.isValid():
            view.clearSelection()
            if not pane.is_virtual() or pane.current_dir():
                self.background_menu(pane, view, pos)
                return
        ents = pane.selected_entries()
        m = QMenu(self)
        cur = pane.current_dir()
        if ents and all(e.kind == "drive" for e in ents):
            e = ents[0]
            m.addAction("Open", lambda: pane.navigate(e.path))
            m.addAction("Open in new tab", lambda: pane.add_tab(e.path, activate=False))
            m.addAction("Pin to Quick access", lambda: self.add_favorites([x.path for x in ents]))
            m.addAction("Copy path", lambda: QApplication.clipboard().setText(getattr(e, "unc", "") or e.path))
            m.addSeparator()
            m.addAction("Refresh\tF5", pane.refresh)
            m.exec(view.viewport().mapToGlobal(pos))
            return
        other = self.other(pane)
        clip_paths, _ = fileops.read_clip_mime(QApplication.clipboard().mimeData())
        if ents:
            e = ents[0]
            if e.kind == "dir":
                m.addAction("Open", lambda: pane.navigate(e.path))
                m.addAction("Open in new tab", lambda: pane.add_tab(e.path, activate=False))
                if other:
                    m.addAction("Open in the other pane", lambda: other.navigate(e.path))
            else:
                if self.cfg["player"]:
                    m.addAction(f"Open in {os.path.splitext(os.path.basename(self.cfg['player']))[0]}",
                                lambda: self.open_entry(e))
                m.addAction("Open with default app", lambda: self.open_entry(e, with_player=False))
            if pane.is_virtual() or pane.model.virtual:
                m.addAction("Go to containing folder",
                            lambda: pane.navigate(e.dirpath, select=e.name))
            m.addAction("Show in Windows Explorer", lambda: self.reveal(e))
            m.addSeparator()
            m.addAction("Cut\tCtrl+X", lambda: self.op_clip(pane, cut=True))
            m.addAction("Copy\tCtrl+C", lambda: self.op_clip(pane, cut=False))
            if clip_paths and e.kind == "dir" and len(ents) == 1:
                m.addAction("Paste into folder", lambda: self.op_paste(pane, target=e.path))
            if other and other.current_dir():
                m.addAction("Copy to the other pane", lambda: self.transfer_to_other(pane, "copy"))
                m.addAction("Move to the other pane", lambda: self.transfer_to_other(pane, "move"))
            if len(ents) == 1:
                m.addAction("Rename\tF2", lambda: self.start_inline_rename(pane, view))
                if e.kind == "seq":
                    m.addAction("Renumber sequence…", lambda: self.op_rename(pane))
            m.addAction("Send to Recycle Bin\tDel", lambda: self.op_trash(pane))
            m.addSeparator()
            cp = m.addMenu("Copy path")
            cp.addAction("Path  (plate.####.exr)\tCtrl+Shift+C", lambda: self.copy_paths(pane, "hash"))
            cp.addAction("Nuke path  (plate.%04d.exr 1001-1100)\tCtrl+Alt+C", lambda: self.copy_paths(pane, "nuke"))
            cp.addAction("Windows path  (with \\)", lambda: self.copy_paths(pane, "win"))
            cp.addAction("First frame", lambda: self.copy_paths(pane, "first"))
            cp.addAction("Folder", lambda: self.copy_paths(pane, "dir"))
            cp.addAction("Name only", lambda: self.copy_paths(pane, "name"))
            m.addSeparator()
            targets = self._targets(ents)
            self._color_menu(m, targets)
        if ents and self.cfg["library_features"]:
            rm = m.addMenu("Rating")
            for n in range(5, 0, -1):
                rm.addAction("★" * n + f"\tCtrl+{n}", lambda n=n: self.op_rating(pane, n))
            rm.addAction("No rating\tCtrl+0", lambda: self.op_rating(pane, 0))
            m.addAction("Tags…\tCtrl+E", lambda: self.op_tags(pane))
            cm = m.addMenu("Add to collection")
            for name in self.lib.collections:
                cm.addAction(name, lambda n=name: self.add_to_collection(ents, n))
            if self.lib.collections:
                cm.addSeparator()
            cm.addAction("New collection…", lambda: self.add_to_collection(ents))
        if ents:
            vinfo = pane.virtual_info()
            if vinfo and vinfo["kind"] == "collection":
                m.addAction("Remove from collection", lambda: (
                    self.lib.remove_from_collection(vinfo["name"], [x.key() for x in ents]),
                    self._lib_changed(), pane.refresh()))
            dirs = [x for x in ents if x.kind == "dir"]
            if dirs and self.mode() == "explorer":
                if self.libpane.allowed(dirs[0].path):
                    m.addAction("View in VFX Library", lambda: self.open_library(dirs[0].path))
                else:
                    m.addAction("Add to the VFX Library", lambda: self.open_library(dirs[0].path))
            if dirs:
                m.addAction("Pin to Quick access", lambda: self.add_favorites([d.path for d in dirs]))
            m.addSeparator()
        if cur:
            if clip_paths:
                m.addAction(f"Paste ({len(clip_paths)} file(s))\tCtrl+V", lambda: self.op_paste(pane))
            m.addAction("New folder…\tCtrl+Shift+N", lambda: self.op_new_folder(pane))
            m.addAction("Pin this folder to Quick access", lambda: self.add_favorites([cur]))
        if cur and self.mode() == "explorer":
            m.addAction("View in VFX Library" if self.libpane.allowed(cur) else "Add this folder to the VFX Library",
                        lambda: self.open_library(cur))
        m.addAction("Refresh\tF5", pane.refresh)
        m.exec(view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ configuración
    def open_settings(self, page=None):
        d = SettingsDialog(self, self)
        if page:
            tw = d.findChild(QTabWidget)
            for i in range(tw.count()):
                if tw.tabText(i) == page:
                    tw.setCurrentIndex(i)
        if d.exec():
            ch = d.apply()
            self.thumbs.reload_settings()
            if ch["thumbs"]:
                self.thumbs.forget()
            if ch["pipeline"]:
                self.pipeline.reload()
                for pb in self.pipebars:
                    pb.reload()
            self.colors.reload()
            self.icons.set_default_folder(self.cfg["folder_color"] or "yellow")
            self._reload_sidebar()
            self.libside.tree.viewport().update()
            if not self.cfg["folder_sizes"]:
                self.dirsizes.clear()
            self.apply_features()
            self.apply_pipeline_location()
            self.refresh_views()
            if ch["listing"]:
                for p in self.all_panes:
                    p.refresh()


class _TreeColorDelegate(QStyledItemDelegate):
    """Pinta el ícono de carpeta con su color en el árbol."""

    def __init__(self, app, view):
        super().__init__(view)
        self.app = app

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.parent().isValid() and option.features & QStyleOptionViewItem.HasDecoration:
            c = self.app.lib.color(norm_key(self.app.fs.filePath(index)))
            option.icon = self.app.icons.folder_icon(c, 18)
            if option.decorationSize.width() < 8:
                option.decorationSize = QSize(18, 18)
