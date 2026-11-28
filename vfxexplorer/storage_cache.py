"""Local last-known directory snapshots. No network IO in cache operations."""
import json
import os
import sqlite3
import threading
from dataclasses import asdict
from concurrent.futures import Future

_lock = threading.Lock()
_inflight = {}


def cache_home(data_path=None):
    # Derived data is disposable and must never follow a portable exe onto a share.
    from .core import app_dir, net_root
    if net_root(app_dir()) or (data_path and net_root(data_path)):
        for base in (os.environ.get('LOCALAPPDATA'), os.environ.get('TEMP'), os.environ.get('TMP'),
                     os.path.join(os.path.expanduser('~'), '.cache')):
            if base and not net_root(base):
                return os.path.join(base, 'VFX Explorer')
        raise OSError('No local cache location available')
    return None


def _db():
    from .core import data_dir
    d = cache_home()
    if not d:
        portable = data_dir()
        d = cache_home(portable) or portable
    os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(os.path.join(d, 'directory-cache.sqlite3'), timeout=2)
    con.execute('CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    return con


def _key(path, hidden, collapse):
    from . import core
    return json.dumps([core.norm_key(path), bool(hidden), bool(collapse), sorted(core.SEQ_LENGTHS),
                       sorted(k for k in core.SPLIT_SEQS if os.path.dirname(k.rsplit("|", 1)[0]) == core.norm_key(path)) if collapse else []], ensure_ascii=False)


def cached_entries(path, hidden=False, collapse=True):
    from .core import Entry, net_root
    if not net_root(path):
        return None
    try:
        with _db() as con:
            row = con.execute('SELECT payload FROM snapshots WHERE key=?', (_key(path, hidden, collapse),)).fetchone()
        return [Entry(**e) for e in json.loads(row[0])] if row else None
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        if 'con' in locals():
            con.close()


def save_entries(key, entries):
    try:
        with _db() as con:
            con.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?)', (key, json.dumps([asdict(e) for e in entries], ensure_ascii=False)))
    except (OSError, sqlite3.Error, ValueError, TypeError):
        pass
    finally:
        if 'con' in locals():
            con.close()


def scan_and_save(path, hidden=False, collapse=True):
    from . import core
    if not core.net_root(path):
        return core.scan_dir(path, hidden, collapse)
    key = _key(path, hidden, collapse)
    # Merge simultaneous scans of the same folder (tabs, live refresh, tags).
    with _lock:
        f = _inflight.get(key)
        leader = f is None
        if leader:
            f = _inflight[key] = Future()
    if not leader:
        import copy
        return copy.deepcopy(f.result())
    try:
        if core.net_root(path) in core.NET_FAKE_OFFLINE:
            raise OSError('Network temporarily unavailable')
        entries = core.scan_dir(path, hidden, collapse, strict=True)
        # Do not save under a stale grouping configuration.
        if key == _key(path, hidden, collapse):
            save_entries(key, entries)
        core.note_network_success(path)
        f.set_result(entries)
        return entries
    except Exception as exc:
        core.note_network_failure(path)
        f.set_exception(exc)
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)


def cached_dirs(path, hidden=False):
    from .core import norm_key
    try:
        with _db() as con:
            row = con.execute('SELECT payload FROM snapshots WHERE key=?', ('dirs:' + str(bool(hidden)) + ':' + norm_key(path),)).fetchone()
        return json.loads(row[0]) if row else None
    except (OSError, sqlite3.Error, ValueError):
        return None
    finally:
        if 'con' in locals():
            con.close()


def save_dirs(path, hidden, names):
    from .core import norm_key
    try:
        with _db() as con:
            con.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?)', ('dirs:' + str(bool(hidden)) + ':' + norm_key(path), json.dumps(names, ensure_ascii=False)))
    except (OSError, sqlite3.Error):
        pass
    finally:
        if 'con' in locals():
            con.close()
