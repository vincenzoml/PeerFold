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
        description="Review PDFs in a native window. Highlights are standard PDF annotations.",
    )
    ap.add_argument("pdf", type=Path, help="PDF to review")
    ap.add_argument(
        "--reviewer",
        "-r",
        default=os.environ.get("PEERFOLD_REVIEWER", os.environ.get("REVIEW_VIEWER", "rev")),
        help="Short annotator name (default: $PEERFOLD_REVIEWER or 'rev')",
    )
    ap.add_argument("--port", type=int, default=0, help="Local port (default: ephemeral)")
    ui = ap.add_mutually_exclusive_group()
    ui.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system browser instead of the embedded window",
    )
    ui.add_argument(
        "--no-browser",
        action="store_true",
        help="Start server only; do not open a window",
    )
    ap.add_argument("--version", action="version", version=f"peerfold {__version__}")
    args = ap.parse_args()

    if args.no_browser:
        mode = "none"
    elif args.browser:
        mode = "browser"
    else:
        mode = "webview"

    run_server(
        args.pdf,
        reviewer=args.reviewer,
        port=args.port,
        ui=mode,
    )


if __name__ == "__main__":
    main()
