"""web-check-mcp — agent wrapper for Lissy93 Web Check OpenAPI."""

__version__ = "0.2.0"

from .client import CHECK_GROUPS, CHECKS, WebCheckClient

__all__ = ["WebCheckClient", "CHECKS", "CHECK_GROUPS", "__version__"]
