FROM joepmeneer/atomic-server:latest

# Install AWS CLI for R2 S3-compatible sync
RUN apt-get update && apt-get install -y --no-install-recommends \
    awscli \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create data directory
RUN mkdir -p /atomic-storage

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy seed script
COPY seed_from_backup.py /seed_from_backup.py

# Install Python for seed script
RUN apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-9883}/health || exit 1

# Render injects $PORT; we bind to it
ENV ATOMIC_PORT=9883
ENV ATOMIC_IP=0.0.0.0
ENV ATOMIC_DATA_DIR=/atomic-storage

EXPOSE 9883

ENTRYPOINT ["/entrypoint.sh"]
