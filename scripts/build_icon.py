#!/usr/bin/env python3
"""Render assets/icon.svg into app icons (macOS icns, PNG sizes, favicon)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "assets" / "icon.svg"
STATIC = ROOT / "src" / "peerfold" / "static"
ASSETS = ROOT / "assets"
ICNS = ASSETS / "PeerFold.icns"
SIZES = (16, 32, 64, 128, 180, 256, 512, 1024)


def render_master_png(dest: Path, size: int = 1024) -> None:
    if sys.platform != "darwin":
        raise SystemExit("Icon rendering requires macOS (AppKit SVG rasterizer).")
    import AppKit
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(SVG.resolve()))
    image = AppKit.NSImage.alloc().initWithContentsOfURL_(url)
    if image is None:
        raise SystemExit(f"Could not load {SVG}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False,
        AppKit.NSDeviceRGBColorSpace, 0, 0,
    )
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(
        AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    )
    image.drawInRect_fromRect_operation_fraction_(
        ((0, 0), (size, size)), ((0, 0), (image.size().width, image.size().height)),
        AppKit.NSCompositingOperationCopy, 1.0,
    )
    AppKit.NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(AppKit.NSPNGFileType, None)
    dest.write_bytes(bytes(data))


def resize_png(src: Path, dest: Path, size: int) -> None:
    subprocess.run(["sips", "-z", str(size), str(size), str(src), "--out", str(dest)], check=True)


def build_icns(master: Path) -> None:
    iconset = ASSETS / "PeerFold.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    mapping = (
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    )
    for size, name in mapping:
        out = iconset / name
        resize_png(master, out, size)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICNS)], check=True)
    shutil.rmtree(iconset)


def main() -> None:
    if not SVG.is_file():
        raise SystemExit(f"Missing {SVG}")
    master = ASSETS / "icon-1024.png"
    render_master_png(master)
    STATIC.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        resize_png(master, STATIC / f"icon-{size}.png", size)
    shutil.copy2(STATIC / "icon-32.png", STATIC / "favicon.png")
    build_icns(master)
    print(f"Wrote {ICNS}")
    print(f"Wrote {STATIC}/icon-*.png")


if __name__ == "__main__":
    main()
