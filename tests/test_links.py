from pathlib import Path

from peerfold.core import app_metadata, print_launch_banner
from peerfold.links import REPOSITORY, WEBSITE, about_body, launch_banner_lines


def test_launch_banner_lines_include_links():
    lines = launch_banner_lines(version="1.0.0", pdf=Path("paper.pdf"))
    text = "\n".join(lines)
    assert "PeerFold 1.0.0 · paper.pdf" in text
    assert WEBSITE in text
    assert REPOSITORY in text


def test_app_metadata_includes_links():
    meta = app_metadata()
    assert meta["website"] == WEBSITE
    assert meta["repository"] == REPOSITORY


def test_about_body_includes_links():
    body = about_body(version="1.0.0")
    assert WEBSITE in body
    assert REPOSITORY in body


def test_print_launch_banner(capsys):
    print_launch_banner(local_url="http://127.0.0.1:8765/")
    out = capsys.readouterr().out
    assert WEBSITE in out
    assert REPOSITORY in out
    assert "http://127.0.0.1:8765/" in out
