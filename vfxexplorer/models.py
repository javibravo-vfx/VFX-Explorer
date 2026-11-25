# -*- coding: utf-8 -*-
"""Modelo de ítems, proxy de filtro/orden y workers de escaneo/búsqueda."""

import os
import time

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QMimeData, QUrl, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon

from .core import (IMAGE_EXTS, date_group, DATE_GROUPS, scan_dir, entry_matches, resolve_refs, natural_key, human_size, fmt_time, fwd,
                   compress_ranges, Query, list_drives)

ROLE_ENTRY = Qt.UserRole + 1
ROLE_SORT = Qt.UserRole + 2

COLS = ["Name", "Type", "Range", "Frames", "Missing", "Size", "Modified", "Rating", "Tags", "Folder",
        "Resolution", "FPS", "Codec", "Channels", "Colorspace"]
C_NAME, C_TYPE, C_RANGE, C_FRAMES, C_MISSING, C_SIZE, C_MTIME, C_RATING, C_TAGS, C_FOLDER, \
    C_RES, C_FPS, C_CODEC, C_CH, C_CS = range(15)
META_COLS = {C_RES: "res", C_FPS: "fps", C_CODEC: "codec", C_CH: "ch", C_CS: "cs"}
VFX_COLS = tuple(META_COLS)       # se leen del archivo (en segundo plano)


def entry_tooltip(e, lib=None):
    if e.kind == "seq":
        t = f"{e.name}\nFrames {e.first}-{e.last} ({len(e.frames)})"
        if e.missing:
            t += f"\nMissing {len(e.missing)}: {compress_ranges(e.missing)[:300]}"
        t += f"\n{human_size(e.size)}"
    else:
        t = e.name
    if lib:
        tags = lib.tags(e.key())
        if tags:
            t += "\n#" + "  #".join(tags)
    return t


class EntryModel(QAbstractTableModel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.entries = []
        self.root = ""
        self.virtual = False
        self.key_rows = {}
        self.group_mode = "none"

    def set_entries(self, entries, root, virtual=False):
        self.beginResetModel()
        self.entries = [e for e in entries if e.kind != "header"]
        self.root = root
        self.virtual = virtual
        if self.group_mode != "none":
            self._build_groups()
        self._reindex()
        self.endResetModel()

    def items(self):
        return [e for e in self.entries if e.kind != "header"]

    # ---------------- grupos (encabezados por carpeta o por tipo)
    TYPE_GROUPS = [("dir", "Folders"), ("seq", "Sequences"), ("video", "Videos"), ("image", "Pictures"),
                   ("model", "3D scenes / models"), ("other", "Other")]

    def regroup(self, mode):
        self.beginResetModel()
        self.group_mode = mode
        self.entries = self.items()
        if mode != "none":
            self._build_groups()
        self._reindex()
        self.endResetModel()

    def _build_groups(self):
        groups = {}
        import datetime as _dt
        today = _dt.date.today()
        order = {k: i for i, (k, _) in enumerate(self.TYPE_GROUPS)}
        labels = dict(self.TYPE_GROUPS)
        for e in self.entries:
            if self.group_mode == "drives":
                net = getattr(e, "drive_kind", "local") == "network"
                key = (1 if net else 0,)
                label = "Network locations" if net else "Devices and drives"
            elif self.group_mode == "date":
                gi = date_group(e.mtime, today)
                key = (gi,)
                label = DATE_GROUPS[gi]
            elif self.group_mode == "type":
                c = e.cat
                key = (order.get(c, 99),)
                label = labels.get(c, "Other")
            else:
                rel = self.folder_text(e) if self.root else e.dirpath
                key = tuple(natural_key(rel if rel != "." else ""))
                label = "(this folder)" if rel == "." else rel
            e._g = key
            g = groups.setdefault(key, [label, 0, 0])
            g[1] += 1
            g[2] += e.size or 0
        from .core import Entry
        for key, (label, n, size) in groups.items():
            h = Entry(kind="header", dirpath="", name=label, path="", size=size)
            h._g = key
            h.count = n
            self.entries.append(h)

    def append_entries(self, entries):
        if not entries:
            return
        n = len(self.entries)
        self.beginInsertRows(QModelIndex(), n, n + len(entries) - 1)
        self.entries.extend(entries)
        for i, e in enumerate(entries, n):
            self.key_rows.setdefault(e.thumb_source(), []).append(i)
        self.endInsertRows()

    def _reindex(self):
        self.key_rows = {}
        self.path_rows = {}
        for i, e in enumerate(self.entries):
            self.key_rows.setdefault(e.thumb_source(), []).append(i)
            self.path_rows.setdefault(e.path, []).append(i)

    def display_name(self, e):
        """Nombre que se ve (en la VFX Library, prolijo si está la opción; F2 y la barra muestran el real)."""
        if getattr(self, "lib_mode", False) and self.app.cfg["lib_pretty_names"] and e.kind in ("dir", "file", "seq"):
            from .core import pretty_name
            return pretty_name(e.name, keep_ext=e.kind != "dir")
        return e.name

    def meta_ready(self, path):
        for r in getattr(self, "path_rows", {}).get(path, []):
            self.dataChanged.emit(self.index(r, C_RES), self.index(r, C_CS), [Qt.DisplayRole])

    def thumb_ready(self, key):
        for r in self.key_rows.get(key, []):
            ix = self.index(r, 0)
            self.dataChanged.emit(ix, ix, [Qt.DecorationRole])

    def dir_size_ready(self, path, size):
        hit = False
        for i, e in enumerate(self.entries):
            if e.kind == "dir" and e.path == path:
                e.size = size
                hit = True
                ix = self.index(i, C_SIZE)
                self.dataChanged.emit(self.index(i, 0), ix)
        return hit

    def refresh_all(self):
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, len(COLS) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        if self.entries[index.row()].kind == "header":
            return Qt.NoItemFlags            # los títulos de grupo no son ítems: las flechas los saltan
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        if index.column() == C_NAME:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid() or index.column() != C_NAME:
            return False
        e = self.entries[index.row()]
        value = (value or "").strip()
        if not value or value == e.name:
            return False
        return bool(self.app.rename_inline(e, value))

    def supportedDragActions(self):
        return Qt.CopyAction

    def folder_text(self, e):
        if self.root:
            rel = os.path.relpath(e.dirpath, self.root)
            return "." if rel == "." else fwd(rel)
        return fwd(e.dirpath)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        e = self.entries[index.row()]
        col = index.column()
        lib = self.app.lib
        if role == ROLE_ENTRY:
            return e
        if e.kind == "drive":
            if role == Qt.DisplayRole:
                if col == C_NAME:
                    return e.name
                if col == C_TYPE:
                    return e.type_label()
                if col == C_SIZE:
                    return human_size(e.size)
                if col == C_RANGE:
                    return f"{human_size(getattr(e, 'free', 0))} free"
                return ""
            if role == Qt.DecorationRole and col == C_NAME:
                return self.app.icons.drive_icon(getattr(e, "drive_kind", "local"), 18)
            if role == ROLE_SORT:
                return natural_key(e.path) if col == C_NAME else (e.size if col == C_SIZE else 0)
            if role == Qt.ToolTipRole:
                return f"{e.name}\n{getattr(e, 'unc', '') or e.path}\n{human_size(getattr(e, 'free', 0))} free of {human_size(e.size)}"
            return None
        if e.kind == "header":
            if role == Qt.DisplayRole:
                return f"{e.name}   ({getattr(e, 'count', 0)} · {human_size(e.size)})" if col == C_NAME else ""
            if role == Qt.ForegroundRole:
                return QColor(self.app.accent())
            if role == Qt.FontRole:
                f = QFont()
                f.setBold(True)
                return f
            return None
        if role == Qt.EditRole and col == C_NAME:
            return e.name
        if role == Qt.DisplayRole:
            if col == C_NAME:
                return self.display_name(e)
            if col == C_TYPE:
                return e.type_label()
            if col == C_RANGE:
                return f"{e.first}-{e.last}" if e.kind == "seq" else ""
            if col == C_FRAMES:
                return str(len(e.frames)) if e.kind == "seq" else ""
            if col == C_MISSING:
                return str(len(e.missing)) if e.kind == "seq" and e.missing else ""
            if col == C_SIZE:
                return (human_size(e.size) if e.size else "") if e.kind == "dir" else human_size(e.size)
            if col == C_MTIME:
                return fmt_time(e.mtime)
            if col == C_RATING:
                r = lib.rating(e.key())
                return "★" * r if r else ""
            if col == C_TAGS:
                return ", ".join(lib.tags(e.key()))
            if col == C_FOLDER:
                return self.folder_text(e)
            if col in META_COLS:
                m = self.app.meta.get(e)
                return "…" if m is None else (m.get(META_COLS[col]) or "")
        if role == ROLE_SORT:
            if col == C_NAME:
                return natural_key(e.name)
            if col == C_TYPE:
                return e.type_label()
            if col == C_RANGE:
                return e.first if e.kind == "seq" else -1
            if col == C_FRAMES:
                return len(e.frames)
            if col == C_MISSING:
                return len(e.missing)
            if col == C_SIZE:
                return e.size
            if col == C_MTIME:
                return e.mtime
            if col == C_RATING:
                return lib.rating(e.key())
            if col == C_TAGS:
                return ", ".join(lib.tags(e.key())).lower()
            if col == C_FOLDER:
                return natural_key(e.dirpath)
            if col in META_COLS:
                m = self.app.meta.cache.get(self.app.meta.key_for(e)) if self.app.meta.applies(e) else None
                v = (m or {}).get(META_COLS[col]) or ""
                if col == C_RES and "×" in v:
                    try:
                        w, h = v.split("×")
                        return int(w) * 100000 + int(h)
                    except ValueError:
                        return 0
                if col == C_FPS:
                    try:
                        return float(v)
                    except ValueError:
                        return 0.0
                return v.lower() if col != C_RES else 0
        if role == Qt.DecorationRole and col == C_NAME:
            if e.kind == "dir":
                return self.app.icons.folder_icon(self.app.entry_color(e, getattr(self, "lib_mode", False)), 18)
            sp = self.app.sys_icon(e, 18)
            return QIcon(sp) if sp is not None else self.app.icons.badge(e)
        if role == Qt.ForegroundRole:
            if col == C_MISSING and e.kind == "seq" and e.missing:
                return QColor("#ff6b6b")
            if col == C_RATING:
                return QColor("#f5c542")
            if col == C_TAGS:
                return QColor("#8fb3ff")
            if col == C_NAME:
                cf = self.app.color_filter_for(e)
                if cf and cf[0]:
                    return QColor(cf[0])
        if role == Qt.BackgroundRole and col == C_NAME:
            cf = self.app.color_filter_for(e)
            if cf and cf[1]:
                return QColor(cf[1])
        if role == Qt.BackgroundRole and e.kind != "dir":
            c = lib.color(e.key())
            if c:
                q = QColor(c)
                q.setAlpha(55)
                return q
        if role == Qt.TextAlignmentRole and col in (C_FRAMES, C_MISSING, C_SIZE):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            return entry_tooltip(e, lib if self.app.cfg["library_features"] else None)
        return None

    def mimeTypes(self):
        return ["text/uri-list", "text/plain"]

    def mimeData(self, indexes):
        seen, ents = set(), []
        for ix in indexes:
            e = self.entries[ix.row()]
            if id(e) not in seen:
                seen.add(id(e))
                ents.append(e)
        md = QMimeData()
        urls, texts = [], []
        for e in ents:
            urls += [QUrl.fromLocalFile(p) for p in e.all_paths()]
            texts.append(f"{fwd(e.pattern_path('printf'))} {e.first}-{e.last}" if e.kind == "seq" else fwd(e.path))
        md.setUrls(urls)
        md.setText("\n".join(texts))
        return md


class EntryProxy(QSortFilterProxyModel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.query = Query()
        self.cat = "all"
        self.setSortRole(ROLE_SORT)
        self.setDynamicSortFilter(False)

    def set_filter(self, query, cat):
        self.query, self.cat = query, cat
        self.refresh_groups()

    def refresh_groups(self):
        m = self.sourceModel()
        self._ok_groups = set()
        if m is not None and m.group_mode != "none":
            for e in m.entries:
                if e.kind != "header" and self._accept(e):
                    self._ok_groups.add(getattr(e, "_g", None))
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        m = self.sourceModel()
        e = m.entries[row]
        if e.kind == "header":
            return getattr(e, "_g", None) in getattr(self, "_ok_groups", set())
        return self._accept(e)

    hide_images = False          # VFX Library: ocultar imágenes sueltas (las secuencias quedan)

    def _accept(self, e):
        m = self.sourceModel()
        if self.hide_images and e.kind == "file" and e.ext in IMAGE_EXTS:
            return False
        if m.virtual:
            if self.query.empty and self.cat == "all":
                return True
            if e.kind == "dir" and self.cat not in ("all", "dir", "noraw"):
                return False
            return entry_matches(e, self.query, self.cat, meta=self.app.lib.meta)
        if e.kind == "dir" and self.cat not in ("all", "dir", "noraw"):
            return False                  # con un filtro de tipo se ven solo esos archivos, sin carpetas
        return entry_matches(e, self.query, self.cat, meta=self.app.lib.meta)

    def lessThan(self, left, right):
        m = self.sourceModel()
        a, b = m.entries[left.row()], m.entries[right.row()]
        asc = self.sortOrder() == Qt.AscendingOrder
        if m.group_mode != "none":
            ga, gb = getattr(a, "_g", ()), getattr(b, "_g", ())
            if ga != gb:
                return (ga < gb) == asc          # los grupos siempre en el mismo orden
            if (a.kind == "header") != (b.kind == "header"):
                return (a.kind == "header") == asc
        if (a.kind == "dir") != (b.kind == "dir"):
            return (a.kind == "dir") == (self.sortOrder() == Qt.AscendingOrder)
        va, vb = left.data(ROLE_SORT), right.data(ROLE_SORT)
        try:
            if va == vb:
                return natural_key(a.name) < natural_key(b.name)
            return va < vb
        except TypeError:
            return str(va) < str(vb)


# ----------------------------------------------------------------------------
# Workers
# ----------------------------------------------------------------------------

class ScanWorker(QThread):
    done = Signal(int, str, object, str)

    def __init__(self, gen, path, show_hidden, collapse=True):
        super().__init__()
        self.gen, self.path, self.show_hidden, self.collapse = gen, path, show_hidden, collapse

    def run(self):
        try:
            self.done.emit(self.gen, self.path, scan_dir(self.path, self.show_hidden, self.collapse), "")
        except Exception as ex:
            self.done.emit(self.gen, self.path, [], str(ex))


class SearchWorker(QThread):
    batch = Signal(int, object)
    progress = Signal(int, int, str)
    finished_search = Signal(int, int, bool)
    MAX_RESULTS = 20000

    def __init__(self, gen, root, query, cat, show_hidden, meta, max_depth=None, collapse=True):
        super().__init__()
        self.collapse = collapse
        self.gen, self.root, self.query, self.cat = gen, root, query, cat
        self.show_hidden, self.meta = show_hidden, meta
        self.max_depth = max_depth          # None = toda la rama · 1 = solo las subcarpetas directas
        self.cancelled = False

    def run(self):
        stack, found, scanned, last = [(self.root, 0)], 0, 0, 0.0
        while stack and not self.cancelled:
            d, depth = stack.pop()
            try:
                entries = scan_dir(d, self.show_hidden, self.collapse)
            except OSError:
                continue
            scanned += 1
            hits, subdirs = [], []
            for e in entries:
                if e.kind == "dir":
                    subdirs.append(e.path)
                if entry_matches(e, self.query, self.cat, recursive=True, meta=self.meta.get):
                    hits.append(e)
            if self.max_depth is None or depth < self.max_depth:
                stack.extend((x, depth + 1) for x in sorted(subdirs, key=natural_key, reverse=True))
            if hits:
                found += len(hits)
                self.batch.emit(self.gen, hits)
            now = time.time()
            if now - last > 0.15:
                last = now
                self.progress.emit(self.gen, scanned, d)
            if found >= self.MAX_RESULTS:
                self.finished_search.emit(self.gen, found, True)
                return
        self.finished_search.emit(self.gen, found, False)


class DrivesWorker(QThread):
    done = Signal(int, object)

    def __init__(self, gen):
        super().__init__()
        self.gen = gen

    def run(self):
        try:
            self.done.emit(self.gen, list_drives())
        except Exception:
            self.done.emit(self.gen, [])


class ResolveWorker(QThread):
    done = Signal(int, object, int)

    def __init__(self, gen, refs):
        super().__init__()
        self.gen, self.refs = gen, refs

    def run(self):
        try:
            found, missing = resolve_refs(self.refs)
        except Exception:
            found, missing = [], self.refs
        self.done.emit(self.gen, found, len(missing))
