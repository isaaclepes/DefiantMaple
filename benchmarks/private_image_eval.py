"""Explicit offline inference on individually curated, rights-cleared local art.

No paths, names, hashes, vectors, or per-image scores appear in the public
summary. The private SQLite selection/vector stores remain outside Git and art.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import struct
import time

from PIL import Image, __version__ as pillow_version

from benchmarks.image_embeddings import MODELS
from defiantmaple.catalog import connect
from defiantmaple.private_eval import (PrivateSelectionStore, _sha256,
                                       assert_outside_git, assert_outside_sources,
                                       sanitize_public_summary)
from defiantmaple.sources import list_sources


VECTOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    asset_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    model_license TEXT NOT NULL,
    weights_sha256 TEXT NOT NULL,
    preprocessing_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    anonymous_id TEXT NOT NULL,
    role TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector_f32 BLOB NOT NULL,
    PRIMARY KEY(asset_id,model_name,model_revision,weights_sha256,preprocessing_version)
);
"""


def _normalized(values) -> tuple[float, ...]:
    values = tuple(float(value) for value in values)
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("Invalid model vector")
    magnitude = math.sqrt(sum(value * value for value in values))
    if not magnitude:
        raise ValueError("Zero model vector")
    return tuple(value / magnitude for value in values)


def _aggregate(rows: list[dict], latency_ms: list[float], peak_mib: float,
               excluded_uncertain: int) -> dict:
    references = [row for row in rows if row["role"] == "reference"]
    queries = [row for row in rows if row["role"] == "query"]
    negatives = [row for row in rows if row["role"] == "near-lookalike-negative"]
    if len({len(row["vector"]) for row in rows}) != 1:
        raise ValueError("Private vectors must share one dimension")
    candidates = references + negatives
    ranks = []
    categories = {"lookalike": 0, "other": 0}
    for query in queries:
        ordered = sorted(
            ((sum(a * b for a, b in zip(query["vector"], candidate["vector"])),
              candidate["anonymous_id"], candidate["role"]) for candidate in candidates),
            reverse=True,
        )
        matches = [rank for rank, (_, label, role) in enumerate(ordered, 1)
                   if role == "reference" and label == query["anonymous_id"]]
        if not matches:
            raise ValueError("Every query needs a rights-cleared reference")
        ranks.append(matches[0])
        if matches[0] != 1:
            categories["lookalike" if ordered[0][2] == "near-lookalike-negative"
                       else "other"] += 1
    raw = {
        "schema": "defiantmaple.private-eval-summary.v1",
        "dataset_counts": {"characters": len({r["anonymous_id"] for r in references}),
                           "references": len(references), "queries": len(queries),
                           "negatives": len(negatives),
                           "excluded_uncertain": excluded_uncertain},
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks) if ranks else None,
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(ranks) if ranks else None,
        "mean_reciprocal_rank": (sum(1 / rank for rank in ranks) / len(ranks)
                                 if ranks else None),
        "latency_ms_p50": statistics.median(latency_ms) if latency_ms else None,
        "memory_rss_peak_mib": peak_mib,
        "false_match_categories": categories,
    }
    return sanitize_public_summary(raw)


def evaluate_offline(catalog: Path, selection_db: Path, vector_db: Path,
                     summary_path: Path, *, model_key: str = "dinov2-small") -> dict:
    """Run only on explicit selections; requires weights already in the local cache."""
    import psutil
    import torch
    from huggingface_hub import snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE
    from transformers import AutoImageProcessor, AutoModel, __version__ as transformer_version

    catalog = Path(catalog).resolve(strict=True)
    sources = {source["source_id"]: source for source in list_sources(catalog)}
    roots = [source["root_path"] for source in sources.values()]
    for path in (selection_db, vector_db, summary_path):
        assert_outside_sources(path, roots)
        assert_outside_git(path)
    assert_outside_sources(Path(HF_HUB_CACHE), roots)
    assert_outside_git(Path(HF_HUB_CACHE))
    if len({str(Path(path).resolve(strict=False)) for path in
            (catalog, selection_db, vector_db, summary_path)}) != 4:
        raise ValueError("Catalog, selections, vectors, and summary need separate files")
    store = PrivateSelectionStore(selection_db, catalog)
    all_selections = store.entries(include_uncertain=True)
    selections = [row for row in all_selections if row["rights_status"] != "uncertain"]
    if not selections:
        raise ValueError("No rights-cleared selections")
    if not any(row["role"] == "reference" for row in selections):
        raise ValueError("Add a rights-cleared reference before evaluation")
    model_meta = MODELS[model_key]
    model_path = Path(snapshot_download(
        model_meta["name"], revision=model_meta["revision"], local_files_only=True,
        allow_patterns=["config.json", "preprocessor_config.json", "model.safetensors"],
    ))
    assert_outside_sources(model_path, roots)
    assert_outside_git(model_path)
    if model_path.resolve().name != model_meta["revision"]:
        raise ValueError("Model cache revision mismatch")
    if _sha256(model_path / "model.safetensors") != model_meta["weights_sha256"]:
        raise ValueError("Model weights hash mismatch")
    processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    model = AutoModel.from_pretrained(model_path, local_files_only=True,
                                      use_safetensors=True).eval().to("cpu")
    preprocessing = (f"transformers-{transformer_version}:pillow-{pillow_version}:"
                     + hashlib.sha256((model_path / "preprocessor_config.json").read_bytes()).hexdigest())
    process = psutil.Process(os.getpid())
    peak = process.memory_info().rss
    output = []
    latency_ms = []
    vector_db = Path(vector_db)
    vector_db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(vector_db)) as private_vectors, private_vectors:
        private_vectors.executescript(VECTOR_SCHEMA)
        private_vectors.execute("DELETE FROM vectors WHERE model_name=? AND model_revision=?",
                                (model_meta["name"], model_meta["revision"]))
        for selected in selections:
            with connect(catalog) as db:
                asset = db.execute(
                    "SELECT current_path,sha256,media_type,source_id FROM assets WHERE asset_id=?",
                    (selected["asset_id"],),
                ).fetchone()
            if asset is None or asset["sha256"] != selected["source_sha256"]:
                raise ValueError("Selected asset changed; curate it again")
            if not asset["media_type"].startswith("image/") or asset["source_id"] not in sources:
                raise ValueError("Selections must be image assets from registered sources")
            path = Path(asset["current_path"])
            root = Path(sources[asset["source_id"]]["root_path"]).resolve(strict=False)
            if path.is_symlink() or root not in path.resolve(strict=True).parents:
                raise ValueError("Selected image is outside its source or is a symlink")
            if _sha256(path) != asset["sha256"]:
                raise ValueError("Selected image changed on disk; rescan before evaluation")
            started = time.perf_counter()
            with Image.open(path) as source:
                inputs = processor(images=source.convert("RGB"), return_tensors="pt")
            with torch.inference_mode():
                if model_key == "dinov2-small":
                    tensor = model(**inputs).last_hidden_state[:, 0, :]
                else:
                    features = model.get_image_features(**inputs)
                    tensor = (features if isinstance(features, torch.Tensor)
                              else features.pooler_output)
            vector = _normalized(tensor[0].float().tolist())
            latency_ms.append((time.perf_counter() - started) * 1000)
            peak = max(peak, process.memory_info().rss)
            private_vectors.execute(
                "INSERT INTO vectors VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (selected["asset_id"], model_meta["name"], model_meta["revision"],
                 model_meta["license"], model_meta["weights_sha256"], preprocessing,
                 selected["source_sha256"], selected["anonymous_id"], selected["role"],
                 len(vector), struct.pack(f"<{len(vector)}f", *vector)),
            )
            output.append({"anonymous_id": selected["anonymous_id"], "role": selected["role"],
                           "vector": vector})
    summary = _aggregate(output, latency_ms, round(peak / 1048576, 1),
                         len(all_selections) - len(selections))
    summary_path = Path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--selections", required=True, type=Path)
    parser.add_argument("--vectors", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--model", choices=MODELS, default="dinov2-small")
    args = parser.parse_args()
    print(json.dumps(evaluate_offline(args.catalog, args.selections, args.vectors,
                                      args.summary, model_key=args.model), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
