# Phase 1 image-embedding benchmark (26 September 2026)

**Recommendation:** use pinned `facebook/dinov2-small` as the *next retrieval
prototype baseline*, not as a character-identity classifier. Both tested models
ranked all 18 generated query variants first, while DINOv2-small used 88.25 MB
of weights versus 812.67 MB and had lower batch-one CPU latency. This evidence
does **not** justify automatic character recognition, a confidence threshold,
or distribution in the desktop installer. A small real-reference evaluation is
the next gate before either model can be recommended for artist libraries.

## Scope and method

The [fixture generator](../benchmarks/embedding_fixture.py) draws six original,
fictional cartoon identities. Each has one gallery portrait and three query
variants: mirrored with a new background, shifted/cropped, and grayscale/rotated.
The 24 PNGs are regenerated locally with Pillow 12.3.0. The checked-in
[manifest](../benchmarks/image-embedding-results/fixture-manifest.json) records
each PNG's SHA-256; its own SHA-256 is
`04dc9082af01b5e541bf583935082f866c2d5a3b9014375799664a6ff713fe55`.
No personal media, external dataset, or asset-catalog rows were benchmarked.

For each pinned safetensors snapshot, the [runner](../benchmarks/image_embeddings.py)
checks the actual weights SHA-256, loads only local files, warms two inferences,
and times 24 individual images at batch size one. It L2-normalizes the CLS token
for DINOv2 and the projected image feature for SigLIP, then ranks six gallery
vectors by cosine similarity for each of 18 queries. Recall@1 and mean reciprocal
rank use the fixture's explicit labels. Reported p95 is the nearest-rank sample
percentile; RSS is sampled every 10 ms for the whole process and includes Python,
PyTorch, processor, and model memory. Runs were sequential.

The machine was Linux x86-64 (Nobara/Fedora 44, kernel 7.2.3), AMD Ryzen 5 5500
(6 physical/12 logical cores), 62.3 GiB RAM, with four PyTorch CPU threads.
Python 3.14.7, PyTorch 2.12.0+cu130, Transformers 5.8.1, Hugging Face Hub 1.33.0,
Pillow 12.3.0, and psutil 7.2.2 were used. CUDA, ROCm, and Apple MPS were not
available for a measured GPU run.

| Candidate (immutable revision) | Model-card license | Safetensors download | Vector | CPU p50 / p95 per image | RSS after load / sampled peak | Recall@1; MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [DINOv2-small](https://huggingface.co/facebook/dinov2-small/blob/ed25f3a31f01632728cabb09d1542f84ab7b0056/README.md) `ed25f3a31f01632728cabb09d1542f84ab7b0056` | Apache-2.0 | 88,249,960 B (84.16 MiB) | 384 | 75.16 / 90.07 ms | 780.3 / 879.0 MiB | 18/18; 1.00 |
| [SigLIP-base](https://huggingface.co/google/siglip-base-patch16-224/blob/7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed/README.md) `7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed` | Apache-2.0 | 812,672,320 B (775.02 MiB) | 768 | 186.78 / 198.73 ms | 784.3 / 1,158.8 MiB | 18/18; 1.00 |

The exact [DINOv2](../benchmarks/image-embedding-results/dinov2-small-cpu.json)
and [SigLIP](../benchmarks/image-embedding-results/siglip-base-cpu.json) reports
include per-query rank, cosine, margin, weights hash, preprocessing fingerprint,
and runtime metadata. Download sizes above are the actual model.safetensors byte
counts, excluding config files and the much larger Python runtime. [Meta's
DINOv2 model card](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md)
explicitly lists nearest-neighbor retrieval and Apache-2.0 licensing for the
standard DINOv2 weights; SigLIP's pinned model card marks the snapshot
Apache-2.0, consistent with the [Google Big Vision repository license](https://github.com/google-research/big_vision#license).
These statements do not extend to other
Meta or Google model families, training data, or transitive packages.

## Vector provenance and use limits

The benchmark writes a separate SQLite store (`.venv-benchmark/results/*.sqlite3`)
and never calls a catalog update. Every vector row stores the model name,
immutable revision, model-card license, actual weights SHA-256, embedding method,
Transformers/Pillow/preprocessor fingerprint, fixture schema, source image SHA-256,
dimensions, and little-endian float32 vector. Queries filter by the same model,
weights, method, preprocessing, and fixture identity. Repeating a run replaces
that selected vector set transactionally, so stale fixture rows cannot alter
retrieval counts. Unit tests verify version
separation, corrupt-vector rejection, deterministic fixture generation, retrieval
scoring, and that writing vectors leaves asset metadata untouched.

Cosine and top-two margin are *ranking signals*, not calibrated probabilities or
proof of identity. The fixture is tiny and programmatically drawn: shared faces,
simple colors and shapes, one reference per identity, no artist style changes,
occlusion, fan art, duplicates, or lookalike characters. Its 100% recall is a
smoke-test result with severe domain gap. No recognition result is promoted to
ground truth or used to change workflow state, tags, names, or source paths.

## Packaging and next gate

The [PyTorch installer](https://pytorch.org/get-started/locally/) lists Linux,
macOS, and Windows builds, but CPU wheel selection, Python/architecture support,
native dependencies, and installed size must be verified per target. This run
used a CUDA-linked Linux PyTorch build even though inference ran on CPU; its RSS
and package footprint should not be generalized to a CPU-only release.
[ONNX Runtime](https://onnxruntime.ai/docs/install/) offers CPU packages and
platform-specific execution providers, but ONNX export, embedding parity,
latency, and package size were not tested. A Windows/macOS/Linux clean packaging
matrix is required before a desktop distribution decision; GPU acceleration is
optional and must keep the same pinned embedding-space identity or trigger a
separate versioned vector set when numerical behavior changes materially.

The smallest useful next experiment is an artist-owned or explicitly licensed,
human-labeled set of about 20 characters with two distinct gallery drawings and
two style-shifted queries per character, plus deliberate near-lookalike negatives.
Run both pinned models without tuning on the test queries, report Recall@1/5 and
false-match examples by style, and measure the same batch-one CPU/RSS plus a
CPU-only install on Windows, macOS, and Linux. Use the observed score distribution
to assess whether a review-only suggestion threshold can be calibrated. Until
that gate, DINOv2-small is a size/latency baseline for a reversible prototype,
and neither candidate is approved as a recognition authority.
