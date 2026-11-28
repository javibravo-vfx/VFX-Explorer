# NAS cache-first — 0.62.0-beta (validation build)

Based on the supplied 0.61.4 NAS source, itself based on 0.61.3. Existing UI layout, workspace settings and library metadata format retained. No Windows binary compiled here.

## What is cached
- Last successful listing for previously visited network directories (directory-cache.sqlite3), independent of the NAS. Existing thumbnails are reused where the source metadata matches; new sidecar/scrub thumbnails can be reused from local cache.
- Cached entries are not copies of original full-resolution files. Opening/decoding an uncached source still requires access to the NAS.
- First successful visit populates snapshots; an older install only has thumbnail caches, so previously unvisited folders cannot be reconstructed offline.
- Normal local directory scans and local OIIO decoding do not go through the new SQLite/IPC path. If the executable itself is on a share, preview/snapshot caches use LOCALAPPDATA (or a home cache fallback); portable config/library metadata stays where it was, so keep the executable and portable data on a local disk for fully offline startup.

## Validation performed for 0.62.0-beta
- `python tests/test_storage_cache.py`: 10 passed (including new-file reconciliation and REVIEW changes).
- `python tests/test_network_state.py`: 6 passed (online TTL expiry, unknown vs offline, state-only reads, recovery, stale probe, missing subfolder).
- `python tests/test_media_process.py`: 1 integration test passed using real spawned Python processes, lazy expansion, timeout, independent role recovery, cancellation and shutdown. Qt/OIIO initializer replaced by a no-op **only in this headless test**.
- `python -m compileall -q vfxexplorer main.py tests`: passed. Workflow YAML parsed successfully.
- `python tests/test_core.py`: could not start here (PySide6 missing). Neither OpenImageIO nor Windows is available here. No Windows binary or GitHub run produced in this environment.

## Windows executable gate
GitHub Actions now requires the original selftest **and** `VFXExplorer.exe --nas-selftest` before packaging or releasing. The NAS selftest uses real EXR/HDR fixtures on local storage marked as a synthetic network root in the parent. It tests the same IPC route as network decoding, not SMB hardware itself. It compares local and isolated thumbnail pixels, HDR linear data/alpha, metadata and layers; confirms lazy workers and distinct PIDs; runs a Qt event-loop heartbeat during a deliberately blocked decoder, verifies timeout/recovery, and verifies child shutdown. The workflow checks the process exit code, success log and remaining VFXExplorer.exe processes. Beta tags create prereleases.

Run manually on Windows (PowerShell):

```powershell
$p = Start-Process .\dist\VFXExplorer\VFXExplorer.exe -ArgumentList '--nas-selftest' -Wait -PassThru
Get-Content "$env:TEMP\vfxexplorer_nas_selftest.log"
$p.ExitCode
```

The output must contain `NAS SELFTEST OK` and exit code 0. These checks have been **added, not executed on Windows**. Keep the existing 0.61.3 backup until they and the physical NAS tests pass.

## Network state and idle policy
A confirmed good share remains good while a fresh asynchronous probe is pending; timeout does not mean offline. Successful actual reads update state without a separate probe. A failed subfolder read checks the share before calling it offline. The root label updates in place without rebuilding the tree. The network timer reads memory only; healthy/inactive shares are not periodically probed. Failed visible folder reads retry after 8, 16, 32 and then 60 seconds, stopping when no longer visible. An inactive offline root is not automatically probed until actual activity; its indicator is last-known state. REVIEW markers reconcile on actual scans, reactivation and refresh; external changes while sitting idle on an active NAS are not continuously watched, by design, to avoid keeping disks awake. No latency or memory benchmark on physical storage was performed.

## Windows/NAS acceptance checks
1. Install/run locally; open an image/EXR/sequence library once with NAS awake; wait for thumbnails and browse into subfolders. Close the app; let drives sleep.
2. Restart app and verify existing library tabs, tree, thumbnails and search results show before disks finish waking. While waiting, move/resize the window, switch to another local tab and scroll.
3. Unplug/turn off NAS. Navigate already cached folders, then reconnect. Confirm contents stay visible and new/deleted files reconcile. Check same-folder refresh and selection/scroll retention.
4. Browse an uncached folder; the app should remain interactive during the wait, then load it when available. Check UNC and mapped-drive paths separately.
5. With NAS permanently awake and SSD/NVMe local, compare startup, thumbnail grid and EXR/HDR playback speed with 0.61.3. Network OIIO adds IPC and must be benchmarked on real media. Check layer selection and metadata. Test rapid navigation and application exit while an SMB operation is pending.
6. Verify pipeline menu actions, collections/tags, autocomplete and folder covers. Leave the app idle to verify NAS sleep policy; failed visible reads can retry, and active browsing/prefetching will still access originals as needed.

7. Leave a NAS awake longer than 30 seconds, then use folder covers and hover thumbnails; no false offline transition should appear. With the NAS offline, confirm the root label appears without losing its expanded children; reconnect while the failed folder is visible. Add, remove and replace files and REVIEW sidecars while disconnected or before reconnecting. Confirm additions do not cause invalidation errors.
8. Check Task Manager: zero decoder subprocesses for local files, normally one per used role, at most two per role under concurrent work. Close the application during an isolated decoder read; all decoder processes should exit. Also test app shutdown during blocked ordinary SMB scans (separate limitation).

Remaining limitations: Windows filesystem calls can still block a worker until SMB returns, and file-operation/dialog/other less common UI paths have not been comprehensively tested. A network failure during a media read may still need reselection or refresh. The persistent cache does not constitute a complete offline replica, and native process isolation is unverified on the frozen Windows executable in this environment. Network-only file operations on stale listings can still fail, and ordinary SMB/Qt worker shutdown is not guaranteed to be instant.
