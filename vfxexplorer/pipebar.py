# -*- coding: utf-8 -*-
"""Barra de pipeline: Proyecto → Secuencia → Shot → Departamento (3D, Comp, DMP…) → Task.
Se puede mostrar arriba (horizontal) o en el panel izquierdo (vertical)."""

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QGridLayout, QLabel, QComboBox, QToolButton, QMenu,
                               QSizePolicy)

from .core import norm_key

LEVELS = (("proj", "Project"), ("seq", "Sequence"), ("shot", "Shot"), ("dept", "Dept"), ("task", "Task"))


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
            cb.setToolTip(ph if key != "dept" else "Department: folders at the 3D level (3D, Comp, DMP, 2D…)")
            cb.activated.connect(lambda _, k=key: self._pick(k))
            cb.view().viewport().installEventFilter(self)     # botón del medio en la lista: en un tab nuevo
            cb.view().viewport().setProperty("pipe_level", key)
            if vertical:
                cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                cb.setMinimumContentsLength(6)
                cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            else:
                cb.setMinimumWidth({"proj": 60, "seq": 60, "shot": 80, "dept": 50, "task": 60}[key])
                cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                cb.setMinimumContentsLength(4)
            self.cbs[key] = cb
        self.add_b = QToolButton()
        self.add_b.setIcon(app.icons.glyph("plus", 16, "#4cc2ff"))
        self.add_b.setToolTip("Create a task or a department folder in this shot")
        self.add_b.setPopupMode(QToolButton.InstantPopup)
        self.add_b.setAutoRaise(True)
        self.add_menu = QMenu(self.add_b)
        self.add_menu.aboutToShow.connect(self._fill_add_menu)
        self.add_b.setMenu(self.add_menu)
        self.folder = QToolButton()
        self.folder.setIcon(app.icons.glyph("folder", 16))
        self.folder.setToolTip("Go to shot / dept / task folders")
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
            g.addWidget(self.add_b, 1, 2)
            g.addWidget(self.folder, 0, 2)
            g.setColumnStretch(1, 1)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(4)
            lbl = QLabel("PIPELINE")
            lbl.setStyleSheet("color:#4cc2ff; font-weight:bold; font-size:8pt; letter-spacing:1px;")
            lay.addWidget(lbl)
            lay.addSpacing(6)
            stretch = {"proj": 3, "seq": 2, "shot": 4, "dept": 2, "task": 3}
            for n, (key, _) in enumerate(LEVELS):
                if n:
                    d = QLabel("›")
                    d.setStyleSheet("color:#5f6368; font-size:13pt; padding:0 2px 2px 2px;")
                    lay.addWidget(d)
                lay.addWidget(self.cbs[key], stretch[key])
            lay.addSpacing(4)
            lay.addWidget(self.add_b)
            lay.addWidget(self.folder)
        self.reload()

    # ---------------- util
    @staticmethod
    def pretty(key, name):
        """Solo para mostrar en el dropdown: _input → INPUT, comp → COMP, 8_lighting → Lighting."""
        if key == "dept":
            return name.lstrip("_").upper() or name
        if key == "task":
            t = re.sub(r"^\d+[_\-. ]*", "", name).replace("_", " ").strip()
            return (t[:1].upper() + t[1:]) if t else name
        return name

    def _v(self, k):
        cb = self.cbs[k]
        v = cb.currentData()
        return v if v is not None else (cb.currentText() if cb.currentIndex() >= 0 else "")

    def _vals(self):
        return tuple(self._v(k) for k, _ in LEVELS)

    def _fill(self, key, items, current=None):
        cb = self.cbs[key]
        cb.blockSignals(True)
        cb.clear()
        for it in items:
            cb.addItem(self.pretty(key, it), it)
            cb.setItemData(cb.count() - 1, it, Qt.ToolTipRole)
        cb.setCurrentIndex(cb.findData(current) if current in items else -1)
        cb.blockSignals(False)

    def reload(self):
        ok = self.pipe.available()
        for cb in self.cbs.values():
            cb.setEnabled(ok)
        self.folder.setEnabled(ok)
        self.add_b.setEnabled(ok)
        if not ok:
            self.setToolTip(f"Pipeline root not found: {self.pipe.base()} (see Settings › Pipeline)")
            return
        self.setToolTip(f"Root: {self.pipe.base()}  ·  config: {self.pipe.source}")
        self._fill("proj", self.pipe.projects(), self._v("proj"))

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        key = obj.property("pipe_level") if hasattr(obj, "property") else None
        if key and ev.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) \
                and ev.button() == Qt.MiddleButton:
            if ev.type() == QEvent.MouseButtonRelease:
                cb = self.cbs[key]
                ix = cb.view().indexAt(ev.position().toPoint())
                if ix.isValid():
                    cb.setCurrentIndex(ix.row())
                    cb.hidePopup()
                    self._pick(key, new_tab=True)
            return True
        return super().eventFilter(obj, ev)

    # ---------------- elegir un nivel = navegar ahí
    def _pick(self, level, new_tab=False):
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
            target = self._same_place(p, s, sh) or pipe.shot_dir(p, s, sh)
        elif level == "dept":
            self._fill("task", pipe.tasks(p, s, sh, d))
            self._task_label(p, s, sh, d)
            target = pipe.dept_dir(p, s, sh, d)
        else:
            target = pipe.task_dir(p, s, sh, t, d)
        if target and os.path.isdir(target):
            self.app.open_in_explorer(target, new_tab=new_tab)

    def _same_place(self, p, s, sh):
        """Al cambiar de shot, entrar al mismo lugar (depto, task, stage, _input…) si existe en el shot nuevo."""
        cur = self.app.explorer_active.current_dir()
        info = self.pipe.parse(cur) if cur else None
        if not info or not info["shot"] or info["shot"] == sh:
            return ""
        old = self.pipe.shot_dir(info["project"], info["seq"], info["shot"])
        try:
            rel = os.path.relpath(cur, old)
        except ValueError:
            return ""
        if rel in (".", "") or rel.startswith(".."):
            return ""
        new = self.pipe.shot_dir(p, s, sh)
        parts = [x.replace(info["shot"], sh) for x in rel.split(os.sep)]
        while parts:
            cand = os.path.join(new, *parts)
            if os.path.isdir(cand):
                return cand
            parts.pop()
        return ""

    def _task_label(self, p, s, sh, d):
        kind = self.pipe.dept_kind(p, s, sh, d) if d else "task"
        cb = self.cbs["task"]
        cb.setPlaceholderText({"task": "Task", "stage": "Stage", "folder": "Shot"}[kind])
        cb.setToolTip({"task": "Tasks of the department",
                       "stage": "This department has no tasks: projects / review / publish",
                       "folder": "Folders of " + d}[kind] if d else "Task")
        return kind

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
        if self.cbs["proj"].findData(p) < 0:
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
        self._task_label(p, s, sh, d)

    def clear(self):
        """Carpeta fuera del pipeline: combos vacíos (la lista de proyectos queda para elegir)."""
        cb = self.cbs["proj"]
        cb.blockSignals(True)
        cb.setCurrentIndex(-1)
        cb.blockSignals(False)
        for k in ("seq", "shot", "dept", "task"):
            self._fill(k, [])
        self.cbs["task"].setPlaceholderText("Task")

    # ---------------- ＋ crear 3D task / DMP / Comp
    def _fill_add_menu(self):
        m = self.add_menu
        m.clear()
        p, s, sh, d, t = self._vals()
        pipe = self.pipe
        if not sh:
            m.addAction("Pick a shot first").setEnabled(False)
            return
        inp = pipe.input_name()
        ex = os.path.isdir(pipe.input_dir(p, s, sh))
        a = m.addAction(("✓  " if ex else "") + inp + "   (plates)")
        a.setEnabled(not ex)
        a.setToolTip(inp + " \\ " + ", ".join(pipe.input_subs()))
        a.triggered.connect(lambda: self._create("__input__"))
        m.addSeparator()
        for dep in pipe.departments():
            name = dep["name"].strip()
            path = pipe.dept_path(p, s, sh, name)
            exists = os.path.isdir(path)
            if dep.get("has_tasks"):
                have = {x.lower() for x in pipe.tasks(p, s, sh, os.path.basename(path))} if exists else set()
                sub = m.addMenu(f"{name} task")
                for task, _inner in pipe.dept_tasks(name):
                    a = sub.addAction(("✓  " if task.lower() in have else "     ") + task)
                    a.setEnabled(task.lower() not in have)
                    a.triggered.connect(lambda c=False, n=name, x=task: self._create(n, x))
                if not pipe.dept_tasks(name):
                    sub.addAction("No tasks (Settings › Pipeline)").setEnabled(False)
            else:
                a = m.addAction(("✓  " if exists else "") + name)
                a.setEnabled(not exists)
                a.setToolTip(name + " \\ " + ", ".join(pipe.dept_folders(name)))
                a.triggered.connect(lambda c=False, n=name: self._create(n))
        if not pipe.departments():
            m.addAction("No departments (Settings › Pipeline)").setEnabled(False)
        m.addSeparator()
        m.addAction("Edit departments…", lambda: self.app.open_settings("Pipeline"))
        m.setToolTipsVisible(True)

    def _create(self, dept, task=None):
        p, s, sh, d, t = self._vals()
        try:
            if dept == "__input__":
                target = self.pipe.create_input(p, s, sh)
            elif task:
                target = self.pipe.create_task(p, s, sh, dept, task)
            else:
                target = self.pipe.create_dept(p, s, sh, dept)
        except OSError as ex:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Pipeline", f"Could not create the folders:\n{ex}")
            return
        if target:
            self.app.status.setText(f"Created {target}")
            self.app.open_in_explorer(target)
            self.sync(target)

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
            m.addAction("Pick a project").setEnabled(False)
            return
        add(f"Project  {p}", pipe.project_dir(p))
        if s:
            add(f"Sequence  {s}", pipe.seq_dir(p, s))
        if sh:
            m.addSeparator()
            add(f"Shot  {sh}", pipe.shot_dir(p, s, sh))
            pd = pipe.plates_dir(p, s, sh)
            if pd and os.path.isdir(pd):
                add("Plates  ▸  " + os.path.relpath(pd, pipe.shot_dir(p, s, sh)), pd, 1)
            for dd in pipe.shot_subdirs(p, s, sh):
                add(dd, os.path.join(pipe.shot_dir(p, s, sh), dd), 1)
        if d:
            m.addSeparator()
            dd = pipe.dept_dir(p, s, sh, d)
            add(f"Dept  {d}", dd)
            for x in pipe.tasks(p, s, sh, d):
                add(x, os.path.join(dd, x), 1)
        kind = pipe.dept_kind(p, s, sh, d) if d else "task"
        if t and kind != "task":
            m.addSeparator()
            td = pipe.task_dir(p, s, sh, t, d)
            add(f"{'Stage' if kind == 'stage' else 'Folder'}  {t}", td)
            for x in pipe.task_subdirs(p, s, sh, t, d):
                add(x, os.path.join(td, x), 1)
        elif t:
            m.addSeparator()
            td = pipe.task_dir(p, s, sh, t, d)
            add(f"Task  {t}", td)
            subs = pipe.dept_folders(d)
            existing = pipe.task_subdirs(p, s, sh, t, d)
            for x in subs + [e for e in existing if e not in subs]:
                add(x, os.path.join(td, x), 1)
            if os.path.isdir(td):
                m.addAction("    ↗ open the task in a new tab", lambda: self.app.open_in_explorer(td, new_tab=True))
        m.setToolTipsVisible(True)
