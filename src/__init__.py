"""web-check-mcp — agent wrapper for Lissy93 Web Check OpenAPI."""

__version__ = "0.3.0"

from .client import CHECK_GROUPS, CHECKS, WebCheckClient

__all__ = ["CHECKS", "CHECK_GROUPS", "WebCheckClient", "__version__"]
