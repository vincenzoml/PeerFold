"""PeerFold server core: PDF session, annotations, and HTTP API."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


def static_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "peerfold" / "static"
    return Path(str(resources.files("peerfold") / "static"))


def data_dir() -> Path:
    if custom := os.environ.get("PEERFOLD_DATA"):
        root = Path(custom).expanduser()
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "PeerFold"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home())) / "PeerFold"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "share" / "peerfold"
    root.mkdir(parents=True, exist_ok=True)
    return root


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path
REVIEWER_RE = re.compile(r"^[A-Za-z0-9._-]{1,16}$")
REVIEW_FILE_RE = re.compile(
    r"^(?P<stem>.+)_(?P<reviewer>[A-Za-z0-9._-]{1,16})-(?P<stamp>\d{4}-\d{2}-\d{2})\.pdf$"
)
MAX_BACKUPS = 12

PALETTE: dict[str, tuple[float, float, float]] = {
    "yellow": (1.0, 0.92, 0.23),
    "green": (0.55, 0.76, 0.29),
    "blue": (0.26, 0.65, 0.96),
    "pink": (0.96, 0.56, 0.69),
    "orange": (1.0, 0.72, 0.30),
}
LINE_Y_TOL = 4.0
_BIB_LINE_RE = re.compile(r"^(\d+)\.\s+")
_CITE_BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def _find_references_start(doc) -> tuple[int, float]:
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = "".join(span.get("text", "") for span in line.get("spans", []))
                if "References" in text:
                    return pno, float(line["bbox"][1])
    return doc.page_count, float("inf")


def build_citation_index(doc) -> tuple[list[tuple[int, int, float]], dict[int, str]]:
    """Map numbered bibliography entries to their primary outbound URL."""
    ref_page, ref_y = _find_references_start(doc)
    entries: list[tuple[int, int, float]] = []
    seen_nums: set[int] = set()
    for pno in range(ref_page, doc.page_count):
        page = doc.load_page(pno)
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                y0 = float(line["bbox"][1])
                if pno == ref_page and y0 < ref_y + 8:
                    continue
                text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                match = _BIB_LINE_RE.match(text)
                if not match:
                    continue
                num = int(match.group(1))
                if num in seen_nums:
                    continue
                seen_nums.add(num)
                entries.append((num, pno, y0))
    entries.sort(key=lambda item: (item[1], item[2]))

    by_page: dict[int, list[tuple[int, float]]] = {}
    for num, pno, y0 in entries:
        by_page.setdefault(pno, []).append((num, y0))

    urls: dict[int, str] = {}
    for pno, page_entries in by_page.items():
        page_entries.sort(key=lambda item: item[1])
        page = doc.load_page(pno)
        link_rows: list[tuple[float, str]] = []
        for raw in page.get_links() or []:
            uri = raw.get("uri")
            rect = raw.get("from")
            if not uri or rect is None:
                continue
            link_rows.append((float(rect.y0), str(uri).strip()))
        link_rows.sort(key=lambda item: item[0])
        for idx, (num, y0) in enumerate(page_entries):
            y1 = page_entries[idx + 1][1] if idx + 1 < len(page_entries) else float("inf")
            for link_y, uri in link_rows:
                if y0 - 5 <= link_y < y1 and num not in urls:
                    urls[num] = uri
                    break
    return entries, urls


def _line_words(page, bbox: list[float]) -> list[tuple[float, float, float, float, str]]:
    cx = (bbox[0] + bbox[2]) * 0.5
    cy = (bbox[1] + bbox[3]) * 0.5
    clip = (bbox[0] - 160, cy - 6, bbox[2] + 160, cy + 6)
    words = page.get_text("words", clip=clip)
    return [w for w in words if abs((w[1] + w[3]) * 0.5 - cy) < 5]


def cite_numbers_for_link(page, bbox: list[float]) -> list[int]:
    """Read citation numbers from bracket text overlapping a PDF link box."""
    cx = (bbox[0] + bbox[2]) * 0.5
    words = sorted(_line_words(page, bbox), key=lambda w: w[0])
    bracket_spans: list[tuple[float, float, list[int]]] = []
    i = 0
    while i < len(words):
        if "[" not in words[i][4]:
            i += 1
            continue
        x0 = float(words[i][0])
        parts: list[str] = []
        x1 = x0
        while i < len(words):
            x1 = float(words[i][2])
            parts.append(words[i][4])
            i += 1
            if "]" in parts[-1]:
                break
        match = _CITE_BRACKET_RE.search("".join(parts))
        if match:
            nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
            bracket_spans.append((x0, x1, nums))
    for x0, x1, nums in bracket_spans:
        if x0 - 2 <= cx <= x1 + 2:
            return nums
    if bracket_spans:
        _, _, nums = min(bracket_spans, key=lambda s: abs((s[0] + s[1]) * 0.5 - cx))
        return nums
    return []


def pick_cite_for_click(page, bbox: list[float], nums: list[int]) -> int | None:
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    cx = (bbox[0] + bbox[2]) * 0.5
    best: int | None = None
    best_dist = float("inf")
    for w in _line_words(page, bbox):
        token = w[4].strip(",; ")
        for num in nums:
            if token != str(num):
                continue
            dist = abs((w[0] + w[2]) * 0.5 - cx)
            if dist < best_dist:
                best_dist = dist
                best = num
    if best is not None:
        return best
    # Hyperref often emits one word token per bracket, e.g. "[22,13]."
    for w in _line_words(page, bbox):
        match = _CITE_BRACKET_RE.search(w[4])
        if not match:
            continue
        inner = match.group(1)
        full = w[4]
        bracket_start = full.find("[")
        x0, x1 = float(w[0]), float(w[2])
        char_w = (x1 - x0) / max(len(full), 1)
        for num in nums:
            s = str(num)
            pos = inner.find(s)
            if pos < 0:
                continue
            abs_pos = bracket_start + 1 + pos
            num_cx = x0 + (abs_pos + len(s) * 0.5) * char_w
            dist = abs(num_cx - cx)
            if dist < best_dist:
                best_dist = dist
                best = num
    return best if best is not None else nums[0]


def merge_line_rects(spans: list[dict[str, Any]], *, y_tol: float = LINE_Y_TOL) -> list[list[float]]:
    """Merge span boxes into one rectangle per text line (Acrobat-style highlights)."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    lines: list[list[dict[str, Any]]] = []
    for sp in ordered:
        y0 = sp["bbox"][1]
        for line in lines:
            if abs(y0 - line[0]["bbox"][1]) <= y_tol:
                line.append(sp)
                break
        else:
            lines.append([sp])
    rects: list[list[float]] = []
    for line in lines:
        rects.append(
            [
                min(s["bbox"][0] for s in line),
                min(s["bbox"][1] for s in line),
                max(s["bbox"][2] for s in line),
                max(s["bbox"][3] for s in line),
            ]
        )
    return rects


def _rects_overlap(a: list[float], b: list[float], tol: float = 1.0) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (
        ax1 < bx0 - tol
        or bx1 < ax0 - tol
        or ay1 < by0 - tol
        or by1 < ay0 - tol
    )


def _annotation_overlaps_rects(ann_rects: list[list[float]], new_rects: list[list[float]]) -> bool:
    return any(_rects_overlap(a, b) for a in ann_rects for b in new_rects)


def import_fitz():
    import fitz  # PyMuPDF

    return fitz


def sanitize_reviewer(name: str) -> str:
    name = name.strip()
    if not REVIEWER_RE.fullmatch(name):
        raise ValueError("reviewer must be 1–16 chars: letters, digits, . _ -")
    return name


def default_reviewer() -> str:
    for key in ("PEERFOLD_REVIEWER", "REVIEW_VIEWER"):
        if raw := os.environ.get(key, "").strip():
            try:
                return sanitize_reviewer(raw)
            except ValueError:
                pass
    import getpass

    raw = getpass.getuser().strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:16].strip("._-")
    if cleaned and REVIEWER_RE.fullmatch(cleaned):
        return cleaned
    return "rev"


def annotated_path(source: Path, reviewer: str, stamp: str | None = None) -> Path:
    reviewer = sanitize_reviewer(reviewer)
    day = stamp or date.today().isoformat()
    return source.with_name(f"{source.stem}_{reviewer}-{day}{source.suffix}")


def save_copy_enabled() -> bool:
    """When false (default), annotations are written to the source PDF in place."""
    raw = os.environ.get("PEERFOLD_SAVE_COPY", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def session_paths(source: Path, reviewer: str) -> tuple[Path, Path]:
    """Return (open_path, save_path) for a review session."""
    source = source.resolve()
    if not save_copy_enabled():
        return source, source
    open_path = latest_review_for(source, reviewer) or source
    if open_path != source:
        return open_path, open_path
    return source, annotated_path(source, reviewer)


def parse_review_file(path: Path, source_stem: str) -> dict[str, Any] | None:
    m = REVIEW_FILE_RE.match(path.name)
    if not m or m.group("stem") != source_stem:
        return None
    try:
        sanitize_reviewer(m.group("reviewer"))
    except ValueError:
        return None
    stat = path.stat()
    return {
        "reviewer": m.group("reviewer"),
        "stamp": m.group("stamp"),
        "path": str(path.resolve()),
        "name": path.name,
        "mtime": stat.st_mtime,
    }


def scan_reviews(source: Path) -> list[dict[str, Any]]:
    parent = source.parent
    stem = source.stem
    found: list[dict[str, Any]] = []
    for candidate in parent.glob(f"{stem}_*-*.pdf"):
        row = parse_review_file(candidate, stem)
        if row:
            found.append(row)
    found.sort(key=lambda r: (r["stamp"], r["mtime"]), reverse=True)
    return found


def reviewers_for_source(source: Path) -> list[str]:
    names = {r["reviewer"] for r in scan_reviews(source)}
    return sorted(names, key=str.lower)


def latest_review_for(source: Path, reviewer: str) -> Path | None:
    reviewer = sanitize_reviewer(reviewer)
    matches = [r for r in scan_reviews(source) if r["reviewer"] == reviewer]
    if not matches:
        return None
    return Path(matches[0]["path"])


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(max(0, min(1, rgb[0])) * 255),
        int(max(0, min(1, rgb[1])) * 255),
        int(max(0, min(1, rgb[2])) * 255),
    )


def nearest_palette_name(rgb: tuple[float, float, float]) -> str:
    best = min(PALETTE, key=lambda k: sum((PALETTE[k][i] - rgb[i]) ** 2 for i in range(3)))
    return best


def annot_fingerprint(ann: dict[str, Any]) -> tuple[Any, ...]:
    """Stable identity for merging annotations across reloads (xrefs change)."""
    rects = ann.get("rects") or []
    rect_key = tuple(
        tuple(round(float(v), 1) for v in rect)
        for rect in rects[:3]
    )
    content = (ann.get("content") or "").strip()
    return (int(ann.get("page", 0)), rect_key, content)


class PdfSession:
    def __init__(
        self,
        source: Path,
        reviewer: str,
        fitz_mod: Any,
        *,
        defer_maintenance: bool = False,
    ) -> None:
        self.fitz = fitz_mod
        self.source = source.resolve()
        self.reviewer = sanitize_reviewer(reviewer)
        self.autosave = True
        self.unsaved = False
        self.revision = 0
        self.lock = threading.RLock()
        self.dpi = 192
        self._file_mtime = 0.0
        data_dir()
        backup_dir()
        open_path, self.save_path = session_paths(self.source, self.reviewer)
        self.doc = fitz_mod.open(str(open_path))
        self._file_mtime = self._disk_mtime()
        self._citation_entries: list[tuple[int, int, float]] = []
        self._citation_urls: dict[int, str] = {}
        self._cleanup_empty_highlights()
        if defer_maintenance:
            threading.Thread(
                target=self._deferred_citation_index,
                name="peerfold-citations",
                daemon=True,
            ).start()
        else:
            self._rebuild_citation_index()

    def _deferred_citation_index(self) -> None:
        with self.lock:
            self._rebuild_citation_index()

    def close(self) -> None:
        with self.lock:
            self.doc.close()

    def _page_size(self, page) -> tuple[float, float]:
        rect = page.rect
        return rect.width, rect.height

    def _disk_mtime(self, path: Path | None = None) -> float:
        target = path or self.save_path
        try:
            return target.stat().st_mtime if target.exists() else 0.0
        except OSError:
            return 0.0

    def _note_mtime(self) -> None:
        self._file_mtime = self._disk_mtime()

    def _bump_revision(self) -> None:
        self.revision += 1

    def _highlight_dict_from_annot(self, page_index: int, annot) -> dict[str, Any] | None:
        if annot.type[0] != self.fitz.PDF_ANNOT_HIGHLIGHT:
            return None
        info = annot.info
        colors = annot.colors or {}
        stroke = colors.get("stroke") or colors.get("fill") or PALETTE["yellow"]
        if isinstance(stroke, (list, tuple)) and len(stroke) >= 3:
            rgb = (float(stroke[0]), float(stroke[1]), float(stroke[2]))
        else:
            rgb = PALETTE["yellow"]
        rects = self._rects_from_annot(annot)
        if not rects:
            return None
        return {
            "id": annot.xref,
            "page": page_index,
            "rects": rects,
            "color": nearest_palette_name(rgb),
            "hex": rgb_to_hex(rgb),
            "content": info.get("content") or "",
            "title": info.get("title") or "",
        }

    def _list_highlights_in_doc(self, doc) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            for annot in page.annots() or []:
                row = self._highlight_dict_from_annot(pno, annot)
                if row:
                    out.append(row)
        return out

    def _read_highlights_from_path(self, path: Path) -> list[dict[str, Any]]:
        doc = self.fitz.open(str(path))
        try:
            return self._list_highlights_in_doc(doc)
        finally:
            doc.close()

    def _merge_missing_annotations(self, disk_annots: list[dict[str, Any]]) -> int:
        local_fps = {annot_fingerprint(a) for a in self._list_highlights_in_doc(self.doc)}
        added = 0
        for da in disk_annots:
            fp = annot_fingerprint(da)
            if fp in local_fps:
                continue
            page = self.doc.load_page(int(da["page"]))
            quads = [self.fitz.Rect(*rect).quad for rect in da["rects"]]
            annot = page.add_highlight_annot(quads)
            color = PALETTE.get(da["color"], PALETTE["yellow"])
            annot.set_colors(stroke=color)
            annot.set_info(title=da.get("title") or self.reviewer, content=da.get("content") or "")
            annot.set_opacity(0.45)
            annot.update()
            local_fps.add(fp)
            added += 1
        return added

    def _reload_from_disk_file(self) -> None:
        path = self.save_path if self.save_path.exists() else self.source
        self.doc.close()
        self.doc = self.fitz.open(str(path))
        self.save_path = path
        self._rebuild_citation_index()
        self._cleanup_empty_highlights()
        self._note_mtime()
        self.unsaved = False
        self._bump_revision()

    def _refresh_from_disk_if_newer(self) -> bool:
        disk_mtime = self._disk_mtime()
        if disk_mtime <= self._file_mtime + 1e-6:
            return False
        if not self.save_path.exists():
            self._file_mtime = disk_mtime
            return False

        if self.unsaved:
            disk_annots = self._read_highlights_from_path(self.save_path)
            added = self._merge_missing_annotations(disk_annots)
            self._file_mtime = disk_mtime
            if added > 0:
                self._bump_revision()
            return added > 0

        self._reload_from_disk_file()
        return True

    def sync_from_disk(self, since: int = 0) -> dict[str, Any]:
        with self.lock:
            self._refresh_from_disk_if_newer()
            return {
                "revision": self.revision,
                "changed": self.revision > since,
                "mtime": self._disk_mtime(),
                "annotations": self._list_highlights_in_doc(self.doc),
                "unsaved": self.unsaved,
            }

    def _ensure_fresh_before_save(self) -> None:
        disk_mtime = self._disk_mtime()
        if disk_mtime <= self._file_mtime + 1e-6:
            return
        if self.unsaved:
            disk_annots = self._read_highlights_from_path(self.save_path)
            self._merge_missing_annotations(disk_annots)
            self._file_mtime = disk_mtime
            return
        self._reload_from_disk_file()

    def _backup_existing(self, target: Path) -> None:
        if not target.exists():
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backups_root = backup_dir()
        backup = backups_root / f"{target.name}.{stamp}.bak"
        shutil.copy2(target, backup)
        backups = sorted(backups_root.glob(f"{target.name}.*.bak"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)

    def _persist_now(self) -> str:
        target = self.save_path
        target.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_fresh_before_save()
        self._backup_existing(target)
        tmp = target.with_suffix(target.suffix + ".tmp")
        self.doc.save(str(tmp), incremental=False, garbage=3, deflate=True)
        tmp.replace(target)
        self.unsaved = False
        self._note_mtime()
        self._bump_revision()
        return str(target)

    def _persist(self) -> str:
        if self.autosave:
            return self._persist_now()
        self.unsaved = True
        self._bump_revision()
        return str(self.save_path)

    def _rebuild_citation_index(self) -> None:
        self._citation_entries, self._citation_urls = build_citation_index(self.doc)

    def _enrich_goto_with_citation(self, page, entry: dict[str, Any]) -> None:
        bbox = entry.get("bbox")
        if not bbox:
            return
        nums = cite_numbers_for_link(page, bbox)
        cite = pick_cite_for_click(page, bbox, nums)
        if cite is None:
            return
        entry["cite"] = cite
        url = self._citation_urls.get(cite)
        if url:
            entry["uri"] = url

    def _reload_doc(self, path: Path, *, save_path: Path | None = None) -> None:
        self.doc.close()
        self.doc = self.fitz.open(str(path))
        self.save_path = save_path or path
        self._rebuild_citation_index()
        self._cleanup_empty_highlights()
        self.unsaved = False
        self._note_mtime()
        self._bump_revision()

    def _cleanup_empty_highlights(self) -> None:
        changed = False
        with self.lock:
            for pno in range(self.doc.page_count):
                page = self.doc.load_page(pno)
                for annot in list(page.annots() or []):
                    if annot.type[0] != self.fitz.PDF_ANNOT_HIGHLIGHT:
                        continue
                    if (annot.info.get("content") or "").strip():
                        continue
                    page.delete_annot(annot)
                    changed = True
            if changed:
                if self.autosave:
                    self._persist_now()
                else:
                    self.unsaved = True
                    self._bump_revision()

    def _annot_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["revision"] = self.revision
        return payload

    def document_info(self) -> dict[str, Any]:
        with self.lock:
            scale = self.dpi / 72.0
            page_sizes: list[dict[str, float]] = []
            for pno in range(self.doc.page_count):
                w, h = self._page_size(self.doc.load_page(pno))
                page_sizes.append({"width": w, "height": h})
            return {
                **app_metadata(),
                "source": str(self.source),
                "save_path": str(self.save_path),
                "save_copy": save_copy_enabled(),
                "name": self.source.name,
                "pages": self.doc.page_count,
                "render_scale": scale,
                "page_sizes": page_sizes,
                "reviewer": self.reviewer,
                "reviewers": reviewers_for_source(self.source) if save_copy_enabled() else [self.reviewer],
                "reviews": scan_reviews(self.source) if save_copy_enabled() else [],
                "palette": {k: rgb_to_hex(v) for k, v in PALETTE.items()},
                "autosave": self.autosave,
                "unsaved": self.unsaved,
                "dirty": self.save_path.exists(),
                "file_mtime": self._disk_mtime(),
                "revision": self.revision,
            }

    def page_spans(self, page_index: int) -> list[dict[str, Any]]:
        page = self.doc.load_page(page_index)
        spans: list[dict[str, Any]] = []
        sid = 0
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    spans.append({"id": sid, "text": text, "bbox": list(span["bbox"])})
                    sid += 1
        return spans

    def page_links(self, page_index: int) -> list[dict[str, Any]]:
        page = self.doc.load_page(page_index)
        out: list[dict[str, Any]] = []
        for raw in page.get_links():
            rect = raw.get("from")
            if rect is None:
                continue
            bbox = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
            uri = raw.get("uri")
            if uri:
                out.append({"type": "uri", "bbox": bbox, "uri": str(uri)})
                continue
            dest_page = raw.get("page")
            if dest_page is not None:
                entry: dict[str, Any] = {
                    "type": "goto",
                    "bbox": bbox,
                    "page": int(dest_page),
                }
                to = raw.get("to")
                if to is not None:
                    entry["y"] = float(to.y)
                self._enrich_goto_with_citation(page, entry)
                out.append(entry)
                continue
            kind = int(raw.get("kind") or 0)
            if kind in (self.fitz.LINK_NAMED, self.fitz.LINK_GOTOR):
                try:
                    dest = page.resolve_link(raw)
                except Exception:
                    dest = None
                if dest and dest.get("page") is not None:
                    entry = {
                        "type": "goto",
                        "bbox": bbox,
                        "page": int(dest["page"]),
                    }
                    to = dest.get("to")
                    if to is not None:
                        entry["y"] = float(to.y)
                    self._enrich_goto_with_citation(page, entry)
                    out.append(entry)
        return out

    def page_payload(self, index: int) -> dict[str, Any]:
        with self.lock:
            page = self.doc.load_page(index)
            w, h = self._page_size(page)
            scale = self.dpi / 72.0
            mat = self.fitz.Matrix(scale, scale)
            # Highlights are drawn in the browser overlay; baking annots into the
            # bitmap leaves stale yellow marks after delete/resize until reload.
            pix = page.get_pixmap(matrix=mat, alpha=False, annots=False)
            spans = self.page_spans(index)
            links = self.page_links(index)
            return {
                "index": index,
                "width": w,
                "height": h,
                "scale": scale,
                "image": base64.b64encode(pix.tobytes("png")).decode("ascii"),
                "spans": spans,
                "links": links,
            }

    def _find_annot(self, xref: int):
        for pno in range(self.doc.page_count):
            page = self.doc.load_page(pno)
            for annot in page.annots() or []:
                if annot.xref == xref:
                    return page, annot
        return None, None

    def list_annotations(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._list_highlights_in_doc(self.doc)

    def create_highlight(
        self,
        page_index: int,
        span_ids: list[int],
        color_name: str,
        content: str,
    ) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("comment cannot be empty")
        color = PALETTE.get(color_name, PALETTE["yellow"])
        with self.lock:
            spans_meta = self.page_spans(page_index)
            chosen = [spans_meta[i] for i in span_ids if 0 <= i < len(spans_meta)]
            if not chosen:
                raise ValueError("no text selected")
            page = self.doc.load_page(page_index)
            span_rects = merge_line_rects(chosen)
            for ex in self._list_highlights_in_doc(self.doc):
                if ex["page"] == page_index and _annotation_overlaps_rects(ex["rects"], span_rects):
                    raise ValueError("highlight overlaps an existing highlight")
            quads = [self.fitz.Rect(*rect).quad for rect in span_rects]
            annot = page.add_highlight_annot(quads)
            annot.set_colors(stroke=color)
            annot.set_info(title=self.reviewer, content=content)
            annot.set_opacity(0.45)
            annot.update()
            self._persist()
            payload = self._annot_response(self._annot_dict(page_index, annot, color_name, rects=span_rects))
            payload["save_path"] = str(self.save_path)
            return payload

    def _rects_from_annot(self, annot) -> list[list[float]]:
        quad_points = annot.vertices
        if quad_points:
            rects: list[list[float]] = []
            for i in range(0, len(quad_points), 4):
                xs = [quad_points[i + j][0] for j in range(4)]
                ys = [quad_points[i + j][1] for j in range(4)]
                rects.append([min(xs), min(ys), max(xs), max(ys)])
            return rects
        rect = annot.rect
        if rect.is_empty or rect.is_infinite:
            return []
        return [list(rect)]

    def _annot_dict(
        self,
        page_index: int,
        annot,
        color_name: str,
        *,
        rects: list[list[float]] | None = None,
    ) -> dict[str, Any]:
        info = annot.info
        color = PALETTE.get(color_name, PALETTE["yellow"])
        return {
            "id": annot.xref,
            "page": page_index,
            "rects": rects if rects is not None else self._rects_from_annot(annot),
            "color": color_name,
            "hex": rgb_to_hex(color),
            "content": info.get("content") or "",
            "title": info.get("title") or "",
        }

    def update_annotation(
        self,
        xref: int,
        *,
        content: str | None = None,
        color_name: str | None = None,
        span_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            if span_ids is not None:
                return self._resize_annotation(xref, span_ids)
            page, annot = self._find_annot(xref)
            if annot is None:
                raise KeyError(xref)
            if content is not None:
                info = annot.info
                annot.set_info(title=info.get("title") or self.reviewer, content=content)
            if color_name is not None:
                annot.set_colors(stroke=PALETTE.get(color_name, PALETTE["yellow"]))
            annot.update()
            pno = page.number
            name = color_name
            if name is None:
                colors = annot.colors or {}
                stroke = colors.get("stroke") or PALETTE["yellow"]
                if isinstance(stroke, (list, tuple)) and len(stroke) >= 3:
                    name = nearest_palette_name((float(stroke[0]), float(stroke[1]), float(stroke[2])))
                else:
                    name = "yellow"
            self._persist()
            return self._annot_response(self._annot_dict(pno, annot, name))

    def _resize_annotation(self, xref: int, span_ids: list[int]) -> dict[str, Any]:
        page, annot = self._find_annot(xref)
        if annot is None:
            raise KeyError(xref)
        pno = page.number
        spans_meta = self.page_spans(pno)
        chosen = [spans_meta[i] for i in span_ids if 0 <= i < len(spans_meta)]
        if not chosen:
            raise ValueError("no text selected")
        span_rects = merge_line_rects(chosen)
        for ex in self._list_highlights_in_doc(self.doc):
            if ex["page"] == pno and int(ex["id"]) != xref:
                if _annotation_overlaps_rects(ex["rects"], span_rects):
                    raise ValueError("highlight overlaps an existing highlight")
        info = annot.info
        colors = annot.colors or {}
        stroke = colors.get("stroke") or colors.get("fill") or PALETTE["yellow"]
        if isinstance(stroke, (list, tuple)) and len(stroke) >= 3:
            rgb = (float(stroke[0]), float(stroke[1]), float(stroke[2]))
            color_name = nearest_palette_name(rgb)
        else:
            rgb = PALETTE["yellow"]
            color_name = "yellow"
        title = info.get("title") or self.reviewer
        content = info.get("content") or ""
        page.delete_annot(annot)
        quads = [self.fitz.Rect(*rect).quad for rect in span_rects]
        new_annot = page.add_highlight_annot(quads)
        new_annot.set_colors(stroke=rgb)
        new_annot.set_info(title=title, content=content)
        new_annot.set_opacity(0.45)
        new_annot.update()
        fp = annot_fingerprint({"page": pno, "rects": span_rects, "content": content})
        self._persist()
        for row in self._list_highlights_in_doc(self.doc):
            if annot_fingerprint(row) == fp:
                result = dict(row)
                result["replaced_id"] = xref
                return self._annot_response(result)
        raise ValueError("could not save resized highlight")

    def delete_annotation(self, xref: int) -> None:
        with self.lock:
            page, annot = self._find_annot(xref)
            if annot is None:
                raise KeyError(xref)
            page.delete_annot(annot)
            self._persist()
            return self.revision

    def delete_annotations(self, xrefs: list[int]) -> dict[str, int]:
        with self.lock:
            deleted = 0
            for xref in xrefs:
                page, annot = self._find_annot(int(xref))
                if annot is None:
                    continue
                page.delete_annot(annot)
                deleted += 1
            if deleted:
                self._persist()
            return {"deleted": deleted, "revision": self.revision}

    def _restore_highlight_locked(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        page_index = int(snapshot["page"])
        color_name = str(snapshot.get("color") or "yellow")
        content = str(snapshot.get("content") or "")
        if not content.strip():
            raise ValueError("comment cannot be empty")
        title = str(snapshot.get("title") or self.reviewer)
        rects = [list(r) for r in (snapshot.get("rects") or [])]
        if not rects:
            raise ValueError("no highlight geometry in snapshot")
        color = PALETTE.get(color_name, PALETTE["yellow"])
        page = self.doc.load_page(page_index)
        for ex in self._list_highlights_in_doc(self.doc):
            if ex["page"] == page_index and _annotation_overlaps_rects(ex["rects"], rects):
                raise ValueError("highlight overlaps an existing highlight")
        quads = [self.fitz.Rect(*rect).quad for rect in rects]
        annot = page.add_highlight_annot(quads)
        annot.set_colors(stroke=color)
        annot.set_info(title=title, content=content)
        annot.set_opacity(0.45)
        annot.update()
        return self._annot_dict(page_index, annot, color_name, rects=rects)

    def restore_highlights(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self.lock:
            if not snapshots:
                raise ValueError("no snapshots to restore")
            restored: list[dict[str, Any]] = []
            for snapshot in snapshots:
                restored.append(self._restore_highlight_locked(snapshot))
            self._persist()
            return restored, self.revision

    def set_reviewer(self, reviewer: str) -> None:
        reviewer = sanitize_reviewer(reviewer)
        with self.lock:
            if self.unsaved and not self.autosave:
                self._persist_now()
            self.reviewer = reviewer
            if save_copy_enabled():
                latest = latest_review_for(self.source, reviewer)
                if latest:
                    self._reload_doc(latest)
                else:
                    self._reload_doc(self.source, save_path=annotated_path(self.source, reviewer))

    def set_autosave(self, enabled: bool) -> None:
        with self.lock:
            self.autosave = bool(enabled)
            if self.autosave and self.unsaved:
                self._persist_now()

    def save(self) -> str:
        with self.lock:
            return self._persist_now()


class ServerSession:
    """Optional PDF session with in-app open/switch support."""

    def __init__(self, reviewer: str, source: Path | None = None) -> None:
        self._reviewer = sanitize_reviewer(reviewer)
        self._session: PdfSession | None = None
        self._error: BaseException | None = None
        self._ready = threading.Event()
        self._lock = threading.RLock()
        if source is None:
            self._ready.set()
        else:
            threading.Thread(
                target=self._load,
                args=(source,),
                name="peerfold-load",
                daemon=True,
            ).start()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    @property
    def has_document(self) -> bool:
        return self._session is not None

    @property
    def loading_error(self) -> str | None:
        return None if self._error is None else str(self._error)

    def _empty_document_info(self) -> dict[str, Any]:
        return {
            **app_metadata(),
            "open": False,
            "source": "",
            "save_path": "",
            "save_copy": save_copy_enabled(),
            "name": "",
            "pages": 0,
            "render_scale": 1.0,
            "page_sizes": [],
            "reviewer": self._reviewer,
            "reviewers": [],
            "reviews": [],
            "palette": {k: rgb_to_hex(v) for k, v in PALETTE.items()},
            "autosave": True,
            "unsaved": False,
            "dirty": False,
            "file_mtime": 0.0,
            "revision": 0,
        }

    def document_info(self) -> dict[str, Any]:
        with self._lock:
            if self._session is None:
                return self._empty_document_info()
            return {"open": True, **self._session.document_info()}

    def _load(self, source: Path) -> None:
        try:
            source = source.resolve()
            if not source.is_file():
                raise FileNotFoundError(f"PDF not found: {source}")
            fitz = import_fitz()
            session = PdfSession(source, self._reviewer, fitz, defer_maintenance=True)
            with self._lock:
                if self._session is not None:
                    self._session.close()
                self._session = session
                self._error = None
        except BaseException as exc:
            with self._lock:
                self._error = exc
        finally:
            self._ready.set()

    def open_pdf(self, source: Path) -> dict[str, Any]:
        with self._lock:
            if self._session is not None:
                self._session.close()
                self._session = None
            self._error = None
            self._ready.clear()
        self._load(source)
        self._ready.wait()
        if self._error is not None:
            raise self._error
        from peerfold.recent_files import add

        add(source)
        return self.document_info()

    def set_reviewer(self, reviewer: str) -> None:
        reviewer = sanitize_reviewer(reviewer)
        with self._lock:
            self._reviewer = reviewer
            if self._session is not None:
                self._session.set_reviewer(reviewer)

    def set_autosave(self, enabled: bool) -> None:
        with self._lock:
            if self._session is not None:
                self._session.set_autosave(enabled)

    def save(self) -> str:
        with self._lock:
            if self._session is None:
                raise RuntimeError("No PDF open")
            return self._session.save()

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.close()
                self._session = None

    def _require(self) -> PdfSession:
        self._ready.wait()
        if self._error is not None:
            raise self._error
        if self._session is None:
            raise RuntimeError("No PDF open")
        return self._session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._require(), name)


def parse_multipart_file_field(
    body: bytes,
    *,
    content_type: str,
    field_name: str = "file",
) -> tuple[str, bytes]:
    """Extract a named file field from multipart/form-data (stdlib-only; no cgi)."""
    match = re.search(
        r"boundary=([^;\s]+|'[^']+'|\"[^\"]+\")",
        content_type,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("missing multipart boundary")
    boundary = match.group(1).strip().strip("'\"")
    marker = b"--" + boundary.encode("ascii", "surrogateescape")

    for chunk in body.split(marker):
        if not chunk or chunk in (b"--", b"--\r\n"):
            continue
        part = chunk[2:] if chunk.startswith(b"\r\n") else chunk
        if part.endswith(b"\r\n"):
            part = part[:-2]
        sep = part.find(b"\r\n\r\n")
        if sep < 0:
            continue
        headers = part[:sep].decode("latin-1", "replace")
        payload = part[sep + 4 :]
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]

        disposition = next(
            (
                line
                for line in headers.split("\r\n")
                if line.lower().startswith("content-disposition:")
            ),
            "",
        )
        if not re.search(
            rf'name="{re.escape(field_name)}"|name={re.escape(field_name)}(?:;|$)',
            disposition,
        ):
            continue

        filename = "upload.pdf"
        fn_match = re.search(
            r'filename\*?=(?:UTF-8\'\')?"?([^";\r\n]+)"?',
            disposition,
            re.IGNORECASE,
        )
        if fn_match:
            filename = Path(fn_match.group(1).strip()).name or filename
        if not payload:
            raise ValueError("empty PDF upload")
        return filename, payload

    raise ValueError("missing PDF file")


class ReviewHandler(BaseHTTPRequestHandler):
    session: ServerSession
    fitz_mod: Any

    def log_message(self, fmt: str, *args) -> None:
        pass

    def _guard_api(self) -> bool:
        session = self.session
        if getattr(session, "ready", True):
            if session.loading_error:
                self._json(500, {"error": session.loading_error})
                return True
            return False
        err = getattr(session, "loading_error", None)
        if err:
            self._json(500, {"error": err})
        else:
            self._json(503, {"status": "loading"})
        return True

    def _guard_document(self) -> bool:
        if self._guard_api():
            return True
        if getattr(self.session, "has_document", True):
            return False
        self._json(503, {"status": "no_document"})
        return True

    def _resolve_open_pdf(self) -> Path:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self._read_upload_pdf()
        data = self._read_json()
        raw = data.get("path")
        if not raw:
            raise ValueError('Open a PDF with a file upload or JSON {"path": "/full/path.pdf"}')
        path = Path(str(raw)).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"PDF not found: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("not a PDF file")
        return path

    def _read_upload_pdf(self) -> Path:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("expected multipart PDF upload")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("empty PDF upload")
        body = self.rfile.read(length)
        raw_name, data = parse_multipart_file_field(body, content_type=content_type)
        upload_dir = data_dir() / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        if not raw_name.lower().endswith(".pdf"):
            raw_name = f"{raw_name}.pdf"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = upload_dir / f"{stamp}-{raw_name}"
        dest.write_bytes(data)
        return dest

    def handle_error(self, request, client_address) -> None:
        exc_type, _, _ = sys.exc_info()
        if exc_type in (BrokenPipeError, ConnectionResetError):
            return
        super().handle_error(request, client_address)

    def _safe_write(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._safe_write(body)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._safe_write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        static = static_root()
        if path in ("", "/"):
            return self._file(static / "index.html")
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            target = (static / rel).resolve()
            if not str(target).startswith(str(static.resolve())):
                self.send_error(403)
                return
            return self._file(target)
        if path == "/api/update-check":
            return self._json(200, update_check_payload())
        if path == "/api/document":
            if self._guard_api():
                return
            return self._json(200, self.session.document_info())
        if path == "/api/sync":
            if self._guard_document():
                return
            qs = parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0] or 0)
            payload = self.session.sync_from_disk(since=since)
            return self._json(200, payload)
        if path == "/api/annotations":
            if self._guard_document():
                return
            return self._json(200, self.session.list_annotations())
        if path.startswith("/api/page/"):
            if self._guard_document():
                return
            try:
                index = int(path.split("/")[-1])
            except ValueError:
                self.send_error(400)
                return
            if index < 0 or index >= self.session.doc.page_count:
                self.send_error(404)
                return
            return self._json(200, self.session.page_payload(index))

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/open":
            if self._guard_api():
                return
            try:
                pdf_path = self._resolve_open_pdf()
                doc = self.session.open_pdf(pdf_path)
                return self._json(200, doc)
            except (ValueError, FileNotFoundError) as exc:
                return self._json(400, {"error": str(exc)})
            except RuntimeError as exc:
                return self._json(500, {"error": str(exc)})
        if path.startswith("/api/") and self._guard_document():
            return
        try:
            if path == "/api/annotations":
                data = self._read_json()
                page_index = int(data["page"])
                span_ids = list(data.get("span_ids") or [])
                color = str(data.get("color") or "yellow")
                content = str(data.get("content") or "")
                created = self.session.create_highlight(page_index, span_ids, color, content)
                return self._json(201, created)
            if path == "/api/annotations/batch-delete":
                data = self._read_json()
                ids = [int(x) for x in (data.get("ids") or [])]
                if not ids:
                    raise ValueError("no annotation ids")
                result = self.session.delete_annotations(ids)
                return self._json(200, {"ok": True, **result})
            if path == "/api/annotations/batch-restore":
                data = self._read_json()
                items = list(data.get("items") or [])
                if not items:
                    raise ValueError("no snapshots to restore")
                restored, revision = self.session.restore_highlights(items)
                return self._json(201, {"items": restored, "revision": revision})
            if path == "/api/save":
                saved = self.session.save()
                return self._json(200, {"path": saved, **self.session.document_info()})
            if path == "/api/reviewer":
                data = self._read_json()
                self.session.set_reviewer(str(data["reviewer"]))
                return self._json(200, self.session.document_info())
            if path == "/api/settings":
                data = self._read_json()
                if "autosave" in data:
                    self.session.set_autosave(bool(data["autosave"]))
                return self._json(200, self.session.document_info())
            self.send_error(404)
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/annotations/"):
            self.send_error(404)
            return
        if self._guard_document():
            return
        try:
            xref = int(path.rsplit("/", 1)[-1])
            data = self._read_json()
            span_ids = data.get("span_ids")
            updated = self.session.update_annotation(
                xref,
                content=data.get("content"),
                color_name=data.get("color"),
                span_ids=list(span_ids) if span_ids is not None else None,
            )
            self._json(200, updated)
        except KeyError as exc:
            self._json(404, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/annotations/"):
            self.send_error(404)
            return
        if self._guard_document():
            return
        try:
            xref = int(path.rsplit("/", 1)[-1])
            revision = self.session.delete_annotation(xref)
            self._json(200, {"ok": True, "revision": revision})
        except KeyError as exc:
            self._json(404, {"error": str(exc)})


def pick_port(preferred: int) -> int:
    import socket

    if preferred > 0:
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


UPDATE_REPO = "vincenzoml/PeerFold"
UPDATE_URL = f"https://github.com/{UPDATE_REPO}/releases/latest"


def app_version() -> str:
    from peerfold import __version__

    return __version__


def app_metadata() -> dict[str, str]:
    return {"app_version": app_version()}


def parse_version_parts(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.lstrip("v").split("."):
        num = ""
        for ch in piece:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def version_newer(latest: str, current: str) -> bool:
    return parse_version_parts(latest) > parse_version_parts(current)


def _github_ssl_context():
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_latest_release_version() -> str | None:
    import json
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    try:
        req = Request(
            f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "PeerFold",
            },
        )
        with urlopen(req, timeout=8, context=_github_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name", "")).lstrip("v")
        return tag or None
    except (URLError, OSError, TimeoutError, ValueError, KeyError):
        return None


def update_check_payload() -> dict[str, Any]:
    current = app_version()
    latest = fetch_latest_release_version()
    available = bool(latest and version_newer(latest, current))
    return {
        "current": current,
        "latest": latest,
        "update_available": available,
        "url": UPDATE_URL,
        "check_ok": latest is not None,
    }


def print_review_target(session: ServerSession) -> None:
    session._ready.wait()
    if session.loading_error or not session.has_document:
        return
    info = session.document_info()
    save = info.get("save_path") or ""
    source = info.get("source") or ""
    if not save:
        return
    if not info.get("save_copy") or Path(save).resolve() == Path(source).resolve():
        print(f"Editing: {save}")
        return
    print(f"Review copy: {save}")
    if source and Path(save).resolve().parent == Path(source).resolve().parent:
        print(f"  (beside {Path(source).name})")


def run_server(
    pdf: Path | None,
    *,
    reviewer: str | None = None,
    port: int = 0,
    ui: str = "webview",
) -> None:
    """Start PeerFold. ui: webview (default), web, or none."""
    from peerfold.ui import (
        WebviewUnavailableError,
        headless_environment,
        launch_web_ui,
        open_webview_strict,
        webview_unavailable_help,
    )

    if pdf is not None:
        pdf = pdf.resolve()
        if not pdf.is_file():
            raise SystemExit(f"PDF not found: {pdf}")

    reviewer = sanitize_reviewer(reviewer or default_reviewer())
    static = static_root()
    if not (static / "index.html").is_file():
        raise SystemExit(
            "PeerFold UI files are missing from this install "
            f"(expected {static / 'index.html'}). "
            "Run: python3 scripts/peerfold.py --update"
        )
    session = ServerSession(reviewer, pdf)
    chosen = pick_port(port)
    url = f"http://127.0.0.1:{chosen}/"
    title = f"PeerFold · {pdf.name}" if pdf else "PeerFold"

    handler = type("BoundReviewHandler", (ReviewHandler,), {})
    handler.session = session
    handler.fitz_mod = None
    server = ThreadingHTTPServer(("127.0.0.1", chosen), handler)

    if pdf:
        print(f"PeerFold · {pdf.name}")
    else:
        print("PeerFold")
    print(f"Open: {url}")
    print_review_target(session)

    if ui == "webview" and headless_environment():
        print(webview_unavailable_help(url=url), file=sys.stderr)
        raise SystemExit(1)

    if ui == "none":
        session._ready.wait()
        if session.loading_error:
            raise SystemExit(session.loading_error)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping…")
        finally:
            server.server_close()
            session.close()
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    if ui == "webview":
        try:
            open_webview_strict(url, title)
        except WebviewUnavailableError as exc:
            print(webview_unavailable_help(url=url, detail=str(exc)), file=sys.stderr)
            raise SystemExit(1) from exc
        finally:
            server.shutdown()
            server.server_close()
            session.close()
        return

    launch_web_ui(url)
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.shutdown()
        server.server_close()
        session.close()
