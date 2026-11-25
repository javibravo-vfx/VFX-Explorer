"""Workspaces: guardar y volver a poner el estado de la interfaz (como los layouts de los programas de 3D
y de edición): modo, pestañas de cada panel y en qué carpeta están, vista, doble panel y su orientación,
panel de detalles y las medidas de los paneles."""
import os

from PySide6.QtCore import Qt, QByteArray, QSize, QTimer, QRectF, QPointF, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QFontMetrics
from PySide6.QtWidgets import QToolButton, QMenu, QInputDialog, QMessageBox

from .core import IS_WIN, THISPC, safe_isdir

SPLITS = (("main", "main_split"), ("left", "left_split"), ("panes", "pane_split"))


def _split_state(sp):
    return bytes(sp.saveState().toBase64()).decode()


def capture(app):
    st = {
        "mode": app.mode(),
        "panes": [p.state() for p in app.panes],
        "dual": bool(app.paneB.isVisible()) if app.mode() == "explorer" else bool(app.cfg["dual"]),
        "orient": app.cfg["dual_orient"] or "h",
        "details": bool(app.info_area.isVisible()),
        "splits": {k: _split_state(getattr(app, attr)) for k, attr in SPLITS},
        "lib_split": _split_state(app.libpage.split),
        "side": app.sidetabs.currentIndex(),
        "active": 1 if app.explorer_active is app.paneB else 0,
    }
    if app.libpane.tabs:
        st["library"] = app.libpane.state()
    return st


def apply(app, st):
    home = os.path.expanduser("~")
    fallback = THISPC if IS_WIN else home
    if app.mode() != "explorer":
        app.set_mode("explorer")
    panes = st.get("panes") or []
    for i, p in enumerate(app.panes):
        ps = panes[i] if i < len(panes) else None
        if ps:
            p._stop_search()
            p.clear_tabs()
            p.restore(ps, fallback)
    app.cfg["dual_orient"] = st.get("orient", "h")
    app.toggle_dual(force=bool(st.get("dual")))
    app.set_active(app.paneB if st.get("active") == 1 and app.paneB.isVisible() else app.paneA)
    lib = st.get("library")
    roots = app.libpane.root_lock()
    if lib and roots:
        lib = dict(lib, tabs=[t for t in lib.get("tabs", []) if app.libpane.allowed(t.get("path", ""))])
        if lib["tabs"]:
            app.libpane.clear_tabs()
            app.libpane.restore(lib, roots[0])
    app.toggle_details(bool(st.get("details", True)))

    def sizes():
        for k, attr in SPLITS:
            v = (st.get("splits") or {}).get(k)
            if v:
                getattr(app, attr).restoreState(QByteArray.fromBase64(v.encode()))
        if st.get("lib_split"):
            app.libpage.split.restoreState(QByteArray.fromBase64(st["lib_split"].encode()))
        app._sync_cmd_left()
    sizes()
    QTimer.singleShot(0, sizes)              # después de que los paneles recién mostrados tomen lugar
    if st.get("mode") == "library":
        app.set_mode("library")
    elif "side" in st:
        app.sidetabs.setCurrentIndex(int(st["side"]))
    app.sync_commandbar(app.active)
    app.save_soon()


class WorkspaceButton(QToolButton):
    """A la izquierda de File Explorer / VFX Library: ícono (ventana con sus paneles) + el nombre del workspace
    activo (cortado con … si es largo) + flechita. El recuadro al pasar el mouse coincide con el de las pestañas
    de modo; queda separado de ellas un poco (GAP)."""
    GAP = 11
    MAX_TEXT = 150

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("wsbutton")
        self.setPopupMode(QToolButton.InstantPopup)
        self.setStyleSheet("QToolButton{border:none; background:transparent;}"
                           " QToolButton::menu-indicator{image:none; width:0px;}")
        self.setMouseTracking(True)
        self.m = QMenu(self)
        self.m.aboutToShow.connect(self._fill)
        self.setMenu(self.m)
        self._label = ""
        self.refresh()

    def _font(self):
        f = self.font()
        f.setPointSizeF(9.5)
        return f

    def _apply_width(self):
        fm = QFontMetrics(self._font())
        t = fm.elidedText(self._label, Qt.ElideRight, self.MAX_TEXT) if self._label else ""
        self._shown = t
        self.setFixedWidth(44 + (fm.horizontalAdvance(t) + 6 if t else 0) + self.GAP)

    def _box(self):
        """El recuadro, a la misma altura que el de File Explorer / VFX Library."""
        mb = self.app.modebar
        h = 28
        try:
            tr = mb.tabRect(0)
            top = mb.mapTo(self.window(), tr.topLeft()).y() - self.mapTo(self.window(), QPoint(0, 0)).y() + 4
            if tr.height() <= 0 or not self.isVisible():
                raise ValueError
        except Exception:
            top = (self.height() - h) / 2
        return QRectF(1, top, self.width() - 2 - self.GAP, h)

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.update()
        super().leaveEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._box()
        if self.underMouse() or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#333333" if self.isDown() else "#2d2d2d"))
            p.drawRoundedRect(r, 6, 6)
        c = QColor("#c5c5c5")
        cy, cx = r.center().y(), 17.0
        p.setPen(QPen(c, 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(cx - 9, cy - 7, 18, 14), 2, 2)
        p.drawLine(QPointF(cx - 3, cy - 7), QPointF(cx - 3, cy + 7))
        p.drawLine(QPointF(cx - 3, cy), QPointF(cx + 9, cy))
        if self._shown:
            p.setFont(self._font())
            p.setPen(QColor("#c9ccd1"))
            p.drawText(QRectF(cx + 15, r.top(), r.width(), r.height()), Qt.AlignVCenter | Qt.AlignLeft, self._shown)
        x = r.right() - 9
        p.setPen(QPen(c, 1.1, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x - 3, cy - 1), QPointF(x, cy + 2))
        p.drawLine(QPointF(x, cy + 2), QPointF(x + 3, cy - 1))
        p.end()

    # ---------------------------------------------------------------- datos
    def items(self):
        return [w for w in (self.app.cfg["workspaces"] or []) if w.get("name")]

    def _find(self, name):
        return next((w for w in self.items() if w["name"] == name), None)

    def _store(self, lst, current=None):
        self.app.cfg["workspaces"] = lst
        if current is not None:
            self.app.cfg["workspace_current"] = current
        self.app.cfg.save()
        self.refresh()

    def refresh(self):
        cur = self.app.cfg["workspace_current"]
        if cur and not self._find(cur):
            cur = ""
        self._label = cur
        self._apply_width()
        tip = "Save the open tabs, panels and their sizes, and switch between layouts\n(Alt+Shift+1…9: the first nine)"
        self.setToolTip((f"Workspace: {cur}\n" if cur else "Workspace\n") + tip)
        self.update()

    # ---------------------------------------------------------------- menú
    def _fill(self):
        m = self.m
        m.clear()
        cur = self.app.cfg["workspace_current"]
        lst = self.items()
        for i, w in enumerate(lst):
            a = m.addAction(w["name"] + (f"\tAlt+Shift+{i + 1}" if i < 9 else ""),
                            lambda n=w["name"]: self.switch(n))
            a.setCheckable(True)
            a.setChecked(w["name"] == cur)
        if not lst:
            m.addAction("No workspaces yet").setEnabled(False)
        m.addSeparator()
        m.addAction("Save as new workspace…", self.save_new)
        has = bool(cur and self._find(cur))
        m.addAction(f"Update «{cur}» with the current layout" if has else "Update workspace",
                    lambda: self.update_ws(cur)).setEnabled(has)
        m.addAction(f"Reset to «{cur}»" if has else "Reset to saved", lambda: self.switch(cur)).setEnabled(has)
        if lst:
            ren = m.addMenu("Rename")
            dele = m.addMenu("Delete")
            up = m.addMenu("Move up")
            for i, w in enumerate(lst):
                ren.addAction(w["name"], lambda n=w["name"]: self.rename(n))
                dele.addAction(w["name"], lambda n=w["name"]: self.delete(n))
                if i:
                    up.addAction(w["name"], lambda n=w["name"]: self.move_up(n))
            up.setEnabled(len(lst) > 1)

    # ---------------------------------------------------------------- acciones
    def switch(self, name):
        w = self._find(name)
        if not w:
            return
        apply(self.app, w["state"])
        self.app.cfg["workspace_current"] = name
        self.app.cfg.save()
        self.refresh()
        self.app.status.setText(f"Workspace: {name}")

    def switch_index(self, i):
        lst = self.items()
        if 0 <= i < len(lst):
            self.switch(lst[i]["name"])

    def _ask_name(self, title, text=""):
        name, ok = QInputDialog.getText(self.app, title, "Name:", text=text)
        name = (name or "").strip()
        return name if ok and name else None

    def save_new(self):
        n = len(self.items()) + 1
        name = self._ask_name("Save workspace", f"Workspace {n}")
        if not name:
            return
        lst = self.items()
        old = self._find(name)
        if old is not None:
            if QMessageBox.question(self.app, "Save workspace", f"Replace the workspace «{name}»?",
                                    QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
            old["state"] = capture(self.app)
        else:
            lst.append({"name": name, "state": capture(self.app)})
        self._store(lst, name)
        self.app.status.setText(f"Workspace saved: {name}")

    def update_ws(self, name):
        lst = self.items()
        w = next((x for x in lst if x["name"] == name), None)
        if w is None:
            return
        w["state"] = capture(self.app)
        self._store(lst, name)
        self.app.status.setText(f"Workspace updated: {name}")

    def rename(self, name):
        new = self._ask_name("Rename workspace", name)
        if not new or new == name:
            return
        lst = self.items()
        if any(x["name"] == new for x in lst):
            QMessageBox.information(self.app, "Rename workspace", f"There is already a workspace «{new}».")
            return
        for x in lst:
            if x["name"] == name:
                x["name"] = new
        cur = self.app.cfg["workspace_current"]
        self._store(lst, new if cur == name else cur)

    def delete(self, name):
        if QMessageBox.question(self.app, "Delete workspace", f"Delete the workspace «{name}»?\n"
                                "(The open tabs and folders are not touched.)",
                                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        lst = [x for x in self.items() if x["name"] != name]
        cur = self.app.cfg["workspace_current"]
        self._store(lst, "" if cur == name else cur)

    def move_up(self, name):
        lst = self.items()
        i = next((k for k, x in enumerate(lst) if x["name"] == name), 0)
        if i:
            lst[i - 1], lst[i] = lst[i], lst[i - 1]
            self._store(lst)
