# -*- coding: utf-8 -*-
"""Ventana principal: barra de pipeline, sidebar (favoritos, colecciones, tags, carpetas), paneles e info."""

import os
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QByteArray, QDir, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices, QCursor
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
from . import fileops


# ----------------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------------

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
        # --- pipeline horizontal: va sobre el panel central (debajo de la barra de comandos)
        self.pipebar_top = PipelineBar(self, vertical=False)
        self.pipe_frame = QFrame()
        self.pipe_frame.setObjectName("pipeFrame")
        pfl = QHBoxLayout(self.pipe_frame)
        pfl.setContentsMargins(6, 4, 6, 4)
        pfl.addWidget(self.pipebar_top)
        pfl.addStretch(1)
        self.modebar = QTabBar()
        self.modebar.setObjectName("modebar")
        self.modebar.setDocumentMode(True)
        self.modebar.setDrawBase(False)
        self.modebar.setExpanding(False)
        self.modebar.addTab(ic.glyph("folder", 16), "Explorador")
        self.modebar.addTab(ic.glyph("library", 16, "#b98cff"), "VFX Library")
        self.modebar.setTabToolTip(0, "Explorador de archivos (Ctrl+Shift+E)")
        self.modebar.setTabToolTip(1, "VFX Library: viewer arriba, elementos abajo (Ctrl+Shift+L)")
        self.modebar.currentChanged.connect(lambda i: self.set_mode("library" if i == 1 else "explorer"))

        # --- barra de comandos (como la del Explorador de Windows 11)
        cb = QToolBar("Comandos")
        cb.setObjectName("cmdbar")
        cb.setMovable(False)
        cb.setIconSize(QSize(16, 16))
        cb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(cb)
        self.cmdbar = cb

        def menu_button(glyph, text, menu, tip=""):
            b = QToolButton()
            b.setIcon(ic.glyph(glyph, 16))
            b.setText(text + "  ")
            b.setToolTip(tip or text)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setPopupMode(QToolButton.InstantPopup)
            b.setMenu(menu)
            cb.addWidget(b)
            return b

        def act(glyph, tip, slot, text=None):
            a = cb.addAction(ic.glyph(glyph, 16), text or "", slot)
            a.setToolTip(tip)
            w = cb.widgetForAction(a)
            if w is not None and not text:
                w.setToolButtonStyle(Qt.ToolButtonIconOnly)
            return a

        cb.addWidget(self.modebar)
        cb.addSeparator()
        m_new = QMenu(self)
        m_new.addAction(ic.glyph("newfolder", 16), "Carpeta\tCtrl+Shift+N", lambda: self.op_new_folder(self.active))
        menu_button("plus", "Nuevo", m_new, "Crear carpeta")
        cb.addSeparator()
        act("cut", "Cortar (Ctrl+X)", lambda: self.op_clip(self.active, cut=True))
        act("copy", "Copiar (Ctrl+C)", lambda: self.op_clip(self.active, cut=False))
        act("paste", "Pegar (Ctrl+V)", lambda: self.op_paste(self.active))
        act("rename", "Cambiar nombre (F2) — también secuencias", lambda: self.start_inline_rename(self.active))
        act("trash", "Eliminar: mandar a la papelera (Supr)", lambda: self.op_trash(self.active))
        cb.addSeparator()

        self.m_sort = QMenu(self)
        self.m_sort.aboutToShow.connect(self._fill_sort_menu)
        menu_button("sort", "Ordenar", self.m_sort)
        self.m_view = QMenu(self)
        self.m_view.aboutToShow.connect(self._fill_view_menu)
        menu_button("grid", "Ver", self.m_view)
        self.m_filter = QMenu(self)
        self.m_filter.aboutToShow.connect(self._fill_filter_menu)
        self.b_filter = menu_button("filter", "Filtrar", self.m_filter, "Mostrar solo un tipo de archivo")
        self.act_sub = cb.addAction(ic.glyph("branch", 16), "Subcarpetas",
                                    lambda: self.active.rec.toggle())
        self.act_sub.setCheckable(True)
        self.act_sub.setToolTip("Incluir subcarpetas (Ctrl+B)\nSin texto: todos los archivos de la rama.\n"
                                "Con texto: busca en toda la rama.")
        cb.addSeparator()
        self.m_more = QMenu(self)
        self.m_more.aboutToShow.connect(self._fill_more_menu)
        more = menu_button("more", "", self.m_more, "Ver más")
        more.setToolButtonStyle(Qt.ToolButtonIconOnly)
        sp2 = QWidget()
        sp2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cb.addWidget(sp2)
        self.act_dual = cb.addAction(ic.glyph("dual", 16), "Doble panel", self.toggle_dual)
        self.act_dual.setCheckable(True)
        self.act_dual.setToolTip("Doble panel (F9) · F6 cambia de panel")
        self.act_details = cb.addAction(ic.glyph("details", 16), "Detalles", self.toggle_details)
        self.act_details.setCheckable(True)
        self.act_details.setToolTip("Panel de detalles (Alt+Shift+P)")
        a = cb.addAction(ic.glyph("gear", 16), "", self.open_settings)
        a.setToolTip("Configuración")
        cb.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonIconOnly)

        # sidebar
        self.favs = self._mk_list(self._favs_menu, lambda it: self.open_in_explorer(it.data(Qt.UserRole)))
        self.favs.setDragDropMode(QAbstractItemView.InternalMove)
        self.favs.model().rowsMoved.connect(self._favs_reordered)
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

        self.color_mode = QComboBox()
        for label, key in COLOR_MODES:
            self.color_mode.addItem(label, key)
        self.color_mode.setCurrentIndex(max(0, self.color_mode.findData(self.cfg["color_mode"])))
        self.color_mode.setToolTip("Colores automáticos de carpetas\n"
                                   "Por proyecto: el proyecto tiene un color, las secuencias uno más claro y los shots más claro.\n"
                                   "Por nombre: reglas como 3D = azul (se editan en ⚙ › Colores).\n"
                                   "El color manual (clic derecho › Etiqueta de color) siempre gana.")
        self.color_mode.setStyleSheet("QComboBox{font-size:8pt; padding:1px 4px;}")
        self.color_mode.currentIndexChanged.connect(self._color_mode_changed)

        self.libside = LibrarySidebar(self, self._section("VFX LIBRARY"))
        self.pipebar_side = PipelineBar(self, vertical=True)
        self.pipebars = [self.pipebar_top, self.pipebar_side]
        left = QSplitter(Qt.Vertical)
        self.side_boxes = {}
        self.thispc = self._mk_list(lambda w, pos: None, lambda it: self.open_in_explorer("::thispc"))
        it = QListWidgetItem(ic.glyph("pc", 18, "#4cc2ff"), "Este equipo")
        it.setToolTip("Discos y ubicaciones de red")
        self.thispc.addItem(it)
        self.thispc.setFixedHeight(34)
        self.thispc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        treebox = QWidget()
        tbl = QVBoxLayout(treebox)
        tbl.setContentsMargins(0, 0, 0, 0)
        tbl.setSpacing(0)
        tbl.addWidget(self.thispc)
        tbl.addWidget(self.tree, 1)
        for key, title, w, extra in (("pipeline", "PIPELINE", self.pipebar_side, None),
                                     ("favs", "ACCESO RÁPIDO", self.favs, None),
                                     ("colls", "COLECCIONES", self.colls, None),
                                     ("tags", "TAGS", self.tagl, None),
                                     ("tree", "CARPETAS", treebox, self.color_mode)):
            if title is None:
                box = w
            else:
                box = QWidget()
                bl = QVBoxLayout(box)
                bl.setContentsMargins(0, 0, 0, 0)
                bl.setSpacing(1)
                if extra is not None:
                    h = QHBoxLayout()
                    h.setContentsMargins(0, 0, 4, 0)
                    h.addWidget(self._section(title), 1)
                    h.addWidget(extra)
                    bl.addLayout(h)
                else:
                    bl.addWidget(self._section(title))
                bl.addWidget(w)
            self.side_boxes[key] = box
            left.addWidget(box)
        left.setSizes([170, 150, 80, 100, 480])
        left.setMinimumWidth(200)
        self.left_split = left
        # dos tabs: Carpetas (explorador) / VFX Library
        self.sidetabs = QTabWidget()
        self.sidetabs.setObjectName("sidetabs")
        self.sidetabs.setDocumentMode(True)
        self.sidetabs.addTab(left, ic.glyph("folder", 16), "Carpetas")
        self.sidetabs.addTab(self.libside, ic.glyph("library", 16, "#b98cff"), "VFX Library")
        self.side_boxes["library"] = self.libside

        # paneles
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

        self.modebar = QTabBar()
        self.modebar.setDocumentMode(True)
        self.modebar.setExpanding(False)
        self.modebar.setObjectName("modebar")
        self.modebar.addTab(ic.glyph("folder", 16), "Explorador")
        self.modebar.addTab(ic.glyph("library", 16, "#b98cff"), "VFX Library")
        self.modebar.setTabToolTip(0, "Explorador de archivos (Ctrl+Shift+E)")
        self.modebar.setTabToolTip(1, "VFX Library: viewer arriba, elementos abajo (Ctrl+Shift+L)")
        self.modebar.currentChanged.connect(lambda i: self.set_mode("library" if i == 1 else "explorer"))
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.pane_split)
        self.center_stack.addWidget(self.libpage)
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.pipe_frame)
        cl.addWidget(self.center_stack, 1)

        # info
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
        main.addWidget(self.sidetabs)
        main.addWidget(center)
        main.addWidget(sa)
        main.setStretchFactor(1, 1)
        main.setSizes([280, 940, 300])
        main.setCollapsible(0, False)
        self.main_split = main
        self.setCentralWidget(main)

        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.status_right = QLabel()
        self.statusBar().addPermanentWidget(self.status_right)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(96, 320)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Tamaño de los íconos")
        self.size_slider.setValue(int(self.cfg["thumb_size"]))
        self.size_slider.valueChanged.connect(self._on_thumb_size)
        self.statusBar().addPermanentWidget(self.size_slider)
        self.sb_list = QToolButton()
        self.sb_list.setIcon(ic.glyph("list", 16))
        self.sb_list.setToolTip("Detalles (Ctrl+2)")
        self.sb_list.setCheckable(True)
        self.sb_list.setAutoRaise(True)
        self.sb_list.clicked.connect(lambda: self.active.set_view("list"))
        self.sb_grid = QToolButton()
        self.sb_grid.setIcon(ic.glyph("grid", 16))
        self.sb_grid.setToolTip("Íconos grandes (Ctrl+1)")
        self.sb_grid.setCheckable(True)
        self.sb_grid.setAutoRaise(True)
        self.sb_grid.clicked.connect(lambda: self.active.set_view("grid"))
        self.statusBar().addPermanentWidget(self.sb_list)
        self.statusBar().addPermanentWidget(self.sb_grid)
        self.statusBar().setSizeGripEnabled(False)

        self.setStyleSheet(f"""
            #pane {{ border:none; }}
            #paneNav[active="true"] {{ border-bottom:2px solid {ACCENT}; }}
            #paneHeader {{ background:#202020; }}
            #paneTabs {{ background:#202020; }}
            #paneNav {{ background:#2b2b2b; border-bottom:2px solid #232323; }}
            #pipeFrame {{ background:#202020; border-bottom:1px solid #1a1a1a; }}
            #sidetabs::pane {{ border:none; }}
            #sidetabs QTabBar::tab {{ padding:6px 14px; min-width:80px; border-radius:6px; margin:4px 2px 2px 4px; }}
            #sidetabs QTabBar::tab:selected {{ background:#2d2d2d; color:#ffffff; }}
            #paneSearch {{ border-radius:4px; }}
            #paneFooter {{ color:#9d9d9d; font-size:8pt; padding:3px 10px; background:#191919;
                           border-top:1px solid #232323; }}
            #paneBanner {{ background:#0f3a55; color:#e6f6ff; padding:5px 12px; font-size:8.5pt;
                           border-bottom:1px solid #1a5c86; }}
            #viewerBar {{ background:#202020; border-top:1px solid #2a2a2a; }}
            #modebar::tab {{ padding:6px 16px; min-width:110px; border-radius:6px; margin:2px; }}
            #modebar::tab:selected {{ background:#2d2d2d; color:#ffffff; }}
            QListWidget, QTreeWidget, QTreeView {{ background:#191919; }}
        """)
        QShortcut(QKeySequence("F9"), self, self.toggle_dual)
        QShortcut(QKeySequence("F6"), self, self.switch_pane)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, lambda: self.set_mode("explorer"))
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, lambda: self.set_mode("library"))
        QShortcut(QKeySequence("Alt+Shift+P"), self, self.toggle_details)
        self._reload_sidebar()
        self.apply_features()
        self.apply_pipeline_location()

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
        for k, sp in (("splitter", self.main_split), ("splitter_left2", self.left_split),
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
        self.cfg["splitter_left2"] = bytes(self.left_split.saveState().toBase64()).decode()
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

    def toggle_details(self, force=None):
        show = (not self.info_area.isVisible()) if force is None else bool(force)
        self.info_area.setVisible(show)
        self.act_details.setChecked(show)
        self.cfg["details_visible"] = show
        self.save_soon()

    def sync_commandbar(self, pane=None):
        """Refleja en la barra de comandos y en la barra de estado el estado del panel activo."""
        pane = pane or self.active
        if pane is not getattr(self, "active", None) or not hasattr(self, "act_sub"):
            return
        self.act_sub.blockSignals(True)
        self.act_sub.setChecked(pane.rec.isChecked())
        self.act_sub.blockSignals(False)
        cat = pane.filter.currentData()
        label = next((l for l, k in FILTERS if k == cat), "Filtrar")
        self.b_filter.setText(("Filtrar" if cat == "all" else label) + "  ")
        self.sb_grid.setChecked(pane.view_mode == "grid")
        self.sb_list.setChecked(pane.view_mode != "grid")

    def _fill_sort_menu(self):
        m = self.m_sort
        m.clear()
        pane = self.active
        hd = pane.list.header()
        cur, order = hd.sortIndicatorSection(), hd.sortIndicatorOrder()
        from .models import C_NAME, C_MTIME, C_TYPE, C_SIZE, C_FRAMES, C_RANGE
        for label, col in (("Nombre", C_NAME), ("Fecha de modificación", C_MTIME), ("Tipo", C_TYPE),
                           ("Tamaño", C_SIZE), ("Cantidad de frames", C_FRAMES), ("Primer frame", C_RANGE)):
            a = m.addAction(label, lambda c=col: pane.list.sortByColumn(c, order))
            a.setCheckable(True)
            a.setChecked(cur == col)
        m.addSeparator()
        for label, o in (("Ascendente", Qt.AscendingOrder), ("Descendente", Qt.DescendingOrder)):
            a = m.addAction(label, lambda o=o: pane.list.sortByColumn(cur, o))
            a.setCheckable(True)
            a.setChecked(order == o)
        m.addSeparator()
        g = m.addMenu("Agrupar por")
        for label, key in (("Automático (carpeta en Subcarpetas)", "auto"), ("(Ninguno)", "none"),
                           ("Carpeta", "folder"), ("Tipo", "type")):
            a = g.addAction(label, lambda k=key: pane.set_group(k))
            a.setCheckable(True)
            a.setChecked(pane.group_mode == key)

    def _fill_view_menu(self):
        m = self.m_view
        m.clear()
        pane = self.active
        ts = int(self.cfg["thumb_size"])
        for label, size in (("Íconos extra grandes", 320), ("Íconos grandes", 240), ("Íconos medianos", 180),
                            ("Íconos pequeños", 120)):
            a = m.addAction(self.icons.glyph("grid", 16), label,
                            lambda sz=size: (pane.set_view("grid"), self.size_slider.setValue(sz)))
            a.setCheckable(True)
            a.setChecked(pane.view_mode == "grid" and abs(ts - size) < 30)
        a = m.addAction(self.icons.glyph("list", 16), "Detalles\tCtrl+2", lambda: pane.set_view("list"))
        a.setCheckable(True)
        a.setChecked(pane.view_mode != "grid")
        m.addSeparator()
        a = m.addAction("Panel de detalles\tAlt+Shift+P", self.toggle_details)
        a.setCheckable(True)
        a.setChecked(self.info_area.isVisible())
        a = m.addAction("Doble panel\tF9", self.toggle_dual)
        a.setCheckable(True)
        a.setChecked(self.paneB.isVisible())
        m.addSeparator()

        def toggle_hidden():
            self.cfg["show_hidden"] = not self.cfg["show_hidden"]
            self.cfg.save()
            for p in self.all_panes:
                p.refresh()
        a = m.addAction("Elementos ocultos", toggle_hidden)
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["show_hidden"]))

        def toggle_sizes():
            self.cfg["folder_sizes"] = not self.cfg["folder_sizes"]
            self.cfg.save()
            if not self.cfg["folder_sizes"]:
                self.dirsizes.clear()
            for p in self.all_panes:
                p.refresh()
        a = m.addAction("Tamaño de carpetas", toggle_sizes)
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
        m.addAction("Seleccionar todo\tCtrl+A", v.selectAll)
        m.addAction("No seleccionar nada", v.clearSelection)

        def invert():
            sel = v.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            for r in range(pane.proxy.rowCount()):
                sel.select(pane.proxy.index(r, 0), QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
        m.addAction("Invertir selección", invert)
        m.addSeparator()
        m.addAction("Copiar ruta  (####)\tCtrl+Shift+C", lambda: self.copy_paths(pane, "hash"))
        m.addAction("Copiar ruta Nuke\tCtrl+Alt+C", lambda: self.copy_paths(pane, "nuke"))
        if pane.current_dir():
            m.addAction("Abrir en el Explorador de Windows", lambda: self.open_default(pane.current_dir()))
            m.addAction("Agregar a acceso rápido", lambda: self.add_favorites([pane.current_dir()]))
        m.addSeparator()
        m.addAction(self.icons.glyph("gear", 16), "Opciones…", self.open_settings)

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
        self.act_dual.setEnabled(not lib)
        self.apply_pipeline_location()
        if lib:
            self.set_active(self.libpane)
            self.libpane.view().setFocus()
            if not self.cfg["library_roots"]:
                self.libpage.viewer.show_message("Elegí la carpeta de tu librería de VFX con el ＋ de «VFX LIBRARY» "
                                                 "en el panel de la izquierda (videos, secuencias, imágenes, HDRIs…).")
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

    def _color_mode_changed(self, _):
        self.cfg["color_mode"] = self.color_mode.currentData()
        self.colors.reload()
        self.save_soon()
        self.refresh_views()
        self._reload_sidebar()

    def apply_pipeline_location(self):
        loc = self.cfg["pipeline_location"] or "center"
        if loc == "top":
            loc = "center"
        self.pipe_frame.setVisible(loc == "center" and self.mode() == "explorer")
        self.side_boxes["pipeline"].setVisible(loc == "sidebar")

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
            QMessageBox.warning(self, APP_NAME, f"No se pudo renombrar:\n{ex}")
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
        self.status.setText(f"Renombrado: {e.name} → {text}")
        return True

    # ------------------------------------------------------------------ paneles
    def set_active(self, pane):
        if pane in self.panes:
            self.explorer_active = pane
        if hasattr(self, "act_sub"):
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
        if show and sum(self.pane_split.sizes()) and min(self.pane_split.sizes()) < 50:
            w = sum(self.pane_split.sizes())
            self.pane_split.setSizes([w // 2, w // 2])
        self.save_soon()

    def switch_pane(self):
        o = self.other(self.active)
        if o:
            self.set_active(o)
            o.view().setFocus()

    def _location_changed(self, pane):
        if pane is not self.active:
            return
        d = pane.current_dir()
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
            self.info.setText(f"<b>{len(ents)} elementos</b><br>{n_files} archivos · {human_size(tot)}")
            self.status_right.setText(f"{len(ents)} seleccionados · {human_size(tot)}")
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
            self.preview.setText("<span style='color:#666'>sin preview</span>")

    def _show_info(self, e):
        self._info_entry = e
        self._set_preview(e)
        rows = [("Tipo", e.type_label())]
        if e.kind == "seq":
            rows.append(("Rango", f"{e.first} – {e.last}"))
            rows.append(("Frames", f"{len(e.frames)}"))
            if e.missing:
                rows.append(("Faltan", f"<span style='color:#ff6b6b'><b>{len(e.missing)}</b>: "
                                       f"{compress_ranges(e.missing)[:600]}</span>"))
            elif "," in compress_ranges(e.frames):
                rows.append(("Tramos", compress_ranges(e.frames)))
        if e.kind != "dir":
            rows.append(("Tamaño", human_size(e.size)))
        rows.append(("Modificado", fmt_time(e.mtime)))
        rows.append(("Carpeta", fwd(e.dirpath)))
        r = self.lib.rating(e.key())
        if r:
            rows.append(("Rating", f"<span style='color:#f5c542'>{'★' * r}</span>"))
        tags = self.lib.tags(e.key())
        if tags:
            rows.append(("Tags", "<span style='color:#8fb3ff'>" + "  ".join("#" + t for t in tags) + "</span>"))
        colls = [n for n, keys in self.lib.collections.items() if e.key() in keys]
        if colls:
            rows.append(("Colecciones", ", ".join(colls)))
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
                self.status.setText(f"No se pudo abrir el reproductor: {ex}")
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
        self.status.setText(f"Copiado: {lines[0]}" + (f"  (+{len(lines) - 1})" if len(lines) > 1 else ""))

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
        self.status.setText(f"{'Cortado' if cut else 'Copiado'}: {n} elemento(s) — Ctrl+V para pegar"
                            f" (también en el Explorador)")

    def op_paste(self, pane, target=None):
        target = target or pane.current_dir()
        if not target:
            return
        paths, cut = fileops.read_clip_mime(QApplication.clipboard().mimeData())
        if not paths:
            self.status.setText("No hay archivos en el portapapeles")
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
        if mods & Qt.ShiftModifier:
            op = "move"
        elif mods & Qt.ControlModifier:
            op = "copy"
        else:
            m = QMenu(self)
            a_copy = m.addAction(f"Copiar aquí  ({len(paths)} archivo(s))")
            a_move = m.addAction("Mover aquí")
            m.addSeparator()
            m.addAction("Cancelar")
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
            QMessageBox.information(self, APP_NAME, "Ya hay una operación en curso.")
            return
        err = fileops.validate_transfer(paths, dest, op)
        if err:
            QMessageBox.warning(self, APP_NAME, err)
            return
        conflicts = fileops.plan_conflicts(paths, dest)
        overwrite = False
        if conflicts:
            names = "\n".join(os.path.basename(c) for c in conflicts[:8]) + ("\n…" if len(conflicts) > 8 else "")
            ans = self._ask("Archivos existentes",
                            f"{len(conflicts)} archivo(s) ya existen en el destino:\n\n{names}",
                            [("Reemplazar", QMessageBox.DestructiveRole), ("Saltear existentes", QMessageBox.AcceptRole),
                             ("Cancelar", QMessageBox.RejectRole)], default="Saltear existentes")
            if ans in (None, "Cancelar"):
                return
            overwrite = ans == "Reemplazar"
        verb = "Copiando" if op == "copy" else "Moviendo"
        dlg = QProgressDialog(f"{verb}…", "Cancelar", 0, 1000, self)
        dlg.setWindowTitle(f"{verb} a {os.path.basename(dest.rstrip(chr(92) + '/')) or dest}")
        dlg.setMinimumDuration(400)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        w = fileops.FileOpWorker(op, paths, dest, overwrite)
        self.op_worker = w

        def prog(done, total, name):
            dlg.setValue(int(1000 * min(1.0, done / max(1, total))))
            dlg.setLabelText(f"{verb}  {name}\n{human_size(done)} de {human_size(total)}")

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
            msg = f"{'Copiados' if op == 'copy' else 'Movidos'} {ok} archivo(s)"
            if cancelled:
                msg += " — cancelado"
            self.status.setText(msg)
            if errors:
                QMessageBox.warning(self, APP_NAME, f"{len(errors)} error(es):\n\n" + "\n".join(errors[:15]))

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
        desc = ents[0].name if len(ents) == 1 else f"{len(ents)} elementos"
        text = f"¿Mandar a la papelera {desc}?" + (f"\n({n_files} archivos)" if n_files > 1 else "")
        if net:
            text += ("\n\n⚠ Está en una unidad de red: Windows lo borra DEFINITIVAMENTE "
                     "(salvo que la papelera de red del NAS esté activada en esa carpeta compartida).")
        ans = self._ask("Mandar a la papelera", text,
                        [("Borrar" if net else "Mandar a la papelera", QMessageBox.DestructiveRole),
                         ("Cancelar", QMessageBox.RejectRole)], default="Cancelar")
        if ans in (None, "Cancelar"):
            return
        w = fileops.TrashWorker(paths)
        self.op_worker = w
        self.status.setText("Borrando…")

        def fin(errors):
            self.op_worker = None
            self.refresh_dirs({e.dirpath for e in ents})
            self.status.setText(f"{desc}: a la papelera" if not errors else "Error al borrar")
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
            QMessageBox.warning(self, APP_NAME, f"No se pudo renombrar:\n{ex}")
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
        name, ok = QInputDialog.getText(self, "Carpeta nueva", "Nombre:", text="nueva carpeta")
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
            self.status.setText(f"Rating {'★' * n if n else 'quitado'} · {len(ents)} elemento(s)")

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
            name, ok = QInputDialog.getText(self, "Colección nueva", "Nombre de la colección:")
            if not ok or not name.strip():
                return
            name = name.strip()
        self.lib.add_to_collection(name, self._targets(ents))
        self._lib_changed()
        self.status.setText(f"{len(ents)} elemento(s) agregados a «{name}»")

    def refs_for(self, kind, name):
        if kind == "tag":
            return self.lib.refs_with_tag(name)
        if kind == "collection":
            return self.lib.refs_in_collection(name)
        if kind == "rating":
            return self.lib.refs_with_rating(int(name))
        return []

    def open_collection(self, name, new_tab=False):
        self.active.show_virtual(f"Colección: {name}", "collection", name, new_tab)

    def open_tag(self, tag, new_tab=False):
        if tag.startswith("★"):
            n = len(tag)
            self.active.show_virtual(f"Rating ≥ {'★' * n}", "rating", n, new_tab)
        else:
            self.active.show_virtual(f"#{tag}", "tag", tag, new_tab)

    # ------------------------------------------------------------------ sidebar
    def _reload_sidebar(self):
        self.favs.clear()
        for p in self.cfg["favorites"]:
            name = os.path.basename(p.rstrip("\\/")) or p
            it = QListWidgetItem(self.icons.folder_icon(self.dir_color(p), 16), name)
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            self.favs.addItem(it)
        self.colls.clear()
        for name, keys in self.lib.collections.items():
            it = QListWidgetItem(self.icons.glyph("grid", 16, "#b98cff"), f"{name}  ({len(keys)})")
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

    def add_favorites(self, paths):
        favs = list(self.cfg["favorites"])
        for p in paths:
            if p and norm_key(p) not in {norm_key(x) for x in favs}:
                favs.append(os.path.normpath(p))
        self.cfg["favorites"] = favs
        self.cfg.save()
        self._reload_sidebar()

    def _favs_reordered(self, *_):
        self.cfg["favorites"] = [self.favs.item(i).data(Qt.UserRole) for i in range(self.favs.count())]
        self.cfg.save()

    def _color_menu(self, menu, targets):
        cm = menu.addMenu("Etiqueta de color")
        for name, hexc in TAG_COLORS:
            cm.addAction(self.icons.swatch(hexc), name, lambda h=hexc: self.set_color(targets, h))
        cm.addSeparator()
        cm.addAction("Quitar color", lambda: self.set_color(targets, None))

    def _favs_menu(self, w, pos):
        it = w.itemAt(pos)
        if not it:
            return
        p = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Abrir", lambda: self.open_in_explorer(p))
        m.addAction("Abrir en pestaña nueva", lambda: self.open_in_explorer(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Abrir en el otro panel", lambda: (self.set_mode("explorer"),
                                                           self.other(self.explorer_active).navigate(p)))
        self._color_menu(m, [dir_target(p)])
        m.addSeparator()

        def remove():
            self.cfg["favorites"] = [x for x in self.cfg["favorites"] if norm_key(x) != norm_key(p)]
            self.cfg.save()
            self._reload_sidebar()
        m.addAction("Quitar de favoritos", remove)
        m.exec(w.viewport().mapToGlobal(pos))

    def _colls_menu(self, w, pos):
        it = w.itemAt(pos)
        m = QMenu(self)
        if it:
            name = it.data(Qt.UserRole)
            m.addAction("Abrir", lambda: self.open_collection(name))
            m.addAction("Abrir en pestaña nueva", lambda: self.open_collection(name, new_tab=True))

            def rename():
                new, ok = QInputDialog.getText(self, "Renombrar colección", "Nombre:", text=name)
                if ok and new.strip():
                    self.lib.rename_collection(name, new.strip())
                    self._lib_changed()

            def delete():
                if self._ask("Borrar colección", f"¿Borrar la colección «{name}»? (los archivos no se tocan)",
                             [("Borrar", QMessageBox.DestructiveRole), ("Cancelar", QMessageBox.RejectRole)],
                             default="Cancelar") == "Borrar":
                    self.lib.delete_collection(name)
                    self._lib_changed()
            m.addAction("Renombrar…", rename)
            m.addAction("Borrar colección", delete)
        else:
            m.addAction("Seleccioná archivos y usá clic derecho › Agregar a colección").setEnabled(False)
        m.exec(w.viewport().mapToGlobal(pos))

    def _tags_menu(self, w, pos):
        it = w.itemAt(pos)
        if not it:
            return
        tag = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Ver", lambda: self.open_tag(tag))
        m.addAction("Ver en pestaña nueva", lambda: self.open_tag(tag, new_tab=True))
        if not tag.startswith("★"):
            def rename():
                new, ok = QInputDialog.getText(self, "Renombrar tag", "Nuevo nombre:", text=tag)
                if ok and new.strip():
                    self.lib.rename_tag(tag, new.strip().lstrip("#"))
                    self._lib_changed()
            m.addAction("Renombrar tag…", rename)
        m.exec(w.viewport().mapToGlobal(pos))

    def _tree_menu(self, pos):
        ix = self.tree.indexAt(pos)
        if not ix.isValid():
            return
        p = self.fs.filePath(ix)
        m = QMenu(self)
        m.addAction("Abrir", lambda: self.open_in_explorer(p))
        m.addAction("Abrir en pestaña nueva", lambda: self.open_in_explorer(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Abrir en el otro panel", lambda: (self.set_mode("explorer"),
                                                           self.other(self.explorer_active).navigate(p)))
        m.addAction("Agregar a favoritos", lambda: self.add_favorites([p]))
        self._color_menu(m, [dir_target(p)])
        m.addAction("Abrir en el Explorador", lambda: self.open_default(p))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ menú contextual de ítems
    def item_menu(self, pane, view, pos):
        self.set_active(pane)
        ix = view.indexAt(pos)
        if ix.isValid() and not view.selectionModel().isSelected(ix):
            view.setCurrentIndex(ix)
        if not ix.isValid():
            view.clearSelection()
        ents = pane.selected_entries()
        m = QMenu(self)
        cur = pane.current_dir()
        if ents and all(e.kind == "drive" for e in ents):
            e = ents[0]
            m.addAction("Abrir", lambda: pane.navigate(e.path))
            m.addAction("Abrir en pestaña nueva", lambda: pane.add_tab(e.path, activate=False))
            m.addAction("Agregar a acceso rápido", lambda: self.add_favorites([x.path for x in ents]))
            m.addAction("Copiar ruta", lambda: QApplication.clipboard().setText(getattr(e, "unc", "") or e.path))
            m.addSeparator()
            m.addAction("Actualizar\tF5", pane.refresh)
            m.exec(view.viewport().mapToGlobal(pos))
            return
        other = self.other(pane)
        clip_paths, _ = fileops.read_clip_mime(QApplication.clipboard().mimeData())
        if ents:
            e = ents[0]
            if e.kind == "dir":
                m.addAction("Abrir", lambda: pane.navigate(e.path))
                m.addAction("Abrir en pestaña nueva", lambda: pane.add_tab(e.path, activate=False))
                if other:
                    m.addAction("Abrir en el otro panel", lambda: other.navigate(e.path))
            else:
                if self.cfg["player"]:
                    m.addAction(f"Abrir en {os.path.splitext(os.path.basename(self.cfg['player']))[0]}",
                                lambda: self.open_entry(e))
                m.addAction("Abrir con programa por defecto", lambda: self.open_entry(e, with_player=False))
            if pane.is_virtual() or pane.model.virtual:
                m.addAction("Ir a la carpeta contenedora",
                            lambda: pane.navigate(e.dirpath, select=e.name))
            m.addAction("Mostrar en el Explorador", lambda: self.reveal(e))
            m.addSeparator()
            m.addAction("Cortar\tCtrl+X", lambda: self.op_clip(pane, cut=True))
            m.addAction("Copiar\tCtrl+C", lambda: self.op_clip(pane, cut=False))
            if clip_paths and e.kind == "dir" and len(ents) == 1:
                m.addAction("Pegar dentro de la carpeta", lambda: self.op_paste(pane, target=e.path))
            if other and other.current_dir():
                m.addAction("Copiar al otro panel", lambda: self.transfer_to_other(pane, "copy"))
                m.addAction("Mover al otro panel", lambda: self.transfer_to_other(pane, "move"))
            if len(ents) == 1:
                m.addAction("Renombrar\tF2", lambda: self.start_inline_rename(pane, view))
                if e.kind == "seq":
                    m.addAction("Renumerar secuencia…", lambda: self.op_rename(pane))
            m.addAction("Mandar a la papelera\tSupr", lambda: self.op_trash(pane))
            m.addSeparator()
            cp = m.addMenu("Copiar ruta")
            cp.addAction("Ruta  (plate.####.exr)\tCtrl+Shift+C", lambda: self.copy_paths(pane, "hash"))
            cp.addAction("Ruta Nuke  (plate.%04d.exr 1001-1100)\tCtrl+Alt+C", lambda: self.copy_paths(pane, "nuke"))
            cp.addAction("Ruta Windows  (con \\)", lambda: self.copy_paths(pane, "win"))
            cp.addAction("Primer frame", lambda: self.copy_paths(pane, "first"))
            cp.addAction("Carpeta", lambda: self.copy_paths(pane, "dir"))
            cp.addAction("Solo nombre", lambda: self.copy_paths(pane, "name"))
            m.addSeparator()
            targets = self._targets(ents)
            self._color_menu(m, targets)
        if ents and self.cfg["library_features"]:
            rm = m.addMenu("Rating")
            for n in range(5, 0, -1):
                rm.addAction("★" * n + f"\tCtrl+{n}", lambda n=n: self.op_rating(pane, n))
            rm.addAction("Sin rating\tCtrl+0", lambda: self.op_rating(pane, 0))
            m.addAction("Tags…\tCtrl+E", lambda: self.op_tags(pane))
            cm = m.addMenu("Agregar a colección")
            for name in self.lib.collections:
                cm.addAction(name, lambda n=name: self.add_to_collection(ents, n))
            if self.lib.collections:
                cm.addSeparator()
            cm.addAction("Colección nueva…", lambda: self.add_to_collection(ents))
        if ents:
            vinfo = pane.virtual_info()
            if vinfo and vinfo["kind"] == "collection":
                m.addAction("Quitar de la colección", lambda: (
                    self.lib.remove_from_collection(vinfo["name"], [x.key() for x in ents]),
                    self._lib_changed(), pane.refresh()))
            dirs = [x for x in ents if x.kind == "dir"]
            if dirs and self.mode() == "explorer":
                if self.libpane.allowed(dirs[0].path):
                    m.addAction("Ver en VFX Library", lambda: self.open_library(dirs[0].path))
                else:
                    m.addAction("Agregar a la VFX Library", lambda: self.open_library(dirs[0].path))
            if dirs:
                m.addAction("Agregar a favoritos", lambda: self.add_favorites([d.path for d in dirs]))
            m.addSeparator()
        if cur:
            if clip_paths:
                m.addAction(f"Pegar ({len(clip_paths)} archivo(s))\tCtrl+V", lambda: self.op_paste(pane))
            m.addAction("Carpeta nueva…\tCtrl+Shift+N", lambda: self.op_new_folder(pane))
            m.addAction("Agregar esta carpeta a favoritos", lambda: self.add_favorites([cur]))
        if cur and self.mode() == "explorer":
            m.addAction("Ver en VFX Library" if self.libpane.allowed(cur) else "Agregar esta carpeta a la VFX Library",
                        lambda: self.open_library(cur))
        m.addAction("Refrescar\tF5", pane.refresh)
        m.exec(view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ configuración
    def open_settings(self):
        d = SettingsDialog(self, self)
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
            self.color_mode.blockSignals(True)
            self.color_mode.setCurrentIndex(max(0, self.color_mode.findData(self.cfg["color_mode"])))
            self.color_mode.blockSignals(False)
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
