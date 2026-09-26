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

# Image embedding benchmark

`embedding_fixture.py` draws 24 original, labeled cartoon portraits: one gallery
reference and three query variants for each of six fictional identities. The
variants flip the portrait, crop it, or rotate a grayscale rendering. The
manifest includes SHA-256 hashes of every generated PNG and the Pillow version.
This is a retrieval smoke test, not a real artist-reference evaluation.

Use Python 3.11+ and install the repository's `requirements.txt`, then a
platform-appropriate CPU build of PyTorch from [the official installer](https://pytorch.org/get-started/locally/),
then `benchmarks/requirements-image-embeddings.txt`. For the recorded run the
versions were Python 3.14.7, PyTorch 2.12.0, Transformers 5.8.1,
Hugging Face Hub 1.33.0, Pillow 12.3.0, and psutil 7.2.2. Pin these exact
versions to reproduce the reported fixture hashes and measurements.

Download only the pinned config, processor, and safetensors files. The model
metadata and revisions are in `image_embeddings.MODELS`:

```bash
export HF_HOME="$PWD/.venv-benchmark/hf"
python - <<'PY'
from benchmarks.image_embeddings import MODELS
from huggingface_hub import snapshot_download
for model in MODELS.values():
    snapshot_download(model["name"], revision=model["revision"],
                      allow_patterns=["config.json", "preprocessor_config.json",
                                      "model.safetensors"])
PY
HF_HUB_OFFLINE=1 python -m benchmarks.image_embeddings dinov2-small
HF_HUB_OFFLINE=1 python -m benchmarks.image_embeddings siglip-base
```

Run one model at a time so CPU and memory readings are comparable. The runner
checks the pinned revision, hashes the actual weights, warms the model twice,
times batch-one inference for all 24 images, and samples process RSS. It writes
per-image vectors into a separate SQLite store under `.venv-benchmark/results`.
Every row includes model name, immutable revision, license, weights SHA-256,
embedding method, preprocessing version, fixture schema, image SHA-256, and
vector dimensions. The catalog and media are never changed. Cosine scores and
margins are uncalibrated ranking signals. CPU is required; CUDA can be tried
separately with `--device cuda` where available.

See [the benchmark report](../docs/embedding-model-benchmark.md) for measured
results, packaging constraints, and the next evidence gate.
