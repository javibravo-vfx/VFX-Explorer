# -*- coding: utf-8 -*-
"""Núcleo sin Qt: detección de secuencias, escaneo de carpetas, búsqueda, config y rutas portables."""

import os
import re
import unicodedata
import sys
import json
import time
import shutil
import fnmatch
from dataclasses import dataclass, field

from . import APP_NAME

IS_WIN = sys.platform.startswith("win")

IMAGE_EXTS = {
    ".exr", ".sxr", ".mxr", ".dpx", ".cin", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".tga", ".bmp", ".hdr", ".rgbe", ".webp", ".psd", ".psb", ".jp2", ".j2k", ".sgi",
    ".rgb", ".tx", ".jxl", ".dds", ".pfm", ".iff", ".rla", ".pic", ".gif",
}
VIDEO_EXTS = {
    ".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".webm", ".mpg", ".mpeg",
    ".wmv", ".mts", ".m2ts",
}
MODEL_EXTS = {
    ".max", ".fbx", ".obj", ".abc", ".usd", ".usda", ".usdc", ".usdz", ".blend",
    ".ma", ".mb", ".hip", ".hiplc", ".hipnc", ".c4d", ".gltf", ".glb", ".ply",
    ".stl", ".3ds", ".vrmesh", ".vrscene", ".bgeo", ".sc", ".vdb", ".spp", ".ztl",
    ".zpr", ".nk", ".aep", ".prproj", ".drp",
}

CATEGORIES = ("dir", "seq", "video", "image", "model", "other")

FILTERS = [
    ("All", "all"),
    ("Media (no others)", "media"),
    ("Sequences", "seq"),
    ("EXR", "exr"),
    ("Videos", "video"),
    ("Single images", "image"),
    ("Models / scenes", "model"),
    ("Folders", "dir"),
]


# ----------------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------------

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    d = os.path.join(app_dir(), "VFXExplorer_data")
    old = os.path.join(app_dir(), "SeqBrowser_data")   # nombre anterior (v0.1)
    if not os.path.isdir(d) and os.path.isdir(old):
        try:
            os.rename(old, d)
        except OSError:
            pass
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return d
    except OSError:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_NAME)
        os.makedirs(d, exist_ok=True)
        return d


def norm_key(path):
    return os.path.normcase(os.path.normpath(path))


def fwd(path):
    return path.replace("\\", "/")


def same_path(a, b):
    return bool(a) and bool(b) and norm_key(a) == norm_key(b)


def human_size(n):
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return ""


def fmt_time(t):
    if not t:
        return ""
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(t))


_NAT_RE = re.compile(r"(\d+)")


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in _NAT_RE.split(s.lower())]


def compress_ranges(nums):
    if not nums:
        return ""
    out = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append((start, prev))
        start = prev = n
    out.append((start, prev))
    return ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in out)


# ----------------------------------------------------------------------------
# Entradas y secuencias
# ----------------------------------------------------------------------------

SEQ_RE = re.compile(r"^(?P<head>.*?)(?P<frame>\d+)(?P<ext>\.[^.]+)$")


@dataclass
class Entry:
    kind: str            # 'dir' | 'seq' | 'file'
    dirpath: str
    name: str            # nombre a mostrar
    path: str            # ruta completa (dir/archivo) o primer frame de la secuencia
    ext: str = ""
    size: int = 0
    mtime: float = 0.0
    head: str = ""
    pad: int = 0
    frames: list = field(default_factory=list)
    files: list = field(default_factory=list)
    _missing: list = None

    @property
    def cat(self):
        if self.kind == "header":
            return "header"
        if self.kind == "drive":
            return "drive"
        if self.kind == "dir":
            return "dir"
        if self.kind == "seq":
            return "seq"
        if self.ext in VIDEO_EXTS:
            return "video"
        if self.ext in IMAGE_EXTS:
            return "image"
        if self.ext in MODEL_EXTS:
            return "model"
        return "other"

    @property
    def first(self):
        return self.frames[0] if self.frames else None

    @property
    def last(self):
        return self.frames[-1] if self.frames else None

    @property
    def missing(self):
        if self._missing is None:
            if self.kind != "seq" or not self.frames or self.last - self.first + 1 > 2_000_000:
                self._missing = []
            else:
                have = set(self.frames)
                self._missing = [f for f in range(self.first, self.last + 1) if f not in have]
        return self._missing

    def hashes(self):
        return "#" * max(self.pad, 1)

    def printf(self):
        return f"%0{self.pad}d" if self.pad > 1 else "%d"

    @property
    def ext_real(self):
        if self.files:
            m = SEQ_RE.match(self.files[0])
            if m:
                return m.group("ext")
        return self.ext

    def pattern_path(self, style="hash"):
        if self.kind != "seq":
            return self.path
        token = self.hashes() if style == "hash" else self.printf()
        return os.path.join(self.dirpath, f"{self.head}{token}{self.ext_real}")

    def thumb_source(self):
        if self.kind == "seq" and self.files:
            return os.path.join(self.dirpath, self.files[len(self.files) // 2])
        return self.path

    def key(self):
        """Clave estable para color/tags/rating/colecciones."""
        if self.kind == "seq":
            return norm_key(os.path.join(self.dirpath, f"{self.head}#{self.ext}"))
        return norm_key(self.path)

    def ref(self):
        """Referencia para volver a encontrar la entrada (colecciones, tags)."""
        return {"dir": self.dirpath, "name": self.name, "kind": self.kind}

    def all_paths(self):
        if self.kind == "seq":
            return [os.path.join(self.dirpath, f) for f in self.files]
        return [self.path]

    def type_label(self):
        e = self.ext[1:].upper() if self.ext else ""
        if self.kind == "dir":
            return "Folder"
        if self.kind == "drive":
            return {"network": "Network drive", "removable": "Removable drive", "cdrom": "CD drive"}.get(
                getattr(self, "drive_kind", "local"), "Local Disk")
        if self.kind == "seq":
            return f"Sequence {e}"
        return {"video": f"Video {e}", "image": f"Image {e}", "model": f"Scene/Model {e}"}.get(self.cat, e or "File")


def _is_frame_boundary(head):
    if head == "":
        return True
    c = head[-1]
    if c in "._- ":
        return True
    # "beauty0001.exr" sí; "shot_v001.exr" no (es versión, no frame)
    return c.isalpha() and c not in "vV"


def split_frame(name):
    """'plate.1001.exr' -> ('plate.', '1001', '.exr') o None si no es candidato a frame."""
    m = SEQ_RE.match(name)
    if not m:
        return None
    if m.group("ext").lower() not in IMAGE_EXTS or not _is_frame_boundary(m.group("head")):
        return None
    return m.group("head"), m.group("frame"), m.group("ext")


def group_files(dirpath, files):
    """files: lista de (nombre, size, mtime). Devuelve Entries de secuencias y archivos."""
    groups = {}
    singles = []
    for name, size, mtime in files:
        sp = split_frame(name)
        if sp:
            head, frame, ext = sp
            groups.setdefault((head, ext.lower()), []).append((int(frame), frame, name, size, mtime))
        else:
            singles.append((name, size, mtime))

    out = []
    for (head, ext), items in groups.items():
        if len(items) == 1:
            _, _, name, size, mtime = items[0]
            singles.append((name, size, mtime))
            continue
        items.sort(key=lambda t: t[0])
        lens = {len(t[1]) for t in items}
        if len(lens) == 1:
            pad = lens.pop()
        else:
            shortest = min(lens)
            pad = shortest if any(t[1].startswith("0") and len(t[1]) == shortest for t in items) else 0
        e = Entry(
            kind="seq", dirpath=dirpath, name="", path=os.path.join(dirpath, items[0][2]),
            ext=ext, size=sum(t[3] for t in items), mtime=max(t[4] for t in items),
            head=head, pad=pad, frames=[t[0] for t in items], files=[t[2] for t in items],
        )
        e.name = f"{head}{e.hashes()}{e.ext_real}"
        out.append(e)

    for name, size, mtime in singles:
        out.append(Entry(kind="file", dirpath=dirpath, name=name, path=os.path.join(dirpath, name),
                         ext=os.path.splitext(name)[1].lower(), size=size, mtime=mtime))
    return out


HIDDEN_NAMES = {"thumbs.db", "desktop.ini", "@eadir", "#recycle", "$recycle.bin", "system volume information"}


def scan_dir(path, show_hidden=False):
    dirs, files = [], []
    with os.scandir(path) as it:
        for de in it:
            name = de.name
            if not show_hidden and (name.startswith(".") or name.lower() in HIDDEN_NAMES):
                continue
            try:
                st = de.stat()
                if IS_WIN and not show_hidden and getattr(st, "st_file_attributes", 0) & 0x6:
                    continue
                if de.is_dir():
                    dirs.append(Entry(kind="dir", dirpath=path, name=name, path=os.path.join(path, name),
                                      mtime=st.st_mtime))
                else:
                    files.append((name, st.st_size, st.st_mtime))
            except OSError:
                continue
    return dirs + group_files(path, files)


# ----------------------------------------------------------------------------
# Este equipo: discos y ubicaciones de red
# ----------------------------------------------------------------------------

THISPC = "::thispc"
LINUX_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "ntfs", "ntfs3", "vfat", "exfat", "fuseblk",
            "nfs", "nfs4", "cifs", "smbfs", "smb3", "overlay", "9p", "f2fs"}


def _win_drives():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    mpr = ctypes.windll.mpr
    out = []
    mask = k32.GetLogicalDrives()
    for i in range(26):
        if not mask & (1 << i):
            continue
        letter = chr(65 + i) + ":"
        root = letter + "\\"
        dtype = k32.GetDriveTypeW(ctypes.c_wchar_p(root))   # 2 removible, 3 fijo, 4 red, 5 cd
        if dtype in (0, 1):
            continue
        label = ""
        buf = ctypes.create_unicode_buffer(261)
        if k32.GetVolumeInformationW(ctypes.c_wchar_p(root), buf, 261, None, None, None, None, 0):
            label = buf.value
        unc = ""
        if dtype == 4:
            ubuf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(1024)
            if mpr.WNetGetConnectionW(ctypes.c_wchar_p(letter), ubuf, ctypes.byref(n)) == 0:
                unc = ubuf.value
        kind = {2: "removable", 3: "local", 4: "network", 5: "cdrom"}.get(dtype, "local")
        out.append({"letter": letter, "root": root, "label": label, "unc": unc, "kind": kind})
    return out


def _posix_drives():
    out, seen = [], set()
    try:
        with open("/proc/mounts") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mnt, fs = parts[0], parts[1].replace("\\040", " "), parts[2]
        if fs not in LINUX_FS or mnt in seen or mnt.startswith(("/proc", "/sys", "/dev", "/run", "/snap", "/boot/efi")):
            continue
        if fs == "overlay" and mnt != "/":
            continue
        seen.add(mnt)
        kind = "network" if fs in ("nfs", "nfs4", "cifs", "smbfs", "smb3", "9p") else "local"
        out.append({"letter": "", "root": mnt, "label": os.path.basename(mnt) or "System",
                    "unc": dev if kind == "network" else "", "kind": kind})
    if not out:
        out.append({"letter": "", "root": "/", "label": "System", "unc": "", "kind": "local"})
    return out


def list_drives():
    """Entradas tipo 'drive' con nombre, total y libre (puede tardar con unidades de red: usar en un thread)."""
    raw = _win_drives() if IS_WIN else _posix_drives()
    out = []
    for d in raw:
        total = free = 0
        try:
            u = shutil.disk_usage(d["root"])
            total, free = u.total, u.free
        except OSError:
            pass
        label = d["label"] or ({"local": "Local Disk", "network": "Network drive", "removable": "Removable drive",
                                "cdrom": "CD drive"}[d["kind"]])
        if d["letter"]:
            name = f"{label} ({d['unc'].rstrip(chr(92))}) ({d['letter']})" if d["unc"] and d["kind"] == "network" \
                else f"{label} ({d['letter']})"
            if d["unc"] and d["kind"] == "network":
                host = d["unc"].lstrip("\\").split("\\")[0]
                name = f"{label} (\\\\{host}) ({d['letter']})"
        else:
            name = label if d["root"] != "/" else "System (/)"
        e = Entry(kind="drive", dirpath="", name=name, path=d["root"], size=total)
        e.free = free
        e.drive_kind = d["kind"]
        e.unc = d["unc"]
        out.append(e)
    return out


def resolve_refs(refs, show_hidden=True):
    """Convierte referencias guardadas (colecciones / tags) en Entries actuales. Devuelve (entries, faltantes)."""
    by_dir = {}
    for key, ref in refs:
        by_dir.setdefault(ref.get("dir", ""), []).append((key, ref))
    out, missing = [], []
    for d, items in by_dir.items():
        try:
            listing = {e.key(): e for e in scan_dir(d, show_hidden)}
        except OSError:
            listing = {}
        for key, ref in items:
            e = listing.get(key)
            if e is None and ref.get("kind") == "dir" and os.path.isdir(os.path.join(d, ref.get("name", ""))):
                p = os.path.join(d, ref["name"])
                e = Entry(kind="dir", dirpath=d, name=ref["name"], path=p, mtime=os.path.getmtime(p))
            if e is None:
                missing.append((key, ref))
            else:
                out.append(e)
    return out, missing


# ----------------------------------------------------------------------------
# Búsqueda: texto, wildcards, #tags y ★rating
# ----------------------------------------------------------------------------

@dataclass
class Query:
    names: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    min_rating: int = 0
    any_of: list = field(default_factory=list)   # pastillas de tags rápidos: alcanza con que coincida una
    any_root: str = ""                          # raíz de la búsqueda (para mirar los nombres de las carpetas)

    @property
    def empty(self):
        return not (self.names or self.tags or self.min_rating or self.any_of)


DATE_GROUPS = ["Today", "Yesterday", "Earlier this week", "Last week", "Earlier this month", "Last month",
               "Earlier this year", "A long time ago"]


def date_group(ts, today=None):
    """Grupo de fecha como «Group by › Date modified» de Windows 11 → índice en DATE_GROUPS."""
    import datetime as _dt
    today = today or _dt.date.today()
    if not ts:
        return 7
    d = _dt.date.fromtimestamp(ts)
    if d >= today:
        return 0
    if d == today - _dt.timedelta(days=1):
        return 1
    week = today - _dt.timedelta(days=today.weekday())          # lunes
    if d >= week:
        return 2
    if d >= week - _dt.timedelta(days=7):
        return 3
    month = today.replace(day=1)
    if d >= month:
        return 4
    if d >= (month - _dt.timedelta(days=1)).replace(day=1):
        return 5
    if d.year == today.year:
        return 6
    return 7


def fold(text):
    """minúsculas y sin acentos: «Explosión» == «explosion»."""
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def parse_pill(text):
    """«Fuego: fire, flame» → ("Fuego", ["fuego", "fire", "flame"])."""
    text = (text or "").strip()
    if ":" in text:
        label, rest = text.split(":", 1)
    else:
        label, rest = text, ""
    label = label.strip()
    kws = [fold(label)] + [fold(k.strip()) for k in re.split(r"[,;]", rest) if k.strip()]
    out = []
    for k in kws:
        if k and k not in out:
            out.append(k)
    return label, out


def parse_query(text):
    q = Query()
    for tok in (text or "").strip().split():
        low = tok.lower()
        if low.startswith("#") and len(low) > 1:
            q.tags.append(low[1:])
        elif low.startswith("tag:") and len(low) > 4:
            q.tags.append(low[4:])
        elif low.startswith("★") or low.startswith("r:") or low.startswith("rating:"):
            digits = re.sub(r"\D", "", low)
            q.min_rating = int(digits) if digits else low.count("★")
        else:
            q.names.append(low)
    return q


def entry_matches(e, q, cat, recursive=False, meta=None):
    """meta: función key -> dict(tags, rating) o None."""
    if cat != "all":
        c = e.cat
        if cat == "dir":
            if c != "dir":
                return False
        elif c == "dir":
            if recursive:
                return False
        elif cat == "media":
            if c not in ("seq", "video", "image"):
                return False
        elif cat == "exr":
            if e.ext != ".exr":
                return False
        elif c != cat:
            return False
    if q.empty:
        return not (recursive and e.kind == "dir" and cat != "dir")
    name = e.name.lower()
    for tok in q.names:
        if "*" in tok or "?" in tok:
            pat = tok if tok.startswith("*") else "*" + tok
            pat = pat if pat.endswith("*") else pat + "*"
            if not fnmatch.fnmatch(name, pat):
                return False
        elif tok not in name:
            return False
    if q.any_of:
        if recursive and e.kind == "dir" and cat != "dir":
            return False
        rel = e.dirpath
        if q.any_root:
            try:
                rel = os.path.relpath(e.dirpath, q.any_root)
            except ValueError:
                pass
        hay = fold(e.name + "/" + rel)
        if not any(k in hay for k in q.any_of):
            m = meta(e.key()) if meta else None
            tags = [fold(t) for t in (m or {}).get("tags", [])]
            if not any(t.startswith(k) for k in q.any_of for t in tags):
                return False
    if q.tags or q.min_rating:
        m = meta(e.key()) if meta else None
        if not m:
            return False
        if q.min_rating and int(m.get("rating", 0)) < q.min_rating:
            return False
        tags = [t.lower() for t in m.get("tags", [])]
        for t in q.tags:
            if not any(x.startswith(t) for x in tags):
                return False
    return True


# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------

DEFAULT_QUICK_TAGS = [
    "Smoke: smoke, humo",
    "Fire: fire, flame, fuego",
    "Explosion: explosion, blast, exp",
    "Sparks: sparks, spark, embers",
    "Dust: dust, polvo",
    "Water: water, splash, agua",
    "Debris: debris, rocks, escombros",
    "Blood: blood, sangre",
]


class Config:
    DEFAULTS = {
        "favorites": [],
        "player": "",
        "ffmpeg": "",
        "colorspace": "acescg",
        "use_chromaticities": True,
        "threads": 4,
        "show_hidden": False,
        "sidecar_previews": True,
        "pipeline_use_stm": False,      # obsoleto (0.11): se importa una vez
        "pipeline_root": "T:",
        "pipeline_prefix": "VFX-",
        "pipeline_seq_exclude": "3D,SOURCE,FOOTAGE,AUDIO,RENDER",
        "pipeline_state": {},
        "thumb_size": 200,
        "dual": False,
        "panes": [],
        "geometry": "",
        "splitter": "",
        "splitter_left": "",
        "splitter_panes": "",
        "splitter_library": "",
        # 0.3
        "library_features": False,     # tags, rating y colecciones
        "folder_sizes": False,
        "tree_line_colors": True,
        "color_mode": "project",
        "name_rules": None,            # None = reglas por defecto
        "library_roots": [],
        "library_pane": {},
        "mode": "explorer",
        "viewer_res": 1280,
        "viewer_mem": 1024,
        "viewer_fps": 24,
        "viewer_autoplay": True,
        "viewer_loop": True,
        # 0.4
        "details_visible": True,
        "tree_lines_style": "solid",    # solid | dotted
        "tree_trace": True,             # Tree Path Tracing (como XYplorer)
        "tree_trace_width": 2,
        "tree_trace_color": "accent",   # accent | folder
        # 0.5
        "pipeline_location": "center",  # center | sidebar | hidden
        "pipeline_depts": "",           # vacío = todas las carpetas del shot (3D, Comp, DMP…)
        "group_mode": "auto",           # auto | none | folder | type
        "scrub_thumbs": True,
        # 0.6
        "folder_color": "yellow",       # yellow (Windows) | blue
        "splitter_left2": "",
        "cfg_version": 8,
        "pipeline_task_depts": None,    # None = "3D": departamentos que tienen tasks
        "pipeline_stages": None,        # None = "1_projects, 2_review, 3_publish"
        # 0.7
        "lib_favorites": [],            # acceso rápido de la VFX Library
        "quick_tags": None,             # None = pastillas por defecto (DEFAULT_QUICK_TAGS)
        "lib_tree_line_color": "#8d6fd1",
        "splitter_left3": "",
        "hidden_sys": [],
        "hidden_drives": [],
        "list_cols": {},                # columnas de Detalles tildadas/destildadas
        "folder_views": {},             # vista/orden/agrupado recordados por carpeta
        "folder_view_default": None,
        "show_hidden_quick": False,
        "show_hidden_drives": False,               # Escritorio/Descargas/Imágenes/Videos ocultos en Acceso rápido
    }

    def __init__(self, path):
        self.path = path
        self.data = json.loads(json.dumps(self.DEFAULTS))
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.data.update(saved)
            if int(saved.get("cfg_version", 0)) < 6:
                self.data["pipeline_location"] = "center"   # 0.6: nuevo lugar por defecto
                self.data["cfg_version"] = 6
            if int(saved.get("cfg_version", 0)) < 8:
                self._import_studio_toolbar()
                self.data["cfg_version"] = 8
        except Exception:
            pass

    def _import_studio_toolbar(self):
        """0.11: el pipeline ya no lee la config de Studio Toolbar; si se usaba, se copia una vez."""
        if not self.data.get("pipeline_use_stm", True):
            return
        self.data["pipeline_use_stm"] = False
        p = os.path.join(os.path.expanduser("~"), ".studio-toolbar", "pipeline_config.ini")
        try:
            with open(p, "r") as f:
                stm = json.load(f)
        except Exception:
            return
        if stm.get("root_drive"):
            self.data["pipeline_root"] = stm["root_drive"]
        if stm.get("project_prefix"):
            self.data["pipeline_prefix"] = stm["project_prefix"]
        if stm.get("seq_exclude") is not None:
            self.data["pipeline_seq_exclude"] = stm["seq_exclude"]
        subs = [stm.get(k, "").strip() for k in ("sub_projects", "sub_review", "sub_publish")]
        subs += [x.strip() for x in stm.get("extra_subs", "").split(",")]
        subs = [x for x in subs if x]
        if subs:
            self.data["pipeline_stages"] = ", ".join(subs)

    def __getitem__(self, k):
        return self.data.get(k, self.DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass


def find_tool(cfg_value, name):
    exe = name + (".exe" if IS_WIN else "")
    cands = []
    if cfg_value:
        cands.append(cfg_value)
        if name == "ffprobe":
            cands.append(os.path.join(os.path.dirname(cfg_value), exe))
    cands += [os.path.join(app_dir(), "bin", exe), os.path.join(app_dir(), exe)]
    for c in cands:
        if c and os.path.isfile(c) and name in os.path.basename(c).lower():
            return c
    return shutil.which(name)
