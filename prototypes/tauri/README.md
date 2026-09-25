# Tauri 2 prototype

This scoped prototype reads the deterministic catalog without touching media.
It implements a Rust/SQLite command layer and a dependency-free virtual web
grid with selection, adjustable cell sizing, arrow-key navigation, review-state
shortcuts `1` through `6`, indexed filtering, a detail pane, read-only file/drop
affordances, and a cancellable Rust background worker.

The toolchain is pinned to Rust 1.98.1, Tauri 2.11.6, Tauri CLI 2.11.5,
`tauri-build` 2.6.3, and `rusqlite` 0.40.2. From the repository root:

```sh
npm install --prefix prototypes/tauri
npm --prefix prototypes/tauri run tauri -- icon app-icon.svg
python -m benchmarks.generate_catalog benchmark.sqlite3
DEFIANTMAPLE_CATALOG="$PWD/benchmark.sqlite3" \
  npm --prefix prototypes/tauri run tauri dev
python -m prototypes.tauri.package \
  --catalog benchmark.sqlite3 --metrics tauri-metrics.json
```

The browser-only virtual-grid unit tests run with `npm test --prefix
prototypes/tauri`. Rust catalog tests run with:

```sh
cargo test --manifest-path prototypes/tauri/src-tauri/Cargo.toml
```

The benchmark mutates review states only in the generated catalog. Packaging
creates and measures an unsigned release executable that relies on the operating
system WebView. CI runs the same 100,000-row fixture on current GitHub-hosted
Ubuntu, Windows, and macOS runners and uploads the executable and metrics. The
Linux run uses Xvfb/X11; it does not establish native Wayland behavior.
