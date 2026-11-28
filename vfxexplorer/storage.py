"""Storage routing. Logical paths remain the identity for all app data.

A mapped SMB path remains network-sensitive for directory/UI operations. Only
native read-only decodes may use a verified equivalent local file. Never use a
remembered mapping as proof of a currently connected local share.
"""
import os
import ntpath
import re
import sys
import time
import threading
from functools import lru_cache

IS_WIN = sys.platform.startswith('win')
_drive_cache = {}
_nonlocal_mappings = {}
_TTL = 5.0


def _drive_type(letter):
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(letter + '\\')


def _remembered(letter):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Network\\' + letter[0]) as key:
            return winreg.QueryValueEx(key, 'RemotePath')[0]
    except OSError:
        return None


def drive_remote(letter):
    now = time.monotonic()
    hit = _drive_cache.get(letter)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        kind = _drive_type(letter)
        remote = kind == 4 or (kind in (0, 1) and bool(_remembered(letter)))
    except Exception:
        # Unknown Windows drive: keep the safe path, not a direct native decode.
        remote = True
    _drive_cache[letter] = (now, remote)
    return remote


def unc_parts(path):
    p = str(path or '').replace('/', '\\')
    if p.lower().startswith('\\\\?\\unc\\'):
        p = '\\\\' + p[8:]
    if not p.startswith('\\\\') or p.startswith(('\\\\?\\', '\\\\.\\')):
        return None
    parts = p[2:].split('\\')
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1], '\\'.join(parts[2:])


def network_root(path):
    p = str(path or '')
    parts = unc_parts(p)
    if parts:
        return '\\\\' + '\\'.join(parts[:2])
    if IS_WIN:
        p = p.replace('/', '\\')
        if p.startswith('\\\\?\\'):
            p = p[4:]
        if len(p) >= 2 and p[1] == ':' and p[0].isalpha():
            letter = p[:2].upper()
            return letter if drive_remote(letter) else None
    return None


def queue_key(path):
    from .core import net_root
    root = net_root(path)
    return root.casefold() if root else None


@lru_cache(maxsize=1)
def local_names():
    """Only exact local names/loopback; no DNS or network probes."""
    names = {'localhost', '127.0.0.1', '::1', '0000--1.ipv6-literal.net'}
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        for fmt in (0, 3, 4, 7):  # NetBIOS/FQDN, physical and virtual names
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(len(buf))
            if ctypes.windll.kernel32.GetComputerNameExW(fmt, buf, ctypes.byref(n)):
                names.add(buf.value.casefold().rstrip('.'))
    return frozenset(names)


def _mapped_unc(letter):
    """Current mapping (not HKCU remembered state). Called only on read workers."""
    import ctypes
    from ctypes import wintypes
    buf = ctypes.create_unicode_buffer(32768)
    n = wintypes.DWORD(len(buf))
    if ctypes.windll.mpr.WNetGetConnectionW(letter, buf, ctypes.byref(n)) == 0:
        return buf.value
    return None


def _share_path(share):
    # Read local server configuration only; no remote RPC or elevation.
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SYSTEM\CurrentControlSet\Services\LanmanServer\Shares') as key:
            values, _ = winreg.QueryValueEx(key, share)
        for value in values:
            if value.lower().startswith('path='):
                return value[5:]
    except OSError:
        pass
    # Volatile shares may not be in the registry. Ask only the local service.
    try:
        import ctypes
        from ctypes import wintypes
        class ShareInfo2(ctypes.Structure):
            _fields_ = [("name", wintypes.LPWSTR), ("type", wintypes.DWORD),
                        ("remark", wintypes.LPWSTR), ("permissions", wintypes.DWORD),
                        ("max_uses", wintypes.DWORD), ("current_uses", wintypes.DWORD),
                        ("path", wintypes.LPWSTR), ("passwd", wintypes.LPWSTR)]
        buf = ctypes.c_void_p()
        api = ctypes.windll.netapi32
        api.NetShareGetInfo.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        api.NetApiBufferFree.argtypes = [ctypes.c_void_p]
        try:
            if api.NetShareGetInfo(None, share, 2, ctypes.byref(buf)) == 0 and buf.value:
                info = ctypes.cast(buf, ctypes.POINTER(ShareInfo2)).contents
                return info.path if info.type & 0xff == 0 else None
        finally:
            if buf.value:
                api.NetApiBufferFree(buf)
    except (OSError, AttributeError, ImportError):
        pass
    return None


def local_candidate(path):
    """Resolve a local SMB candidate; not yet proof of file equivalence."""
    if not IS_WIN:
        return None
    p = str(path).replace('/', '\\')
    if not unc_parts(p):
        if p.startswith('\\\\?\\'):
            p = p[4:]
        drive, tail = ntpath.splitdrive(p)
        if len(drive) != 2 or not tail.startswith('\\') or not drive_remote(drive.upper()):
            return None
        letter = drive.upper()
        now = time.monotonic()
        if now - _nonlocal_mappings.get(letter, -float('inf')) < _TTL:
            return None
        mapped = _mapped_unc(letter)
        parts = unc_parts(mapped)
        if not parts or parts[0].casefold().rstrip('.') not in local_names():
            _nonlocal_mappings[letter] = now
            return None
        p = mapped.rstrip('\\') + tail
    parts = unc_parts(p)
    if not parts or parts[0].casefold().rstrip('.') not in local_names():
        return None
    _, share, tail = parts
    base = _share_path(share)
    if not base:
        return None
    base = ntpath.normpath(base)
    drive, rest = ntpath.splitdrive(base)
    if len(drive) != 2 or not rest.startswith('\\') or _drive_type(drive.upper()) != 3:
        return None
    # Reject traversal, ADS and absolute components. Keep identity unchanged.
    if any(x in ('.', '..') or ':' in x for x in tail.split('\\')):
        return None
    return ntpath.join(base, tail)


def _fixed_final_path(path):
    """Do not route a fixed-drive junction to a remote filesystem."""
    final = os.path.realpath(path, strict=True)
    if final.startswith('\\\\?\\') and not unc_parts(final):
        final = final[4:]
    drive, tail = ntpath.splitdrive(final)
    if len(drive) == 2 and tail.startswith('\\') and _drive_type(drive.upper()) == 3:
        return final
    return None


def _file_id(f):
    import ctypes
    import msvcrt
    from ctypes import wintypes
    class FileIdInfo(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_ulonglong), ("id", ctypes.c_ubyte * 16)]
    data = FileIdInfo()
    api = ctypes.windll.kernel32.GetFileInformationByHandleEx
    api.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    if api(msvcrt.get_osfhandle(f.fileno()), 18, ctypes.byref(data), ctypes.sizeof(data)):
        return (data.volume, bytes(data.id)) if any(data.id) else None
    return None


def _same_file(a, b):
    sa, sb = os.fstat(a.fileno()), os.fstat(b.fileno())
    if sa.st_ino and sb.st_ino and os.path.samestat(sa, sb):
        return True
    try:
        aid, bid = _file_id(a), _file_id(b)
        return aid is not None and aid == bid
    except (OSError, AttributeError, ImportError):
        return False


def native_read_path(path):
    """Physical path only after a successful SMB access and identical file ID.

    Never rewrite file operations, tags, or config. If Windows does not expose
    equivalent IDs, permissions differ, or mapping is unavailable, isolate.
    """
    from .core import net_root
    if not net_root(path) or not IS_WIN:
        return path
    # No blocking mapping lookup or stat on the GUI thread.
    if threading.current_thread() is threading.main_thread():
        return path
    try:
        candidate = local_candidate(path)
        if not candidate:
            return path
        candidate = _fixed_final_path(candidate)
        if not candidate:
            return path
        # Opening original also honors share-level access restrictions.
        with open(path, 'rb') as original, open(candidate, 'rb') as local:
            if _same_file(original, local):
                return candidate
    except (OSError, ValueError, TypeError, ImportError, AttributeError):
        pass
    return path


class RootPools:
    """Lazy per-network-root Qt queues; physical local keeps its existing pool."""
    def __init__(self, local, owner, threads):
        self.local, self.owner, self.threads = local, owner, threads
        self.remote = {}

    def for_path(self, path):
        key = queue_key(path)
        if not key:
            return self.local
        if key not in self.remote:
            from PySide6.QtCore import QThreadPool
            pool = QThreadPool(self.owner)
            pool.setMaxThreadCount(self.threads)
            self.remote[key] = pool
        return self.remote[key]

    def clear(self):
        self.local.clear()
        for pool in self.remote.values():
            pool.clear()
