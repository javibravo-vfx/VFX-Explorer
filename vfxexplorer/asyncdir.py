# -*- coding: utf-8 -*-
"""Listar subcarpetas en otro hilo (para carpetas de red: un NAS que se está despertando puede tardar
varios segundos en contestar y la interfaz no tiene que trabarse)."""

import os
import threading

from PySide6.QtCore import QObject, Signal, Qt, Slot


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
                    return None
                out.append(d.name)
    except OSError:
        return None
    return sorted(out, key=str.lower)


class AsyncLister(QObject):
    done = Signal(str, object)          # ruta, subcarpetas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = set()

    def request(self, path, show_hidden=False):
        if path in self.busy:
            return
        self.busy.add(path)

        def work():
            from .core import net_root, note_network_success, note_network_failure
            from .storage_cache import cached_dirs, save_dirs
            remote = net_root(path)
            if remote:
                hit = cached_dirs(path, show_hidden)
                if hit is not None:
                    try:
                        self.done.emit(path, hit)
                    except RuntimeError:
                        self.busy.discard(path)
                        return
            try:
                names = list_subdirs(path, show_hidden)
                if remote and names is not None:
                    save_dirs(path, show_hidden, names)
                    note_network_success(path)
                elif remote:
                    note_network_failure(path)
            finally:
                self.busy.discard(path)
            try:
                self.done.emit(path, names)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()


class _AsyncResult(QObject):
    sig = Signal(object)

    def __init__(self, owner, callback):
        super().__init__(owner)
        self.callback = callback
        self.sig.connect(self.deliver, Qt.QueuedConnection)

    @Slot(object)
    def deliver(self, result):
        try:
            self.callback(result)
        finally:
            self.deleteLater()


def run_async(fn, callback, owner):
    """Compute on a daemon worker; explicitly marshal results to the Qt owner thread."""
    s = _AsyncResult(owner, callback)
    def work():
        try:
            result = fn()
        except Exception:
            result = None
        try:
            s.sig.emit(result)
        except RuntimeError:
            pass
    threading.Thread(target=work, daemon=True).start()
