# -*- coding: utf-8 -*-
"""Viewer / player de VFX Library: secuencias (EXR, JPG, PNG…), videos (vía ffmpeg) e imágenes / HDRIs.

Un solo reproductor de frames: un thread decodifica por delante del cabezal y guarda los frames en una
caché con límite de memoria; la reproducción solo avanza cuando el próximo frame está listo (en el primer
loop puede ir más lento que tiempo real; después corre a la velocidad elegida)."""

import os
import json
import time
import threading
import subprocess

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect, QRectF, QSize, QObject
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSlider, QLabel, QComboBox,
                               QSizePolicy)
from collections import OrderedDict

from . import imaging
from .core import VIDEO_EXTS, find_tool, human_size, IS_WIN

NO_WINDOW = 0x08000000 if IS_WIN else 0
FPS_CHOICES = ["12", "23.976", "24", "25", "29.97", "30", "48", "50", "60"]
HDR_STILL_EXTS = {".exr", ".hdr", ".sxr", ".mxr", ".pfm", ".rgbe"}
HDR_RES = 2048          # el visor de HDRIs lee hasta este tamaño (lo que entra en pantalla, con aire)
HDR_CACHE = 10          # HDRIs ya leídos que quedan en memoria (ir y volver es instantáneo)
LDR_RES = 2048          # fotos (JPG, PNG, TIFF, RAW…): se leen hasta este tamaño
LDR_CACHE = 30          # fotos ya leídas que quedan en memoria
STILL_RAM = 512 << 20   # memoria para las imágenes sueltas ya leídas (fotos y HDRIs), como el visor de fotos


class StillPool(QObject):
    """Dos hilos fijos para leer imágenes sueltas (como el visor de fotos): la que se pidió va primero y las
    precargas esperan; las precargas que ya no sirven (te moviste para otro lado) se descartan."""
    done = Signal(object, object)                 # clave, resultado

    def __init__(self, parent=None, workers=2):
        super().__init__(parent)
        import collections
        self._fg = collections.deque()
        self._bg = collections.deque()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._running = set()
        for _ in range(workers):
            threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, key, fn, foreground):
        with self._cv:
            if key in self._running:
                return
            for q in (self._fg, self._bg):
                for i, (k, f) in enumerate(q):
                    if k == key:
                        if foreground and q is self._bg:      # ya estaba como precarga: pasa adelante
                            del q[i]
                            self._fg.appendleft((key, fn))
                            self._cv.notify()
                        return
            (self._fg.appendleft if foreground else self._bg.append)((key, fn))
            self._cv.notify()

    def keep_only(self, keys):
        """Precargas pendientes que ya no hacen falta: afuera."""
        with self._cv:
            for k, f in list(self._bg):
                if k not in keys:
                    self._bg.remove((k, f))

    def busy(self, key):
        with self._lock:
            return key in self._running or any(k == key for k, _ in self._fg) or any(k == key for k, _ in self._bg)

    def _loop(self):
        while True:
            with self._cv:
                while not self._fg and not self._bg:
                    self._cv.wait()
                key, fn = (self._fg or self._bg).popleft()
                self._running.add(key)
            try:
                r = fn()
            except Exception:
                r = None
            with self._lock:
                self._running.discard(key)
            try:
                self.done.emit(key, r)
            except RuntimeError:                  # la ventana ya se cerró
                return


# ----------------------------------------------------------------------------
# Fuentes de frames
# ----------------------------------------------------------------------------

def _read_image(path, settings, maxdim):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in imaging.QT_FAST:
        return imaging.qt_thumb(path, maxdim)
    if ext in imaging.OIIO_EXTS and imaging.HAS_OIIO:
        return imaging.oiio_thumb(path, settings, maxdim)
    return QImage()


class SeqSource:
    sequential = False

    def __init__(self, e, settings, maxdim):
        self.paths = [os.path.join(e.dirpath, f) for f in e.files]
        self.labels = list(e.frames)
        self.n = len(self.paths)
        self.fps = None
        self.settings, self.maxdim = settings, maxdim

    def read(self, i):
        return _read_image(self.paths[i], self.settings, self.maxdim)

    def close(self):
        pass


class StillSource(SeqSource):
    def __init__(self, path, settings, maxdim):
        self.paths = [path]
        self.labels = [1]
        self.n = 1
        self.fps = None
        self.settings, self.maxdim = settings, maxdim


def probe_video(path, ffprobe):
    if not ffprobe:
        return None
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-print_format", "json",
           "-show_streams", "-show_format", path]
    r = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW)
    d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    st = (d.get("streams") or [None])[0]
    if not st:
        return None
    try:
        a, b = st.get("avg_frame_rate", "0/1").split("/")
        fps = float(a) / float(b) if float(b) else 0
    except Exception:
        fps = 0
    if not fps:
        try:
            a, b = st.get("r_frame_rate", "24/1").split("/")
            fps = float(a) / float(b)
        except Exception:
            fps = 24.0
    n = int(st.get("nb_frames") or 0)
    if not n:
        dur = float(st.get("duration") or d.get("format", {}).get("duration") or 0)
        n = max(1, int(round(dur * fps)))
    return {"w": int(st.get("width") or 0), "h": int(st.get("height") or 0), "fps": fps, "n": n}


class VideoSource:
    sequential = True

    def __init__(self, path, ffmpeg, info, maxdim):
        self.path, self.ffmpeg = path, ffmpeg
        w, h = info["w"] or 1920, info["h"] or 1080
        s = min(1.0, maxdim / max(w, h))
        self.W = max(2, int(w * s) // 2 * 2)
        self.H = max(2, int(h * s) // 2 * 2)
        self.fb = self.W * self.H * 3
        self.n = info["n"]
        self.fps = info["fps"]
        self.labels = list(range(1, self.n + 1))
        self.proc = None
        self.pos = 0

    def _start(self, i):
        self.close()
        ss = max(0.0, i / self.fps) if self.fps else 0.0
        cmd = [self.ffmpeg, "-v", "error", "-ss", f"{ss:.4f}", "-i", self.path, "-an", "-sn",
               "-vf", f"scale={self.W}:{self.H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=self.fb * 2, creationflags=NO_WINDOW)
        self.pos = i

    def _read_raw(self):
        buf = bytearray()
        while len(buf) < self.fb:
            chunk = self.proc.stdout.read(self.fb - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def read(self, i):
        if self.proc is None or i < self.pos or i > self.pos + 36:
            self._start(i)
        while self.pos < i:
            if self._read_raw() is None:
                return None
            self.pos += 1
        data = self._read_raw()
        if data is None:
            return None
        self.pos += 1
        return QImage(data, self.W, self.H, self.W * 3, QImage.Format_RGB888).copy()

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
            self.proc = None


# ----------------------------------------------------------------------------
# Thread de decodificación con caché
# ----------------------------------------------------------------------------

class DecodeThread(QThread):
    frame_ready = Signal(int)
    length_changed = Signal(int)
    failed = Signal(str)

    def __init__(self, source, budget_bytes):
        super().__init__()
        self.src = source
        self.n = source.n
        self.budget = budget_bytes
        self.max_frames = source.n
        self.cache = {}
        self.lock = threading.Lock()
        self.playhead = 0
        self.stopped = False
        self.bad = set()

    def get(self, i):
        with self.lock:
            return self.cache.get(i)

    def cached_count(self):
        with self.lock:
            return len(self.cache)

    def stop(self):
        self.stopped = True

    def run(self):
        first = True
        try:
            while not self.stopped:
                n = self.n
                if n <= 0:
                    break
                ph = self.playhead % n
                window = min(n, self.max_frames)
                target = None
                for k in range(window):
                    i = (ph + k) % n
                    if i not in self.cache and i not in self.bad:
                        target = i
                        break
                if target is None:
                    self.msleep(12)
                    continue
                try:
                    img = self.src.read(target)
                except Exception as ex:
                    img = None
                    if first:
                        self.failed.emit(str(ex))
                if self.stopped:
                    break
                if img is None or img.isNull():
                    if self.src.sequential and target > 0 and target < self.n:
                        self.n = target          # el video tenía menos frames de los informados
                        self.length_changed.emit(target)
                    else:
                        self.bad.add(target)
                        if first and len(self.bad) >= min(3, n):
                            self.failed.emit("Could not decode")
                            break
                    continue
                with self.lock:
                    self.cache[target] = img
                    if first:
                        first = False
                        per = max(1, img.sizeInBytes())
                        self.max_frames = max(6, int(self.budget // per))
                    if len(self.cache) > self.max_frames:
                        keep = {(ph + k) % n for k in range(min(n, self.max_frames))}
                        for key in [k for k in self.cache if k not in keep]:
                            del self.cache[key]
                self.frame_ready.emit(target)
        finally:
            try:
                self.src.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# Widgets
# ----------------------------------------------------------------------------

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.message = ""
        self.title = ""
        self.corner = ""
        self.buffering = False
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.ClickFocus)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0c0d"))
        r = self.rect()
        if self.image is not None and not self.image.isNull():
            sz = self.image.size().scaled(r.size(), Qt.KeepAspectRatio)
            tgt = QRect((r.width() - sz.width()) // 2, (r.height() - sz.height()) // 2, sz.width(), sz.height())
            # la imagen ya escalada al tamaño del panel se guarda: repintar no la vuelve a escalar
            ck = (self.image.cacheKey(), sz.width(), sz.height())
            if getattr(self, "_spm_key", None) != ck:
                from PySide6.QtGui import QPixmap
                self._spm = QPixmap.fromImage(self.image.scaled(sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self._spm_key = ck
            p.drawPixmap(tgt.topLeft(), self._spm)
        if self.message:
            p.setPen(QColor("#7d8590"))
            f = QFont(self.font())
            f.setPointSizeF(10.5)
            p.setFont(f)
            p.drawText(r.adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, self.message)
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        fm = QFontMetrics(f)
        if self.title:
            t = fm.elidedText(self.title, Qt.ElideMiddle, r.width() - 200)
            p.fillRect(QRect(8, 8, fm.horizontalAdvance(t) + 12, fm.height() + 6), QColor(0, 0, 0, 150))
            p.setPen(QColor("#e8e8e8"))
            p.drawText(QRect(14, 11, r.width(), fm.height()), Qt.AlignLeft, t)
        if self.corner:
            w = fm.horizontalAdvance(self.corner) + 12
            p.fillRect(QRect(r.width() - w - 8, 8, w, fm.height() + 6), QColor(0, 0, 0, 150))
            p.setPen(QColor("#c9ccd1"))
            p.drawText(QRect(r.width() - w - 2, 11, w, fm.height()), Qt.AlignLeft, self.corner)
        if self.buffering:
            p.setPen(QColor("#f5c542"))
            p.drawText(QRect(14, r.height() - fm.height() - 12, 300, fm.height() + 4), Qt.AlignLeft, "loading…")
        p.end()


class Viewer(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.thread = None
        self.entry = None
        self.cur = 0
        self.n = 0
        self.labels = []
        self.playing = False
        self.fps = float(app.cfg["viewer_fps"] or 24)
        self._old_threads = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.canvas = Canvas()
        lay.addWidget(self.canvas, 1)

        bar = QWidget()
        bar.setObjectName("viewerBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 3, 6, 3)
        bl.setSpacing(4)
        ic = app.icons

        def btn(glyph, tip, slot, checkable=False):
            b = QToolButton()
            b.setIcon(ic.glyph(glyph, 18))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setCheckable(checkable)
            if slot:
                b.clicked.connect(slot)
            bl.addWidget(b)
            return b
        self.b_prev = btn("prev", "Previous frame (,)", lambda: self.step(-1))
        self.b_play = btn("play", "Play / pause (Space)", self.toggle)
        self.b_next = btn("next", "Next frame (.)", lambda: self.step(1))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.seek)
        self.slider.sliderPressed.connect(lambda: self.seek(self.slider.value()))
        bl.addWidget(self.slider, 1)
        self.lbl = QLabel("—")
        self.lbl.setMinimumWidth(130)
        self.lbl.setStyleSheet("color:#c9ccd1; font-family:Consolas,monospace;")
        bl.addWidget(self.lbl)
        self.layer_cb = QComboBox()
        self.layer_cb.setToolTip("EXR layer / AOV (beauty, alpha, depth, normals…)")
        self.layer_cb.setMinimumContentsLength(14)
        self.layer_cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.layer_cb.activated.connect(self._layer_changed)
        self.layer_cb.hide()
        bl.addWidget(self.layer_cb)
        self._layers = []
        self._layer_pref = "Beauty / RGB"
        self.fps_cb = QComboBox()
        self.fps_cb.addItems(FPS_CHOICES)
        self.fps_cb.setCurrentText(self._fps_text(self.fps))
        self.fps_cb.setToolTip("Sequence speed (fps). Videos use their own.")
        self.fps_cb.currentTextChanged.connect(self._fps_changed)
        bl.addWidget(self.fps_cb)
        self.b_loop = btn("loop", "Loop", None, checkable=True)
        self.b_loop.setChecked(bool(app.cfg["viewer_loop"]))
        self.b_loop.toggled.connect(lambda v: self._save("viewer_loop", v))
        self.b_auto = QToolButton()
        self.b_auto.setText("Auto")
        self.b_auto.setCheckable(True)
        self.b_auto.setAutoRaise(True)
        self.b_auto.setToolTip("Autoplay on selection")
        self.b_auto.setChecked(bool(app.cfg["viewer_autoplay"]))
        self.b_auto.toggled.connect(lambda v: self._save("viewer_autoplay", v))
        bl.addWidget(self.b_auto)
        # HDRIs (EXR / HDR sueltos): en vez de los controles de reproducción, exposición y gamma
        self.hdr_bar = QWidget()
        hl = QHBoxLayout(self.hdr_bar)
        hl.setContentsMargins(4, 0, 0, 0)
        hl.setSpacing(6)
        self.exposure, self.gamma = 0.0, 1.0
        self.exp_lbl = QLabel()
        self.exp_sl = QSlider(Qt.Horizontal)
        self.exp_sl.setRange(-80, 80)                    # décimas de stop: -8 … +8
        self.gam_lbl = QLabel()
        self.gam_sl = QSlider(Qt.Horizontal)
        self.gam_sl.setRange(20, 300)                    # 0.20 … 3.00
        self.gam_sl.setValue(100)
        for lb in (self.exp_lbl, self.gam_lbl):
            lb.setStyleSheet("color:#c9ccd1;")
            lb.setMinimumWidth(104)
        self.exp_sl.setToolTip("Exposure in stops (double-click: back to 0)")
        self.gam_sl.setToolTip("Gamma (double-click: back to 1.00)")
        self.exp_sl.valueChanged.connect(lambda v: self._set_look(exposure=v / 10.0))
        self.gam_sl.valueChanged.connect(lambda v: self._set_look(gamma=v / 100.0))
        self.exp_sl.installEventFilter(self)
        self.gam_sl.installEventFilter(self)
        hl.addWidget(self.exp_lbl)
        hl.addWidget(self.exp_sl, 2)
        hl.addSpacing(14)
        hl.addWidget(self.gam_lbl)
        hl.addWidget(self.gam_sl, 1)
        b_reset = QToolButton()
        b_reset.setText("Reset")
        b_reset.setAutoRaise(True)
        b_reset.setToolTip("Exposure 0, gamma 1.00")
        b_reset.clicked.connect(lambda: (self.exp_sl.setValue(0), self.gam_sl.setValue(100)))
        hl.addWidget(b_reset)
        bl.insertWidget(0, self.hdr_bar, 1)
        self.hdr_bar.hide()
        self._play_widgets = [self.b_prev, self.b_play, self.b_next, self.slider, self.fps_cb, self.b_loop,
                              self.b_auto]
        self._hdr_mode = False
        self._hdr_cache = OrderedDict()                  # (ruta, fecha, capa) → (rgb, alpha)
        self._hdr_cur = None
        self._hdr_busy = set()
        self._look_timer = QTimer(self, singleShot=True, interval=0, timeout=self._show_hdr)
        self._update_look_labels()
        lay.addWidget(bar)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self._set_interval()
        self.show_message("Pick a library element below.\n"
                          "Move with the arrow keys and it plays by itself (looped).")

    # ---------------- HDRIs
    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.MouseButtonDblClick and obj in (self.exp_sl, self.gam_sl):
            obj.setValue(0 if obj is self.exp_sl else 100)
            return True
        return super().eventFilter(obj, ev)

    @staticmethod
    def is_hdr_still(e):
        return e is not None and e.kind == "file" and (e.ext or "").lower() in HDR_STILL_EXTS

    @classmethod
    def is_still(cls, e):
        """Una imagen suelta (foto o HDRI): visor rápido, sin controles de reproducción."""
        return e is not None and e.kind == "file" and (cls.is_hdr_still(e) or e.cat == "image")

    def _set_hdr_mode(self, on, kind=None):
        """on: imagen suelta (sin controles de player); kind "hdr" muestra exposición y gamma."""
        kind = kind if on else None
        if (on, kind) == (self._hdr_mode, getattr(self, "_still_kind", None)):
            return
        self._hdr_mode = on
        self._still_kind = kind
        for w in self._play_widgets:
            w.setVisible(not on)
        self.hdr_bar.setVisible(on and kind == "hdr")

    def _update_look_labels(self):
        self.exp_lbl.setText(f"Exposure: {self.exposure:+.1f}")
        self.gam_lbl.setText(f"Gamma: {self.gamma:.2f}")

    def _set_look(self, exposure=None, gamma=None):
        if exposure is not None:
            self.exposure = exposure
        if gamma is not None:
            self.gamma = gamma
        self._update_look_labels()
        if self._hdr_mode and self._hdr_cur is not None:
            self._look_timer.start()                     # se junta con el próximo movimiento del slider

    def _show_hdr(self):
        if self._hdr_cur is None:
            return
        if isinstance(self._hdr_cur, QImage):        # una foto: tal cual, sin exposición ni gamma
            img = self._hdr_cur
            self.canvas.image = img
            self.canvas.buffering = False
            self.canvas.corner = getattr(self, "_still_size", "") or f"{img.width()}×{img.height()}"
            self.canvas.update()
            return
        rgb, alpha = self._hdr_cur
        self.canvas.image = imaging.hdr_display(rgb, self.exposure, self.gamma, alpha)
        self.canvas.buffering = False
        self.canvas.corner = f"{rgb.shape[1]}×{rgb.shape[0]}"
        self.canvas.update()

    def _hdr_key(self, e, settings):
        # la fecha que ya se leyó al listar la carpeta: sin tocar el disco (un NAS dormido trababa la ventana)
        return (e.path, getattr(e, "mtime", 0) or 0, tuple(settings.get("channels") or ()))

    def _hdr_decode(self, path, settings):
        try:
            if os.path.splitext(path)[1].lower() in HDR_STILL_EXTS:
                return imaging.hdr_linear(path, settings, HDR_RES)
            img = _read_image(path, settings, LDR_RES)        # foto: decodificada ya escalada (rapidísimo)
            return img if img is not None and not img.isNull() else None
        except Exception:
            return None

    @staticmethod
    def _nbytes(v):
        if isinstance(v, QImage):
            return v.sizeInBytes()
        rgb, alpha = v
        return rgb.nbytes + (alpha.nbytes if alpha is not None else 0)

    def _hdr_store(self, key, r):
        """Caché por memoria (512 MB, como el visor de fotos); se van las más viejas."""
        self._hdr_cache[key] = r
        self._hdr_cache.move_to_end(key)
        total = sum(self._nbytes(v) for v in self._hdr_cache.values())
        while len(self._hdr_cache) > 1 and (total > STILL_RAM or len(self._hdr_cache) > HDR_CACHE + LDR_CACHE):
            k, v = self._hdr_cache.popitem(last=False)
            total -= self._nbytes(v)

    def _start_hdr(self, e, settings):
        """Una imagen suelta: primero el thumbnail que ya está (al instante), después la imagen (HDRI: en float)."""
        hdr = self.is_hdr_still(e)
        self._set_hdr_mode(True, "hdr" if hdr else "ldr")
        self.n, self.labels = 1, [1]
        self.lbl.setText("HDR" if hdr else "image")
        self.canvas.message = ""
        self.canvas.title = e.name
        self.canvas.corner = ""
        key = self._hdr_key(e, settings)
        hit = self._hdr_cache.get(key)
        if hit is not None:
            self._hdr_cache.move_to_end(key)
            self._hdr_cur = hit
            self._show_hdr()
            return
        self._hdr_cur = None
        pm = self.app.thumbs.cache.get(self.app.thumbs.key_for(e))
        self.canvas.image = pm.toImage() if pm is not None and hasattr(pm, "toImage") else \
            (pm if pm is not None else None)
        self.canvas.buffering = True
        self.canvas.update()
        self._hdr_wait = (self._load_token, key)        # la que se espera (aunque la haya pedido la precarga)
        path = e.path
        self._pool().submit(key, lambda: self._hdr_decode(path, settings), foreground=True)

    def _pool(self):
        if getattr(self, "_still_pool", None) is None:
            self._still_pool = StillPool(self)
            self._still_pool.done.connect(self._pool_done)
        return self._still_pool

    def _pool_done(self, key, r):
        if r is not None:
            self._hdr_store(key, r)
        self._hdr_arrived(key, r)

    def _hdr_arrived(self, key, r, tok=None):
        wait = getattr(self, "_hdr_wait", None)
        mine = wait and wait[1] == key and wait[0] == self._load_token
        if not mine or not self._hdr_mode:
            return
        self._hdr_wait = None
        if r is None:
            self.show_message(f"{self.entry.name if self.entry else ''}\n\nCould not read the image")
            return
        self._hdr_cur = r
        self._show_hdr()

    def prefetch(self, entries):
        """Los HDRIs de al lado (siguiente / anterior) se leen de antemano: al moverse con las flechas
        aparecen al instante."""
        settings = dict(self.app.thumbs.settings)
        pool = self._pool()
        want = []
        for e in entries:
            if not self.is_still(e):
                continue
            key = self._hdr_key(e, settings)
            want.append(key)
            if key in self._hdr_cache:
                continue
            pool.submit(key, lambda p=e.path: self._hdr_decode(p, settings), foreground=False)
        pool.keep_only(set(want))

    def cached_still(self, e):
        """¿Ya está en memoria? (entonces se muestra sin esperar)"""
        if not self.is_still(e):
            return False
        return self._hdr_key(e, dict(self.app.thumbs.settings)) in self._hdr_cache

    # ---------------- util
    @staticmethod
    def _fps_text(f):
        for t in FPS_CHOICES:
            if abs(float(t) - f) < 0.01:
                return t
        return f"{f:.3f}".rstrip("0").rstrip(".")

    def _save(self, k, v):
        self.app.cfg[k] = v
        self.app.save_soon()

    def _fps_changed(self, t):
        try:
            self.fps = float(t)
        except ValueError:
            return
        self._set_interval()
        if self.entry is not None and self.entry.kind == "seq":
            self._save("viewer_fps", self.fps)

    def _set_interval(self):
        self.timer.setInterval(max(5, int(round(1000.0 / max(1.0, self.fps)))))

    def show_message(self, text):
        if hasattr(self, "layer_cb") and self.entry is None:
            self.layer_cb.hide()
        if hasattr(self, "_hdr_mode") and (self.entry is None or not self.is_still(self.entry)):
            self._set_hdr_mode(False)
            self._hdr_cur = None
        self.canvas.image = None
        self.canvas.message = text
        self.canvas.title = ""
        self.canvas.corner = ""
        self.canvas.buffering = False
        self.canvas.update()

    # ---------------- carga
    def stop(self):
        self.pause()
        if self.thread is not None:
            t = self.thread
            t.stop()
            try:
                t.frame_ready.disconnect()
                t.length_changed.disconnect()
                t.failed.disconnect()
            except Exception:
                pass
            self._old_threads.append(t)
            t.finished.connect(lambda t=t: self._old_threads.remove(t) if t in self._old_threads else None)
            self.thread = None

    def _layer_changed(self, i):
        if 0 <= i < len(self._layers):
            self._layer_pref = self._layers[i][0].split("  [")[0]
            playing = self.playing
            cur = self.cur
            self.load(self.entry, keep_layers=True, start=cur)
            if not playing:
                self.pause()

    def _fill_layers(self, e):
        path = e.thumb_source() if e.kind == "seq" else e.path
        try:
            layers = imaging.exr_layers(path) if e.ext == ".exr" else []
        except Exception:
            layers = []
        self._set_layers(layers)

    def load(self, e, keep_layers=False, start=0):
        if self.entry is not None and self.n > 1:          # F7: se vuelve al mismo frame para comparar
            self._resume = getattr(self, "_resume", {})
            self._resume[self.entry.path] = self.cur
            if len(self._resume) > 50:
                self._resume.pop(next(iter(self._resume)))
        self.stop()
        self.entry = e
        self.cur = 0
        self.n = 0
        self._load_token = getattr(self, "_load_token", 0) + 1
        if e is None:
            self.show_message("")
            return
        from .core import net_root
        if net_root(e.dirpath or e.path):
            # en la red (un NAS despertando tarda): capas y ffprobe se leen en otro hilo
            tok = self._load_token
            self.canvas.message = ""
            self.canvas.image = None
            self.canvas.title = e.name
            self.canvas.buffering = True
            self.canvas.update()
            from .asyncdir import run_async
            run_async(lambda: self._prepare(e, keep_layers),
                      lambda r: tok == self._load_token and self._start(e, r, keep_layers, start), self)
            return
        self._start(e, self._prepare(e, keep_layers), keep_layers, start)

    def _prepare(self, e, keep_layers):
        """Lo que lee el disco (puede correr en otro hilo): capas del EXR e info del video."""
        out = {"layers": None, "info": None, "err": None}
        if not keep_layers:
            path = e.thumb_source() if e.kind == "seq" else e.path
            try:
                out["layers"] = imaging.exr_layers(path) if e.ext == ".exr" else []
            except Exception:
                out["layers"] = []
        if e.cat == "video" and e.kind != "seq":
            ffprobe = find_tool(self.app.cfg["ffmpeg"], "ffprobe")
            if ffprobe:
                try:
                    out["info"] = probe_video(e.path, ffprobe)
                except Exception:
                    out["info"] = None
        return out

    def _set_layers(self, layers):
        self._layers = layers
        self.layer_cb.blockSignals(True)
        self.layer_cb.clear()
        sel = 0
        for i, (label, chans, data) in enumerate(self._layers):
            self.layer_cb.addItem(label)
            if label.split("  [")[0] == self._layer_pref:
                sel = i
        self.layer_cb.setCurrentIndex(sel)
        self.layer_cb.blockSignals(False)
        self.layer_cb.setVisible(len(self._layers) > 1)

    def _start(self, e, prep, keep_layers, start):
        cfg = self.app.cfg
        maxdim = int(cfg["viewer_res"] or 1280)
        settings = dict(self.app.thumbs.settings)
        if not keep_layers and prep["layers"] is not None:
            self._set_layers(prep["layers"])
        li = self.layer_cb.currentIndex()
        if self._layers and 0 <= li < len(self._layers) and self._layers[li][1]:
            settings["channels"] = self._layers[li][1]
            settings["data"] = self._layers[li][2]
        if self.is_still(e):
            self._start_hdr(e, settings)
            return
        self._set_hdr_mode(False)
        self._hdr_cur = None
        src = None
        if e.kind == "seq":
            src = SeqSource(e, settings, maxdim)
        elif e.cat == "video":
            ffmpeg = find_tool(cfg["ffmpeg"], "ffmpeg")
            ffprobe = find_tool(cfg["ffmpeg"], "ffprobe")
            if not ffmpeg or not ffprobe:
                self.show_message(f"{e.name}\n\nTo play videos put ffmpeg.exe and ffprobe.exe in the "
                                  f"bin\\ folder of VFX Explorer (or set the path in ⚙ Settings).")
                return
            info = prep["info"]
            if not info:
                self.show_message(f"{e.name}\n\nCould not read the video.")
                return
            src = VideoSource(e.path, ffmpeg, info, maxdim)
        elif e.cat == "image" or (e.cat in ("model", "dir") and self.app.cfg["sidecar_previews"]):
            path = e.path
            if e.cat in ("model", "dir"):
                path = imaging.find_sidecar(e, self.app.thumbs.index)
            if path and imaging.can_decode(os.path.splitext(path)[1]):
                src = StillSource(path, settings, max(maxdim, 1600))
        if src is None:
            self.show_message(f"{e.name}\n\n" + ("Folder" if e.kind == "dir" else "No preview for this type"))
            return
        self.n = src.n
        self.labels = src.labels
        if src.fps:
            self.fps_cb.blockSignals(True)
            self.fps_cb.setCurrentText(self._fps_text(src.fps))
            self.fps_cb.blockSignals(False)
            self.fps = src.fps
        elif e.kind == "seq":
            self.fps = float(cfg["viewer_fps"] or 24)
            self.fps_cb.blockSignals(True)
            self.fps_cb.setCurrentText(self._fps_text(self.fps))
            self.fps_cb.blockSignals(False)
        self._set_interval()
        self.slider.setRange(0, max(0, self.n - 1))
        self.slider.setValue(0)
        self.canvas.message = ""
        self.canvas.image = None
        self.canvas.title = e.name
        self.canvas.corner = ""
        self.canvas.buffering = True
        self.canvas.update()
        budget = int(cfg["viewer_mem"] or 1024) * 1024 * 1024
        self.thread = DecodeThread(src, budget)
        self.thread.frame_ready.connect(self._frame_ready)
        self.thread.length_changed.connect(self._length_changed)
        self.thread.failed.connect(lambda msg: self.show_message(f"{e.name}\n\n{msg}"))
        if start:
            self.cur = min(start, self.n - 1)
            self.thread.playhead = self.cur
        self.thread.start()
        self._update_label()
        if self.n > 1 and self.b_auto.isChecked():
            self.play()

    # ---------------- reproducción
    def play(self):
        if self.n <= 1:
            return
        self.playing = True
        self.b_play.setIcon(self.app.icons.glyph("pause", 18))
        self.timer.start()

    def pause(self):
        self.playing = False
        self.b_play.setIcon(self.app.icons.glyph("play", 18))
        self.timer.stop()

    def toggle(self):
        self.pause() if self.playing else self.play()

    def step(self, d):
        if self.n <= 0:
            return
        self.pause()
        self.seek((self.cur + d) % self.n)

    def seek(self, i):
        if not self.n:
            return
        self.cur = max(0, min(self.n - 1, int(i)))
        if self.thread:
            self.thread.playhead = self.cur
        self._show_current()

    def _show_current(self):
        img = self.thread.get(self.cur) if self.thread else None
        if img is not None:
            self.canvas.image = img
            self.canvas.buffering = False
        else:
            self.canvas.buffering = True
        self.slider.blockSignals(True)
        self.slider.setValue(self.cur)
        self.slider.blockSignals(False)
        self._update_label()
        self.canvas.update()

    def _update_label(self):
        if self.entry is not None and self.n > 1:          # F7: se vuelve al mismo frame para comparar
            self._resume = getattr(self, "_resume", {})
            self._resume[self.entry.path] = self.cur
            if len(self._resume) > 50:
                self._resume.pop(next(iter(self._resume)))
        if not self.n:
            self.lbl.setText("—")
            self.canvas.corner = ""
            return
        lab = self.labels[self.cur] if self.cur < len(self.labels) else self.cur + 1
        if self.n == 1:
            img = self.canvas.image
            txt = f"{img.width()}×{img.height()}" if img is not None else ""
            self.lbl.setText("image")
        else:
            first, last = self.labels[0], self.labels[min(len(self.labels), self.n) - 1]
            txt = f"{lab}  [{first}-{last}]"
            self.lbl.setText(f"{lab} / {self.n}f")
        self.canvas.corner = txt

    def _tick(self):
        if not self.playing or not self.thread or self.n <= 1:
            return
        nxt = self.cur + 1
        if nxt >= self.n:
            if not self.b_loop.isChecked():
                self.pause()
                return
            nxt = 0
        if self.thread.get(nxt) is not None:
            self.cur = nxt
            self.thread.playhead = nxt
            self._show_current()
        else:
            self.canvas.buffering = True
            self.canvas.update()

    def _frame_ready(self, i):
        if i == self.cur and (self.canvas.image is None or self.canvas.buffering):
            self._show_current()

    def _length_changed(self, n):
        self.n = n
        self.slider.setRange(0, max(0, n - 1))
        if self.cur >= n:
            self.seek(0)

    def shutdown(self):
        self.stop()
        for t in list(self._old_threads):
            t.wait(2000)
