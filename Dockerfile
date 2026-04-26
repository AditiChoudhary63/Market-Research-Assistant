FROM python:3.14-slim

# Install uv in runtime too (so venv/scripts are created in final image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install system CA certificates and zstd support
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libzstd-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PORT=8000

# Copy application code
COPY . .

# Install project + runtime dependencies into uv-managed environment
RUN uv sync --frozen --no-dev

# Expose the application port
EXPOSE 8000

# Run the FastAPI server
CMD ["uv", "run", "--frozen", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
