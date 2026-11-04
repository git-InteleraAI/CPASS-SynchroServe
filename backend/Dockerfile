# CPASS Backend Dockerfile
# Python 3.11 slim runtime with pinned reproducible dependencies and non-root execution

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal OS dependencies for network operations and container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -s /bin/bash -m appuser

# Install pinned production dependencies directly for deterministic reproducible builds
RUN pip install --no-cache-dir \
    fastapi==0.147.0 \
    "uvicorn[standard]==0.54.0" \
    supabase==2.33.0 \
    pydantic-settings==2.16.0 \
    python-multipart==0.0.32 \
    pandas==3.0.6 \
    openpyxl==3.1.5 \
    google-api-python-client==2.201.0 \
    google-auth==2.62.0 \
    httpx==0.28.1

# Copy application source files
COPY . /app

# Ensure proper non-root permissions
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose internal FastAPI listening port
EXPOSE 8000

# Container healthcheck targeting the unauthenticated /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn ASGI server with proxy headers enabled
# Restrict forwarded-allow-ips to loopback and private Docker RFC 1918 subnets for defense-in-depth
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16"]
