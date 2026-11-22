# -*- coding: utf-8 -*-
"""Metadatos de la librería: color, tags, rating y colecciones. Se guarda en library.json (portable)."""

import os
import json
from collections import Counter, OrderedDict

from .core import norm_key


class Library:
    def __init__(self, path):
        self.path = path
        self.items = {}          # key -> {"tags": [], "rating": 0, "color": "#hex", "ref": {...}}
        self.collections = OrderedDict()   # nombre -> [key, ...]
        self.dirty = False
        self._load()

    # ---------------- persistencia ----------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.items = d.get("items", {})
            self.collections = OrderedDict(d.get("collections", {}))
        except Exception:
            pass

    def save(self):
        if not self.dirty:
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "items": self.items, "collections": self.collections},
                          f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass

    def migrate_colors(self, colors):
        """Importa colores de la config de la v0.1 (clave -> color)."""
        for k, c in (colors or {}).items():
            it = self.items.setdefault(k, {})
            it.setdefault("color", c)
            if "ref" not in it:
                it["ref"] = {"dir": os.path.dirname(k), "name": os.path.basename(k), "kind": "dir"}
        if colors:
            self.dirty = True

    # ---------------- lectura ----------------
    def meta(self, key):
        return self.items.get(key)

    def color(self, key):
        it = self.items.get(key)
        return it.get("color") if it else None

    def tags(self, key):
        it = self.items.get(key)
        return list(it.get("tags", [])) if it else []

    def rating(self, key):
        it = self.items.get(key)
        return int(it.get("rating", 0)) if it else 0

    def snapshot(self):
        """Copia liviana para usar desde threads."""
        return {k: {"tags": list(v.get("tags", [])), "rating": v.get("rating", 0)} for k, v in self.items.items()}

    def all_tags(self):
        c = Counter()
        for v in self.items.values():
            for t in v.get("tags", []):
                c[t] += 1
        return sorted(c.items(), key=lambda kv: kv[0].lower())

    def refs_with_tag(self, tag):
        tag = tag.lower()
        return [(k, v["ref"]) for k, v in self.items.items()
                if "ref" in v and any(t.lower() == tag for t in v.get("tags", []))]

    def refs_with_rating(self, minimum):
        return [(k, v["ref"]) for k, v in self.items.items() if "ref" in v and int(v.get("rating", 0)) >= minimum]

    def refs_in_collection(self, name):
        out = []
        for k in self.collections.get(name, []):
            it = self.items.get(k)
            if it and "ref" in it:
                out.append((k, it["ref"]))
        return out

    # ---------------- escritura ----------------
    def _item(self, key, ref=None):
        it = self.items.setdefault(key, {})
        if ref:
            it["ref"] = ref
        return it

    def _cleanup(self, key):
        it = self.items.get(key)
        if it is None:
            return
        in_coll = any(key in v for v in self.collections.values())
        if not it.get("tags") and not it.get("rating") and not it.get("color") and not in_coll:
            del self.items[key]

    def set_color(self, targets, color):
        """targets: lista de (key, ref)."""
        for key, ref in targets:
            it = self._item(key, ref)
            if color:
                it["color"] = color
            else:
                it.pop("color", None)
            self._cleanup(key)
        self.dirty = True

    def set_rating(self, targets, rating):
        for key, ref in targets:
            it = self._item(key, ref)
            if rating:
                it["rating"] = int(rating)
            else:
                it.pop("rating", None)
            self._cleanup(key)
        self.dirty = True

    def edit_tags(self, targets, new_common, old_common):
        """Aplica a cada ítem: quita los tags comunes que se borraron y agrega los nuevos."""
        removed = {t.lower() for t in old_common} - {t.lower() for t in new_common}
        for key, ref in targets:
            it = self._item(key, ref)
            cur = [t for t in it.get("tags", []) if t.lower() not in removed]
            low = {t.lower() for t in cur}
            for t in new_common:
                if t.lower() not in low:
                    cur.append(t)
                    low.add(t.lower())
            if cur:
                it["tags"] = cur
            else:
                it.pop("tags", None)
            self._cleanup(key)
        self.dirty = True

    def rename_tag(self, old, new):
        for v in self.items.values():
            tags = v.get("tags", [])
            if any(t.lower() == old.lower() for t in tags):
                out = []
                for t in tags:
                    t2 = new if t.lower() == old.lower() else t
                    if t2 and t2.lower() not in {x.lower() for x in out}:
                        out.append(t2)
                v["tags"] = out
        for k in list(self.items):
            self._cleanup(k)
        self.dirty = True

    def add_to_collection(self, name, targets):
        lst = self.collections.setdefault(name, [])
        for key, ref in targets:
            self._item(key, ref)
            if key not in lst:
                lst.append(key)
        self.dirty = True

    def remove_from_collection(self, name, keys):
        lst = self.collections.get(name, [])
        self.collections[name] = [k for k in lst if k not in set(keys)]
        for k in keys:
            self._cleanup(k)
        self.dirty = True

    def delete_collection(self, name):
        keys = self.collections.pop(name, [])
        for k in keys:
            self._cleanup(k)
        self.dirty = True

    def rename_collection(self, old, new):
        if old in self.collections and new and new not in self.collections:
            self.collections = OrderedDict((new if k == old else k, v) for k, v in self.collections.items())
            self.dirty = True

    def path_moved(self, old_key, new_key, new_ref):
        """Mantiene metadatos al renombrar/mover."""
        if old_key == new_key or old_key not in self.items:
            return
        it = self.items.pop(old_key)
        it["ref"] = new_ref
        self.items[new_key] = it
        for name, lst in self.collections.items():
            self.collections[name] = [new_key if k == old_key else k for k in lst]
        self.dirty = True


def dir_target(path):
    """(key, ref) para una carpeta dada por ruta (árbol, favoritos)."""
    path = os.path.normpath(path)
    return norm_key(path), {"dir": os.path.dirname(path), "name": os.path.basename(path), "kind": "dir"}
