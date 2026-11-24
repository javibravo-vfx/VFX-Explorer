# Changelog

## 0.15.2
- App icon: the marker is now viewfinder corners with a center cross, in cyan.

## 0.15.1
- App icon: light-blue tracking marker on the front folder, drawn per size (16–256 px) in the .ico and the window icon.

## 0.15.0
- App icon: back to the stacked-folders design, now yellow-orange with a light-blue dot.
- Folders with image sequences or images open in Large icons (until you choose another view).
- Downloads is grouped by date (newest first) by default.
- OneDrive in Quick access, hidden by default (show it with the eye).
- Del sends to the Recycle Bin right away; Shift+Del deletes permanently and asks first.
- New folder creates «New folder» and leaves its name ready to edit, like Windows.

## 0.14.2
- Tab close × back to a normal size.
- The Details pane keeps the width you chose whatever you select (text files and long names no longer widen it).
- Dragging the Details pane closed turns the Details button off; turning it on brings it back at its minimum width.
- This PC is the top level: Up is disabled there.

## 0.14.1
- Original file icons are centered in the grid on scaled displays (125%, 150%…); generic "unknown type" icons fall back to the type badge.
- Bigger tab close button (×), further from the edge.

## 0.14.0
- **PDF preview** in the Details pane (pages one below the other, at the pane width) and PDF thumbnails in the grid.
- **Original icons** of programs and documents (exe, zip, pdf, office…), not for images, video or audio; can be turned off in ⚙ › General.
- **WinRAR** in the right-click menu when it's installed: extract here / to folder / files…, open, add to .rar / .zip.
- **RAW filter**: camera RAW formats and DNG.
- **This PC opens in Large icons** and remembers its view if you change it (also when going back to it).
- **Details pane**: minimum width like Windows; it can't be dragged narrower and turns itself off when the window gets too narrow (and comes back when there's room). Its contents fit the pane width (long names and paths wrap, the preview scales).
- **⚙ › Reset all**: clears the cache and every setting and restarts as the first time. **Color filters** have their own settings tab; `.zip`, `.rar`, `.7z` in orange by default.
- Search box a bit narrower (it still grows with the window); the background behind ← → ↑ ⟳ and the search box matches the address bar again.
- Taller drive bars in This PC.
- New app icon with yellow folders.

## 0.13.0
- **One search box and one ← → ↑ ⟳** for File Explorer: they work on the active pane. In dual pane each pane only has its tabs, address bar and filter.
- **Dual pane one above the other** (F10) besides side by side (F9); two icon buttons in the toolbar.
- **Color filters** button: paints file names by pattern (default: `.exe`, `.msi`, `.bat` in red). Rules in ⚙ › Colors (`pattern = color` or `= text, background`, `dir:` for folders).
- **Text files** (.ini, .txt, .json, .nk, .py…) are shown in the whole Details pane, read-only and selectable.
- **Default view is Details** for every folder; This PC keeps its tiles and Pictures opens in Large icons. The **icon size is remembered per folder** too.
- The **View** button shows the current view. Toolbar order: New, Sort, View, ⋯.
- **Filter** moved between the address bar and the search box: fixed width, highlighted with a small drawing of the type (or «EXR») when on.
- Pipeline dropdowns read nicer: `_input` → INPUT, `comp` → COMP, `8_lighting` → Lighting (only in the dropdown). The last one says Task (3D), Stage (Comp, DMP) or Shot (INPUT).
- Row numbers can be turned off from the column headers menu.
- Closing the only tab closes the app (in dual pane it closes that pane).
- Quick access only highlights the current folder (follows navigation and tab changes).
- Double-click the empty space of the list or the tree to go up one level.
- References to other programs removed from the app.

## 0.12.0
- **New tree style**: › / ⌄ chevrons and a single thin path line to the current folder (no gray lines or ⊞ boxes). The old style is still in ⚙ › Colors.
- **Row numbers** in Details (View › Row numbers).
- **Subfolders switch** at the bottom of the center pane: off · 1 level · the whole branch (Ctrl+B steps through).
- **Pipeline bar spans the center pane**, aligned with it (dividers at both edges), and follows the splitters. New and View shrink to icons when the left pane is narrow; **Sort** moved between the address bar and the search box.
- **Active file-type filter** shows its name highlighted (e.g. «Sequences»).
- **This PC** tiles like Windows: narrower, more drives per row.
- **Quick access**: Documents added. Dragging a folder over the VFX LIBRARY tab no longer switches Quick access (the tree only switches after hovering a moment, and comes back after the drop).
- Dragging from the VFX Library to a File Explorer folder **copies without asking**.
- The **Details pane** is remembered per folder too.
- Light-blue accent for the pipeline, the VFX Library and Dual pane / Details; gear icon for Settings; darker title and tab bar; the empty space of the tab bar moves the window (double click maximizes).
- Bigger type in the grid; cleaner ＋ next to the quick tags.

## 0.11.0
- **ffmpeg included** in `bin\` (LGPL build): videos play and get thumbnails/info without downloading anything. The CI selftest now checks video.
- **Grid names centered** and wrapped on up to two lines, like Windows.
- **Standalone pipeline settings**: everything is set in ⚙ › Pipeline.
- **Departments with or without tasks**: 3D › Task › Stage; Comp / DMP go straight to the stages (the last dropdown becomes «Stage»); `_input` lists its folders («Folder»). Configurable.
- **Switching shot keeps your place**: same dept / task / stage / `_input` subfolder in the new shot when it exists (falls back to the closest parent).

## 0.10.0
- «Folders» mode renamed to **File Explorer**.
- **Right-click on the background** opens a Windows 11 style menu: View, Sort by, Group by, Refresh, Paste, New, Pin, Copy folder path, Open in Windows Explorer and Properties.
- **Group by › Date modified**: Today, Yesterday, Earlier this week, Last week, Earlier this month, Last month, Earlier this year, A long time ago.
- **Every folder remembers its view** (icons/details, sort, grouping). View › «Apply this view to all folders» sets the default.
- **Details columns**: right-click the column headers to tick the columns you want, «Size column to fit» and «Size all columns to fit».
- More breathing room: margins in the file grid / details view, the trees and Quick access; taller rows in Details.

## 0.9.0
- **The whole UI is now in English.**
- New tabs open in **This PC** (Folders mode).
- **Drag a folder onto Quick access** to pin it (from the Folders tree, the VFX Library tree or the center pane).
- **Windows 11 address bar**: taller, bigger type, more spaced buttons, search box ≈ 30% of the width; **⊕ New**, **Sort** and **View** buttons like Explorer.
- **Quick access**: divider between the Windows folders and your pinned ones, pin icon, roomier rows.
- **👁 toggles** (no menus): show hidden Quick access items, and hidden drives in the Folders tree. Hide with right-click › Hide / Hide drive.
- This PC breadcrumb shows «This PC ›» instead of a title.

## 0.8.0
- **Pestañas como Windows 11**: ancho fijo (se achican solo cuando no entran), ícono siempre (carpeta, disco o Este equipo), la activa en negrita, el ＋ pegado a la última.
- **Pestañas de Carpetas siempre arriba**, también en doble panel (una cabecera por panel, alineadas): activar el doble panel ya no mueve la interfaz. Click en las pestañas de un panel lo activa; desde la VFX Library, vuelve a Carpetas.
- **VFX Library con sus pestañas en el centro**, entre el viewer y los elementos.
- **Arrastrar de la VFX Library a una pestaña de Carpetas** copia o mueve a esa carpeta.
- **Tabs del panel izquierdo independientes**: cambiar de tab solo muestra el otro árbol; el modo cambia al hacer click en una carpeta (se puede desplegar el árbol de Carpetas para soltar ahí un elemento de la librería).
- **Acceso rápido** con Escritorio, Descargas, Imágenes y Videos (ojito para ocultarlos) y su propio ＋.
- Subcarpetas, Filtrar, Ordenar, Ver y ⋯ al lado del ＋ de la fila del pipeline; **pipeline** más ancho, cubriendo el centro, con divisores.
- En doble panel, cerrar la única pestaña de un panel cierra ese panel.
- Líneas divisorias suaves entre paneles; los botones de ícono ya no se corren al pasar el mouse.

## 0.7.0
- **Nueva disposición** (como el Explorador de Windows 11): pestañas y dirección a todo el ancho, selector **Carpetas / VFX Library** arriba a la derecha, fila con ＋ · pipeline · Doble panel · Detalles · ⚙, y Subcarpetas / Filtrar / Ordenar / Ver / ⋯ en la barra de abajo.
- **Acceso rápido por modo**: uno para Carpetas y otro para la VFX Library, arriba del panel izquierdo.
- **Árbol de la VFX Library** con líneas en otro color (configurable) y path tracing; sigue a la pestaña activa.
- **Tags rápidos** en la VFX Library (Humo, Fuego, Explosión…): filtran toda la rama por nombre, carpeta o tag. Editables.
- **Arrastrar entre los dos mundos**: soltar archivos en las carpetas de los árboles; al arrastrar sobre un tab se muestra su árbol.
- **Botón de colores** con los modos (manual, por proyecto, por nombre, ambos) en lugar del combo.

## 0.6.0
- **Este equipo**: discos y ubicaciones de red con barras de uso, como en Windows 11 (también en la barra de dirección y al subir desde la raíz de un disco).
- **Panel izquierdo en dos tabs**: Carpetas / VFX Library, sincronizados con el modo del panel central.
- **Pipeline** horizontal sobre el panel central por defecto (también panel izquierdo u oculto).
- **Carpetas amarillas** estilo Windows por defecto; el celeste queda como opción en ⚙ › Colores.

## 0.5.0
- **Viewer: AOVs / canales de EXR**: selector de capa (beauty, alpha, depth, normales…); las capas de datos se ven sin conversión de color y normalizadas.
- **Scrub** en los thumbnails de secuencias y videos.
- **Agrupar por carpeta o tipo**; con Subcarpetas, agrupado automático por subcarpeta (estilo Found).
- **Pipeline**: nuevo nivel **Depto** (3D, Comp, DMP…) entre Shot y Task; dropdowns en el panel izquierdo, arriba u ocultos, configurable.
- **Explorador y VFX Library separados**: el panel izquierdo lleva al Explorador; la Library no sale de sus carpetas y su dirección arranca en la raíz.

## 0.4.0
- **Look Windows 11**: pestañas estilo Explorador, fila de navegación con barra de dirección y «Buscar en…», barra de comandos (Nuevo, Cortar, Copiar, Pegar, Cambiar nombre, Eliminar, Ordenar, Ver, Filtrar, Subcarpetas, Ver más), panel de Detalles conmutable, botones de vista y tamaño en la barra de estado, tema oscuro Win11 y barra de título oscura.
- **Árbol con líneas**: líneas sólidas (o punteadas), cajitas ⊞/⊟ y Tree Path Tracing (camino hasta la carpeta actual en color de acento), con grosor y color configurables.
- Árbol con scroll horizontal para rutas profundas; indicador de panel activo en doble panel.

## 0.3.0
- **VFX Library**: tab propio con viewer/player arriba y elementos abajo (grilla). Autoplay en loop al moverse con las flechas. Secuencias EXR/JPG/PNG, videos vía ffmpeg e imágenes/HDRIs. Raíces de la librería elegibles desde el panel izquierdo.
- **Subcarpetas** (Ctrl+B): sin texto muestra todos los archivos de la rama; con texto busca en la rama. Banner y carpeta relativa visibles.
- **Colores automáticos** de carpetas por proyecto (más claro en secuencias y shots) y/o por nombre (reglas editables), con selector en el panel de carpetas.
- **Árbol con líneas**, coloreadas con el color de cada carpeta.
- **Tamaño de carpetas** opcional, calculado en segundo plano.
- **Renombrar en el lugar (F2)**, también secuencias completas (cambia el padding según la cantidad de #). «Renumerar secuencia…» queda en el menú.
- Tags, rating y colecciones apagados por defecto (se prenden en Configuración).
- Fix: en la grilla no se podía arrastrar para copiar o mover.
- Fix: los combos de pipeline quedaban con datos viejos al salir del pipeline.

## 0.2.0
- Pestañas por panel (se recuerdan al cerrar) y doble panel (F9 / F6).
- Breadcrumb clickeable, con menú de subcarpetas en cada tramo.
- Operaciones de archivo: copiar / cortar / pegar (compatible con el Explorador), copia y movimiento con progreso, papelera, renombrar, **renumerar secuencias**, carpeta nueva y drag & drop entre paneles y con el Explorador.
- Librería de assets: tags, rating ★1–5, colecciones; sidebar de tags y colecciones; búsqueda con `#tag` y `★N`.
- Barra de pipeline.
- Thumbnails con OpenImageIO: HDR, TIFF de 16 y 32 bits, TX y EXR tileados con mips, DPX, PSD. Lectura por franjas para imágenes enormes.
- Previews de modelos y carpetas con imágenes del mismo nombre (sidecar).
- Build automático en GitHub Actions con selftest del exe; release en tags `v*`.

## 0.1.0
- Primera versión: secuencias agrupadas con frames faltantes, thumbnails EXR/video, colores de carpeta, búsqueda recursiva, panel de info.
