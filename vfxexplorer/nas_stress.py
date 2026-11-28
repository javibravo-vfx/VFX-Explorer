"""Prueba de estrés de navegación con un NAS que se duerme y se despierta (para el exe en GitHub Windows).

    VFXExplorer.exe --nas-stress [semilla] [pasos]

Arma ~150 carpetas con fotos, EXR, HDR y una secuencia EXR en una carpeta temporal marcada como «red»
(NET_FAKE_ROOTS: listados, thumbnails y decodificadores siguen el camino del NAS, con procesos aislados),
y simula un NAS con discos que se duermen: la primera lectura después de un rato espera WAKE segundos
(todas las que llegan mientras tanto esperan lo mismo) y después responde normal hasta volver a dormirse.

Mientras tanto, la app real (MainWindow) recibe acciones al azar: navegar en la VFX Library y en File
Explorer, expandir y colapsar el árbol, clic en el árbol, seleccionar archivos (visor / Details), pestañas,
cambiar de modo, refrescar, volver atrás. El crash.log (faulthandler) queda en %TEMP%/vfx_nas_stress/.

Sale con 0 y «NAS STRESS OK» si la app sobrevive y la ventana no se trabó más de MAX_GAP segundos.
No toca la configuración del usuario: usa VFXExplorer_data del exe que corre la prueba (CI).
"""
import os
import random
import sys
import tempfile
import threading
import time
import traceback

WAKE = 4.0          # lo que tardan los discos en arrancar
AWAKE = 10.0        # despiertos hasta volver a dormirse (sin uso)
MAX_GAP = 5.0       # la ventana no puede quedar trabada más que esto


class FakeNas:
    def __init__(self, root):
        self.root = os.path.normcase(os.path.normpath(root))
        self._lock = threading.Lock()
        self.awake_until = 0.0          # arranca dormido
        self.wake_end = 0.0
        self.wakeups = 0
        self.waits = 0

    def sleep(self):
        """Los discos se duermen ya (para repetir muchas veces el arranque mientras se navega)."""
        with self._lock:
            if time.monotonic() >= self.wake_end:
                self.awake_until = 0.0

    def mine(self, path):
        try:
            p = os.path.normcase(os.path.normpath(str(path)))
        except Exception:
            return False
        return p == self.root or p.startswith(self.root + os.sep)

    def touch(self, path):
        """Una lectura del NAS: si los discos duermen, espera a que arranquen (fuera del GIL, como una lectura real)."""
        if not self.mine(path):
            return
        with self._lock:
            now = time.monotonic()
            if now >= self.awake_until and now >= self.wake_end:
                self.wake_end = now + WAKE * random.uniform(.5, 1.5)   # empieza a despertarse
                self.wakeups += 1
            wait = self.wake_end - now
            self.awake_until = max(self.awake_until, self.wake_end) + AWAKE
            if wait > 0:
                self.waits += 1
        if wait > 0:
            time.sleep(wait)


def _fixture(base):
    import numpy as np
    from PySide6.QtGui import QImage, QColor
    import OpenImageIO as oiio
    rnd = random.Random(7)
    tops = ["Assets 3D", "Surfaces Textures", "Lighting", "VFX Stock Elements", "Reference", "Mocap"]
    folders = []
    rgb = np.linspace(.02, 2.0, 96 * 48 * 3, dtype=np.float32).reshape(48, 96, 3)
    for t in tops:
        for i in range(5):
            for j in range(4):
                d = os.path.join(base, t, f"{t.split()[0]}_{i:02d}", f"take_{j}")
                os.makedirs(d, exist_ok=True)
                folders.append(d)
                for k in range(4):
                    im = QImage(320, 200, QImage.Format_RGB32)
                    im.fill(QColor(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
                    im.save(os.path.join(d, f"img_{k}.jpg"))
                if (i + j) % 3 == 0:
                    for name, n in (("plate.exr", 1), ("sky.hdr", 1)):
                        out = oiio.ImageOutput.create(name)
                        out.open(os.path.join(d, name), oiio.ImageSpec(96, 48, 3, "float"))
                        out.write_image(rgb)
                        out.close()
                if (i + j) % 4 == 1:
                    for f in range(1001, 1006):
                        out = oiio.ImageOutput.create("exr")
                        out.open(os.path.join(d, f"shot_{f}.exr"), oiio.ImageSpec(96, 48, 3, "half"))
                        out.write_image(rgb)
                        out.close()
            folders.append(os.path.join(base, t, f"{t.split()[0]}_{i:02d}"))
        folders.append(os.path.join(base, t))
    return folders


def run(argv):
    from . import crashlog, VERSION
    out_dir = os.path.join(tempfile.gettempdir(), "vfx_nas_stress")
    os.makedirs(out_dir, exist_ok=True)
    try:
        os.remove(os.path.join(out_dir, "crash.log"))
    except OSError:
        pass
    crashlog.install(out_dir, VERSION + " nas-stress")
    args = [a for a in argv[argv.index("--nas-stress") + 1:] if not a.startswith("-")]
    seed = int(args[0]) if args else 1
    steps = int(args[1]) if len(args) > 1 else 400
    log = []

    def say(s):
        log.append(s)
        crashlog._write(s)
        try:
            print(s, flush=True)
        except Exception:
            pass

    ok = False
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, QItemSelectionModel
    crashlog.install_qt()
    app = QApplication(sys.argv[:1])
    from . import core, imaging, asyncdir, media_process
    base = tempfile.mkdtemp(prefix="vfx_nas_")
    nas = FakeNas(base)
    try:
        imaging.init_formats()
        folders = _fixture(base)
        say(f"fixture: {len(folders)} carpetas en {base} · semilla {seed} · {steps} pasos")
        core.NET_FAKE_ROOTS.add(base)

        # todo lo que lee el NAS pasa por el «disco que duerme»
        _scan = core.scan_dir
        core.scan_dir = lambda p, *a, **k: (nas.touch(p), _scan(p, *a, **k))[1]
        _ls = asyncdir.list_subdirs
        asyncdir.list_subdirs = lambda p, *a, **k: (nas.touch(p), _ls(p, *a, **k))[1]
        _lt = imaging.load_thumbnail
        imaging.load_thumbnail = lambda e, *a, **k: (nas.touch(e.path), _lt(e, *a, **k))[1]
        _qt = imaging.qt_thumb
        imaging.qt_thumb = lambda p, *a, **k: (nas.touch(p), _qt(p, *a, **k))[1]
        _call = media_process.call

        def call(module, name, args, *a, **k):
            if args and isinstance(args[0], str):
                nas.touch(args[0])
            return _call(module, name, args, *a, **k)
        media_process.call = call

        from .mainwindow import MainWindow
        from .models import ROLE_ENTRY
        w = MainWindow(None)
        w.cfg["library_roots"] = [base]
        w.cfg.save()
        w.resize(1500, 900)
        w.show()
        w.libside.reload()
        rnd = random.Random(seed)
        state = {"n": 0, "errors": 0, "last": time.monotonic(), "gap": 0.0, "gaps": []}

        def beat():
            now = time.monotonic()
            g = now - state["last"]
            if g > state["gap"]:
                state["gap"] = g
            if g > 1.0:
                state["gaps"].append(round(g, 2))
            state["last"] = now
        hb = QTimer(interval=50, timeout=beat)
        hb.start()

        def tree_items(tree):
            out = []

            def walk(it):
                out.append(it)
                for i in range(it.childCount()):
                    walk(it.child(i))
            for i in range(tree.topLevelItemCount()):
                walk(tree.topLevelItem(i))
            return out

        def select_random(pane):
            v = pane.view()
            m = v.model()
            if m.rowCount():
                ix = m.index(rnd.randrange(m.rowCount()), 0)
                v.setCurrentIndex(ix)
                v.selectionModel().select(ix, QItemSelectionModel.ClearAndSelect)

        def act():
            L = w.libpane
            if rnd.random() < .07:
                nas.sleep()
            r = rnd.random()
            if r < .28:
                w.set_mode("library") if w.mode() != "library" else None
                L.navigate(rnd.choice(folders))
            elif r < .36:
                w.active.navigate(rnd.choice(folders))
            elif r < .52:
                select_random(L if w.mode() == "library" else w.active)
            elif r < .66:
                its = tree_items(w.libside.tree)
                if its:
                    it = rnd.choice(its)
                    it.setExpanded(not it.isExpanded())
            elif r < .72:
                its = [it for it in tree_items(w.libside.tree) if it.data(0, 256)]
                if its:
                    it = rnd.choice(its)
                    w.libside.tree.setCurrentItem(it)
                    w.libside.tree.itemClicked.emit(it, 0)
            elif r < .78:
                if len(L.tabs) < 6:
                    L.add_tab(rnd.choice(folders))
                elif len(L.tabs) > 1:
                    L.close_tab(rnd.randrange(len(L.tabs)))
            elif r < .84:
                w.set_mode(rnd.choice(["library", "explorer"]))
            elif r < .90:
                (L if w.mode() == "library" else w.active).refresh()
            elif r < .95:
                (L if w.mode() == "library" else w.active).go_back()
            else:
                w.libside.reload()

        def step():
            state["n"] += 1
            try:
                act()
            except Exception:
                state["errors"] += 1
                crashlog._write(f"--- paso {state['n']}: error en la acción\n" + traceback.format_exc())
            if state["n"] % 50 == 0:
                say(f"  paso {state['n']}: despertares {nas.wakeups} · lecturas que esperaron {nas.waits} · "
                    f"traba máx {state['gap']:.2f} s")
            if state["n"] < steps:
                QTimer.singleShot(rnd.choice([0, 20, 60, 150, 300, 600]), step)
            else:
                QTimer.singleShot(int((WAKE + 4) * 1000), finish)     # que lleguen las lecturas pendientes

        def finish():
            hb.stop()
            say(f"pasos {state['n']} · errores de acción {state['errors']} · despertares del NAS {nas.wakeups} · "
                f"lecturas que esperaron {nas.waits} · traba máx {state['gap']:.2f} s · trabas >1 s {state['gaps'][:20]}")
            state["done"] = True
            w.close()
            app.quit()

        w.set_mode("library")
        QTimer.singleShot(800, step)
        app.exec()
        if not state.get("done"):
            say("la app salió antes de terminar")
        elif state["gap"] > MAX_GAP:
            say(f"la ventana se trabó {state['gap']:.1f} s (máximo {MAX_GAP} s)")
        else:
            ok = True
    except Exception:
        say(traceback.format_exc())
    finally:
        try:
            media_process.shutdown()
        except Exception:
            pass
    say("NAS STRESS " + ("OK" if ok else "FAILED"))
    with open(os.path.join(out_dir, "result.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    return 0 if ok else 1
