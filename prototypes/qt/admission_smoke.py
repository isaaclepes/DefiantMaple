"""Generated actual-executable admission exclusion and release preservation smoke."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

from defiantmaple.catalog import initialize


def frozen_admission_smoke(command_prefix, environment):
    with tempfile.TemporaryDirectory(prefix="defiantmaple-admission-smoke-") as temporary:
        root = Path(temporary)
        catalog = root / "generated.sqlite3"
        initialize(catalog)
        before = hashlib.sha256(catalog.read_bytes()).hexdigest()
        owned = subprocess.run([*command_prefix, "--catalog", str(catalog), "--smoke-admission"],
                               check=True, capture_output=True, text=True, env=environment, timeout=60)
        report = json.loads(owned.stdout)
        expected = {"schema": "defiantmaple.admission-smoke.v1", "status": "passed",
                    "second_client_refused": True, "owner_still_valid": True}
        if report != expected:
            raise ValueError("Executable admission smoke returned an unexpected result")
        reopened = subprocess.run([*command_prefix, "--catalog", str(catalog), "--smoke-admission-probe"],
                                  check=True, capture_output=True, text=True, env=environment, timeout=30)
        if json.loads(reopened.stdout) != {"admission_acquired": True}:
            raise ValueError("Executable admission lease was not released")
        if hashlib.sha256(catalog.read_bytes()).hexdigest() != before:
            raise ValueError("Admission smoke mutated its generated catalog")
        if {path.name for path in root.iterdir()} != {catalog.name}:
            raise ValueError("Admission smoke left unexpected files beside its generated catalog")
        return {**report, "released_and_reopened": True, "catalog_unchanged": True}
