"""Lightweight desktop entry point; spawned core workers skip GUI imports."""
import multiprocessing


if __name__ == "__main__":
    multiprocessing.freeze_support()
    from prototypes.qt.app import main

    raise SystemExit(main())
