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


def open_image(path, mode="default"):
    """mode: default (Fotos con anterior/siguiente si es la app predeterminada) · photoviewer · system."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if mode == "photoviewer" and open_photo_viewer(path):
            return "photoviewer"
        if mode in ("default", "photos") and (mode == "photos" or default_is_photos(ext)):
            open_in_photos(path)
            return "photos"
    except OSError:
        pass
    os.startfile(path)
    return "system"
