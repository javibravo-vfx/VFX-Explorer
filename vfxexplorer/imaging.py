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
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QImageReader

try:
    import OpenImageIO as oiio
    oiio.attribute("threads", 2)
    HAS_OIIO = True
except Exception:  # pragma: no cover
    oiio = None
    HAS_OIIO = False

from .core import IS_WIN, VIDEO_EXTS, find_tool

NO_WINDOW = 0x08000000 if IS_WIN else 0
THUMB_RES = 320

COLORSPACES = [
    ("ACEScg", "acescg"),
    ("ACES2065-1 (AP0)", "aces"),
    ("Lineal Rec.709 / sRGB", "lin709"),
    ("Ya es sRGB (sin conversión)", "srgb"),
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


def oiio_thumb(path, settings, maxdim=THUMB_RES):
    inp = oiio.ImageInput.open(path)
    if not inp:
        return QImage()
    try:
        spec = inp.spec()
        idx = pick_channels(list(spec.channelnames))
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
                return QImage()
            arr = np.concatenate(rows, 0)
        else:
            a = inp.read_image(0, mip, cb, ce, "float")
            if a is None:
                return QImage()
            a = np.asarray(a)
            if a.ndim == 2:
                a = a[..., None]
            arr = a[::step, ::step][..., sub]
    finally:
        inp.close()

    ext = os.path.splitext(path)[1].lower()
    if ext in (".exr", ".sxr", ".mxr"):
        cs = (detect_cs_from_chroma(chroma) if settings["chroma"] else None) or settings["cs"]
    elif is_float:
        cs = "srgb" if "srgb" in cs_attr else "lin709"
    else:
        cs = "srgb"
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


def video_thumb(path, ffmpeg, maxdim=THUMB_RES):
    if not ffmpeg:
        return QImage()
    vf = f"scale=w={maxdim}:h={maxdim}:force_original_aspect_ratio=decrease"
    for ss in ("1", "0"):
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
            pass
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

def load_thumbnail(e, settings, cache_dir, index):
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
            return img
    e2 = ext.lstrip(".")
    if cat == "video" or ext in VIDEO_EXTS:
        img = video_thumb(src, settings["ffmpeg"])
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
    return img


class Signals(QObject):
    done = Signal(str, QImage)
    info = Signal(int, str)


class ThumbTask(QRunnable):
    def __init__(self, key, entry, settings, cache_dir, index, signals):
        super().__init__()
        self.key, self.e = key, entry
        self.settings, self.cache_dir, self.index, self.signals = settings, cache_dir, index, signals

    def run(self):
        try:
            img = load_thumbnail(self.e, self.settings, self.cache_dir, self.index)
        except Exception:
            img = QImage()
        self.signals.done.emit(self.key, img)


class ThumbManager(QObject):
    ready = Signal(str)

    def __init__(self, cfg, data_dir):
        super().__init__()
        self.cfg = cfg
        self.pool = QThreadPool()
        self.cache = OrderedDict()
        self.scaled = {}
        self.pending = set()
        self.failed = set()
        self.index = DirIndex()
        self.signals = Signals()
        self.signals.done.connect(self._done)
        self.cache_dir = os.path.join(data_dir, "thumbs")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.reload_settings()

    def reload_settings(self):
        self.settings = {
            "cs": self.cfg["colorspace"],
            "chroma": bool(self.cfg["use_chromaticities"]),
            "ffmpeg": find_tool(self.cfg["ffmpeg"], "ffmpeg"),
            "sidecar": bool(self.cfg["sidecar_previews"]),
        }
        self.pool.setMaxThreadCount(max(1, int(self.cfg["threads"])))

    def can_thumb(self, e):
        c = e.cat
        if c in ("dir", "model"):
            return self.settings["sidecar"]
        if c == "other":
            return False
        if c == "video":
            return bool(self.settings["ffmpeg"])
        return can_decode(e.ext)

    @staticmethod
    def key_for(e):
        return e.thumb_source()

    def get(self, e, w=None, h=None):
        if not self.can_thumb(e):
            return None
        key = self.key_for(e)
        pm = self.cache.get(key)
        if pm is None:
            if key not in self.pending and key not in self.failed:
                self.pending.add(key)
                self.pool.start(ThumbTask(key, e, dict(self.settings), self.cache_dir, self.index, self.signals))
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

    def has_failed(self, e):
        return self.key_for(e) in self.failed

    def _done(self, key, img):
        self.pending.discard(key)
        if img.isNull():
            self.failed.add(key)
        else:
            self.cache[key] = QPixmap.fromImage(img)
            while len(self.cache) > 2500:
                self.cache.popitem(last=False)
        self.ready.emit(key)

    def cancel_pending(self):
        self.pool.clear()
        self.pending.clear()

    def forget(self, keys=None):
        """Olvida thumbs (todos o algunos) para que se regeneren."""
        if keys is None:
            self.cancel_pending()
            self.cache.clear()
            self.scaled.clear()
            self.failed.clear()
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
    inp = oiio.ImageInput.open(path)
    if not inp:
        return [("Error", oiio.geterror() or "no se pudo abrir")]
    rows = []
    try:
        spec = inp.spec()
        W, H = spec.width, spec.height
        fw, fh = spec.full_width or W, spec.full_height or H
        rows.append(("Resolución", f"{fw} × {fh}"))
        if (fw, fh) != (W, H) or spec.x != spec.full_x or spec.y != spec.full_y:
            rows.append(("Data window", f"{W} × {H}  ({spec.x},{spec.y})"))
        comp = spec.get_string_attribute("compression")
        if comp:
            rows.append(("Compresión", comp.upper()))
        fmts = [str(t) for t in spec.channelformats] if len(spec.channelformats) else [str(spec.format)]
        rows.append(("Tipo", ", ".join(sorted(set(fmts)))))
        names = list(spec.channelnames)
        layers = OrderedDict()
        for n in names:
            pre = n.rsplit(".", 1)[0] if "." in n else "(rgba)"
            layers.setdefault(pre, []).append(n.rsplit(".", 1)[-1])
        order = {"R": 0, "G": 1, "B": 2, "A": 3, "X": 0, "Y": 1, "Z": 2}
        for k in layers:
            layers[k].sort(key=lambda c: (order.get(c.upper(), 9), c))
        rows.append(("Canales", f"{len(names)} en {len(layers)} capa(s)"))
        if len(layers) > 1 or names[:3] != ["R", "G", "B"]:
            rows.append(("Capas", "<br>".join(
                f"{k} <span style='color:#888'>[{''.join(v) if all(len(x) == 1 for x in v) else ','.join(v)}]</span>"
                for k, v in layers.items())))
        nsub = spec.get_int_attribute("oiio:subimages", 1)
        if nsub > 1:
            rows.append(("Partes", str(nsub)))
        mips = 1
        while inp.seek_subimage(0, mips):
            mips += 1
        if mips > 1:
            rows.append(("Mipmaps", f"{mips} niveles"))
        if spec.tile_width:
            rows.append(("Tiles", f"{spec.tile_width}×{spec.tile_height}"))
        cs = detect_cs_from_chroma(spec.getattribute("chromaticities"))
        if cs:
            rows.append(("Chromaticities", {"aces": "ACES AP0", "acescg": "ACEScg AP1", "lin709": "Rec.709"}[cs]))
        ocs = spec.get_string_attribute("oiio:ColorSpace")
        if ocs:
            rows.append(("ColorSpace", ocs))
        for attr, label in (("FramesPerSecond", "FPS"), ("Software", "Software"), ("DateTime", "Fecha"),
                            ("HostComputer", "Equipo")):
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
        return [("Info", "ffprobe no encontrado (ver Configuración)")]
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW)
    d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    rows = []
    vs = [s for s in d.get("streams", []) if s.get("codec_type") == "video"]
    aus = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    if vs:
        s = vs[0]
        rows.append(("Resolución", f"{s.get('width')} × {s.get('height')}"))
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
        rows.append(("Duración", f"{int(dur // 60):02d}:{dur % 60:05.2f}"))
    if fmt.get("bit_rate"):
        rows.append(("Bitrate", f"{int(fmt['bit_rate']) / 1e6:.1f} Mb/s"))
    rows.append(("Audio", f"{len(aus)} pista(s)" if aus else "no"))
    return rows


def qt_info(path):
    r = QImageReader(path)
    sz = r.size()
    rows = []
    if sz.isValid():
        rows.append(("Resolución", f"{sz.width()} × {sz.height()}"))
    fmt = bytes(r.format()).decode() if r.format() else ""
    if fmt:
        rows.append(("Formato", fmt.upper()))
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
