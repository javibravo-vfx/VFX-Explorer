# -*- coding: utf-8 -*-
"""Operaciones de archivo: copiar / mover con progreso, renombrar y renumerar secuencias,
papelera, carpeta nueva y portapapeles compatible con el Explorador de Windows."""

import os
import re
import shutil
import ctypes

from PySide6.QtCore import QThread, Signal, QMimeData, QUrl, QFile

from .core import IS_WIN, fwd, same_path, norm_key

DROP_EFFECT_FMT = 'application/x-qt-windows-mime;value="Preferred DropEffect"'
INVALID_CHARS = set('<>:"/\\|?*')
CHUNK = 8 * 1024 * 1024


# ----------------------------------------------------------------------------
# Portapapeles
# ----------------------------------------------------------------------------

def make_clip_mime(paths, cut=False):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(p) for p in paths])
    md.setData(DROP_EFFECT_FMT, (2 if cut else 5).to_bytes(4, "little"))
    return md


def read_clip_mime(md):
    paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md is not None else []
    cut = False
    if md is not None and md.hasFormat(DROP_EFFECT_FMT):
        b = bytes(md.data(DROP_EFFECT_FMT))
        if len(b) >= 1:
            v = int.from_bytes(b[:4].ljust(4, b"\0"), "little")
            cut = bool(v & 2) and not (v & 1)
    return [os.path.normpath(p) for p in paths if p], cut


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------

def valid_name(name):
    name = name.strip()
    if not name or name in (".", "..") or any(c in INVALID_CHARS for c in name):
        return False
    return not name.endswith((".", " "))


def is_subpath(child, parent):
    c, p = norm_key(child), norm_key(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def is_network_path(path):
    p = os.path.abspath(path)
    if p.startswith("\\\\") or p.startswith("//"):
        return True
    if IS_WIN:
        try:
            root = os.path.splitdrive(p)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 4  # DRIVE_REMOTE
        except Exception:
            return False
    return False


def new_folder(parent, name):
    if not valid_name(name):
        raise ValueError("Invalid name")
    p = os.path.join(parent, name.strip())
    if os.path.exists(p):
        raise FileExistsError(f"Already exists: {name}")
    os.makedirs(p)
    return p


# ----------------------------------------------------------------------------
# Papelera
# ----------------------------------------------------------------------------

def _trash_windows(paths):
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    errors = []
    for i in range(0, len(paths), 2000):
        batch = [os.path.abspath(p) for p in paths[i:i + 2000]]
        buf = ctypes.create_unicode_buffer("\0".join(batch) + "\0\0")
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = ctypes.cast(buf, ctypes.c_wchar_p)
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res != 0 or op.fAnyOperationsAborted:
            errors.append(f"Error {res} moving to the Recycle Bin ({len(batch)} files)")
    return errors


def trash(paths):
    """Manda a la papelera. Devuelve lista de errores."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return []
    if IS_WIN:
        return _trash_windows(paths)
    errors = []
    for p in paths:
        if not QFile.moveToTrash(p):
            errors.append(f"Could not send to the Recycle Bin: {p}")
    return errors


def delete_permanently(paths):
    """Borra sin pasar por la papelera (Shift+Del). Devuelve lista de errores."""
    import shutil
    errors = []
    for p in paths:
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            elif os.path.lexists(p):
                os.remove(p)
        except Exception as ex:
            errors.append(f"Could not delete {p}: {ex}")
    return errors


def unique_name(parent, base="New folder"):
    """«New folder», «New folder (2)»… como Windows."""
    name, n = base, 2
    while os.path.exists(os.path.join(parent, name)):
        name = f"{base} ({n})"
        n += 1
    return name


class TrashWorker(QThread):
    done = Signal(list)

    def __init__(self, paths, permanent=False):
        super().__init__()
        self.paths = paths
        self.permanent = permanent

    def run(self):
        try:
            self.done.emit(delete_permanently(self.paths) if self.permanent else trash(self.paths))
        except Exception as ex:
            self.done.emit([str(ex)])


# ----------------------------------------------------------------------------
# Renombrar / renumerar
# ----------------------------------------------------------------------------

def split_head(head):
    """'plate_v001.' -> ('plate_v001', '.')"""
    if head and head[-1] in "._- ":
        return head[:-1], head[-1]
    return head, ""


def rename_plan(e, new_base, start_frame=None, sep=None):
    """Lista de (viejo, nuevo). Para secuencias: new_base sin separador, frame ni extensión."""
    new_base = new_base.strip()
    if e.kind != "seq":
        if not valid_name(new_base):
            raise ValueError("Invalid name")
        return [(e.path, os.path.join(e.dirpath, new_base))]
    if new_base and not valid_name(new_base):
        raise ValueError("Invalid name")
    base, old_sep = split_head(e.head)
    sep = old_sep if sep is None else sep
    offset = 0 if start_frame is None else int(start_frame) - e.first
    if e.first + offset < 0:
        raise ValueError("The first frame can't be negative")
    pairs = []
    ext = e.ext_real
    for f, name in zip(e.frames, e.files):
        nf = f + offset
        num = str(nf).zfill(e.pad) if e.pad > 1 else str(nf)
        pairs.append((os.path.join(e.dirpath, name), os.path.join(e.dirpath, f"{new_base}{sep}{num}{ext}")))
    return pairs


SEQ_TOKEN_RE = re.compile(r"^(?P<head>.*?)(?P<tok>#+|@+|%0?(?P<n>\d*)d)(?P<tail>.*)$")


def seq_rename_from_text(e, text):
    """Renombra una secuencia a partir del texto editado (F2), ej. 'plate_v001.####.exr' -> 'sh010_v002.####.exr'.
    Cambiar la cantidad de # cambia el padding. Si no hay # se toma como nombre base y se conserva el separador."""
    text = text.strip()
    if not text:
        raise ValueError("Empty name")
    ext = e.ext_real
    m = SEQ_TOKEN_RE.match(text)
    if m:
        head, tok, tail = m.group("head"), m.group("tok"), m.group("tail")
        if tok.startswith("%"):
            pad = int(m.group("n") or 0)
        elif tok.startswith("@"):
            pad = 0
        else:
            pad = len(tok) if len(tok) > 1 or e.pad > 1 else 0
        if tail and tail.lower() != ext.lower():
            raise ValueError(f"The extension must stay {ext}")
    else:
        stem = text[:-len(ext)] if text.lower().endswith(ext.lower()) else text
        base, sep = split_head(e.head)
        head, pad = stem + sep, e.pad
    if any(c in INVALID_CHARS for c in head):
        raise ValueError("Invalid name")
    if not head.strip(" ._-"):
        raise ValueError("Missing name")
    return seq_plan(e, head, pad)


def seq_plan(e, new_head, new_pad=None, start_frame=None):
    pad = e.pad if new_pad is None else new_pad
    offset = 0 if start_frame is None else int(start_frame) - e.first
    if e.first + offset < 0:
        raise ValueError("The first frame can't be negative")
    ext = e.ext_real
    pairs = []
    for f, name in zip(e.frames, e.files):
        nf = f + offset
        num = str(nf).zfill(pad) if pad > 1 else str(nf)
        pairs.append((os.path.join(e.dirpath, name), os.path.join(e.dirpath, f"{new_head}{num}{ext}")))
    return pairs


def apply_renames(pairs):
    """Renombra en dos fases si hace falta (renumerado que se pisa). Falla antes de tocar nada si hay choques."""
    pairs = [(a, b) for a, b in pairs if a != b]
    if not pairs:
        return
    srcs = {norm_key(a) for a, _ in pairs}
    dsts = [norm_key(b) for _, b in pairs]
    if len(set(dsts)) != len(dsts):
        raise ValueError("Two files would end up with the same name")
    for _, b in pairs:
        if os.path.exists(b) and norm_key(b) not in srcs:
            # en Windows renombrar solo mayúsculas/minúsculas es válido
            raise FileExistsError(f"Already exists: {os.path.basename(b)}")
    if any(d in srcs for d in dsts):
        tmp = []
        for i, (a, b) in enumerate(pairs):
            t = f"{a}.__sbtmp{i}"
            os.rename(a, t)
            tmp.append((t, b))
        pairs = tmp
    done = []
    try:
        for a, b in pairs:
            os.rename(a, b)
            done.append((a, b))
    except Exception:
        for a, b in reversed(done):
            try:
                os.rename(b, a)
            except OSError:
                pass
        raise


# ----------------------------------------------------------------------------
# Copiar / mover
# ----------------------------------------------------------------------------

def plan_conflicts(sources, dest_dir):
    """Destinos que ya existen (archivos), para preguntar antes."""
    out = []
    for src in sources:
        dst = os.path.join(dest_dir, os.path.basename(src))
        if os.path.isdir(src):
            if os.path.isdir(dst):
                for root, _, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    for f in files:
                        d = os.path.normpath(os.path.join(dst, rel, f))
                        if os.path.exists(d):
                            out.append(d)
                            if len(out) > 500:
                                return out
        elif os.path.exists(dst):
            out.append(dst)
    return out


def _free(path_fn):
    """Primer nombre libre: « - Copy», « - Copy (2)», « - Copy (3)»… (como Windows)."""
    n = 1
    while True:
        cand = path_fn(" - Copy" if n == 1 else f" - Copy ({n})")
        if cand is not None:
            return cand
        n += 1


def duplicate_map(paths, entries=None):
    """Copiar y pegar en la misma carpeta = duplicar: {origen: destino} con « - Copy».
    Las secuencias se duplican enteras con el mismo nombre nuevo (siguen siendo una secuencia):
    shot.1001.exr → shot - Copy.1001.exr. Archivos: name - Copy.ext. Carpetas: name - Copy."""
    out = {}
    done = set()
    for e in entries or []:
        if e.kind != "seq" or not e.files:
            continue
        head = e.head
        sep = head[-1] if head and head[-1] in "._- " else ""
        stem = head[:-1] if sep else head

        def try_head(suffix, e=e, stem=stem, sep=sep):
            nh = stem + suffix + sep
            if any(os.path.exists(os.path.join(e.dirpath, nh + f[len(e.head):])) for f in e.files):
                return None
            return nh
        nh = _free(try_head)
        for f in e.files:
            src = os.path.join(e.dirpath, f)
            out[src] = os.path.join(e.dirpath, nh + f[len(e.head):])
            done.add(norm_key(src))
    taken = set()
    for src in paths:
        if norm_key(src) in done:
            continue
        d, name = os.path.split(src.rstrip("\\/"))
        if os.path.isdir(src):
            stem, ext = name, ""
        else:
            stem, ext = os.path.splitext(name)

        def try_name(suffix, d=d, stem=stem, ext=ext):
            c = os.path.join(d, stem + suffix + ext)
            return None if (os.path.exists(c) or norm_key(c) in taken) else c
        dst = _free(try_name)
        taken.add(norm_key(dst))
        out[src] = dst
    return out


def validate_transfer(sources, dest_dir, op):
    """Devuelve mensaje de error o None."""
    if not os.path.isdir(dest_dir):
        return f"Destination folder doesn't exist: {dest_dir}"
    for s in sources:
        if os.path.isdir(s) and is_subpath(dest_dir, s):
            return f"Can't {'copy' if op == 'copy' else 'move'} a folder into itself: {os.path.basename(s)}"
        if same_path(os.path.dirname(s), dest_dir):
            return "Source and destination are the same folder" if op == "move" else \
                "Can't copy into the same folder (pick another folder)"
    return None


class FileOpWorker(QThread):
    progress = Signal(object, object, str)   # bytes hechos, bytes totales, archivo actual
    done = Signal(int, list, bool)           # ok, errores, cancelado

    def __init__(self, op, sources, dest_dir, overwrite, rename_map=None):
        super().__init__()
        self.op, self.sources, self.dest, self.overwrite = op, list(sources), dest_dir, overwrite
        self.rename_map = rename_map or {}          # duplicar en la misma carpeta: origen → destino
        self.cancelled = False
        self.ok = 0
        self.errors = []
        self.total = 0
        self.done_bytes = 0

    def _same_dev(self, src):
        try:
            return os.stat(src).st_dev == os.stat(self.dest).st_dev
        except OSError:
            return False

    def _plan(self):
        tasks = []  # (tipo, src, dst, size)
        for src in self.sources:
            dst = self.rename_map.get(src) or os.path.join(self.dest, os.path.basename(src))
            if same_path(src, dst) or not os.path.exists(src):
                continue
            fast_move = self.op == "move" and self._same_dev(src)
            if os.path.isdir(src):
                if fast_move and not os.path.exists(dst):
                    tasks.append(("rename", src, dst, 0))
                    continue
                for root, dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    droot = os.path.normpath(os.path.join(dst, rel))
                    tasks.append(("mkdir", root, droot, 0))
                    for f in files:
                        s, d = os.path.join(root, f), os.path.join(droot, f)
                        if os.path.exists(d) and not self.overwrite:
                            continue
                        size = os.path.getsize(s)
                        tasks.append(("rename" if fast_move else "copy", s, d, size))
                if self.op == "move":
                    tasks.append(("prune", src, "", 0))
            else:
                if os.path.exists(dst) and not self.overwrite:
                    continue
                size = os.path.getsize(src)
                tasks.append(("rename" if fast_move else "copy", src, dst, size))
        return tasks

    def _copy_file(self, s, d):
        with open(s, "rb") as fi, open(d, "wb") as fo:
            while True:
                if self.cancelled:
                    raise InterruptedError()
                buf = fi.read(CHUNK)
                if not buf:
                    break
                fo.write(buf)
                self.done_bytes += len(buf)
                self.progress.emit(self.done_bytes, self.total, os.path.basename(s))
        shutil.copystat(s, d)

    def run(self):
        try:
            tasks = self._plan()
        except Exception as ex:
            self.done.emit(0, [str(ex)], False)
            return
        self.total = sum(t[3] for t in tasks if t[0] == "copy") or 1
        for kind, s, d, size in tasks:
            if self.cancelled:
                break
            try:
                if kind == "mkdir":
                    os.makedirs(d, exist_ok=True)
                elif kind == "rename":
                    try:
                        if self.overwrite and os.path.isfile(d):
                            os.remove(d)
                        os.replace(s, d)
                    except OSError:
                        if os.path.isdir(s):
                            shutil.copytree(s, d, dirs_exist_ok=True)
                            shutil.rmtree(s)
                        else:
                            self._copy_file(s, d)
                            os.remove(s)
                    self.ok += 1
                    self.progress.emit(self.done_bytes, self.total, os.path.basename(s))
                elif kind == "copy":
                    self._copy_file(s, d)
                    if self.op == "move":
                        os.remove(s)
                    self.ok += 1
                elif kind == "prune":
                    for root, dirs, files in os.walk(s, topdown=False):
                        if not os.listdir(root):
                            os.rmdir(root)
            except InterruptedError:
                try:
                    if os.path.isfile(d):
                        os.remove(d)   # archivo a medio copiar
                except OSError:
                    pass
                break
            except Exception as ex:
                self.errors.append(f"{os.path.basename(s)}: {ex}")
        self.done.emit(self.ok, self.errors, self.cancelled)
