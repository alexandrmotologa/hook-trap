FROM python:3.12-slim

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project metadata and install dependencies
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache -e .

# Copy application code
COPY hook_trap/ ./hook_trap/

# Persistent data directory
VOLUME ["/data"]
ENV HOOK_TRAP_DB_PATH=/data/hook_trap.db
ENV HOOK_TRAP_HOST=0.0.0.0
ENV HOOK_TRAP_PORT=8080

EXPOSE 8080

ENTRYPOINT ["hook-trap"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--db-path", "/data/hook_trap.db"]
