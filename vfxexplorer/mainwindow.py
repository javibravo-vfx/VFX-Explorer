# -*- coding: utf-8 -*-
"""Ventana principal: barra de pipeline, sidebar (favoritos, colecciones, tags, carpetas), paneles e info."""

import os
import sys
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QByteArray, QDir, QUrl, QEvent, Signal, QRectF, QPointF, QObject
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices, QCursor, QAction, QPixmap
from PySide6.QtWidgets import (QLineEdit, QPlainTextEdit, QTreeWidgetItem, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView,
                               QListWidget, QListWidgetItem, QComboBox, QSlider, QToolBar, QLabel, QMenu,
                               QFileSystemModel, QAbstractItemView, QToolButton, QScrollArea, QFrame,
                               QMessageBox, QInputDialog, QProgressDialog, QStyledItemDelegate, QSizePolicy, QStyleOptionViewItem,
                               QTabBar, QStackedWidget, QTabWidget)

from . import APP_NAME, VERSION
from .core import (safe_isdir, reachable, net_root, net_offline_roots, AUDIO_EXTS, Config, IS_WIN, data_dir, norm_key, fwd, human_size, fmt_time, compress_ranges, find_tool,
                   same_path, Entry, FILTERS)
from .library import Library, dir_target
from .pipeline import Pipeline
from .imaging import ThumbManager, InfoTask, Signals, init_formats
from .widgets import Icons, TAG_COLORS, TagDialog, RenameDialog, SettingsDialog, ACCENT
from .pane import FilePane
from .colors import ColorEngine, COLOR_MODES, DEFAULT_NAME_RULES
from .tree import FolderTree, MiniTree
from .dirsize import DirSizeManager
from .library_ui import LibraryPage, LibrarySidebar
from .pipebar import PipelineBar
from .quicklist import QuickList
from .tagbar import QuickTagBar
from . import fileops


# ----------------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------------

DETAILS_MIN_W = 300        # ancho mínimo del panel de detalles (como el de Windows)


def soft(t):
    """Deja cortar rutas y nombres largos en el panel de detalles (espacio de ancho cero tras / \\ _ . -)."""
    import re as _re
    return _re.sub(r"([/\\_.\-])", "\\1\u200b", str(t))


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
    """Interruptor de subcarpetas apagado · 1 nivel · toda la rama."""
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
        from .meta import MetaManager
        self.meta = MetaManager(self)
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
        self._ready = False             # hasta terminar de abrir no se guardan vistas por carpeta
        self._sys_view_defaults()
        self._build()
        self._restore(start_path)
        self._ready = True
        for p in self.all_panes:
            p._apply_folder_view()
        from .hoverbox import HoverBox
        self.hoverbox = HoverBox(self)
        for p in self.all_panes:
            self.hoverbox.attach(p.grid)
            self.hoverbox.attach(p.list)
        # red: lo que estaba caído al abrir (NAS apagado) se vuelve a chequear solo y aparece cuando responde
        self._net_known_bad = set(net_offline_roots())
        self.net_timer = QTimer(self, interval=4000, timeout=self._net_watch)
        self.net_timer.start()
        self._start_freeze_watch()

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
        self.modebar.addTab(ic.glyph("folder", 16, "#ffcf48"), "File Explorer")
        self.modebar.addTab(ic.glyph("library", 16, "#9d9d9d"), "VFX Library")
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
        self.ctx_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)   # no fija el ancho mínimo de la ventana
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
        self.m_sort = QMenu(self)
        self.m_sort.aboutToShow.connect(self._fill_sort_menu)
        self.b_sort = ChevronButton(ic.glyph("sort", 18, ACCENT), "Sort", self.m_sort, "Sort and group")
        cll.addWidget(self.b_sort)
        self.m_view = QMenu(self)
        self.m_view.aboutToShow.connect(self._fill_view_menu)
        self.b_view = ChevronButton(ic.glyph("list", 18), "View", self.m_view, "View: icon size, details, hidden items…")
        cll.addWidget(self.b_view)
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
        self.chev_buttons = (self.b_new, self.b_sort, self.b_view)

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
        self.act_dual = QAction(ic.glyph("dual", 18, ACCENT), "", self)
        self.act_dual.triggered.connect(lambda: self.toggle_dual(orient="h"))
        self.act_dual.setCheckable(True)
        self.act_dual.setToolTip("Dual pane, side by side (F9) · F6 switches pane")
        self.act_dual_v = QAction(ic.glyph("dualv", 18, ACCENT), "", self)
        self.act_dual_v.triggered.connect(lambda: self.toggle_dual(orient="v"))
        self.act_dual_v.setCheckable(True)
        self.act_dual_v.setToolTip("Dual pane, one above the other (F10) · F6 switches pane")
        self.act_cfilter = QAction(ic.glyph("colorfilter", 18), "", self)
        self.act_cfilter.setCheckable(True)
        self.act_cfilter.setChecked(bool(self.cfg["color_filters_on"]))
        self.act_cfilter.toggled.connect(self._toggle_color_filters)
        self.act_cfilter.setToolTip("Color filters: paint file names by type or pattern (e.g. .exe in red)\n"
                                    "Set the rules in ⚙ › Colors")
        self.act_folderpdf = QAction(ic.glyph("doc", 18, ACCENT), "", self)
        self.act_folderpdf.setCheckable(True)
        self.act_folderpdf.setChecked(bool(self.cfg["lib_folder_pdf"]))
        self.act_folderpdf.toggled.connect(self._toggle_folder_pdf)
        self.act_folderpdf.setToolTip("Folder PDF / cover (VFX Library): the PDF of the folder you are in — or of a "
                                      "parent folder — stays in Details\n(e.g. the main PDF of a 3D model "
                                      "collection); without a PDF, a cover image of the folder")
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
        for a in (self.act_folderpdf, self.act_cfilter, self.act_dual, self.act_dual_v, self.act_details, a_set):
            b = tool(a)
            crr.addWidget(b)
            if a is self.act_folderpdf:
                self.b_folderpdf = b
                b.setVisible(self.cfg["mode"] == "library")
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
            self.hook_list_keys(w, click_fn)
            w.model().rowsMoved.connect(self._favs_reordered)
            w.dropped.connect(lambda dirs, lib=lib: self._quick_dropped(dirs, lib))
        self.colls = self._mk_list(self._colls_menu, lambda it: self.open_collection(it.data(Qt.UserRole)))
        self.tagl = self._mk_list(self._tags_menu, lambda it: self.open_tag(it.data(Qt.UserRole)))

        # árbol de File Explorer con This PC como raíz: completo o Mini tree (solo lo visitado)
        self.tree = FolderTree(self)
        self.minitree = MiniTree(self)
        for t in (self.tree, self.minitree):
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            t.itemClicked.connect(lambda it, c: it.data(0, Qt.UserRole) and
                                  self.open_in_explorer(it.data(0, Qt.UserRole)))
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.customContextMenuRequested.connect(lambda pos, t=t: self._tree_menu(t, pos))
        for t in (self.tree, self.minitree):
            self.hook_tree_keys(t, self.open_in_explorer)
        self._drives_gen = 0
        QTimer.singleShot(0, self.reload_tree_drives)
        self.tree_stack = QStackedWidget()
        self.tree_stack.addWidget(self.tree)
        self.tree_stack.addWidget(self.minitree)

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
        folders_page = QWidget()
        fpl = QVBoxLayout(folders_page)
        fpl.setContentsMargins(0, 0, 0, 0)
        fpl.setSpacing(0)
        self.side_boxes["pipeline"] = boxed("PIPELINE", self.pipebar_side)
        fpl.addWidget(self.side_boxes["pipeline"])
        fpl.addWidget(self.tree_stack, 1)
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
        self.b_minitree = QToolButton()
        self.b_minitree.setCheckable(True)
        self.b_minitree.setAutoRaise(True)
        self.b_minitree.setChecked(bool(self.cfg["mini_tree_on"]))
        self.b_minitree.toggled.connect(self._toggle_minitree)
        self._popfix(self.b_minitree)
        self.b_mini_clear = QToolButton()          # en Mini tree, el lugar del ojito: tijera para vaciarlo
        self.b_mini_clear.setAutoRaise(True)
        self.b_mini_clear.setIcon(ic.glyph("scissors", 15, "#c9ccd1"))
        self.b_mini_clear.setToolTip("Clear the Mini tree (start again from the current folder)")
        self.b_mini_clear.clicked.connect(self._clear_minitree)
        self._popfix(self.b_mini_clear)
        crl.addWidget(self.b_eye_tree)
        crl.addWidget(self.b_mini_clear)
        crl.addWidget(self.b_minitree)
        crl.addWidget(self.b_colors)
        crl.addWidget(self.b_side_add)
        self.sidetabs.setCornerWidget(corner, Qt.TopRightCorner)
        self._peek = False
        self.sidetabs.currentChanged.connect(self._sidetab_changed)
        self._toggle_minitree()
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
        from .slots import SlotController
        self.lib_slots = SlotController(self, self.libpage)      # Ctrl / Shift + 1…4 en el player
        lp = self.libpane
        lp.proxy.hide_images = not self.cfg["lib_show_images"]
        lp.model.lib_mode = True
        lp.grid.lib_mode = True
        lp.list.lib_mode = True
        lp.root_lock = lambda: [r for r in (self.cfg["library_roots"] or []) if safe_isdir(r)]
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
        self.center_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.center_stack.setMinimumWidth(220)

        # --- detalles
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(170)
        self.preview.setStyleSheet("background:#17181a; border-radius:6px;")
        from .blowup import BlowUpController
        self.blowup = BlowUpController(self, self.preview)     # mantener apretado: imagen al 100 %
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
        sa.setWidget(iw)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        # archivos de texto (.ini, .txt, .nk…): se leen en todo el panel, como un bloc de notas (sin editar)
        from PySide6.QtWidgets import QPlainTextEdit
        tp = QWidget()
        tpl = QVBoxLayout(tp)
        tpl.setContentsMargins(8, 8, 8, 8)
        tpl.setSpacing(6)
        self.text_title = QLabel()
        self.text_title.setStyleSheet("font-size:10pt; font-weight:bold; color:#eee;")
        self.text_title.setWordWrap(True)
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text_view.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.text_view.setStyleSheet("QPlainTextEdit{background:#141414; border:1px solid #2a2a2a; border-radius:4px;"
                                     "font-family:Consolas,'Cascadia Mono','DejaVu Sans Mono',monospace;"
                                     "font-size:9.5pt; color:#d6d6d6; padding:4px;}")
        self.text_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.text_meta = QLabel()
        self.text_meta.setWordWrap(True)
        self.text_meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.text_meta.setStyleSheet("color:#8b9099; font-size:8.5pt;")
        tpl.addWidget(self.text_title)
        tpl.addWidget(self.text_view, 1)
        tpl.addWidget(self.text_meta)
        # PDF: las páginas una debajo de la otra, al ancho del panel
        self.pdf_area = QScrollArea()
        self.pdf_area.setWidgetResizable(True)
        self.pdf_area.setFrameShape(QFrame.NoFrame)
        self.pdf_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        pw = QWidget()
        self.pdf_lay = QVBoxLayout(pw)
        self.pdf_lay.setContentsMargins(8, 8, 8, 8)
        self.pdf_lay.setSpacing(8)
        self.pdf_lay.addStretch(1)
        self.pdf_area.setWidget(pw)
        self.pdf_pages = []
        self.pdf_token = 0
        self.details_stack = QStackedWidget()
        self.details_stack.addWidget(sa)
        self.details_stack.addWidget(tp)
        self.details_stack.addWidget(self.pdf_area)
        self.info_area = QWidget()
        dsl = QVBoxLayout(self.info_area)
        dsl.setContentsMargins(0, 0, 0, 0)
        dsl.addWidget(self.details_stack)
        self.info_area.setMinimumWidth(0)      # el mínimo (DETAILS_MIN_W) lo maneja el splitter
        # lo que se muestra adentro nunca cambia el ancho del panel (lo elige el usuario)
        self.info_area.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.details_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.text_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.preview.installEventFilter(self)
        self.pdf_area.viewport().installEventFilter(self)
        self._preview_pm = None

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.center_stack)
        main.addWidget(self.info_area)
        main.setStretchFactor(1, 1)
        main.setSizes([280, 940, 300])
        main.setCollapsible(0, False)
        main.splitterMoved.connect(lambda *_: self._sync_cmd_left())
        main.splitterMoved.connect(lambda *_: self._clamp_details())
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
        hh = QVBoxLayout(self.head_host)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.setSpacing(0)
        self.tabs_host = QWidget()
        self.tabs_host.setObjectName("paneTabs")
        thl = QHBoxLayout(self.tabs_host)
        thl.setContentsMargins(0, 0, 0, 0)
        thl.setSpacing(0)
        self.nav_host = QWidget()
        self.nav_host.setObjectName("navHost")
        nhl = QHBoxLayout(self.nav_host)
        nhl.setContentsMargins(0, 0, 0, 0)
        nhl.setSpacing(0)
        hh.addWidget(self.tabs_host)
        hh.addWidget(self.nav_host)
        # ← → ↑ ⟳ y buscador: uno solo para File Explorer, trabajan sobre el panel activo
        self.gnav = QWidget()
        gl = QHBoxLayout(self.gnav)
        gl.setContentsMargins(8, 7, 4, 7)
        gl.setSpacing(6)
        self.gnav_buttons = {}
        for key, glyph, tip, fn in (("back", "back", "Back (Alt+←)", "go_back"), ("fwd", "fwd", "Forward (Alt+→)", "go_forward"),
                                    ("up", "up", "Up (Alt+↑ · Backspace)", "go_up"), ("ref", "reload", "Refresh (F5)", "refresh")):
            b = QToolButton()
            b.setFixedSize(38, 34)
            b.setIconSize(QSize(18, 18))
            b.setIcon(ic.glyph(glyph, 18))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, fn=fn: self._gnav(fn))
            gl.addWidget(b)
            self.gnav_buttons[key] = b
        self.gsearch = QLineEdit()
        self.gsearch.setObjectName("paneSearch")
        self.gsearch.setToolTip("Search the active pane · name or part · *wildcards*\n"
                                "With Subfolders on it searches the branch · Ctrl+F · Esc clears")
        self.gsearch.setClearButtonEnabled(True)
        self.gsearch.addAction(ic.glyph("search", 16, "#c5c5c5"), QLineEdit.TrailingPosition)
        self.gsearch.setFixedHeight(36)
        self.gsearch.setStyleSheet("QLineEdit{font-size:10.5pt; padding:4px 10px; border-radius:5px;"
                                   "border:1px solid #333333; background:#2d2d2d;}"
                                   "QLineEdit:focus{background:#1f1f1f; border-bottom:2px solid #4cc2ff;}")
        self.gsearch.textChanged.connect(self._gsearch_changed)
        self.gsearch.returnPressed.connect(lambda: self._gpane()._apply_search())
        self.gsearch.installEventFilter(self)
        self.gsearch_box = QWidget()
        gsl = QHBoxLayout(self.gsearch_box)
        gsl.setContentsMargins(4, 7, 10, 7)
        gsl.addWidget(self.gsearch)
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
        self.b_collapse = QToolButton()
        self.b_collapse.setCheckable(True)
        self.b_collapse.setAutoRaise(True)
        self.b_collapse.setChecked(bool(self.cfg["collapse_seqs"]))
        self.b_collapse.setToolTip("Collapse image sequences into one item\nOff: every frame as its own file")
        self.b_collapse.toggled.connect(self._toggle_collapse)
        self._collapse_icon()
        sb.addPermanentWidget(self.b_collapse)
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
            #navHost {{ background:#2b2b2b; border-bottom:1px solid #232323; }}
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
        QShortcut(QKeySequence("F9"), self, lambda: self.toggle_dual(orient="h"))
        QShortcut(QKeySequence("F7"), self, lambda: self.active.go_previous())   # ir y volver entre las 2 últimas
        QShortcut(QKeySequence("F10"), self, lambda: self.toggle_dual(orient="v"))
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
        """Arriba, a todo el ancho: las pestañas y la dirección de File Explorer, con ← → ↑ ⟳ y el buscador
        compartidos (trabajan sobre el panel activo). Doble panel lado a lado: cada panel tiene sus pestañas y su
        dirección arriba, alineadas con él. Doble panel arriba/abajo (F10): el de abajo lleva las suyas adentro.
        La VFX Library tiene sus propias pestañas en el centro, entre el viewer y los elementos."""
        orient = self.cfg["dual_orient"] or "h"
        dual = bool(self.cfg["dual"]) if self.mode() == "library" else self.paneB.isVisible()
        side = dual and orient == "h"
        stacked = dual and orient == "v"
        th, nh = self.tabs_host.layout(), self.nav_host.layout()
        A, B = self.paneA, self.paneB
        while th.count():
            th.takeAt(0)
        while nh.count():
            nh.takeAt(0)
        th.addWidget(A.tabsrow, 0 if side else 1)
        nh.addWidget(self.gnav)
        nh.addWidget(A.navrow, 1)
        if side:
            th.addWidget(B.tabsrow, 1)
            nh.addWidget(B.navrow, 1)
        nh.addWidget(self.gsearch_box)
        for w in (A.tabsrow, A.navrow, self.gnav, self.gsearch_box):
            w.show()
        hl = B.header.layout()
        if stacked or not dual:
            if B.tabsrow.parent() is not B.header:
                hl.insertWidget(0, B.tabsrow)
                hl.insertWidget(1, B.navrow)
            B.tabsrow.show()
            B.navrow.show()
        elif side:
            B.tabsrow.show()
            B.navrow.show()
        A.header.hide()
        B.header.setVisible(stacked)
        for p in self.panes:                       # ← → ↑ ⟳ y buscador: uno solo (el de arriba), para el activo
            for w in p.nav_buttons:
                w.setVisible(False)
            p.search.setVisible(False)
        lp = self.libpane
        if lp.header.parent() is not lp:
            lp.layout().insertWidget(0, lp.header)
        (B if side else A).corner.addWidget(self.modebar)
        for p in self.all_panes:
            p.footer.setVisible(dual and p is not lp)
        self.pane_split.setOrientation(Qt.Vertical if orient == "v" else Qt.Horizontal)
        self.modebar.ensurePolished()
        QTimer.singleShot(0, lambda: self.modebar.setMinimumWidth(
            sum(self.modebar.tabRect(i).width() for i in range(self.modebar.count())) + 8))
        QTimer.singleShot(0, self._sync_cmd_left)

    def _gpane(self):
        return self.explorer_active

    def _gnav(self, fn):
        if self.mode() == "library":
            self.set_mode("explorer")
        getattr(self._gpane(), fn)()

    def _gsearch_changed(self, text):
        p = self._gpane()
        if p.search.text() != text:
            p.search.setText(text)

    def sync_nav(self, pane):
        """El buscador y ← → ↑ ⟳ compartidos reflejan el panel activo de File Explorer."""
        if not hasattr(self, "gsearch") or pane is not self._gpane():
            return
        self.gnav_buttons["back"].setEnabled(pane.b_back.isEnabled())
        self.gnav_buttons["fwd"].setEnabled(pane.b_fwd.isEnabled())
        self.gnav_buttons["up"].setEnabled(pane.b_up.isEnabled())
        if self.gsearch.text() != pane.search.text():
            self.gsearch.blockSignals(True)
            self.gsearch.setText(pane.search.text())
            self.gsearch.blockSignals(False)
        self.gsearch.setPlaceholderText(pane.search.placeholderText())

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
        for b in reversed(self.chev_buttons):         # no entra: quedan solo con ícono (View, Sort, New)
            if need() <= lw:
                break
            b.set_compact(True)
        self.cmd_left.setFixedWidth(lw - 1)
        rw = (s[2] + hw) if (self.info_area.isVisible() and s[2] > 0) else 0
        self.cmd_right.setFixedWidth(max(self.cmd_right.layout().sizeHint().width(), rw))
        self.sb_right.setFixedWidth(max(self.sb_right.layout().sizeHint().width(), rw))
        # buscador de ancho fijo (no baila) y, lado a lado, cada cabecera alineada con su panel
        self.gsearch_box.setFixedWidth(int(self.width() * 0.19))     # crece con la ventana
        A, B = self.paneA, self.paneB
        side = B.isVisible() and (self.cfg["dual_orient"] or "h") == "h" and B.tabsrow.parent() is self.tabs_host
        if side:
            ps = self.pane_split.sizes()
            if ps and ps[0] > 0:
                x = s[0] + hw + ps[0] + self.pane_split.handleWidth() // 2
                A.tabsrow.setFixedWidth(x)
                A.navrow.setFixedWidth(max(120, x - self.gnav.sizeHint().width()))
        else:
            for w in (A.tabsrow, A.navrow):
                w.setMinimumWidth(0)
                w.setMaximumWidth(16777215)

    def _popfix(self, b):
        """Botones de ícono que no se corren al pasar el mouse."""
        b.setStyleSheet("QToolButton{border:none;padding:3px;border-radius:4px;}"
                        "QToolButton:hover{background:#2d2d2d;} QToolButton:checked{background:#383838;}"
                        "QToolButton::menu-indicator{image:none;width:0px;}")
        b.setFixedSize(28, 26)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._sync_cmd_left)
        QTimer.singleShot(0, self._auto_details)

    def _clamp_details(self):
        """El panel de detalles no se achica arrastrando por debajo de su mínimo; si se colapsa del todo,
        se apaga (y el botón Details también)."""
        s = self.main_split.sizes()
        if self.info_area.isVisible() and len(s) == 3 and s[2] == 0:
            self.toggle_details(False)
            return
        if self.info_area.isVisible() and len(s) == 3 and 0 < s[2] < DETAILS_MIN_W:
            d = DETAILS_MIN_W - s[2]
            self.main_split.setSizes([s[0], max(50, s[1] - d), DETAILS_MIN_W])

    def _ensure_details_width(self):
        """Al volver a mostrar el panel de detalles, que tenga al menos su ancho mínimo."""
        s = self.main_split.sizes()
        if self.info_area.isVisible() and len(s) == 3 and s[2] < DETAILS_MIN_W:
            d = DETAILS_MIN_W - s[2]
            self.main_split.setSizes([s[0], max(220, s[1] - d), DETAILS_MIN_W])
        self._sync_cmd_left()

    def _auto_details(self):
        """Si la ventana queda tan angosta que el panel de detalles no entra con su mínimo, se apaga solo
        (y vuelve cuando hay lugar)."""
        if not hasattr(self, "main_split"):
            return
        s = self.main_split.sizes()
        need = (s[0] if s else 250) + 320 + DETAILS_MIN_W
        if self.info_area.isVisible() and (s[2] < DETAILS_MIN_W - 2 or s[1] < 300):
            self._details_auto_off = True
            self.toggle_details(False, remember=False)
        elif getattr(self, "_details_auto_off", False) and self.width() >= need + 40:
            self._details_auto_off = False
            self.toggle_details(True, remember=False)

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
                   ("videos", "Videos"), ("onedrive", "OneDrive"), ("nuke", ".nuke"))

    def _sys_view_defaults(self):
        """0.17: Downloads (agrupado por fecha) y Videos (íconos grandes) arrancan con su vista de fábrica,
        aunque ya se hubiera guardado otra antes."""
        done = int(self.cfg["sys_view_defaults"] or 0)
        if done >= 3:
            return
        fv = dict(self.cfg["folder_views"] or {})
        # 1: Downloads y Videos (0.17) · 2: Documents (0.28) · 3: Downloads otra vez (0.29: por fecha de verdad)
        for kind in ("downloads", "videos", "documents") if done < 1 else ("documents", "downloads"):
            p = self._sys_path(kind)
            if p:
                fv.pop(norm_key(p), None)
        self.cfg["folder_views"] = fv
        self.cfg["sys_view_defaults"] = 3
        self.cfg.save()

    def _sys_path(self, kind):
        from PySide6.QtCore import QStandardPaths as SP
        if kind == "nuke":                         # carpeta .nuke del usuario (solo si existe)
            p = os.path.join(os.path.expanduser("~"), ".nuke")
            return p if os.path.isdir(p) else ""
        if kind == "onedrive":
            for v in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
                p = os.environ.get(v)
                if p and os.path.isdir(p):
                    return os.path.normpath(p)
            p = os.path.join(os.path.expanduser("~"), "OneDrive")
            return p if os.path.isdir(p) else ""
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
        self.tree.apply_hidden()
        self.minitree.apply_hidden()

    def hook_tree_keys(self, tree, opener):
        """Moverse con las flechas por un árbol abre la carpeta (con una pequeña espera, para no cargar
        cada carpeta por la que se pasa rápido)."""
        tree._syncing = False
        timer = QTimer(tree, singleShot=True, interval=0)      # inmediato (la carpeta se lee en otro hilo)
        state = {"path": None}

        def fire():
            p = state["path"]
            if not p:
                return
            pane = self.libpane if opener == self.open_library else self.explorer_active
            t = pane.tab() if pane.tabs else None
            here = "::thispc" if (t and t["virtual"] and t["virtual"]["kind"] == "thispc") else pane.current_dir()
            if here and (p == here or (not p.startswith("::") and not here.startswith("::")
                                       and same_path(p, here))):
                return
            opener(p)

        timer.timeout.connect(fire)

        self._mark_keynav(tree)

        def changed(cur, prev):
            # solo cuando lo movió el usuario con el teclado (no al rearmar el árbol ni con el mouse)
            if getattr(tree, "_syncing", False) or cur is None or not getattr(tree, "_keynav", False):
                return
            state["path"] = cur.data(0, Qt.UserRole) if isinstance(cur, QTreeWidgetItem) else cur.data(Qt.UserRole)
            timer.start()
        tree.currentItemChanged.connect(changed)

    _NAV_KEYS = (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp, Qt.Key_PageDown,
                 Qt.Key_Home, Qt.Key_End)

    def _mark_keynav(self, w):
        """Marca mientras se procesa una flecha / letra en la lista o el árbol."""
        app = self

        class F(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.KeyPress and (ev.key() in app._NAV_KEYS or ev.text().isalnum()):
                    w._keynav = True
                    QTimer.singleShot(0, lambda: setattr(w, "_keynav", False))
                return False
        w._keyfilter = F(w)
        w.installEventFilter(w._keyfilter)

    def hook_list_keys(self, w, click_fn):
        """Listas del panel izquierdo (Quick access, colecciones, tags): moverse con las flechas abre."""
        self._mark_keynav(w)

        def changed(cur, prev):
            # solo con el teclado: rearmar la lista (p. ej. al mostrar ocultos) no tiene que navegar
            if cur is None or not getattr(w, "_keynav", False):
                return
            if cur.data(Qt.UserRole):
                QTimer.singleShot(0, lambda it=cur: click_fn(it))
        w.currentItemChanged.connect(changed)

    def reload_tree_drives(self):
        """Discos del árbol (This PC): se leen en segundo plano (una unidad de red caída no traba)."""
        from .models import DrivesWorker
        self._drives_gen += 1
        w = DrivesWorker(self._drives_gen)
        w.done.connect(self._tree_drives_ready)
        self._drives_worker = w
        w.start()

    def _tree_drives_ready(self, gen, drives):
        if gen != self._drives_gen:
            return
        self.tree.set_drives(drives)
        self.minitree.set_drives(drives)

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

    # ---------------- layouts de columnas (vista Details)
    COL_LAYOUTS = (
        ("Standard", ["Name", "Type", "Range", "Frames", "Missing", "Size", "Modified"]),
        ("VFX", ["Name", "Range", "Frames", "Missing", "Resolution", "FPS", "Codec", "Channels", "Colorspace",
                 "Size", "Modified"]),
        ("Video", ["Name", "Resolution", "FPS", "Codec", "Colorspace", "Size", "Modified"]),
        ("Minimal", ["Name", "Size", "Modified"]),
    )

    def _visible_cols(self, pane):
        from .models import COLS
        hd = pane.list.header()
        return [COLS[lg] for lg in sorted(range(len(COLS)), key=hd.visualIndex) if not pane.list.isColumnHidden(lg)]

    def fill_layout_menu(self, m, pane):
        cur = self._visible_cols(pane)
        custom = dict(self.cfg["col_layouts"] or {})
        for name, cols in list(self.COL_LAYOUTS) + sorted(custom.items()):
            a = m.addAction(name, lambda c=cols: self.apply_col_layout(c))
            a.setCheckable(True)
            a.setChecked(cols == cur)
            a.setToolTip(", ".join(cols))
        m.setToolTipsVisible(True)
        m.addSeparator()
        m.addAction("Save current layout as…", lambda: self._save_col_layout(pane))
        if custom:
            d = m.addMenu("Delete layout")
            for name in sorted(custom):
                d.addAction(name, lambda n=name: self._del_col_layout(n))

    def apply_col_layout(self, cols):
        from .models import COLS
        self.cfg["list_cols"] = {n: (n in cols) for n in COLS}
        self.cfg["col_order"] = [c for c in cols if c in COLS]
        self.cfg.save()
        for p in self.all_panes:
            p._apply_columns()
            if p.view_mode != "grid":
                p.fit_columns()

    def _save_col_layout(self, pane):
        name, ok = QInputDialog.getText(self, "Column layout", "Name:")
        name = (name or "").strip()
        if not ok or not name:
            return
        lay = dict(self.cfg["col_layouts"] or {})
        lay[name] = self._visible_cols(pane)
        self.cfg["col_layouts"] = lay
        self.cfg.save()
        self.status.setText(f"Column layout «{name}» saved")

    def _del_col_layout(self, name):
        lay = dict(self.cfg["col_layouts"] or {})
        lay.pop(name, None)
        self.cfg["col_layouts"] = lay
        self.cfg.save()

    def show_hashes(self, path):
        from .hashdlg import HashDialog
        d = HashDialog(self, path)
        d.show()

    # ---------------- slots del player de la librería
    _SLOT_SCANCODES = ({2: 0, 3: 1, 4: 2, 5: 3},          # Windows: teclas 1-4 de la fila de números
                       {10: 0, 11: 1, 12: 2, 13: 3})     # X11
    _SLOT_SHIFT_KEYS = {Qt.Key_Exclam: 0, Qt.Key_At: 1, Qt.Key_QuoteDbl: 1, Qt.Key_NumberSign: 2,
                        Qt.Key_periodcentered: 2, Qt.Key_Dollar: 3}

    def _digit(self, ev):
        """Tecla 1-4 de la fila de números (0-3) aunque Shift la convierta en ! " # $ según el teclado."""
        sc = ev.nativeScanCode()
        table = self._SLOT_SCANCODES[0 if IS_WIN else 1]
        if sc in table:
            return table[sc]
        k = ev.key()
        return self._SLOT_SHIFT_KEYS.get(k, (k - Qt.Key_1) if Qt.Key_1 <= k <= Qt.Key_4 else -1)

    def _slot_key(self, ev):
        """Ctrl+1…4: guardar el video actual en el slot · Shift+1…4: ir al slot. Solo en la VFX Library
        y no mientras se escribe en un campo de texto."""
        if not self.isActiveWindow():
            return False
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QPlainTextEdit)) or (fw is not None and fw.inherits("QAbstractSpinBox")):
            return False
        mods = ev.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier)
        k = ev.key()
        i = -1
        act = None
        if mods == (Qt.ControlModifier | Qt.ShiftModifier):        # Ctrl+Shift+1 / 2: vista íconos / lista
            i = self._digit(ev)
            if i not in (0, 1):
                return False
            if ev.type() == QEvent.ShortcutOverride:
                ev.accept()
                return True
            self.active.set_view("grid" if i == 0 else "list")
            return True
        if self.mode() != "library":
            return False
        if mods == Qt.ControlModifier and Qt.Key_1 <= k <= Qt.Key_4:
            i, act = k - Qt.Key_1, "set"
        elif not mods and Qt.Key_1 <= k <= Qt.Key_4:          # 1…4 (fila de números o teclado numérico)
            i, act = k - Qt.Key_1, "go"
        if i < 0 or act is None:
            return False
        if ev.type() == QEvent.ShortcutOverride:
            ev.accept()                    # que llegue como tecla (y no dispare otro atajo)
            return True
        if act == "set":
            self.lib_slots.assign(i)
        else:
            self.lib_slots.go(i)
        return True

    def _toggle_hover_box(self):
        self.cfg["hover_box"] = not self.cfg["hover_box"]
        self.cfg.save()
        if not self.cfg["hover_box"]:
            self.hoverbox.hide_box()
        self.status.setText("Hover box on" if self.cfg["hover_box"] else "Hover box off")

    def _toggle_minitree(self, on=None):
        on = self.b_minitree.isChecked() if on is None else on
        self.cfg["mini_tree_on"] = bool(on)
        self.tree_stack.setCurrentIndex(1 if on else 0)
        self.b_minitree.setIcon(self.icons.glyph("minitree", 15, "#4cc2ff" if on else "#9d9d9d"))
        self.b_minitree.setToolTip("Mini tree: only the folders you visited  (click: full folder tree)" if on
                                   else "Full folder tree  (click: Mini tree, only the folders you visited)")
        self._side_tooltip(self.sidetabs.currentIndex() if hasattr(self, "sidetabs") else 0)
        if not on:
            cur = self.explorer_active.current_dir() if hasattr(self, "explorer_active") else None
            t = self.explorer_active.tab() if hasattr(self, "explorer_active") else None
            here = "::thispc" if (t and t["virtual"] and t["virtual"]["kind"] == "thispc") else cur
            if here and (here == "::thispc" or reachable(here)):
                self.tree.sync(here)

    def _clear_minitree(self):
        self.minitree.clear_all()
        t = self.explorer_active.tab()
        cur = self.explorer_active.current_dir()
        here = "::thispc" if (t and t["virtual"] and t["virtual"]["kind"] == "thispc") else cur
        if cur:
            self.minitree.add(cur)
        self.minitree.sync(here or "")
        self.status.setText("Mini tree cleared")

    def _minitree_menu(self, pos):
        it = self.minitree.itemAt(pos)
        p = it.data(0, Qt.UserRole) if it else ""
        m = QMenu(self)
        if p:
            m.addAction("Open in new tab", lambda: self.open_in_explorer(p, new_tab=True))
            m.addAction("Remove from Mini tree", lambda: self.minitree.remove(p))
            m.addSeparator()
        m.addAction("Clear Mini tree", self._clear_minitree)
        m.addAction("Show the full folder tree", lambda: self.b_minitree.setChecked(False))
        m.exec(self.minitree.viewport().mapToGlobal(pos))

    def _side_tooltip(self, i):
        self.b_side_add.setVisible(i == 1)
        self.b_eye.setVisible(i == 0)
        self.b_minitree.setVisible(i == 0)
        self.b_eye_tree.setVisible(i == 0 and not self.b_minitree.isChecked())
        self.b_mini_clear.setVisible(i == 0 and self.b_minitree.isChecked())

    def _sidetab_changed(self, i):
        """Los tabs del panel izquierdo solo cambian el árbol (y el acceso rápido): el modo del centro cambia
        recién al hacer click en una carpeta."""
        self._side_tooltip(i)
        if not self._peek:
            self.quick_stack.setCurrentIndex(i)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            if obj is getattr(self, "preview", None):
                QTimer.singleShot(0, self._fit_preview)
            elif hasattr(self, "pdf_area") and obj is self.pdf_area.viewport():
                w = max(60, self.pdf_area.viewport().width() - 16)
                for lb in self.pdf_pages[1:]:
                    self._fit_pdf_page(lb, w)
        if obj is getattr(self, "gsearch", None) and ev.type() == QEvent.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self.gsearch.clear()
                self._gpane().view().setFocus()
                return True
            if ev.key() in (Qt.Key_Down, Qt.Key_Up):
                self._gpane().view().setFocus()
                return False
        if ev.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and hasattr(self, "lib_slots") \
                and self._slot_key(ev):
            return True
        if ev.type() == QEvent.MouseButtonPress and isinstance(obj, QWidget) and hasattr(self, "panes"):
            self._header_press(obj, ev)
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

    def _header_press(self, w, ev=None):
        """Click en las pestañas o la dirección de un panel de Carpetas: activa ese panel (y si estamos en la
        VFX Library, vuelve a Carpetas). El selector de modo queda afuera."""
        x = w
        while x is not None:
            if x is self.modebar:
                return
            if x is self.gnav or x is self.gsearch_box:
                if self.mode() == "library":
                    self.set_mode("explorer")
                return
            for p in self.panes:
                if x is p.tabsrow or x is p.navrow:
                    if self.mode() == "library" and x is p.tabsrow and ev is not None:
                        # espacio vacío de la fila de pestañas: mueve la ventana, no cambia de modo
                        pos = p.tabbar.mapFromGlobal(ev.globalPosition().toPoint())
                        if not (p.tabbar.rect().contains(pos) and p.tabbar.tabAt(pos) >= 0):
                            return
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
        self.hook_list_keys(w, click_fn)
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
        if not self.cfg["splitter"]:              # primera vez: panel izquierdo con lugar para sus botones
            tot = max(1200, self.width())
            self.main_split.setSizes([340, tot - 340 - 360, 360])
        states = self.cfg["panes"] or []
        home = QDir.homePath()
        from .core import THISPC
        fallback = start_path if safe_isdir(start_path) else (THISPC if IS_WIN else home)
        a_state = states[0] if states else None
        if safe_isdir(start_path):
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
        if self.libpane.tabs:              # con la librería offline no se pisan sus pestañas guardadas
            self.cfg["library_pane"] = self.libpane.state()
        self.cfg["dual"] = self.paneB.isVisible()
        self.cfg.save()
        self.lib.save()

    def save_soon(self):
        self.save_timer.start()

    def reset_all(self, parent=None):
        """⚙ › Reset all: borra caché y toda la configuración y vuelve a abrir como la primera vez."""
        r = QMessageBox.question(parent or self, "Reset all",
                                 "Clear the cache and every setting (Quick access, tabs, folder views, colors, "
                                 "tags, collections, library folders…) and restart VFX Explorer as the first time?\n\n"
                                 "Your files are not touched.",
                                 QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if r != QMessageBox.Yes:
            return
        self._resetting = True
        if parent is not None:
            parent.reject()
        QTimer.singleShot(0, self.close)

    def _finish_reset(self):
        import shutil
        from PySide6.QtCore import QProcess
        shutil.rmtree(self.data_dir, ignore_errors=True)
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, sys.argv)

    def closeEvent(self, ev):
        if getattr(self, "_resetting", False):
            self.save_timer.stop()
            for p in self.all_panes:
                p._stop_search()
            self.thumbs.cancel_pending()
            self.thumbs.pool.waitForDone(3000)
            self.dirsizes.clear()
            self.libpage.shutdown()
            super().closeEvent(ev)
            self._finish_reset()
            return
        self.meta.cancel()
        self.meta.save()
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
        if remember:
            self._details_auto_off = False
        self.info_area.setVisible(show)
        if show and changed:
            QTimer.singleShot(0, self._ensure_details_width)
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
        pane.b_filter.update()
        # el ícono de View muestra la vista actual
        self.b_view.setIcon(self.icons.glyph("grid" if pane.view_mode == "grid" else "list", 18))
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(int(getattr(pane, "thumb_size", self.cfg["thumb_size"])))
        self.size_slider.blockSignals(False)
        self.size_slider.setEnabled(pane.view_mode == "grid")
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
            self.fill_layout_menu(m.addMenu("Column layout"), pane)
            a = m.addAction("Row numbers", self._toggle_row_numbers)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg["list_row_numbers"]))
        m.addSeparator()
        m.addAction("Apply this view to all folders", lambda: (
            pane.apply_view_to_all(), self.status.setText("This view is now the default for every folder")))
        if not full:
            return
        m.addSeparator()
        a = m.addAction("Hover box (preview under the mouse)", self._toggle_hover_box)
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["hover_box"]))
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
        self.act_dual_v.setEnabled(not lib)
        if hasattr(self, "b_folderpdf"):
            self.b_folderpdf.setVisible(lib)
        self._place_headers()
        self.apply_pipeline_location()
        if lib:
            roots = self.libpane.root_lock()
            if not self.libpane.tabs and roots:
                self.libpane.add_tab(roots[0])
            was_lib = self.cfg["mode"] == "library"
            self.set_active(self.libpane)
            if not was_lib:                       # al cambiar de modo; si no, el foco queda donde estaba
                self.libpane.view().setFocus()
            if not self.cfg["library_roots"]:
                self.libpage.viewer.show_message("Choose your VFX library folder with the ＋ next to the "
                                                 "«VFX LIBRARY» tab in the left pane (videos, sequences, "
                                                 "images, HDRIs…).")
        else:
            self.libpage.viewer.pause()
            self.set_active(self.explorer_active)
        # Details: cada modo muestra lo suyo (no se mezcla lo de File Explorer con la librería)
        if lib:
            self._details_owner = ""
            self._lib_details(self.libpane.selected_entries() if self.libpane.tabs else [])
        else:
            self._details_owner = "explorer"
            self._clear_details()
            self._sel_changed(self.explorer_active)
        # el ícono del modo activo en color (explorer amarillo, librería celeste), el otro gris
        self.modebar.setTabIcon(0, self.icons.glyph("folder", 16, "#9d9d9d" if lib else "#ffcf48"))
        self.modebar.setTabIcon(1, self.icons.glyph("library", 16, "#4cc2ff" if lib else "#9d9d9d"))
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

    LIB_FOLDER = "#4cc2ff"          # en la VFX Library las carpetas sin color propio son celestes

    def entry_color(self, e, lib=False):
        if e.kind == "dir":
            return self.colors.dir_color(e.path) or (self.LIB_FOLDER if lib else None)
        return self.lib.color(e.key())

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
            if pane in self.panes:
                self.sync_nav(pane)
            self._location_changed(pane)
            self._sel_changed(pane)
            self._pane_status(pane)

    def other(self, pane):
        if not self.paneB.isVisible() or pane not in self.panes or self.mode() != "explorer":
            return None
        return self.paneB if pane is self.paneA else self.paneA

    def toggle_dual(self, force=None, orient=None):
        """F9 / botón: doble panel lado a lado · F10 / botón: uno arriba del otro."""
        if force is None and self.mode() != "explorer":
            self.set_mode("explorer")
        cur = self.cfg["dual_orient"] or "h"
        if force is None:
            if orient and self.paneB.isVisible() and orient != cur:
                show = True                         # ya hay doble panel: solo cambia la orientación
            else:
                show = not self.paneB.isVisible()
        else:
            show = force
        if orient:
            self.cfg["dual_orient"] = orient
        self.paneB.setVisible(show)
        o = self.cfg["dual_orient"] or "h"
        self.act_dual.setChecked(show and o == "h")
        self.act_dual_v.setChecked(show and o == "v")
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
        """Cerrar la única pestaña: en doble panel cierra ese panel; con un solo panel cierra la app."""
        if pane not in self.panes:
            return
        if not self.paneB.isVisible():
            self.close()
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

    def _sync_quick(self, d):
        """Acceso rápido: queda marcado solo el ítem de la carpeta actual (si está)."""
        k = norm_key(d) if d else None
        for w in (self.favs, self.lib_favs):
            hit = None
            for i in range(w.count()):
                p = w.item(i).data(Qt.UserRole)
                if k and p and norm_key(p) == k:
                    hit = w.item(i)
                    break
            w.blockSignals(True)
            if hit is not None:
                w.setCurrentItem(hit)
            else:
                w.clearSelection()
                w.setCurrentRow(-1)
            w.blockSignals(False)

    def _location_changed(self, pane):
        if pane is not self.active:
            return
        d = pane.current_dir()
        self._sync_quick(d)
        if pane is self.libpane:
            self.libside.sync(d or "")
            QTimer.singleShot(0, lambda dd=d: self._lib_folder_changed(dd))
            if d:
                self.setWindowTitle(f"{os.path.basename(d.rstrip(chr(92) + '/')) or d} — {APP_NAME} {VERSION}")
            return
        t = pane.tab()
        here = "::thispc" if (t and t["virtual"] and t["virtual"]["kind"] == "thispc") else (d or "")
        d_tree = d if (d and reachable(d)) else ""
        if d:
            self.minitree.add(d)
        self.minitree.sync(here)
        if not self.b_minitree.isChecked():       # el árbol completo se sincroniza solo si está a la vista
            self.tree.sync(here if (here == "::thispc" or d_tree) else "")
        if not d:
            for pb in self.pipebars:
                pb.clear()
        if d_tree:
            for pb in self.pipebars:
                pb.sync(d)
            self.setWindowTitle(f"{os.path.basename(d.rstrip(chr(92) + '/')) or d} — {APP_NAME} {VERSION}")

    def _pane_status(self, pane):
        if pane is self.active:
            self.status.setText(pane.status_text)

    def _on_thumb_size(self, v):
        """El tamaño de íconos es de la carpeta (como Windows): cambia el panel activo y se recuerda."""
        self.active.set_thumb_size(v)
        self.thumbs.scaled.clear()
        self.active._save_folder_view()
        self.save_soon()

    def refresh_views(self):
        self.colors.invalidate()
        for p in self.all_panes:
            p.model.refresh_all()
            p.grid.viewport().update()
            p.list.viewport().update()
        self.tree.viewport().update()
        self.minitree.refresh_colors()

    def _start_freeze_watch(self):
        """Diagnóstico: si la ventana se traba más de 2 s, anota en VFXExplorer_data/freeze.log qué estaba
        haciendo (para encontrar lo que traba con el NAS). No cuesta nada mientras todo anda."""
        import threading
        import time as _t
        import traceback as _tb
        self._hb = _t.monotonic()
        self._hb_timer = QTimer(self, interval=250, timeout=lambda: setattr(self, "_hb", _t.monotonic()))
        self._hb_timer.start()
        log = os.path.join(self.data_dir, "freeze.log")
        main_id = threading.main_thread().ident

        def watch():
            logged = False
            while True:
                _t.sleep(0.5)
                stall = _t.monotonic() - self._hb
                if stall > 2.0 and not logged:
                    logged = True
                    try:
                        fr = sys._current_frames().get(main_id)
                        stack = "".join(_tb.format_stack(fr)) if fr is not None else "?"
                        with open(log, "a", encoding="utf-8") as f:
                            f.write(f"\n=== {_t.strftime('%Y-%m-%d %H:%M:%S')} · window stuck > 2 s ===\n{stack}")
                    except Exception:
                        pass
                elif stall < 1.0:
                    logged = False
        threading.Thread(target=watch, daemon=True).start()

    def _net_watch(self):
        bad = set(net_offline_roots())
        for r in list(self._net_known_bad | bad):
            if r not in bad:                 # respondió de nuevo
                self._net_back(r)
            else:
                reachable(r, 0)              # dispara otro chequeo en segundo plano (no espera)
        self._net_known_bad = set(net_offline_roots())

    def _net_back(self, root):
        self.status.setText(f"{root} is back online")
        self.libside.reload()
        roots = self.libpane.root_lock()
        if roots and not self.libpane.tabs:
            lst = self.cfg["library_pane"] or None
            if lst:
                lst = dict(lst, tabs=[t for t in lst.get("tabs", []) if self.libpane.allowed(t.get("path", ""))])
            self.libpane.restore(lst, roots[0])
        for p in self.all_panes:
            cur = p.current_dir()
            if cur and net_root(cur) == root:
                p.refresh()
        for pb in self.pipebars:
            pb.reload()

    def refresh_dirs(self, dirs):
        keys = {norm_key(d) for d in dirs if d}
        for d in dirs:
            if d:
                self.tree.refresh_dir(d)
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
        if pane is self.libpane:
            self._lib_details(ents)
            return
        self._details_owner = "explorer"
        self.info_token += 1
        self._info_entry = None
        self.details_stack.setCurrentIndex(0)
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

    # ---------------- Details en la VFX Library
    # Queda fija la última imagen / PDF: la seleccionada en la grilla o el PDF (o la portada) de la carpeta.
    # Elegir videos, modelos o carpetas no la cambia (el player muestra eso): sirve para comparar.
    def _lib_show(self, e):
        cur = self._info_entry
        if cur is not None and cur.path == e.path and getattr(self, "_details_owner", "") == "library":
            return
        self._details_owner = "library"
        self._lib_details_entry = e
        self.info_token += 1
        self._show_info(e)

    def _lib_details(self, ents):
        if len(ents) == 1:
            e = ents[0]
            # todo lo que no es video (eso lo muestra el player): imágenes, PDF, textos, modelos…
            if (e.kind == "file" and e.cat != "video") or (e.kind == "seq" and e.cat != "audio"):
                self._lib_show(e)
                return
        if getattr(self, "_details_owner", "") != "library":
            le = getattr(self, "_lib_details_entry", None)
            if le is not None:
                self._lib_show(le)
            else:
                self._clear_details()

    def _lib_folder_changed(self, d):
        """Al entrar a una carpeta de la librería: su PDF (o portada) pasa a Details; el video de otra
        carpeta se pausa (queda su cuadro) para no seguir sonando mientras se busca otra cosa."""
        v = self.libpage.viewer
        if v.entry is not None and d and not same_path(v.entry.dirpath, d) and v.playing:
            v.pause()
        if not self.cfg["lib_folder_pdf"] or self.mode() != "library":
            return

        def got(doc):                             # se busca en otro hilo (en el NAS puede tardar)
            if self.mode() != "library" or not same_path(self.libpane.current_dir() or "", d):
                return
            if not doc:                           # carpeta sin PDF ni portada: Details queda vacío
                self._lib_details_entry = None
                if getattr(self, "_details_owner", "") == "library" or self._info_entry is not None:
                    self._clear_details()
                    self._details_owner = "library"
                return
            ext = os.path.splitext(doc)[1].lower()
            self._lib_show(Entry(kind="file", dirpath=os.path.dirname(doc), name=os.path.basename(doc),
                                 path=doc, ext=ext))
        from .asyncdir import run_async
        run_async(lambda: self._folder_doc(d), got, self)

    def _clear_details(self):
        self.info_token += 1
        self._info_entry = None
        self.details_stack.setCurrentIndex(0)
        self.preview.clear()
        self._preview_pm = None
        self.info.setText("")
        self.status_right.setText("")

    COVER_WORDS = ("cover", "portada", "preview", "thumb", "poster", "folder", "front")

    def _folder_doc(self, d):
        """PDF de la carpeta o de la madre más cercana; si no hay ninguno, una imagen de portada."""
        pdf = self._folder_pdf(d)
        if pdf:
            return pdf
        return self._folder_cover(d)

    def _folder_cover(self, d):
        from .core import IMAGE_EXTS
        if not d or not reachable(d):
            return None
        roots = [os.path.normcase(os.path.normpath(r)) for r in self.libpane.root_lock()]
        cur = os.path.normpath(d)
        while True:
            try:
                with os.scandir(cur) as sc:
                    imgs = sorted((x.name for x in sc if os.path.splitext(x.name)[1].lower() in IMAGE_EXTS
                                   and x.is_file()), key=str.lower)
            except OSError:
                imgs = []
            if imgs:
                named = [n for n in imgs if any(w in n.lower() for w in self.COVER_WORDS)]
                return os.path.join(cur, (named or imgs)[0])
            return None                           # la portada es solo de la carpeta misma

    def _folder_pdf(self, d):
        """PDF de la carpeta actual o de la carpeta madre más cercana (dentro de la librería)."""
        if not d or not reachable(d):
            return None
        roots = [os.path.normcase(os.path.normpath(r)) for r in self.libpane.root_lock()]
        cache = self.__dict__.setdefault("_pdf_cache", {})
        cur = os.path.normpath(d)
        while True:
            try:
                mt = os.stat(cur).st_mtime
            except OSError:
                return None
            hit = cache.get(cur)
            if hit is None or hit[0] != mt:
                found = None
                try:
                    with os.scandir(cur) as sc:
                        pdfs = sorted((x.name for x in sc if x.name.lower().endswith(".pdf") and x.is_file()),
                                      key=str.lower)
                    found = os.path.join(cur, pdfs[0]) if pdfs else None
                except OSError:
                    pass
                cache[cur] = hit = (mt, found)
            if hit[1]:
                return hit[1]
            if os.path.normcase(cur) in roots:
                return None
            parent = os.path.dirname(cur)
            if parent == cur:
                return None
            cur = parent

    def _toggle_folder_pdf(self, on):
        self.cfg["lib_folder_pdf"] = bool(on)
        self.cfg.save()
        if on and self.mode() == "library":
            self._lib_folder_changed(self.libpane.current_dir())

    def _set_preview(self, e):
        pm = self.thumbs.get(e)
        if pm is None and e.kind == "dir":
            pm = self.icons.folder(self.lib.color(e.key()), 120)
        if pm is None:
            pm = self.sys_icon(e, 128)
        self._preview_pm = pm
        if pm is not None:
            self._fit_preview()
        else:
            self.preview.setText("<span style='color:#666'>no preview</span>")

    def _fit_preview(self):
        """La imagen del panel de detalles se ajusta al ancho elegido del panel."""
        pm = self._preview_pm
        if pm is None:
            return
        w = max(40, self.preview.width() - 8)
        h = min(260, max(80, int(w * 0.75)))
        sp = pm if (pm.width() <= w and pm.height() <= h) else pm.scaled(w, h, Qt.KeepAspectRatio,
                                                                          Qt.SmoothTransformation)
        self.preview.setPixmap(sp)

    # ---------------- PDF en el panel de detalles
    def _pdf_preview(self, e):
        from .imaging import HAS_PDF, pdf_page_count
        if e.kind != "file" or e.ext != ".pdf" or not HAS_PDF:
            return False
        n = pdf_page_count(e.path)
        if not n:
            return False
        self.pdf_token += 1
        for lb in self.pdf_pages:
            lb.deleteLater()
        self.pdf_pages = []
        title = QLabel(f"<b>{e.name}</b><br><span style='color:#8b9099'>{n} page(s) · {human_size(e.size)}</span>")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pdf_lay.insertWidget(0, title)
        self.pdf_pages.append(title)
        for i in range(min(n, 40)):
            lb = QLabel()
            lb.setAlignment(Qt.AlignCenter)
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            lb.setFixedHeight(int(max(60, self.pdf_area.viewport().width() - 16) * 1.29))
            lb.setStyleSheet("background:#ffffff; border-radius:2px;")
            self.pdf_lay.insertWidget(i + 1, lb)
            self.pdf_pages.append(lb)
        self.details_stack.setCurrentIndex(2)
        self.pdf_area.verticalScrollBar().setValue(0)
        self.status_right.setText(fwd(e.path))
        self._pdf_src = (e.path, min(n, 40))
        QTimer.singleShot(0, lambda t=self.pdf_token: self._pdf_render_next(t, 0))
        return True

    def _pdf_render_next(self, token, i):
        """Renderiza de a una página sin trabar la interfaz."""
        if token != self.pdf_token or not getattr(self, "_pdf_src", None):
            return
        path, n = self._pdf_src
        if i >= n:
            return
        from .imaging import pdf_render
        dpr = self.devicePixelRatioF()
        w = max(60, self.pdf_area.viewport().width() - 16)
        img = pdf_render(path, i, int(min(1800, w * dpr * 1.25)))
        if token != self.pdf_token:
            return
        lb = self.pdf_pages[i + 1]
        if not img.isNull():
            lb._img = img
            self._fit_pdf_page(lb, w)
        QTimer.singleShot(1, lambda: self._pdf_render_next(token, i + 1))

    def _fit_pdf_page(self, lb, w):
        img = getattr(lb, "_img", None)
        if img is None:
            return
        dpr = self.devicePixelRatioF()
        pm = QPixmap.fromImage(img.scaledToWidth(int(w * dpr), Qt.SmoothTransformation))
        pm.setDevicePixelRatio(dpr)
        lb.setFixedHeight(int(pm.height() / dpr))
        lb.setPixmap(pm)

    TEXT_EXTS = {".txt", ".ini", ".cfg", ".conf", ".json", ".xml", ".yaml", ".yml", ".md", ".log", ".csv", ".tsv",
                 ".py", ".mel", ".ms", ".mcr", ".nk", ".gizmo", ".bat", ".cmd", ".ps1", ".sh", ".lua", ".js", ".html",
                 ".htm", ".css", ".toml", ".usda", ".srt", ".vtt", ".glsl", ".osl", ".vfl", ".chan", ".ocio", ".spi1d",
                 ".cube", ".edl", ".rtf", ".reg", ".env", ".properties"}

    def _text_preview(self, e):
        """Muestra el contenido de un archivo de texto en todo el panel. Devuelve False si no es texto."""
        if e.kind != "file" or os.path.splitext(e.name)[1].lower() not in self.TEXT_EXTS:
            return False
        try:
            with open(e.path, "rb") as f:
                raw = f.read(512 * 1024)
        except OSError:
            return False
        if raw.count(b"\0") > 8:
            return False
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                txt = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        cut = e.size > len(raw)
        self.text_title.setText(e.name)
        self.text_view.setPlainText(txt + ("\n\n… (only the first 512 KB)" if cut else ""))
        self.text_meta.setText(f"{human_size(e.size)} · {txt.count(chr(10)) + 1} lines · {fmt_time(e.mtime)} · "
                               f"{fwd(e.dirpath)}")
        self.details_stack.setCurrentIndex(1)
        self.status_right.setText(fwd(e.path))
        return True

    def _show_info(self, e):
        self._info_entry = e
        if self._text_preview(e) or self._pdf_preview(e):
            return
        self.details_stack.setCurrentIndex(0)
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
        rows.append(("Folder", soft(fwd(e.dirpath))))
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
            f"<div style='font-size:10pt; font-weight:bold; color:#eee;'>{soft(e.name)}</div><table width='100%'>"
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
    PHOTO_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".avif",
                  ".tif", ".tiff"}

    def open_entry(self, e, with_player=True):
        player = self.cfg["player"]
        # fotos numeradas (IMG_0001.jpg…) agrupadas como secuencia: se abren como fotos sueltas
        if e.kind == "seq" and e.ext in self.PHOTO_EXTS and e.files:
            first = os.path.join(e.dirpath, e.files[0])
            e = Entry(kind="file", dirpath=e.dirpath, name=e.files[0], path=first, ext=e.ext)
        if with_player and player and os.path.isfile(player) and e.cat in ("seq", "video"):
            try:
                subprocess.Popen([player, e.path])
                return
            except Exception as ex:
                self.status.setText(f"Could not open the player: {ex}")
        viewer = self.cfg["image_viewer"]
        if with_player and viewer and os.path.isfile(viewer) and e.kind == "file" and e.cat == "image":
            try:
                subprocess.Popen([viewer, e.path])     # visor de imágenes elegido en Settings
                return
            except Exception as ex:
                self.status.setText(f"Could not open the image viewer: {ex}")
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

    def op_trash(self, pane, permanent=False):
        """Del: a la papelera directo, sin preguntar. Shift+Del: borrar para siempre, preguntando.
        En discos de red Windows no tiene papelera: ahí Del también pregunta."""
        ents = pane.selected_entries()
        if not ents or self.op_worker is not None:
            return
        paths = [p for e in ents for p in e.all_paths()]
        net = any(fileops.is_network_path(p) for p in paths[:1])
        n_files = len(paths)
        desc = ents[0].name if len(ents) == 1 else f"{len(ents)} items"
        if permanent:
            text = f"Permanently delete {desc}?" + (f"\n({n_files} files)" if n_files > 1 else "") + \
                   "\n\nThis can't be undone."
            ans = self._ask("Delete permanently", text, [("Delete", QMessageBox.DestructiveRole),
                                                         ("Cancel", QMessageBox.RejectRole)], default="Cancel")
            if ans in (None, "Cancel"):
                return
        elif net:
            text = (f"Delete {desc}?" + (f"\n({n_files} files)" if n_files > 1 else "") +
                    "\n\n⚠ It's on a network drive: Windows deletes it PERMANENTLY "
                    "(unless the NAS recycle bin is enabled for that shared folder).")
            ans = self._ask("Delete", text, [("Delete", QMessageBox.DestructiveRole),
                                             ("Cancel", QMessageBox.RejectRole)], default="Cancel")
            if ans in (None, "Cancel"):
                return
        w = fileops.TrashWorker(paths, permanent=permanent)
        self.op_worker = w
        self.status.setText("Deleting…")

        def fin(errors):
            self.op_worker = None
            self.refresh_dirs({e.dirpath for e in ents})
            done = "deleted" if (permanent or net) else "sent to the Recycle Bin"
            self.status.setText(f"{desc}: {done}" if not errors else "Delete error")
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
        # como Windows: crea «New folder» y queda con el nombre en edición
        name = fileops.unique_name(d, "New folder")
        try:
            fileops.new_folder(d, name)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        pane.pending_select = name
        pane.pending_edit = True
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
                col = self.dir_color(p) or (self.LIB_FOLDER if key == "lib_favorites" else None)
                it = QListWidgetItem(self.icons.folder_icon(col, 18), name)
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
        self.minitree.refresh_colors()
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

    def _tree_menu(self, tree, pos):
        it = tree.itemAt(pos)
        if it is None:
            if tree.mini:
                self._minitree_menu(pos)
            return
        p = it.data(0, Qt.UserRole)
        if p == "::thispc":
            m = QMenu(self)
            m.addAction("Open", lambda: self.open_in_explorer(p))
            m.addAction("Open in new tab", lambda: self.open_in_explorer(p, new_tab=True))
            m.addAction("Refresh drives", self.reload_tree_drives)
            if tree.mini:
                m.addSeparator()
                m.addAction("Clear Mini tree", self._clear_minitree)
            m.exec(tree.viewport().mapToGlobal(pos))
            return
        m = QMenu(self)
        m.addAction("Open", lambda: self.open_in_explorer(p))
        if tree.mini:
            m.addAction("Remove from Mini tree", lambda: self.minitree.remove(p))
        if it.parent() is tree.root and not tree.mini:   # disco: se puede ocultar del árbol
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
        m.exec(tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ menú contextual de ítems
    def _toggle_row_numbers(self):
        self.cfg["list_row_numbers"] = not self.cfg["list_row_numbers"]
        self.cfg.save()
        for p in self.all_panes:
            p.list.apply_numbers()

    def sys_icon(self, e, size):
        """Ícono original del archivo (el del programa / tipo, como en el Explorador) o None.
        No para imágenes, video, audio ni los que no tienen ícono propio. Se apaga en ⚙ › General."""
        if not self.cfg["system_icons"] or e.kind != "file" or e.cat in ("image", "video") \
                or e.ext in AUDIO_EXTS:
            return None
        per_file = e.ext in (".exe", ".lnk", ".ico", ".url", ".msi", ".appref-ms", "")
        if per_file and net_root(e.path):          # en la red: el Explorador de Windows tarda; sin ícono propio
            return None
        key = (e.path if per_file else e.ext, int(size))
        cache = self.__dict__.setdefault("_sysic", {})
        if key in cache:
            return cache[key]
        from PySide6.QtWidgets import QFileIconProvider
        from PySide6.QtCore import QFileInfo
        prov = self.__dict__.setdefault("_iconprov", QFileIconProvider())
        pm = None
        try:
            src = e.path
            if not per_file:
                # el ícono del tipo sale de un archivito vacío local con la misma extensión: no toca la red
                src = os.path.join(self.data_dir, "icons", "type" + e.ext)
                if not os.path.exists(src):
                    os.makedirs(os.path.dirname(src), exist_ok=True)
                    open(src, "w").close()
            ic = prov.icon(QFileInfo(src))
            if not ic.isNull():
                pm = ic.pixmap(int(size), int(size))
                if pm.isNull():
                    pm = None
            if pm is not None:                 # los íconos genéricos ("archivo" / tipo desconocido) no sirven
                gk = ("__generic__", int(size))
                if gk not in cache:
                    gens = []
                    gi = prov.icon(QFileIconProvider.IconType.File)
                    if not gi.isNull():
                        gens.append(gi.pixmap(int(size), int(size)).toImage())
                    try:
                        probe = os.path.join(self.data_dir, "probe.vfxunknownext")   # portable: nada afuera
                        if not os.path.exists(probe):
                            open(probe, "w").close()
                        ui = prov.icon(QFileInfo(probe))
                        if not ui.isNull():
                            gens.append(ui.pixmap(int(size), int(size)).toImage())
                    except OSError:
                        pass
                    cache[gk] = gens
                img = pm.toImage()
                if any(img == g for g in cache[gk]):
                    pm = None
        except Exception:
            pm = None
        cache[key] = pm
        return pm

    def _collapse_icon(self):
        on = self.b_collapse.isChecked()
        self.b_collapse.setIcon(self.icons.glyph("seqstack", 18, "#4cc2ff" if on else "#6e7378"))

    def _toggle_collapse(self, on):
        self._collapse_icon()
        self.cfg["collapse_seqs"] = on
        self.cfg.save()
        self.status.setText("Sequences collapsed" if on else "Sequences expanded: one item per frame")
        for p in self.all_panes:
            if p.tabs:
                p.refresh()

    def _toggle_color_filters(self, on):
        self.cfg["color_filters_on"] = bool(on)
        self.cfg.save()
        self._cf_rules = None
        self.refresh_views()

    def color_filter_for(self, e):
        """(color de texto, fondo) según los Color filters, o None."""
        if not self.cfg["color_filters_on"] or e.kind in ("header", "drive"):
            return None
        rules = getattr(self, "_cf_rules", None)
        if rules is None:
            from .core import parse_color_filters, DEFAULT_COLOR_FILTERS
            v = self.cfg["color_filters"]
            rules = self._cf_rules = parse_color_filters(DEFAULT_COLOR_FILTERS if v is None else v)
        from .core import color_filter_match
        name = e.pattern_path("hash") if e.kind == "seq" else e.name
        return color_filter_match(rules, os.path.basename(name), e.kind == "dir")

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

    # ---------------- WinRAR (si está instalado): extraer / comprimir desde el menú contextual
    ARCHIVE_EXTS = {".rar", ".zip", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".cab", ".iso", ".arj", ".lz", ".zst"}

    def winrar_exe(self):
        if hasattr(self, "_winrar"):
            return self._winrar
        exe = ""
        if IS_WIN:
            try:
                import winreg
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    for sub in (r"SOFTWARE\WinRAR", r"SOFTWARE\WOW6432Node\WinRAR"):
                        try:
                            with winreg.OpenKey(hive, sub) as k:
                                for val in ("exe64", "exe32"):
                                    try:
                                        v = winreg.QueryValueEx(k, val)[0]
                                        if v and os.path.isfile(v):
                                            exe = v
                                            break
                                    except OSError:
                                        pass
                        except OSError:
                            pass
                        if exe:
                            break
                    if exe:
                        break
            except Exception:
                pass
            if not exe:
                for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
                    c = os.path.join(base, "WinRAR", "WinRAR.exe")
                    if os.path.isfile(c):
                        exe = c
                        break
        self._winrar = exe
        return exe

    def _winrar_run(self, args, refresh=None):
        try:
            subprocess.Popen([self.winrar_exe()] + args)
        except OSError as ex:
            QMessageBox.warning(self, "WinRAR", str(ex))
            return
        if refresh:
            QTimer.singleShot(2500, lambda: self.refresh_dirs([refresh]))

    def _winrar_menu(self, m, pane, ents):
        exe = self.winrar_exe()
        if not exe or not ents:
            return
        files = [f for e in ents for f in (e.files if e.kind == "seq" else [e.path])]
        archives = [e for e in ents if e.kind == "file" and e.ext in self.ARCHIVE_EXTS]
        from PySide6.QtWidgets import QFileIconProvider
        from PySide6.QtCore import QFileInfo
        sub = m.addMenu(QFileIconProvider().icon(QFileInfo(exe)), "WinRAR")
        if archives:
            e0 = archives[0]
            here = e0.dirpath
            folder = os.path.splitext(e0.name)[0]
            sub.addAction("Extract files…", lambda: [self._winrar_run(["x", "-ad", a.path, here + os.sep])
                                                     for a in archives])
            sub.addAction("Extract here", lambda: [self._winrar_run(["x", "-ibck", "-o-", a.path, here + os.sep],
                                                                    here) for a in archives])
            sub.addAction(f"Extract to {folder}\\" if len(archives) == 1 else "Extract each to its own folder",
                          lambda: [self._winrar_run(["x", "-ibck", "-o-", a.path,
                                                     os.path.join(here, os.path.splitext(a.name)[0]) + os.sep], here)
                                   for a in archives])
            sub.addAction("Open in WinRAR", lambda: self._winrar_run([e0.path]))
            sub.addSeparator()
        base = os.path.splitext(ents[0].name)[0] if len(ents) == 1 else os.path.basename(pane.current_dir() or "archive")
        d = pane.current_dir() or ents[0].dirpath
        sub.addAction("Add to archive…", lambda: self._winrar_run(["a", "-ep1", os.path.join(d, base + ".rar")] + files))
        sub.addAction(f"Add to «{base}.rar»", lambda: self._winrar_run(
            ["a", "-ibck", "-ep1", os.path.join(d, base + ".rar")] + files, d))
        sub.addAction(f"Add to «{base}.zip»", lambda: self._winrar_run(
            ["a", "-ibck", "-ep1", "-afzip", os.path.join(d, base + ".zip")] + files, d))

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
            self._winrar_menu(m, pane, ents)
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
            m.addAction("Delete\tDel", lambda: self.op_trash(pane))
            m.addAction("Delete permanently\tShift+Del", lambda: self.op_trash(pane, permanent=True))
            m.addSeparator()
            cp = m.addMenu("Copy path")
            cp.addAction("Path  (plate.####.exr)\tCtrl+Shift+C", lambda: self.copy_paths(pane, "hash"))
            cp.addAction("Nuke path  (plate.%04d.exr 1001-1100)\tCtrl+Alt+C", lambda: self.copy_paths(pane, "nuke"))
            cp.addAction("Windows path  (with \\)", lambda: self.copy_paths(pane, "win"))
            cp.addAction("First frame", lambda: self.copy_paths(pane, "first"))
            cp.addAction("Folder", lambda: self.copy_paths(pane, "dir"))
            cp.addAction("Name only", lambda: self.copy_paths(pane, "name"))
            if len(ents) == 1 and e.kind == "file":
                m.addAction("File hashes (MD5, SHA-1, SHA-256)…", lambda: self.show_hashes(e.path))
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
            m.addAction("New folder\tCtrl+Shift+N", lambda: self.op_new_folder(pane))
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
            self._cf_rules = None
            self.icons.set_default_folder(self.cfg["folder_color"] or "yellow")
            self._reload_sidebar()
            self.libside.reload()
            if not self.cfg["folder_sizes"]:
                self.dirsizes.clear()
            self.apply_features()
            self.apply_pipeline_location()
            self.refresh_views()
            if ch["listing"]:
                for p in self.all_panes:
                    p.refresh()


