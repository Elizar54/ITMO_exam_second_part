"""Project-specific exceptions for integration boundaries."""


class RetrievalUnavailableError(RuntimeError):
    """Raised when retrieval cannot be performed."""


class LLMTimeoutError(RuntimeError):
    """Raised when an LLM request times out."""


class LLMRateLimitError(RuntimeError):
    """Raised when an LLM provider rate limit is reached."""


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM provider is unavailable."""


class AuditUnavailableError(RuntimeError):
    """Raised when audit storage is unavailable."""
