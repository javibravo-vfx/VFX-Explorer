# -*- coding: utf-8 -*-
"""Abrir una imagen en la app predeterminada de Windows (Fotos, etc.) pasándole los archivos vecinos, como hace
el Explorador: así en el visor se puede pasar a la imagen siguiente / anterior de la carpeta.
Usa la API oficial Windows.System.Launcher con NeighboringFilesQuery (paquetes winrt-*). Si algo falla, se abre
como siempre (os.startfile)."""

import os
import threading

try:
    from winrt.windows.storage import StorageFile, StorageFolder
    from winrt.windows.storage.search import QueryOptions, CommonFileQuery
    from winrt.windows.system import Launcher, LauncherOptions
    HAS_WINRT = True
except Exception:          # Linux / sin los paquetes
    HAS_WINRT = False


def _launch(path, exts):
    import asyncio

    async def run():
        f = await StorageFile.get_file_from_path_async(path)
        folder = await StorageFolder.get_folder_from_path_async(os.path.dirname(path))
        q = folder.create_file_query_with_options(QueryOptions(CommonFileQuery.ORDER_BY_NAME, list(exts)))
        opts = LauncherOptions()
        opts.neighboring_files_query = q
        return await Launcher.launch_file_with_options_async(f, opts)

    return bool(asyncio.run(run()))


def open_with_neighbors(path, exts, fallback):
    """Lanza en un hilo (no traba la interfaz); `fallback(path)` se usa si no se pudo."""
    if not HAS_WINRT:
        fallback(path)
        return

    def work():
        try:
            ok = _launch(os.path.normpath(path), exts)
        except Exception:
            ok = False
        if not ok:
            fallback(path)

    threading.Thread(target=work, daemon=True).start()
