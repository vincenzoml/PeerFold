# PeerFold

**Website:** [vincenzoml.github.io/PeerFold](https://vincenzoml.github.io/PeerFold/) · **Source:** [github.com/vincenzoml/PeerFold](https://github.com/vincenzoml/PeerFold)

Review PDFs in a native window. Click, type, done.

Saved reviews: `manuscript_VC-2026-06-09.pdf` next to the original.

## Install

**macOS & Linux**

```bash
curl -fsSL https://vincenzoml.github.io/PeerFold/install.sh | bash
```

**Windows** (PowerShell)

```powershell
irm https://vincenzoml.github.io/PeerFold/install.ps1 | iex
```

**Python 3.10+**

```bash
python3 -m pip install --user peerfold-review
peerfold manuscript.pdf --reviewer RB
```

Over SSH: `peerfold paper.pdf --web`

## Shared folder or git repo

One launcher file — pinned PyPI version, same build for every co-author. Do **not** submodule PeerFold.

**One-liner** (from project root):

```bash
curl -fsSLO https://vincenzoml.github.io/PeerFold/peerfold.py && chmod +x peerfold.py
./peerfold.py your-paper.pdf --reviewer AB
```

**Or download** [peerfold.py](https://vincenzoml.github.io/PeerFold/peerfold.py) into your project root. Packages are cached in `~/.local/share/peerfold/cache` (uv; override with `PEERFOLD_CACHE` / `PEERFOLD_DATA`).

Upgrade when needed:

```bash
./peerfold.py --update   # then commit peerfold.py
```

Site: [vincenzoml.github.io/PeerFold](https://vincenzoml.github.io/PeerFold/)

## Usage

```bash
peerfold paper.pdf                  # native window (default)
peerfold paper.pdf -r VC            # reviewer short name
peerfold paper.pdf --web            # system browser (SSH)
peerfold paper.pdf --no-browser     # server only
```

Environment: `PEERFOLD_REVIEWER` sets the default reviewer name. Set `PEERFOLD_SAVE_COPY=1` to write sidecar files (`paper_VC-2026-06-09.pdf`) instead of editing in place.

## Roadmap

Planned features (discussion and design in GitHub issues):

| Feature | Issue |
|---------|-------|
| Merge comments from different PDFs into one view | [#1](https://github.com/vincenzoml/PeerFold/issues/1) |
| PDF diff view for revised manuscripts | [#2](https://github.com/vincenzoml/PeerFold/issues/2) |
| GitHub integration for paper repos and review versioning | [#3](https://github.com/vincenzoml/PeerFold/issues/3) |
| Export comments to human-readable text (page, section, quote) | [#4](https://github.com/vincenzoml/PeerFold/issues/4) |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
peerfold sample.pdf
pytest
```

## License

MIT — see [LICENSE](LICENSE). Uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL).

Brought to you by [vincenzoml@gmail.com](mailto:vincenzoml@gmail.com) · [vincenzoml.github.io](https://vincenzoml.github.io/)
