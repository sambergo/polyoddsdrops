# Stage 1: Build React UI
FROM oven/bun:1 AS ui-builder
WORKDIR /app/ui
COPY ui/package.json ui/bun.lockb* ./
RUN bun install --frozen-lockfile
COPY ui/ .
RUN bun run build

# Stage 2: Python application
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/
COPY main.py .

# Copy built UI from stage 1
COPY --from=ui-builder /app/ui/dist ui/dist

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 3565

CMD ["uv", "run", "python", "main.py"]
