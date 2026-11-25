# -*- coding: utf-8 -*-
"""Listar subcarpetas en otro hilo (para carpetas de red: un NAS que se está despertando puede tardar
varios segundos en contestar y la interfaz no tiene que trabarse)."""

import os
import threading

from PySide6.QtCore import QObject, Signal


def list_subdirs(path, show_hidden=False):
    out = []
    try:
        with os.scandir(path) as sc:
            for d in sc:
                try:
                    if not d.is_dir():
                        continue
                    if not show_hidden:
                        if d.name.startswith((".", "$")):
                            continue
                        attrs = getattr(d.stat(follow_symlinks=False), "st_file_attributes", 0)
                        if attrs & 0x6:
                            continue
                except OSError:
                    continue
                out.append(d.name)
    except OSError:
        return []
    return sorted(out, key=str.lower)


class AsyncLister(QObject):
    done = Signal(str, list)          # ruta, subcarpetas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = set()

    def request(self, path, show_hidden=False):
        if path in self.busy:
            return
        self.busy.add(path)

        def work():
            names = list_subdirs(path, show_hidden)
            self.busy.discard(path)
            self.done.emit(path, names)
        threading.Thread(target=work, daemon=True).start()


def run_async(fn, callback, owner):
    """Corre fn() en otro hilo y llama callback(resultado) en el hilo de la interfaz."""
    class _S(QObject):
        sig = Signal(object)
    s = _S(owner)
    s.sig.connect(lambda r: (callback(r), s.deleteLater()))
    threading.Thread(target=lambda: s.sig.emit(fn()), daemon=True).start()
