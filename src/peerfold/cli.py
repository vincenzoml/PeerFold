"""PeerFold command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from peerfold import __version__
from peerfold.core import default_reviewer


def main() -> None:
    if getattr(sys, "frozen", False):
        print("PeerFold loading…", file=sys.stderr, flush=True)
    ap = argparse.ArgumentParser(
        prog="peerfold",
        description="Review PDFs in a native window. Highlights are standard PDF annotations.",
    )
    ap.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=None,
        help="PDF to review (optional — open from the app if omitted)",
    )
    ap.add_argument(
        "--reviewer",
        "-r",
        default=os.environ.get("PEERFOLD_REVIEWER", os.environ.get("REVIEW_VIEWER")),
        help="Short annotator name (default: username or $PEERFOLD_REVIEWER)",
    )
    ap.add_argument("--port", type=int, default=0, help="Local port (default: ephemeral)")
    ui = ap.add_mutually_exclusive_group()
    ui.add_argument(
        "--web",
        "--browser",
        action="store_true",
        help="Open in your system browser (use this over SSH)",
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
    elif args.web:
        mode = "web"
    else:
        mode = "webview"

    from peerfold.core import run_server

    run_server(
        args.pdf,
        reviewer=args.reviewer or default_reviewer(),
        port=args.port,
        ui=mode,
    )


if __name__ == "__main__":
    main()
