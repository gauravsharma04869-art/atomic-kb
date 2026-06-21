#!/bin/bash
set -e

# ============================================================
#  atomic-server Cloud Deploy — Render + Cloudflare R2
#  Syncs data on startup and every 5 minutes to survive
#  Render's ephemeral filesystem.
# ============================================================

# --- Configuration ---
DATA_DIR="${ATOMIC_DATA_DIR:-/atomic-storage}"
R2_BUCKET="${R2_BUCKET:-atomic-kb-data}"
R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Render injects PORT; fallback to ATOMIC_PORT if not set
LISTEN_PORT="${PORT:-${ATOMIC_PORT:-9883}}"

echo "==================================="
echo "  Atomic-Server Cloud Deploy"
echo "==================================="
echo "Data directory: $DATA_DIR"
echo "Listen port:    $LISTEN_PORT"
echo "R2 bucket:      $R2_BUCKET"
echo "==================================="

# --- Configure AWS CLI for R2 ---
aws configure set aws_access_key_id "$R2_ACCESS_KEY_ID" 2>/dev/null
aws configure set aws_secret_access_key "$R2_SECRET_ACCESS_KEY" 2>/dev/null

# --- Restore data from R2 ---
echo ""
echo "-> Restoring from R2..."
mkdir -p "${DATA_DIR}/databases"

if [ -n "$R2_ACCESS_KEY_ID" ] && [ -n "$R2_SECRET_ACCESS_KEY" ]; then
    aws s3 sync "s3://${R2_BUCKET}/data/" "${DATA_DIR}/" \
        --endpoint-url "$R2_ENDPOINT" \
        --exclude "*.db-shm" \
        --exclude "*.db-wal" \
        2>&1 || echo "   [INFO] No existing data in R2. Starting fresh."
    
    # Move database to the location atomic-server expects it
    if [ -f "${DATA_DIR}/default.db" ]; then
        mkdir -p "${DATA_DIR}/databases"
        cp "${DATA_DIR}/default.db" "${DATA_DIR}/databases/default.db"
        echo "   Database restored from R2 backup."
    fi
else
    echo "   [INFO] R2 credentials not set. Running without persistence."
fi

# --- Build command flags ---
FLAGS="--data-path $DATA_DIR --port $LISTEN_PORT --ip 0.0.0.0"

if [ -n "$ATOMIC_AUTH_TOKEN" ]; then
    FLAGS="$FLAGS --auth-token $ATOMIC_AUTH_TOKEN"
    echo "   Auth token configured"
fi

if [ "$ATOMIC_PUBLIC_MODE" = "true" ]; then
    FLAGS="$FLAGS --public-mode"
fi

# Add any extra flags passed as arguments
if [ $# -gt 0 ]; then
    FLAGS="$FLAGS $@"
fi

# --- Start atomic-server ---
echo ""
echo "-> Starting atomic-server..."
echo "   atomic-server $FLAGS"
atomic-server $FLAGS 2>&1 &
ATOMIC_PID=$!

# Wait for it to be ready
echo "   Waiting for server to be ready..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${LISTEN_PORT}/health" > /dev/null 2>&1; then
        echo "   Server is ready! (PID: $ATOMIC_PID)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "   [WARN] Server may not have started correctly."
    fi
    sleep 1
done

# --- Seed from R2 backup if atoms are missing ---
echo ""
echo "-> Running seed from backup..."
BACKUP_PATH="${DATA_DIR}/atomic_backup.json"
if [ -f "$BACKUP_PATH" ]; then
    python3 /seed_from_backup.py || echo "   [INFO] Seed completed or skipped."
else
    echo "   [INFO] No backup found at $BACKUP_PATH. Skipping seed."
fi

# --- Background sync loop ---
if [ -n "$R2_ACCESS_KEY_ID" ] && [ -n "$R2_SECRET_ACCESS_KEY" ]; then
    echo ""
    echo "-> Starting background sync to R2 (every 5 minutes)..."
    (
    while true; do
        sleep 300
        if [ -d "${DATA_DIR}" ]; then
            aws s3 sync "${DATA_DIR}/" "s3://${R2_BUCKET}/data/" \
                --endpoint-url "$R2_ENDPOINT" \
                --exclude "*.db-shm" \
                --exclude "*.db-wal" \
                2>&1 | grep -v "upload:" || echo "   [sync] Nothing new to upload"
        fi
    done
    ) &
    SYNC_PID=$!
    echo "   Sync loop started (PID: $SYNC_PID)"
fi

# --- Wait for atomic-server (foreground) ---
wait $ATOMIC_PID
