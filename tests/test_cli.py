import sys
from unittest.mock import AsyncMock, patch

import pytest

from newswatch.cli import cli


def test_cli_no_args(monkeypatch, capsys):
    # Simulate no command-line arguments
    monkeypatch.setattr(sys, "argv", ["cli.py"])

    # Mock the main scraping function to avoid real network calls
    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        capsys.readouterr()

        # Verify that main was called with expected arguments
        mock_main.assert_called_once()
        args = mock_main.call_args[0][0]
        assert args.method == "search"
        assert args.keywords is None
        assert args.scrapers == "auto"
        assert args.output_format == "csv"


def test_cli_with_invalid_args(monkeypatch, capsys):
    # Simulate invalid command-line arguments
    monkeypatch.setattr(sys, "argv", ["cli.py", "--unknown_arg"])

    # Mock the main function (shouldn't be called due to arg parsing error)
    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        with pytest.raises(SystemExit):
            cli()
        captured = capsys.readouterr()
        assert "unrecognized arguments" in captured.err.lower()
        # Main should not be called due to argument parsing error
        mock_main.assert_not_called()


def test_cli_help(monkeypatch, capsys):
    # Simulate '--help' argument
    monkeypatch.setattr(sys, "argv", ["cli.py", "--help"])

    # Mock the main function (shouldn't be called due to help exit)
    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        with pytest.raises(SystemExit):
            cli()
        captured = capsys.readouterr()
        assert "News Watch - Scrape news articles" in captured.out
        # Main should not be called when showing help
        mock_main.assert_not_called()


def test_cli_list_scrapers(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "--list_scrapers"])

    # Mock the main function (shouldn't be called when listing scrapers)
    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        captured = capsys.readouterr()
        assert "Supported search scrapers:" in captured.out
        # Main should not be called when listing scrapers
        mock_main.assert_not_called()


def test_cli_latest_method(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "--method", "latest"])

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        capsys.readouterr()

        mock_main.assert_called_once()
        args = mock_main.call_args[0][0]
        assert args.method == "latest"


def test_cli_list_latest_scrapers(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["cli.py", "--method", "latest", "--list_scrapers"]
    )

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        captured = capsys.readouterr()
        assert "Supported latest scrapers:" in captured.out
        mock_main.assert_not_called()


def test_cli_latest_with_limit_and_max_pages(monkeypatch, capsys):
    """Test that --limit and --max-pages are parsed in latest mode."""
    monkeypatch.setattr(
        sys, "argv", ["cli.py", "--method", "latest", "--limit", "5", "--max-pages", "2"]
    )

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        capsys.readouterr()

        mock_main.assert_called_once()
        args = mock_main.call_args[0][0]
        assert args.method == "latest"
        assert args.limit == 5
        assert args.max_pages == 2


def test_cli_scraper_timeout_arg(monkeypatch, capsys):
    """Test that --scraper-timeout is parsed."""
    monkeypatch.setattr(sys, "argv", ["cli.py", "--scraper-timeout", "30"])

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        capsys.readouterr()

        mock_main.assert_called_once()
        args = mock_main.call_args[0][0]
        assert args.scraper_timeout == 30


def test_cli_progress_flag(monkeypatch, capsys):
    """Test that --progress flag is parsed."""
    monkeypatch.setattr(sys, "argv", ["cli.py", "--progress"])

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main:
        cli()
        capsys.readouterr()

        mock_main.assert_called_once()
        args = mock_main.call_args[0][0]
        assert args.progress is True
