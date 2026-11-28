# -*- coding: utf-8 -*-
"""Listar subcarpetas en otro hilo (para carpetas de red: un NAS que se está despertando puede tardar
varios segundos en contestar y la interfaz no tiene que trabarse)."""

import os
import threading
import time

from PySide6.QtCore import QObject, Signal, Qt, Slot, QTimer


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


class RemoteScan(QObject):
    """Poll Python futures on the owner thread; workers never touch Qt objects."""
    def __init__(self, owner):
        super().__init__(owner)
        self._job = None
        self._timer = QTimer(self, interval=15, timeout=self._poll)

    def cancel(self):
        job, self._job = self._job, None
        self._timer.stop()
        if job:
            for f in job[:2]:
                if f is not None:
                    f.cancel()

    def request(self, root, cache, scan, on_cache, on_done):
        from .scan_queue import cache_scans, pane_scans
        self.cancel()
        hit = cache_scans.submit('cache', cache, latest=True) if cache else None
        live = pane_scans.submit(root, scan, latest=True)
        self._job = [hit, live, on_cache, on_done]
        self._timer.start()

    def _poll(self):
        job = self._job
        if job is None:
            return
        hit, live, on_cache, on_done = job
        if hit is not None and hit.done():
            job[0] = None
            try:
                value = hit.result()
            except Exception:
                value = None
            if value is not None:
                on_cache(value)
        if self._job is not job:
            return
        if live.done() and (job[0] is None or live.exception() is None):
            self.cancel()
            try:
                value = live.result()
            except Exception as exc:
                on_done(None, str(exc) or type(exc).__name__)
            else:
                on_done(value, '')


class AsyncLister(QObject):
    done = Signal(str, object)          # authoritative result (or legacy cache presentation)
    cached = Signal(str, object)

    def __init__(self, parent=None, separate_cache=False):
        super().__init__(parent)
        self.busy = set()
        self._jobs = {}
        self._separate_cache = separate_cache
        self._timer = QTimer(self, interval=15, timeout=self._poll)

    def request(self, path, show_hidden=False):
        from .core import net_root, note_network_success, note_network_failure
        from .storage_cache import cached_dirs, save_dirs
        from .scan_queue import cache_scans, tree_scans
        if path in self.busy:
            return
        self.busy.add(path)
        remote = net_root(path)

        def work():
            try:
                names = list_subdirs(path, show_hidden)
            except Exception:
                names = None
            if remote and names is not None:
                save_dirs(path, show_hidden, names)
                note_network_success(path)
            elif remote:
                note_network_failure(path)
            return names

        hit = cache_scans.submit('cache', lambda: cached_dirs(path, show_hidden)) if remote else None
        live = tree_scans.submit(remote.casefold() if remote else 'local', work)
        self._jobs[path] = [hit, live]
        if not self._timer.isActive():
            self._timer.start()

    def cancel(self, path):
        job = self._jobs.pop(path, None)
        self.busy.discard(path)
        if job:
            for f in job:
                if f is not None:
                    f.cancel()
        if not self._jobs:
            self._timer.stop()

    def cancel_all(self):
        for path in list(self._jobs):
            self.cancel(path)

    def _poll(self):
        # NAS spin-up can release many directory reads at once. Spread GUI updates
        # across ticks instead of applying every completed tree result in one burst.
        deadline = time.perf_counter() + .008
        for path, job in list(self._jobs.items()):
            if time.perf_counter() >= deadline:
                break
            if self._jobs.get(path) is not job:
                continue
            hit, live = job
            if hit is not None and hit.done():
                job[0] = None
                try:
                    value = hit.result()
                except Exception:
                    value = None
                if value is not None:
                    (self.cached if self._separate_cache else self.done).emit(path, value)
            if self._jobs.get(path) is not job:
                continue
            if live.done() and (job[0] is None or (live.exception() is None and live.result() is not None)):
                self.cancel(path)
                try:
                    value = live.result()
                except Exception:
                    value = None
                self.done.emit(path, value)


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
