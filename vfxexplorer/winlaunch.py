# -*- coding: utf-8 -*-
"""Abrir una imagen en la app predeterminada de Windows (Fotos, etc.) pasándole los archivos vecinos, como hace
el Explorador: así en el visor se puede pasar a la imagen siguiente / anterior de la carpeta.

Usa la API oficial Windows.System.Launcher con NeighboringFilesQuery (paquetes winrt-*). Esa llamada tiene que
hacerse desde el hilo de la interfaz (STA): el archivo y la consulta de la carpeta se preparan en otro hilo y el
lanzamiento se dispara en el hilo principal sin esperar (se revisa el resultado con un timer). Si algo falla, se
abre como siempre (os.startfile). Lo que pasa queda en VFXExplorer_data/launch.log."""

import os
import threading
import time
import traceback

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from winrt.windows.storage import StorageFile, StorageFolder
    from winrt.windows.storage.search import QueryOptions, CommonFileQuery
    from winrt.windows.system import Launcher, LauncherOptions
    HAS_WINRT = True
except Exception:          # Linux / sin los paquetes
    HAS_WINRT = False

PHOTO_VIEWER = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Photo Viewer",
                            "PhotoViewer.dll")


class NeighborLauncher(QObject):
    _ready = Signal(object, object, str, object)     # StorageFile, query, ruta, fallback

    def __init__(self, log_path=None):
        super().__init__()
        self.log_path = log_path
        self._ready.connect(self._launch_ui)
        self._ops = []

    def log(self, msg):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
        except OSError:
            pass

    def open(self, path, exts, fallback):
        if not HAS_WINRT:
            self.log(f"winrt not available → default open: {path}")
            fallback(path)
            return
        path = os.path.normpath(path)

        def prepare():
            import asyncio

            async def run():
                f = await StorageFile.get_file_from_path_async(path)
                folder = await StorageFolder.get_folder_from_path_async(os.path.dirname(path))
                q = folder.create_file_query_with_options(QueryOptions(CommonFileQuery.ORDER_BY_NAME, list(exts)))
                return f, q
            try:
                f, q = asyncio.run(run())
            except Exception:
                self.log("prepare failed:\n" + traceback.format_exc())
                f = q = None
            self._ready.emit(f, q, path, fallback)

        threading.Thread(target=prepare, daemon=True).start()

    def _launch_ui(self, f, q, path, fallback):
        """En el hilo principal: lanzar sin bloquear y revisar el resultado."""
        if f is None:
            fallback(path)
            return
        try:
            opts = LauncherOptions()
            opts.neighboring_files_query = q
            op = Launcher.launch_file_with_options_async(f, opts)
        except Exception:
            self.log("launch failed:\n" + traceback.format_exc())
            fallback(path)
            return
        t0 = time.time()
        holder = {"op": op, "f": f, "q": q}
        self._ops.append(holder)

        def check():
            try:
                st = int(op.status)          # 0 started · 1 completed · 2 canceled · 3 error
            except Exception:
                st = 3
            if st == 0 and time.time() - t0 < 15:
                QTimer.singleShot(150, check)
                return
            self._ops.remove(holder)
            ok = False
            if st == 1:
                try:
                    ok = bool(op.get_results())
                except Exception:
                    ok = False
            self.log(f"launch with neighbors: status={st} ok={ok} · {path}")
            if not ok:
                fallback(path)
        QTimer.singleShot(100, check)


def open_photo_viewer(path):
    """Visualizador de fotos clásico de Windows: recorre solo las imágenes de la carpeta."""
    import subprocess
    if not os.path.isfile(PHOTO_VIEWER):
        return False
    subprocess.Popen(["rundll32.exe", f"{PHOTO_VIEWER},ImageView_Fullscreen", os.path.normpath(path)])
    return True
