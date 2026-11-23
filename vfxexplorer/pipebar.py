# -*- coding: utf-8 -*-
"""Barra de pipeline: Proyecto → Secuencia → Shot → Departamento (3D, Comp, DMP…) → Task.
Se puede mostrar arriba (horizontal) o en el panel izquierdo (vertical)."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QGridLayout, QLabel, QComboBox, QToolButton, QMenu,
                               QSizePolicy)

from .core import norm_key

LEVELS = (("proj", "Proyecto"), ("seq", "Secuencia"), ("shot", "Shot"), ("dept", "Depto"), ("task", "Task"))


class PipelineBar(QWidget):
    def __init__(self, app, vertical=False):
        super().__init__()
        self.app = app
        self.pipe = app.pipeline
        self.vertical = vertical
        self.cbs = {}
        for key, ph in LEVELS:
            cb = QComboBox()
            cb.setPlaceholderText(ph)
            cb.setToolTip(ph if key != "dept" else "Departamento: carpetas al nivel de 3D (3D, Comp, DMP, 2D…)")
            cb.activated.connect(lambda _, k=key: self._pick(k))
            if vertical:
                cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                cb.setMinimumContentsLength(6)
                cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            else:
                cb.setMinimumWidth({"proj": 90, "seq": 80, "shot": 170, "dept": 80, "task": 120}[key])
                cb.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            self.cbs[key] = cb
        self.folder = QToolButton()
        self.folder.setIcon(app.icons.glyph("folder", 16))
        self.folder.setToolTip("Ir a carpetas del shot / depto / task")
        self.folder.setPopupMode(QToolButton.InstantPopup)
        self.folder.setAutoRaise(True)
        self.menu = QMenu(self.folder)
        self.menu.aboutToShow.connect(self._fill_menu)
        self.folder.setMenu(self.menu)

        if vertical:
            g = QGridLayout(self)
            g.setContentsMargins(8, 2, 8, 6)
            g.setHorizontalSpacing(6)
            g.setVerticalSpacing(3)
            for r, (key, ph) in enumerate(LEVELS):
                l = QLabel(ph)
                l.setStyleSheet("color:#9d9d9d; font-size:8pt;")
                g.addWidget(l, r, 0)
                g.addWidget(self.cbs[key], r, 1)
            g.addWidget(self.folder, 0, 2)
            g.setColumnStretch(1, 1)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(4)
            lbl = QLabel("PIPELINE")
            lbl.setStyleSheet("color:#b98cff; font-weight:bold; font-size:8pt; letter-spacing:1px;")
            lay.addWidget(lbl)
            for key, _ in LEVELS:
                lay.addWidget(self.cbs[key])
            lay.addWidget(self.folder)
        self.reload()

    # ---------------- util
    def _v(self, k):
        return self.cbs[k].currentText()

    def _vals(self):
        return tuple(self._v(k) for k, _ in LEVELS)

    def _fill(self, key, items, current=None):
        cb = self.cbs[key]
        cb.blockSignals(True)
        cb.clear()
        cb.addItems(items)
        cb.setCurrentIndex(cb.findText(current) if current in items else -1)
        cb.blockSignals(False)

    def reload(self):
        ok = self.pipe.available()
        for cb in self.cbs.values():
            cb.setEnabled(ok)
        self.folder.setEnabled(ok)
        if not ok:
            self.setToolTip(f"No se encontró la raíz del pipeline: {self.pipe.base()} (ver Configuración › Pipeline)")
            return
        self.setToolTip(f"Raíz: {self.pipe.base()}  ·  config: {self.pipe.source}")
        self._fill("proj", self.pipe.projects(), self._v("proj"))

    # ---------------- elegir un nivel = navegar ahí
    def _pick(self, level):
        p, s, sh, d, t = self._vals()
        pipe = self.pipe
        if level == "proj":
            self._fill("seq", pipe.sequences(p))
            for k in ("shot", "dept", "task"):
                self._fill(k, [])
            target = pipe.project_dir(p)
        elif level == "seq":
            self._fill("shot", pipe.shots(p, s))
            self._fill("dept", [])
            self._fill("task", [])
            target = pipe.seq_dir(p, s)
        elif level == "shot":
            self._fill("dept", pipe.depts(p, s, sh))
            self._fill("task", [])
            target = pipe.shot_dir(p, s, sh)
        elif level == "dept":
            self._fill("task", pipe.tasks(p, s, sh, d))
            target = pipe.dept_dir(p, s, sh, d)
        else:
            target = pipe.task_dir(p, s, sh, t, d)
        if target and os.path.isdir(target):
            self.app.open_in_explorer(target)

    def sync(self, path):
        """Pone los combos según la carpeta actual (sin navegar)."""
        if not path or not self.pipe.available():
            return
        info = self.pipe.parse(path)
        if not info or not norm_key(path).startswith(norm_key(self.pipe.project_dir(info["project"]))):
            self.clear()
            return
        pipe = self.pipe
        p = info["project"]
        if self.cbs["proj"].findText(p) < 0:
            self._fill("proj", pipe.projects(), p)
        else:
            cb = self.cbs["proj"]
            cb.blockSignals(True)
            cb.setCurrentText(p)
            cb.blockSignals(False)
        self._fill("seq", pipe.sequences(p), info["seq"])
        s = self._v("seq")
        self._fill("shot", pipe.shots(p, s) if s else [], info["shot"])
        sh = self._v("shot")
        self._fill("dept", pipe.depts(p, s, sh) if sh else [], info["dept"])
        d = self._v("dept")
        self._fill("task", pipe.tasks(p, s, sh, d) if d else [], info["task"])

    def clear(self):
        """Carpeta fuera del pipeline: combos vacíos (la lista de proyectos queda para elegir)."""
        cb = self.cbs["proj"]
        cb.blockSignals(True)
        cb.setCurrentIndex(-1)
        cb.blockSignals(False)
        for k in ("seq", "shot", "dept", "task"):
            self._fill(k, [])

    def _fill_menu(self):
        m = self.menu
        m.clear()
        p, s, sh, d, t = self._vals()
        pipe = self.pipe

        def add(label, path, indent=0):
            a = m.addAction(("    " * indent) + label)
            ok = bool(path) and os.path.isdir(path)
            a.setEnabled(ok)
            if path:
                a.setToolTip(path)
            a.triggered.connect(lambda c=False, x=path: self.app.open_in_explorer(x))
            return a

        if not p:
            m.addAction("Elegí un proyecto").setEnabled(False)
            return
        add(f"Proyecto  {p}", pipe.project_dir(p))
        if s:
            add(f"Secuencia  {s}", pipe.seq_dir(p, s))
        if sh:
            m.addSeparator()
            add(f"Shot  {sh}", pipe.shot_dir(p, s, sh))
            for dd in pipe.shot_subdirs(p, s, sh):
                add(dd, os.path.join(pipe.shot_dir(p, s, sh), dd), 1)
        if d:
            m.addSeparator()
            dd = pipe.dept_dir(p, s, sh, d)
            add(f"Depto  {d}", dd)
            for x in pipe.tasks(p, s, sh, d):
                add(x, os.path.join(dd, x), 1)
        if t:
            m.addSeparator()
            td = pipe.task_dir(p, s, sh, t, d)
            add(f"Task  {t}", td)
            subs = pipe.subfolders()
            existing = pipe.task_subdirs(p, s, sh, t, d)
            for x in subs + [e for e in existing if e not in subs]:
                add(x, os.path.join(td, x), 1)
            if os.path.isdir(td):
                m.addAction("    ↗ abrir el task en pestaña nueva", lambda: self.app.open_in_explorer(td, new_tab=True))
        m.setToolTipsVisible(True)
