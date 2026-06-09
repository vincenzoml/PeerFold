"""PeerFold command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from peerfold import __version__
from peerfold.core import run_server


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="peerfold",
        description="Review PDFs in the browser. Highlights are standard PDF annotations.",
    )
    ap.add_argument("pdf", type=Path, help="PDF to review")
    ap.add_argument(
        "--reviewer",
        "-r",
        default=os.environ.get("PEERFOLD_REVIEWER", os.environ.get("REVIEW_VIEWER", "rev")),
        help="Short annotator name (default: $PEERFOLD_REVIEWER or 'rev')",
    )
    ap.add_argument("--port", type=int, default=0, help="Local port (default: ephemeral)")
    ap.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    ap.add_argument("--version", action="version", version=f"peerfold {__version__}")
    args = ap.parse_args()

    run_server(
        args.pdf,
        reviewer=args.reviewer,
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
