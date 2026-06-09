# PeerFold

Review PDFs in your browser. Highlights are written as standard PDF `/Highlight` annotations — open the saved copy in Acrobat, Preview, or any PDF reader.

```bash
pipx install peerfold-review
peerfold manuscript.pdf --reviewer VC
```

Saved reviews: `manuscript_VC-2026-06-09.pdf` next to the original.

## Install

| Method | Command |
|--------|---------|
| **pipx** (recommended) | `pipx install peerfold-review` |
| pip | `pip install peerfold-review` |
| Standalone binary | [GitHub Releases](https://github.com/vincenzoml/PeerFold/releases) |

## Usage

```bash
peerfold paper.pdf                  # open browser UI
peerfold paper.pdf -r VC            # reviewer short name (filename + metadata)
peerfold paper.pdf --port 8765      # fixed port
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
