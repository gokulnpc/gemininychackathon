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

# Expose port — Cloud Run injects $PORT (8080), local dev uses 8000
EXPOSE 8080

# Health check uses $PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','8080') + '/health')"

# Run with uvicorn — respects $PORT injected by Cloud Run (defaults to 8080)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
