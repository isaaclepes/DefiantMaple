# Tauri 2 prototype

This scoped prototype reads the deterministic catalog without touching media.
It implements a Rust/SQLite command layer and a dependency-free virtual web
grid with selection, adjustable cell sizing, arrow-key navigation, review-state
shortcuts `1` through `6`, indexed filtering, a detail pane, read-only file/drop
affordances, and a cancellable Rust background worker.

The toolchain is pinned to Rust 1.98.1, Tauri 2.11.6, Tauri CLI 2.11.5,
its matching 2.11 runtime and 2.6/2.9 code-generation crates, and `rusqlite`
0.40.2. These explicit pins keep the lockfile-free prototype from combining
incompatible Tauri releases. From the repository root:

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

## Catalog compatibility

The comparison reader supports schema v2–v6 without migrating it. On v5/v6,
asset pages and review updates expose persisted rating/favorite values; older
catalogs expose unrated/not-favorite defaults. Curation editing, filters and undo
are provided by Qt and the Python API, not this comparison client. The current
Python fixture initializer produces v6 for release validation; Rust tests retain
old-schema readers and include v5/v6 field-preservation cases.
