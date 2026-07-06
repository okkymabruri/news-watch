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

def test_cli_health_report_flag(monkeypatch, capsys):
    """Test that --health-report flag runs health report instead of main."""
    monkeypatch.setattr(sys, "argv", ["cli.py", "--health-report"])

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main, \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary") as mock_summary:
        mock_health.return_value = [{"slug": "test", "status": "ok"}]
        cli()

        mock_main.assert_not_called()
        mock_health.assert_called_once()
        mock_summary.assert_called_once()

def test_cli_health_report_with_output(monkeypatch, capsys, tmp_path):
    """Test --health-report with --output_path and --method."""
    outfile = str(tmp_path / "health.json")
    monkeypatch.setattr(sys, "argv", [
        "cli.py", "--health-report", "--method", "latest",
        "--scrapers", "kompas", "--output_path", outfile,
        "--scraper-timeout", "20", "--max-pages", "1",
    ])

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main, \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary") as mock_summary, \
         patch("newswatch.cli.health_report_to_file") as mock_to_file:
        mock_health.return_value = [{"slug": "kompas", "status": "ok"}]
        cli()

        mock_main.assert_not_called()
        mock_health.assert_called_once_with(
            method="latest", scrapers="kompas",
            scraper_timeout=20, max_pages=1, limit=1,
        )
        mock_to_file.assert_called_once_with(
            mock_health.return_value, outfile, "csv",
        )
        mock_summary.assert_called_once()



def test_cli_health_report_history_flag(monkeypatch, capsys, tmp_path):
    """Test --health-history wires append_health_history with the flag path."""
    history = str(tmp_path / "subdir" / "health.jsonl")
    monkeypatch.setattr(sys, "argv", [
        "cli.py", "--health-report", "--health-history", history,
    ])
    monkeypatch.delenv("NEWSWATCH_HEALTH_HISTORY", raising=False)

    with patch("newswatch.cli.run_main", new_callable=AsyncMock) as mock_main, \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary"), \
         patch("newswatch.cli.append_health_history") as mock_append:
        mock_health.return_value = [
            {"slug": "kompas", "status": "ok", "article_count": 2},
            {"slug": "tempo", "status": "ok", "article_count": 1},
        ]
        mock_append.return_value = 2
        cli()

        mock_main.assert_not_called()
        mock_append.assert_called_once()
        args, kwargs = mock_append.call_args
        assert args[0] == mock_health.return_value
        assert args[1] == history
        captured = capsys.readouterr()
        assert "Appended 2 health record(s)" in captured.out
        assert history in captured.out


def test_cli_health_report_history_from_env(monkeypatch, capsys, tmp_path):
    """Test NEWSWATCH_HEALTH_HISTORY env wires append_health_history when flag absent."""
    history = str(tmp_path / "env_health.jsonl")
    monkeypatch.setattr(sys, "argv", ["cli.py", "--health-report"])
    monkeypatch.setenv("NEWSWATCH_HEALTH_HISTORY", history)

    with patch("newswatch.cli.run_main", new_callable=AsyncMock), \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary"), \
         patch("newswatch.cli.append_health_history") as mock_append:
        mock_health.return_value = [{"slug": "kompas", "status": "ok"}]
        mock_append.return_value = 1
        cli()

        mock_append.assert_called_once()
        assert mock_append.call_args[0][1] == history
        captured = capsys.readouterr()
        assert "Appended 1 health record(s)" in captured.out


def test_cli_health_report_no_history_skips_append(monkeypatch, capsys, tmp_path):
    """Test --health-report without --health-history or env does NOT call append."""
    monkeypatch.setattr(sys, "argv", ["cli.py", "--health-report"])
    monkeypatch.delenv("NEWSWATCH_HEALTH_HISTORY", raising=False)

    with patch("newswatch.cli.run_main", new_callable=AsyncMock), \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary"), \
         patch("newswatch.cli.append_health_history") as mock_append:
        mock_health.return_value = [{"slug": "kompas", "status": "ok"}]
        cli()
        mock_append.assert_not_called()
        captured = capsys.readouterr()
        assert "Appended" not in captured.out


def test_cli_health_report_flag_overrides_env(monkeypatch, capsys, tmp_path):
    """Test --health-history flag wins over NEWSWATCH_HEALTH_HISTORY env."""
    flag_path = str(tmp_path / "flag_health.jsonl")
    env_path = str(tmp_path / "env_health.jsonl")
    monkeypatch.setattr(sys, "argv", [
        "cli.py", "--health-report", "--health-history", flag_path,
    ])
    monkeypatch.setenv("NEWSWATCH_HEALTH_HISTORY", env_path)

    with patch("newswatch.cli.run_main", new_callable=AsyncMock), \
         patch("newswatch.cli.health_report") as mock_health, \
         patch("newswatch.cli._print_health_summary"), \
         patch("newswatch.cli.append_health_history") as mock_append:
        mock_health.return_value = [{"slug": "kompas", "status": "ok"}]
        mock_append.return_value = 1
        cli()
        assert mock_append.call_args[0][1] == flag_path