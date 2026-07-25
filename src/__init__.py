"""web-check-mcp — agent wrapper for Lissy93 Web Check OpenAPI."""

__version__ = "0.2.0"

from .client import WebCheckClient, CHECKS, CHECK_GROUPS

__all__ = ["WebCheckClient", "CHECKS", "CHECK_GROUPS", "__version__"]
