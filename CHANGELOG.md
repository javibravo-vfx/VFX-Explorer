# Changelog

## 0.37.2
- F9 / F10 (dual pane): the window doesn't paint while tabs and address bars are rearranged, so the quick flash of a tab moving is gone.

## 0.37.1
- Dual pane: the light-blue line that marks the active pane is now drawn at the top of that pane's content, exactly as wide as the pane (before, in top/bottom mode, it ran under the whole address row).

## 0.37.0
- Workspace notes: the right panel has «DETAILS | NOTES». Notes is a to-do list (tick with the box or Space, edit with double-click / F2, Del removes, drag to reorder, right-click › Clear done items) and a free text block. Each workspace has its own notes (Default too); they are saved with the app's settings.
- A small light-blue dot next to NOTES — and on the Details button when the panel is closed — tells that the workspace has something written.

## 0.36.0
- Workspace Pins: in a workspace (not Default) the File Explorer Quick access header becomes «QUICK ACCESS | WORKSPACE PINS». Workspace Pins are folders only that workspace sees; Quick access stays the same for every workspace. Add pins by dragging folders onto the list, with ＋, or right-click › «Pin to Workspace Pins»; rename them with F2 (the folder keeps its name), reorder by dragging, unpin from the menu. Each workspace remembers which of the two lists you were looking at.

## 0.35.0
- Workspaces · «Keep updated» (on by default, in the Workspace menu): each workspace remembers by itself the tabs and panels you open, close or move in it — switching workspaces is like having several windows open. «Update» is not needed (disabled) and «Reset» takes the workspace back to how it was when the app was opened (or created, if it is new).
- Without Keep updated, workspaces work as before: changes are saved with «Update» and «Reset» goes back to the saved layout.
- Default always remembers what you do in it (also after switching to another workspace and back); «Reset Default to zero» leaves it as the first time the app opens.

## 0.34.0
- Quick access: the folders you pinned can get their own name (F2 or right-click › Rename here) without renaming the real folder; the tooltip shows the real path, and «Back to the folder's name» undoes it. Works in File Explorer and in the VFX Library.
- Workspaces: «New workspace…» starts from zero — it asks whether to update the current workspace first, closes the tabs and leaves everything as when the app opens for the first time (one tab, no dual pane, Details on, default panel sizes), then saves it under the new name. Quick access and the VFX Library are not touched.
- Workspaces: built-in «Default» layout at the top of the menu (Alt+Shift+0).

## 0.33.0
- Sharp icons on scaled screens (125 %, 150 %…): the app's icons (This PC, tabs, Quick access, tree, address bar, buttons, folders in the grid) are drawn at the screen's real resolution instead of being stretched.
- Quick access: Desktop, Documents, Downloads, Pictures, Videos, OneDrive and .nuke use line icons in the app's style, each with its color.
- Workspace button: smaller icon (about the size of the filter's), closer to File Explorer, and the name in the same font size as File Explorer.

## 0.32.1
- Workspace button: an icon (window with its panels) with the active workspace's name (cut with … if long) and a down arrow, aligned with File Explorer / VFX Library and a little apart from them. File Explorer / VFX Library have a fixed width, so turning bold when selected doesn't move anything.
- Address bar: the arrows between folders are drawn the size of the New / Sort / View arrows (and point down while the subfolder menu is open).
- Startup: every launch writes VFXExplorer_data/startup.log with how long each step takes (to find what slows it down on each PC). The CI build measures it too: about 1.1 s on a clean Windows.

## 0.32.0
- Workspaces: a «Workspace» button left of File Explorer / VFX Library saves the interface as it is — mode, the tabs of each pane and their folders, view, dual pane and its orientation, Details pane and the panel sizes — and switches between saved layouts, like 3D and editing programs. Save as new, update, reset, rename, reorder and delete; Alt+Shift+1…9 switch to the first nine.
- Filters: «Camera RAW» (only camera RAW / DNG) and the new «Hide Camera RAW» (everything except them). With a file-type filter on, folders are no longer shown in the center pane (they stay with Hide Camera RAW).
- App icon: bigger, it now fills its square like the other taskbar icons.

## 0.31.1
- VFX Library: the video keeps playing while you click other folders or move through the tree with the arrows; it only changes when you pick another video.

## 0.31.0
- VFX Library Details: selecting a video shows its details again, and they follow as you move from video to video.
- «Folder PDF» is now «Cover»: the PDF or cover image of the folder — or of its main folder — stays in Details (an image named cover / preview / portada / thumb / poster…, or named like the folder; in the folder itself also its only image next to other files). Without a cover, or with Cover off, Details shows each selected file (videos included).
- VFX Library tree: a library root that is a folder (not a whole drive) shows its clean name («04_vfx_stock_elements» → «VFX Stock Elements») with its keyword icon; its subfolders use plain folder icons.
- Grouped views (e.g. Downloads by date): the arrow keys skip the group titles («Earlier this week»…).

## 0.30.1
- NAS waking up: found (by simulating every network read as slow) the last reads that ran on the window's thread and moved them to the background — only for network paths, local files work exactly as before:
  - entering a network folder no longer asks the server whether it exists first (the background listing reports it);
  - the player's ffprobe / EXR layer reading for a network file runs in the background ("buffering" meanwhile);
  - text and PDF previews of network files load in the background; PDF pages always render in the background;
  - the Blow Up doesn't read the image header of a network file from the window.

## 0.30.0
- VFX Library tree: with a single library root (e.g. a whole drive) its node is called «VFX Library» (like This PC) instead of the drive letter; several roots show «VFX Library (E:)» for drives.
- VFX Library: main folders get an icon by the words in their name (3D / assets → cube, textures / surfaces → checker, lighting / HDRI → bulb, VDB / simulations → cloud, mocap → figure, VFX / stock / elements → spark, reference → photo, pipeline / tools → wrench, learning → cap, admin → briefcase, incoming → inbox, personal → person, archive / projects → box, library → books, audio → note, fonts → Aa, video / plates → film). The 3D cube is now a true isometric cube.
- VFX Library Details: selecting any file that isn't a video (text, PDF, image, model…) shows it; with Folder PDF on, a folder without PDF or cover clears Details (the cover is taken only from the folder itself).
- Quick access .nuke icon: yellow circle with a black circle inside.
- Diagnostics: if the window gets stuck for more than 2 s, what it was doing is written to VFXExplorer_data/freeze.log (to track the NAS wake-up freeze).

## 0.29.0
- Downloads really opens grouped by date: folders with their own default (Downloads, Pictures…) are no longer switched to Large icons because they contain images (reset once on update).
- NAS waking up no longer freezes the window: network folders in the VFX Library tree and the folder tree are read in the background ("loading…"), library roots and tabs are checked without waiting, the folder PDF / cover is searched in the background, file-type icons come from a local probe (no network access), and navigation doesn't ask the server whether a folder is a file. Tested with every network access taking 2 s: the app opens in about 1 s.
- VFX Library: clean names on by default — «01_assets_3d» shows as «Assets 3D» (no order number, spaces, capitals, 3D / 2D / VFX / HDRI… in upper case), in the tree and the grid; the address bar and F2 show the real name. Settings › VFX Library to turn it off.
- VFX Library: main folders with "3d" in the name get a light-blue rotated cube icon.

## 0.28.1
- Documents back to the normal default view (the date grouping is for Downloads, which already had it).
- No more flash of the wrong view when entering a folder: the folder's view is applied together with its contents.
- Side lists and trees only navigate when you move with the keyboard (rebuilding them — e.g. after Hidden items — no longer jumps to another folder such as Desktop).
- Quick access: the user's .nuke folder, if it exists, with its own icon (hide it with right-click like the others).

## 0.28.0
- Documents opens in Details (list) grouped by date modified, like Windows (reset once on update).
- Arrow keys in Quick access and the other side lists open the folder, like in the trees.
- Folder trees: moving with the arrows opens the folder instantly (no delay).
- VFX Library tree: after clicking a folder the keyboard stays in the tree (the grid no longer takes the focus), so the arrows keep moving through folders.

## 0.27.2
- Images open right away with Windows' default app, like a normal double click (no remapping, no special launch). Settings › General › "Image viewer": pick a program to open images with instead, like the Player for videos. Removed the "Images open in" options (Photos link and classic Photo Viewer).

## 0.27.1
- Images: new default "auto" — when Windows Photos is the default app and the image is on this PC, it opens with previous / next. Drives that are a share of this same PC remapped as a network drive (e.g. T: → \\this-pc\share) are resolved to the real local folder first, so there is no security prompt and it is as fast as a local file. Real network drives (a NAS) open plainly with the default app.

## 0.27.0
- Images open with the system's default app again (instant, no prompts). Settings › "Images open in" keeps the Photos-with-previous/next and classic Photo Viewer options.
- Numbered photos grouped as a sequence (IMG_0001.jpg…) open like single photos (the first one) instead of failing.
- Folder trees (File Explorer and VFX Library): moving with the arrow keys opens the folder after a short pause.
- VFX Library tree: auto collapse happens on double click; a single click only opens the folder.
- Details per mode: the VFX Library and File Explorer no longer show each other's item.
- VFX Library Details: the last image / PDF stays (the one you selected, or the folder's PDF / cover image) while you pick videos or models in the grid — handy for comparing. Without a PDF, a cover image of the folder is shown (names like cover / portada / preview first).
- VFX Library: a video from another folder pauses when you move to a different folder.

## 0.26.0
- Windows Photos now opens with previous / next: images are launched through Photos' own viewer link (ms-photos:viewer?fileName=…), the only way it accepts the folder from another program. Instant, no background work. Settings › "Images open in": default app, Photos always, or the classic Photo Viewer. (The winrt packages are no longer needed.)
- VFX Library tree: buttons below it for auto collapse (closes the folders outside the current path) and sort by name (default; off = the order they were added).
- VFX Library folder PDF: the PDF of the folder you are in — or of the nearest parent folder — stays in Details while you browse there (3D model collections). Toggle with the document button left of Color filters (on by default, only in the VFX Library).
- Blow Up: full-screen backdrop and inverted panning for any size (mouse right → image left); images that fit the screen also move.
- Settings: "Created by Javi Bravo" with a link to GitHub at the bottom.

## 0.25.0
- Player slots: 1…4 (no modifier) switch to the slot; right-click a circle puts the selected item there (or clears it if it's the same); slots work with videos, sequences, images and sounds; smaller circles.
- Opening an image with its neighbors: the Windows launch now runs on the UI thread as the API requires (it fell back to a plain open before), with a log in VFXExplorer_data/launch.log. New Settings › General › "Images open in": default app or the classic Windows Photo Viewer (always browses the folder). The external player is now only for sequences and videos, as its hint says.
- First start: the tab opens directly in This PC (it showed the user folder first).

## 0.24.0
- VFX Library player slots: Ctrl+1…4 puts the current video in a slot, Shift+1…4 (or clicking its circle on the left of the player) jumps to it — in its folder, playing from where it was. Right-click a circle clears it. Four circles: dim when empty, brighter when set, light blue for the one playing.
- Mode bar: the File Explorer icon is yellow when active, the VFX Library icon light blue when active; the inactive one is gray.
- Settings › Shortcuts lists every active shortcut.
- Views: Ctrl+Shift+1 / Ctrl+Shift+2 for icons / details (like Windows; Ctrl+1/2 clashed with the rating keys and did nothing). Rating moved to Alt+0…5.

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
