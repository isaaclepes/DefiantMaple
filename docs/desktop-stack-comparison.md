# Desktop stack comparison: discovery stage

Status: the discovery comparison completed 25 September 2026. Qt/PySide6 was
selected for Phase 1 in [ADR 0001](adr-0001-desktop-stack.md), backed by scoped
release-build measurements on Windows, macOS, and hosted Linux/X11.

## Product-specific decision criteria

The SDD makes the 100,000-asset gallery, background media work, and safe local
filesystem access the decisive constraints. The comparison therefore weights:

| Criterion | Weight | Evidence required |
| --- | ---: | --- |
| Large gallery responsiveness | 25% | Shared 100k catalog, release-build frame timing, memory after 10k visited cells |
| Desktop integration | 15% | File dialogs, drag/drop, clipboard, high-DPI, shortcuts, accessibility on three OSes |
| Background/native work | 15% | Bounded workers, cancellation, SQLite access, FFmpeg and future ONNX integration |
| Packaging and updates | 15% | Reproducible signed/notarized artifacts and clean-machine install evidence |
| Local security boundary | 10% | Minimum filesystem/process authority and reviewable plugin permissions |
| Keyboard and accessible UX | 10% | Focus order, screen-reader labels, configurable commands, rapid review test |
| Development fit | 10% | Complexity, diagnostics, testability, dependency/licensing maintenance |

The reproducible fixture and measurement procedure live in
[`benchmarks/README.md`](../benchmarks/README.md).

## Candidates retained for the first comparison

### Qt 6 with PySide6

Qt for Python is the official Qt binding and exposes Qt's mature model/view
classes. `QListView` supports icon mode and batched layout, which directly maps
to a thumbnail gallery. It can also reuse the current Python spike without a
language boundary. Qt documents `pyside6-deploy` for Windows, Linux, and macOS.

The main risks are packaging complexity and license compliance. Qt for Python is
offered under LGPLv3/GPLv3 and commercial terms; the exact modules, linking, and
distribution process need review before a product decision. Native-looking
widgets are useful, but custom gallery delegates and QML/Widgets choice still
need a prototype.

Primary sources:

- [Qt for Python overview and licensing](https://doc.qt.io/qtforpython-6/)
- [Qt model/view architecture](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-model-view-programming.html)
- [QListView icon and batched layout](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QListView.html)
- [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html)

### Tauri 2 with a web frontend and Rust core

Tauri uses the operating system webview and a Rust application core rather than
shipping a browser engine. Its capability system can constrain which windows may
call filesystem or process commands, a strong fit for the SDD's future plugin
trust model. It is licensed under MIT or Apache-2.0 terms.

The risks are system-webview rendering differences and a frontend/backend bridge
for SQLite rows, thumbnail transport, cancellation, FFmpeg, and eventual ONNX.
Linux development and distribution depend on WebKitGTK and related system
packages. Large-grid virtualization belongs to the selected web frontend rather
than Tauri itself, so it must be demonstrated, not assumed.

Primary sources:

- [Tauri architecture](https://v2.tauri.app/concept/architecture/)
- [Tauri capabilities](https://v2.tauri.app/security/capabilities/)
- [Tauri platform prerequisites](https://v2.tauri.app/start/prerequisites/)
- [Tauri repository and licenses](https://github.com/tauri-apps/tauri)

### Flutter desktop

Flutter provides natively compiled apps for Windows, macOS, and Linux from a
shared Dart UI. `GridView.builder` creates visible children on demand, giving it
a suitable primitive for the gallery experiment. Flutter is BSD-3-Clause.

The risks are a Dart-to-native boundary for the existing core and media tooling,
platform-specific desktop integration, and separate build hosts/toolchains.
Flutter's own setup documentation requires platform toolchains, and desktop
integration tests must run on each target platform.

Primary sources:

- [Flutter platform integration](https://docs.flutter.dev/platform-integration)
- [GridView.builder on-demand construction](https://api.flutter.dev/flutter/widgets/GridView/GridView.builder.html)
- [Flutter desktop integration tests](https://docs.flutter.dev/testing/integration-tests)
- [Flutter license FAQ](https://docs.flutter.dev/resources/faq)

### Avalonia UI with .NET

Avalonia provides a shared C#/XAML UI on Windows, macOS, and Linux, uses its own
rendering stack, exposes native handles for integration, and is MIT licensed.
It is a credible desktop-first control candidate with a simpler native boundary
than a browser frontend.

The risks are replacing the current Python spike or maintaining a process/FFI
boundary, plus Linux backend maturity. Current documentation says X11/XWayland
is the default and its native Wayland backend is experimental, which must be
tested for the target Linux environments.

Primary sources:

- [Avalonia overview](https://docs.avaloniaui.net/)
- [Avalonia native interop](https://docs.avaloniaui.net/docs/app-development/native-interop)
- [Avalonia Linux backend](https://docs.avaloniaui.net/docs/platform-specific-guides/linux)
- [Avalonia license FAQ](https://docs.avaloniaui.net/tools/faq)

## First spike order

Build the Qt/PySide6 and Tauri 2 gallery prototypes first. They test the two most
relevant architectural poles: direct reuse of the Python core with a desktop
model/view toolkit, and a narrow Rust authority layer with a web UI. Both must
read the same generated catalog and implement only the comparison surface:

1. Virtualized thumbnail placeholders with selection and adjustable cell size.
2. Keyboard next/previous, rating/state change, filter, and detail-pane actions.
3. A bounded background task with visible progress and cancellation.
4. File dialog plus drag/drop using read-only access.
5. Release packaging on Windows, macOS, and Linux.

Flutter and Avalonia remain active candidates. Prototype them if Qt or Tauri
misses a gate, or if their expected maintainability advantage can be tested with
the same scope. A stack is eliminated only by measured failure, an unacceptable
license/distribution condition, or inability to satisfy a required OS behavior.

## Open follow-up inputs

- Name the minimum Windows, macOS, and Linux versions and whether native Wayland
  is required at first release.
- Name reference hardware and latency/memory budgets for NFR-002.
- Decide whether LGPL compliance is acceptable or Qt commercial terms must be
  priced into the comparison.
- Decide whether maintaining Rust/TypeScript, Dart, or C# is acceptable for the
  expected contributor base.
- Define the supported update channels and signing/notarization expectations.
