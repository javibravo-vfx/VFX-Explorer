"""Isolate native network decoders from the GUI process, including their GIL.

Each role gets one persistent worker on demand, a second only for concurrent work.
A timed-out slot is retired independently; local media never uses IPC.
"""
import atexit
import multiprocessing as mp
import threading
import time
import os
from multiprocessing import shared_memory

_child = False
_slots = {"preview": [], "foreground": []}
_lock = threading.Lock()
_closed = False
_TIMEOUT = 90.0
_MAX_PER_ROLE = 2
_MAX_IDLE = 4
_SHM_LIMIT = 256 << 20
_SHM_TOTAL = 512 << 20
_shm_reserved = 0
_shm_lock = threading.Lock()
_shm_transfers = 0


def decode_path(path):
    if _child:
        return path
    from .storage import native_read_path
    physical = native_read_path(path)
    if physical != path:
        # leído directo del disco local: si es un HDD dormido, que arranque sin tomar el GIL
        from .imaging import warm_disk
        warm_disk(physical, path)
    return physical


def _reserve_buffer(maxdim):
    # RGB + alpha float32, bounded across all concurrent calls. Parent owns it.
    global _shm_reserved
    size = int(maxdim) ** 2 * 16
    if size <= 0 or size > _SHM_LIMIT:
        return None
    with _shm_lock:
        if _shm_reserved + size > _SHM_TOTAL:
            return None
        if os.name != "nt":
            # /dev/shm is often small in containers; avoid SIGBUS on first write.
            try:
                if size + _shm_reserved > int(os.statvfs("/dev/shm").f_bavail * os.statvfs("/dev/shm").f_frsize * .75):
                    return None
            except OSError:
                return None
        try:
            buf = shared_memory.SharedMemory(create=True, size=size)
        except (OSError, ValueError, MemoryError):
            return None
        _shm_reserved += size
        return buf


def _release_buffer(buf):
    global _shm_reserved
    size = buf.size
    try:
        buf.close()
        try:
            buf.unlink()
        except FileNotFoundError:
            pass
    finally:
        with _shm_lock:
            _shm_reserved -= size


def _pack_linear(result, buffer_name):
    if result is None or not buffer_name:
        return result
    import numpy as np
    arrays = [None if a is None else np.asarray(a) for a in result]
    try:
        buf = shared_memory.SharedMemory(name=buffer_name)
    except (OSError, ValueError):
        return result
    try:
        if sum(a.nbytes for a in arrays if a is not None) > buf.size:
            return result
        offset, desc = 0, []
        for a in arrays:
            if a is None:
                desc.append(None)
                continue
            target = np.ndarray(a.shape, dtype=a.dtype, buffer=buf.buf, offset=offset)
            np.copyto(target, a)
            del target
            desc.append((a.shape, a.dtype.str, offset))
            offset += a.nbytes
        return ("vfx-shm-v1", desc)
    finally:
        buf.close()


def _unpack_linear(value, buf):
    global _shm_transfers
    if not (buf is not None and isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) and value[0] == "vfx-shm-v1"):
        return value
    import numpy as np
    out = tuple(None if d is None else np.ndarray(d[0], dtype=np.dtype(d[1]), buffer=buf.buf, offset=d[2]).copy() for d in value[1])
    with _shm_lock:
        _shm_transfers += 1
    return out


def shared_transfers():
    with _shm_lock:
        return _shm_transfers


def _init():
    global _child, _qt_app
    _child = True
    from PySide6.QtCore import QCoreApplication
    _qt_app = QCoreApplication.instance() or QCoreApplication([])
    from . import imaging
    imaging.init_formats()


def _execute(module, name, args, buffer_name=None):
    from importlib import import_module
    result = getattr(import_module(module), name)(*args)
    if name == 'hdr_linear':
        return _pack_linear(result, buffer_name)
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
        self.last_used = time.monotonic()
        self.retired = threading.Event()


def _acquire(role):
    with _lock:
        if _closed:
            raise OSError('Network decoder is shutting down')
        slots = _slots.setdefault(role, [])
        slot = min(slots, key=lambda s: s.jobs) if slots else None
        if slot is None or (slot.jobs and len(slots) < _MAX_PER_ROLE):
            slot = _Slot()
            slots.append(slot)
        slot.jobs += 1
        return slot


def _prune_idle():
    # Active roots never wait for another root's process budget. Bound idle retention.
    with _lock:
        idle = sorted(((slot.last_used, group, slot) for group, slots in _slots.items()
                       for slot in slots if slot.jobs == 0), key=lambda x: x[0])
        old = idle[:max(0, len(idle) - _MAX_IDLE)]
        for _, group, slot in old:
            _slots[group].remove(slot)
            slot.retired.set()
    for _, _, slot in old:
        slot.pool.terminate()
        slot.pool.join()


def _retire(role, slot):
    with _lock:
        if slot not in _slots[role]:
            return
        _slots[role].remove(slot)
        slot.retired.set()
    # Do not hold the global lock while killing native processes.
    slot.pool.terminate()
    slot.pool.join()


def call(module, name, args, preview=False, *, _timeout=None, storage=None):
    from .storage import queue_key
    base = 'preview' if preview else 'foreground'
    if storage is None and name in ('hdr_linear', 'oiio_thumb', 'oiio_info', 'exr_layers', 'read_image_meta'):
        storage = args[0]
    key = queue_key(storage) if storage else None
    role = (base, key) if key else base
    slot = _acquire(role)
    buf = None
    try:
        if name == 'hdr_linear':
            buf = _reserve_buffer(args[2])
        if slot.retired.is_set():
            raise OSError('Network decoder stopped')
        try:
            pending = slot.pool.apply_async(_execute, (module, name, args, buf.name if buf else None))
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
                if name == "hdr_linear":
                    value = _unpack_linear(value, buf)
                break
            except mp.TimeoutError:
                continue
    finally:
        try:
            if buf is not None:
                _release_buffer(buf)
        finally:
            with _lock:
                slot.jobs -= 1
                slot.last_used = time.monotonic()
            _prune_idle()
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
        return {base: sum(len(slots) for role, slots in _slots.items() if (role[0] if isinstance(role, tuple) else role) == base) for base in ("preview", "foreground")}


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
