"""Offline image-embedding comparison; never writes to the asset catalog."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import struct
import sys
import threading
import time

from PIL import Image, __version__ as pillow_version

from benchmarks.embedding_fixture import generate


MODELS = {
    "dinov2-small": {
        "name": "facebook/dinov2-small",
        "revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056",
        "license": "Apache-2.0",
        "weights_bytes": 88249960,
        "weights_sha256": "ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1",
        "method": "cls-token",
    },
    "siglip-base": {
        "name": "google/siglip-base-patch16-224",
        "revision": "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed",
        "license": "Apache-2.0",
        "weights_bytes": 812672320,
        "weights_sha256": "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8",
        "method": "image-projection",
    },
}

STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    model_name TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    model_license TEXT NOT NULL,
    weights_sha256 TEXT NOT NULL,
    embedding_method TEXT NOT NULL,
    preprocessing_version TEXT NOT NULL,
    fixture_schema TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    file_name TEXT NOT NULL,
    label TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('gallery','query')),
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector_f32 BLOB NOT NULL,
    PRIMARY KEY(model_name,model_revision,weights_sha256,embedding_method,
                preprocessing_version,fixture_schema,image_sha256)
);
"""


def write_vector(db: sqlite3.Connection, item: dict, meta: dict, values) -> None:
    if not meta["name"] or len(meta["revision"]) != 40:
        raise ValueError("A pinned model name and 40-character revision are required")
    if len(meta["weights_sha256"]) != 64:
        raise ValueError("A SHA-256 fingerprint of the actual weights is required")
    if any(not meta[key] for key in ("license", "method", "preprocessing_version", "fixture_schema")):
        raise ValueError("License, method, preprocessing, and fixture versions are required")
    if len(item["sha256"]) != 64:
        raise ValueError("A SHA-256 fingerprint of the input image is required")
    values = [float(value) for value in values]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("The embedding must be a nonempty finite vector")
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        raise ValueError("The embedding must be nonzero")
    normalized = [value / magnitude for value in values]
    db.execute(
        "INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (meta["name"], meta["revision"], meta["license"], meta["weights_sha256"],
         meta["method"], meta["preprocessing_version"], meta["fixture_schema"],
         item["sha256"], item["file"], item["label"], item["role"],
         len(normalized), struct.pack(f"<{len(normalized)}f", *normalized)),
    )


def read_vectors(db: sqlite3.Connection, meta: dict):
    rows = db.execute(
        "SELECT file_name,label,role,dimensions,vector_f32 FROM vectors "
        "WHERE model_name=? AND model_revision=? AND weights_sha256=? "
        "AND embedding_method=? AND preprocessing_version=? AND fixture_schema=? "
        "ORDER BY file_name",
        (meta["name"], meta["revision"], meta["weights_sha256"], meta["method"],
         meta["preprocessing_version"], meta["fixture_schema"]),
    ).fetchall()
    result = []
    for file_name, label, role, dimensions, blob in rows:
        if len(blob) != dimensions * 4:
            raise ValueError(f"Damaged vector: {file_name}")
        values = struct.unpack(f"<{dimensions}f", blob)
        result.append({"file": file_name, "label": label, "role": role, "vector": values})
    return result


def score_retrieval(rows):
    gallery = [row for row in rows if row["role"] == "gallery"]
    queries = [row for row in rows if row["role"] == "query"]
    if not gallery or not queries:
        raise ValueError("Fixture needs gallery and query images")
    if len({len(row["vector"]) for row in rows}) != 1:
        raise ValueError("Cannot compare vectors with different dimensions")
    details = []
    for query in queries:
        scores = sorted(
            ((sum(a * b for a, b in zip(query["vector"], candidate["vector"])),
              candidate["label"], candidate["file"]) for candidate in gallery),
            reverse=True,
        )
        correct_ranks = [rank for rank, (_, label, _) in enumerate(scores, 1)
                         if label == query["label"]]
        if not correct_ranks:
            raise ValueError(f"No gallery reference for {query['label']}")
        details.append({"query": query["file"], "label": query["label"],
                        "top_label": scores[0][1], "rank": correct_ranks[0],
                        "top_cosine": round(scores[0][0], 5),
                        "margin": round(scores[0][0] - scores[1][0], 5)
                        if len(scores) > 1 else None})
    return {"queries": len(details),
            "recall_at_1": sum(row["rank"] == 1 for row in details) / len(details),
            "mean_reciprocal_rank": sum(1 / row["rank"] for row in details) / len(details),
            "per_query": details,
            "score_warning": "Cosine and margin are ranking signals, not calibrated identity confidence."}


def _memory_sampler(samples, stop):
    import psutil
    process = psutil.Process(os.getpid())
    while not stop.is_set():
        samples.append(process.memory_info().rss)
        stop.wait(0.01)
    samples.append(process.memory_info().rss)


def run(model_key: str, fixture_dir: Path, output_dir: Path, device: str = "cpu"):
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoImageProcessor, AutoModel, __version__ as transformers_version

    if device != "cpu" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable; run the required CPU benchmark")
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    model_meta = MODELS[model_key]
    fixture = generate(fixture_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = Path(snapshot_download(
        model_meta["name"], revision=model_meta["revision"], local_files_only=True,
        allow_patterns=["config.json", "preprocessor_config.json", "model.safetensors"],
    ))
    if model_path.resolve().name != model_meta["revision"]:
        raise ValueError("Model directory must resolve to the pinned revision")
    weights = model_path / "model.safetensors"
    digest = sha256()
    with weights.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    actual_hash = digest.hexdigest()
    if actual_hash != model_meta["weights_sha256"]:
        raise ValueError("Downloaded weights do not match the pinned SHA-256")
    processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
    samples = []
    stop = threading.Event()
    sampler = threading.Thread(target=_memory_sampler, args=(samples, stop), daemon=True)
    sampler.start()
    start = time.perf_counter()
    model = AutoModel.from_pretrained(model_path, local_files_only=True,
                                      use_safetensors=True).eval().to(device)
    load_seconds = time.perf_counter() - start
    import psutil
    memory_after_load = psutil.Process(os.getpid()).memory_info().rss
    meta = {"name": model_meta["name"], "revision": model_meta["revision"],
            "license": model_meta["license"], "weights_sha256": actual_hash,
            "method": model_meta["method"],
            "preprocessing_version": f"transformers-{transformers_version}:pillow-{pillow_version}:" +
            sha256((model_path / "preprocessor_config.json").read_bytes()).hexdigest(),
            "fixture_schema": fixture["schema"]}

    def embed(path):
        with Image.open(path) as source:
            inputs = processor(images=source.convert("RGB"), return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            if model_key == "dinov2-small":
                vector = model(**inputs).last_hidden_state[:, 0, :]
            else:
                output = model.get_image_features(**inputs)
                vector = output if isinstance(output, torch.Tensor) else output.pooler_output
        return vector[0].float().cpu().tolist()

    first = fixture["items"][0]
    for _ in range(2):
        embed(fixture_dir / first["file"])
    times = []
    database = output_dir / f"{model_key}-{device}.sqlite3"
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(STORE_SCHEMA)
        for item in fixture["items"]:
            start = time.perf_counter()
            vector = embed(fixture_dir / item["file"])
            times.append((time.perf_counter() - start) * 1000)
            write_vector(db, item, meta, vector)
        retrieval = score_retrieval(read_vectors(db, meta))
    stop.set()
    sampler.join()
    report = {"schema": "defiantmaple.embedding-benchmark.v1", "model": meta,
              "weights_bytes": weights.stat().st_size, "vector_dimensions": len(vector),
              "device": device, "torch_version": torch.__version__,
              "python_version": sys.version.split()[0], "platform": platform.platform(),
              "pillow_version": pillow_version,
              "cpu_threads": torch.get_num_threads(),
              "optional_gpu": {
                  "cuda_available": torch.cuda.is_available(),
                  "mps_available": bool(getattr(torch.backends, "mps", None)
                                        and torch.backends.mps.is_available()),
                  "rocm_version": torch.version.hip,
                  "gpu_measured": device != "cpu",
              },
              "load_seconds": round(load_seconds, 3),
              "latency_ms_p50": round(statistics.median(times), 2),
              "latency_ms_p95": round(sorted(times)[math.ceil(.95 * len(times)) - 1], 2),
              "memory_rss_after_load_mib": round(memory_after_load / 1048576, 1),
              "memory_rss_peak_mib": round(max(samples) / 1048576, 1),
              "fixture_count": len(fixture["items"]), "retrieval": retrieval}
    (output_dir / f"{model_key}-{device}-metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=MODELS)
    parser.add_argument("--fixture", type=Path, default=Path(".venv-benchmark/fixture"))
    parser.add_argument("--output", type=Path, default=Path(".venv-benchmark/results"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    print(json.dumps(run(args.model, args.fixture, args.output, args.device), indent=2))


if __name__ == "__main__":
    main()
