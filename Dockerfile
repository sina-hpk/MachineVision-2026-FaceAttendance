# CV Attendance System - Dockerfile
# Multi-stage build for production (Linux containers)

# Build stage: install Python deps (heavy native builds: dlib, insightface)
FROM python:3.11-slim as builder

# System deps required to BUILD native extensions (dlib needs cmake)
# Note: on Debian Trixie (base of python:3.11-slim) the package is `libgl1`
#       (libgl1-mesa-glx was removed).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Runtime libraries only (no compiler needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

WORKDIR /app

# Copy installed packages from build stage
ENV PYTHONPATH=/install/lib/python3.11/site-packages
COPY --from=builder /install /install

# Copy application code
COPY --chown=appuser:appuser . .

# Create data directories
RUN mkdir -p /app/data/faces /app/data/attendance && \
    chown -R appuser:appuser /app/data

# Non-root user needs a writable HOME: InsightFace downloads its model
# weights to ~/.insightface on first use and the process refuses to start
# without a writable home directory.
ENV HOME=/home/appuser

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=5)" || exit 1

# Run the application (workers=1: the camera thread must not be duplicated)
CMD ["python", "-m", "uvicorn", "main_fastapi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]