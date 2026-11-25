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
RAW_EXTS = {      # RAW de cámaras de fotos + DNG
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2", ".rwl",
    ".pef", ".srw", ".x3f", ".3fr", ".fff", ".iiq", ".erf", ".kdc", ".dcr", ".mrw", ".mos", ".raw", ".gpr",
}
IMAGE_EXTS |= RAW_EXTS
AUDIO_EXTS = {".wav", ".mp3", ".aif", ".aiff", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
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
    ("RAW (camera / DNG)", "raw"),
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


# ---------------------------------------------------------------- red sin congelarse
# Preguntar por una carpeta de un NAS apagado (o una unidad mapeada desconectada) traba el hilo que pregunta
# hasta 20-30 s en Windows. Antes de tocar una ruta de red desde la interfaz, se consulta `reachable()`:
# el chequeo corre en otro hilo con un tiempo máximo y el resultado se guarda por «share» (\\server\share o X:).
import threading as _thr

_NET = {}            # raíz -> {"ok": bool|None, "t": float, "busy": bool, "ev": Event}
_NET_LOCK = _thr.Lock()
_NET_OK_TTL = 30.0   # una vez visto vivo, no se vuelve a chequear por 30 s
_NET_BAD_TTL = 8.0   # caído: se reintenta cada 8 s (en otro hilo)
_DRIVE_TYPES = {}
NET_FAKE_ROOTS = set()     # pruebas en Linux: carpetas que se tratan como un share de red
NET_FAKE_OFFLINE = set()   # pruebas: de esas, las que están caídas (el chequeo tarda y falla)


def _drive_is_remote(letter):
    if letter in _DRIVE_TYPES:
        return _DRIVE_TYPES[letter]
    r = False
    if IS_WIN:
        try:
            import ctypes
            r = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter + "\\")) == 4   # DRIVE_REMOTE
        except Exception:
            r = False
    _DRIVE_TYPES[letter] = r
    return r


def net_root(path):
    r"""«\\server\share», «T:» (unidad de red) o None si la ruta es local."""
    p = str(path or "").replace("/", "\\") if IS_WIN else str(path or "")
    if p.startswith("\\\\") or p.startswith("//"):
        parts = [x for x in re.split(r"[\\/]+", p) if x]
        return ("\\\\" + "\\".join(parts[:2])) if len(parts) >= 2 else None
    if NET_FAKE_ROOTS:                               # pruebas
        np_ = os.path.normcase(os.path.normpath(p))
        for r in NET_FAKE_ROOTS:
            nr = os.path.normcase(os.path.normpath(r))
            if np_ == nr or np_.startswith(nr.rstrip("\\/") + os.sep):
                return r
    if IS_WIN and len(p) >= 2 and p[1] == ":":
        letter = p[:2].upper()
        return letter if _drive_is_remote(letter) else None
    return None


def _net_probe(root, st):
    try:
        if root in NET_FAKE_OFFLINE:
            time.sleep(3.0)
            ok = False
        else:
            ok = os.path.isdir(root + ("\\" if IS_WIN and len(root) == 2 else ""))
    except Exception:
        ok = False
    with _NET_LOCK:
        st["ok"], st["t"], st["busy"] = ok, time.monotonic(), False
    st["ev"].set()


def reachable(path, timeout=0.6):
    """True si la ruta es local o su servidor responde. Nunca bloquea más de `timeout`."""
    root = net_root(path)
    if not root:
        return True
    now = time.monotonic()
    with _NET_LOCK:
        st = _NET.setdefault(root, {"ok": None, "t": 0.0, "busy": False, "ev": _thr.Event()})
        fresh = st["ok"] is not None and now - st["t"] < (_NET_OK_TTL if st["ok"] else _NET_BAD_TTL)
        if fresh or st["busy"]:
            return bool(st["ok"])
        st["busy"] = True
        st["ev"] = _thr.Event()
        ev = st["ev"]
    _thr.Thread(target=_net_probe, args=(root, st), daemon=True).start()
    ev.wait(timeout)
    with _NET_LOCK:
        if st["busy"]:              # no contestó a tiempo: por ahora, caída (el chequeo sigue en su hilo)
            if st["ok"] is None:
                st["ok"] = False
            return False
        return bool(st["ok"])


def net_offline_roots():
    with _NET_LOCK:
        return [r for r, st in _NET.items() if st["ok"] is False]


_ISDIR = {}          # ruta de red -> [resultado, momento, chequeando]
_ISDIR_TTL = 30.0


def safe_isdir(path, timeout=0.6):
    """isdir que no traba con carpetas de red: si el servidor está lento (un NAS despertando), contesta lo
    último conocido (o que sí, si el servidor responde) y lo confirma en otro hilo."""
    if not path:
        return False
    if not net_root(path):
        return os.path.isdir(path)
    if not reachable(path, timeout):
        return False
    now = time.monotonic()
    with _NET_LOCK:
        st = _ISDIR.get(path)
        if st and (now - st[1] < _ISDIR_TTL or st[2]):
            return st[0]
        st = _ISDIR.setdefault(path, [True, 0.0, False])
        st[2] = True
        ev = _thr.Event()

    def work():
        try:
            r = os.path.isdir(path)
        except Exception:
            r = False
        with _NET_LOCK:
            st[0], st[1], st[2] = r, time.monotonic(), False
        ev.set()
    _thr.Thread(target=work, daemon=True).start()
    ev.wait(min(timeout, 0.25))
    return st[0]


_PRETTY_UPPER = {"3d": "3D", "2d": "2D", "vfx": "VFX", "fx": "FX", "cg": "CG", "hdri": "HDRI", "hdr": "HDR",
                 "exr": "EXR", "pbr": "PBR", "4k": "4K", "8k": "8K", "2k": "2K", "1k": "1K", "16k": "16K",
                 "uv": "UV", "ai": "AI", "fbx": "FBX", "usd": "USD", "obj": "OBJ", "dmp": "DMP", "sfx": "SFX",
                 "ui": "UI", "suv": "SUV", "vdb": "VDB", "abc": "ABC", "usdz": "USDZ", "rgb": "RGB", "lut": "LUT", "aces": "ACES", "ocio": "OCIO", "tv": "TV"}


def pretty_name(name, keep_ext=False):
    """«01_assets_3d» → «Assets 3D» (solo para mostrar): saca el número de orden del principio, cambia _ por
    espacios, mayúscula al comienzo de cada palabra y siglas conocidas en mayúsculas (3D, 2D, VFX, HDRI…)."""
    base, ext = (os.path.splitext(name) if keep_ext else (name, ""))
    t = re.sub(r"^\d{1,3}[ _.-]+(?=\D)", "", base)          # 01_ · 02 - · 3. (si sigue texto)
    t = re.sub(r"[_]+", " ", t).strip()
    words = []
    for w in t.split(" "):
        if not w:
            continue
        lw = w.lower()
        if lw in _PRETTY_UPPER:
            words.append(_PRETTY_UPPER[lw])
        elif w[0].isalpha():
            words.append(w[0].upper() + w[1:])
        else:
            words.append(w)
    out = " ".join(words) or base
    return out + ext


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


def group_files(dirpath, files, collapse=True):
    """files: lista de (nombre, size, mtime). Devuelve Entries de secuencias y archivos."""
    groups = {}
    if not collapse:
        return [Entry(kind="file", dirpath=dirpath, name=name, path=os.path.join(dirpath, name),
                      ext=os.path.splitext(name)[1].lower(), size=size, mtime=mtime) for name, size, mtime in files]
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


def scan_dir(path, show_hidden=False, collapse=True):
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
    return dirs + group_files(path, files, collapse)


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
        _DRIVE_TYPES[letter] = dtype == 4
        buf = ctypes.create_unicode_buffer(261)
        # con una unidad de red caída, GetVolumeInformation traba: solo si responde
        if (dtype != 4 or reachable(root, 0.3)) and \
                k32.GetVolumeInformationW(ctypes.c_wchar_p(root), buf, 261, None, None, None, None, 0):
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
            if d["kind"] != "network" or reachable(d["root"], 0.3):
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
        elif cat == "raw":
            if e.ext not in RAW_EXTS:
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


DEFAULT_COLOR_FILTERS = """\
# Color filters: pattern = text color   (or  = text color, background color)
# Several patterns with ;  ·  dir: only folders  ·  case-insensitive, * and ? allowed
*.exe;*.msi;*.bat;*.cmd = #ff5c5c
*.zip;*.rar;*.7z = #ff9f43
# *.nk;*.gizmo = #f5a623
# *.max;*.hip;*.hipnc;*.blend = #4cc2ff
# *.mov;*.mp4 = #c49bff
# dir:_input = #3ecf8e
# *_v001* = #ffffff, #5a1f1f
"""


def parse_color_filters(text):
    """→ [(patrones, solo_carpetas, color_texto, color_fondo)] en orden (gana la primera que coincide)."""
    rules = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        pat, col = line.rsplit("=", 1)
        cols = [c.strip() for c in col.split(",")]
        fg = cols[0] if cols and cols[0].startswith("#") else None
        bg = cols[1] if len(cols) > 1 and cols[1].startswith("#") else None
        pat = pat.strip()
        only_dirs = pat.lower().startswith("dir:")
        if only_dirs:
            pat = pat[4:]
        pats = [x.strip().lower() for x in pat.split(";") if x.strip()]
        if pats and (fg or bg):
            rules.append((pats, only_dirs, fg, bg))
    return rules


def color_filter_match(rules, name, is_dir):
    import fnmatch
    n = name.lower()
    for pats, only_dirs, fg, bg in rules:
        if only_dirs and not is_dir:
            continue
        if any(fnmatch.fnmatchcase(n, x) for x in pats):
            return fg, bg
    return None


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
        "tree_lines_style": "chevron",  # chevron (› + línea del camino) | solid | dotted
        "tree_trace": True,             # Tree Path Tracing 
        "tree_trace_width": 1,
        "tree_trace_color": "accent",   # accent | folder
        # 0.5
        "pipeline_location": "center",  # center | sidebar | hidden
        "pipeline_depts": "",           # vacío = todas las carpetas del shot (3D, Comp, DMP…)
        "group_mode": "auto",           # auto | none | folder | type
        "scrub_thumbs": True,
        # 0.6
        "folder_color": "yellow",       # yellow (Windows) | blue
        "splitter_left2": "",
        "cfg_version": 14,
        "pipeline_task_depts": None,    # None = "3D": departamentos que tienen tasks
        "pipeline_stages": None,        # None = "1_projects, 2_review, 3_publish"
        "pipeline_templates": {},       # (0.17, reemplazado por pipeline_departments)
        "pipeline_departments": None,   # None = DEFAULT_DEPTS (o lo que había en la config vieja)
        "pipeline_only_depts": None,
        "pipeline_input": None,         # carpeta de plates dentro del shot (None = "_input")
        "pipeline_input_subs": None,    # sus subcarpetas (None = "plates, refs"); la primera = plates    # el desplegable Dept muestra solo los definidos
        "sys_view_defaults": 0,         # vistas por defecto de Downloads / Videos ya aplicadas
        # 0.7
        "lib_favorites": [],            # acceso rápido de la VFX Library
        "quick_tags": None,             # None = pastillas por defecto (DEFAULT_QUICK_TAGS)
        "lib_tree_line_color": "#ffcf48",     # amarillo: las carpetas de la librería son celestes
        "splitter_left3": "",
        "hidden_sys": ["onedrive"],
        "collapse_seqs": True,
        "mini_tree_on": True,
        "hover_box": True,
        "image_viewer": "",             # programa para abrir imágenes (vacío = el predeterminado de Windows)
        "lib_slots": [None, None, None, None],
        "lib_tree_autocollapse": True,  # VFX Library: el árbol cierra las carpetas fuera del camino actual
        "lib_tree_sort_name": True,     # VFX Library: raíces por nombre (si no, en el orden en que se agregaron)
        "lib_folder_pdf": True,
        "lib_pretty_names": True,       # VFX Library: «01_assets_3d» se ve «Assets 3D» (F2 muestra el nombre real)         # VFX Library: el PDF de la carpeta (o de una madre) se ve en Details   # canales del player de la librería (Ctrl / Shift + 1…4)
        "col_layouts": {},              # layouts de columnas propios {nombre: [columnas en orden]}
        "col_order": None,              # orden de columnas del último layout aplicado              # preview flotante al dejar el mouse sobre un ítem           # árbol solo con las carpetas visitadas
        "mini_tree": [],                # carpetas visitadas (más recientes primero)          # secuencias de imágenes en una sola entrada
        "lib_show_images": True,        # VFX Library: mostrar imágenes sueltas (jpg de capturas, etc.)
        "hidden_drives": [],
        "list_cols": {},
        "system_icons": True,           # ícono original de programas/documentos (no en imágenes, video, audio)
        "dual_orient": "h",             # doble panel: h = lado a lado (F9) · v = uno arriba del otro (F10)
        "color_filters_on": False,      # pintar nombres por tipo / patrón
        "color_filters": None,          # None = DEFAULT_COLOR_FILTERS
        "list_row_numbers": True,        # numeración de filas en Detalles                 # columnas de Detalles tildadas/destildadas
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
            if int(saved.get("cfg_version", 0)) < 9:            # 0.12: árbol con chevrons, acento celeste
                self.data["tree_lines_style"] = "chevron"
                self.data["tree_trace_width"] = 1
                if self.data.get("lib_tree_line_color") == "#8d6fd1":
                    self.data["lib_tree_line_color"] = "#4cc2ff"
                self.data["cfg_version"] = 9
            if int(saved.get("cfg_version", 0)) < 10:           # 0.15: OneDrive en Quick access, oculto
                hs = list(self.data.get("hidden_sys") or [])
                if "onedrive" not in hs:
                    hs.append("onedrive")
                self.data["hidden_sys"] = hs
                self.data["cfg_version"] = 10
            if int(saved.get("cfg_version", 0)) < 11:           # 0.22: librería con línea amarilla, hover box off
                if self.data.get("lib_tree_line_color") in ("#4cc2ff", "#8d6fd1", None):
                    self.data["lib_tree_line_color"] = "#ffcf48"
                self.data["hover_box"] = False
                self.data["cfg_version"] = 11
            if int(saved.get("cfg_version", 0)) < 12:           # 0.23: hover box de nuevo (solo imágenes y PDF)
                self.data["hover_box"] = True
                self.data["cfg_version"] = 12
            if int(saved.get("cfg_version", 0)) < 13:           # 0.27: imágenes con la app del sistema
                self.data["cfg_version"] = 13
            if int(saved.get("cfg_version", 0)) < 14:           # 0.27.1: Fotos con anterior/siguiente en esta PC
                self.data.pop("image_opener", None)          # (opción vieja, ya no existe)
                self.data["cfg_version"] = 14
        except Exception:
            pass

    def _import_studio_toolbar(self):
        """0.11: el pipeline ya no lee la config de the toolbar; si se usaba, se copia una vez."""
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
