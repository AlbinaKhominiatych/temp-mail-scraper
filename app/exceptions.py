class TempMailError(Exception):
    """Base exception for all scraper errors."""


class SessionError(TempMailError):
    """Browser session is broken or unreachable."""


class ElementNotFoundError(TempMailError):
    """A required DOM element was not found after waiting."""


class EmailNotFoundError(TempMailError):
    """The requested email ID does not exist in the current inbox."""


class RefreshError(TempMailError):
    """Failed to generate a new email address."""
