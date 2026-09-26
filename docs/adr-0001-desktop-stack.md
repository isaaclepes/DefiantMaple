# ADR 0001: Use Qt/PySide6 for the Phase 1 desktop client

- Status: Accepted for Phase 1
- Date: 25 September 2026
- Decision owners: DefiantMaple maintainers
- Evidence: Qt PR #2 at `9c339924e1962a09aaa5682095c3d331508f3f87` and Tauri PR #3 at `e037d92af616daf38eaccce244c7235264c4af94`

## Context

The SDD requires a local-first desktop gallery that remains usable with 100,000
cataloged assets while background media work is active. It also calls for strong
filesystem safety, keyboard review, accessibility, and distribution on Windows,
macOS, and Linux. The discovery comparison retained Qt/PySide6, Tauri 2,
Flutter, and Avalonia, then implemented the two candidates that best represented
the architectural choice: an in-process Python desktop model/view toolkit and a
Rust authority layer with a system-WebView frontend.

Both prototypes read the same deterministic 100,000-row SQLite catalog and
implement a virtual gallery, selection, cell sizing, filters, detail display,
real keyboard-event navigation and review-state changes, read-only file/drop
affordances, and cancellable background work. Their release harnesses run the
same interaction script, including a 60-second traversal while the worker is
active. The raw results and workflow artifact identities are preserved under
[`benchmarks/results/2026-09-25`](../benchmarks/results/2026-09-25/README.md).

## Decision

Use **Qt 6.11.2 with PySide6 6.11.2 and Qt Widgets** for the Phase 1 desktop
client. Keep catalog and media-domain code behind ordinary Python interfaces so
the UI can be replaced or split into another process if later evidence changes
the decision.

Tauri remains the first fallback. Reconsider it if Qt distribution licensing is
unacceptable, if a future plugin boundary requires Tauri's capability model, or
if decoded-thumbnail and native-display measurements reverse the responsiveness
result.

## Measured evidence

GitHub Actions run
[`36110310826`](https://github.com/isaaclepes/DefiantMaple/actions/runs/36110310826)
measured the Qt release artifacts. Run
[`36109240316`](https://github.com/isaaclepes/DefiantMaple/actions/runs/36109240316)
measured Tauri. Each platform used a fresh checkout and removed local build
outputs before the timed release build. The artifacts were unsigned.

The latency values below are milliseconds. The over-budget column is the number
of synchronous traversal steps above 16.7 ms, followed by the total steps
completed in 60 seconds.

| OS | Stack | Start | Query p95 | Key p95/max | Review p95/max | Scroll med/p95 | Over 16.7 ms | Cancel |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| macOS ARM64 | Qt | 443.6 | 6.5 | 3.3 / 13.8 | 4.6 / 10.5 | 3.7 / 7.4 | 197 / 13,947 | 0.2 |
| macOS ARM64 | Tauri | 2,105.0 | 14.0 | 20.0 / 22.0 | 34.0 / 41.0 | 25.0 / 30.0 | 2,390 / 2,426 | 16.0 |
| Ubuntu 24.04 | Qt | 588.5 | 2.6 | 1.4 / 14.2 | 3.3 / 5.3 | 3.7 / 4.3 | 249 / 14,863 | 1.1 |
| Ubuntu 24.04/X11 | Tauri | 34,967.8 | 40.0 | 23.0 / 27.0 | 51.0 / 71.0 | 46.0 / 53.0 | 1,293 / 1,316 | 42.0 |
| Windows Server 2025 | Qt | 1,757.7 | 47.2 | 2.9 / 27.4 | 4.6 / 5.4 | 4.8 / 7.0 | 183 / 10,794 | 4.0 |
| Windows Server 2025 | Tauri | 5,377.0 | 72.4 | 62.6 / 437.3 | 140.6 / 223.8 | 64.3 / 74.8 | 919 / 920 | 35.8 |

RSS is omitted from the comparison because the Tauri harness reports only its
Rust process and excludes system-WebView browser and renderer children, while
the Qt prototype runs in one process. Package bytes are also omitted because
the Tauri harness measures a bare executable, whereas Qt measures a one-file
binary on Windows and Linux and a complete `.app` on macOS. The raw values
remain in the result files but are not comparable until full process trees and
equivalent distributions are measured.

Qt completed far more traversal steps with a p95 below 8 ms on every runner.
Tauri's p95 ranged from 30 to 74.8 ms, and nearly every measured traversal step
exceeded 16.7 ms. Qt also had lower startup, keyboard, state-change, and
cancellation latency on all three systems. Tauri provides a stronger
declarative capability boundary. Its bare executable was smaller, but equivalent
distribution size remains unmeasured.

The Windows jobs did not use the same processor vendor, and hosted runner load
is uncontrolled. The direction of the interaction result is nevertheless
consistent on all three operating systems and large enough to decide this
phase. No ratio in this document is a product performance guarantee.

## Weighted assessment

Scores use the discovery weights and a 1-to-5 scale. Criteria without the
required equivalent evidence remain unscored. The subtotal therefore covers
60% of the discovery weights and applies to these scoped implementations and
current project constraints, not to the frameworks in general.

| Criterion | Weight | Qt | Tauri | Evidence and tradeoff |
| --- | ---: | ---: | ---: | --- |
| Large gallery responsiveness | 25% | 5 | 2 | Qt won startup, queries, input, traversal, and cancellation across all hosted samples. |
| Desktop integration | 15% | — | — | Clipboard, high-DPI, focus, and assistive-technology checks were not run across the three operating systems. |
| Background/native work | 15% | 4 | 4 | Both cancel bounded work; Qt reuses Python directly while Tauri gives Rust-native authority. |
| Packaging and updates | 15% | — | — | The harnesses did not produce equivalent installers or test clean-machine install, update, rollback, and uninstall behavior. |
| Local security boundary | 10% | 3 | 5 | Tauri capabilities provide the clearer least-authority boundary. Qt needs an application-owned command boundary. |
| Keyboard and accessible UX | 10% | — | — | Input latency was measured, but focus order, names, announcements, configurable commands, and screen readers were not audited. |
| Development fit | 10% | 5 | 3 | Qt keeps the current Python core in process. Tauri adds Rust, web UI, IPC, and two data models. |
| **Evidence subtotal** | **60% scored** | **4.42** | **3.17** | 265 and 190 weighted points respectively, divided by the 60 scored weight. |

The selection is reversible. Qt leads the highest-weight measured criterion and
has the better fit with the existing Python core. Any of the unscored Phase 1
gates can reverse the choice if equivalent packaging, desktop integration, or
accessibility evidence reveals a blocking condition.

## Consequences

- Phase 1 UI work will extend the Qt model/view prototype and keep database reads
  paged and bounded.
- Media hashing, metadata, thumbnailing, and future inference stay outside the
  GUI thread behind cancellable interfaces.
- The application will define an internal command boundary for filesystem and
  process authority; choosing Qt does not permit arbitrary UI-layer access.
- Distribution work must document LGPLv3 obligations or obtain acceptable
  commercial Qt terms before shipping. This ADR is not a license opinion.
- Distribution size remains unknown until equivalent signed installers are
  produced and measured with their runtime dependencies.
- Tauri code remains a comparison prototype rather than a production dependency.
  Flutter and Avalonia stay unevaluated because the first candidate met the
  current gate; they should be prototyped only if a recorded reversal condition
  occurs.

## Required follow-up evidence

1. Repeat the 100,000-asset test with decoded image thumbnails, video posters,
   cold and warm thumbnail caches, and representative local storage.
2. Measure actual compositor presentation on supported Windows and macOS
   versions, Linux/X11, and native Wayland where claimed.
3. Run keyboard-only and screen-reader audits, including focus order, names,
   state announcements, and shortcut configuration.
4. Build signed/notarized installers and test first run, upgrades, rollback, and
   uninstall on clean machines.
5. Complete Qt license/distribution review and record the chosen compliance path.
6. Name reference hardware plus absolute latency and memory budgets before
   treating the measurements as pass/fail NFR evidence.

## Measurement limits

The fixture contains catalog rows and placeholder cells; it performs no image
decode, video seek, color management, or thumbnail disk I/O. Qt used the
offscreen platform. Tauri used the system WebView, with Xvfb/X11 on Linux. These
runs therefore measure synchronous application work, not displayed frame times.
Native Wayland, clipboard behavior, screen readers, signing, notarization,
installers, and updates were not measured. Tauri RSS excludes its system-WebView
child processes, and package bytes cover different artifact scopes. Startup is
one process-to-first-grid sample per artifact with filesystem, extraction,
WebView, and OS caches left uncontrolled. No personal media was used.
