import sys

import pytest

from newswatch.cli import cli


def test_cli_no_args(monkeypatch, capsys):
    # Simulate no command-line arguments
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    cli()
    captured = capsys.readouterr()
    # Check that scraping runs with default arguments
    assert "data written to" in captured.out.lower()


def test_cli_with_invalid_args(monkeypatch, capsys):
    # Simulate invalid command-line arguments
    monkeypatch.setattr(sys, "argv", ["cli.py", "--unknown_arg"])
    with pytest.raises(SystemExit):
        cli()
    captured = capsys.readouterr()
    assert "unrecognized arguments" in captured.err.lower()


def test_cli_help(monkeypatch, capsys):
    # Simulate '--help' argument
    monkeypatch.setattr(sys, "argv", ["cli.py", "--help"])
    with pytest.raises(SystemExit) as e:
        cli()
    captured = capsys.readouterr()
    assert "News Watch - Scrape news articles" in captured.out


def test_cli_list_scrapers(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "--list_scrapers"])
    cli()
    captured = capsys.readouterr()
    assert "Supported scrapers:" in captured.out
