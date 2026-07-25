# MCP-only image (thin wrapper). Upstream Web Check API is external.
# For full UI+API self-host, run lissy93/web-check separately and point
# WEB_CHECK_BASE_URL at it — see docker-compose.yml.
FROM python:3.12-slim
WORKDIR /app
COPY src/ ./src/
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir -e .

ENV WEB_CHECK_BASE_URL=https://web-check.as93.net/api
ENTRYPOINT ["python", "-m", "src.server"]
CMD ["--stdio"]
