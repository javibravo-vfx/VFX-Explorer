"""Workspaces: guardar y volver a poner el estado de la interfaz (como los layouts de los programas de 3D
y de edición): modo, pestañas de cada panel y en qué carpeta están, vista, doble panel y su orientación,
panel de detalles y las medidas de los paneles."""
import copy
import os

from PySide6.QtCore import Qt, QByteArray, QSize, QTimer, QRectF, QPointF, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QFontMetrics, QFont
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
        "details": bool(app.cfg["details_explorer"]),   # Details de File Explorer
        "details_lib": bool(app.cfg["details_library"]),
        "splits": {k: _split_state(getattr(app, attr)) for k, attr in SPLITS},
        "lib_split": _split_state(app.libpage.split),
        "lib_quick": _split_state(app.lib_quick) if hasattr(app, "lib_quick") else "",
        "side": app.sidetabs.currentIndex(),
        "active": 1 if app.explorer_active is app.paneB else 0,
    }
    if app.libpane.tabs:
        st["library"] = app.libpane.state()
    # colores: cada workspace con los suyos (automáticos, líneas del árbol, Color filters de los nombres)
    st["colors"] = {"mode": app.cfg["color_mode"] or "project", "lines": bool(app.cfg["tree_line_colors"]),
                    "cfilters": bool(app.cfg["color_filters_on"])}
    st["win_nav"] = bool(app.cfg["win_nav"])           # modo Windows del panel izquierdo
    st["win_bonsai"] = bool(app.cfg["win_bonsai"])     # … con el Bonsai
    st["lib_slots"] = list(app.cfg["lib_slots"] or [])  # los circulitos 1…4 del player de la librería
    st["bonsai"] = list(app.cfg["mini_tree"] or [])     # cada workspace con su Bonsai (lo que podaste queda podado)
    return st


def apply_win_nav(app, on):
    on = True                                     # File Explorer navega siempre en modo Windows
    app.cfg["win_nav"] = bool(on)
    if hasattr(app, "b_winnav") and app.b_winnav.isChecked() != bool(on):
        app.b_winnav.setChecked(bool(on))         # (lo aplica _toggle_winnav)


def apply_bonsai(app, lst):
    """Antes de abrir las carpetas del workspace: su Bonsai (None = workspace viejo sin Bonsai guardado: no se toca)."""
    if lst is None:
        return
    app.cfg["mini_tree"] = list(lst)
    app.minitree.rebuild()
    if hasattr(app, "winbonsai"):
        app.winbonsai.rebuild()


FACTORY_COLORS = {"mode": "project", "lines": True, "cfilters": False}


def apply_colors(app, c):
    c = c or FACTORY_COLORS                       # sin colores guardados (o Reset a cero): los de fábrica
    app.cfg["color_mode"] = c.get("mode", app.cfg["color_mode"])
    app.cfg["tree_line_colors"] = bool(c.get("lines", app.cfg["tree_line_colors"]))
    app.colors.reload()
    app.update_palette_icon()
    on = bool(c.get("cfilters", app.cfg["color_filters_on"]))
    if app.act_cfilter.isChecked() != on:
        app.act_cfilter.setChecked(on)            # (lo aplica _toggle_color_filters)
    app.refresh_views()
    app.tree.refresh_colors()
    app.tree.viewport().update()
    app._reload_sidebar()


def apply(app, st):
    home = os.path.expanduser("~")
    fallback = THISPC if IS_WIN else home
    if app.mode() != "explorer":
        app.set_mode("explorer")
    apply_colors(app, st.get("colors"))           # (un workspace viejo sin colores guardados: los de fábrica)
    apply_bonsai(app, st.get("bonsai"))
    if "lib_slots" in st:
        app.cfg["lib_slots"] = list(st["lib_slots"] or [None] * 4)
        if hasattr(app, "lib_slots"):
            app.lib_slots.bar.update()
    if "win_nav" in st:
        apply_win_nav(app, st["win_nav"])
    if "win_bonsai" in st and hasattr(app, "b_winbonsai") and app.b_winbonsai.isChecked() != bool(st["win_bonsai"]):
        app.b_winbonsai.setChecked(bool(st["win_bonsai"]))
    panes = st.get("panes") or []
    remember = bool(app.cfg["ws_remember_selection"])
    for i, p in enumerate(app.panes):
        ps = panes[i] if i < len(panes) else None
        if ps and not remember:               # Settings: al cambiar de workspace, sin nada seleccionado
            ps = dict(ps, tabs=[{k: v for k, v in t.items() if k != "sel"} for t in ps.get("tabs", [])])
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
    app.cfg["details_explorer"] = bool(st.get("details", False))
    app.cfg["details_library"] = bool(st.get("details_lib", True))
    app.toggle_details(bool(app.cfg[app._details_key()]), remember=False)

    def sizes():
        sync = bool(app.cfg["left_split_sync"])   # tildado: el panel izquierdo queda a la misma altura en todos
        for k, attr in SPLITS:
            if k == "left" and sync:
                continue
            v = (st.get("splits") or {}).get(k)
            if v:
                getattr(app, attr).restoreState(QByteArray.fromBase64(v.encode()))
        if not sync and st.get("lib_quick") and hasattr(app, "lib_quick"):
            app.lib_quick.restoreState(QByteArray.fromBase64(st["lib_quick"].encode()))
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


DEFAULT = "Default"


def reset_layout(app, keep_win=False):
    """Como al abrir la app por primera vez, solo en lo visual: una pestaña (This PC) en File Explorer, sin doble
    panel, Details prendido y las medidas de fábrica. No toca Quick access, la librería ni ninguna configuración."""
    home = os.path.expanduser("~")
    first = THISPC if IS_WIN else home
    if app.mode() != "explorer":
        app.set_mode("explorer")
    apply_colors(app, None)                       # los colores también vuelven a los de fábrica
    apply_bonsai(app, [])                         # y el Bonsai arranca podado (queda solo la carpeta que se abre)
    if not keep_win:
        apply_win_nav(app, True)                  # panel izquierdo como en Windows (sin el Bonsai)
        if hasattr(app, "b_winbonsai") and app.b_winbonsai.isChecked():
            app.b_winbonsai.setChecked(False)
    for p in app.panes:
        p._stop_search()
        p.clear_tabs()
        p.restore(None, first)
    app.cfg["dual_orient"] = "h"
    app.toggle_dual(force=False)
    app.set_active(app.paneA)
    roots = app.libpane.root_lock()
    if roots:
        app.libpane.clear_tabs()
        app.libpane.restore(None, roots[0])
        app.libpane.set_view("grid", emit=False)
    app.cfg["details_explorer"] = False          # de fábrica: Details apagado en File Explorer, prendido en la librería
    app.cfg["details_library"] = True
    app.toggle_details(bool(app.cfg[app._details_key()]), remember=False)
    defaults = getattr(app, "_default_splits", {})

    def sizes():
        tot = max(1200, sum(app.main_split.sizes()) or app.width())
        app.main_split.setSizes([340, tot - 340 - 360, 360])
        if defaults.get("left") and not app.cfg["left_split_sync"]:
            app.left_split.restoreState(QByteArray.fromBase64(defaults["left"].encode()))
        if defaults.get("lib"):
            app.libpage.split.restoreState(QByteArray.fromBase64(defaults["lib"].encode()))
        app._sync_cmd_left()
    sizes()
    QTimer.singleShot(0, sizes)
    app.sidetabs.setCurrentIndex(0)
    app.sync_commandbar(app.active)
    app.save_soon()


class WorkspaceButton(QToolButton):
    """A la izquierda de File Explorer / VFX Library: ícono (ventana con sus paneles) + el nombre del workspace
    activo (cortado con … si es largo) + flechita. El recuadro al pasar el mouse coincide con el de las pestañas
    de modo; queda separado de ellas un poco (GAP)."""
    GAP = 5                      # + el margen de la pestaña: apenas más que entre File Explorer y VFX Library
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
        # cómo estaba cada workspace al abrir la app (para «Reset» con Keep updated)
        self._start = {w["name"]: copy.deepcopy(w["state"]) for w in self.items()}
        self.refresh()

    def _font(self):
        f = QFont(self.app.modebar.font())       # la misma letra que File Explorer / VFX Library, sin negrita
        f.setBold(False)
        return f

    def _apply_width(self):
        fm = QFontMetrics(self._font())
        t = fm.elidedText(self._label, Qt.ElideRight, self.MAX_TEXT) if self._label else ""
        self._shown = t
        self.setFixedWidth(22 + (5 + fm.horizontalAdvance(t) if t else 0) + 9 + 6 + 9 + self.GAP)

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

    def event(self, ev):
        from PySide6.QtCore import QEvent
        import time
        if ev.type() == QEvent.ToolTip and (self.m.isVisible() or time.monotonic() < getattr(self, "_quiet", 0)):
            return True                           # recién elegido un workspace (o con el menú abierto): sin cartel
        return super().event(ev)

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
        cy, cx = r.center().y(), 15.0
        p.setPen(QPen(c, 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(cx - 7, cy - 5.5, 14, 11), 1.8, 1.8)
        p.drawLine(QPointF(cx - 2.5, cy - 5.5), QPointF(cx - 2.5, cy + 5.5))
        p.drawLine(QPointF(cx - 2.5, cy), QPointF(cx + 7, cy))
        if self._shown:
            p.setFont(self._font())
            p.setPen(QColor("#c9ccd1"))
            p.drawText(QRectF(cx + 12, r.top(), r.width(), r.height()), Qt.AlignVCenter | Qt.AlignLeft, self._shown)
        x = r.right() - 12
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

    def current(self):
        """Workspace activo; si no hay ninguno elegido (o se borró), es Default."""
        cur = self.app.cfg["workspace_current"]
        return cur if cur and cur != DEFAULT and self._find(cur) else DEFAULT

    def keep_updated(self):
        return True                               # cada workspace se guarda solo mientras se trabaja (siempre)

    def refresh(self):
        cur = self.current()
        self._label = cur
        self._apply_width()
        self.setToolTip(f"Workspace: {cur}  (Shift+F1…F6)")
        from PySide6.QtWidgets import QToolTip
        QToolTip.hideText()                       # al cambiar de workspace no queda un cartel flotando
        import time
        self._quiet = time.monotonic() + 4
        self.update()
        if hasattr(self.app, "_qa_refresh"):
            self.app._qa_refresh()             # QUICK ACCESS | WORKSPACE PINS del workspace activo
        if hasattr(self.app, "_notes_refresh"):
            self.app._notes_refresh()          # NOTES del workspace activo

    # ---------------------------------------------------------------- memoria automática
    def autosave(self):
        """Lo llama el guardado de la app (pestañas, paneles…): Default recuerda siempre; los demás, con
        Keep updated. No guarda en disco (lo hace quien llama)."""
        if getattr(self, "_applying", False):
            return
        cur = self.current()
        try:
            st = capture(self.app)
        except Exception:
            return
        if cur == DEFAULT:
            self.app.cfg["workspace_default_state"] = st
        elif self.keep_updated():
            w = self._find(cur)
            if w is not None:
                w["state"] = st

    def _apply(self, st):
        self._applying = True
        try:
            if st:
                apply(self.app, st)
            else:
                reset_layout(self.app)
        finally:
            self._applying = False

    # ---------------------------------------------------------------- menú
    def _fill(self):
        m = self.m
        m.clear()
        cur = self.current()
        keep = self.keep_updated()
        lst = self.items()
        d = m.addAction(f"{DEFAULT}\tShift+F1", lambda: self.switch(DEFAULT))
        d.setCheckable(True)
        d.setChecked(cur == DEFAULT)
        if lst:
            m.addSeparator()
        for i, w in enumerate(lst):
            a = m.addAction(w["name"] + (f"\tShift+F{i + 2}" if i < 5 else (f"\tAlt+Shift+{i + 1}" if i < 9 else "")),
                            lambda n=w["name"]: self.switch(n))
            a.setCheckable(True)
            a.setChecked(w["name"] == cur)
        m.addSeparator()
        m.addSection("On startup")
        c = m.addAction("Continue where you left off", lambda: self._toggle_cfg("ws_continue"))
        c.setCheckable(True)
        c.setChecked(bool(self.app.cfg["ws_continue"]))
        c.setToolTip("On: the app opens in the workspace you were in. Off: it opens in Default")
        r = m.addAction(f"Reset «{DEFAULT}» to zero on startup", lambda: self._toggle_cfg("ws_reset_default"))
        r.setCheckable(True)
        r.setChecked(bool(self.app.cfg["ws_reset_default"]))
        r.setToolTip(f"On: «{DEFAULT}» starts clean every time (one tab in This PC, factory panels)")
        sm = m.addMenu("Startup workspace")
        sm.setToolTip("Where the app opens when «Continue where you left off» is off")
        start = self.app.cfg["ws_startup"] or DEFAULT
        if start != DEFAULT and not self._find(start):
            start = DEFAULT
        for n in [DEFAULT] + [w["name"] for w in lst]:
            a = sm.addAction(n, lambda n=n: self._set_startup(n))
            a.setCheckable(True)
            a.setChecked(n == start)
        m.addSeparator()
        m.addAction("New workspace…", self.new_ws)
        m.addAction("Save current layout as new workspace…", self.save_new)
        m.setToolTipsVisible(True)
        if cur == DEFAULT:
            m.addAction(f"Reset «{DEFAULT}» to zero", lambda: self.reset(DEFAULT))
        else:
            m.addAction(f"Reset «{cur}» to how it was when the app opened", lambda: self.reset(cur))
            z = m.addAction(f"Reset «{cur}» to zero", lambda: self.reset_zero(cur))
            z.setToolTip("One tab in This PC and factory panels (keeps its Workspace Pins, notes and Windows mode)")
        if lst:
            ren = m.addMenu("Rename")
            dele = m.addMenu("Delete")
            mv = m.addMenu("Move up")
            for i, w in enumerate(lst):
                ren.addAction(w["name"], lambda n=w["name"]: self.rename(n))
                dele.addAction(w["name"], lambda n=w["name"]: self.delete(n))
                if i:
                    mv.addAction(w["name"], lambda n=w["name"]: self.move_up(n))
            mv.setEnabled(len(lst) > 1)

    def _toggle_cfg(self, key):
        self.app.cfg[key] = not bool(self.app.cfg[key])
        self.app.cfg.save()

    def _set_startup(self, name):
        self.app.cfg["ws_startup"] = name
        self.app.cfg.save()

    def reset_zero(self, name):
        """Cualquier workspace a cero: una pestaña en This PC y paneles de fábrica (el modo Windows queda como está)."""
        if name == DEFAULT:
            self.reset(DEFAULT)
            return
        w = self._find(name)
        if w is None:
            return
        self._applying = True
        try:
            reset_layout(self.app, keep_win=True)
        finally:
            self._applying = False
        w["state"] = capture(self.app)
        self._start[name] = copy.deepcopy(w["state"])
        self.app.cfg["workspace_current"] = name
        self.app.cfg.save()
        self.refresh()
        self.app.status.setText(f"Workspace reset to zero: {name}")

    def startup(self, start_path=None):
        """Al abrir la app: «Reset Default to zero on startup» y «Continue where you left off»."""
        cfg = self.app.cfg
        if cfg["ws_reset_default"]:
            cfg["workspace_default_state"] = None
        cur = self.current()
        if start_path:                            # se abrió con una carpeta: esa manda (no se rearma nada)
            return
        target = cur
        if not cfg["ws_continue"]:                # arranca en el «Startup workspace» (Default si no se eligió otro)
            target = cfg["ws_startup"] or DEFAULT
            if target != DEFAULT and not self._find(target):
                target = DEFAULT
        if target != cur:
            self._apply((cfg["workspace_default_state"] or None) if target == DEFAULT else self._find(target)["state"])
            cfg["workspace_current"] = target
            self.refresh()
        elif target == DEFAULT and cfg["ws_reset_default"]:
            self._apply(None)
        cfg.save()

    def save_slot(self, i):
        """Ctrl+F1…F6 (como en Nuke): guarda la vista actual en ese workspace (F1 = Default)."""
        if i == 0:
            self.app.cfg["workspace_default_state"] = capture(self.app)
            self.app.cfg.save()
            self.app.status.setText(f"Workspace updated: {DEFAULT}")
            return
        lst = self.items()
        if i - 1 < len(lst):
            self.update_ws(lst[i - 1]["name"])
        else:
            self.save_new()

    def _toggle_keep(self):
        self.autosave()
        self.app.cfg["workspace_keep_updated"] = not self.keep_updated()
        self.app.cfg.save()
        self.refresh()

    # ---------------------------------------------------------------- acciones
    def switch(self, name):
        if name != DEFAULT and not self._find(name):
            return
        if name == self.current():
            return
        self.autosave()                       # el que se deja queda como está (Default siempre, el resto con Keep)
        if name == DEFAULT:
            self._apply(self.app.cfg["workspace_default_state"] or None)
        else:
            self._apply(self._find(name)["state"])
        self.app.cfg["workspace_current"] = name
        self.app.cfg.save()
        self.refresh()
        self.app.status.setText(f"Workspace: {name}")

    def switch_index(self, i):
        lst = self.items()
        if 0 <= i < len(lst):
            self.switch(lst[i]["name"])

    def reset(self, name):
        """Default: a cero (como la primera vez). Con Keep updated: como estaba al abrir la app. Si no: al guardado."""
        if name == DEFAULT:
            self._apply(None)
            self.app.cfg["workspace_default_state"] = capture(self.app)
        else:
            w = self._find(name)
            if w is None:
                return
            st = self._start.get(name) if self.keep_updated() else None
            self._apply(st or w["state"])
            w["state"] = capture(self.app)
        self.app.cfg["workspace_current"] = name
        self.app.cfg.save()
        self.refresh()
        self.app.status.setText(f"Workspace reset: {name}")

    def _offer_update(self, title):
        """Sin Keep updated: antes de dejar el workspace actual, ¿guardarle los cambios? False = cancelar."""
        cur = self.current()
        if cur == DEFAULT or self.keep_updated():
            self.autosave()
            return True
        r = QMessageBox.question(self.app, title, f"Update the workspace «{cur}» with the current layout first?",
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Yes:
            self.update_ws(cur)
        return True

    def _ask_name(self, title, text=""):
        name, ok = QInputDialog.getText(self.app, title, "Name:", text=text)
        name = (name or "").strip()
        if ok and name == DEFAULT:
            QMessageBox.information(self.app, title, f"«{DEFAULT}» is the built-in workspace; choose another name.")
            return None
        return name if ok and name else None

    def _confirm_replace(self, title, name):
        return QMessageBox.question(self.app, title, f"Replace the workspace «{name}»?",
                                    QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def _add(self, name, st):
        lst = self.items()
        old = next((x for x in lst if x["name"] == name), None)
        if old is not None:
            old["state"] = st
        else:
            lst.append({"name": name, "state": st})
        self._start[name] = copy.deepcopy(st)
        self._store(lst, name)

    def new_ws(self):
        """Workspace nuevo desde cero: cierra las pestañas y deja todo como al abrir la app la primera vez
        (no borra Quick access ni nada de la librería)."""
        if not self._offer_update("New workspace"):
            return
        name = self._ask_name("New workspace", f"Workspace {len(self.items()) + 1}")
        if not name or (self._find(name) and not self._confirm_replace("New workspace", name)):
            return
        self._apply(None)
        self._add(name, capture(self.app))
        self.app.status.setText(f"New workspace: {name}")

    def save_new(self):
        name = self._ask_name("Save workspace", f"Workspace {len(self.items()) + 1}")
        if not name or (self._find(name) and not self._confirm_replace("Save workspace", name)):
            return
        self.autosave()
        self._add(name, capture(self.app))
        self.app.status.setText(f"Workspace saved: {name}")

    def update_ws(self, name):
        w = self._find(name)
        if w is None:
            return
        w["state"] = capture(self.app)
        self._store(self.items(), name)
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
        if name in self._start:
            self._start[new] = self._start.pop(name)
        if self.app.cfg["ws_startup"] == name:
            self.app.cfg["ws_startup"] = new
        cur = self.app.cfg["workspace_current"]
        self._store(lst, new if cur == name else cur)

    def delete(self, name):
        if QMessageBox.question(self.app, "Delete workspace", f"Delete the workspace «{name}»?\n"
                                "(The open tabs and folders are not touched.)",
                                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        was = self.current() == name
        lst = [x for x in self.items() if x["name"] != name]
        self._start.pop(name, None)
        self._store(lst, DEFAULT if was else None)
        if was:                                   # se vuelve a Default con lo que recordaba
            self._apply(self.app.cfg["workspace_default_state"] or None)

    def move_up(self, name):
        lst = self.items()
        i = next((k for k, x in enumerate(lst) if x["name"] == name), 0)
        if i:
            lst[i - 1], lst[i] = lst[i], lst[i - 1]
            self._store(lst)
