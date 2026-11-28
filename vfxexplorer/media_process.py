"""Isolate native network decoders from the GUI process, including their GIL.

Each role gets one persistent worker on demand, a second only for concurrent work.
A timed-out slot is retired independently; local media never uses IPC.
"""
import atexit
import multiprocessing as mp
import threading
import time

_child = False
_slots = {"preview": [], "foreground": []}
_lock = threading.Lock()
_closed = False
_TIMEOUT = 90.0
_MAX_PER_ROLE = 2


def _init():
    global _child, _qt_app
    _child = True
    from PySide6.QtCore import QCoreApplication
    _qt_app = QCoreApplication.instance() or QCoreApplication([])
    from . import imaging
    imaging.init_formats()


def _execute(module, name, args):
    from importlib import import_module
    result = getattr(import_module(module), name)(*args)
    if name == 'oiio_thumb':
        from PySide6.QtGui import QImage
        if result.isNull():
            return None
        img = result.convertToFormat(QImage.Format_RGBA8888)
        return (img.width(), img.height(), img.bytesPerLine(), bytes(img.constBits()))
    return result


def isolated(path):
    from .core import net_root
    return not _child and bool(net_root(path))


class _Slot:
    def __init__(self):
        self.pool = mp.get_context('spawn').Pool(1, initializer=_init)
        self.jobs = 0
        self.retired = threading.Event()


def _acquire(role):
    with _lock:
        if _closed:
            raise OSError('Network decoder is shutting down')
        slots = _slots[role]
        slot = min(slots, key=lambda s: s.jobs) if slots else None
        if slot is None or (slot.jobs and len(slots) < _MAX_PER_ROLE):
            slot = _Slot()
            slots.append(slot)
        slot.jobs += 1
        return slot


def _retire(role, slot):
    with _lock:
        if slot not in _slots[role]:
            return
        _slots[role].remove(slot)
        slot.retired.set()
    # Do not hold the global lock while killing native processes.
    slot.pool.terminate()
    slot.pool.join()


def call(module, name, args, preview=False, *, _timeout=None):
    role = 'preview' if preview else 'foreground'
    slot = _acquire(role)
    try:
        if slot.retired.is_set():
            raise OSError('Network decoder stopped')
        try:
            pending = slot.pool.apply_async(_execute, (module, name, args))
        except (ValueError, OSError) as exc:
            raise OSError('Network decoder stopped') from exc
        deadline = time.monotonic() + (_TIMEOUT if _timeout is None else _timeout)
        while True:
            if slot.retired.is_set():
                raise OSError('Network decoder stopped')
            left = deadline - time.monotonic()
            if left <= 0:
                _retire(role, slot)
                raise OSError('Network decoder timed out')
            try:
                value = pending.get(timeout=min(left, .1))
                break
            except mp.TimeoutError:
                continue
    finally:
        with _lock:
            slot.jobs -= 1
    if name == 'oiio_thumb':
        from PySide6.QtGui import QImage
        if value is None:
            return QImage()
        w, h, stride, data = value
        return QImage(data, w, h, stride, QImage.Format_RGBA8888).copy()
    return value


def worker_counts():
    """Diagnostic: logical active worker slots by role; no process startup."""
    with _lock:
        return {role: len(slots) for role, slots in _slots.items()}


@atexit.register
def shutdown():
    global _closed
    with _lock:
        _closed = True
        slots = [slot for group in _slots.values() for slot in group]
        for group in _slots.values():
            group.clear()
        for slot in slots:
            slot.retired.set()
    for slot in slots:
        slot.pool.terminate()
        slot.pool.join()
