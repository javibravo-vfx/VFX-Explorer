#!/usr/bin/env python3
"""VFX Explorer — punto de entrada.  Uso: VFXExplorer.exe [carpeta]   |   VFXExplorer.exe --selftest"""
import os
import sys
import time

_T0 = time.perf_counter()
_MARKS = []


def _mark(name):
    _MARKS.append((name, time.perf_counter()))


def _process_age():
    """Segundos desde que Windows creó el proceso (incluye el arranque del exe y la carga de Python)."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        c, e, kk, u, now = (wintypes.FILETIME() for _ in range(5))
        if not k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kk),
                                 ctypes.byref(u)):
            return None
        k.GetSystemTimeAsFileTime(ctypes.byref(now))
        v = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
        return (v(now) - v(c)) / 1e7
    except Exception:
        return None


_AGE0 = _process_age()


def _write_timing(extra_print=False):
    """VFXExplorer_data/startup.log: cuánto tarda cada etapa del arranque."""
    lines = []
    if _AGE0 is not None:
        lines.append(f"{'exe + python start':28s} {_AGE0:6.2f} s")
    prev = _T0
    for name, t in _MARKS:
        lines.append(f"{name:28s} {t - prev:6.2f} s")
        prev = t
    total = (_MARKS[-1][1] - _T0 if _MARKS else 0) + (_AGE0 or 0)
    lines.append(f"{'TOTAL until usable':28s} {total:6.2f} s")
    txt = "\n".join(lines)
    try:
        from vfxexplorer.core import data_dir
        with open(os.path.join(data_dir(), "startup.log"), "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    except Exception:
        pass
    if extra_print:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "vfxexplorer_startup.log"), "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        try:
            print(txt)
        except Exception:
            pass


def selftest():
    """Chequeo rápido para CI: lee imágenes, genera thumbnails y abre la ventana. Exit code 0 = ok."""
    import time
    import tempfile
    import traceback
    log = []
    ok = True
    try:
        import numpy as np
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        app = QApplication(sys.argv[:1])
        from vfxexplorer import VERSION, imaging, core
        imaging.init_formats()
        log.append(f"VFX Explorer {VERSION} · OIIO={imaging.HAS_OIIO} · OIIO formats={len(imaging.OIIO_EXTS)}")
        tmp = tempfile.mkdtemp()
        if imaging.HAS_OIIO:
            import OpenImageIO as oiio
            for i in range(1001, 1004):
                p = os.path.join(tmp, f"plate.{i}.exr")
                arr = np.random.rand(64, 96, 4).astype(np.float32)
                o = oiio.ImageOutput.create(p)
                o.open(p, oiio.ImageSpec(96, 64, 4, "half"))
                o.write_image(arr)
                o.close()
        ents = core.scan_dir(tmp)
        log.append("entries: " + ", ".join(e.name for e in ents))
        settings = {"cs": "acescg", "chroma": True, "ffmpeg": None, "sidecar": True}
        for e in ents:
            img = imaging.load_thumbnail(e, settings, tmp, imaging.DirIndex())
            log.append(f"thumb {e.name}: {img.width()}x{img.height()}")
            ok = ok and not img.isNull()
        # video: con el ffmpeg incluido en bin\ (en CI es obligatorio: --require-ffmpeg)
        ffmpeg = core.find_tool(None, "ffmpeg")
        ffprobe = core.find_tool(None, "ffprobe")
        log.append(f"ffmpeg: {ffmpeg or '-'} · ffprobe: {ffprobe or '-'}")
        if "--require-ffmpeg" in sys.argv and not (ffmpeg and ffprobe):
            ok = False
            log.append("ffmpeg/ffprobe missing in bin\\")
        if ffmpeg and ffprobe:
            import subprocess
            vdir = tempfile.mkdtemp()
            mp4 = os.path.join(vdir, "test.mp4")
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                            "-t", "1", "-c:v", "mpeg4", mp4], timeout=60, creationflags=imaging.NO_WINDOW)
            vimg = imaging.video_thumb(mp4, ffmpeg)
            info = dict(imaging.video_info(mp4, ffprobe))
            log.append(f"video thumb: {vimg.width()}x{vimg.height()} · info: {info.get('Resolution', info)}")
            ok = ok and not vimg.isNull()
        # PDF (pypdfium2 incluido en el exe)
        try:
            import pypdfium2 as pdfium
            pdf = os.path.join(tempfile.mkdtemp(), "test.pdf")
            doc = pdfium.PdfDocument.new()
            doc.new_page(400, 300)
            doc.save(pdf)
            doc.close()
            pimg = imaging.pdf_render(pdf, 0, 200)
            log.append(f"pdf render: {pimg.width()}x{pimg.height()}")
            ok = ok and not pimg.isNull()
        except Exception as ex:
            ok = False
            log.append(f"pdf: {ex}")
        from vfxexplorer.mainwindow import MainWindow
        w = MainWindow(tmp)
        w.show()
        seq = [e for e in ents if e.kind == "seq"]
        if seq:
            w.set_mode("library")
            w.libpage.viewer.load(seq[0])
        t0 = time.time()
        frames = {"n": 0}

        def poll():
            v = w.libpage.viewer
            n = v.thread.cached_count() if v.thread else 0
            frames["n"] = max(frames["n"], n)
            if ((not seq or n >= 1) and time.time() - t0 > 1.0) or time.time() - t0 > 12:
                app.quit()
            else:
                QTimer.singleShot(200, poll)
        QTimer.singleShot(200, poll)
        app.exec()
        if seq:
            v = w.libpage.viewer
            got = frames["n"]
            log.append(f"viewer: {got}/{v.n} frames decoded")
            ok = ok and got >= 1
        w.close()
        log.append("window ok")
    except Exception:
        ok = False
        log.append(traceback.format_exc())
    log.append("SELFTEST " + ("OK" if ok else "FAILED"))
    out = os.path.join(tempfile.gettempdir(), "vfxexplorer_selftest.log")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    try:
        print("\n".join(log))
    except Exception:
        pass
    return 0 if ok else 1


def main():
    if "--nas-selftest" in sys.argv:
        from vfxexplorer.nas_selftest import run
        sys.exit(run())
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("javibravo-vfx.vfxexplorer")
        except Exception:
            pass
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    _mark("import Qt")
    app = QApplication(sys.argv)
    app.setApplicationName("VFX Explorer")
    _mark("QApplication")
    for mod in ("numpy", "OpenImageIO", "pypdfium2"):
        try:
            __import__(mod)
        except Exception:
            pass
        _mark(f"import {mod}")
    from vfxexplorer.widgets import apply_dark
    from vfxexplorer.mainwindow import MainWindow
    _mark("import app modules")
    apply_dark(app)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    timing = "--startup-timing" in sys.argv
    prof = None
    if timing:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    w = MainWindow(args[0] if args else None)
    if prof:
        prof.disable()
    _mark("build window")
    w.show()
    _mark("show")

    def ready():
        _mark("first paint / idle")
        _write_timing(timing)
        if prof:
            import io
            import pstats
            out = io.StringIO()
            pstats.Stats(prof, stream=out).sort_stats("cumulative").print_stats(30)
            import tempfile
            with open(os.path.join(tempfile.gettempdir(), "vfxexplorer_startup.log"), "a", encoding="utf-8") as f:
                f.write("\n" + out.getvalue())
        if timing:
            QTimer.singleShot(300, w.close)
    QTimer.singleShot(0, ready)
    sys.exit(app.exec())


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
