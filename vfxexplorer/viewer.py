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

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect, QRectF, QSize
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSlider, QLabel, QComboBox,
                               QSizePolicy)

from . import imaging
from .core import VIDEO_EXTS, find_tool, human_size, IS_WIN

NO_WINDOW = 0x08000000 if IS_WIN else 0
FPS_CHOICES = ["12", "23.976", "24", "25", "29.97", "30", "48", "50", "60"]


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
                            self.failed.emit("No se pudo decodificar")
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
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(tgt, self.image)
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
            p.drawText(QRect(14, r.height() - fm.height() - 12, 300, fm.height() + 4), Qt.AlignLeft, "cargando…")
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
        btn("prev", "Frame anterior (,)", lambda: self.step(-1))
        self.b_play = btn("play", "Play / pausa (Espacio)", self.toggle)
        btn("next", "Frame siguiente (.)", lambda: self.step(1))
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
        self.layer_cb.setToolTip("Capa / AOV del EXR (beauty, alpha, depth, normales…)")
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
        self.fps_cb.setToolTip("Velocidad de las secuencias (fps). Los videos usan la suya.")
        self.fps_cb.currentTextChanged.connect(self._fps_changed)
        bl.addWidget(self.fps_cb)
        self.b_loop = btn("loop", "Loop", None, checkable=True)
        self.b_loop.setChecked(bool(app.cfg["viewer_loop"]))
        self.b_loop.toggled.connect(lambda v: self._save("viewer_loop", v))
        self.b_auto = QToolButton()
        self.b_auto.setText("Auto")
        self.b_auto.setCheckable(True)
        self.b_auto.setAutoRaise(True)
        self.b_auto.setToolTip("Reproducir automáticamente al seleccionar")
        self.b_auto.setChecked(bool(app.cfg["viewer_autoplay"]))
        self.b_auto.toggled.connect(lambda v: self._save("viewer_autoplay", v))
        bl.addWidget(self.b_auto)
        lay.addWidget(bar)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self._set_interval()
        self.show_message("Elegí un elemento de la librería abajo.\n"
                          "Con las flechas te movés y se reproduce solo (en loop).")

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
            self._layers = imaging.exr_layers(path) if e.ext == ".exr" else []
        except Exception:
            self._layers = []
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

    def load(self, e, keep_layers=False, start=0):
        self.stop()
        self.entry = e
        self.cur = 0
        self.n = 0
        if e is None:
            self.show_message("")
            return
        cfg = self.app.cfg
        maxdim = int(cfg["viewer_res"] or 1280)
        settings = dict(self.app.thumbs.settings)
        if not keep_layers:
            self._fill_layers(e)
        li = self.layer_cb.currentIndex()
        if self._layers and 0 <= li < len(self._layers) and self._layers[li][1]:
            settings["channels"] = self._layers[li][1]
            settings["data"] = self._layers[li][2]
        src = None
        if e.kind == "seq":
            src = SeqSource(e, settings, maxdim)
        elif e.cat == "video":
            ffmpeg = find_tool(cfg["ffmpeg"], "ffmpeg")
            ffprobe = find_tool(cfg["ffmpeg"], "ffprobe")
            if not ffmpeg or not ffprobe:
                self.show_message(f"{e.name}\n\nPara reproducir videos poné ffmpeg.exe y ffprobe.exe en la carpeta "
                                  f"bin\\ de VFX Explorer (o indicá la ruta en ⚙ Configuración).")
                return
            try:
                info = probe_video(e.path, ffprobe)
            except Exception:
                info = None
            if not info:
                self.show_message(f"{e.name}\n\nNo se pudo leer el video.")
                return
            src = VideoSource(e.path, ffmpeg, info, maxdim)
        elif e.cat == "image" or (e.cat in ("model", "dir") and self.app.cfg["sidecar_previews"]):
            path = e.path
            if e.cat in ("model", "dir"):
                path = imaging.find_sidecar(e, self.app.thumbs.index)
            if path and imaging.can_decode(os.path.splitext(path)[1]):
                src = StillSource(path, settings, max(maxdim, 1600))
        if src is None:
            self.show_message(f"{e.name}\n\n" + ("Carpeta" if e.kind == "dir" else "Sin preview para este tipo"))
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
        if not self.n:
            self.lbl.setText("—")
            self.canvas.corner = ""
            return
        lab = self.labels[self.cur] if self.cur < len(self.labels) else self.cur + 1
        if self.n == 1:
            img = self.canvas.image
            txt = f"{img.width()}×{img.height()}" if img is not None else ""
            self.lbl.setText("imagen")
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
