#!/bin/sh
set -e

# ============================================================
#  atomic-server Cloud Deploy — Render + Cloudflare R2
#  Uses Cloudflare API (cfat token) for R2 access — no S3 keys.
#  Seeds from JSON-AD backup on start, syncs sled store to
#  R2 every 5 minutes to survive ephemeral filesystem.
# ============================================================

# --- Configuration ---
DATA_DIR="${ATOMIC_DATA_DIR:-/atomic-storage}"
R2_BUCKET="${R2_BUCKET:-atomic-kb-data}"
R2_ACCOUNT_ID="${R2_ACCOUNT_ID}"
CF_API_TOKEN="${CF_API_TOKEN}"
R2_API_BASE="https://api.cloudflare.com/client/v4/accounts/${R2_ACCOUNT_ID}/r2/buckets/${R2_BUCKET}/objects"

# Render injects PORT; fallback to ATOMIC_PORT if not set
LISTEN_PORT="${PORT:-${ATOMIC_PORT:-9883}}"

# Public URL — Render URL is stable; Cloudflare Worker is the user-facing domain
PUBLIC_URL="${PUBLIC_URL:-https://atomic-kb.onrender.com}"

echo "==================================="
echo "  Atomic-Server Cloud Deploy"
echo "==================================="
echo "Data directory: $DATA_DIR"
echo "Listen port:    $LISTEN_PORT"
echo "Public URL:     $PUBLIC_URL"
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

# --- Restore sled store from R2 ---
echo ""
echo "-> Restoring store from R2..."

STORE_DIR="${DATA_DIR}/store"
mkdir -p "$STORE_DIR"

if [ -n "$CF_API_TOKEN" ] && [ -n "$R2_ACCOUNT_ID" ]; then
    if r2_download "store_snapshot.tar.gz" "/tmp/store_snapshot.tar.gz"; then
        echo "   Store snapshot downloaded. Extracting..."
        tar -xzf "/tmp/store_snapshot.tar.gz" -C "$DATA_DIR"
        rm -f "/tmp/store_snapshot.tar.gz"
        echo "   Store restored from R2 snapshot ($(du -sh "$STORE_DIR" | cut -f1))."
    else
        echo "   [INFO] No existing snapshot in R2. Starting fresh store."
    fi
else
    echo "   [INFO] Cloudflare API token not set. Running without persistence."
fi

# --- Seed from JSON-AD backup ---
echo ""
echo "-> Seeding data from JSON-AD backup..."
SEED_FILE="/seed_backup.jsonad"
if [ -f "$SEED_FILE" ]; then
    # Replace old parent URL (localhost:10000) with actual server URL
    echo "   Replacing parent URLs with: $PUBLIC_URL"
    sed "s|http://localhost:10000|$PUBLIC_URL|g" "$SEED_FILE" > "/tmp/seed_backup.jsonad"

    echo "   Importing seed data into store..."
    atomic-server import -p "/tmp/seed_backup.jsonad" --data-dir "$DATA_DIR" 2>&1
    echo "   Seed import completed."
    rm -f "/tmp/seed_backup.jsonad"
else
    echo "   [WARN] Seed file not found at $SEED_FILE. Skipping."
fi

# --- Ensure setup invite is available ---
echo ""
echo "-> Initializing setup invite..."
atomic-server --initialize --data-dir "$DATA_DIR" 2>&1 || echo "   [INFO] Initialize skipped (already configured)."

# --- Build command flags ---
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
    echo ""
    echo "-> Starting background sync to R2 (every 5 minutes)..."
    (
    while true; do
        sleep 300
        if [ -d "$STORE_DIR" ] && [ -n "$(ls -A "$STORE_DIR" 2>/dev/null)" ]; then
            SNAPSHOT="/tmp/store_snapshot.tar.gz"
            tar -czf "$SNAPSHOT" -C "$DATA_DIR" "store"
            if r2_upload "store_snapshot.tar.gz" "$SNAPSHOT"; then
                echo "   [sync] Store synced to R2 ($(date -u +"%Y-%m-%dT%H:%M:%SZ"))"
            else
                echo "   [sync] Upload failed"
            fi
            rm -f "$SNAPSHOT"
        fi
    done
    ) &
    SYNC_PID=$!
    echo "   Sync loop started (PID: $SYNC_PID)"
fi

# --- Wait for atomic-server (foreground) ---
wait $ATOMIC_PID
