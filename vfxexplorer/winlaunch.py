# -*- coding: utf-8 -*-
"""Abrir imágenes en Windows de forma que el visor pueda pasar a las otras de la carpeta.

· Fotos de Windows (la app nueva): solo muestra anterior / siguiente si se la abre con su URI
  «ms-photos:viewer?fileName=<ruta codificada>» (lo mismo que hace Total Commander desde 2024/2025).
  Abrir el archivo directo, o con NeighboringFilesQuery, la deja con una sola imagen.
· Visualizador de fotos clásico: recorre la carpeta solo.
Todo es instantáneo (sin hilos ni esperas)."""

import os
import subprocess
from urllib.parse import quote

PHOTO_VIEWER = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Photo Viewer",
                            "PhotoViewer.dll")
PHOTOS_APPID = "appx43hnxtbyyps62jhe9sqpdzxn1790zetc"      # ProgId de Fotos (Microsoft.Windows.Photos)


def default_is_photos(ext):
    """¿La app predeterminada de esta extensión es Fotos de Windows?"""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice")
        prog, _ = winreg.QueryValueEx(k, "ProgId")
        winreg.CloseKey(k)
        return PHOTOS_APPID in str(prog).lower() or "microsoft.windows.photos" in str(prog).lower()
    except OSError:
        pass
    try:                                     # sin elección del usuario: la de fábrica de Windows 10/11 es Fotos
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext)
        prog, _ = winreg.QueryValueEx(k, "")
        winreg.CloseKey(k)
        return PHOTOS_APPID in str(prog).lower()
    except OSError:
        return False


def open_in_photos(path):
    uri = "ms-photos:viewer?fileName=" + quote(os.path.normpath(path), safe=":\\")
    os.startfile(uri)


def open_photo_viewer(path):
    """Visualizador de fotos clásico de Windows: recorre solo las imágenes de la carpeta."""
    if not os.path.isfile(PHOTO_VIEWER):
        return False
    subprocess.Popen(["rundll32.exe", f"{PHOTO_VIEWER},ImageView_Fullscreen", os.path.normpath(path)])
    return True


# ---------------------------------------------------------------- unidades remapeadas a esta misma PC
_LOCAL_CACHE = {}


def _this_pc_names():
    import socket
    names = {"localhost", "127.0.0.1", "::1", "."}
    for n in (os.environ.get("COMPUTERNAME", ""), socket.gethostname()):
        if n:
            names.add(n.lower())
            names.add(n.split(".")[0].lower())
    return names


def _unc_of_drive(letter):
    """T: → \\\\servidor\\share (si es una unidad de red mapeada)."""
    import ctypes
    from ctypes import wintypes
    buf = ctypes.create_unicode_buffer(1024)
    n = wintypes.DWORD(1024)
    r = ctypes.windll.mpr.WNetGetConnectionW(ctypes.c_wchar_p(letter), buf, ctypes.byref(n))
    return buf.value if r == 0 else None


def _local_share_path(share):
    """Carpeta real de un recurso compartido de esta PC (lo que Windows guarda al compartir)."""
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\LanmanServer\Shares")
        val, _ = winreg.QueryValueEx(k, share)
        winreg.CloseKey(k)
    except OSError:
        return None
    for line in (val if isinstance(val, (list, tuple)) else str(val).split("\0")):
        if line.lower().startswith("path="):
            return line[5:]
    return None


def local_path(path):
    """Si la ruta está en una unidad de red que en realidad es una carpeta compartida de esta misma PC
    (T: → \\\\estaPC\\share), devuelve la ruta local real (D:\\…): Windows la trata como local, sin avisos
    de seguridad y más rápido. Si no, la misma ruta."""
    try:
        p = os.path.normpath(path)
        if p.startswith("\\\\"):
            unc, rest = p, ""
        elif len(p) >= 2 and p[1] == ":":
            letter = p[:2].upper()
            if letter not in _LOCAL_CACHE:
                _LOCAL_CACHE[letter] = _unc_of_drive(letter)
            unc = _LOCAL_CACHE[letter]
            if not unc:
                return path
            rest = p[2:].lstrip("\\")
        else:
            return path
        parts = [x for x in unc.split("\\") if x]
        if len(parts) < 2 or parts[0].lower() not in _this_pc_names():
            return path
        base = _local_share_path(parts[1])
        if not base:
            return path
        extra = parts[2:] + ([rest] if rest else [])
        lp = os.path.join(base, *extra) if extra else base
        return lp if os.path.exists(lp) else path
    except Exception:
        return path


def open_image(path, mode="auto"):
    """mode: auto (Fotos con anterior/siguiente si es la app predeterminada y el archivo está en esta PC;
    si no, la app predeterminada) · system · photos (Fotos con anterior/siguiente siempre) · photoviewer."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if mode == "photoviewer" and open_photo_viewer(path):
            return "photoviewer"
        if mode in ("auto", "photos") and default_is_photos(ext):
            lp = local_path(path)                  # remapeo local → ruta real: sin aviso y más rápido
            is_local = not lp.startswith("\\\\") and _unc_of_drive(lp[:2].upper()) is None
            if mode == "photos" or is_local:
                open_in_photos(lp)
                return "photos"
    except OSError:
        pass
    os.startfile(path)
    return "system"
