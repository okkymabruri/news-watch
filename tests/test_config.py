"""Tests for newswatch.config env helpers."""

import pytest

from newswatch import config


PROXY_KEYS = (
    "NEWSWATCH_PROXY",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    """Ensure no proxy env leaks between tests."""
    for key in PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NEWSWATCH_HEALTH_HISTORY", raising=False)
    yield


class TestGetProxy:
    def test_returns_none_when_unset(self):
        assert config.get_proxy() is None

    def test_newswatch_proxy_wins(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_PROXY", "http://news.example:8080")
        monkeypatch.setenv("HTTPS_PROXY", "http://fallback.example:8080")
        assert config.get_proxy() == "http://news.example:8080"

    def test_https_proxy_used(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://secure.example:8080")
        assert config.get_proxy() == "http://secure.example:8080"

    def test_https_proxy_lowercase_used(self, monkeypatch):
        monkeypatch.setenv("https_proxy", "http://lower.example:8080")
        assert config.get_proxy() == "http://lower.example:8080"

    def test_http_proxy_lowercase_used(self, monkeypatch):
        monkeypatch.setenv("http_proxy", "http://plain.example:8080")
        assert config.get_proxy() == "http://plain.example:8080"

    def test_uppercase_http_proxy_used(self, monkeypatch):
        monkeypatch.setenv("HTTP_PROXY", "http://upper.example:8080")
        assert config.get_proxy() == "http://upper.example:8080"


class TestGetUserAgent:
    def test_default_returns_non_empty(self, monkeypatch):
        monkeypatch.delenv("NEWSWATCH_USER_AGENT", raising=False)
        assert isinstance(config.get_user_agent(), str)
        assert config.get_user_agent().strip()

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_USER_AGENT", "UA-Override/1.0")
        assert config.get_user_agent() == "UA-Override/1.0"

    def test_env_empty_falls_back(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_USER_AGENT", "")
        assert config.get_user_agent() == config.DEFAULT_USER_AGENT


class TestGetMaxRetries:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("NEWSWATCH_MAX_RETRIES", raising=False)
        assert config.get_max_retries() == config.DEFAULT_MAX_RETRIES

    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_MAX_RETRIES", "5")
        assert config.get_max_retries() == 5

    def test_zero_is_valid(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_MAX_RETRIES", "0")
        assert config.get_max_retries() == 0

    def test_invalid_string_falls_back(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_MAX_RETRIES", "not-a-number")
        assert config.get_max_retries() == config.DEFAULT_MAX_RETRIES

    def test_negative_falls_back(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_MAX_RETRIES", "-1")
        assert config.get_max_retries() == config.DEFAULT_MAX_RETRIES

    def test_empty_falls_back(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_MAX_RETRIES", "")
        assert config.get_max_retries() == config.DEFAULT_MAX_RETRIES


class TestGetHealthHistoryPath:
    def test_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("NEWSWATCH_HEALTH_HISTORY", raising=False)
        assert config.get_health_history_path() is None

    def test_none_when_empty(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_HEALTH_HISTORY", "")
        assert config.get_health_history_path() is None

    def test_returns_path_when_set(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_HEALTH_HISTORY", "/tmp/health.jsonl")
        assert config.get_health_history_path() == "/tmp/health.jsonl"

    def test_relative_path_preserved(self, monkeypatch):
        monkeypatch.setenv("NEWSWATCH_HEALTH_HISTORY", "output/health.jsonl")
        assert config.get_health_history_path() == "output/health.jsonl"
