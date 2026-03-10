# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb",
#     "pyarrow",
#     "pandas",
#     "tantivy",
# ]
# ///

import argparse
import json
import os
import lancedb
import pyarrow as pa
import hashlib
from datetime import datetime

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
base_dir = os.environ.get('MEMORY_BANK_DIR')
if base_dir:
    DB_PATH = os.path.join(base_dir, 'lancedb')
    EXPORT_PATH = os.path.join(base_dir, 'conclusions_backup.parquet')
else:
    DB_PATH = os.path.join(PROJECT_ROOT, '.agent', 'memory-bank', 'lancedb')
    EXPORT_PATH = os.path.join(PROJECT_ROOT, '.agent', 'memory-bank', 'conclusions_backup.parquet')

# Ensure directories exist
os.makedirs(DB_PATH, exist_ok=True)
os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)

# Connection to LanceDB
_db_connection = None

def get_db():
    global _db_connection
    if _db_connection is None:
        _db_connection = lancedb.connect(DB_PATH)
    return _db_connection

# Define schema for the table
schema = pa.schema([
    ("id", pa.string()),
    ("text", pa.string()),
    ("metadata", pa.string()),
    ("timestamp", pa.string())
])

TABLE_NAME = "memory_bank"

def get_or_create_table():
    db = get_db()
    try:
        return db.open_table(TABLE_NAME)
    except Exception:
        return db.create_table(TABLE_NAME, schema=schema)

def export_to_parquet():
    table = get_or_create_table()
    df = table.to_pandas()
    df.to_parquet(EXPORT_PATH)
    print(f"Exported {len(df)} records to {EXPORT_PATH}")

def save_memory(text, metadata_json):
    if "type" not in metadata_json:
        metadata_json["type"] = "learning" # default or we could error out
        
    table = get_or_create_table()
    timestamp = datetime.now().isoformat()
    record_id = hashlib.sha256((text + timestamp).encode()).hexdigest()
    
    data = [{
        "id": record_id,
        "text": text,
        "metadata": json.dumps(metadata_json),
        "timestamp": timestamp
    }]
    
    table.add(data)
    print(f"Saved memory: {record_id}")
    # Decoupled export, must be manually triggered now or handled via separate command
    
def update_memory(record_id, text, metadata_json):
    table = get_or_create_table()
    timestamp = datetime.now().isoformat()
    
    # We delete the old one and insert the new one
    table.delete(f"id = '{record_id}'")
    
    data = [{
        "id": record_id,
        "text": text,
        "metadata": json.dumps(metadata_json),
        "timestamp": timestamp
    }]
    
    table.add(data)
    print(f"Updated memory: {record_id}")

def delete_memory(record_id):
    table = get_or_create_table()
    table.delete(f"id = '{record_id}'")
    print(f"Deleted memory: {record_id}")

def query_memory(query_text, format_type="markdown"):
    table = get_or_create_table()
    
    try:
        # Create FTS index in case there's new data. Replace=True allows recreating it.
        table.create_fts_index("text", replace=True)
        results_df = table.search(query_text).limit(20).to_pandas()
    except Exception as e:
        # Fallback if FTS fails (e.g. empty table or tantivy not working)
        df = table.to_pandas()
        if df.empty:
            if format_type == "json":
                print(json.dumps([]))
            else:
                print("No memories found.")
            return
            
        results_df = df[
            df['text'].astype(str).str.contains(query_text, case=False, na=False) |
            df['metadata'].astype(str).str.contains(query_text, case=False, na=False)
        ]
        
    if results_df.empty:
        if format_type == "json":
            print(json.dumps([]))
        else:
            print("No memories found.")
        return
        
    output = []
    for _, row in results_df.iterrows():
        output.append({
            "id": row['id'],
            "text": row['text'],
            "metadata": json.loads(row['metadata']),
            "timestamp": row['timestamp']
        })
        
    if format_type == "json":
        print(json.dumps(output, indent=2))
    else:
        # Markdown formatting
        print(f"### Memory Search Results for '{query_text}'\n")
        for idx, item in enumerate(output):
            print(f"**{idx + 1}. ID:** `{item['id']}`")
            print(f"**Date:** {item['timestamp']}")
            print(f"**Text:**\n{item['text']}\n")
            print(f"**Metadata:**")
            for k, v in item['metadata'].items():
                print(f"- `{k}`: {v}")
            print("\n---\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory Manager for Project Memory Bank")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Save command
    save_parser = subparsers.add_parser("save", help="Save a new memory")
    save_parser.add_argument("--text", required=True, help="Text conclusion or learning")
    save_parser.add_argument("--metadata", required=True, help="JSON string of metadata")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update an existing memory")
    update_parser.add_argument("--id", required=True, help="ID of the memory to update")
    update_parser.add_argument("--text", required=True, help="Updated text")
    update_parser.add_argument("--metadata", required=True, help="Updated JSON string of metadata")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an existing memory")
    delete_parser.add_argument("--id", required=True, help="ID of the memory to delete")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query memories")
    query_parser.add_argument("--query", required=True, help="Text to search for")
    query_parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output format")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export memory bank to parquet")
    
    args = parser.parse_args()
    
    if args.command == "save":
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("Error: metadata must be a valid JSON string.")
            exit(1)
            
        if "type" not in metadata:
            print("Error: metadata must contain a 'type' key.")
            exit(1)
            
        save_memory(args.text, metadata)
        
    elif args.command == "update":
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("Error: metadata must be a valid JSON string.")
            exit(1)
            
        if "type" not in metadata:
            print("Error: metadata must contain a 'type' key.")
            exit(1)
            
        update_memory(args.id, args.text, metadata)
        
    elif args.command == "delete":
        delete_memory(args.id)
        
    elif args.command == "query":
        query_memory(args.query, args.format)
        
    elif args.command == "export":
        export_to_parquet()
        
    else:
        parser.print_help()
