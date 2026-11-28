"""Registro de cierres inesperados: VFXExplorer_data/crash.log.

El exe no tiene consola, así que si la app se cierra de golpe no queda rastro. Acá se anota:
- un cierre nativo (access violation en Qt, OpenImageIO, etc.) con la pila de todos los hilos (faulthandler);
- errores de Python no atrapados, en el hilo principal o en otros hilos;
- mensajes críticos o fatales de Qt;
- el cierre normal (así se distingue un cierre de golpe: un arranque sin su «exit» correspondiente).
"""
import os
import sys
import time
import threading
import traceback

_f = None
_lock = threading.Lock()
MAX_BYTES = 512 << 10


def _write(text):
    if _f is None:
        return
    with _lock:
        try:
            _f.write(text if text.endswith("\n") else text + "\n")
            _f.flush()
        except Exception:
            pass


def _stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def install(data_dir, version):
    global _f
    path = os.path.join(data_dir, "crash.log")
    try:
        if os.path.getsize(path) > MAX_BYTES:            # se queda con la última parte
            with open(path, "rb") as f:
                f.seek(-MAX_BYTES // 2, 2)
                tail = f.read()
            with open(path, "wb") as f:
                f.write(tail)
    except OSError:
        pass
    try:
        _f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    _write(f"\n=== start {_stamp()} · VFX Explorer {version} · pid {os.getpid()} ===")
    try:
        import faulthandler
        faulthandler.enable(_f, all_threads=True)
    except Exception:
        pass

    prev_hook = sys.excepthook

    def excepthook(t, v, tb):
        _write(f"--- {_stamp()} error no atrapado (hilo principal)\n" + "".join(traceback.format_exception(t, v, tb)))
        try:
            prev_hook(t, v, tb)
        except Exception:
            pass
    sys.excepthook = excepthook

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        _write(f"--- {_stamp()} error no atrapado (hilo {name})\n"
               + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thread_hook

    import atexit
    atexit.register(lambda: _write(f"=== exit {_stamp()} · pid {os.getpid()} ==="))
    return path


def install_qt():
    """Mensajes críticos / fatales de Qt (después de importar PySide6)."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return

    def handler(mode, ctx, msg):
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            kind = "FATAL" if mode == QtMsgType.QtFatalMsg else "critical"
            _write(f"--- {_stamp()} Qt {kind}: {msg}")
            if mode == QtMsgType.QtFatalMsg:
                _write("".join(traceback.format_stack()))
        elif sys.stderr is not None:                      # el resto, como siempre (consola al desarrollar)
            try:
                sys.stderr.write(msg + "\n")
            except Exception:
                pass
    qInstallMessageHandler(handler)
