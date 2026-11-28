"""Bounded daemon I/O queues. No Qt objects or callbacks in storage threads.

Separate roles keep tree expansion from starving the foreground pane; separate
roots keep a sleeping share from holding up another. Active OS reads cannot be
interrupted safely; cancellation removes queued work, not an active read.
"""
from collections import deque
from concurrent.futures import Future
from threading import Lock, Thread


class QueueFull(RuntimeError):
    pass


class ScanQueue:
    def __init__(self, workers=2, pending=64):
        self.workers = workers
        self.pending = pending
        self._lock = Lock()
        self._groups = {}

    def submit(self, key, fn, latest=False):
        f = Future()
        with self._lock:
            g = self._groups.setdefault(key, [0, deque()])
            g[1] = deque((job, call) for job, call in g[1] if not job.cancelled())
            if len(g[1]) >= self.pending:
                f.set_exception(QueueFull('Storage scan queue full'))
                return f
            if latest:
                g[1].appendleft((f, fn))
            else:
                g[1].append((f, fn))
            self._start(key, g)
        return f

    def _start(self, key, g):
        # Caller owns the lock. Start at most N daemon threads per root.
        while g[0] < self.workers and g[1]:
            f, fn = g[1].popleft()
            if not f.set_running_or_notify_cancel():
                continue
            g[0] += 1
            try:
                Thread(target=self._run, args=(key, g, f, fn), daemon=True,
                       name='VFX-storage-scan').start()
            except RuntimeError as exc:
                g[0] -= 1
                f.set_exception(exc)

    def _run(self, key, g, f, fn):
        try:
            f.set_result(fn())
        except BaseException as exc:
            f.set_exception(exc)
        finally:
            with self._lock:
                g[0] -= 1
                self._start(key, g)
                if not g[0] and not g[1]:
                    self._groups.pop(key, None)


pane_scans = ScanQueue(workers=2, pending=16)
tree_scans = ScanQueue(workers=2, pending=64)
cache_scans = ScanQueue(workers=2, pending=128)
