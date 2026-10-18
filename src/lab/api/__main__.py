"""python -m lab.api [--port 8000]   Serves on 127.0.0.1 only. Stage 1 refuses any other host."""
from __future__ import annotations

import argparse
from typing import Sequence

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lab.api", description=__doc__)
    ap.add_argument("--host", default="127.0.0.1", help="loopback only: 127.0.0.1, localhost or ::1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        ap.error("Stage 1 API is local-only; refusing a non-loopback host")
    import uvicorn  # imported here so `import lab.api` never needs the web stack

    from .app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
