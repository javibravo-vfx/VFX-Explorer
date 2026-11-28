# -*- coding: utf-8 -*-
"""Thumbnails e info de medios: OpenImageIO (EXR, HDR, TIFF float, DPX, PSD, TX…), Qt (JPG/PNG) y ffmpeg (video)."""

import os
import json
import time
import hashlib
import threading
import subprocess
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QImageReader

try:
    import OpenImageIO as oiio
    oiio.attribute("threads", 2)
    HAS_OIIO = True
except Exception:  # pragma: no cover
    oiio = None
    HAS_OIIO = False

from .core import IS_WIN, VIDEO_EXTS, find_tool, net_root

try:
    import pypdfium2 as _pdfium
    HAS_PDF = True
except Exception:          # pragma: no cover
    _pdfium = None
    HAS_PDF = False
_PDF_LOCK = threading.Lock()     # pdfium no es thread-safe



_WARM = {}            # unidad de red -> último momento en que se la despertó


def _warm(path, whole=False, root=None):
    """OpenImageIO no suelta el GIL de Python mientras espera al disco: con el NAS con los discos dormidos, un
    hilo leyendo un EXR congelaba toda la app hasta que arrancaban. Antes se lee un pedacito con Python (que sí lo
    suelta): los discos arrancan acá, sin trabar nada. Si el NAS se usó hace menos de 30 s, los discos ya están
    andando y no se lee nada de más (reproducir una secuencia desde el NAS rinde igual que antes)."""
    root = root or net_root(path)
    if not root:
        return
    now = time.monotonic()
    if now - _WARM.get(root, -1e9) < 30:
        return
    try:
        with open(path, "rb", buffering=0) as f:
            f.read(64 << 10)
        _WARM[root] = time.monotonic()
    except OSError:
        pass


def warm_disk(physical, logical):
    """Una unidad mapeada que se lee directo del disco físico (SMB local, p. ej. T: → W:): ese disco también
    puede estar dormido (HDD) y OIIO esperaría con el GIL tomado. Se despierta igual que el NAS."""
    from .storage import queue_key
    _warm(physical, root="phys:" + (queue_key(logical) or physical[:2].casefold()))


def oiio_open(path, whole=False):
    from . import media_process
    if not media_process._child:
        _warm(path, whole)
    return oiio.ImageInput.open(path)

def pdf_page_count(path):
    if not HAS_PDF:
        return 0
    with _PDF_LOCK:
        try:
            d = _pdfium.PdfDocument(path)
            n = len(d)
            d.close()
            return n
        except Exception:
            return 0


def pdf_render(path, page=0, width=400):
    """Página de un PDF como QImage del ancho pedido (fondo blanco)."""
    if not HAS_PDF:
        return QImage()
    with _PDF_LOCK:
        try:
            d = _pdfium.PdfDocument(path)
            if page >= len(d):
                d.close()
                return QImage()
            pg = d[page]
            pw, ph = pg.get_size()
            bm = pg.render(scale=max(0.05, width / max(1.0, pw)), rev_byteorder=True)
            a = np.ascontiguousarray(bm.to_numpy())
            pg.close()
            d.close()
        except Exception:
            return QImage()
    h, w = a.shape[:2]
    fmt = QImage.Format_RGBA8888 if a.shape[2] == 4 else QImage.Format_RGB888
    return QImage(a.data, w, h, a.strides[0], fmt).copy()

NO_WINDOW = 0x08000000 if IS_WIN else 0
THUMB_RES = 320

COLORSPACES = [
    ("ACEScg", "acescg"),
    ("ACES2065-1 (AP0)", "aces"),
    ("Linear Rec.709 / sRGB", "lin709"),
    ("Already sRGB (no conversion)", "srgb"),
]
M_ACESCG_TO_709 = np.array([
    [1.70505, -0.62179, -0.08326],
    [-0.13026, 1.14080, -0.01055],
    [-0.02400, -0.12897, 1.15297]], np.float32)
M_ACES_TO_709 = np.array([
    [2.52169, -1.13413, -0.38756],
    [-0.27648, 1.37272, -0.09624],
    [-0.01538, -0.15298, 1.16835]], np.float32)

QT_FAST = set()
OIIO_EXTS = set()


def init_formats():
    qt = {bytes(f).decode().lower() for f in QImageReader.supportedImageFormats()}
    QT_FAST.update({"jpg", "jpeg", "png", "webp", "bmp", "gif"} & qt)
    if HAS_OIIO:
        for part in oiio.get_string_attribute("extension_list").split(";"):
            if ":" not in part:
                continue
            fmt, exts = part.split(":", 1)
            if fmt in ("null", "term", "zfile", "ffmpeg", "fits"):
                continue
            OIIO_EXTS.update(e.strip().lower() for e in exts.split(",") if e.strip())
    else:
        QT_FAST.update({"tif", "tiff", "tga"} & qt)


def can_decode(ext):
    e = ext.lstrip(".").lower()
    return e in QT_FAST or e in OIIO_EXTS


# ----------------------------------------------------------------------------
# Conversión de color
# ----------------------------------------------------------------------------

def detect_cs_from_chroma(ch):
    if ch is None:
        return None
    try:
        rx, ry = float(ch[0]), float(ch[1])
    except Exception:
        return None
    if abs(rx - 0.7347) < 0.01 and abs(ry - 0.2653) < 0.01:
        return "aces"
    if abs(rx - 0.713) < 0.01 and abs(ry - 0.293) < 0.01:
        return "acescg"
    if abs(rx - 0.64) < 0.01 and abs(ry - 0.33) < 0.01:
        return "lin709"
    return None


def _checker(h, w, cell=8):
    y, x = np.mgrid[0:h, 0:w]
    return (0.16 + 0.08 * (((x // cell + y // cell) % 2).astype(np.float32)))[..., None]


def to_qimage(rgb, alpha, cs, premult, maxdim):
    rgb = np.nan_to_num(rgb.astype(np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    if cs == "acescg":
        rgb = rgb @ M_ACESCG_TO_709.T
    elif cs == "aces":
        rgb = rgb @ M_ACES_TO_709.T
    rgb = np.clip(rgb, 0.0, 1.0)
    if cs != "srgb":
        rgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    if alpha is not None:
        a = np.clip(np.nan_to_num(alpha.astype(np.float32)), 0.0, 1.0)[..., None]
        if float(a.min()) < 0.999:
            bg = _checker(rgb.shape[0], rgb.shape[1])
            rgb = rgb + bg * (1 - a) if premult else rgb * a + bg * (1 - a)
            rgb = np.clip(rgb, 0, 1)
    arr = np.ascontiguousarray((rgb * 255.0 + 0.5).astype(np.uint8))
    h, w = arr.shape[:2]
    img = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy()
    if w > maxdim or h > maxdim:
        img = img.scaled(maxdim, maxdim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img


def pick_channels(names):
    """Índices de los canales a mostrar: RGB(A) o la capa beauty/combined; si no, Y o el primero."""
    lower = [n.lower() for n in names]

    def find(seq):
        return [lower.index(c) for c in seq if c in lower]

    rgb = find(("r", "g", "b"))
    if len(rgb) == 3:
        a = find(("a",))
        return rgb + a
    layers = {}
    for i, n in enumerate(names):
        if "." in n:
            pre, suf = n.rsplit(".", 1)
            layers.setdefault(pre, {})[suf.lower()] = i
    cands = [p for p, d in layers.items() if all(c in d for c in ("r", "g", "b"))]
    if cands:
        prio = ("combined", "beauty", "rgba", "rgb", "color", "main")
        cands.sort(key=lambda p: next((i for i, k in enumerate(prio) if p.lower().endswith(k)), 99))
        d = layers[cands[0]]
        return [d["r"], d["g"], d["b"]] + ([d["a"]] if "a" in d else [])
    y = find(("y",))
    return y or [0]


# ----------------------------------------------------------------------------
# Lectores
# ----------------------------------------------------------------------------

def _is_float(typedesc):
    return str(typedesc) in ("float", "half", "double")


DATA_HINTS = ("depth", "z", "normal", "position", "pos", "pworld", "nworld", "uv", "motion", "vector", "velocity",
              "crypto", "id", "mask", "ao", "occlusion", "fresnel", "facing", "pref", "zdepth", "n", "p")


def exr_layers(path):
    """Capas de un EXR para el selector del viewer: [(etiqueta, [canales] | None, es_dato)]."""
    if not HAS_OIIO:
        return []
    from .media_process import isolated, call, decode_path
    path = decode_path(path)
    if isolated(path):
        return call(__name__, "exr_layers", (path,))
    inp = oiio_open(path)
    if not inp:
        return []
    try:
        names = list(inp.spec().channelnames)
    finally:
        inp.close()
    if len(names) <= 1:
        return []
    groups = OrderedDict()
    for n in names:
        pre = n.rsplit(".", 1)[0] if "." in n else ""
        groups.setdefault(pre, []).append(n)
    out = [("Beauty / RGB", None, False)]
    order = {"r": 0, "g": 1, "b": 2, "a": 3, "x": 0, "y": 1, "z": 2, "w": 3, "u": 0, "v": 1}
    alpha = None
    for pre, chans in groups.items():
        suf = {c.rsplit(".", 1)[-1].lower(): c for c in chans}
        if "a" in suf and alpha is None:
            alpha = suf["a"]
        if all(k in suf for k in ("r", "g", "b")):
            sel = [suf["r"], suf["g"], suf["b"]]
        else:
            sel = sorted(chans, key=lambda c: order.get(c.rsplit(".", 1)[-1].lower(), 9))[:3]
        low = pre.lower().split(".")[-1] if pre else ""
        is_data = (len(sel) == 1 and "a" not in suf) or any(low == h or low.startswith(h) for h in DATA_HINTS) \
            or all(c.rsplit(".", 1)[-1].lower() in "xyzuvw" for c in sel)
        label = pre or "(no layer)"
        if pre == "" and sel[:3] == [suf.get("r"), suf.get("g"), suf.get("b")]:
            continue        # ya está como Beauty
        tag = "".join(c.rsplit(".", 1)[-1] for c in sel) if all(len(c.rsplit(".", 1)[-1]) == 1 for c in sel) else ""
        out.append((f"{label}  [{tag}]" if tag else label, sel, is_data))
        if pre == "":
            # canales sueltos sin capa (Z, Y…) además del grupo
            for c in chans:
                if c.lower() not in ("r", "g", "b", "a") and len(chans) > 1:
                    out.append((c, [c], True))
    if alpha:
        out.append(("Alpha", [alpha], True))
    return out


def oiio_thumb(path, settings, maxdim=THUMB_RES):
    from .media_process import isolated, call, decode_path
    path = decode_path(path)
    if isolated(path):
        return call(__name__, "oiio_thumb", (path, settings, maxdim), preview=maxdim <= THUMB_RES)
    r = _oiio_read(path, settings, maxdim)
    if r is None:
        return QImage()
    arr, chroma, is_float, cs_attr, wanted = r
    return _oiio_finish(path, settings, maxdim, arr, chroma, is_float, cs_attr, wanted)


def _oiio_read(path, settings, maxdim):
    """Lee los píxeles en float, salteando filas y columnas (y con el mip más chico que alcance) hasta ~2× maxdim.
    Devuelve (arr, chroma, is_float, cs_attr, wanted) o None."""
    inp = oiio_open(path, whole=True)
    if not inp:
        return None
    try:
        spec = inp.spec()
        names = list(spec.channelnames)
        wanted = settings.get("channels")
        idx = [names.index(c) for c in wanted if c in names] if wanted else []
        if not idx:
            idx = pick_channels(names)
            wanted = None
        chroma = spec.getattribute("chromaticities")
        is_float = _is_float(spec.format)
        cs_attr = (spec.get_string_attribute("oiio:ColorSpace") or "").lower()
        # mip más chico que siga siendo suficiente (TX, EXR tileados)
        mip = 0
        m = 1
        while inp.seek_subimage(0, m):
            s2 = inp.spec()
            if max(s2.width, s2.height) < maxdim * 1.5:
                break
            mip = m
            m += 1
        inp.seek_subimage(0, mip)
        spec = inp.spec()
        W, H = spec.width, spec.height
        cb, ce = min(idx), max(idx) + 1
        sub = [i - cb for i in idx]
        step = max(1, max(W, H) // (maxdim * 2))
        if spec.tile_width == 0 and W * H > 8_000_000:
            rows = []
            chunk = max(64, step * 16)
            for y0 in range(spec.y, spec.y + H, chunk):
                y1 = min(y0 + chunk, spec.y + H)
                a = inp.read_scanlines(0, mip, y0, y1, 0, cb, ce, "float")
                if a is None:
                    break
                a = np.asarray(a)
                if a.ndim == 2:
                    a = a[..., None]
                start = (-(y0 - spec.y)) % step
                rows.append(a[start::step, ::step][..., sub])
            if not rows:
                return None
            arr = np.concatenate(rows, 0)
        else:
            a = inp.read_image(0, mip, cb, ce, "float")
            if a is None:
                return None
            a = np.asarray(a)
            if a.ndim == 2:
                a = a[..., None]
            arr = a[::step, ::step][..., sub]
    finally:
        inp.close()
    return arr, chroma, is_float, cs_attr, wanted


def _oiio_cs(path, settings, chroma, is_float, cs_attr):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".exr", ".sxr", ".mxr"):
        return (detect_cs_from_chroma(chroma) if settings["chroma"] else None) or settings["cs"]
    if is_float:
        return "srgb" if "srgb" in cs_attr else "lin709"
    return "srgb"


def hdr_linear(path, settings, maxdim):
    """Para el visor de HDRIs: la imagen en float lineal Rec.709 (sin recortar los altos), para aplicarle
    exposición y gamma al vuelo. Devuelve (rgb HxWx3 float32, alpha o None) o None."""
    from .media_process import isolated, call, decode_path
    path = decode_path(path)
    if isolated(path):
        return call(__name__, "hdr_linear", (path, settings, maxdim))
    r = _oiio_read(path, settings, maxdim)
    if r is None:
        return None
    arr, chroma, is_float, cs_attr, wanted = r
    arr = np.nan_to_num(arr.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if wanted and settings.get("data"):
        lo, hi = float(np.percentile(arr, 1)), float(np.percentile(arr, 99))
        if lo < -0.001 or hi > 1.001:
            arr = (arr - lo) / max(1e-6, hi - lo)
        cs = "data"
    else:
        cs = _oiio_cs(path, settings, chroma, is_float, cs_attr)
    alpha = None
    if arr.shape[2] >= 4:
        alpha = arr[..., 3]
        arr = arr[..., :3]
    if arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.shape[2] == 2:
        arr = np.dstack([arr[..., 0], arr[..., 1], np.zeros_like(arr[..., 0])])
    if cs == "acescg":
        arr = arr @ M_ACESCG_TO_709.T
    elif cs == "aces":
        arr = arr @ M_ACES_TO_709.T
    elif cs in ("srgb", "data"):              # ya codificada: a lineal, así la exposición se comporta igual
        a = np.clip(arr, 0.0, None)
        arr = np.where(a <= 0.04045, a / 12.92, np.power((a + 0.055) / 1.055, 2.4))
    h, w = arr.shape[:2]
    if max(w, h) > maxdim:                     # al tamaño pedido (se leyó hasta ~2×): promedio de bloques
        k = int(np.ceil(max(w, h) / maxdim))
        H2, W2 = h // k * k, w // k * k
        arr = arr[:H2, :W2].reshape(H2 // k, k, W2 // k, k, 3).mean(axis=(1, 3))
        if alpha is not None:
            alpha = alpha[:H2, :W2].reshape(H2 // k, k, W2 // k, k).mean(axis=(1, 3))
    return np.ascontiguousarray(arr, dtype=np.float32), alpha


def hdr_display(rgb, exposure=0.0, gamma=1.0, alpha=None):
    """float lineal → QImage sRGB con exposición (stops) y gamma (como en el visor)."""
    x = rgb * np.float32(2.0 ** exposure) if exposure else rgb
    x = np.clip(x, 0.0, 1.0)
    x = np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4, dtype=np.float32) - 0.055)
    if abs(gamma - 1.0) > 1e-3:
        x = np.power(x, 1.0 / max(0.05, gamma), dtype=np.float32)
    if alpha is not None:
        a = np.clip(alpha, 0.0, 1.0)[..., None]
        if float(a.min()) < 0.999:
            bg = _checker(x.shape[0], x.shape[1])
            x = np.clip(x + bg * (1 - a), 0, 1)
    arr = np.ascontiguousarray((x * 255.0 + 0.5).astype(np.uint8))
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy()


def _oiio_finish(path, settings, maxdim, arr, chroma, is_float, cs_attr, wanted):
    if wanted and settings.get("data"):
        # capa de datos (depth, normales, alpha…): sin conversión de color, normalizada si se sale de 0-1
        arr = np.nan_to_num(arr.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        lo, hi = float(np.percentile(arr, 1)), float(np.percentile(arr, 99))
        if lo < -0.001 or hi > 1.001:
            arr = (arr - lo) / max(1e-6, hi - lo)
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.shape[2] == 2:
            arr = np.dstack([arr[..., 0], arr[..., 1], np.zeros_like(arr[..., 0])])
        return to_qimage(arr[..., :3], None, "srgb", premult=False, maxdim=maxdim)
    cs = _oiio_cs(path, settings, chroma, is_float, cs_attr)
    alpha = None
    if arr.shape[2] >= 4:
        alpha = arr[..., 3]
        arr = arr[..., :3]
    if arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
        if cs in ("acescg", "aces"):
            cs = "lin709"
    elif arr.shape[2] == 2:
        arr = np.dstack([arr[..., 0], arr[..., 1], np.zeros_like(arr[..., 0])])
    return to_qimage(arr, alpha, cs, premult=is_float, maxdim=maxdim)


def qt_thumb(path, maxdim=THUMB_RES):
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and (sz.width() > maxdim or sz.height() > maxdim):
        r.setScaledSize(sz.scaled(maxdim, maxdim, Qt.KeepAspectRatio))
    img = r.read()
    if img.isNull():
        return QImage()
    if img.width() > maxdim or img.height() > maxdim:
        img = img.scaled(maxdim, maxdim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if img.hasAlphaChannel():
        bg = QImage(img.size(), QImage.Format_RGB32)
        p = QPainter(bg)
        cell = 8
        for y in range(0, bg.height(), cell):
            for x in range(0, bg.width(), cell):
                p.fillRect(x, y, cell, cell, QColor(66, 66, 66) if (x // cell + y // cell) % 2 else QColor(41, 41, 41))
        p.drawImage(0, 0, img)
        p.end()
        img = bg
    return img


_DUR = {}
_DUR_LOCK = threading.Lock()


def video_duration(path, ffprobe):
    with _DUR_LOCK:
        if path in _DUR:
            return _DUR[path]
    dur = 0.0
    if ffprobe:
        try:
            r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                                "default=nw=1:nk=1", path], capture_output=True, timeout=15, creationflags=NO_WINDOW)
            dur = float(r.stdout.decode().strip() or 0)
        except Exception:
            dur = 0.0
    with _DUR_LOCK:
        _DUR[path] = dur
    return dur


def video_thumb(path, ffmpeg, maxdim=THUMB_RES, at=None):
    if not ffmpeg:
        return QImage()
    vf = f"scale=w={maxdim}:h={maxdim}:force_original_aspect_ratio=decrease"
    for ss in ((f"{at:.3f}", "0") if at is not None else ("1", "0")):
        cmd = [ffmpeg, "-v", "error", "-ss", ss, "-i", path, "-frames:v", "1", "-vf", vf,
               "-f", "image2pipe", "-vcodec", "png", "-"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=25, creationflags=NO_WINDOW)
        except Exception:
            return QImage()
        if r.stdout:
            img = QImage.fromData(r.stdout, "PNG")
            if not img.isNull():
                return img
    return QImage()


# ----------------------------------------------------------------------------
# Previews "sidecar" para modelos y carpetas
# ----------------------------------------------------------------------------

PREVIEW_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".exr", ".tga")
PREVIEW_DIRS = ("thumbs", ".thumbs", "_thumbs", "previews", "preview", "_preview", "thumbnails")
DIR_PREVIEW_STEMS = ("thumbnail", "thumb", "preview", "folder", "cover", "_preview", "_thumb")


class DirIndex:
    """Listado de nombres por carpeta, cacheado unos segundos (compartido entre threads)."""

    def __init__(self, ttl=20.0, limit=4000):
        self.ttl, self.limit = ttl, limit
        self._c = {}
        self._lock = threading.Lock()

    def names(self, d):
        now = time.time()
        with self._lock:
            hit = self._c.get(d)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        out = {}
        try:
            with os.scandir(d) as it:
                for i, de in enumerate(it):
                    if i >= self.limit:
                        break
                    out[de.name.lower()] = de.name
        except OSError:
            return out
        with self._lock:
            if len(self._c) > 2000:
                self._c.clear()
            self._c[d] = (now, out)
        return out

    def clear(self):
        with self._lock:
            self._c.clear()


def find_sidecar(e, index):
    if e.kind == "dir":
        names = index.names(e.path)
        for stem in DIR_PREVIEW_STEMS + (e.name.lower(),):
            for ext in PREVIEW_EXTS:
                n = names.get(stem + ext)
                if n:
                    return os.path.join(e.path, n)
        return None
    stem = os.path.splitext(e.name)[0].lower()
    stems = (stem, stem + "_thumb", stem + "_preview", stem + ".thumb", stem + ".preview", stem + "_thumbnail")
    dirs = [e.dirpath]
    names = index.names(e.dirpath)
    dirs += [os.path.join(e.dirpath, names[d]) for d in PREVIEW_DIRS if d in names]
    for d in dirs:
        nm = names if d == e.dirpath else index.names(d)
        for s in stems:
            for ext in PREVIEW_EXTS:
                n = nm.get(s + ext)
                if n:
                    return os.path.join(d, n)
    return None


# ----------------------------------------------------------------------------
# Carga de thumbnails (en threads) con caché en disco
# ----------------------------------------------------------------------------

def _thumb_cache_alias(e, settings, cache_dir):
    # Snapshot identity: the middle frame / sidecar may not have its own stat in Entry.
    sig = repr((e.thumb_source(), e.kind, e.mtime, e.size, e.thumb_mtime, e.thumb_size, settings['cs'], settings['chroma'], settings['sidecar'], 'nas-v1'))
    return os.path.join(cache_dir, hashlib.sha1(sig.encode('utf-8', 'replace')).hexdigest() + '.jpg')


def cached_thumbnail(e, settings, cache_dir):
    if e.cat in ('dir', 'model') and not settings['sidecar']:
        return QImage()
    img = QImage(_thumb_cache_alias(e, settings, cache_dir))
    if not img.isNull():
        return img
    # Reuse existing v2 cache for ordinary files, including upgrades from 0.61.3.
    if (e.kind == 'file' and e.cat != 'model' and e.mtime) or (e.kind == 'seq' and e.thumb_mtime):
        mt, size = (e.thumb_mtime, e.thumb_size) if e.kind == 'seq' else (e.mtime, e.size)
        sig = f"{e.thumb_source()}|{mt}|{size}|{settings['cs']}|{settings['chroma']}|v2"
        return QImage(os.path.join(cache_dir, hashlib.sha1(sig.encode('utf-8', 'replace')).hexdigest() + '.jpg'))
    return QImage()


def _save_alias(img, e, settings, cache_dir):
    if net_root(e.path) and not img.isNull() and (e.cat in ("dir", "model") or not (e.mtime if e.kind == "file" else e.thumb_mtime)):
        # atomic publish: the cache-only pool must never see a partially written JPG
        ck = _thumb_cache_alias(e, settings, cache_dir)
        tmp = ck + '.' + str(threading.get_ident()) + '.tmp'
        try:
            if img.convertToFormat(QImage.Format_RGB32).save(tmp, 'JPG', 88):
                os.replace(tmp, ck)
        except OSError:
            pass
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


def load_thumbnail(e, settings, cache_dir, index):
    if net_root(e.path):
        hit = cached_thumbnail(e, settings, cache_dir)
        if not hit.isNull():
            return hit
    src, ext, cat = e.thumb_source(), e.ext, e.cat
    if cat in ("dir", "model"):
        if not settings["sidecar"]:
            return QImage()
        src = find_sidecar(e, index)
        if not src:
            return QImage()
        ext, cat = os.path.splitext(src)[1].lower(), "image"
    try:
        st = os.stat(src)
    except OSError:
        return QImage()
    sig = f"{src}|{st.st_mtime}|{st.st_size}|{settings['cs']}|{settings['chroma']}|v2"
    ck = os.path.join(cache_dir, hashlib.sha1(sig.encode("utf-8", "replace")).hexdigest() + ".jpg")
    if os.path.isfile(ck):
        img = QImage(ck)
        if not img.isNull():
            _save_alias(img, e, settings, cache_dir)
            return img
    e2 = ext.lstrip(".")
    if cat == "video" or ext in VIDEO_EXTS:
        img = video_thumb(src, settings["ffmpeg"])
    elif ext == ".pdf":
        img = pdf_render(src, 0, 480)
    elif e2 in QT_FAST:
        img = qt_thumb(src)
    elif e2 in OIIO_EXTS and HAS_OIIO:
        img = oiio_thumb(src, settings)
    else:
        img = QImage()
    if not img.isNull():
        try:
            img.convertToFormat(QImage.Format_RGB32).save(ck, "JPG", 88)
        except Exception:
            pass
    _save_alias(img, e, settings, cache_dir)
    return img


class Signals(QObject):
    done = Signal(str, QImage, int)
    info = Signal(int, str)
    cache_miss = Signal(object)


class ThumbTask(QRunnable):
    def __init__(self, key, entry, settings, cache_dir, index, signals, cache_only=False, epoch=0):
        super().__init__()
        self.key, self.e = key, entry
        self.cache_only, self.epoch = cache_only, epoch
        self.settings, self.cache_dir, self.index, self.signals = settings, cache_dir, index, signals

    def run(self):
        try:
            img = (cached_thumbnail(self.e, self.settings, self.cache_dir) if self.cache_only else
                   load_thumbnail(self.e, self.settings, self.cache_dir, self.index))
        except Exception:
            img = QImage()
        if self.cache_only and img.isNull():
            self.signals.cache_miss.emit((self.key, self.e, self.settings, self.epoch))
        else:
            self.signals.done.emit(self.key, img, self.epoch)


class VideoScrubTask(QRunnable):
    """Frame k de steps de un video (para el scrub de la grilla)."""

    def __init__(self, key, path, k, steps, settings, cache_dir, signals, epoch=0, stamp=None):
        super().__init__()
        self.stamp = stamp
        self.key, self.path, self.k, self.steps = key, path, k, steps
        self.epoch = epoch
        self.settings, self.cache_dir, self.signals = settings, cache_dir, signals

    def run(self):
        img = QImage()
        try:
            if self.stamp:
                mt, size = self.stamp
            else:
                st = os.stat(self.path)
                mt, size = st.st_mtime, st.st_size
            sig = f"{self.path}|{mt}|{size}|scrub{self.k}/{self.steps}|v1"
            ck = os.path.join(self.cache_dir, hashlib.sha1(sig.encode("utf-8", "replace")).hexdigest() + ".jpg")
            if os.path.isfile(ck):
                img = QImage(ck)
            if img.isNull():
                ffprobe = find_tool(self.settings.get("ffmpeg_cfg", ""), "ffprobe") if not self.settings.get("ffprobe") \
                    else self.settings["ffprobe"]
                dur = video_duration(self.path, ffprobe)
                if dur > 0:
                    t = (self.k + 0.5) / self.steps * dur
                    img = video_thumb(self.path, self.settings["ffmpeg"], THUMB_RES, at=t)
                    if not img.isNull():
                        img.convertToFormat(QImage.Format_RGB32).save(ck, "JPG", 85)
        except Exception:
            img = QImage()
        self.signals.done.emit(self.key, img, self.epoch)


class ThumbManager(QObject):
    ready = Signal(str)

    def __init__(self, cfg, data_dir):
        super().__init__()
        self.cfg = cfg
        self.pool = QThreadPool()
        self.cache_pool = QThreadPool(self)
        self.cache_pool.setMaxThreadCount(4)
        from .storage import RootPools
        self.storage_pools = RootPools(self.pool, self, 3)
        self._epoch = 0
        self.retry_after = {}
        self.cache = OrderedDict()
        self.scaled = {}
        self.pending = set()
        self.failed = set()
        self.index = DirIndex()
        self.signals = Signals()
        self.signals.done.connect(self._done)
        self.signals.cache_miss.connect(self._cache_miss)
        from .storage_cache import cache_home
        self.cache_dir = os.path.join(cache_home(data_dir) or data_dir, "thumbs")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.reload_settings()

    def reload_settings(self):
        self.settings = {
            "cs": self.cfg["colorspace"],
            "chroma": bool(self.cfg["use_chromaticities"]),
            "ffmpeg": find_tool(self.cfg["ffmpeg"], "ffmpeg"),
            "sidecar": bool(self.cfg["sidecar_previews"]),
            "ffprobe": find_tool(self.cfg["ffmpeg"], "ffprobe"),
        }
        self.pool.setMaxThreadCount(max(1, int(self.cfg["threads"])))

    def can_thumb(self, e):
        c = e.cat
        if c in ("dir", "model"):
            return self.settings["sidecar"]
        if c == "other":
            return e.ext == ".pdf" and HAS_PDF
        if c == "video":
            return bool(self.settings["ffmpeg"])
        return can_decode(e.ext)

    @staticmethod
    def key_for(e):
        return e.thumb_source()

    def invalidate(self, keys):
        """Archivos que cambiaron en disco (pisados): el thumbnail en memoria se descarta y se vuelve a hacer
        (el de disco ya tiene la fecha y el tamaño en su clave)."""
        keys = set(keys)
        if not keys:
            return
        for k in keys:
            self.cache.pop(k, None)
            self.failed.discard(k)
            self.retry_after.pop(k, None)
        for sk in [sk for sk in self.scaled if sk[0] in keys]:
            self.scaled.pop(sk, None)

    def get(self, e, w=None, h=None):
        if not self.can_thumb(e):
            return None
        key = self.key_for(e)
        pm = self.cache.get(key)
        if pm is None:
            if key not in self.pending and key not in self.failed and time.monotonic() >= self.retry_after.get(key, 0):
                self.pending.add(key)
                remote = bool(net_root(e.path))
                pool = self.cache_pool if remote else self.pool
                pool.start(ThumbTask(key, e, dict(self.settings), self.cache_dir, self.index, self.signals, remote, self._epoch))
            return None
        self.cache.move_to_end(key)
        if w and h:
            sk = (key, w, h)
            s = self.scaled.get(sk)
            if s is None:
                s = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if len(self.scaled) > 1500:
                    self.scaled.clear()
                self.scaled[sk] = s
            return s
        return pm

    SCRUB_STEPS_SEQ = 48
    SCRUB_STEPS_VIDEO = 24

    def get_scrub(self, e, frac, w, h):
        """Thumbnail del frame que corresponde a la posición del mouse. Devuelve (pixmap|None, etiqueta)."""
        frac = min(1.0, max(0.0, frac))
        if e.kind == "seq" and len(e.files) > 1:
            n = len(e.files)
            steps = min(n, self.SCRUB_STEPS_SEQ)
            idx = int(round(round(frac * (steps - 1)) * (n - 1) / max(1, steps - 1)))
            from .core import Entry
            fe = Entry(kind="file", dirpath=e.dirpath, name=e.files[idx], path=os.path.join(e.dirpath, e.files[idx]),
                       ext=e.ext)
            return self.get(fe, w, h), str(e.frames[idx])
        if e.cat == "video" and self.settings["ffmpeg"]:
            steps = self.SCRUB_STEPS_VIDEO
            k = int(round(frac * (steps - 1)))
            key = f"{e.path}#scrub{k}"
            pm = self.cache.get(key)
            if pm is None:
                if key not in self.pending and key not in self.failed and time.monotonic() >= self.retry_after.get(key, 0):
                    self.pending.add(key)
                    pool = self.storage_pools.for_path(e.path)
                    pool.start(VideoScrubTask(key, e.path, k, steps, dict(self.settings), self.cache_dir,
                                                   self.signals, self._epoch, (e.mtime, e.size) if net_root(e.path) and e.mtime else None))
                return None, f"{int(frac * 100)}%"
            sk = (key, w, h)
            s = self.scaled.get(sk)
            if s is None:
                s = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.scaled[sk] = s
            return s, f"{int(frac * 100)}%"
        return None, ""

    def has_failed(self, e):
        return self.key_for(e) in self.failed

    def _cache_miss(self, payload):
        key, e, settings, epoch = payload
        if epoch == self._epoch and key in self.pending:
            self.storage_pools.for_path(e.path).start(ThumbTask(key, e, settings, self.cache_dir, self.index, self.signals, epoch=epoch))

    def _done(self, key, img, epoch):
        if epoch != self._epoch:
            return
        self.pending.discard(key)
        if img.isNull():
            if net_root(key):
                self.retry_after[key] = time.monotonic() + 15
            else:
                self.failed.add(key)
        else:
            self.retry_after.pop(key, None)
            self.cache[key] = QPixmap.fromImage(img)
            while len(self.cache) > 2500:
                self.cache.popitem(last=False)
        self.ready.emit(key)

    def cancel_pending(self):
        self._epoch += 1
        self.storage_pools.clear()
        self.cache_pool.clear()
        self.pending.clear()

    def forget(self, keys=None):
        """Olvida thumbs (todos o algunos) para que se regeneren."""
        if keys is None:
            self.cancel_pending()
            self.cache.clear()
            self.scaled.clear()
            self.failed.clear()
            self.retry_after.clear()
            self.index.clear()
            return
        for k in keys:
            self.cache.pop(k, None)
            self.failed.discard(k)
        self.scaled.clear()

    def clear_disk(self):
        self.forget()
        for n in os.listdir(self.cache_dir):
            try:
                os.remove(os.path.join(self.cache_dir, n))
            except OSError:
                pass

    def disk_usage(self):
        total = 0
        try:
            for de in os.scandir(self.cache_dir):
                total += de.stat().st_size
        except OSError:
            pass
        return total


# ----------------------------------------------------------------------------
# Info detallada
# ----------------------------------------------------------------------------

def oiio_info(path):
    from .media_process import isolated, call, decode_path
    path = decode_path(path)
    if isolated(path):
        return call(__name__, "oiio_info", (path,), preview=True)
    inp = oiio_open(path)
    if not inp:
        return [("Error", oiio.geterror() or "could not open")]
    rows = []
    try:
        spec = inp.spec()
        W, H = spec.width, spec.height
        fw, fh = spec.full_width or W, spec.full_height or H
        rows.append(("Resolution", f"{fw} × {fh}"))
        if (fw, fh) != (W, H) or spec.x != spec.full_x or spec.y != spec.full_y:
            rows.append(("Data window", f"{W} × {H}  ({spec.x},{spec.y})"))
        comp = spec.get_string_attribute("compression")
        if comp:
            rows.append(("Compression", comp.upper()))
        fmts = [str(t) for t in spec.channelformats] if len(spec.channelformats) else [str(spec.format)]
        rows.append(("Type", ", ".join(sorted(set(fmts)))))
        names = list(spec.channelnames)
        layers = OrderedDict()
        for n in names:
            pre = n.rsplit(".", 1)[0] if "." in n else "(rgba)"
            layers.setdefault(pre, []).append(n.rsplit(".", 1)[-1])
        order = {"R": 0, "G": 1, "B": 2, "A": 3, "X": 0, "Y": 1, "Z": 2}
        for k in layers:
            layers[k].sort(key=lambda c: (order.get(c.upper(), 9), c))
        rows.append(("Channels", f"{len(names)} in {len(layers)} layer(s)"))
        if len(layers) > 1 or names[:3] != ["R", "G", "B"]:
            rows.append(("Layers", "<br>".join(
                f"{k} <span style='color:#888'>[{''.join(v) if all(len(x) == 1 for x in v) else ','.join(v)}]</span>"
                for k, v in layers.items())))
        nsub = spec.get_int_attribute("oiio:subimages", 1)
        if nsub > 1:
            rows.append(("Parts", str(nsub)))
        mips = 1
        while inp.seek_subimage(0, mips):
            mips += 1
        if mips > 1:
            rows.append(("Mipmaps", f"{mips} levels"))
        if spec.tile_width:
            rows.append(("Tiles", f"{spec.tile_width}×{spec.tile_height}"))
        cs = detect_cs_from_chroma(spec.getattribute("chromaticities"))
        if cs:
            rows.append(("Chromaticities", {"aces": "ACES AP0", "acescg": "ACEScg AP1", "lin709": "Rec.709"}[cs]))
        ocs = spec.get_string_attribute("oiio:ColorSpace")
        if ocs:
            rows.append(("ColorSpace", ocs))
        for attr, label in (("FramesPerSecond", "FPS"), ("Software", "Software"), ("DateTime", "Date"),
                            ("HostComputer", "Host")):
            v = spec.getattribute(attr)
            if v not in (None, ""):
                if attr == "FramesPerSecond":
                    try:
                        v = f"{v[0] / v[1]:.3f}".rstrip("0").rstrip(".") if isinstance(v, tuple) else v
                    except Exception:
                        pass
                rows.append((label, str(v)))
    finally:
        inp.close()
    return rows


def video_info(path, ffprobe):
    if not ffprobe:
        return [("Info", "ffprobe not found (see Settings)")]
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW)
    d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    rows = []
    vs = [s for s in d.get("streams", []) if s.get("codec_type") == "video"]
    aus = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    if vs:
        s = vs[0]
        rows.append(("Resolution", f"{s.get('width')} × {s.get('height')}"))
        prof = s.get("profile")
        rows.append(("Codec", f"{s.get('codec_name', '')}" + (f" ({prof})" if prof else "")))
        try:
            a, b = s.get("r_frame_rate", "0/1").split("/")
            rows.append(("FPS", f"{float(a) / float(b):.3f}".rstrip("0").rstrip(".")))
        except Exception:
            pass
        if s.get("pix_fmt"):
            rows.append(("Pixel format", s["pix_fmt"]))
        if s.get("nb_frames"):
            rows.append(("Frames", s["nb_frames"]))
        if s.get("color_primaries") or s.get("color_transfer"):
            rows.append(("Color", f"{s.get('color_primaries', '?')} / {s.get('color_transfer', '?')}"))
        tc = s.get("tags", {}).get("timecode") or d.get("format", {}).get("tags", {}).get("timecode")
        if tc:
            rows.append(("Timecode", tc))
    fmt = d.get("format", {})
    if fmt.get("duration"):
        dur = float(fmt["duration"])
        rows.append(("Duration", f"{int(dur // 60):02d}:{dur % 60:05.2f}"))
    if fmt.get("bit_rate"):
        rows.append(("Bitrate", f"{int(fmt['bit_rate']) / 1e6:.1f} Mb/s"))
    rows.append(("Audio", f"{len(aus)} track(s)" if aus else "no"))
    return rows


def qt_info(path):
    r = QImageReader(path)
    sz = r.size()
    rows = []
    if sz.isValid():
        rows.append(("Resolution", f"{sz.width()} × {sz.height()}"))
    fmt = bytes(r.format()).decode() if r.format() else ""
    if fmt:
        rows.append(("Format", fmt.upper()))
    return rows


class InfoTask(QRunnable):
    def __init__(self, token, entry, ffprobe, index, sidecar, signals):
        super().__init__()
        self.token, self.e, self.ffprobe, self.index, self.sidecar, self.signals = \
            token, entry, ffprobe, index, sidecar, signals

    def run(self):
        rows = []
        e = self.e
        try:
            src = e.thumb_source()
            e2 = e.ext.lstrip(".")
            if e.cat in ("model", "dir"):
                if self.sidecar:
                    sc = find_sidecar(e, self.index)
                    if sc:
                        rows.append(("Preview", os.path.basename(sc)))
            elif e.cat == "video":
                rows = video_info(src, self.ffprobe)
            elif e2 in QT_FAST:
                rows = qt_info(src)
            elif e2 in OIIO_EXTS and HAS_OIIO:
                rows = oiio_info(src)
        except Exception as ex:
            rows = [("Error", str(ex))]
        html = "".join(f"<tr><td class='k'>{k}</td><td>{v}</td></tr>" for k, v in rows)
        self.signals.info.emit(self.token, html)
