# Qt/PySide6 prototype

This scoped prototype reads the deterministic catalog without touching media.
It implements a page-cached `QAbstractListModel`, batched `QListView` icon grid,
selection and details, adjustable cell sizing, review-state shortcuts `1` through
`6`, indexed state filtering, read-only file/drop affordances, and a cancellable
background worker.

Create a virtual environment, install `requirements.txt`, then run from the
repository root:

```sh
python -m benchmarks.generate_catalog benchmark.sqlite3
python -m prototypes.qt.app --catalog benchmark.sqlite3
QT_QPA_PLATFORM=offscreen python -m prototypes.qt.app \
  --catalog benchmark.sqlite3 --benchmark-json qt-source-metrics.json
python -m prototypes.qt.package \
  --catalog benchmark.sqlite3 --metrics qt-metrics.json
```

The benchmark mutates review states only in the generated catalog. The packaging
command builds the unsigned artifact and benchmarks that executable, including
one-file extraction in startup time. CI runs the same 100,000-row fixture and
uploads unsigned prototype metrics/artifacts.
