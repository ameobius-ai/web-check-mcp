# Bundle web-check-mcp CLI with the upstream web-check app.
# Gives you a single container exposing :3000 (Web Check UI+API) and the
# `web-check-mcp` entrypoint for MCP stdio use.
FROM node:20-alpine AS webcheck
RUN apk add --no-cache chromium
ENV CHROME_PATH=/usr/bin/chromium-browser
WORKDIR /app
COPY . .
RUN yarn install --frozen-lockfile && yarn build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=webcheck /app /app/web-check
COPY src/ ./src/
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .

ENV WEB_CHECK_BASE_URL=http://127.0.0.1:3000/api
ENV CHROME_PATH=/usr/bin/chromium
EXPOSE 3000

# Start upstream web-check (API+UI) in background; foreground stays MCP-able.
CMD ["sh", "-c", "cd /app/web-check && node server.js &  sleep 3 && exec python -m src.server --stdio"]
