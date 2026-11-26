# -*- coding: utf-8 -*-
"""Colores de carpetas: manuales + automáticos (por proyecto del pipeline o por nombre)."""

import os
import fnmatch
import hashlib

from PySide6.QtGui import QColor

from .core import norm_key

COLOR_MODES = [
    ("Manual only", "manual"),
    ("By project", "project"),
    ("By name", "name"),
    ("Project + name", "both"),
]

DEFAULT_NAME_RULES = """\
# pattern = color   (case-insensitive; * and ? allowed)
3D = #3e63dd
2D = #30a46c
comp = #f76b15
plates = #f5d90a
plate = #f5d90a
renders = #8e4ec6
render = #8e4ec6
*_publish = #0ac5f5
*_review = #e93d82
*_projects = #8b8d98
footage = #b5835a
source = #b5835a
audio = #e93d82
ref* = #00a2c7
"""

# paleta para proyectos sin color manual (distintos y saturados para fondo oscuro)
PROJECT_PALETTE = ["#e5484d", "#f76b15", "#f5d90a", "#30a46c", "#0ac5f5", "#3e63dd", "#8e4ec6",
                   "#e93d82", "#12a594", "#ffb224", "#5b5bd6", "#d6409f"]

# cuánto se aclara cada nivel: proyecto, secuencia, shot, adentro del shot
LEVEL_MIX = (0.0, 0.30, 0.52, 0.64)


def parse_rules(text):
    rules = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        pat, col = line.rsplit("=", 1)
        pat, col = pat.strip().lower(), col.strip()
        if pat and QColor(col).isValid():
            rules.append((pat, QColor(col).name()))
    return rules


def mix_white(hexc, t):
    c = QColor(hexc)
    r = c.red() + (255 - c.red()) * t
    g = c.green() + (255 - c.green()) * t
    b = c.blue() + (255 - c.blue()) * t
    return QColor(int(r), int(g), int(b)).name()


class ColorEngine:
    def __init__(self, app):
        self.app = app
        self._cache = {}
        self.reload()

    def reload(self):
        self.mode = self.app.cfg["color_mode"] or "project"
        self.rules = parse_rules(self.app.cfg["name_rules"])
        self._cache.clear()

    def invalidate(self):
        self._cache.clear()

    def _by_name(self, name):
        n = name.lower()
        for pat, col in self.rules:
            if fnmatch.fnmatchcase(n, pat):
                return col
        return None

    def _by_project(self, path):
        pipe = self.app.pipeline
        parts = [p for p in os.path.normpath(path).replace("/", "\\").split("\\") if p]
        pre = pipe.prefix
        idx = next((i for i, p in enumerate(parts) if pre and p.startswith(pre) and len(p) > len(pre)), None)
        if idx is None:
            return None
        level = len(parts) - idx - 1
        proj_path = os.sep.join(parts[: idx + 1])
        if path.startswith("\\\\"):
            proj_path = "\\\\" + proj_path
        elif path.startswith("/"):
            proj_path = "/" + proj_path
        if len(parts[idx]) == 2 and parts[idx][1] == ":":
            proj_path += os.sep
        # solo proyectos que cuelgan de la raíz del pipeline (evita colorear cualquier "VFX-algo").
        # Se compara sin la barra final: «T:\» y «T:» son lo mismo (antes no coincidían y nunca coloreaba)
        canon = lambda x: x.replace("/", "\\").rstrip("\\").lower()
        if canon(os.path.dirname(proj_path)) != canon(pipe.base()):
            return None
        base = self.app.lib.color(norm_key(proj_path))
        if not base:
            h = int(hashlib.md5(parts[idx].lower().encode()).hexdigest(), 16)
            base = PROJECT_PALETTE[h % len(PROJECT_PALETTE)]
        return mix_white(base, LEVEL_MIX[min(level, len(LEVEL_MIX) - 1)])

    def dir_color(self, path):
        """Color de una carpeta: el manual gana; si no, el automático según el modo."""
        if not path:
            return None
        key = norm_key(path)
        manual = self.app.lib.color(key)
        if manual or self.mode == "manual":
            return manual
        hit = self._cache.get(key, 0)
        if hit != 0:
            return hit
        col = None
        name = os.path.basename(os.path.normpath(path))
        if self.mode in ("name", "both"):
            col = self._by_name(name)
        if col is None and self.mode in ("project", "both"):
            col = self._by_project(path)
        if len(self._cache) > 20000:
            self._cache.clear()
        self._cache[key] = col
        return col
