# VFX Explorer

![Version](https://img.shields.io/badge/version-0.2.0-informational) ![Platform](https://img.shields.io/badge/platform-Windows-555) ![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white) ![Qt](https://img.shields.io/badge/PySide-6-41CD52?logo=qt&logoColor=white) [![Build](https://github.com/javibravo-vfx/VFX-Explorer/actions/workflows/build.yml/badge.svg)](https://github.com/javibravo-vfx/VFX-Explorer/actions/workflows/build.yml)

Explorador de archivos **liviano y portable** pensado para VFX: secuencias EXR como un solo ítem, thumbnails de EXR, HDR, TX y videos, pestañas, doble panel, librería de assets con tags, rating y colecciones, y la navegación de pipeline de [Studio Toolbar](https://github.com/javibravo-vfx/StudioToolbar-max).

![VFX Explorer](docs/screenshot.png)

## Descarga

Bajá `VFXExplorer-win64.zip` desde **[Releases](https://github.com/javibravo-vfx/VFX-Explorer/releases)**, descomprimilo donde quieras (otro disco, el NAS, un pendrive) y abrí `VFXExplorer.exe`. No hace falta instalar nada.

Para thumbnails e info de videos, copiá `ffmpeg.exe` y `ffprobe.exe` en la carpeta `bin\`.

## Funciones

| | |
|---|---|
| **Secuencias** | `plate.1001.exr … plate.1100.exr` → un ítem `plate.####.exr` con rango, frames, tamaño total y **frames faltantes** en rojo. No confunde versiones (`_v001`) con frames |
| **Thumbnails** | EXR (multicapa, tileados con mips, ACEScg / ACES2065-1 → sRGB, detección por chromaticities), HDR, TIFF de 16 y 32 bits, TX, DPX, PSD, TGA, JPG/PNG con alpha sobre damero, MOV/MP4/MXF vía ffmpeg. Caché en disco |
| **Previews de modelos y carpetas** | `.max`, `.fbx`, `.abc`, `.usd`, `.blend`… usan el JPG/PNG con el mismo nombre (`rock.max` → `rock.jpg`, `rock_thumb.png`, o dentro de `thumbs/` o `previews/`). Las carpetas usan su `thumbnail.jpg`, `preview.png`, `cover.jpg` o la imagen con el nombre de la carpeta |
| **Pestañas** | Ctrl+T, Ctrl+W, click del medio en una carpeta la abre en pestaña nueva, se reordenan arrastrando y se recuerdan al cerrar |
| **Doble panel** | F9 lo activa y F6 cambia de panel. Copiar o mover al otro panel desde el menú, o arrastrando entre paneles |
| **Breadcrumb** | Cada tramo de la ruta es clickeable y el `›` despliega sus subcarpetas. Click en el espacio vacío (o Ctrl+L) para escribir la ruta |
| **Operaciones** | Copiar / cortar / pegar (Ctrl+C/X/V, compatible con el Explorador), copia y movimiento con progreso y cancelación, Supr manda a la papelera, F2 renombra y **renumera secuencias** (ej. 1 → 1001), Ctrl+Shift+N crea carpeta. Las secuencias se tratan siempre como un solo ítem |
| **Librería de assets** | Etiqueta de color, rating ★1–5 (Ctrl+0…5), tags (Ctrl+E) y colecciones que agrupan assets de distintas carpetas sin moverlos. El sidebar lista tags y colecciones; un click muestra todo lo que tiene ese tag o rating |
| **Búsqueda** | Nombre, `*comodines*`, `#tag`, `★3` (rating mínimo), filtro por tipo y **Sub** para buscar en todas las subcarpetas |
| **Pipeline** | Proyecto → Secuencia → Shot → Task, con la misma estructura y configuración que Studio Toolbar (`T:\VFX-{PROY}\{SEQ}\{SHOT}\3D\{TASK}\`). Elegir un nivel navega ahí; el botón de carpeta lleva al shot, al task o a sus subcarpetas (`1_projects`, `2_review`, `3_publish`…). Al navegar, los combos se sincronizan solos |
| **Info** | Resolución, data window, compresión, canales/AOVs, partes, mipmaps y chromaticities de EXR; codec, fps, duración, timecode y pixel format de video |
| **Copiar ruta** | `plate.####.exr`, formato Nuke `plate.%04d.exr 1001-1100`, ruta Windows, primer frame o carpeta |

## Atajos

| Tecla | Acción |
|---|---|
| Enter / doble click | Abrir (secuencias y videos en el reproductor configurado) |
| Backspace · Alt+↑ | Subir |
| Alt+← / Alt+→ · botones del mouse | Atrás / Adelante |
| Ctrl+T / Ctrl+W / Ctrl+Tab | Pestaña nueva / cerrar / siguiente |
| F9 / F6 | Doble panel / cambiar de panel |
| Ctrl+C / Ctrl+X / Ctrl+V | Copiar / cortar / pegar archivos |
| Ctrl+Shift+C · Ctrl+Alt+C | Copiar ruta `####` · ruta Nuke |
| F2 | Renombrar / renumerar |
| Supr | Mandar a la papelera |
| Ctrl+Shift+N | Carpeta nueva |
| Ctrl+E · Ctrl+0…5 | Tags · rating |
| Ctrl+L · Ctrl+F | Escribir ruta · buscar |
| Ctrl+1 / Ctrl+2 | Grilla / lista |
| F5 | Refrescar |

## Configuración

En ⚙:
- **Reproductor**: mrv2, DJV u OpenRV para abrir secuencias y videos con doble click.
- **Espacio de color EXR**: ACEScg por defecto.
- **Pipeline**: por defecto lee `%USERPROFILE%\.studio-toolbar\pipeline_config.ini`, la misma configuración que la toolbar. Si no existe, usa la raíz, el prefijo y las exclusiones que pongas acá.

Todo lo de VFX Explorer (favoritos, pestañas, colores, tags, colecciones, caché de thumbnails) se guarda en `VFXExplorer_data\`, junto al exe. Si esa carpeta no tiene permisos de escritura, va a `%APPDATA%\VFX Explorer`.

> Borrar en una unidad de red (NAS) es definitivo, salvo que la papelera de red del NAS esté activada en esa carpeta compartida. VFX Explorer te avisa antes.

## Desarrollo

```bat
build.bat              :: crea .venv, instala dependencias y compila dist\VFXExplorer
run.bat                :: corre desde el código
python tests\test_core.py
```

Cada push a `main` compila el exe en GitHub Actions; el zip queda como artifact del workflow. Un tag `v*` crea un Release con el zip:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

Estructura: `vfxexplorer/core.py` (secuencias, búsqueda), `imaging.py` (OpenImageIO / Qt / ffmpeg), `library.py` (tags, rating, colecciones), `pipeline.py` (Studio Toolbar), `fileops.py`, `models.py`, `pane.py`, `widgets.py`, `mainwindow.py`.
