"""
Hand Cricket — Server entry point.

Usage:
  python run.py                  # development (auto-reload, debug=True)
  python run.py --production     # production  (no reload, debug=False)

Production note:
  For high-traffic production deployments, use uvicorn directly or
  behind a process manager:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

  The single-worker constraint is intentional — all game state lives
  in-process memory (RoomRegistry).  Multiple workers would create
  isolated state silos.
"""

import argparse

import uvicorn

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand Cricket API server")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Run in production mode (no reload, debug=False)",
    )
    args = parser.parse_args()

    if args.production:
        import os
        os.environ["ENVIRONMENT"] = "production"

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload if not args.production else False,
        log_level=settings.log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()
