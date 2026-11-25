# Changelog

## 0.23.0
- Blow Up (hold on the Details preview): true 1:1 pixels (Windows display scaling taken into account), opens at the real size right away, and moving the mouse pans the whole image in every direction (reaching a screen edge shows that edge of the image).
- Hover box back on, only for images, image sequences and PDFs (no videos or folders).
- Double-clicking an image opens it in the default app with its neighboring images, like from Windows Explorer: in Photos you can go to the next / previous image of the folder.

## 0.22.0
- Mouse Down Blow Up in the Details pane: hold the mouse button on the preview to see the image at 100 % (full-resolution EXR, image, video frame or PDF page), centered on the point you pressed; move to pan, release to close. The floating hover box is now off by default (View › Hover box).
- F7 in the VFX Library goes back to the previous folder with the same video selected and playing from where it was — press again to go back: handy for comparing two videos.
- VFX Library: folders are light blue (unless they have their own color) and the tree line is yellow.
- VFX Library: clicking the empty part of the top tab bar no longer jumps to File Explorer, so the window can be moved from there.
- First start: wider left panel so its new buttons fit.
- Portable: the generic-icon probe file is kept inside VFXExplorer_data (nothing written to the system temp folder).

## 0.21.0
- Folder tree with This PC as its root (in the full tree and the Mini tree): the path line starts at This PC, and going to This PC selects it (no grey box left on the last folder). The full tree reads folders by itself, network drives only when they answer.
- Mini tree like the reference: only drives and folders you went into, everything open.
- Corner of FILE EXPLORER: the eye's place shows scissors in Mini tree (clear it), then a new tree button to switch Mini / full tree.
- Settings › Pipeline: the department fields keep their width when a department has tasks; new "Plates / input folder" (default _input with plates, refs): the ＋ creates it and the folder button jumps to the plates.

## 0.20.0
- Reopen closed tabs with Ctrl+Shift+T (with their back/forward history), also from the tab right-click menu.
- File hashes: right-click a file › File hashes shows its MD5, SHA-1 and SHA-256 (read once, in the background), with Copy and a Compare box to check a pasted hash.

## 0.19.0
- Network without freezing: a NAS or mapped drive that is off no longer hangs the app (startup, VFX Library, tabs, tree, This PC). It shows "(offline)", checks again by itself and comes back when the server answers.
- F7: go to the previous location and back (between the last two).
- Hover box: leave the mouse over an item for a large preview next to the cursor (image, first frame, video, PDF, text, folder contents). View › Hover box turns it off.
- Column layouts (right-click the column titles or View › Column layout): Standard, VFX, Video, Minimal, and your own. New columns Resolution, FPS, Codec, Channels and Colorspace, read in the background.
- 6 Key Navigation in the address bar: → at the end of a folder lists its subfolders, Ctrl+← / Ctrl+→ jump between folders of the path, Ctrl+↓ lists at the cursor, ↑ ↓ choose, Ctrl+↑ closes, Enter goes, Ctrl+Enter opens the file / the folder in a new tab.
- Mini tree (on by default): the folder tree shows only the folders you visited; the tree button switches to the full tree.

## 0.18.1
- The folder PDF no longer opens by itself in Details (it was meant only for a future 3D Library).
- VFX Library images button: turning it on or off reloads the folder, so the images come back without pressing Refresh.

## 0.18.0
- Settings › Pipeline unified: one list of departments (Department 1, 2…), each with its folder, whether it has tasks, its tasks and its folders. Replaces "Departments", "Departments with tasks", "Stage folders" and the New folders tab (old settings are carried over).
- Pipeline ＋ works for any department: tasks for departments with tasks, the department with its folders for the others.
- Option: the Dept dropdown shows only the listed departments.
- A folder with a PDF opens it in the Details pane by itself (nothing selected).

## 0.17.0
- Pipeline ＋: creates a 3D task (with its subfolders), DMP or Comp in the current shot; existing ones are checked off.
- Settings › New folders: edit the 3D tasks (and what goes inside 1_projects for each), the task folders, DMP and Comp subfolders.
- Downloads starts grouped by date modified and Videos in Large icons (reset once on update).
- App icon: one big folder with the marker and a second one tucked right behind.

## 0.16.0
- Sequence collapse button in the status bar (left of Subfolders): off shows every frame as its own file.
- VFX Library: Large icons by default for every folder (its views are remembered apart from File Explorer).
- VFX Library: images button in the tags bar to hide/show loose images (jpg, png…); sequences and videos stay.
- TAGS gets the same left margin as PIPELINE.
- App icon: two folders in the Windows folder yellow with the Explorer blue marker.

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
