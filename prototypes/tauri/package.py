"""Build and measure the unsigned Tauri prototype release executable."""
from argparse import ArgumentParser
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    args = parser.parse_args(argv)

    prototype = Path(__file__).resolve().parent
    cli_name = "tauri.cmd" if sys.platform == "win32" else "tauri"
    cli = prototype / "node_modules" / ".bin" / cli_name
    if not cli.exists():
        parser.error("install the pinned Tauri CLI with npm install --prefix prototypes/tauri")

    environment = os.environ.copy()
    subprocess.run(
        [str(cli), "icon", str(prototype / "app-icon.svg")],
        cwd=prototype,
        env=environment,
        check=True,
    )
    target = prototype / "src-tauri" / "target"
    shutil.rmtree(target, ignore_errors=True)
    started = time.perf_counter()
    subprocess.run(
        [str(cli), "build", "--no-bundle"],
        cwd=prototype,
        env=environment,
        check=True,
    )
    build_seconds = time.perf_counter() - started

    suffix = ".exe" if sys.platform == "win32" else ""
    artifact = prototype / "src-tauri" / "target" / "release" / f"defiantmaple-tauri{suffix}"
    if not artifact.is_file():
        raise FileNotFoundError(f"Tauri produced no release executable at {artifact}")

    metrics_path = args.metrics.resolve()
    benchmark_environment = environment.copy()
    benchmark_environment.update({
        "DEFIANTMAPLE_CATALOG": str(args.catalog.resolve()),
        "DEFIANTMAPLE_METRICS": str(metrics_path),
        "DEFIANTMAPLE_LAUNCH_TIME_NS": str(time.time_ns()),
    })
    command = [str(artifact)]
    if sys.platform.startswith("linux"):
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            command = [xvfb, "-a", *command]
        benchmark_environment.setdefault("GDK_BACKEND", "x11")
        benchmark_environment.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
    subprocess.run(
        command,
        cwd=prototype,
        env=benchmark_environment,
        check=True,
        timeout=180,
    )

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if "error" in metrics:
        raise RuntimeError(f"packaged benchmark failed: {metrics['error']}")
    metrics.update({
        "package_tool": "Tauri CLI",
        "package_mode": "release_executable_system_webview",
        "package_path": str(artifact),
        "package_bytes": artifact.stat().st_size,
        "release_build_seconds": round(build_seconds, 3),
        "signed": False,
    })
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
