# Hosted desktop comparison results — 25 September 2026

These files are the JSON metrics emitted by the unsigned release artifacts used
for [ADR 0001](../../../docs/adr-0001-desktop-stack.md). Executables remain in
the GitHub Actions artifacts and are not committed to the repository.

| Stack | Head | Workflow run |
| --- | --- | --- |
| Qt/PySide6 | `9c339924e1962a09aaa5682095c3d331508f3f87` | [36110310826](https://github.com/isaaclepes/DefiantMaple/actions/runs/36110310826) |
| Tauri 2 | `e037d92af616daf38eaccce244c7235264c4af94` | [36109240316](https://github.com/isaaclepes/DefiantMaple/actions/runs/36109240316) |

| File | Artifact ID | Artifact digest |
| --- | ---: | --- |
| `qt-macos-arm64.json` | 10853405181 | `sha256:6c838fff3a2f51162af8d6898d62a5bcc839f158d61ecc6b59002ebefd648cf0` |
| `qt-linux-x64.json` | 10852369929 | `sha256:a0e04aae044eb30ae1e70ab13af0d6d46af438405510308f18505d3a070e9efb` |
| `qt-windows-x64.json` | 10852752776 | `sha256:e5527e818eeae4e8e22d00207d202cafe670e22ced41f3579f2e277bb39893cc` |
| `tauri-macos-arm64.json` | 10852013603 | `sha256:f30e8f5a1b01d6cc6fb9d9f2a57154fcafeb29569ef48b0a84930cab9b389e3e` |
| `tauri-linux-x64.json` | 10852402907 | `sha256:b054109df3ba8038f5946b0080c44fb7797228878bc1d453bc140ca1c168a993` |
| `tauri-windows-x64.json` | 10853135329 | `sha256:4da52b16522f712a2f48a348ce34850e3bf1f91624a935900d2182d63e94548f` |

Each run used fixture version 1 with 100,000 catalog records. The raw metrics
contain the framework/runtime versions, reported processor and CPU count,
display backend, display size/scale, build mode, package size, and measurement
limitations. Artifact digests identify the complete uploaded ZIP, not the JSON
file alone.

Hosted runners and their load can change, so these files are evidence samples.
They do not establish supported OS versions or absolute product budgets.
The Tauri macOS WebView user agent includes a `Mac OS X 10_15_7`
compatibility token while the system API reports macOS 26.6.2; use the
`platform` field for the recorded host and do not infer it from that token.
