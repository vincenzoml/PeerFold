# PeerFold

Review PDFs in a native window — embedded WebKit/WebView2 via [pywebview](https://pywebview.flowrl.com/), no browser tabs or URL bar. Use `--browser` for the system browser instead. Highlights are written as standard PDF `/Highlight` annotations — open the saved copy in Acrobat, Preview, or any PDF reader.

Saved reviews: `manuscript_VC-2026-06-09.pdf` next to the original.

## Install

**macOS & Linux**

```bash
curl -fsSL https://vincenzoml.github.io/PeerFold/install.sh | bash
```

Installs the latest release: macOS → `Applications/PeerFold.app`; Linux → `~/.local/bin/peerfold`.

**Windows** (PowerShell)

```powershell
irm https://vincenzoml.github.io/PeerFold/install.ps1 | iex
```

Installs to `%LOCALAPPDATA%\Programs\PeerFold` and adds `peerfold` to your user PATH.

**Python 3.10+** (no pipx required)

```bash
python3 -m pip install --user peerfold-review
peerfold manuscript.pdf --reviewer RB
```

Ensure `~/.local/bin` is on your PATH, or use a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install peerfold-review
peerfold manuscript.pdf --reviewer RB
```

With [pipx](https://pipx.pypa.io/) (isolated CLI on PATH):

```bash
pipx install peerfold-review
peerfold manuscript.pdf --reviewer RB
```

### Sharing with co-authors (same paper repo)

Do **not** submodule PeerFold — it is a published package. Pick one:

1. **One-liner** — each co-author runs `python3 -m pip install --user peerfold-review` once.
2. **Repo launcher** (recommended for co-authors) — from your paper repo root:

```bash
mkdir -p scripts && curl -fsSL https://vincenzoml.github.io/PeerFold/peerfold.py -o scripts/peerfold.py
python3 scripts/peerfold.py review-builds/paper.pdf --reviewer AB
```

Add `.venv-peerfold/` to `.gitignore`. Re-running upgrades PeerFold from PyPI.
3. **Standalone app** — `curl -fsSL …/install.sh | bash` (macOS/Linux) or the Windows PowerShell installer; no Python needed.

Manual downloads: [GitHub Releases](https://github.com/vincenzoml/PeerFold/releases/latest).

Install scripts: [install.sh](https://vincenzoml.github.io/PeerFold/install.sh) · [install.ps1](https://vincenzoml.github.io/PeerFold/install.ps1)

## Usage

```bash
peerfold paper.pdf                  # open browser UI
peerfold paper.pdf -r VC            # reviewer short name (filename + metadata)
peerfold paper.pdf --port 8765      # fixed port
peerfold paper.pdf --browser        # system browser instead of native window
peerfold paper.pdf --no-browser     # server only
```

Environment: `PEERFOLD_REVIEWER` sets the default reviewer name.

## Features

- Span-accurate text highlights with comment threads
- Citation links open DOIs/URLs directly
- Multi-tab sync, autosave, reviewer switching
- Adobe-compatible annotation format

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
peerfold sample.pdf
pytest
```

## License

MIT — see [LICENSE](LICENSE). Uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL).
