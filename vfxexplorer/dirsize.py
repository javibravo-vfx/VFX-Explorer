# -*- coding: utf-8 -*-
"""Tamaño de carpetas en segundo plano (opcional, se activa en Configuración)."""

import os
import time

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool


def folder_size(path, deadline=None):
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for de in it:
                    try:
                        if de.is_dir(follow_symlinks=False):
                            stack.append(de.path)
                        else:
                            total += de.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
        if deadline and time.time() > deadline:
            return total, False
    return total, True


class _Sig(QObject):
    done = Signal(str, object, bool)


class _Task(QRunnable):
    def __init__(self, path, sig):
        super().__init__()
        self.path, self.sig = path, sig

    def run(self):
        size, complete = folder_size(self.path, deadline=time.time() + 120)
        self.sig.done.emit(self.path, size, complete)


class DirSizeManager(QObject):
    ready = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.cache = {}
        self.pending = set()
        self.sig = _Sig()
        self.sig.done.connect(self._done)

    def get(self, path):
        return self.cache.get(path)

    def request(self, path):
        if path in self.cache or path in self.pending:
            return
        self.pending.add(path)
        self.pool.start(_Task(path, self.sig))

    def _done(self, path, size, complete):
        self.pending.discard(path)
        self.cache[path] = size
        self.ready.emit(path, size)

    def clear(self):
        self.pool.clear()
        self.pending.clear()
        self.cache.clear()
