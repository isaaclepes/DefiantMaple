"""Build and measure the unsigned Qt prototype artifact."""
from argparse import ArgumentParser
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    args = parser.parse_args(argv)
    executable = "pyside6-deploy.exe" if sys.platform == "win32" else "pyside6-deploy"
    environment_deploy = Path(sys.executable).parent / executable
    deploy = str(environment_deploy) if environment_deploy.exists() else shutil.which(executable)
    if not deploy:
        parser.error("pyside6-deploy is not installed")
    entry = Path(__file__).with_name("app.py")
    started = time.perf_counter()
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    cache_root = Path(tempfile.gettempdir()) / "defiantmaple-nuitka-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    environment["XDG_CACHE_HOME"] = str(cache_root)
    subprocess.run([
        deploy, str(entry), "-f", "--name", "DefiantMapleQt",
        "--nuitka-version", "4.2.2",
        "--extra-ignore-dirs", "tests,__pycache__",
    ], check=True, env=environment)
    build_seconds = time.perf_counter() - started

    candidates = []
    for root in (Path.cwd(), entry.parent):
        candidates.extend(path for path in root.rglob("DefiantMapleQt*") if path.is_file())
        candidates.extend(path for path in root.rglob("DefiantMapleQt.app") if path.is_dir())
    if not candidates:
        raise FileNotFoundError("pyside6-deploy produced no DefiantMapleQt artifact")
    artifact = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    if artifact.is_dir():
        artifact_bytes = sum(path.stat().st_size for path in artifact.rglob("*") if path.is_file())
        launchable = next(
            path for path in (artifact / "Contents" / "MacOS").iterdir()
            if path.is_file()
        )
    else:
        artifact_bytes = artifact.stat().st_size
        launchable = artifact
    benchmark_environment = environment.copy()
    benchmark_environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    benchmark_environment["DEFIANTMAPLE_LAUNCH_TIME_NS"] = str(time.time_ns())
    subprocess.run([
        str(launchable), "--catalog", str(args.catalog),
        "--benchmark-json", str(args.metrics),
    ], check=True, env=benchmark_environment)
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    metrics.update({
        "package_tool": "pyside6-deploy/Nuitka",
        "package_mode": "onefile" if artifact.is_file() else "application_bundle",
        "package_path": str(artifact),
        "package_bytes": artifact_bytes,
        "release_build_seconds": round(build_seconds, 3),
        "signed": False,
    })
    args.metrics.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
