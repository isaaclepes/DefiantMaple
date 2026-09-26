"""Build and measure the unsigned Qt prototype artifact."""
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def find_artifact(*roots: Path) -> Path:
    bundle_candidates = []
    file_candidates = []
    for root in roots:
        bundle_candidates.extend(path for path in root.rglob("DefiantMapleQt.app") if path.is_dir())
        file_candidates.extend(
            path for path in root.rglob("DefiantMapleQt*")
            if path.is_file() and not any(parent.suffix == ".app" for parent in path.parents)
        )
    candidates = bundle_candidates or file_candidates
    if not candidates:
        raise FileNotFoundError("pyside6-deploy produced no DefiantMapleQt artifact")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def bundle_launchable(bundle: Path) -> Path:
    executable_dir = bundle / "Contents" / "MacOS"
    preferred = executable_dir / bundle.stem
    if preferred.is_file():
        return preferred
    executables = [
        path for path in executable_dir.iterdir()
        if path.is_file() and os.access(path, os.X_OK)
    ]
    if len(executables) != 1:
        raise FileNotFoundError(f"could not identify application executable in {executable_dir}")
    return executables[0]


def add_nuitka_download_consent(spec: Path) -> None:
    config = ConfigParser()
    config.read(spec, encoding="utf-8")
    extra_args = config.get("nuitka", "extra_args", fallback="")
    config.set("nuitka", "extra_args", f"{extra_args} --assume-yes-for-downloads".strip())
    with spec.open("w", encoding="utf-8") as stream:
        config.write(stream)


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
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    cache_root = Path(tempfile.gettempdir()) / "defiantmaple-nuitka-cache"
    shutil.rmtree(cache_root, ignore_errors=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    environment["XDG_CACHE_HOME"] = str(cache_root)
    for root in {Path.cwd().resolve(), entry.parent.resolve()}:
        for name in ("DefiantMapleQt", "DefiantMapleQt.bin", "DefiantMapleQt.exe", "DefiantMapleQt.app"):
            stale = root / name
            if stale.is_dir():
                shutil.rmtree(stale)
            elif stale.exists():
                stale.unlink()
    spec = entry.parent / "pysidedeploy.spec"
    if spec.exists():
        spec.unlink()
    deploy_command = [
        deploy, str(entry), "-f", "--name", "DefiantMapleQt",
        "--nuitka-version", "4.2.2",
        "--extra-ignore-dirs", "tests,__pycache__",
    ]
    if sys.platform == "win32":
        subprocess.run(
            [*deploy_command, "--init"],
            cwd=entry.parent,
            check=True,
            env=environment,
        )
        add_nuitka_download_consent(spec)
        deploy_command = [
            deploy, "-c", str(spec), "-f", "--nuitka-version", "4.2.2",
        ]
    started = time.perf_counter()
    subprocess.run(deploy_command, cwd=entry.parent, check=True, env=environment)
    build_seconds = time.perf_counter() - started

    artifact = find_artifact(Path.cwd(), entry.parent)
    if artifact.is_dir():
        artifact_bytes = sum(path.stat().st_size for path in artifact.rglob("*") if path.is_file())
        launchable = bundle_launchable(artifact)
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
