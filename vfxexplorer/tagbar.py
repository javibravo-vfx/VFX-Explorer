# -*- coding: utf-8 -*-
"""Tags rápidos de la VFX Library: pastillas (Humo, Fuego, Explosión…) que filtran toda la rama.

Cada pastilla es «Nombre: palabra, palabra». Un elemento entra si alguna palabra aparece en su nombre,
en el nombre de alguna de sus carpetas (desde la carpeta actual) o en sus tags. Varias pastillas = cualquiera."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QToolButton, QMenu, QInputDialog, QScrollArea,
                               QFrame, QSizePolicy)

from .core import DEFAULT_QUICK_TAGS, parse_pill

PILL_CSS = """
QToolButton#pill {
    background:#2b2b2b; color:#d6d6d6; border:1px solid #3a3a3a; border-radius:11px;
    padding:2px 11px; font-size:8.5pt; min-height:18px;
}
QToolButton#pill:hover { background:#353535; border-color:#4a4a4a; }
QToolButton#pill:checked { background:#0f3a55; color:#ffffff; border-color:#4cc2ff; }
QToolButton#pillAdd, QToolButton#pillClear {
    background:transparent; color:#9d9d9d; border:none; border-radius:11px;
    padding:2px 8px; font-size:9pt; min-height:18px;
}
QToolButton#pillAdd:hover, QToolButton#pillClear:hover { color:#ffffff; background:#2d2d2d; }
"""


class QuickTagBar(QWidget):
    changed = Signal(list, list)          # etiquetas activas, palabras clave

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setStyleSheet(PILL_CSS)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)          # mismo aire a la izquierda que PIPELINE
        lay.setSpacing(6)
        lbl = QLabel("FILTER")
        lbl.setStyleSheet("color:#4cc2ff; font-weight:bold; font-size:8pt; letter-spacing:1px;")
        lbl.setToolTip("Filter: show only matching elements from the whole branch of the current library folder.\n"
                       "They match the file name, its folder names or its tags.\n"
                       "Several on = any of them. Right-click to edit.")
        lay.addWidget(lbl)
        self.inner = QWidget()
        self.il = QHBoxLayout(self.inner)
        self.il.setContentsMargins(0, 0, 0, 0)
        self.il.setSpacing(5)
        sa = QScrollArea()
        sa.setWidget(self.inner)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }")
        sa.setFixedHeight(28)
        sa.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(sa, 1)
        # solo el tipo que manda en cada carpeta: en una carpeta de videos no se ven los jpg sueltos, en una de
        # HDRIs no se ve el jpg de preview, en una de fotos no se ve el mov que quedó
        self.b_images = QToolButton()
        self.b_images.setCheckable(True)
        self.b_images.setAutoRaise(True)
        self.b_images.setChecked(bool(app.cfg["lib_main_type_only"]))
        self.b_images.setToolTip("Only the main type of each folder (on)\n"
                                 "A folder full of videos hides the stray JPGs, a folder of HDRIs hides the\n"
                                 "preview JPG, a folder of photos hides the odd MOV. Folders, 3D files and\n"
                                 "documents always show. Off: everything.")
        self.b_images.toggled.connect(self._images_toggled)
        self._images_icon()
        lay.addWidget(self.b_images)
        self.buttons = []
        self.reload()

    def _images_icon(self):
        on = self.b_images.isChecked()
        self.b_images.setIcon(self.app.icons.glyph("image", 18, "#4cc2ff" if on else "#6e7378"))

    def _images_toggled(self, on):
        self._images_icon()
        self.app.cfg["lib_main_type_only"] = on
        self.app.cfg.save()
        if hasattr(self.app, "libpane"):
            self.app.libpane.set_main_type_only(on)

    # ---------------- datos
    def specs(self):
        v = self.app.cfg["quick_tags"]
        if v is not None and not self.app.cfg["quick_tags_hdri"]:
            # una lista editada antes: se le suma HDRI una sola vez (si después la borrás, no vuelve)
            self.app.cfg["quick_tags_hdri"] = True
            if not any(parse_pill(x)[0].lower() == "hdri" for x in v):
                v = list(v) + ["HDRI: hdri, hdr, skydome"]
                self.app.cfg["quick_tags"] = v
            self.app.cfg.save()
        return list(DEFAULT_QUICK_TAGS if v is None else v)

    def _save(self, specs):
        self.app.cfg["quick_tags"] = specs
        self.app.cfg.save()
        self.reload()

    def reload(self):
        active = {b.text() for b in self.buttons if b.isChecked()}
        while self.il.count():
            it = self.il.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.buttons = []
        for i, spec in enumerate(self.specs()):
            label, kws = parse_pill(spec)
            if not label:
                continue
            b = QToolButton()
            b.setObjectName("pill")
            b.setText(label)
            b.setCheckable(True)
            b.setChecked(label in active)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("Matches: " + ", ".join(kws))
            b.setProperty("kws", kws)
            b.setProperty("spec_i", i)
            b.toggled.connect(self._emit)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, b=b: self._menu(b))
            self.il.addWidget(b)
            self.buttons.append(b)
        add = QToolButton()
        add.setObjectName("pillAdd")
        add.setText("＋")
        add.setToolTip("Add a filter")
        add.clicked.connect(self.add)
        self.il.addWidget(add)
        self.clear_b = QToolButton()
        self.clear_b.setObjectName("pillClear")
        self.clear_b.setText("✕ Clear")
        self.clear_b.setToolTip("Turn off all filters")
        self.clear_b.clicked.connect(self.clear)
        self.il.addWidget(self.clear_b)
        self.il.addStretch(1)
        self._emit()

    def active(self):
        labels, kws = [], []
        for b in self.buttons:
            if b.isChecked():
                labels.append(b.text())
                kws += [k for k in b.property("kws") if k not in kws]
        return labels, kws

    def _emit(self, *_):
        labels, kws = self.active()
        self.clear_b.setVisible(bool(labels))
        self.changed.emit(labels, kws)

    def clear(self):
        if not any(b.isChecked() for b in self.buttons):
            return
        for b in self.buttons:
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self._emit()

    # ---------------- edición
    def _ask(self, title, text=""):
        t, ok = QInputDialog.getText(self, title, "Name: words to match (comma separated)\n"
                                                  "E.g.  Fire: fire, flame, fuego", text=text)
        return t.strip() if ok and t.strip() and parse_pill(t)[0] else None

    def add(self):
        t = self._ask("New filter")
        if t:
            self._save(self.specs() + [t])

    def _menu(self, b):
        i = b.property("spec_i")
        specs = self.specs()
        m = QMenu(self)

        def edit():
            t = self._ask("Edit filter", specs[i])
            if t:
                specs[i] = t
                self._save(specs)

        def remove():
            specs.pop(i)
            self._save(specs)

        def move(d):
            j = i + d
            if 0 <= j < len(specs):
                specs[i], specs[j] = specs[j], specs[i]
                self._save(specs)
        def solo():
            for x in self.buttons:
                x.blockSignals(True)
                x.setChecked(x is b)
                x.blockSignals(False)
            self._emit()
        m.addAction("Only this one", solo)
        m.addSeparator()
        m.addAction("Edit…", edit)
        m.addAction("Move left", lambda: move(-1)).setEnabled(i > 0)
        m.addAction("Move right", lambda: move(1)).setEnabled(i < len(specs) - 1)
        m.addAction("Remove", remove)
        m.addSeparator()
        m.addAction("Restore defaults", lambda: self._save(list(DEFAULT_QUICK_TAGS)))
        m.exec(b.mapToGlobal(b.rect().bottomLeft()))
