"""Notas del workspace (panel derecho › NOTES): una lista de pendientes con casillas y un bloque de texto libre.
Cada workspace tiene las suyas (Default también). Se guardan en la configuración (VFXExplorer_data)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QLineEdit,
                               QPlainTextEdit, QAbstractItemView, QMenu)


def _check_png():
    """Tilde celeste para las casillas (se dibuja una vez en VFXExplorer_data/icons)."""
    import os
    from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
    from PySide6.QtCore import QPointF
    from .core import data_dir
    d = os.path.join(data_dir(), "icons")
    path = os.path.join(d, "notes_check.png")
    if not os.path.exists(path):
        os.makedirs(d, exist_ok=True)
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#4cc2ff"), 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(8, 16.5), QPointF(13.5, 22), QPointF(24, 10)])
        p.end()
        pm.save(path)
    return path.replace("\\", "/")


def has_content(d):
    d = d or {}
    return bool(d.get("todo")) or bool((d.get("text") or "").strip())


class TodoList(QListWidget):
    """Pendientes: casilla para tildar, doble clic / F2 para editar, Supr para borrar, arrastrar para ordenar."""

    def __init__(self):
        super().__init__()
        self.setObjectName("notesTodo")
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrap(True)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.state() != QAbstractItemView.EditingState:
            it = self.currentItem()
            if it is not None:
                self.takeItem(self.row(it))
                self.model().layoutChanged.emit()
                self.itemChanged.emit(None)
                return
        if ev.key() == Qt.Key_Space and self.currentItem() is not None \
                and self.state() != QAbstractItemView.EditingState:
            it = self.currentItem()
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
            return
        super().keyPressEvent(ev)


class NotesPanel(QWidget):
    changed = Signal()                  # cualquier cambio (para guardar y actualizar la marquita)

    def __init__(self):
        super().__init__()
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(4)
        lab = "color:#7d8590; font-size:7.5pt; font-weight:bold; letter-spacing:1px; padding:4px 2px 2px 2px;"
        t1 = QLabel("TO DO")
        t1.setStyleSheet(lab)
        lay.addWidget(t1)
        self.todo = TodoList()
        ck = _check_png()
        self.todo.setStyleSheet("QListWidget#notesTodo{background:transparent; border:none; outline:none;}"
                                " QListWidget#notesTodo::indicator{width:13px; height:13px; border:1px solid #6a6a6a;"
                                " border-radius:3px; background:transparent; margin-right:4px;}"
                                " QListWidget#notesTodo::indicator:hover{border-color:#9a9a9a;}"
                                " QListWidget#notesTodo::indicator:checked{border-color:#4cc2ff; background:#163447;"
                                f" image:url({ck});}}"
                                " QListWidget#notesTodo::item{padding:3px 2px; border-radius:4px;}"
                                " QListWidget#notesTodo::item:selected{background:#2d2d2d; color:#e6e6e6;}"
                                " QListWidget#notesTodo::item:hover{background:#262626;}")
        self.todo.itemChanged.connect(self._item_changed)
        self.todo.model().rowsMoved.connect(lambda *_: self._emit())
        self.todo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.todo.customContextMenuRequested.connect(self._todo_menu)
        lay.addWidget(self.todo)
        self.add = QLineEdit()
        self.add.setPlaceholderText("+ Add item")
        self.add.setStyleSheet("QLineEdit{background:transparent; border:none; border-bottom:1px solid #2e2e2e;"
                               " padding:4px 2px; color:#e6e6e6;} QLineEdit:focus{border-bottom:1px solid #4cc2ff;}")
        self.add.returnPressed.connect(self._add_item)
        lay.addWidget(self.add)
        lay.addSpacing(10)
        t2 = QLabel("NOTES")
        t2.setStyleSheet(lab)
        lay.addWidget(t2)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Look, references, delivery dates… whatever helps in this workspace")
        self.text.setStyleSheet("QPlainTextEdit{background:#222; border:1px solid #333; border-radius:6px;"
                                " padding:6px; color:#d8d8d8;} QPlainTextEdit:focus{border:1px solid #3d5a6e;}")
        self.text.textChanged.connect(self._emit)
        lay.addWidget(self.text, 1)
        self.todo.model().rowsInserted.connect(lambda *_: self._fit())
        self.todo.model().rowsRemoved.connect(lambda *_: self._fit())
        self._fit()

    def _fit(self):
        """La lista mide lo que sus renglones (hasta un tope, después scroll): «+ Add item» queda justo abajo."""
        n = self.todo.count()
        h = sum(self.todo.sizeHintForRow(i) for i in range(n)) + 4 if n else 0
        self.todo.setFixedHeight(min(h, 280))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit()

    # ---------------------------------------------------------------- datos
    def load(self, d):
        d = d or {}
        self._loading = True
        self.todo.clear()
        for x in d.get("todo", []):
            self._new_item(x.get("t", ""), bool(x.get("done")))
        self.text.setPlainText(d.get("text", ""))
        self.add.clear()
        self._loading = False

    def data(self):
        todo = []
        for i in range(self.todo.count()):
            it = self.todo.item(i)
            t = it.text().strip()
            if t:
                todo.append({"t": t, "done": it.checkState() == Qt.Checked})
        return {"todo": todo, "text": self.text.toPlainText()}

    # ---------------------------------------------------------------- edición
    def _new_item(self, text, done=False):
        it = QListWidgetItem(text)
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
                    | Qt.ItemIsDragEnabled)
        it.setCheckState(Qt.Checked if done else Qt.Unchecked)
        self._style(it)
        self.todo.addItem(it)
        return it

    def _style(self, it):
        f = QFont(self.todo.font())
        done = it.checkState() == Qt.Checked
        f.setStrikeOut(done)
        it.setFont(f)
        it.setForeground(Qt.gray if done else Qt.white)

    def _add_item(self):
        t = self.add.text().strip()
        if not t:
            return
        self._new_item(t)
        self.add.clear()
        self._emit()

    def _item_changed(self, it):
        if self._loading:
            return
        if it is not None:
            self.todo.blockSignals(True)
            if not it.text().strip():                 # dejarlo vacío al editar = borrarlo
                self.todo.takeItem(self.todo.row(it))
            else:
                self._style(it)
            self.todo.blockSignals(False)
        self._emit()

    def _todo_menu(self, pos):
        it = self.todo.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            m.addAction("Edit\tF2", lambda: self.todo.editItem(it))
            m.addAction("Delete\tDel", lambda: (self.todo.takeItem(self.todo.row(it)), self._emit()))
            m.addSeparator()
        done = [self.todo.item(i) for i in range(self.todo.count()) if self.todo.item(i).checkState() == Qt.Checked]
        a = m.addAction("Clear done items", lambda: ([self.todo.takeItem(self.todo.row(x)) for x in done],
                                                     self._emit()))
        a.setEnabled(bool(done))
        m.exec(self.todo.viewport().mapToGlobal(pos))

    def _emit(self, *_):
        if not self._loading:
            self.changed.emit()
