"""Copy stdin to an exclusive bounded file; drain but fail if the cap is exceeded."""

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--cap", type=int, default=1024 * 1024)
    args = parser.parse_args()
    if not 0 < args.cap <= 1024 * 1024:
        raise SystemExit("invalid cap")
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    total = 0
    overflow = False
    with os.fdopen(fd, "wb") as output:
        while True:
            block = os.read(0, 65536)
            if not block:
                break
            total += len(block)
            if total <= args.cap:
                output.write(block)
            else:
                overflow = True
        output.flush()
        os.fsync(output.fileno())
    if overflow:
        raise SystemExit("captured stream exceeded cap")


if __name__ == "__main__":
    main()
