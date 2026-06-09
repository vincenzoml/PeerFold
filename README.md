# PeerFold

Review PDFs in a native window. Highlights are standard PDF annotations — open the saved copy in any reader.

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
mkdir -p scripts && curl -fsSL https://vincenzoml.github.io/PeerFold/peerfold.py -o scripts/peerfold.py && echo '.venv-peerfold/' >> .gitignore
python3 scripts/peerfold.py manuscript.pdf --reviewer AB
```

**Or download** [peerfold.py](https://vincenzoml.github.io/PeerFold/peerfold.py) → `scripts/peerfold.py`, add `.venv-peerfold/` to `.gitignore`.

Upgrade when needed:

```bash
python3 scripts/peerfold.py --update   # then commit scripts/peerfold.py
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

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
peerfold sample.pdf
pytest
```

## License

MIT — see [LICENSE](LICENSE). Uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL).
