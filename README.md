# VFX Explorer

![Version](https://img.shields.io/badge/version-0.6.0-informational) ![Platform](https://img.shields.io/badge/platform-Windows-555) ![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white) ![Qt](https://img.shields.io/badge/PySide-6-41CD52?logo=qt&logoColor=white) [![Build](https://github.com/javibravo-vfx/VFX-Explorer/actions/workflows/build.yml/badge.svg)](https://github.com/javibravo-vfx/VFX-Explorer/actions/workflows/build.yml)

Explorador de archivos **liviano y portable** pensado para VFX, con la cara del **Explorador de Windows 11** y el manejo de carpetas de **XYplorer**: secuencias EXR como un solo ítem, thumbnails de EXR, HDR, TX y videos, pestañas, doble panel, **VFX Library con viewer/player**, colores automáticos por proyecto y la navegación de pipeline de [Studio Toolbar](https://github.com/javibravo-vfx/StudioToolbar-max).

![VFX Explorer](docs/screenshot.png)

![VFX Library](docs/screenshot-library.png)

## Descarga

Bajá `VFXExplorer-win64.zip` desde **[Releases](https://github.com/javibravo-vfx/VFX-Explorer/releases)**, descomprimilo donde quieras (otro disco, el NAS, un pendrive) y abrí `VFXExplorer.exe`. No hace falta instalar nada.

Para thumbnails e info de videos, copiá `ffmpeg.exe` y `ffprobe.exe` en la carpeta `bin\`.

## Funciones

| | |
|---|---|
| **Estilo Windows 11** | Pestañas como las del Explorador (ancho fijo, ícono, la activa en negrita) y dirección arriba a todo el ancho, con el selector **Carpetas / VFX Library** a la derecha. En doble panel cada panel tiene su cabecera arriba, alineada con él. Debajo, una fila con ＋ (carpeta, pestaña, acceso rápido), Subcarpetas, Filtrar, Ordenar, Ver y ⋯, el **pipeline** (o los tags rápidos en la VFX Library), Doble panel, Detalles y ⚙. Cortar/Copiar/Pegar/Renombrar/Eliminar en el clic derecho y con los atajos de siempre. Tema y barra de título oscuros |
| **Este equipo** | Como en Windows 11: discos locales y ubicaciones de red con etiqueta, letra (y servidor en las unidades de red), barra de uso (roja cuando está casi lleno) y espacio libre. Desde «Este equipo» en el panel izquierdo, el primer tramo de la barra de dirección, o subiendo desde la raíz de un disco |
| **Panel izquierdo** | Arriba **Acceso rápido**, uno para cada mundo: el de Carpetas trae Escritorio, Descargas, Imágenes y Videos (el ojito los oculta) y su ＋ agrega la carpeta actual. Abajo dos tabs, **CARPETAS** (Este equipo y árbol) y **VFX LIBRARY** (árbol de la librería, con ＋ para sumar carpetas). Cambiar de tab solo muestra el otro árbol: el panel central cambia recién al hacer click en una carpeta, así podés abrir el árbol de Carpetas y soltar ahí un elemento de la librería. También se puede soltar sobre una pestaña de Carpetas. Junto a los tabs: botón de **colores automáticos** |
| **Árbol estilo XYplorer** | Líneas finas (sólidas o punteadas), cajitas ⊞/⊟ y **Tree Path Tracing**: una línea de acento marca el camino desde la raíz hasta la carpeta actual. Las líneas pueden tomar el color de cada carpeta. El árbol de la VFX Library usa las mismas líneas con su propio color (violeta por defecto). Soltar archivos sobre una carpeta del árbol copia o mueve ahí (se expande sola si esperás encima). Se configura en ⚙ › Colores |
| **VFX Library** | Modo propio (Ctrl+Shift+L), con sus pestañas en el centro entre el viewer y los elementos, que solo navega **dentro de las carpetas de la librería** (no se puede salir de sus raíces). Tiene su propio árbol y su propio acceso rápido; el ＋ al lado del tab «VFX LIBRARY» elige dónde está tu librería (una o varias carpetas). Arriba hay un viewer y abajo los elementos en grilla: te movés con las flechas y cada uno se reproduce solo, en loop. Reproduce secuencias EXR/JPG/PNG/DPX, videos MOV/MP4 (con ffmpeg) e imágenes / HDRIs. En EXR multicapa, un selector cambia de **AOV / canal** (beauty, alpha, depth, normales…); las capas de datos se muestran sin conversión de color y normalizadas. Espacio: play/pausa · `,` `.`: frame a frame. Elegís los fps y el loop/autoplay se recuerdan |
| **Tags rápidos** | En la VFX Library, donde va el pipeline: pastillas como **Humo, Fuego, Explosión, Chispas, Polvo, Agua…** que muestran todos los elementos de la rama cuyo nombre, carpeta o tag coincide (`Fuego: fire, flame, llama`). Varias prendidas = cualquiera de ellas. ＋ agrega, clic derecho edita, reordena o quita |
| **Scrub en thumbnails** | Pasá el mouse sobre una secuencia o un video en la grilla y se recorren sus frames (con el número de frame) |
| **Agrupar** | Ordenar › Agrupar por: carpeta o tipo. Con **Subcarpetas** se agrupa solo por carpeta, como el «expandir todas las carpetas» de Found: todo el contenido de la rama en una pantalla, ordenado por subcarpeta |
| **Subcarpetas** | El botón **Subcarpetas** (Ctrl+B): sin texto muestra **todos los archivos** de la carpeta y sus subcarpetas; con texto busca en toda la rama. Una barra azul avisa que estás viendo subcarpetas y cada ítem muestra en qué subcarpeta está (↳ renders) |
| **Colores automáticos** | Desde el botón de colores del panel izquierdo: **Por proyecto** (cada proyecto del pipeline con su color, más claro en secuencias y shots), **Por nombre** (reglas como `3D = azul`, `comp = naranja`, editables en ⚙ › Colores) o ambos. El color manual siempre gana. Líneas del árbol estilo XYplorer, con el color de cada carpeta |
| **Secuencias** | `plate.1001.exr … plate.1100.exr` → un ítem `plate.####.exr` con rango, frames, tamaño total y **frames faltantes** en rojo. No confunde versiones (`_v001`) con frames |
| **Thumbnails** | EXR (multicapa, tileados con mips, ACEScg / ACES2065-1 → sRGB, detección por chromaticities), HDR, TIFF de 16 y 32 bits, TX, DPX, PSD, TGA, JPG/PNG con alpha sobre damero, MOV/MP4/MXF vía ffmpeg. Caché en disco |
| **Previews de modelos y carpetas** | `.max`, `.fbx`, `.abc`, `.usd`, `.blend`… usan el JPG/PNG con el mismo nombre (`rock.max` → `rock.jpg`, `rock_thumb.png`, o dentro de `thumbs/` o `previews/`). Las carpetas usan su `thumbnail.jpg`, `preview.png`, `cover.jpg` o la imagen con el nombre de la carpeta |
| **Pestañas** | Ctrl+T, Ctrl+W, click del medio en una carpeta la abre en pestaña nueva, se reordenan arrastrando y se recuerdan al cerrar |
| **Doble panel** | F9 lo activa y F6 cambia de panel (o click en sus pestañas). Cerrar la única pestaña de un panel cierra ese panel. Copiar o mover al otro panel desde el menú, o arrastrando entre paneles |
| **Breadcrumb** | Cada tramo de la ruta es clickeable y el `›` despliega sus subcarpetas. Click en el espacio vacío (o Ctrl+L) para escribir la ruta |
| **Operaciones** | Copiar / cortar / pegar (Ctrl+C/X/V, compatible con el Explorador), arrastrar en grilla o lista (a una carpeta, al otro panel o desde/hacia el Explorador), copia y movimiento con progreso y cancelación, Supr manda a la papelera, Ctrl+Shift+N crea carpeta. Las secuencias se tratan siempre como un solo ítem |
| **Renombrar secuencias** | **F2** edita el nombre en el lugar, como un archivo: `plate_v001.####.exr` → `sh010_plate_v002.####.exr` renombra todos los frames. Cambiar la cantidad de `#` cambia el padding. «Renumerar secuencia…» (clic derecho) cambia el primer frame (ej. 1 → 1001) |
| **Tamaño de carpetas** | Opcional (⚙ › General): se calcula en segundo plano y se ve en la grilla y en la lista |
| **Tags / rating / colecciones** | Apagados por defecto; se prenden en ⚙ › General. Rating ★1–5 (Ctrl+0…5), tags (Ctrl+E) y colecciones que agrupan assets de distintas carpetas sin moverlos |
| **Búsqueda** | Nombre o parte, `*comodines*`, filtro por tipo y **Subcarpetas** para buscar en toda la rama (con tags activos: `#tag`, `★3`) |
| **Pipeline** | Proyecto → Secuencia → Shot → **Depto** (3D, Comp, DMP, 2D…) → Task, con la estructura de Studio Toolbar (`T:\VFX-{PROY}\{SEQ}\{SHOT}\{DEPTO}\{TASK}\`). Los dropdowns van en horizontal sobre el panel central (por defecto), en el panel izquierdo u ocultos (⚙ › Pipeline), y se puede limitar qué carpetas cuentan como departamento. Elegir un nivel navega ahí; el botón de carpeta lleva al shot, al task o a sus subcarpetas (`1_projects`, `2_review`, `3_publish`…). Al navegar, los combos se sincronizan solos, y quedan vacíos en carpetas que no son del pipeline |
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
| F2 | Renombrar en el lugar (también secuencias) |
| Ctrl+B | Subcarpetas: todos los archivos de la rama / buscar en la rama |
| Ctrl+Shift+E / Ctrl+Shift+L | Explorador / VFX Library |
| Espacio · `,` `.` | (VFX Library) play/pausa · frame anterior/siguiente |
| Supr | Mandar a la papelera |
| Ctrl+Shift+N | Carpeta nueva |
| Ctrl+E · Ctrl+0…5 | Tags · rating (si están activos) |
| Ctrl+L · Ctrl+F | Escribir ruta · buscar |
| Alt+Shift+P | Panel de detalles |
| Ctrl+1 / Ctrl+2 | Grilla / lista |
| F5 | Refrescar |

## Configuración

En ⚙:
- **Reproductor**: mrv2, DJV u OpenRV para abrir secuencias y videos con doble click.
- **Espacio de color EXR**: ACEScg por defecto (también se usa en el viewer).
- **Colores**: color de las carpetas (amarillo como Windows o celeste), modo automático y reglas por nombre.
- **VFX Library**: resolución del viewer, memoria para frames (cuánto del loop queda en caché), autoplay y loop.
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

Estructura: `vfxexplorer/core.py` (secuencias, búsqueda), `imaging.py` (OpenImageIO / Qt / ffmpeg), `viewer.py` (player de frames), `library_ui.py` (VFX Library), `colors.py` (colores automáticos), `tree.py` (árbol con líneas), `dirsize.py`, `library.py` (tags, rating, colecciones), `pipeline.py` (Studio Toolbar), `fileops.py`, `models.py`, `pane.py`, `widgets.py`, `mainwindow.py`.
