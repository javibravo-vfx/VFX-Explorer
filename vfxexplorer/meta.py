# -*- coding: utf-8 -*-
"""Columnas VFX (Resolution, FPS, Codec, Channels, Colorspace): se leen del encabezado del archivo en segundo
plano (OpenImageIO para imágenes / primer frame de la secuencia, ffprobe para video) y se guardan en caché."""

import json
import os
import subprocess
from collections import OrderedDict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImageReader

from .imaging import HAS_OIIO, oiio, OIIO_EXTS, QT_FAST, NO_WINDOW, detect_cs_from_chroma

META_KEYS = ("res", "fps", "codec", "ch", "cs")


def _fmt_fps(v):
    try:
        return f"{float(v):.3f}".rstrip("0").rstrip(".")
    except Exception:
        return ""


def read_image_meta(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    out = {}
    if HAS_OIIO and (ext in OIIO_EXTS or ext not in QT_FAST):
        from .media_process import isolated, call
        if isolated(path):
            return call(__name__, "read_image_meta", (path,), preview=True)
        from .imaging import oiio_open
        inp = oiio_open(path)
        if inp:
            try:
                spec = inp.spec()
                fw, fh = spec.full_width or spec.width, spec.full_height or spec.height
                out["res"] = f"{fw}×{fh}"
                comp = spec.get_string_attribute("compression")
                fmts = sorted({str(t) for t in spec.channelformats}) if len(spec.channelformats) else [str(spec.format)]
                out["codec"] = " · ".join(x for x in ((comp or "").upper(), "/".join(fmts)) if x)
                names = list(spec.channelnames)
                layers = {n.rsplit(".", 1)[0] for n in names if "." in n}
                base = "".join(c for c in names if "." not in c and len(c) == 1) or ""
                out["ch"] = (base or f"{len(names)} ch") + (f" +{len(layers)} layers" if layers else "")
                cs = detect_cs_from_chroma(spec.getattribute("chromaticities"))
                ocs = spec.get_string_attribute("oiio:ColorSpace")
                out["cs"] = {"aces": "ACES AP0", "acescg": "ACEScg", "lin709": "Rec.709"}.get(cs, "") or ocs or ""
                fps = spec.getattribute("FramesPerSecond")
                if fps not in (None, ""):
                    out["fps"] = _fmt_fps(fps[0] / fps[1]) if isinstance(fps, tuple) and fps[1] else _fmt_fps(fps)
            finally:
                inp.close()
            return out
    r = QImageReader(path)
    s = r.size()
    if s.isValid():
        out["res"] = f"{s.width()}×{s.height()}"
        out["codec"] = bytes(r.format()).decode().upper()
    return out


def read_video_meta(path, ffprobe):
    if not ffprobe:
        return {}
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-print_format", "json", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW)
    d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    st = (d.get("streams") or [None])[0]
    if not st:
        return {}
    out = {"res": f"{st.get('width')}×{st.get('height')}"}
    prof = st.get("profile")
    out["codec"] = (st.get("codec_name") or "") + (f" ({prof})" if prof and prof != "unknown" else "")
    try:
        a, b = (st.get("avg_frame_rate") or st.get("r_frame_rate") or "0/1").split("/")
        out["fps"] = _fmt_fps(float(a) / float(b)) if float(b) else ""
    except Exception:
        pass
    out["ch"] = st.get("pix_fmt") or ""
    prim, trc = st.get("color_primaries"), st.get("color_transfer")
    out["cs"] = " / ".join(x for x in (prim, trc) if x and x != "unknown")
    return out


class _Sig(QObject):
    done = Signal(str, object)


class _Task(QRunnable):
    def __init__(self, key, kind, path, ffprobe, sig):
        super().__init__()
        self.key, self.kind, self.path, self.ffprobe, self.sig = key, kind, path, ffprobe, sig

    def run(self):
        try:
            m = read_video_meta(self.path, self.ffprobe) if self.kind == "video" else read_image_meta(self.path)
        except Exception:
            m = {}
        self.sig.done.emit(self.key, m or {})


class MetaManager(QObject):
    ready = Signal(str)          # clave (ruta del ítem) con metadata nueva

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.cache = OrderedDict()
        self.pending = set()
        self.sig = _Sig()
        self.sig.done.connect(self._done)
        self.path = os.path.join(app.data_dir, "meta_cache.json")
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.cache = OrderedDict(json.load(f))
        except Exception:
            pass

    @staticmethod
    def key_for(e):
        return f"{e.path}|{int(e.mtime or 0)}|{len(e.files) if e.kind == 'seq' else 0}"

    def applies(self, e):
        return e.kind == "seq" or (e.kind == "file" and e.cat in ("image", "video"))

    def get(self, e):
        """dict con res/fps/codec/ch/cs, o None (y la pide en segundo plano)."""
        if not self.applies(e):
            return {}
        k = self.key_for(e)
        m = self.cache.get(k)
        if m is not None:
            return m
        if k not in self.pending:
            self.pending.add(k)
            src = os.path.join(e.dirpath, e.files[0]) if e.kind == "seq" and e.files else e.path
            kind = "video" if e.cat == "video" else "image"
            self.pool.start(_Task(k, kind, src, self.app.thumbs.settings.get("ffprobe"), self.sig))
        return None

    def _done(self, key, m):
        self.pending.discard(key)
        self.cache[key] = m
        if len(self.cache) > 20000:
            for _ in range(2000):
                self.cache.popitem(last=False)
        self.ready.emit(key.split("|", 1)[0])

    def cancel(self):
        self.pool.clear()
        self.pending.clear()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cache, f)
            os.replace(tmp, self.path)
        except OSError:
            pass
