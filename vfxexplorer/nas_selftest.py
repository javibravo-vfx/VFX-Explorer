"""Packaged executable acceptance test for network OIIO process isolation.

Uses local fixtures marked as a network share in the parent, so CI exercises
actual IPC/decoders without requiring SMB hardware. No app settings are touched.
"""
import multiprocessing as mp
import os
import sys
import tempfile
import threading
import time
import traceback


def run():
    log = []
    ok = False
    from . import media_process as media, core
    try:
        import numpy as np
        import OpenImageIO as oiio
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from . import imaging
        app = QApplication(sys.argv[:1])
        imaging.init_formats()
        assert imaging.HAS_OIIO, 'OpenImageIO unavailable in executable'
        settings = {'cs': 'lin709', 'chroma': False, 'ffmpeg': None, 'sidecar': True}
        # Optional real Windows SMB-loopback fixture, provisioned by CI.
        share_path = os.environ.get('VFX_LOOPBACK_LOCAL')
        mapped_path = os.environ.get('VFX_LOOPBACK_MAPPED')
        with tempfile.TemporaryDirectory(dir=share_path if share_path and mapped_path else None) as tmp:
            # Deterministic float pixel data including values above 1.0, plus EXR alpha.
            rgb = np.linspace(.02, 2.0, 64 * 32 * 3, dtype=np.float32).reshape(32, 64, 3)
            rgba = np.concatenate((rgb, np.full((32, 64, 1), .75, dtype=np.float32)), axis=2)
            paths = []
            for ext, arr in (('exr', rgba), ('hdr', rgb)):
                path = os.path.join(tmp, 'fixture.' + ext)
                out = oiio.ImageOutput.create(path)
                assert out, f'cannot create {ext}'
                assert out.open(path, oiio.ImageSpec(64, 32, arr.shape[2], 'float')), out.geterror()
                assert out.write_image(arr), out.geterror()
                assert out.close(), out.geterror()
                paths.append(path)
            def decode(path):
                thumb = imaging.oiio_thumb(path, settings)
                linear = imaging.hdr_linear(path, settings, 64)
                info = imaging.oiio_info(path)
                assert not thumb.isNull() and linear is not None and info, path
                assert not any(k == 'Error' for k, _ in info), info
                pix = thumb.convertToFormat(QImage.Format_RGBA8888)
                return (pix.width(), pix.height(), bytes(pix.constBits())), linear, info
            baseline = [decode(p) for p in paths]
            layers = imaging.exr_layers(paths[0])
            assert layers, 'missing EXR layers'
            assert media.worker_counts() == {'preview': 0, 'foreground': 0}, 'local decoding started a process'
            log.append('Local EXR/HDR: OK; zero decoder processes')
            if share_path and mapped_path:
                from .storage import native_read_path
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(1) as pool:
                    for path, expected in zip(paths, baseline):
                        mapped = os.path.join(mapped_path, os.path.relpath(path, share_path))
                        assert core.net_root(mapped), 'mapped drive is not network-sensitive'
                        resolved = pool.submit(native_read_path, mapped).result(timeout=20)
                        assert resolved != mapped and not core.net_root(resolved), f'local SMB not resolved: {mapped}'
                        actual = pool.submit(decode, mapped).result(timeout=30)
                        assert actual[0] == expected[0], 'SMB-local thumbnail differs'
                        np.testing.assert_allclose(actual[1][0], expected[1][0], rtol=1e-6, atol=1e-7)
                        if expected[1][1] is None:
                            assert actual[1][1] is None
                        else:
                            np.testing.assert_allclose(actual[1][1], expected[1][1], rtol=1e-6, atol=1e-7)
                        assert actual[2] == expected[2], 'SMB-local metadata differs'
                assert media.worker_counts() == {'preview': 0, 'foreground': 0}, 'SMB local unexpectedly started decoder'
                log.append('Real local SMB mapped drive: direct EXR/HDR, zero decoder processes')
            else:
                log.append('Real local SMB mapped drive: NOT RUN (no fixture configured)')
            core.NET_FAKE_ROOTS.add(tmp)
            try:
                for path, expected in zip(paths, baseline):
                    assert media.isolated(path), 'fixture did not enter network code path'
                    t = time.perf_counter()
                    thumb, linear, info = decode(path)
                    assert thumb == expected[0], 'thumbnail differs from local decoding'
                    np.testing.assert_allclose(linear[0], expected[1][0], rtol=1e-6, atol=1e-7)
                    if expected[1][1] is None:
                        assert linear[1] is None
                    else:
                        np.testing.assert_allclose(linear[1], expected[1][1], rtol=1e-6, atol=1e-7)
                    assert info == expected[2], 'metadata differs from local decoding'
                    log.append(f'Network {os.path.splitext(path)[1]} thumb + linear + info: OK ({time.perf_counter()-t:.3f}s)')
                assert media.shared_transfers() >= len(paths), 'float data did not use shared memory'
                assert imaging.exr_layers(paths[0]) == layers, 'layer selector differs'
                assert media.worker_counts() == {'preview': 1, 'foreground': 1}, 'extra idle processes'
                parent = os.getpid()
                old = media.call('os', 'getpid', (), _timeout=20, storage=tmp)
                preview = media.call('os', 'getpid', (), preview=True, _timeout=20, storage=tmp)
                assert len({old, preview, parent}) == 3, 'not isolated into separate processes'
                log.append(f'Lazy spawn: parent={parent}, foreground={old}, preview={preview}')
                # Deliberately block a child; the actual Qt event loop must keep ticking.
                done = threading.Event()
                result = []
                def blocked():
                    try:
                        media.call('time', 'sleep', (30,), _timeout=.6, storage=tmp)
                        result.append('unexpected success')
                    except OSError as exc:
                        result.append(str(exc))
                    finally:
                        done.set()
                worker = threading.Thread(target=blocked, daemon=True)
                loop = QEventLoop()
                ticks = [0]
                timer = QTimer()
                timer.setInterval(30)
                def tick():
                    ticks[0] += 1
                    if done.is_set():
                        loop.quit()
                timer.timeout.connect(tick)
                QTimer.singleShot(15000, loop.quit)
                timer.start()
                worker.start()
                loop.exec()
                timer.stop()
                worker.join(1)
                assert done.is_set() and result == ['Network decoder timed out'], result
                assert ticks[0] >= 5, f'GUI heartbeat stalled: {ticks[0]}'
                assert media.call('os', 'getpid', (), preview=True, _timeout=20, storage=tmp) == preview, 'preview pool was lost'
                new = media.call('os', 'getpid', (), _timeout=20, storage=tmp)
                assert new != old, 'blocked worker was not replaced'
                assert imaging.hdr_linear(paths[0], settings, 64) is not None, 'decoder failed after recovery'
                log.append(f'Blocked child: {ticks[0]} GUI timer ticks; isolated timeout + recovery OK')
            finally:
                core.NET_FAKE_ROOTS.discard(tmp)
                media.shutdown()
            assert media.worker_counts() == {'preview': 0, 'foreground': 0}
            assert not mp.active_children(), 'orphan decoder process'
            log.append('Shutdown: no live children')
        ok = True
    except Exception:
        log.append(traceback.format_exc())
    finally:
        media.shutdown()
    log.append('NAS SELFTEST ' + ('OK' if ok else 'FAILED'))
    with open(os.path.join(tempfile.gettempdir(), 'vfxexplorer_nas_selftest.log'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(log) + '\n')
    try:
        print('\n'.join(log))
    except Exception:
        pass
    return 0 if ok else 1
