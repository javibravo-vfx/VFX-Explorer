#!/usr/bin/env python3
"""VFX Explorer — punto de entrada.  Uso: VFXExplorer.exe [carpeta]   |   VFXExplorer.exe --selftest"""
import os
import sys


def selftest():
    """Chequeo rápido para CI: lee imágenes, genera thumbnails y abre la ventana. Exit code 0 = ok."""
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
        log.append(f"VFX Explorer {VERSION} · OIIO={imaging.HAS_OIIO} · formatos OIIO={len(imaging.OIIO_EXTS)}")
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
        log.append("entradas: " + ", ".join(e.name for e in ents))
        settings = {"cs": "acescg", "chroma": True, "ffmpeg": None, "sidecar": True}
        for e in ents:
            img = imaging.load_thumbnail(e, settings, tmp, imaging.DirIndex())
            log.append(f"thumb {e.name}: {img.width()}x{img.height()}")
            ok = ok and not img.isNull()
        from vfxexplorer.mainwindow import MainWindow
        w = MainWindow(tmp)
        w.show()
        QTimer.singleShot(1500, app.quit)
        app.exec()
        w.close()
        log.append("ventana ok")
    except Exception:
        ok = False
        log.append(traceback.format_exc())
    log.append("SELFTEST " + ("OK" if ok else "FALLÓ"))
    out = os.path.join(tempfile.gettempdir(), "vfxexplorer_selftest.log")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    try:
        print("\n".join(log))
    except Exception:
        pass
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("javibravo-vfx.vfxexplorer")
        except Exception:
            pass
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("VFX Explorer")
    from vfxexplorer.widgets import apply_dark
    from vfxexplorer.mainwindow import MainWindow
    apply_dark(app)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    w = MainWindow(args[0] if args else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
