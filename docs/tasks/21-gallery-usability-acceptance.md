# Task 21: Phase 1a gallery usability acceptance

## Scope and evidence classes

This acceptance record tests the four priorities in [the feedback record](../gallery-usability-feedback.md), using only deterministic generated fictional images, a temporary catalog, and isolated application data. The probe is [native_acceptance.py](../../prototypes/qt/native_acceptance.py). Its Qt assertions and app-window capture are one evidence class. KWin compositor-reported identity is a separate native evidence class. Offscreen Qt tests and hosted CI are regression evidence only; they do not establish KDE compositor behavior or a release qualification.

The expected native host for this run is Nobara 44, a Fedora-derived distribution, KDE Plasma on Wayland. Report it by that exact name. Evidence on this host does not qualify plain Fedora or another Fedora version. Capture only the generated application window via Qt; never capture the full desktop or inspect unrelated windows.

## Run procedure

From the repository root, use the supplied Qt runtime and an empty evidence directory outside Git and outside source media. The command sends TERM at 120 seconds and allows up to 5 additional seconds for forced cleanup; the scripted thumbnail drain is capped at 90 seconds and full-image decodes at 12 seconds.

```sh
qt_python="$(realpath ../.venv-gallery-usability)/bin/python"
timeout --signal=TERM --kill-after=5s 120s "$qt_python" \
  -m prototypes.qt.native_acceptance \
  --output /tmp/defiantmaple-gallery-usability-reproduction
```

The probe deliberately requires `HEAD == b0d1755fd344f7cb033c83d66413dff04997bfd4`; the recorded measurement came from that baseline plus the uncommitted implementation tree. To reproduce after publication, create a detached worktree at that baseline, generate a binary diff from the baseline to the exact published PR head in the source checkout, and apply that diff in the detached worktree without committing. Confirm HEAD remains at the required baseline and each path/digest in `acceptance.json` → `provenance.code_file_digests` matches before running. Use a fresh external output directory and a host-appropriate Qt runtime; the `../.venv-gallery-usability` path above refers to the original local workspace.

The probe creates 64 supported fictional images, including landscape, portrait, square, EXIF-oriented and alpha anchors plus a deterministic scrolling batch and a 1920×1200 original. It creates and scans a temporary catalog, puts XDG cache/data in the evidence directory, launches the actual `GalleryWindow`, fills the bounded thumbnail queue, scrolls while decoding remains outstanding, and captures the final selected target. It records fixture/source/catalog hashes, runtime/backend, cold completion-from-window-show and warm-cache observations, raw timer heartbeat gaps, sampled process-tree RSS when `psutil` is available, queue/thread/decoder limits, selection identity, original-preview dimensions and controls, Qt identity, compositor identity, and clean-close outcome. It refuses an evidence destination within the repository or a nonempty destination. Source hashes and catalog rows/metadata assignment snapshots are compared before/after; catalog integrity is checked. The published PNGs are byte-for-byte app-window-only captures of generated fixtures. They may show synthetic fixture identifiers and the isolated temporary fixture root; they contain no user media or whole-desktop content.

The local raw result includes checkout HEAD, a dirty-tree flag/path list, and SHA-256 hashes for the actual measured Qt implementation, probe, media/cache/catalog/source modules, desktop entry, and icon before and after the run. The baseline commit identifies ancestry only; the uncommitted working-tree source hashes identify the measured implementation. The filtered public JSON omits local paths, identifiers, and raw logs while retaining code-file digests and generated-only numeric telemetry. The eight PNGs are unchanged app-window captures, with digests matching their local originals.

For compositor identity, the probe opens a temporary D-Bus receiver and a 0600 KWin script. The script first filters `workspace.windowList()` by this generated app process PID, then reports only matching windows' `internalId`, `resourceClass`, and `desktopFileName`; the receiver authenticates that reports came from the KWin D-Bus owner. It queries while the generated full-image window is visible and unloads the temporary script in `finally`. KWin output is stored separately. Do not change persistent compositor settings, query/report unrelated window properties, or capture private desktop contents.

## Acceptance matrix

| Area | Required result | Evidence and limit |
| --- | --- | --- |
| Aspect and orientation | Portrait, landscape, square, and EXIF-rotated originals retain their expected display dimensions and aspect. Thumbnail cells do not stretch pixels. | Generated source manifest, decoded thumbnail dimensions, Qt-rendered app window. A thumbnail's bounded pixel dimensions do not imply full-resolution viewing. |
| Alpha | The alpha fixture retains transparency; checker/light/dark choices change only the preview background. | Original alpha-channel facts and preview control state. No source-media write. |
| Cold/warm loading | The cache begins empty. First-visible thumbnail completion and subsequent cache reuse are separately observed across a generated 64-image batch while queueing, scrolling, selection changes, and a QTimer heartbeat overlap. | Record per-item completion time from window show, the raw event gaps/derived p95 and maximum, queue high-water, and sampled process-tree RSS where available. This bounded fixture run is not a reference workload. Do not compare against unadopted SDD §19.2 budgets. |
| Selection and stale work | Rapid selection changes leave the current asset identity on the requested final item; completion from old work cannot retarget selection or detail/inspect commands. | Before/after asset UUIDs and worker completion observations from the isolated run. |
| Full-image inspect | Display uses the captured asset's original supported pixels with EXIF orientation, a 1920×1200 original, fit, zoom, pan, alpha choices, Enter-to-open, F11 full-screen toggle, Escape close, and explicit errors. | Original dimensions and dialog state/scale before and after control actions. Current preview limits are 40 MP, 512 MiB and 12 s. |
| App identity | Qt reports product name and window/icon state; KWin reports only windows belonging to the probe PID, including main gallery and full-image dialog, with resource class and desktop file name matching the packaged identity. | Keep Qt self-report and compositor report separate. This is Nobara 44 host evidence only, not a generic Fedora or distribution-release claim. |
| Cleanup, integrity, privacy | Workers stop, window closes, temporary fixtures/cache stay under the evidence directory, catalog integrity succeeds, and fixture/source hashes are unchanged. | Manifest plus generated-only app capture. Remove the isolated evidence directory after review if desired. |

## Baseline Core CI audit

The merged-main baseline workflow [run 37180554573](https://github.com/isaaclepes/DefiantMaple/actions/runs/37180554573) checked out `b0d1755fd344f7cb033c83d66413dff04997bfd4`. The six core Python test-matrix jobs, three source-scan soak jobs, and three scan-cost profile jobs all completed successfully. The Windows Server 2025 / Python 3.13 core job reported 195 tests, one skipped, and passed the public-artifact privacy check. This predates Phase 1a gallery changes; it establishes neither Qt UI coverage nor native Fedora/KDE identity evidence.

## Result and deferrals

### Attempt 1 — generated scan setup failure

The first native attempt exited 1 in 0.63 seconds before opening the gallery. Its preserved catalog contained zero assets and 64 pending source entries: `scan_sources(..., quiet_seconds=0)` intentionally records a new candidate as pending on its first observation. This was a probe setup error, not a gallery result. No KWin script was loaded. The wrapper log and generated-only output remain preserved at `work/gallery-usability-native-attempt1.log` and `/tmp/defiantmaple-gallery-usability-native-attempt1`.

The final probe performs bounded repeated scans and requires 64 indexed assets with no pending entries. Its reviewed diagnostic version also records progress and partial evidence before each gate so an interrupted or failed attempt retains source hashes, catalog-before snapshot, completed cold-thumbnail measurements, and exact control-stage state.

### Attempt 2 — native control-stage failure

The second native attempt used probe SHA `0015a4f75d5a6985dcced4370330463a2683dd51e443ee680068791aae16b6da`, confirmed by the pre-run frozen-code check. It reached the generated gallery captures and opened the EXIF-oriented original, then exited 1 at the combined keyboard/focus/pan/fullscreen/Escape assertion. The assertion did not preserve its component booleans, so the individual failed control is unknown. The full-image capture appears full-screen; that alone does not establish whether the second F11 transition failed or had not settled when captured. No compositor/KWin identity stage or final `native-acceptance.json` was produced. Do not treat this attempt as control or app-identity acceptance.

Preserved files: `work/gallery-usability-native-attempt2.log` and `/tmp/defiantmaple-gallery-usability-native-attempt2`. A read-only post-run audit found 64 generated fixture files matching attempt 1 byte-for-byte, SQLite integrity `ok`, 64 indexed assets in `new` state, and zero tag/entity assignments. Those post-run checks do not substitute for the missing in-run before/after catalog snapshot. The app-only captures show the generated shape/orientation anchors and EXIF original; native cold-load measurements, per-control results, KWin identity, and in-run cleanup evidence remain unaccepted.

### Attempt 3 — scoped gates passed; successful stage archive missing

The third reviewed-probe run exited 0 and passed its scoped native gates. It exercised the 64-file generated workload, rendered the shape/orientation anchors and full-size original, completed the viewer control path, queried only the generated app's own KWin windows, and closed the gallery and worker. The successful-path cleanup removed the probe's stage receipt, however, so raw heartbeat gaps, RSS samples, and detailed control state were not retained. Treat this as a successful run with an evidence-retention gap; its aggregates alone are not used as the final raw performance evidence. The filtered attempt history records its probe/log/receipt hashes without publishing local raw files.

### Attempt 4 — limited native acceptance

The fourth run used the reviewed and frozen probe SHA `f8ec25b011fb1ebe91dcf64884760c7f7f17e918dc8c6dc7ef7152e075e13948`; it exited 0 under the 120-second cap. All 64 generated fixtures were indexed after two bounded scans. Before/after source digests matched, the catalog snapshot digest remained `b272ab580ebc82740a161a023689244e837ae58ff35ef7654ab4e5f051cb65db`, SQLite integrity was `ok`, and tag/entity assignments remained zero. The app-only captures show generated gallery anchors and the original-image viewer. The EXIF-oriented original decoded at 180×320; the larger generated original decoded at 1920×1200. Fit/zoom, pan, focus, settled F11 enter/exit, Escape close, alpha background controls, final selection, worker cleanup, and window close gates all passed.

KWin independently reported two windows from the generated application's own process with desktop-file name and resource class `io.github.isaaclepes.DefiantMaple`; the temporary script was unloaded. This is compositor evidence on this Nobara 44 KDE Wayland host, separate from Qt's self-report. The retained 98-stage archive includes 2,873 heartbeat-gap observations from the cold-loading phase and 308 process-tree RSS samples spanning the timer's lifetime through viewer and KWin stages. Recalculation of the retained gaps gives nearest-rank p95 14.495934 ms and maximum 29.405538 ms; the retained RSS array maximum is 298,377,216 bytes. Process-tree RSS can double-count shared pages and miss short child peaks; it includes Python and Qt workers and excludes compositor/system/GPU memory. Thumbnail completion times are measured from window show, include queueing, and are not decoder CPU time.

The public derivative, attempt history, and eight generated-app-only captures are in [the attempt 4 evidence directory](../evidence/gallery-usability/attempt4/). The JSON omits local paths, UUIDs, catalog/source/asset identifiers, process identifiers, and raw logs. The unchanged PNGs show only generated fixture content and the application window, though the gallery UI visibly includes the synthetic catalog path and generated identifiers. Original raw JSON receipts and logs remain preserved locally and are represented by SHA-256 receipts. The gallery-window and alpha capture hashes happen to be identical; the evidence manifest preserves that fact rather than implying distinct pixels.

This is limited evidence for the tested generated workload and recorded host. It does not close the broader requirements, qualify another OS/distribution, certify a release package, or establish accessibility across platforms. SDD §19.2 numerical budgets remain unadopted; measurements are descriptive only. High-DPI behavior was not established at DPR 1.0, and the zoomed EXIF capture is not a full-frame visual demonstration of orientation. Preserve all four attempt outputs and logs; do not rerun selectively to obtain a preferred result.
