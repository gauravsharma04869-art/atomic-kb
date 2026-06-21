#!/usr/bin/env python3
"""
Extract atoms, tags, and semantic_edges from old SQLite and
create a JSON-AD import file for atomic-server.
"""
import sqlite3
import json
import sys
import re
from datetime import datetime, timezone

DB_PATH = r"D:\sylvies folder\Project#079\atomic_data\databases\default.db"
OUTPUT_PATH = r"D:\sylvies folder\Project#079\atomic-cloud\seed_backup.jsonad"

# Atomic Data property URLs
P_NAME = "https://atomicdata.dev/properties/name"
P_DESC = "https://atomicdata.dev/properties/description"
P_ISA = "https://atomicdata.dev/properties/isA"
P_CREATED = "https://atomicdata.dev/properties/createdAt"
P_PARENT = "https://atomicdata.dev/properties/parent"
P_SHORTNAME = "https://atomicdata.dev/properties/shortname"
P_TAG = "https://atomicdata.dev/properties/tag"  # Custom property for tagging

CLASS_DOCUMENT = "https://atomicdata.dev/classes/Document"
CLASS_TAG = "https://atomicdata.dev/classes/Tag"

DRIVE_URL = "http://localhost:10000"

def extract():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    result = {
        "resources": [],
        "counts": {}
    }
    
    # --- Extract atoms ---
    try:
        atoms = conn.execute("SELECT * FROM atoms").fetchall()
        atom_columns = [desc[0] for desc in conn.execute("SELECT * FROM atoms LIMIT 0").description]
        print(f"Atoms columns: {atom_columns}", file=sys.stderr)
        print(f"Atoms count: {len(atoms)}", file=sys.stderr)
        
        for a in atoms:
            atom_id = a["id"]
            title = a["title"] or ""
            content = a["content"] or ""
            created_at = a["created_at"] or ""
            updated_at = a["updated_at"] or ""
            
            resource = {
                "@id": f"{DRIVE_URL}/{atom_id}",
                P_ISA: [CLASS_DOCUMENT],
                P_PARENT: DRIVE_URL,
            }
            
            if title:
                resource[P_NAME] = title
            if content:
                resource[P_DESC] = content
            if created_at:
                try:
                    resource[P_CREATED] = int(
                        datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=timezone.utc).timestamp() * 1000
                    )
                except:
                    pass
            
            result["resources"].append(resource)
        
        result["counts"]["atoms"] = len(atoms)
        
        # Print first 3 atoms for verification
        for a in atoms[:3]:
            print(f"  Atom: {a['id'][:8]}... title='{(a['title'] or '')[:50]}'", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting atoms: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
    
    # --- Extract tags ---
    try:
        tags = conn.execute("SELECT * FROM tags").fetchall()
        tag_columns = [desc[0] for desc in conn.execute("SELECT * FROM tags LIMIT 0").description]
        print(f"\nTags columns: {tag_columns}", file=sys.stderr)
        print(f"Tags count: {len(tags)}", file=sys.stderr)
        
        for t in tags:
            tag_id = t["id"]
            name = t["name"] or ""
            
            resource = {
                "@id": f"{DRIVE_URL}/tag-{tag_id}",
                P_ISA: [CLASS_TAG],
                P_PARENT: DRIVE_URL,
            }
            if name:
                resource[P_NAME] = name
                resource[P_SHORTNAME] = name.lower().replace(" ", "-")
            
            result["resources"].append(resource)
        
        result["counts"]["tags"] = len(tags)
        
        for t in tags[:3]:
            print(f"  Tag: {t['id'][:8]}... name='{(t['name'] or '')}'", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting tags: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
    
    # --- Extract atom_tags (links) ---
    try:
        atom_tags = conn.execute("SELECT * FROM atom_tags").fetchall()
        print(f"\natom_tags count: {len(atom_tags)}", file=sys.stderr)
        result["counts"]["atom_tags"] = len(atom_tags)
        if atom_tags:
            print(f"  Sample: {dict(atom_tags[0])}", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting atom_tags: {e}", file=sys.stderr)
    
    # --- Extract semantic_edges ---
    try:
        edges = conn.execute("SELECT * FROM semantic_edges").fetchall()
        edge_columns = [desc[0] for desc in conn.execute("SELECT * FROM semantic_edges LIMIT 0").description]
        print(f"\nsemantic_edges columns: {edge_columns}", file=sys.stderr)
        print(f"semantic_edges count: {len(edges)}", file=sys.stderr)
        if edges:
            print(f"  Sample: {dict(edges[0])}", file=sys.stderr)
        result["counts"]["semantic_edges"] = len(edges)
    except Exception as e:
        print(f"Error extracting semantic_edges: {e}", file=sys.stderr)
    
    # --- Extract settings ---
    try:
        settings = conn.execute("SELECT * FROM settings").fetchall()
        print(f"\nSettings count: {len(settings)}", file=sys.stderr)
        if settings:
            print(f"  Sample: {dict(settings[0])}", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting settings: {e}", file=sys.stderr)
    
    # --- Extract reports ---
    try:
        reports = conn.execute("SELECT * FROM reports").fetchall()
        print(f"\nReports count: {len(reports)}", file=sys.stderr)
        if reports:
            print(f"  Sample: {dict(reports[0])}", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting reports: {e}", file=sys.stderr)
    
    # --- Extract conversations ---
    try:
        conversations = conn.execute("SELECT * FROM conversations").fetchall()
        print(f"\nConversations count: {len(conversations)}", file=sys.stderr)
        if conversations:
            print(f"  Sample: {dict(conversations[0])}", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting conversations: {e}", file=sys.stderr)
    
    conn.close()
    return result

if __name__ == "__main__":
    data = extract()
    
    # Write JSON-AD array
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data["resources"], f, indent=2, default=str)
    
    print(f"\nWritten {len(data['resources'])} resources to {OUTPUT_PATH}", file=sys.stderr)
    print(f"Summary: {json.dumps(data['counts'], indent=2)}", file=sys.stderr)
    print(json.dumps(data["counts"]))
