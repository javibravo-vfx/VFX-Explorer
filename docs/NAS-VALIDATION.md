# NAS validation — 0.62.6-beta

## Scope and changes (from 0.62.5-beta, a1ff647)

- Library tree caches and real results have distinct signals. Only authoritative success resets the retry counter; eight retries are scheduled at 2/4/8/16/30/30/30/30 seconds. Reload, collapse, branch removal and recovery invalidate stale tickets. Exhausted branches stop auto-retrying until explicitly reopened or recovery is observed. Existing children remain visible.
- Ordinary foreground and live pane scans use a bounded daemon queue per logical network root (2 active, 16 pending); tree listings use another (2 active, 64 pending). Latest foreground requests take priority and superseded queued work is cancelled. Cache queries use a separate bounded local queue (2 active, 128 pending), so an SMB wait does not consume cache capacity. No Qt objects are touched by these storage workers. Owner-thread timers check completions every 15 ms while pending; tree callbacks are budgeted between results. This adds a small scheduling interval to mapped/UNC directory delivery, not a per-file check. Fixed local pane and local tree scan paths are unchanged.
- OS reads already in progress cannot safely be interrupted; if both slots are blocked, the latest uncached folder waits for a slot, while its cached listing can appear independently. Limits are per mapped letter/UNC share and role, not global or across alias letters. Recursive searches, file operations, folder covers and other `run_async` jobs are not covered by these new scan limits. The existing global thumbnail cancellation is unchanged; the reported Qt crash has NOT been diagnosed or reproduced here.
- Windows CI now runs the new Qt regression tests and requires both offscreen and real-window stress. The stress gate fails on unhandled/action exceptions, no observed wake/wait, stuck loading, gaps >1.5 s, p95 >200 ms, p99 >500 ms (50 ms heartbeat). These are provisional acceptance gates, not measured Windows latency. The fake NAS no longer accumulates arbitrary awake time per access. The `beta-0.62` branch triggers builds without changing main.

## Validation performed here

- 34 passing non-GUI tests: 10 storage cache, 6 network state, 11 routing, 1 real process, 1 real shared-memory transport, 5 queue/retry. The new queue test simulates 100 rapid requests behind two blocked reads: only the last queued request executes, another root completes independently.
- `test_storage_routing.py` has one additional Qt-dependent case that could not run; `test_core.py` and the five new Qt delivery tests also require PySide6. Installation was unavailable here. OpenImageIO and Windows are not available. Syntax compile and workflow YAML checks passed. The EXE was not built or run, and GitHub was not accessed or modified.
- No measured navigation throughput or actual crash reproduction. Run the Windows gates and compare directory opening/scroll on local, SMB-loopback and real remote drives before merging.

## Manual acceptance

1. Populate the cache on E: with the NAS awake, let the NAS sleep, then open many folders quickly while the disks start. Verify the current folder wins, prior queued results never replace it, the tree stays responsive and cached entries remain visible.
2. While E: is blocked, navigate T: (local SMB) and a physical local drive. Compare perceived speed and directory timings to 0.62.5 and 0.61.3 (100/1,000/10,000 entries, cold/warm cache). Also test a second real NAS and an all-local configuration. Verify no changes to tags, paths, viewer or Review.
3. With NAS off, inspect backoff and collapse/reopen branches; stop issuing retries for closed branches. Reconnect and verify the list/selection/scroll recover. Repeat while closing the app. Keep VFXExplorer_data/crash.log from any unexpected exit and Windows WER report; do not assume this patch proves the native crash resolved.
4. In Windows run the frozen EXE stress and NAS selftest; use GitHub artifacts only after required gates pass. Keep main/0.61.3 as a backup.

---

# NAS cache-first — 0.62.1-beta (validation build)

## 0.62.1 storage routing and transfer

This beta is based on the supplied 0.62.0-beta source. No paths, tags, ratings, favourites, library roots, or config are migrated. Fixed local drives keep their original no-IPC decode route. Logical mapped and UNC paths retain network-safe listing/caching even for SMB loopback. On background native-image reads, the current Windows mapping is checked against exact local computer names (no DNS). The share's local physical path is resolved from local configuration/service; a direct file read is used only when the actual original SMB open succeeds, the physical file is on a fixed local drive, and file identity matches. If any check fails, the original isolated decoder is used. No file operations are redirected, and no share permissions are changed. Local name aliases not recognized, DFS/junctions, inaccessible shares, non-equivalent file IDs, and unusual mapping providers may conservatively use IPC. The Windows SMB path is not considered proven until real tests pass. No manual override UI is added in this beta.

- Separate thumbnail, metadata and still-viewer work queues per mapped letter or UNC share, separate from fixed local reads. Native decoder pools are also partitioned by logical root, with lazy spawn and at most two slots per role per root, and four retained idle slots overall. Multiple simultaneously active roots may use more than four workers. Alias letters and UNC paths for the same physical NAS can have separate queues. Ordinary file-operation and other less common paths are not comprehensively isolated.
- Remote HDR linear RGB/alpha results can use parent-owned shared memory instead of pickling pixel arrays. The parent copies into ordinary owned NumPy arrays before closing/unlinking the mapping, preserving existing viewer cache semantics. Per-call allocation cap 256 MiB; aggregate cap 512 MiB; fallback to existing IPC if unavailable or too large. No performance claim until measured on Windows with real media. Local images do not use shared memory.
- Directory, thumbnail and metadata caches prefer local paths. Existing local portable caches remain in place. Portable config/library metadata still follows the existing app data location; run locally for full offline startup. Reparse points and unusual redirected local cache paths are not comprehensively handled.

### Tests run in the development environment

- `test_storage_cache.py`: 10 tests.
- `test_network_state.py`: 6 tests.
- `test_media_process.py`: 1 real spawned-process test.
- `test_storage_routing.py`: 10 tests (Windows APIs simulated, real file-identity checks).
- `test_media_transport.py`: 1 real spawned-process test (RGB and alpha fidelity, no alpha, no image, ordinary IPC fallback, per-root separation during a blocked read, timeout cleanup and child shutdown).
- Syntax compilation and workflow YAML parsing passed. Qt/OIIO, the full general suite, Windows, and physical NAS are unavailable here. The EXE has not been built and GitHub Actions has not been run.

### Windows acceptance gate and mixed setup

The packaged EXE test requires shared-memory transfer for its small EXR/HDR fixtures. CI also attempts to create an ephemeral local SMB share mapped to a free letter. If provisioning succeeds, the EXE must verify direct local-file resolution, matching image pixels/metadata and zero native decoder children for that mapping. If Windows policy prevents creating/mapping the share, the CI log explicitly says the real SMB fixture was not run; this is **not** proof that loopback works. The synthetic NAS test is mandatory either way. Keep this version beta until an actual mapping is verified.

Test the packaged EXE in three setups: all fixed local, all NAS (awake and sleeping), and mixed. In the mixed setup, open EXR/HDR files from T: while E: is suspended or disconnected; check that the logical path stays T:, the local decode is selected for verified files and a pending E: read does not hold T:'s queue. Compare Windows Task Manager process counts and time-to-first-frame for each route. For a controlled test of an existing verified local SMB share, set the following **only in a disposable writable test folder** (not a production library); the selftest creates and removes its own temporary fixture subfolder:

```powershell
$env:VFX_LOOPBACK_LOCAL = 'W:\VFX_WANKA_T\test-folder'
$env:VFX_LOOPBACK_MAPPED = 'T:\test-folder'
$p = Start-Process .\dist\VFXExplorer\VFXExplorer.exe -ArgumentList '--nas-selftest' -Wait -PassThru
Get-Content "$env:TEMP\vfxexplorer_nas_selftest.log"
$p.ExitCode
Remove-Item Env:VFX_LOOPBACK_LOCAL,Env:VFX_LOOPBACK_MAPPED
```

Expected: `Real local SMB mapped drive: direct EXR/HDR, zero decoder processes` and `NAS SELFTEST OK`. A failed equivalence test must be investigated rather than forcing direct reads. A local HDD that suspends or a filesystem filter can still stall native local decoding. Windows real-hardware timing and suspension behavior remain unverified.

---

## Previous 0.62.0-beta validation notes

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
