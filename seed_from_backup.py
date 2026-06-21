#!/usr/bin/env python3
"""
Seed atomic-server from JSON backup if atoms table is empty.
Runs after atomic-server starts, checks via API, and imports if needed.
"""
import json, os, sys, time, urllib.request, urllib.error

API_BASE = os.environ.get("ATOMIC_API_URL", "http://127.0.0.1:9883")
BACKUP_PATH = os.environ.get("BACKUP_PATH", "/atomic-storage/atomic_backup.json")
AUTH_TOKEN = os.environ.get("ATOMIC_AUTH_TOKEN", "")

HEADERS = {"Content-Type": "application/json"}
if AUTH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {AUTH_TOKEN}"

def api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  [seed] GET {path} failed: HTTP {e.code}", flush=True)
        return None
    except Exception as e:
        print(f"  [seed] GET {path} failed: {e}", flush=True)
        return None

def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:200]
        print(f"  [seed] POST {path} failed: HTTP {e.code} {err}", flush=True)
        return None

def main():
    print("[seed] Checking if seeding is needed...", flush=True)
    
    # Wait for server
    for i in range(30):
        result = api_get("/health")
        if result:
            break
        time.sleep(1)
    
    if not result:
        print("[seed] ERROR: Server not ready after 30s", flush=True)
        return
    
    # Check atom count
    result = api_get("/atoms?limit=1")
    count = (result.get("total_count", 0) if result else 0)
    print(f"[seed] Current atom count: {count}", flush=True)
    
    if count > 0:
        print("[seed] Atoms exist, skipping seed.", flush=True)
        return
    
    # Load backup
    if not os.path.exists(BACKUP_PATH):
        print(f"[seed] Backup not found at {BACKUP_PATH}, skipping.", flush=True)
        return
    
    print(f"[seed] Loading backup from {BACKUP_PATH}...", flush=True)
    with open(BACKUP_PATH, "r", encoding="utf-8") as f:
        backup = json.load(f)
    
    atoms = backup.get("atoms", [])
    tags = backup.get("tags", [])
    print(f"[seed] Found {len(atoms)} atoms and {len(tags)} tags in backup", flush=True)
    
    # Create tags
    for t in tags:
        name = t.get("name", "")
        if not name:
            continue
        payload = {"name": name}
        result = api_post("/tags", payload)
        if result:
            print(f"  [seed] Tag: {name}", flush=True)
        time.sleep(0.05)
    
    # Create atoms
    for i, a in enumerate(atoms):
        content = a.get("content", "")
        title = a.get("title", "")
        payload = {"content": content}
        if title:
            payload["title"] = title
        if a.get("id"):
            payload["id"] = a["id"]
        
        result = api_post("/atoms", payload)
        if result:
            print(f"  [seed] Atom {i+1}/{len(atoms)}: {title[:40]}...", flush=True)
        time.sleep(0.05)
    
    print(f"[seed] Done! {len(atoms)} atoms seeded.", flush=True)

if __name__ == "__main__":
    main()
