#!/usr/bin/env python3
"""
Extract all data from the old atomic-server SQLite database 
and output as JSON for migration.
"""
import sqlite3
import json
import sys

DB_PATH = r"D:\sylvies folder\Project#079\atomic_data\databases\default.db"

def extract():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get all tables
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    
    result = {}
    
    for t in tables:
        name = t["name"]
        # Skip virtual tables (like vec0) which may require extensions
        try:
            rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
        except sqlite3.OperationalError as e:
            print(f"  [WARN] Skipping table '{name}': {e}", file=sys.stderr)
            result[name] = {"columns": [], "rows": [], "count": 0, "error": str(e)}
            continue
        columns = [desc[0] for desc in conn.execute(f"SELECT * FROM [{name}] LIMIT 0").description]
        
        rows_list = []
        for r in rows:
            row_dict = {}
            for col in columns:
                val = r[col]
                # Convert bytes to hex string for JSON
                if isinstance(val, bytes):
                    val = val.hex()
                row_dict[col] = val
            rows_list.append(row_dict)
        
        result[name] = {
            "columns": columns,
            "rows": rows_list,
            "count": len(rows_list)
        }
    
    conn.close()
    return result

if __name__ == "__main__":
    data = extract()
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Exported to {out_path}", file=sys.stderr)
    else:
        print(json.dumps(data, indent=2, default=str))
