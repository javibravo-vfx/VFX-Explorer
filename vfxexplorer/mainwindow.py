# -*- coding: utf-8 -*-
"""Ventana principal: barra de pipeline, sidebar (favoritos, colecciones, tags, carpetas), paneles e info."""

import os
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QByteArray, QDir, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices, QCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView,
                               QListWidget, QListWidgetItem, QComboBox, QSlider, QToolBar, QLabel, QMenu,
                               QFileSystemModel, QAbstractItemView, QToolButton, QScrollArea, QFrame,
                               QMessageBox, QInputDialog, QProgressDialog, QStyledItemDelegate, QSizePolicy, QStyleOptionViewItem)

from . import APP_NAME, VERSION
from .core import (Config, IS_WIN, data_dir, norm_key, fwd, human_size, fmt_time, compress_ranges, find_tool,
                   same_path, Entry)
from .library import Library, dir_target
from .pipeline import Pipeline
from .imaging import ThumbManager, InfoTask, Signals, init_formats
from .widgets import Icons, TAG_COLORS, TagDialog, RenameDialog, SettingsDialog, ACCENT
from .pane import FilePane
from . import fileops


# ----------------------------------------------------------------------------
# Barra de pipeline (misma lógica que Studio Toolbar)
# ----------------------------------------------------------------------------

class PipelineBar(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pipe = app.pipeline
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(4)
        lbl = QLabel("PIPELINE")
        lbl.setStyleSheet("color:#b98cff; font-weight:bold; font-size:8pt; letter-spacing:1px;")
        lay.addWidget(lbl)
        self.proj, self.seq, self.shot, self.task = (QComboBox() for _ in range(4))
        for cb, ph, w in ((self.proj, "Proyecto", 100), (self.seq, "Secuencia", 90),
                          (self.shot, "Shot", 190), (self.task, "Task", 130)):
            cb.setPlaceholderText(ph)
            cb.setMinimumWidth(w)
            cb.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            cb.setToolTip(ph)
            lay.addWidget(cb)
        self.proj.activated.connect(lambda _: self._pick("proj"))
        self.seq.activated.connect(lambda _: self._pick("seq"))
        self.shot.activated.connect(lambda _: self._pick("shot"))
        self.task.activated.connect(lambda _: self._pick("task"))
        self.folder = QToolButton()
        self.folder.setIcon(app.icons.glyph("folder", 18))
        self.folder.setToolTip("Ir a carpetas del shot / task")
        self.folder.setPopupMode(QToolButton.InstantPopup)
        self.folder.setAutoRaise(True)
        self.menu = QMenu(self.folder)
        self.menu.aboutToShow.connect(self._fill_menu)
        self.folder.setMenu(self.menu)
        lay.addWidget(self.folder)
        self.reload()

    def _vals(self):
        return self.proj.currentText(), self.seq.currentText(), self.shot.currentText(), self.task.currentText()

    def _fill(self, cb, items, current=None):
        cb.blockSignals(True)
        cb.clear()
        cb.addItems(items)
        cb.setCurrentIndex(cb.findText(current) if current in items else -1)
        cb.blockSignals(False)

    def reload(self):
        ok = self.pipe.available()
        for cb in (self.proj, self.seq, self.shot, self.task):
            cb.setEnabled(ok)
        self.folder.setEnabled(ok)
        if not ok:
            self.setToolTip(f"No se encontró la raíz del pipeline: {self.pipe.base()} (ver Configuración › Pipeline)")
            return
        self.setToolTip(f"Raíz: {self.pipe.base()}  ·  config: {self.pipe.source}")
        cur = self.proj.currentText()
        self._fill(self.proj, self.pipe.projects(), cur)

    def _pick(self, level):
        p, s, sh, t = self._vals()
        pipe = self.pipe
        if level == "proj":
            self._fill(self.seq, pipe.sequences(p))
            self._fill(self.shot, [])
            self._fill(self.task, [])
            target = pipe.project_dir(p)
        elif level == "seq":
            self._fill(self.shot, pipe.shots(p, s))
            self._fill(self.task, [])
            target = pipe.seq_dir(p, s)
        elif level == "shot":
            tasks = pipe.tasks(p, s, sh)
            self._fill(self.task, tasks)
            target = pipe.shot_dir(p, s, sh)
        else:
            target = pipe.task_dir(p, s, sh, t)
        if target and os.path.isdir(target):
            self.app.active.navigate(target)

    def sync(self, path):
        """Pone los combos según la carpeta actual (sin navegar)."""
        if not path or not self.pipe.available():
            return
        info = self.pipe.parse(path)
        if not info or not same_path(os.path.dirname(self.pipe.project_dir(info["project"])), self.pipe.base()) and \
                not norm_key(path).startswith(norm_key(self.pipe.project_dir(info["project"]))):
            return
        pipe = self.pipe
        if self.proj.findText(info["project"]) < 0:
            self._fill(self.proj, pipe.projects(), info["project"])
        else:
            self.proj.blockSignals(True)
            self.proj.setCurrentText(info["project"])
            self.proj.blockSignals(False)
        p = info["project"]
        self._fill(self.seq, pipe.sequences(p), info["seq"])
        s = self.seq.currentText()
        self._fill(self.shot, pipe.shots(p, s) if s else [], info["shot"])
        sh = self.shot.currentText()
        self._fill(self.task, pipe.tasks(p, s, sh) if sh else [], info["task"])

    def _fill_menu(self):
        m = self.menu
        m.clear()
        p, s, sh, t = self._vals()
        pipe = self.pipe

        def add(label, path, indent=0):
            a = m.addAction(("    " * indent) + label)
            ok = bool(path) and os.path.isdir(path)
            a.setEnabled(ok)
            if path:
                a.setToolTip(path)
            a.triggered.connect(lambda c=False, x=path: self.app.active.navigate(x))
            return a

        def add_newtab(label, path):
            if path and os.path.isdir(path):
                m.addAction("    ↗ " + label + " en pestaña nueva",
                            lambda x=path: self.app.active.navigate(x, new_tab=True))

        if not p:
            m.addAction("Elegí un proyecto").setEnabled(False)
            return
        add(f"Proyecto  {p}", pipe.project_dir(p))
        if s:
            add(f"Secuencia  {s}", pipe.seq_dir(p, s))
        if sh:
            m.addSeparator()
            add(f"Shot  {sh}", pipe.shot_dir(p, s, sh))
            for d in pipe.shot_subdirs(p, s, sh):
                add(d, os.path.join(pipe.shot_dir(p, s, sh), d), 1)
        if t:
            m.addSeparator()
            td = pipe.task_dir(p, s, sh, t)
            add(f"Task  {t}", td)
            subs = pipe.subfolders()
            existing = pipe.task_subdirs(p, s, sh, t)
            for d in subs + [x for x in existing if x not in subs]:
                add(d, os.path.join(td, d), 1)
            add_newtab(t, td)
        m.setToolTipsVisible(True)


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
        self.icons = Icons()
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
        tb = QToolBar("Principal")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)
        self.pipebar = PipelineBar(self)
        tb.addWidget(self.pipebar)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.act_dual = tb.addAction(ic.glyph("dual"), "Doble panel (F9)", self.toggle_dual)
        self.act_dual.setCheckable(True)
        tb.addSeparator()
        szl = QLabel("Tamaño")
        szl.setStyleSheet("color:#7d8590; font-size:8pt;")
        tb.addWidget(szl)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(96, 320)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setValue(int(self.cfg["thumb_size"]))
        self.size_slider.valueChanged.connect(self._on_thumb_size)
        tb.addWidget(self.size_slider)
        tb.addSeparator()
        tb.addAction(ic.glyph("gear"), "Configuración", self.open_settings)

        # sidebar
        self.favs = self._mk_list(self._favs_menu, lambda it: self.active.navigate(it.data(Qt.UserRole)))
        self.favs.setDragDropMode(QAbstractItemView.InternalMove)
        self.favs.model().rowsMoved.connect(self._favs_reordered)
        self.colls = self._mk_list(self._colls_menu, lambda it: self.open_collection(it.data(Qt.UserRole)))
        self.tagl = self._mk_list(self._tags_menu, lambda it: self.open_tag(it.data(Qt.UserRole)))

        self.tree = QTreeView()
        self.tree.setModel(self.fs)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.clicked.connect(lambda ix: self.active.navigate(self.fs.filePath(ix)))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.setItemDelegate(_TreeColorDelegate(self, self.tree))

        left = QSplitter(Qt.Vertical)
        for title, w in (("FAVORITOS", self.favs), ("COLECCIONES", self.colls), ("TAGS", self.tagl),
                         ("CARPETAS", self.tree)):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(1)
            bl.addWidget(self._section(title))
            bl.addWidget(w)
            left.addWidget(box)
        left.setSizes([130, 110, 130, 420])
        left.setMinimumWidth(180)
        self.left_split = left

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
        sa.setWidget(iw)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setMinimumWidth(240)

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.pane_split)
        main.addWidget(sa)
        main.setStretchFactor(1, 1)
        main.setSizes([250, 960, 300])
        main.setCollapsible(0, False)
        self.main_split = main
        self.setCentralWidget(main)

        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.status_right = QLabel()
        self.statusBar().addPermanentWidget(self.status_right)

        self.setStyleSheet(f"""
            #pane {{ border-top:2px solid transparent; }}
            #pane[active="true"] {{ border-top:2px solid {ACCENT}; }}
            #paneHeader {{ background:#202125; }}
            #paneFooter {{ color:#8b9099; font-size:8pt; padding:2px 8px; background:#1d1e21; }}
        """)
        QShortcut(QKeySequence("F9"), self, self.toggle_dual)
        QShortcut(QKeySequence("F6"), self, self.switch_pane)
        self._reload_sidebar()

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
        for k, sp in (("splitter", self.main_split), ("splitter_left", self.left_split),
                      ("splitter_panes", self.pane_split)):
            if self.cfg[k]:
                sp.restoreState(QByteArray.fromBase64(self.cfg[k].encode()))
        states = self.cfg["panes"] or []
        home = QDir.homePath()
        fallback = start_path if start_path and os.path.isdir(start_path) else home
        a_state = states[0] if states else None
        if start_path and os.path.isdir(start_path):
            a_state = {"tabs": [{"path": start_path}], "current": 0, "view": (a_state or {}).get("view", "grid")}
        self.paneA.restore(a_state, fallback)
        self.paneB.restore(states[1] if len(states) > 1 else None, fallback)
        if self.cfg["dual"]:
            self.toggle_dual(force=True)
        self.set_active(self.paneA)

    def _save_now(self):
        self.cfg["panes"] = [p.state() for p in self.panes]
        self.cfg["dual"] = self.paneB.isVisible()
        self.cfg.save()
        self.lib.save()

    def save_soon(self):
        self.save_timer.start()

    def closeEvent(self, ev):
        self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.cfg["splitter"] = bytes(self.main_split.saveState().toBase64()).decode()
        self.cfg["splitter_left"] = bytes(self.left_split.saveState().toBase64()).decode()
        self.cfg["splitter_panes"] = bytes(self.pane_split.saveState().toBase64()).decode()
        self._save_now()
        for p in self.panes:
            p._stop_search()
        self.thumbs.cancel_pending()
        super().closeEvent(ev)

    # ------------------------------------------------------------------ paneles
    def set_active(self, pane):
        if pane is not self.active or not pane.property("active"):
            self.active = pane
            for p in self.panes:
                p.set_active(p is pane and self.paneB.isVisible())
            self._location_changed(pane)
            self._sel_changed(pane)
            self._pane_status(pane)

    def other(self, pane):
        if not self.paneB.isVisible():
            return None
        return self.paneB if pane is self.paneA else self.paneA

    def toggle_dual(self, force=None):
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
        if d:
            ix = self.fs.index(d)
            if ix.isValid():
                self.tree.setCurrentIndex(ix)
                self.tree.scrollTo(ix)
            self.pipebar.sync(d)
            self.setWindowTitle(f"{os.path.basename(d.rstrip(chr(92) + '/')) or d} — {APP_NAME} {VERSION}")

    def _pane_status(self, pane):
        if pane is self.active:
            self.status.setText(pane.status_text)

    def _on_thumb_size(self, v):
        for p in self.panes:
            p.set_thumb_size(v)
        self.thumbs.scaled.clear()
        self.cfg["thumb_size"] = v
        self.save_soon()

    def refresh_views(self):
        for p in self.panes:
            p.model.refresh_all()
            p.grid.viewport().update()
        self.tree.viewport().update()

    def refresh_dirs(self, dirs):
        keys = {norm_key(d) for d in dirs if d}
        for p in self.panes:
            if p.isVisible() or p is self.paneA:
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
        for p in self.panes:
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
        self._lib_changed()

    def op_rating(self, pane, n):
        ents = pane.selected_entries()
        if ents:
            self.lib.set_rating(self._targets(ents), n)
            self._lib_changed()
            self.status.setText(f"Rating {'★' * n if n else 'quitado'} · {len(ents)} elemento(s)")

    def op_tags(self, pane):
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
            it = QListWidgetItem(self.icons.folder_icon(self.lib.color(norm_key(p)), 16), name)
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
        m.addAction("Abrir", lambda: self.active.navigate(p))
        m.addAction("Abrir en pestaña nueva", lambda: self.active.navigate(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Abrir en el otro panel", lambda: self.other(self.active).navigate(p))
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
        m.addAction("Abrir", lambda: self.active.navigate(p))
        m.addAction("Abrir en pestaña nueva", lambda: self.active.navigate(p, new_tab=True))
        if self.paneB.isVisible():
            m.addAction("Abrir en el otro panel", lambda: self.other(self.active).navigate(p))
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
                m.addAction("Renumerar / renombrar…\tF2" if e.kind == "seq" else "Renombrar…\tF2",
                            lambda: self.op_rename(pane))
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
            vinfo = pane.virtual_info()
            if vinfo and vinfo["kind"] == "collection":
                m.addAction("Quitar de la colección", lambda: (
                    self.lib.remove_from_collection(vinfo["name"], [x.key() for x in ents]),
                    self._lib_changed(), pane.refresh()))
            dirs = [x for x in ents if x.kind == "dir"]
            if dirs:
                m.addAction("Agregar a favoritos", lambda: self.add_favorites([d.path for d in dirs]))
            m.addSeparator()
        if cur:
            if clip_paths:
                m.addAction(f"Pegar ({len(clip_paths)} archivo(s))\tCtrl+V", lambda: self.op_paste(pane))
            m.addAction("Carpeta nueva…\tCtrl+Shift+N", lambda: self.op_new_folder(pane))
            m.addAction("Agregar esta carpeta a favoritos", lambda: self.add_favorites([cur]))
        m.addAction("Refrescar\tF5", pane.refresh)
        m.exec(view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ configuración
    def open_settings(self):
        d = SettingsDialog(self, self)
        if d.exec():
            thumbs_changed, hidden_changed, pipe_changed = d.apply()
            self.thumbs.reload_settings()
            if thumbs_changed:
                self.thumbs.forget()
                self.refresh_views()
            if pipe_changed:
                self.pipeline.reload()
                self.pipebar.reload()
            if hidden_changed:
                for p in self.panes:
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
