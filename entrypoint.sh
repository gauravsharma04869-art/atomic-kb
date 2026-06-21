#!/bin/sh
set -e

# ============================================================
#  atomic-server Cloud Deploy — Render + Cloudflare R2
#  Uses Cloudflare API (cfat token) for R2 access — no S3 keys needed.
#  Syncs data on startup and every 5 minutes to survive
#  Render's ephemeral filesystem.
# ============================================================

# --- Configuration ---
DATA_DIR="${ATOMIC_DATA_DIR:-/atomic-storage}"
R2_BUCKET="${R2_BUCKET:-atomic-kb-data}"
R2_ACCOUNT_ID="${R2_ACCOUNT_ID}"
CF_API_TOKEN="${CF_API_TOKEN}"
R2_API_BASE="https://api.cloudflare.com/client/v4/accounts/${R2_ACCOUNT_ID}/r2/buckets/${R2_BUCKET}/objects"

# Render injects PORT; fallback to ATOMIC_PORT if not set
LISTEN_PORT="${PORT:-${ATOMIC_PORT:-9883}}"

echo "==================================="
echo "  Atomic-Server Cloud Deploy"
echo "==================================="
echo "Data directory: $DATA_DIR"
echo "Listen port:    $LISTEN_PORT"
echo "R2 bucket:      $R2_BUCKET"
echo "==================================="

# --- Helper: download from R2 via CF API ---
r2_download() {
    local object="$1"
    local output="$2"
    if [ -z "$CF_API_TOKEN" ] || [ -z "$R2_ACCOUNT_ID" ]; then
        return 1
    fi
    local url="${R2_API_BASE}/${object}"
    http_code=$(curl -s -o "$output" -w "%{http_code}" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        "$url")
    if [ "$http_code" = "200" ]; then
        return 0
    else
        rm -f "$output"
        return 1
    fi
}

# --- Helper: upload to R2 via CF API ---
r2_upload() {
    local object="$1"
    local file="$2"
    if [ -z "$CF_API_TOKEN" ] || [ -z "$R2_ACCOUNT_ID" ]; then
        return 1
    fi
    if [ ! -f "$file" ]; then
        return 1
    fi
    local url="${R2_API_BASE}/${object}"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X PUT \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/octet-stream" \
        --data-binary "@$file" \
        "$url")
    [ "$http_code" = "200" ]
}

# --- Restore data from R2 ---
echo ""
echo "-> Restoring from R2..."

if [ -n "$CF_API_TOKEN" ] && [ -n "$R2_ACCOUNT_ID" ]; then
    
    # Download the main store — new atomic-server expects SQLite at "${DATA_DIR}/store"
    if r2_download "default.db" "${DATA_DIR}/store"; then
        echo "   Database restored from R2 backup ($(du -h "${DATA_DIR}/store" | cut -f1))."
    else
        echo "   [INFO] No existing database in R2. Starting fresh."
    fi
    
    # Also restore registry (settings, tokens) if available
    if r2_download "registry.db" "${DATA_DIR}/registry.db"; then
        echo "   Registry restored from R2 backup ($(du -h "${DATA_DIR}/registry.db" | cut -f1))."
    else
        echo "   [INFO] No registry in R2. Starting fresh config."
    fi
else
    echo "   [INFO] Cloudflare API token not set. Running without persistence."
fi

# --- Build command flags ---
# Public URL — Render URL is stable; Cloudflare Worker is the user-facing domain
PUBLIC_URL="${PUBLIC_URL:-https://atomic-kb.onrender.com}"
FLAGS="--data-dir $DATA_DIR --port $LISTEN_PORT --ip 0.0.0.0 --public-mode --server-url $PUBLIC_URL"

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

# --- Background sync loop (every 5 minutes) ---
if [ -n "$CF_API_TOKEN" ] && [ -n "$R2_ACCOUNT_ID" ]; then
    DB_PATH="${DATA_DIR}/store"
    echo ""
    echo "-> Starting background sync to R2 (every 5 minutes)..."
    (
    while true; do
        sleep 300
        if [ -f "$DB_PATH" ]; then
            if r2_upload "default.db" "$DB_PATH"; then
                echo "   [sync] Database synced to R2 ($(date -u +"%Y-%m-%dT%H:%M:%SZ"))"
            else
                echo "   [sync] Upload failed"
            fi
        fi
    done
    ) &
    SYNC_PID=$!
    echo "   Sync loop started (PID: $SYNC_PID)"
fi

# --- Wait for atomic-server (foreground) ---
wait $ATOMIC_PID
