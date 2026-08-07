# MCP-only image (thin wrapper). Upstream Web Check API is external.
# For full UI+API self-host, run lissy93/web-check separately and point
# WEB_CHECK_BASE_URL at it - see docker-compose.yml.

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy only necessary files for installation (better layer caching)
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Upgrade pip and install the package (non-editable for production)
RUN pip install --upgrade pip && \
    pip install .

# Default configuration
ENV WEB_CHECK_BASE_URL=https://web-check.as93.net/api \
    WEB_CHECK_TIMEOUT=25 \
    WEB_CHECK_MAX_WORKERS=6 \
    WEB_CHECK_MAX_CHARS=12000

# Switch to non-root user
USER appuser

# Healthcheck - verify MCP server is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.client import WebCheckClient; import sys; sys.exit(0 if WebCheckClient().health()['reachable'] else 1)" || exit 1

# Run MCP server in STDIO mode by default
ENTRYPOINT ["python", "-m", "src.server"]
CMD ["--stdio"]
