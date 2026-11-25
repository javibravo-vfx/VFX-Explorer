# -*- coding: utf-8 -*-
"""File hashes: MD5, SHA-1 y SHA-256 de un archivo (las tres en una sola lectura, en segundo plano),
con copiar y comparar contra un hash pegado."""

import hashlib
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
                               QApplication, QDialogButtonBox, QHBoxLayout)

from .core import human_size

ALGOS = (("MD5", "md5"), ("SHA-1", "sha1"), ("SHA-256", "sha256"))


class HashWorker(QThread):
    progress = Signal(int)
    done = Signal(dict, str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        hs = {k: hashlib.new(k) for _, k in ALGOS}
        try:
            total = max(1, os.path.getsize(self.path))
            read = 0
            last = -1
            with open(self.path, "rb") as f:
                while not self._stop:
                    b = f.read(4 * 1024 * 1024)
                    if not b:
                        break
                    for h in hs.values():
                        h.update(b)
                    read += len(b)
                    pc = int(read * 100 / total)
                    if pc != last:
                        last = pc
                        self.progress.emit(pc)
        except OSError as ex:
            self.done.emit({}, str(ex))
            return
        if self._stop:
            return
        self.done.emit({k: h.hexdigest() for k, h in hs.items()}, "")


class HashDialog(QDialog):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.setWindowTitle("File hashes")
        self.setMinimumWidth(640)
        self.path = path
        lay = QVBoxLayout(self)
        name = QLabel(f"<b>{os.path.basename(path)}</b><br><span style='color:#9d9d9d'>{path} · "
                      f"{human_size(os.path.getsize(path)) if os.path.exists(path) else ''}</span>")
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name.setWordWrap(True)
        lay.addWidget(name)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)
        g = QGridLayout()
        self.fields = {}
        for r, (label, key) in enumerate(ALGOS):
            g.addWidget(QLabel(label), r, 0)
            f = QLineEdit()
            f.setReadOnly(True)
            f.setPlaceholderText("calculating…")
            f.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
            g.addWidget(f, r, 1)
            b = QPushButton("Copy")
            b.clicked.connect(lambda c=False, f=f: f.text() and QApplication.clipboard().setText(f.text()))
            g.addWidget(b, r, 2)
            self.fields[key] = f
        lay.addLayout(g)
        cl = QHBoxLayout()
        cl.addWidget(QLabel("Compare:"))
        self.cmp = QLineEdit()
        self.cmp.setPlaceholderText("paste a hash (MD5, SHA-1 or SHA-256) to check it")
        self.cmp.textChanged.connect(self._compare)
        cl.addWidget(self.cmp, 1)
        self.cmp_res = QLabel("")
        self.cmp_res.setMinimumWidth(130)
        cl.addWidget(self.cmp_res)
        lay.addLayout(cl)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.w = HashWorker(path)
        self.w.progress.connect(self.bar.setValue)
        self.w.done.connect(self._done)
        self.w.start()

    def _done(self, res, err):
        if err:
            self.bar.setFormat("Error: " + err)
            return
        self.bar.setValue(100)
        self.bar.setFormat("Done")
        for k, v in res.items():
            self.fields[k].setText(v)
        self._compare(self.cmp.text())

    def _compare(self, t):
        t = (t or "").strip().lower().replace(" ", "")
        if not t:
            self.cmp_res.setText("")
            return
        vals = {f.text().lower(): k for k, f in self.fields.items() if f.text()}
        if not vals:
            self.cmp_res.setText("…")
            return
        if t in vals:
            label = dict((k, l) for l, k in ALGOS)[vals[t]]
            self.cmp_res.setText(f"<span style='color:#4ec97b'>✓ matches {label}</span>")
        else:
            self.cmp_res.setText("<span style='color:#ff6b6b'>✗ no match</span>")

    def done(self, r):
        if self.w.isRunning():
            self.w.stop()
            self.w.wait(2000)
        super().done(r)
