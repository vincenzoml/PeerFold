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

**Python 3.10+**

```bash
pipx install peerfold-review
peerfold manuscript.pdf --reviewer RB
```

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
