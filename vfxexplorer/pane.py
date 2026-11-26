# -*- coding: utf-8 -*-
"""Panel de archivos: pestañas, breadcrumb, búsqueda, grilla/lista y drag & drop."""

import os

from PySide6.QtCore import (Qt, Signal, QSize, QTimer, QEvent, QItemSelectionModel, QRect, QPersistentModelIndex,
                            QModelIndex, QRectF, QPointF, QPoint)
from PySide6.QtGui import QKeySequence, QShortcut, QCursor, QPainter, QPainterPath, QColor, QPen, QFont
from PySide6.QtWidgets import (QSizePolicy, QFrame, QVBoxLayout, QHBoxLayout, QTabBar, QToolButton, QLineEdit, QComboBox,
                               QCheckBox, QListView, QTreeView, QStackedWidget, QAbstractItemView, QHeaderView,
                               QLabel, QMenu, QWidget)

from .core import IS_WIN, FILTERS, parse_query, norm_key, same_path, THISPC, IMAGE_EXTS, reachable
from .fileops import is_subpath, is_network_path
from .models import (EntryModel, EntryProxy, ScanWorker, SearchWorker, ResolveWorker, DrivesWorker, ROLE_ENTRY, COLS,
                     C_NAME, C_FOLDER, C_TAGS, C_RATING, VFX_COLS)
from .widgets import GridDelegate, BreadcrumbBar, ListNameDelegate


class _ViewMixin:
    def mouseDoubleClickEvent(self, ev):
        """Doble click en el espacio vacío: subir un nivel."""
        if ev.button() == Qt.LeftButton and not self.indexAt(ev.position().toPoint()).isValid():
            self.pane.go_up()
            return
        super().mouseDoubleClickEvent(ev)

    def _setup(self, pane):
        self.pane = pane
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)   # F2 = renombrar en el lugar
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        self.dragEnterEvent(ev)

    def dropEvent(self, ev):
        paths = [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
        ix = self.indexAt(ev.position().toPoint())
        target = None
        if ix.isValid():
            e = ix.data(ROLE_ENTRY)
            if e is not None and e.kind == "dir":
                target = e.path
        if target is None:
            target = self.pane.current_dir()
        mods = ev.modifiers()
        ev.setDropAction(Qt.CopyAction)
        ev.accept()
        if target and paths:
            pos = QCursor.pos()
            QTimer.singleShot(0, lambda: self.pane.app.handle_drop(self.pane, paths, target, mods, pos))

    def startDrag(self, actions):
        """Arrastrar: en vez del thumbnail grande (que tapa el destino), una miniatura chica abajo a la derecha
        del cursor, apilada si son varias, con un circulito celeste que dice cuántas son."""
        from PySide6.QtGui import QDrag
        rows = sorted({ix.row() for ix in self.selectionModel().selectedIndexes()})
        idx = [self.model().index(r, 0) for r in rows]
        md = self.model().mimeData(idx) if idx else None
        if md is None or not md.hasUrls():
            super().startDrag(Qt.CopyAction)
            self.pane.app.drag_finished()
            return
        drag = QDrag(self)
        drag.setMimeData(md)
        try:
            pm = self._drag_pixmap([ix.data(ROLE_ENTRY) for ix in idx[:3]], len(idx))
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(0, 0))
        except Exception:
            pass
        drag.exec(Qt.CopyAction)
        self.pane.app.drag_finished()

    def _drag_pixmap(self, ents, count):
        from PySide6.QtGui import QPixmap
        from .widgets import icon_dpr
        app = self.pane.app
        TW, TH = 44, 33                     # miniatura
        OX, OY = 18, 16                     # separación del cursor (la punta queda libre)
        n = max(1, min(3, len(ents)))
        W, H = OX + TW + 3 * (n - 1) + 14, OY + TH + 3 * (n - 1) + 4
        d = icon_dpr()
        pm = QPixmap(int(W * d), int(H * d))
        pm.setDevicePixelRatio(d)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for k in reversed(range(n)):
            e = ents[k] if k < len(ents) else None
            r = QRect(OX + k * 3, OY + 3 * (n - 1) - k * 3, TW, TH)
            path = QPainterPath()
            path.addRoundedRect(r, 4, 4)
            p.fillPath(path, QColor(40, 40, 40, 235))
            img = None
            if e is not None and e.kind != "dir":
                try:
                    img = app.thumbs.get(e)
                except Exception:
                    img = None
            p.save()
            p.setClipPath(path)
            if img is not None and not img.isNull():
                s = img.scaled(int(TW * d), int(TH * d), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                s.setDevicePixelRatio(d)
                sw, sh = s.width() / d, s.height() / d
                p.drawPixmap(int(r.x() + (TW - sw) / 2), int(r.y() + (TH - sh) / 2), s)
            elif e is not None:
                ic = app.icons.folder_icon(app.entry_color(e), 24) if e.kind == "dir" else self._entry_icon(e)
                if ic is not None:
                    ic.paint(p, QRect(r.x() + (TW - 24) // 2, r.y() + (TH - 24) // 2, 24, 24))
            p.restore()
            p.setPen(QPen(QColor(20, 20, 20), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 4, 4)
        if count > 1:
            c = QPoint(OX + TW + 3 * (n - 1) + 4, OY - 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#4cc2ff"))
            rad = 9 if count < 100 else 11
            p.drawEllipse(c, rad, rad)
            f = QFont(self.font())
            f.setPointSizeF(7.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#08202e"))
            p.drawText(QRect(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), Qt.AlignCenter, str(count))
        p.end()
        return pm

    def _entry_icon(self, e):
        try:
            sp = self.pane.app.sys_icon(e, 24)
            from PySide6.QtGui import QIcon
            return QIcon(sp) if sp is not None else self.pane.app.icons.badge(e)
        except Exception:
            return None

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            ix = self.indexAt(ev.position().toPoint())
            e = ix.data(ROLE_ENTRY) if ix.isValid() else None
            if e is not None and e.kind == "dir":
                self.pane.add_tab(e.path, activate=False)
            return
        super().mouseReleaseEvent(ev)

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self.pane.focused.emit(self.pane)

    def mousePressEvent(self, ev):
        self.pane.focused.emit(self.pane)
        if ev.button() in (Qt.BackButton, Qt.XButton1):
            self.pane.go_back()
            return
        if ev.button() in (Qt.ForwardButton, Qt.XButton2):
            self.pane.go_forward()
            return
        super().mousePressEvent(ev)


class GridView(_ViewMixin, QListView):
    """Grilla con scrub: al pasar el mouse sobre una secuencia o un video se recorren sus frames."""
    scrub = None    # (QPersistentModelIndex, fracción)

    def thumb_rect(self, ix):
        r = self.visualRect(ix).adjusted(3, 3, -3, -3)
        return QRect(r.x() + 5, r.y() + 5, r.width() - 10, int((r.width() - 10) * 9 / 16))

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if ev.buttons() or not self.pane.app.cfg["scrub_thumbs"]:
            return
        pos = ev.position().toPoint()
        ix = self.indexAt(pos)
        e = ix.data(ROLE_ENTRY) if ix.isValid() else None
        old = self.scrub
        if e is not None and ((e.kind == "seq" and len(e.files) > 1) or e.cat == "video"):
            th = self.thumb_rect(ix)
            if th.contains(pos):
                self.scrub = (QPersistentModelIndex(ix), (pos.x() - th.x()) / max(1, th.width()))
                self.viewport().update(self.visualRect(ix))
                if old and old[0] != self.scrub[0]:
                    self.viewport().update(self.visualRect(QModelIndex(old[0])))
                return
        if old:
            self.scrub = None
            self.viewport().update(self.visualRect(QModelIndex(old[0])))

    def leaveEvent(self, ev):
        super().leaveEvent(ev)
        if self.scrub:
            old = self.scrub
            self.scrub = None
            self.viewport().update(self.visualRect(QModelIndex(old[0])))

    def scrub_ready(self, key):
        if self.scrub:
            self.viewport().update(self.visualRect(QModelIndex(self.scrub[0])))


class ListView(_ViewMixin, QTreeView):
    """Vista Detalles con numeración de filas a la izquierda (se dibuja en el área de ramas)."""

    def setup_numbers(self, pane):
        self._numpane = pane
        self._nums = None
        m = self.model()
        for sig in (m.layoutChanged, m.modelReset, m.rowsInserted, m.rowsRemoved):
            sig.connect(self._invalidate_nums)
        self.apply_numbers()

    def numbers_on(self):
        return bool(self._numpane.app.cfg["list_row_numbers"])

    def apply_numbers(self):
        on = self.numbers_on()
        self.setRootIsDecorated(on)
        self._invalidate_nums()

    def _invalidate_nums(self, *a):
        self._nums = None
        if self.numbers_on():
            n = max(1, self.model().rowCount())
            ind = max(30, self.fontMetrics().horizontalAdvance(str(n)) + 18)
            if ind != self.indentation():
                self.setIndentation(ind)
            self.header().setStyleSheet(f"QHeaderView::section:first {{ padding-left:{ind + 8}px; }}")
        else:
            self.header().setStyleSheet("")
        self.viewport().update()

    def _row_numbers(self):
        if self._nums is None:
            nums, k, m = {}, 0, self.model()
            for r in range(m.rowCount()):
                e = m.index(r, 0).data(ROLE_ENTRY)
                if e is not None and e.kind != "header":
                    k += 1
                    nums[r] = k
            self._nums = nums
        return self._nums

    def drawBranches(self, p, rect, index):
        if not self.numbers_on() or index.parent().isValid():
            return
        n = self._row_numbers().get(index.row())
        if not n:
            return
        p.save()
        p.setPen(QColor("#7d7d7d"))
        p.drawText(rect.adjusted(0, 0, -8, 0), Qt.AlignRight | Qt.AlignVCenter, str(n))
        p.setPen(QColor("#2c2c2c"))
        p.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        p.restore()


class TabCloseButton(QToolButton):
    """× de la pestaña: grande y fino, con fondo al pasar el mouse (como Windows 11)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(24, 24)
        self.setToolTip("Close tab (Ctrl+W · middle click)")
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet("QToolButton{border:none;background:transparent;border-radius:5px;}"
                           "QToolButton:hover{background:#3a3a3a;}")

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#ffffff" if self.underMouse() else "#c5c5c5"), 1.3, Qt.SolidLine, Qt.RoundCap))
        c = QPointF(self.width() / 2, self.height() / 2)
        k = 4.0
        p.drawLine(QPointF(c.x() - k, c.y() - k), QPointF(c.x() + k, c.y() + k))
        p.drawLine(QPointF(c.x() + k, c.y() - k), QPointF(c.x() - k, c.y() + k))
        p.end()


class FilterButton(QToolButton):
    """Filtro de tipo de archivo entre la dirección y el buscador. Ancho fijo (no corre nada); cuando hay un
    filtro se resalta y muestra un dibujito del tipo (o «EXR»)."""

    def __init__(self, pane):
        super().__init__()
        self.pane = pane
        self.setFixedSize(52, 34)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setStyleSheet("QToolButton{border:none;} QToolButton::menu-indicator{image:none;width:0px;}")
        self.m = QMenu(self)
        self.m.aboutToShow.connect(self._fill)
        self.setMenu(self.m)
        self.setMouseTracking(True)
        self.setToolTip("Filter: show only one file type")

    def _fill(self):
        self.pane.app.set_active(self.pane)
        self.m.clear()
        cur = self.pane.filter.currentData()
        for i, (label, key) in enumerate(FILTERS):
            a = self.m.addAction(label, lambda i=i: self.pane.filter.setCurrentIndex(i))
            a.setCheckable(True)
            a.setChecked(key == cur)
            if i == 0:
                self.m.addSeparator()

    def paintEvent(self, ev):
        cat = self.pane.filter.currentData() or "all"
        on = cat != "all"
        label = next((l for l, k in FILTERS if k == cat), "")
        self.setToolTip("Filter: show only one file type" if not on else f"Filter on: {label}")
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        hover = self.underMouse()
        if on:
            p.setPen(QPen(QColor("#2f7fb0"), 1))
            p.setBrush(QColor("#164a6b" if hover else "#0f3a55"))
            p.drawRoundedRect(r, 5, 5)
        elif hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3a3a3a"))
            p.drawRoundedRect(r, 5, 5)
        c = QColor("#4cc2ff" if on else "#c5c5c5")
        cx, cy = 20.0, r.center().y()
        p.setPen(QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if cat == "all":
            f = QPainterPath()
            f.moveTo(cx - 7, cy - 6); f.lineTo(cx + 7, cy - 6); f.lineTo(cx + 2, cy + 1)
            f.lineTo(cx + 2, cy + 6); f.lineTo(cx - 2, cy + 7); f.lineTo(cx - 2, cy + 1); f.closeSubpath()
            p.drawPath(f)
        elif cat == "exr":
            fnt = QFont(self.font())
            fnt.setPointSizeF(7.5)
            fnt.setBold(True)
            p.setFont(fnt)
            p.setPen(c)
            p.drawText(QRectF(cx - 13, cy - 8, 26, 16), Qt.AlignCenter, "EXR")
        elif cat == "seq":
            for k in (4, 0, -4):
                p.drawRect(QRectF(cx - 6 + k * .5, cy - 5 - k * .5, 11, 9))
        elif cat == "video":
            p.drawRoundedRect(QRectF(cx - 8, cy - 6, 16, 12), 2, 2)
            t = QPainterPath()
            t.moveTo(cx - 2, cy - 3); t.lineTo(cx + 3, cy); t.lineTo(cx - 2, cy + 3); t.closeSubpath()
            p.fillPath(t, c)
        elif cat == "image":
            p.drawRoundedRect(QRectF(cx - 8, cy - 6, 16, 12), 2, 2)
            mnt = QPainterPath()
            mnt.moveTo(cx - 6, cy + 4); mnt.lineTo(cx - 1, cy - 1); mnt.lineTo(cx + 2, cy + 2)
            mnt.lineTo(cx + 4, cy); mnt.lineTo(cx + 7, cy + 4)
            p.drawPath(mnt)
        elif cat == "model":
            cube = QPainterPath()
            cube.moveTo(cx, cy - 7); cube.lineTo(cx + 7, cy - 3); cube.lineTo(cx + 7, cy + 4); cube.lineTo(cx, cy + 8)
            cube.lineTo(cx - 7, cy + 4); cube.lineTo(cx - 7, cy - 3); cube.closeSubpath()
            cube.moveTo(cx - 7, cy - 3); cube.lineTo(cx, cy + 1); cube.lineTo(cx + 7, cy - 3)
            cube.moveTo(cx, cy + 1); cube.lineTo(cx, cy + 8)
            p.drawPath(cube)
        elif cat == "dir":
            d = QPainterPath()
            d.moveTo(cx - 8, cy + 6); d.lineTo(cx - 8, cy - 6); d.lineTo(cx - 3, cy - 6); d.lineTo(cx - 1, cy - 4)
            d.lineTo(cx + 8, cy - 4); d.lineTo(cx + 8, cy + 6); d.closeSubpath()
            p.drawPath(d)
        else:      # media
            p.drawRoundedRect(QRectF(cx - 8, cy - 6, 10, 9), 2, 2)
            t = QPainterPath()
            t.moveTo(cx + 1, cy - 1); t.lineTo(cx + 8, cy + 3); t.lineTo(cx + 1, cy + 7); t.closeSubpath()
            p.fillPath(t, c)
        # flechita
        p.setPen(QPen(QColor("#c5c5c5"), 1.3))
        x = r.right() - 11
        p.drawLine(QPointF(x - 3, cy - 1), QPointF(x, cy + 2))
        p.drawLine(QPointF(x, cy + 2), QPointF(x + 3, cy - 1))
        p.end()


class WinTabBar(QTabBar):
    """Pestañas como las del Explorador de Windows 11: ancho fijo, se achican solo cuando no entran,
    el ＋ va pegado a la última pestaña."""
    TAB_W = 240
    MIN_W = 96

    def __init__(self):
        super().__init__()
        self.plus = QToolButton(self)
        self.plus.setAutoRaise(True)
        self.plus.setFixedSize(36, 32)
        self.plus.setIconSize(QSize(18, 18))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        f = self.font()
        f.setPointSizeF(10)
        self.setFont(f)

    def _avail(self):
        return max(self.MIN_W, self.width() - self.plus.width() - 10)

    def tabSizeHint(self, i):
        n = max(1, self.count())
        w = max(self.MIN_W, min(self.TAB_W, self._avail() // n))
        return QSize(w, 40)

    def minimumTabSizeHint(self, i):
        return QSize(self.MIN_W, self.tabSizeHint(i).height())

    def minimumSizeHint(self):
        return QSize(self.MIN_W + 40, 40)

    def sizeHint(self):
        return QSize(self.TAB_W + 40, 40)

    def _place_plus(self):
        if self.count():
            r = self.tabRect(self.count() - 1)
            x = min(r.right() + 6, self.width() - self.plus.width())
        else:
            x = 4
        self.plus.move(x, (self.height() - self.plus.height()) // 2)
        self.plus.raise_()

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self._place_plus()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._place_plus)

    def tabInserted(self, i):
        super().tabInserted(i)
        QTimer.singleShot(0, self._place_plus)

    def tabRemoved(self, i):
        super().tabRemoved(i)
        QTimer.singleShot(0, self._place_plus)

    def paintEvent(self, ev):
        """Como Windows 11: ícono y texto alineados a la izquierda, la activa en negrita y unida a la barra."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cur = self.currentIndex()
        mouse = self.mapFromGlobal(QCursor.pos())
        for i in range(self.count()):
            r = self.tabRect(i).adjusted(1, 4, -1, 0)
            sel = i == cur
            hover = r.contains(mouse) and not sel
            if sel or hover:
                path = QPainterPath()
                rr = QRectF(r).adjusted(0, 0, 0, 8)
                path.addRoundedRect(rr, 7, 7)
                p.save()
                p.setClipRect(r)
                p.fillPath(path, QColor("#2b2b2b" if sel else "#262626"))
                p.restore()
            elif i + 1 != cur and i < self.count() - 1:
                p.setPen(QColor("#3a3a3a"))
                p.drawLine(r.right() + 1, r.top() + 8, r.right() + 1, r.bottom() - 6)
            x = r.left() + 12
            ic = self.tabIcon(i)
            if not ic.isNull():
                ic.paint(p, QRect(x, r.center().y() - 8, 16, 16))
                x += 24
            f = self.font()
            f.setBold(sel)
            p.setFont(f)
            btn = self.tabButton(i, QTabBar.RightSide)
            right = (btn.geometry().left() - 4) if btn is not None and btn.isVisible() else r.right() - 8
            tr = QRect(x, r.top(), max(0, right - x), r.height())
            p.setPen(QColor("#ffffff" if sel else "#c5c5c5"))
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(self.tabText(i), Qt.ElideRight, tr.width()))
        p.end()

    def enterEvent(self, ev):
        self.setMouseTracking(True)
        super().enterEvent(ev)

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        self.update()

    def leaveEvent(self, ev):
        super().leaveEvent(ev)
        self.update()


class FilePane(QFrame):
    focused = Signal(object)
    selection_changed = Signal(object)
    location_changed = Signal(object)
    status_changed = Signal(object)

    def __init__(self, app, name):
        super().__init__()
        self.app = app
        self.name = name
        self.setObjectName("pane")
        self.model = EntryModel(app)
        self.proxy = EntryProxy(app)
        self.proxy.setSourceModel(self.model)
        app.thumbs.ready.connect(self.model.thumb_ready)
        app.meta.ready.connect(self.model.meta_ready)
        self.gen = 0
        self.workers = set()
        self.search_worker = None
        self.pending_select = None
        self.pending_edit = False            # New folder: queda con el nombre en edición
        self._loc_prev = self._loc_cur = None   # F7
        self._loc_sel = {}
        self._f7_resume = False
        self.tabs = []
        self.ti = -1
        self.view_mode = "grid"
        self.status_text = ""
        self.search_timer = QTimer(self, singleShot=True, interval=450, timeout=self._apply_search)
        self.root_lock = None          # función -> [raíces]; si está, el panel no sale de esas carpetas
        self.group_mode = "auto"       # auto | none | folder | type
        self.pill_labels = []          # pastillas de tags rápidos activas
        self.pill_kw = []
        self._pending = []
        self.flush_timer = QTimer(self, singleShot=True, interval=350, timeout=self._flush_pending)
        self._build()
        self.proxy.layoutChanged.connect(self._respan)
        self.proxy.modelReset.connect(self._respan)

    # ------------------------------------------------------------------ UI
    def _build(self):
        ic = self.app.icons
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("paneHeader")
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        # --- fila de pestañas (como la barra de pestañas del Explorador de Windows 11)
        tabsrow = QFrame()
        tabsrow.setObjectName("paneTabs")
        trow = QHBoxLayout(tabsrow)
        trow.setContentsMargins(6, 4, 6, 0)
        trow.setSpacing(2)
        self.tabbar = WinTabBar()
        self.tabbar.setTabsClosable(False)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setDrawBase(False)
        self.tabbar.setElideMode(Qt.ElideRight)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setIconSize(QSize(16, 16))
        self.tabbar.setAcceptDrops(True)
        self.tabbar.currentChanged.connect(self._tab_changed)
        # clic en una pestaña (aunque ya sea la actual, p. ej. la del otro panel): el foco va a su contenido
        self.tabbar.tabBarClicked.connect(lambda i: (not self.root_lock) and QTimer.singleShot(0, self._focus_view))
        self.tabbar.tabMoved.connect(self._tab_moved)
        self.tabbar.installEventFilter(self)
        self.tabbar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabbar.customContextMenuRequested.connect(self._tab_menu)
        trow.addWidget(self.tabbar, 1)

        def tb(glyph, tip, slot, row, size=18):
            b = QToolButton()
            b.setFixedSize(38, 34)
            b.setIconSize(QSize(size, size))
            b.setIcon(ic.glyph(glyph, size))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            row.addWidget(b)
            return b
        self.tabbar.plus.setIcon(ic.glyph("plus", 16))
        self.tabbar.plus.setToolTip("New tab (Ctrl+T)")
        self.tabbar.plus.clicked.connect(self.new_tab)
        self.tabsrow = tabsrow
        tabsrow.installEventFilter(self)
        self.corner = QHBoxLayout()        # acá va el selector de modo (Carpetas / VFX Library)
        self.corner.setContentsMargins(0, 0, 0, 0)
        trow.addLayout(self.corner)
        hl.addWidget(tabsrow)

        # --- fila de navegación: ← → ↑ ⟳ | dirección | buscar
        navrow = QFrame()
        navrow.setObjectName("paneNav")
        self.navrow = navrow
        nrow = QHBoxLayout(navrow)
        nrow.setContentsMargins(8, 7, 10, 7)
        nrow.setSpacing(6)
        self.b_back = tb("back", "Back (Alt+←)", self.go_back, nrow)
        self.b_fwd = tb("fwd", "Forward (Alt+→)", self.go_forward, nrow)
        self.b_up = tb("up", "Up (Alt+↑ · Backspace)", self.go_up, nrow)
        self.b_ref = tb("reload", "Refresh (F5)", self.refresh, nrow)
        self.nav_spacer = QWidget()
        self.nav_spacer.setFixedWidth(10)
        nrow.addWidget(self.nav_spacer)
        self.nav_buttons = (self.b_back, self.b_fwd, self.b_up, self.b_ref, self.nav_spacer)
        self.crumb = BreadcrumbBar()
        self.crumb.setMinimumWidth(140)
        self.crumb.navigate.connect(self.navigate)
        self.crumb.open_alt.connect(self._crumb_alt)
        nrow.addWidget(self.crumb, 7)
        self.filter = QComboBox(self)                 # estado del filtro de tipo (lo maneja el botón)
        for label, key in FILTERS:
            self.filter.addItem(label, key)
        self.filter.hide()
        self.b_filter = FilterButton(self)
        nrow.addWidget(self.b_filter)
        self.search = QLineEdit()
        self.search.setObjectName("paneSearch")
        self.search.setToolTip("Name or part · *wildcards* · (with tags on: #tag, ★3)\n"
                               "With «Subfolders» on it searches the whole branch · Ctrl+F · Esc clears")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(ic.glyph("search", 16, "#c5c5c5"), QLineEdit.TrailingPosition)
        self.search.setMinimumWidth(150)
        self.search.setFixedHeight(36)
        self.search.setStyleSheet("QLineEdit{font-size:10.5pt; padding:4px 10px; border-radius:5px;"
                                  "border:1px solid #333333; background:#2d2d2d;}"
                                  "QLineEdit:focus{background:#1f1f1f; border-bottom:2px solid #4cc2ff;}")
        self.search.textChanged.connect(self._on_search_text)
        self.search.textChanged.connect(lambda *_: self._notify_nav())
        self.search.returnPressed.connect(self._apply_search)
        nrow.addWidget(self.search, 3)
        hl.addWidget(navrow)

        # --- estado que se maneja desde la barra de comandos (no se muestra en el panel)
        self.filter.currentIndexChanged.connect(self._apply_search)
        self.filter.currentIndexChanged.connect(lambda *_: self.b_filter.update())
        self.filter.currentIndexChanged.connect(lambda *_: self.app.sync_commandbar(self))
        self.filter.hide()
        self.rec = QToolButton(self)
        self.rec_level = 2                 # con Subcarpetas: 1 = un nivel · 2 = toda la rama (como Found)
        self.rec.setCheckable(True)
        self.rec.toggled.connect(self._apply_search)
        self.rec.toggled.connect(lambda *_: self.app.sync_commandbar(self))
        self.rec.hide()
        self.b_grid = QToolButton(self)
        self.b_list = QToolButton(self)
        for b in (self.b_grid, self.b_list):
            b.setCheckable(True)
            b.hide()
        lay.addWidget(self.header)
        # doble panel: línea celeste arriba del contenido del panel activo (justo de su ancho)
        self.active_bar = QFrame()
        self.active_bar.setObjectName("paneActiveBar")
        self.active_bar.setFixedHeight(2)
        lay.addWidget(self.active_bar)

        self.banner = QLabel()
        self.banner.setObjectName("paneBanner")
        self.banner.setTextFormat(Qt.RichText)
        self.banner.setWordWrap(False)
        self.banner.setCursor(Qt.PointingHandCursor)
        self.banner.setToolTip("Click to see only this folder again")
        self.banner.mousePressEvent = lambda ev: self._banner_clicked()
        self.banner.hide()
        lay.addWidget(self.banner)

        # vistas
        self.grid = GridView()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid._setup(self)   # después de setMovement: Static apaga el drag & drop
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(2)
        self.grid.setWrapping(True)
        self.grid.setMouseTracking(True)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.grid.verticalScrollBar().setSingleStep(24)
        self.grid.setModel(self.proxy)
        self.grid.setItemDelegate(GridDelegate(self.app, self.grid))
        self.app.thumbs.ready.connect(self.grid.scrub_ready)
        ts = int(self.app.cfg["thumb_size"])
        self.thumb_size = ts
        self.grid.setIconSize(QSize(ts, ts))

        self.list = ListView()
        self.list._setup(self)
        self.list.setModel(self.proxy)
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setSortingEnabled(True)
        self.list.setAlternatingRowColors(True)
        self.list.setIconSize(QSize(18, 18))
        self.list.setItemDelegate(ListNameDelegate(self.list))
        self.list.setup_numbers(self)
        hd = self.list.header()
        hd.setStretchLastSection(True)
        hd.setSectionResizeMode(QHeaderView.Interactive)
        hd.resizeSection(0, 320)
        for c, w in zip(range(1, len(COLS)), (120, 90, 55, 50, 75, 115, 60, 130, 200)):
            hd.resizeSection(c, w)
        self.list.sortByColumn(0, Qt.AscendingOrder)
        self.list.setColumnHidden(C_FOLDER, True)
        hd.moveSection(hd.visualIndex(C_FOLDER), 1)     # "Carpeta" al lado del nombre
        hd.sortIndicatorChanged.connect(lambda c, o: self.proxy.sort(c, o))
        hd.sortIndicatorChanged.connect(lambda *_: self._save_folder_view())
        hd.setContextMenuPolicy(Qt.CustomContextMenu)
        hd.customContextMenuRequested.connect(self._header_menu)
        self._folder_col_default = False
        self._applying_view = False
        self.grid.setObjectName("fileGrid")
        self.list.setObjectName("fileList")

        for v in (self.grid, self.list):
            v.activated.connect(self._activate)
            if not IS_WIN:
                v.doubleClicked.connect(self._activate)
            v.customContextMenuRequested.connect(lambda pos, v=v: self.app.item_menu(self, v, pos))
            v.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed.emit(self))
            v.selectionModel().selectionChanged.connect(lambda *_: self._track_tab_sel())
            v.selectionModel().selectionChanged.connect(lambda *_: self._remember_sel())
            self._view_shortcuts(v)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.list)
        lay.addWidget(self.stack, 1)

        self.footer = QLabel()
        self.footer.setObjectName("paneFooter")
        lay.addWidget(self.footer)

        self._pane_shortcuts()
        self.set_view("grid", emit=False)
        self.apply_features()
        for w in (self.search, self.filter, self.rec, self.crumb.edit):
            w.installEventFilter(self)

    def _view_shortcuts(self, v):
        a = self.app

        def sc(keys, fn):
            QShortcut(QKeySequence(keys), v, fn, context=Qt.WidgetShortcut)
        sc(Qt.Key_Backspace, self.go_up)
        sc(QKeySequence.Delete, lambda: a.op_trash(self))
        sc("Shift+Del", lambda: a.op_trash(self, permanent=True))
        sc("Ctrl+C", lambda: a.op_clip(self, cut=False))
        sc("Ctrl+X", lambda: a.op_clip(self, cut=True))
        sc("Ctrl+V", lambda: a.op_paste(self))
        sc("Ctrl+Shift+C", lambda: a.copy_paths(self, "hash"))
        sc("Ctrl+Alt+C", lambda: a.copy_paths(self, "nuke"))
        sc("Ctrl+Shift+N", lambda: a.op_new_folder(self))
        sc("Ctrl+E", lambda: a.op_tags(self))
        for n in range(6):                       # rating (con las funciones de librería prendidas)
            sc(f"Alt+{n}", lambda n=n: a.op_rating(self, n))

    def _pane_shortcuts(self):
        def sc(keys, fn):
            QShortcut(QKeySequence(keys), self, fn, context=Qt.WidgetWithChildrenShortcut)
        sc("Alt+Left", self.go_back)
        sc("Alt+Right", self.go_forward)
        sc("Alt+Up", self.go_up)
        sc("F5", self.refresh)
        sc("Ctrl+T", self.new_tab)
        sc("Ctrl+W", lambda: self.close_tab(self.ti))
        sc("Ctrl+Shift+T", self.reopen_closed_tab)
        sc("Ctrl+Tab", lambda: self.tabbar.setCurrentIndex((self.ti + 1) % max(1, len(self.tabs))))
        sc("Ctrl+Shift+Tab", lambda: self.tabbar.setCurrentIndex((self.ti - 1) % max(1, len(self.tabs))))
        sc("Ctrl+L", self.crumb.start_edit)
        sc("Ctrl+F", self.focus_search)
        # Ctrl+Shift+1 / 2 (vista) los maneja la ventana: Shift+número cambia de tecla según el teclado
        sc("Ctrl+B", lambda: self.set_rec_level({0: 1, 1: 2, 2: 0}[self.rec_value()]))

    def _tab_drop_target(self, ev):
        i = self.tabbar.tabAt(ev.position().toPoint())
        if i < 0 or i >= len(self.tabs) or self.tabs[i]["virtual"]:
            return None
        p = self.tabs[i]["path"]
        return p if os.path.isdir(p) else None

    def _window_drag(self, ev):
        """El espacio vacío de la fila de pestañas mueve la ventana (doble click: maximizar)."""
        win = self.window()
        if ev.type() == QEvent.MouseButtonDblClick:
            win.showNormal() if win.isMaximized() else win.showMaximized()
            return True
        if ev.button() == Qt.LeftButton and win.windowHandle() is not None:
            win.windowHandle().startSystemMove()
            return True
        return False

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) and (
                obj is self.tabsrow or (obj is self.tabbar and self.tabbar.tabAt(ev.position().toPoint()) < 0)):
            self.focused.emit(self)
            if self._window_drag(ev):
                return True
        if obj is self.tabbar and ev.type() in (QEvent.DragEnter, QEvent.DragMove):
            if ev.mimeData().hasUrls():
                ev.accept()
                if ev.type() == QEvent.DragMove and not self._tab_drop_target(ev):
                    ev.ignore()
            else:
                ev.ignore()
            return True
        if obj is self.tabbar and ev.type() == QEvent.Drop:
            target = self._tab_drop_target(ev)
            paths = [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
            mods = ev.modifiers()
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            if target and paths:
                pos = QCursor.pos()
                QTimer.singleShot(0, lambda: self.app.handle_drop(self, paths, target, mods, pos))
            return True
        if obj is self.tabbar and ev.type() == QEvent.MouseButtonRelease and ev.button() == Qt.MiddleButton:
            i = self.tabbar.tabAt(ev.position().toPoint())
            if i >= 0:
                self.close_tab(i)
                return True
        if ev.type() == QEvent.FocusIn:
            self.focused.emit(self)
        if obj is getattr(self, "search", None) and ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self.search.clear()
            self.view().setFocus()
            return True
        return super().eventFilter(obj, ev)

    def set_active(self, active):
        self.setProperty("active", bool(active))
        for w in (self, self.active_bar):
            w.setProperty("active", bool(active))
            w.style().unpolish(w)
            w.style().polish(w)

    def view(self):
        return self.grid if self.stack.currentIndex() == 0 else self.list

    # ------------------------------------------------------------------ columnas (vista Detalles)
    def _apply_columns(self, folder_default=None):
        """Columnas visibles: las que el usuario tildó en el menú del encabezado (como en Windows 11)."""
        if folder_default is not None:
            self._folder_col_default = folder_default
        vis = self.app.cfg["list_cols"] or {}
        lib = bool(self.app.cfg["library_features"])
        for c, name in enumerate(COLS):
            if c == C_NAME:
                continue
            if c in (C_RATING, C_TAGS) and not lib:
                self.list.setColumnHidden(c, True)
                continue
            default = self._folder_col_default if c == C_FOLDER else (c not in VFX_COLS)
            self.list.setColumnHidden(c, not vis.get(name, default))
        order = self.app.cfg["col_order"]
        if order:
            hd = self.list.header()
            for i, name in enumerate(n for n in order if n in COLS):
                lg = COLS.index(name)
                if hd.visualIndex(lg) != i:
                    hd.moveSection(hd.visualIndex(lg), i)

    def _header_menu(self, pos):
        hd = self.list.header()
        col = hd.logicalIndexAt(pos)
        m = QMenu(self)
        a = m.addAction("Size column to fit", lambda: self.list.resizeColumnToContents(col))
        a.setEnabled(col >= 0)
        m.addAction("Size all columns to fit", self.fit_columns)
        a = m.addAction("Row numbers", self.app._toggle_row_numbers)
        a.setCheckable(True)
        a.setChecked(bool(self.app.cfg["list_row_numbers"]))
        m.addSeparator()
        self.app.fill_layout_menu(m.addMenu("Column layout"), self)
        m.addSeparator()
        lib = bool(self.app.cfg["library_features"])
        for c in sorted(range(len(COLS)), key=hd.visualIndex):
            name = COLS[c]
            if c in (C_RATING, C_TAGS) and not lib:
                continue
            a = m.addAction(name, lambda c=c: self._toggle_column(c))
            a.setCheckable(True)
            a.setChecked(not self.list.isColumnHidden(c))
            a.setEnabled(c != C_NAME)
        m.exec(hd.mapToGlobal(pos))

    def _toggle_column(self, c):
        vis = dict(self.app.cfg["list_cols"] or {})
        vis[COLS[c]] = self.list.isColumnHidden(c)
        self.app.cfg["list_cols"] = vis
        self.app.cfg.save()
        for p in self.app.all_panes:
            p._apply_columns()

    def fit_columns(self):
        hd = self.list.header()
        last = max((c for c in range(len(COLS)) if not self.list.isColumnHidden(c)), key=hd.visualIndex, default=0)
        for c in range(len(COLS)):
            if not self.list.isColumnHidden(c) and c != last:
                self.list.resizeColumnToContents(c)

    # ------------------------------------------------------------------ vista por carpeta
    VIEW_DEFAULT = {"view": "list", "sort": 0, "order": 0, "group": "auto"}      # como Windows: Detalles
    THISPC_DEFAULT = {"view": "grid", "sort": 0, "order": 0, "group": "auto"}             # Íconos grandes
    PICTURES_DEFAULT = {"view": "grid", "size": 240, "sort": 0, "order": 0, "group": "auto"}   # Íconos grandes
    DOWNLOADS_DEFAULT = {"view": "list", "sort": 6, "order": 1, "group": "date"}          # agrupado por fecha

    def _fv_key(self):
        t = self.tab()
        if not t:
            return None
        if t["virtual"]:
            return THISPC if t["virtual"]["kind"] == "thispc" else None     # This PC también recuerda su vista
        if t["path"] == THISPC or norm_key(t["path"]) == norm_key(THISPC):
            return THISPC
        if self.root_lock:                          # la VFX Library recuerda sus vistas aparte
            return "lib:" + norm_key(t["path"])
        return norm_key(t["path"])

    def _apply_folder_view(self):
        """Cada carpeta recuerda su vista, orden y agrupado (como Windows)."""
        k = self._fv_key()
        if not k:
            return
        st = (self.app.cfg["folder_views"] or {}).get(k)
        self._fv_generic = False
        if not st:
            sp = getattr(self.app, "_sys_path", None)
            pics = sp("pictures") if sp else ""
            downs = sp("downloads") if sp else ""
            if k == THISPC:
                st = self.THISPC_DEFAULT
            elif pics and norm_key(pics) == k:
                st = self.PICTURES_DEFAULT
            elif downs and norm_key(downs) == k:
                st = self.DOWNLOADS_DEFAULT
            elif sp and sp("videos") and norm_key(sp("videos")) == k:
                st = self.PICTURES_DEFAULT               # Videos: Íconos grandes
            elif self.root_lock:                     # VFX Library: Íconos grandes para todo
                st = self.PICTURES_DEFAULT
            else:
                st = self.app.cfg["folder_view_default"] or self.VIEW_DEFAULT
                self._fv_generic = True            # solo estas carpetas pasan solas a íconos si hay imágenes
        self._apply_state(st)

    def _auto_image_view(self, entries):
        """Carpeta sin vista guardada con secuencias o imágenes → Íconos grandes directamente."""
        k = self._fv_key()
        if not k or k == THISPC or (self.app.cfg["folder_views"] or {}).get(k) \
                or not getattr(self, "_fv_generic", False):      # Downloads, Pictures… tienen la suya
            return
        if any(e.kind == "seq" or (e.kind == "file" and e.ext in IMAGE_EXTS) for e in entries):
            self._apply_state(self.PICTURES_DEFAULT, details=False)

    def _apply_state(self, st, details=True):
        self._applying_view = True
        try:
            if st.get("view", "grid") != self.view_mode:
                self.set_view(st.get("view", "grid"), emit=False)
            self.group_mode = st.get("group", "auto")
            size = int(st.get("size") or self.app.cfg["thumb_size"])
            if size != self.thumb_size:
                self.set_thumb_size(size)
                if self.app.active is self and hasattr(self.app, "size_slider"):
                    self.app.size_slider.blockSignals(True)
                    self.app.size_slider.setValue(size)
                    self.app.size_slider.blockSignals(False)
            col = int(st.get("sort", 0))
            order = Qt.DescendingOrder if int(st.get("order", 0)) else Qt.AscendingOrder
            hd = self.list.header()
            if hd.sortIndicatorSection() != col or hd.sortIndicatorOrder() != order:
                self.list.sortByColumn(col, order)
            if details and "details" in st and hasattr(self.app, "info_area") and self.app.active is self \
                    and st["details"] != self.app.info_area.isVisible():
                self.app.toggle_details(st["details"], remember=False)
        finally:
            self._applying_view = False

    def _view_state(self):
        hd = self.list.header()
        st = {"view": self.view_mode, "sort": hd.sortIndicatorSection(),
              "order": 1 if hd.sortIndicatorOrder() == Qt.DescendingOrder else 0, "group": self.group_mode,
              "size": self.thumb_size}
        if hasattr(self.app, "info_area"):
            st["details"] = self.app.info_area.isVisible()
        return st

    def _save_folder_view(self):
        if self._applying_view or getattr(self, "_view_pending", False) or not getattr(self.app, "_ready", False):
            return
        k = self._fv_key()
        if not k:
            return
        fv = dict(self.app.cfg["folder_views"] or {})
        fv.pop(k, None)
        fv[k] = self._view_state()
        while len(fv) > 3000:
            fv.pop(next(iter(fv)))
        self.app.cfg["folder_views"] = fv
        self.app.save_soon()

    def apply_view_to_all(self):
        """«Apply to all folders»: esta vista pasa a ser la de todas las carpetas."""
        self.app.cfg["folder_view_default"] = self._view_state()
        self.app.cfg["folder_views"] = {}
        self.app.cfg.save()

    def set_view(self, mode, emit=True):
        self.view_mode = mode
        self.stack.setCurrentIndex(0 if mode == "grid" else 1)
        self.b_grid.setChecked(mode == "grid")
        self.b_list.setChecked(mode != "grid")
        if hasattr(self.app, "sync_commandbar"):
            self.app.sync_commandbar(self)
        if emit:
            self._save_folder_view()
            self.app.save_soon()

    # ------------------------------------------------------------------ grupos
    def effective_group(self, virtual=None):
        mode = self.group_mode or "auto"
        if mode == "auto":
            v = self.model.virtual if virtual is None else virtual
            return "folder" if (v and self.rec.isChecked()) else "none"
        return mode

    def set_group(self, mode):
        self.group_mode = mode
        self._save_folder_view()
        self.model.regroup(self.effective_group())
        self._grid_uniform()
        self.proxy.refresh_groups()
        self._sort()
        self._update_status()
        self.app.save_soon()

    def _grid_uniform(self):
        self.grid.setUniformItemSizes(self.model.group_mode == "none")

    def _respan(self, *a):
        if self.model.group_mode == "none":
            return
        for r in range(self.proxy.rowCount()):
            e = self.proxy.index(r, 0).data(ROLE_ENTRY)
            self.list.setFirstColumnSpanned(r, self.list.rootIndex(), e is not None and e.kind == "header")

    def apply_features(self):
        on = bool(self.app.cfg["library_features"])
        self._apply_columns()
        if not self.banner.isVisible():
            self.search.setPlaceholderText(self._placeholder())
            self._notify_nav()

    def set_thumb_size(self, v):
        self.thumb_size = int(v)
        self.grid.setIconSize(QSize(int(v), int(v)))

    # ------------------------------------------------------------------ pestañas
    def tab(self):
        return self.tabs[self.ti] if 0 <= self.ti < len(self.tabs) else None

    def tab_path(self):
        t = self.tab()
        return t["path"] if t else ""

    def lock_root_for(self, path):
        """Raíz de la librería que contiene path (o None)."""
        if not self.root_lock:
            return None
        for r in self.root_lock():
            if path and is_subpath(path, r):
                return r
        return None

    def allowed(self, path):
        return not self.root_lock or self.lock_root_for(path) is not None

    def add_tab(self, path, activate=True):
        virtual = None
        if path == THISPC and not self.root_lock:
            # la pestaña nace ya como This PC (antes se abría la carpeta del usuario y después cambiaba)
            virtual = {"title": "This PC", "kind": "thispc", "name": ""}
            path = os.path.expanduser("~")
        if self.root_lock:
            roots = self.root_lock()
            if not self.allowed(path):
                path = roots[0] if roots else ""
            if not path:
                return
        path = path or os.path.expanduser("~")
        t = {"path": os.path.normpath(path), "history": [THISPC if virtual else os.path.normpath(path)], "hpos": 0,
             "virtual": virtual}
        self.tabs.append(t)
        self.tabbar.blockSignals(True)
        i = self.tabbar.addTab(self._tab_icon(t), self._tab_title(t))
        self.tabbar.setTabToolTip(i, "This PC" if virtual else t["path"])
        close = QWidget()                       # contenedor: deja aire a la derecha, como Windows
        close.setFixedSize(34, 28)
        cl = QHBoxLayout(close)
        cl.setContentsMargins(0, 0, 8, 0)
        btn = TabCloseButton()
        btn.clicked.connect(lambda c=False, b=close: self._close_by_button(b))
        cl.addWidget(btn, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.tabbar.setTabButton(i, QTabBar.RightSide, close)
        self.tabbar.blockSignals(False)
        if activate or len(self.tabs) == 1:
            self.tabbar.setCurrentIndex(i)
            if self.ti != i:
                self._tab_changed(i)
        self.app.save_soon()

    def _remember_closed(self, t):
        """Ctrl+Shift+T: la pestaña cerrada (con su historial) queda para volver a abrirla."""
        here = THISPC if (t["virtual"] and t["virtual"]["kind"] == "thispc") else (None if t["virtual"] else t["path"])
        if not here:
            return
        st = self.app.__dict__.setdefault("closed_tabs", {}).setdefault("lib" if self.root_lock else "exp", [])
        st.append({"path": here, "history": list(t["history"]), "hpos": t["hpos"]})
        del st[:-30]

    def reopen_closed_tab(self):
        st = self.app.__dict__.get("closed_tabs", {}).get("lib" if self.root_lock else "exp") or []
        while st:
            c = st.pop()
            if c["path"] == THISPC or self.allowed(c["path"]):
                self.add_tab(c["path"])
                t = self.tabs[-1]
                if c["path"] != THISPC and c["history"]:
                    t["history"], t["hpos"] = c["history"], min(c["hpos"], len(c["history"]) - 1)
                    self._show_location()
                self.app.status.setText("Tab reopened")
                return
        self.app.status.setText("No closed tabs to reopen")

    def close_tab(self, i):
        if 0 <= i < len(self.tabs):
            self._remember_closed(self.tabs[i])
        if len(self.tabs) <= 1 and 0 <= i < len(self.tabs):
            self.app.close_pane(self)          # doble panel: cierra ese panel · un solo panel: cierra la app
            return
        if not (0 <= i < len(self.tabs)):
            return
        self.tabs.pop(i)
        self.tabbar.blockSignals(True)
        self.tabbar.removeTab(i)
        self.tabbar.blockSignals(False)
        self.ti = -1
        self._tab_changed(self.tabbar.currentIndex())
        self.app.save_soon()

    def _close_by_button(self, b):
        for i in range(self.tabbar.count()):
            if self.tabbar.tabButton(i, QTabBar.RightSide) is b:
                self.close_tab(i)
                return

    def _tab_moved(self, frm, to):
        self.tabs.insert(to, self.tabs.pop(frm))
        self.ti = self.tabbar.currentIndex()
        self.app.save_soon()

    def _tab_sel_names(self):
        """Lo seleccionado ahora (nombres), para recordarlo en la pestaña."""
        return [e.name for e in self.selected_entries()[:200]]

    def _track_tab_sel(self):
        """La pestaña va guardando lo que se selecciona en su carpeta (sobrevive a recargas y cambios de pestaña)."""
        t = self.tab()
        if t is None or t["virtual"] or self.root_lock or self.model.virtual \
                or not same_path(self.model.root or "", t["path"]):
            return
        t["sel"] = {"path": t["path"], "names": self._tab_sel_names()}

    def _keep_tab_sel(self):
        """File Explorer: cada pestaña recuerda qué tenía seleccionado (en su carpeta)."""
        old = self.tab()
        if old is not None and not old["virtual"] and not self.root_lock and self.model.entries \
                and not self.model.virtual and same_path(self.model.root or "", old["path"]):
            old["sel"] = {"path": old["path"], "names": self._tab_sel_names()}

    def _tab_changed(self, i):
        if i < 0 or i >= len(self.tabs) or i == self.ti:
            return
        self._keep_tab_sel()
        self.ti = i
        t = self.tab()
        sel = t.get("sel") if not self.root_lock else None
        if sel and not t["virtual"] and same_path(sel.get("path", ""), t["path"]):
            self.pending_select = list(sel.get("names") or []) or None
        if t["virtual"]:
            self._load_virtual()
        else:
            self._show_location()
            self._load()
        if not self.root_lock and getattr(self.app, "active", None) is self:
            QTimer.singleShot(0, self._focus_view)      # cambio de pestaña en el panel activo (Ctrl+Tab, clic)

    def _focus_view(self):
        """El foco va al contenido de la pestaña en la que se está (y el panel queda activo)."""
        if not self.isVisible():
            return
        try:
            self.view().setFocus(Qt.TabFocusReason)
        except RuntimeError:
            pass

    def _tab_icon(self, t):
        ic = self.app.icons
        v = t.get("virtual")
        if v:
            if v["kind"] == "thispc":
                return ic.glyph("pc", 16, "#4cc2ff")
            if v["kind"] in ("tag", "rating"):
                return ic.glyph("search", 16, "#c9ccd1")
            return ic.glyph("library", 16, "#4cc2ff")
        p = t["path"]
        if os.path.dirname(p.rstrip("\\/")) in ("", p.rstrip("\\/")) or len(p.rstrip("\\/")) <= 2:
            return ic.drive_icon("network" if is_network_path(p) else "local", 16)
        return ic.folder_icon(self.app.dir_color(p), 16)

    def _tab_title(self, t):
        if t.get("virtual"):
            return t["virtual"]["title"]
        p = t["path"].rstrip("\\/")
        return os.path.basename(p) or t["path"]

    def _update_tab(self):
        t = self.tab()
        if t:
            self.tabbar.setTabText(self.ti, self._tab_title(t))
            self.tabbar.setTabIcon(self.ti, self._tab_icon(t))
            self.tabbar.setTabToolTip(self.ti, t["virtual"]["title"] if t["virtual"] else t["path"])

    def _tab_menu(self, pos):
        i = self.tabbar.tabAt(pos)
        if i < 0:
            return
        m = QMenu(self)
        m.addAction("Duplicate tab", lambda: self.add_tab(self.tabs[i]["path"]))
        m.addAction("Close", lambda: self.close_tab(i)).setEnabled(len(self.tabs) > 1)

        def close_others():
            keep = self.tabs[i]
            for j in reversed(range(len(self.tabs))):
                if self.tabs[j] is not keep:
                    self.close_tab(j)
        m.addAction("Close other tabs", close_others).setEnabled(len(self.tabs) > 1)
        m.addSeparator()
        st = self.app.__dict__.get("closed_tabs", {}).get("lib" if self.root_lock else "exp") or []
        m.addAction("Reopen closed tab\tCtrl+Shift+T", self.reopen_closed_tab).setEnabled(bool(st))
        m.exec(self.tabbar.mapToGlobal(pos))

    def state(self):
        tabs = []
        for i, t in enumerate(self.tabs):
            d = {"path": THISPC if (t["virtual"] and t["virtual"]["kind"] == "thispc") else t["path"]}
            if not self.root_lock and not t["virtual"]:          # File Explorer: lo seleccionado en cada pestaña
                if i == self.ti and self.model.entries:
                    d["sel"] = self._tab_sel_names()
                elif t.get("sel") and same_path(t["sel"].get("path", ""), t["path"]):
                    d["sel"] = list(t["sel"].get("names") or [])
            tabs.append(d)
        return {"tabs": tabs, "current": self.ti, "view": self.view_mode, "group": self.group_mode}

    def new_tab(self):
        """Pestaña nueva: en Carpetas abre Este equipo (como Windows); en la librería, la carpeta actual."""
        if self.root_lock:
            self.add_tab(self.current_dir() or self.tab_path())
        else:
            self.add_tab(THISPC)

    def clear_tabs(self):
        self.tabbar.blockSignals(True)
        while self.tabbar.count():
            self.tabbar.removeTab(0)
        self.tabbar.blockSignals(False)
        self.tabs = []
        self.ti = -1

    def restore(self, st, fallback):
        sels = {t.get("path"): t.get("sel") for t in (st or {}).get("tabs", []) if t.get("path") and t.get("sel")}
        tabs = [t.get("path") for t in (st or {}).get("tabs", []) if t.get("path")]
        # una pestaña en un NAS apagado no traba el arranque: se abre igual y avisa (al volver la red, Refresh)
        from .core import safe_isdir
        tabs = [p for p in tabs if p == THISPC or not reachable(p, 0.3) or safe_isdir(p, 0.3)] or [fallback]
        if self.root_lock:
            tabs = [p for p in tabs if self.allowed(p)] or ([fallback] if fallback else [])
        for p in tabs:
            self.add_tab(p, activate=False)
            if sels.get(p) and not self.root_lock and not self.tabs[-1]["virtual"]:
                self.tabs[-1]["sel"] = {"path": p, "names": list(sels[p])}
        self.set_view((st or {}).get("view", "grid"), emit=False)
        self.group_mode = (st or {}).get("group", "auto")
        cur = min(max(0, int((st or {}).get("current", 0))), len(self.tabs) - 1)
        if self.tabbar.currentIndex() == cur and self.ti != cur:
            self._tab_changed(cur)
        self.tabbar.setCurrentIndex(cur)
        if self.ti < 0:
            self._tab_changed(cur)
        t = self.tab()                        # la pestaña activa vuelve con lo que tenía seleccionado
        if t is not None and t.get("sel") and not t["virtual"] and same_path(t["sel"].get("path", ""), t["path"]):
            self.pending_select = list(t["sel"].get("names") or []) or None

    # ------------------------------------------------------------------ navegación
    def current_dir(self):
        t = self.tab()
        return None if (t is None or t["virtual"]) else t["path"]

    def navigate(self, path, add_history=True, select=None, new_tab=False):
        path = (path or "").strip().strip('"').strip("'")
        if not path:
            return
        if path == THISPC:
            if self.root_lock:
                return
            if new_tab:
                self.add_tab(THISPC)
                return
            t = self.tab()
            if t is not None and add_history and t["history"][t["hpos"]] != THISPC:
                t["history"] = t["history"][: t["hpos"] + 1] + [THISPC]
                t["hpos"] = len(t["history"]) - 1
            self.show_virtual("This PC", "thispc", "")
            return
        path = os.path.expandvars(os.path.expanduser(path))
        if not reachable(path):
            self._set_status(f"Network location not available: {path}  (it retries by itself; Refresh when it's back)")
            self.crumb.set_path(self.tab_path())
            return
        from .core import net_root
        ext = os.path.splitext(path)[1]
        # en la red solo se pregunta si es archivo cuando el nombre lo parece (un NAS lento no traba la navegación)
        if (not net_root(path) or (ext and len(ext) <= 6 and ext[1:].isalnum())) and os.path.isfile(path):
            select = os.path.basename(path)
            path = os.path.dirname(path)
        if not net_root(path) and not os.path.isdir(path):     # en la red lo dice la lectura (otro hilo)
            self._set_status(f"Folder doesn't exist: {path}")
            self.crumb.set_path(self.tab_path())
            return
        path = os.path.normpath(os.path.abspath(path))
        if IS_WIN and len(path) == 2 and path[1] == ":":
            path += "\\"
        if not self.allowed(path):
            self._set_status("The VFX Library only browses inside its folders (add them with the ＋ of «VFX LIBRARY»)")
            self.crumb.set_path(self.tab_path(), root=self.lock_root_for(self.tab_path()))
            return
        if new_tab:
            self.add_tab(path)
            return
        t = self.tab()
        if t is None:
            self.add_tab(path)
            return
        was_virtual = t["virtual"] is not None
        t["virtual"] = None
        if add_history and (was_virtual or not same_path(t["history"][t["hpos"]], path)):
            t["history"] = t["history"][: t["hpos"] + 1]
            t["history"].append(path)
            t["hpos"] = len(t["history"]) - 1
        t["path"] = path
        self.pending_select = select
        self._show_location()
        self._load()
        self.app.save_soon()

    def _show_location(self):
        t = self.tab()
        if not t:
            return
        self.crumb.set_path(t["path"], t["virtual"]["title"] if t["virtual"] else "",
                            root=self.lock_root_for(t["path"]))
        if not self.banner.isVisible():
            self.search.setPlaceholderText(self._placeholder())
            self._notify_nav()
        if t["virtual"]:
            self._apply_folder_view()
        else:
            # la vista de la carpeta se aplica cuando llega su contenido (si no, por un instante se ve la
            # carpeta anterior con la vista nueva)
            self._view_pending = True
        self.b_back.setEnabled(t["hpos"] > 0 or bool(t["virtual"]))
        self.b_fwd.setEnabled(t["hpos"] < len(t["history"]) - 1)
        top = (t["virtual"] and t["virtual"]["kind"] == "thispc") or t["path"] == THISPC
        if self.root_lock and not t["virtual"]:
            top = any(same_path(t["path"], r) for r in self.root_lock())
        self.b_up.setEnabled(not top)
        # F7: recuerda las dos últimas ubicaciones (carpetas o This PC) para ir y volver
        loc = THISPC if (t["virtual"] and t["virtual"]["kind"] == "thispc") else (None if t["virtual"] else t["path"])
        if loc and loc != self._loc_cur:
            self._loc_prev, self._loc_cur = self._loc_cur, loc
        self._notify_nav()
        self._update_tab()
        self.location_changed.emit(self)

    def _crumb_alt(self, path):
        """Ctrl+Enter en la barra: un archivo se abre; una carpeta, en una pestaña nueva."""
        p = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
        if reachable(p) and os.path.isfile(p):
            from .core import Entry
            name = os.path.basename(p)
            e = Entry(kind="file", dirpath=os.path.dirname(p), name=name, path=p, ext=os.path.splitext(name)[1].lower())
            self.app.open_entry(e)
        else:
            self.navigate(p, new_tab=True)

    def _remember_sel(self):
        """Lo seleccionado en cada ubicación (F7 vuelve con eso seleccionado: en la librería, el video
        que se estaba viendo)."""
        if self._loc_cur:
            ents = self.selected_entries()
            if ents:
                self._loc_sel[self._loc_cur] = [e.name for e in ents[:50]]

    def go_previous(self):
        """F7: va a la ubicación anterior (y otra vez F7 vuelve). Si está abierta en otra pestaña, va a esa."""
        prev = self._loc_prev
        if not prev:
            return
        want = self._loc_sel.get(prev)
        for i, tt in enumerate(self.tabs):
            if i != self.ti:
                here = THISPC if (tt["virtual"] and tt["virtual"]["kind"] == "thispc") else tt["path"]
                if not tt["virtual"] or here == THISPC:
                    if here == prev or (prev != THISPC and same_path(here, prev)):
                        self.tabbar.setCurrentIndex(i)
                        return
        self.navigate(prev)
        if want:
            self._f7_resume = True
            self.pending_select = list(want)

    def go_back(self):
        t = self.tab()
        if not t:
            return
        if t["virtual"] and t["virtual"]["kind"] != "thispc":
            self.navigate(t["path"], add_history=False)
            return
        if t["hpos"] > 0:
            t["hpos"] -= 1
            self.navigate(t["history"][t["hpos"]], add_history=False)

    def go_forward(self):
        t = self.tab()
        if t and t["hpos"] < len(t["history"]) - 1:
            t["hpos"] += 1
            self.navigate(t["history"][t["hpos"]], add_history=False)

    def go_up(self):
        t = self.tab()
        if not t:
            return
        if (t["virtual"] and t["virtual"]["kind"] == "thispc") or t["path"] == THISPC:
            return                                  # This PC es el nivel más alto
        if t["virtual"]:
            self.navigate(t["path"], add_history=False)
            return
        cur = t["path"]
        if self.root_lock and any(same_path(cur, r) for r in self.root_lock()):
            self._set_status("You're at the library root")
            return
        parent = os.path.dirname(cur.rstrip("\\/"))
        if (not parent or same_path(parent, cur) or same_path(os.path.dirname(cur), cur)) and not self.root_lock:
            self.navigate(THISPC)
            return
        if parent and not same_path(parent, cur):
            if IS_WIN and len(parent) == 2 and parent[1] == ":":
                parent += "\\"
            self.navigate(parent, select=os.path.basename(cur.rstrip("\\/")))

    # ------------------------------------------------------------------ puesta al día sola
    @staticmethod
    def _live_stamp(e):
        return (e.size, round(e.mtime or 0, 2))

    @classmethod
    def _live_sig(cls, entries):
        # nombre + tamaño + fecha: también detecta un archivo pisado por otro con el mismo nombre
        return sorted((e.kind, e.name, len(e.files) if e.kind == "seq" else 0, cls._live_stamp(e))
                      for e in entries if e.kind != "header")

    def live_update(self):
        """La pestaña visible se pone al día sola (archivos nuevos / borrados / renombrados): se relee en otro
        hilo y solo si cambió algo se actualiza, sin perder la selección ni el scroll."""
        t = self.tab()
        if t is None or t["virtual"] or self._recursive_active() or getattr(self, "_live_busy", False):
            return
        path = self.tab_path()
        if not path:
            return
        gen = self.gen
        sh = bool(self.app.cfg["show_hidden"])
        col = bool(self.app.cfg["collapse_seqs"])
        self._live_busy = True

        def scan():
            from .core import scan_dir
            if not reachable(path):            # en otro hilo: un NAS dormido no traba la ventana
                return None
            try:
                return scan_dir(path, sh, col)
            except Exception:
                return None

        def got(entries):
            self._live_busy = False
            if entries is None or gen != self.gen or not same_path(self.tab_path() or "", path):
                return
            if self._live_sig(entries) == self._live_sig(self.model.entries):
                return
            # los que se pisaron (mismo nombre, otra fecha/tamaño): thumbnail nuevo y, si están seleccionados,
            # Details se vuelve a cargar
            old = {(e.kind, e.name): e for e in self.model.entries if e.kind != "header"}
            changed = [e for e in entries if (e.kind, e.name) in old and e.kind != "dir"
                       and self._live_stamp(old[(e.kind, e.name)]) != self._live_stamp(e)]
            th = self.app.thumbs
            th.invalidate([th.key_for(e) for e in changed] + [th.key_for(old[(e.kind, e.name)]) for e in changed])
            self._live_prev = self._tab_sel_names()
            touched_sel = bool({e.name for e in changed} & set(self._live_prev))
            if touched_sel:
                self._live_prev = None             # fuerza que Details se actualice
            bars = (self.grid.verticalScrollBar().value(), self.list.verticalScrollBar().value())
            self.pending_select = self._tab_sel_names() or None
            if touched_sel and hasattr(self.app, "_info_entry"):
                self.app._info_entry = None
            self._live = True
            try:
                self.gen += 1
                self._scan_done(self.gen, path, entries, "")
            finally:
                self._live = False
            self.grid.verticalScrollBar().setValue(bars[0])
            self.list.verticalScrollBar().setValue(bars[1])
        from .asyncdir import run_async
        run_async(scan, got, self)

    def refresh(self):
        self.app.thumbs.failed.clear()
        self.app.thumbs.index.clear()
        t = self.tab()
        if t and t["virtual"]:
            self._load_virtual()
        else:
            self._load()

    # ------------------------------------------------------------------ carga
    def _notify_nav(self):
        """Avisa a la ventana (buscador y ← → ↑ ⟳ compartidos entre los paneles de File Explorer)."""
        if hasattr(self.app, "sync_nav"):
            self.app.sync_nav(self)

    def focus_search(self):
        if self.search.isVisible():
            self.search.setFocus()
            self.search.selectAll()
        else:
            self.app.set_active(self)
            self.app.gsearch.setFocus()
            self.app.gsearch.selectAll()

    def rec_value(self):
        return self.rec_level if self.rec.isChecked() else 0

    def set_rec_level(self, v):
        """Subcarpetas: 0 = apagado · 1 = esta carpeta y sus subcarpetas directas · 2 = toda la rama."""
        v = int(v)
        if v and v != self.rec_level:
            self.rec_level = v
            if self.rec.isChecked():
                self._apply_search()
        self.rec.setChecked(bool(v))
        self.app.sync_commandbar(self)

    def _recursive_active(self):
        return (self.rec.isChecked() or bool(self.pill_kw)) and not self.is_virtual()

    def _query(self):
        q = parse_query(self.search.text())
        if self.pill_kw and not self.is_virtual():
            q.any_of = list(self.pill_kw)
            q.any_root = self.tab_path()
        return q

    def set_hide_images(self, hide):
        """Mostrar / ocultar imágenes sueltas: vuelve a leer la carpeta (o la búsqueda) para que la vista
        se rearme entera, igual que con Refresh."""
        self.proxy.hide_images = bool(hide)
        t = self.tab()
        if t and t["virtual"]:
            self._load_virtual()
        elif t:
            self._load()

    def set_pills(self, labels, keywords):
        """Tags rápidos: busca en toda la rama los elementos cuyo nombre, carpeta o tag coincida."""
        self.pill_labels, self.pill_kw = list(labels), list(keywords)
        if self.tabs:
            self._load()

    def _load(self):
        self.app.thumbs.cancel_pending()
        if self._recursive_active():
            if getattr(self, "_view_pending", False):
                self._view_pending = False
                self._apply_folder_view()
            self._start_search()
            return
        self._stop_search()
        self.gen += 1
        self._set_status("Reading…")
        w = ScanWorker(self.gen, self.tab_path(), bool(self.app.cfg["show_hidden"]),
                       collapse=bool(self.app.cfg["collapse_seqs"]))
        w.done.connect(self._scan_done)
        self._track(w)
        w.start()

    def _track(self, w):
        self.workers.add(w)
        w.finished.connect(lambda w=w: self.workers.discard(w))

    def _scan_done(self, gen, path, entries, err):
        if gen != self.gen:
            return
        live = getattr(self, "_live", False)
        if getattr(self, "_view_pending", False):
            self._view_pending = False
            self._apply_folder_view()
        if not live:
            self._auto_image_view(entries)
        self.model.group_mode = self.effective_group(virtual=False)
        self.model.set_entries(entries, path, virtual=False)
        self._apply_columns(folder_default=False)
        self._set_banner(None)
        self._grid_uniform()
        self.proxy.set_filter(self._query(), self.filter.currentData())
        self._sort()
        self._update_status(f"Error: {err}" if err else None)
        t = self.tab()
        if self.pending_select is None and not self.root_lock and t is not None and t.get("sel") \
                and same_path(t["sel"].get("path", ""), path):
            self.pending_select = list(t["sel"].get("names") or []) or None     # una recarga no la pierde
        self._select_pending()
        if not self.root_lock and not (live and self._tab_sel_names() == getattr(self, "_live_prev", None)):
            # Details al día con lo seleccionado (o vacío): vaciar la vista no avisa por sí solo
            # (en una puesta al día sola, si la selección no cambió, Details no se toca: el video sigue)
            self.selection_changed.emit(self)
        self.app.request_dir_sizes(self, entries)

    def _sort(self):
        hd = self.list.header()
        self.proxy.sort(hd.sortIndicatorSection(), hd.sortIndicatorOrder())

    def _select_pending(self):
        names = self.pending_select
        self.pending_select = None
        if not names:
            return
        if isinstance(names, str):
            names = [names]
        v = self.view()
        first = None
        sel = v.selectionModel()
        sel.clearSelection()
        for r, e in enumerate(self.model.entries):
            if e.name in names or any(n in e.files for n in names):
                pix = self.proxy.mapFromSource(self.model.index(r, 0))
                if pix.isValid():
                    sel.select(pix, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                    first = first or pix
        if first is not None:
            sel.setCurrentIndex(first, QItemSelectionModel.NoUpdate)
            v.scrollTo(first)
            if self.pending_edit:
                pix = QPersistentModelIndex(first.sibling(first.row(), 0))
                v.setFocus()
                QTimer.singleShot(0, lambda: pix.isValid() and v.edit(self.proxy.index(pix.row(), 0)))
        self.pending_edit = False

    # ------------------------------------------------------------------ búsqueda
    def _on_search_text(self, _):
        if self.rec.isChecked() or (self.tab() and self.tab()["virtual"]):
            self.search_timer.start()
        else:
            self._apply_search()

    def _apply_search(self):
        self.search_timer.stop()
        t = self.tab()
        if t and t["virtual"]:
            self.proxy.set_filter(self._query(), self.filter.currentData())
            self._update_status()
            return
        if self._recursive_active():
            self._start_search()
        elif self.model.virtual:
            self._load()
        else:
            self.proxy.set_filter(self._query(), self.filter.currentData())
            self._update_status()

    def _stop_search(self):
        if self.search_worker:
            self.search_worker.cancelled = True
            self.search_worker = None

    def _start_search(self):
        self._stop_search()
        self.app.thumbs.cancel_pending()
        self.gen += 1
        self._pending = []
        self.model.group_mode = self.effective_group(virtual=True)
        self.model.set_entries([], self.tab_path(), virtual=True)
        self._grid_uniform()
        self._apply_columns(folder_default=True)
        self._set_banner(0, scanning=0)
        self.proxy.set_filter(parse_query(""), "all")
        depth = 1 if (self.rec.isChecked() and self.rec_level == 1) else None
        w = SearchWorker(self.gen, self.tab_path(), self._query(), self.filter.currentData(),
                         bool(self.app.cfg["show_hidden"]), self.app.lib.snapshot(), max_depth=depth,
                         collapse=bool(self.app.cfg["collapse_seqs"]))
        w.batch.connect(self._search_batch)
        w.progress.connect(self._search_progress)
        w.finished_search.connect(self._search_done)
        self._track(w)
        self.search_worker = w
        self._set_status("Searching…")
        w.start()

    def _search_batch(self, gen, entries):
        if gen == self.gen:
            if self.model.group_mode != "none":
                self._pending.extend(entries)      # con grupos se reagrupa cada tanto (no por cada carpeta)
                if not self.flush_timer.isActive():
                    self.flush_timer.start()
            else:
                self.model.append_entries(entries)
            self.app.request_dir_sizes(self, entries)

    def _flush_pending(self):
        if not self._pending:
            return
        items = self.model.items() + self._pending
        self._pending = []
        self.model.set_entries(items, self.model.root, virtual=self.model.virtual)
        self.proxy.refresh_groups()
        self._sort()

    def _search_progress(self, gen, scanned, d):
        if gen == self.gen:
            self._set_status(f"Searching… {len(self.model.entries)} results · {scanned} folders")
            self._set_banner(len(self.model.entries), scanning=scanned)

    def _search_done(self, gen, found, capped):
        if gen != self.gen:
            return
        self.search_worker = None
        self.flush_timer.stop()
        self._flush_pending()
        self._sort()
        extra = f" (limit {SearchWorker.MAX_RESULTS})" if capped else ""
        self._set_banner(found, capped=capped)
        self._update_status(f"{'Search in' if self.search.text().strip() else 'All contents of'} "
                            f"subfolders: {found}{extra}")

    def _banner_clicked(self):
        if self.pill_kw:
            self.app.clear_pills()
        self.rec.setChecked(False)

    def _set_banner(self, count, scanning=None, capped=False):
        """Barra que deja claro que se está viendo el contenido de las subcarpetas."""
        if count is None:
            self.banner.hide()
            self.search.setPlaceholderText(self._placeholder())
            self._notify_nav()
            return
        root = os.path.basename(self.tab_path().rstrip("\\/")) or self.tab_path()
        q = self.search.text().strip()
        what = f"Results for «{q}»" if q else "All files"
        if self.pill_labels:
            what = " · ".join(self.pill_labels) + (f" + «{q}»" if q else "")
        tail = f" · searching… ({scanning} folders)" if scanning else (" · limit reached" if capped else "")
        lvl = " (1 level)" if (self.rec.isChecked() and self.rec_level == 1) else ""
        self.banner.setText(f"<b>⤓ {what}</b> in <b>{root}</b> and its subfolders{lvl} — {count} found{tail}"
                            f"&nbsp;&nbsp;<span style='color:#cfe0ff'>✕ show only this folder</span>")
        self.banner.show()
        self.search.setPlaceholderText(f"Search {root} and subfolders")
        self._notify_nav()

    def _placeholder(self):
        t = self.tab()
        if t and t["virtual"]:
            return f"Search {t['virtual']['title']}"
        name = os.path.basename(self.tab_path().rstrip("\\/")) if self.tabs else ""
        return f"Search {name}" if name else "Search"

    # ------------------------------------------------------------------ vistas virtuales (tags, colecciones)
    def show_virtual(self, title, kind, name, new_tab=False):
        if new_tab:
            self.add_tab(self.current_dir() or self.tab_path())
        t = self.tab()
        t["virtual"] = {"title": title, "kind": kind, "name": name}
        self._show_location()
        self._load_virtual()

    def _load_virtual(self):
        self._stop_search()
        self.app.thumbs.cancel_pending()
        t = self.tab()
        v = t["virtual"]
        if v["kind"] == "thispc":
            self.gen += 1
            self.model.group_mode = "drives"
            self.model.set_entries([], "", virtual=True)
            if not self.root_lock:
                self.selection_changed.emit(self)          # Details vacío (This PC no tiene selección)
            self._grid_uniform()
            self._apply_columns(folder_default=False)
            self._set_banner(None)
            self._show_location()
            self._set_status("Reading drives…")
            w = DrivesWorker(self.gen)
            w.done.connect(self._drives_done)
            self._track(w)
            w.start()
            return
        refs = self.app.refs_for(v["kind"], v["name"])
        self.gen += 1
        self.model.set_entries([], "", virtual=True)
        if not self.root_lock:
            self.selection_changed.emit(self)
        self._apply_columns(folder_default=True)
        self._set_banner(None)
        self._show_location()
        self._set_status("Searching the library…")
        w = ResolveWorker(self.gen, refs)
        w.done.connect(self._virtual_done)
        self._track(w)
        w.start()

    def _drives_done(self, gen, entries):
        if gen != self.gen:
            return
        self.model.group_mode = "drives"
        self.model.set_entries(entries, "", virtual=True)
        self._grid_uniform()
        self.proxy.set_filter(parse_query(""), "all")
        self._sort()
        n = len(entries)
        self._set_status(f"{n} {'drive' if n == 1 else 'drives'}")

    def _virtual_done(self, gen, entries, n_missing):
        if gen != self.gen:
            return
        self.model.group_mode = self.effective_group(virtual=True)
        self.model.set_entries(entries, "", virtual=True)
        self._grid_uniform()
        self.proxy.set_filter(self._query(), self.filter.currentData())
        self._sort()
        extra = f" · {n_missing} not found (moved or deleted)" if n_missing else ""
        self._update_status(f"{self.tab()['virtual']['title']}{extra}")

    def is_virtual(self):
        t = self.tab()
        return bool(t and t["virtual"])

    def virtual_info(self):
        t = self.tab()
        return t["virtual"] if t else None

    # ------------------------------------------------------------------ selección / abrir
    def selected_entries(self):
        v = self.view()
        rows = v.selectionModel().selectedRows(0) if v is self.list else v.selectionModel().selectedIndexes()
        out, seen = [], set()
        for ix in rows:
            e = ix.data(ROLE_ENTRY)
            if e is not None and e.kind != "header" and id(e) not in seen:
                seen.add(id(e))
                out.append(e)
        return out

    def _activate(self, ix):
        e = ix.data(ROLE_ENTRY)
        if e is None or e.kind == "header":
            return
        if e.kind in ("dir", "drive"):
            self.navigate(e.path)
        else:
            self.app.open_entry(e)

    # ------------------------------------------------------------------ estado
    def _set_status(self, text):
        self.status_text = text
        self.footer.setText(text)
        self.status_changed.emit(self)

    def _update_status(self, prefix=None):
        counts = {}
        for r in range(self.proxy.rowCount()):
            e = self.proxy.mapToSource(self.proxy.index(r, 0)).data(ROLE_ENTRY)
            if e.kind != "header":
                counts[e.cat] = counts.get(e.cat, 0) + 1
        parts = []
        for k, lbl in (("dir", "folders"), ("seq", "sequences"), ("video", "videos"), ("image", "images"),
                       ("model", "scenes/models"), ("other", "other")):
            if counts.get(k):
                parts.append(f"{counts[k]} {lbl}")
        txt = " · ".join(parts) or "empty"
        self._set_status(f"{prefix} — {txt}" if prefix else txt)
