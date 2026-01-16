"""
Custom exceptions for the newswatch package.

This module defines a hierarchy of exceptions used throughout the newswatch
application for better error handling and debugging.
"""


class NewsWatchError(Exception):
    """Base exception class for all newswatch-related errors."""

    pass


class ScraperError(NewsWatchError):
    """Base exception for scraper-related errors."""

    pass


class NetworkError(ScraperError):
    """Exception raised for network-related errors during scraping."""

    pass


class ParseError(ScraperError):
    """Exception raised when parsing website content fails."""

    pass


class RateLimitError(ScraperError):
    """Exception raised when rate limiting is encountered."""

    def __init__(self, message, retry_after=None):
        """
        Initialize RateLimitError.

        Args:
            message (str): Error message
            retry_after (int, optional): Seconds to wait before retrying
        """
        super().__init__(message)
        self.retry_after = retry_after


class ValidationError(NewsWatchError):
    """Exception raised for input validation errors."""

    pass
