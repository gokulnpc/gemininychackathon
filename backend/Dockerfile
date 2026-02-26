# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System runtime dependencies
#   ffmpeg       — video processing (compose, animate, export)
#   libjpeg-dev  — Pillow JPEG encode/decode (Gemini image chain-editing)
#   libpng-dev   — Pillow PNG support
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libjpeg62-turbo \
        libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create directories that the pipeline writes to at runtime
RUN mkdir -p /app/output /tmp/voicevid_work

# Expose the FastAPI port
EXPOSE 8000

# Health check — Docker / ECS will restart if /health stops responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with uvicorn (1 worker — pipeline is async, not CPU-bound per request)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
