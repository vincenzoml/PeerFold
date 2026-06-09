# PeerFold

Review PDFs in a native window (or your browser with `--browser`). Highlights are written as standard PDF `/Highlight` annotations — open the saved copy in Acrobat, Preview, or any PDF reader.

```bash
pipx install peerfold-review
peerfold manuscript.pdf --reviewer VC
```

Saved reviews: `manuscript_VC-2026-06-09.pdf` next to the original.

## Install

| Platform | Method |
|----------|--------|
| Any (Python 3.10+) | `pipx install peerfold-review` |
| Any (venv) | `pip install peerfold-review` |
| macOS | [peerfold-macos.dmg](https://github.com/vincenzoml/PeerFold/releases/latest) or self-extracting `peerfold-macos` |
| Linux | self-extracting [peerfold-linux](https://github.com/vincenzoml/PeerFold/releases/latest) |
| Windows | self-extracting [peerfold-win.exe](https://github.com/vincenzoml/PeerFold/releases/latest) |

`chmod +x peerfold-macos peerfold-linux` then run with your PDF path.

## Usage

```bash
peerfold paper.pdf                  # open browser UI
peerfold paper.pdf -r VC            # reviewer short name (filename + metadata)
peerfold paper.pdf --port 8765      # fixed port
peerfold paper.pdf --browser          # system browser instead of native window
peerfold paper.pdf --no-browser       # server only
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
