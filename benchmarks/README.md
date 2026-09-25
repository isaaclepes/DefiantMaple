# Desktop comparison benchmark contract

The stack decision is measured against the same data and interaction script.
Generate the first version of the shared 100,000-row catalog from the repository
root:

```sh
python -m benchmarks.generate_catalog /tmp/defiantmaple-100k.sqlite3
```

The generator is deterministic, dependency-free, refuses a nonempty catalog,
and creates representative media types, workflow states, provenance rows, and
exact-duplicate groups. It creates catalog records only; a later fixture version
will add decoded thumbnail files without committing a large binary corpus.

Each prototype must record the following on the same reference machine and OS:

| Measurement | Procedure |
| --- | --- |
| Cold start | Time from process launch to a usable first grid with the catalog already created |
| Memory | Resident memory after first grid and after visiting 10,000 distinct cells |
| Scroll | 60-second automated traversal; report median and p95 frame time and dropped frames |
| Keyboard review | Time for 500 next-item and state-change actions, including worst input latency |
| Query change | Time to display the first page after alternating two indexed filters 50 times |
| Background pressure | Repeat scrolling while a bounded hash worker is active; cancel it and report cancellation latency |
| Desktop behavior | File dialog, drag/drop, clipboard, high-DPI, screen reader labels, focus order, and shortcuts |
| Packaging | Clean release build time, installed size, first-run behavior, signing/notarization steps |

Run the interaction measurements on Windows, macOS, Linux/X11, and Linux/Wayland
where the candidate claims support. Capture exact framework/runtime versions,
hardware, display scale, build mode, and whether thumbnails were warm or cold.
Do not compare one candidate's debug build with another candidate's release build.

The initial comparison is relative rather than a compliance claim. Absolute
pass/fail budgets require named reference hardware and product latency targets.
