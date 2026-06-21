FROM joepmeneer/atomic-server:latest

# Install curl (for R2 API calls), python3, and cryptography (for seed script)
# Base image is Alpine Linux, so we use apk
RUN apk add --no-cache \
    curl \
    ca-certificates \
    python3 \
    py3-cryptography \
    openssl

# Create data directory
RUN mkdir -p /atomic-storage

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy seed backup (JSON-AD for atomic-server import)
COPY seed_backup.jsonad /seed_backup.jsonad

# Copy seed script (HTTP API-based, generates agent + posts data)
COPY seed_via_api.py /seed_via_api.py

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-9883}/health || exit 1

# Render injects $PORT; we bind to it
ENV ATOMIC_PORT=9883
ENV ATOMIC_IP=0.0.0.0
ENV ATOMIC_DATA_DIR=/atomic-storage

EXPOSE 9883

ENTRYPOINT ["/entrypoint.sh"]
