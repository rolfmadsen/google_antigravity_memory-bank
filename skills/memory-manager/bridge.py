# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb",
#     "pyarrow",
#     "pandas",
# ]
# ///

import argparse
import json
import os
import lancedb
import pyarrow as pa
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
    table = get_or_create_table()
    timestamp = datetime.now().isoformat()
    record_id = str(hash(text + timestamp))
    
    data = [{
        "id": record_id,
        "text": text,
        "metadata": json.dumps(metadata_json),
        "timestamp": timestamp
    }]
    
    table.add(data)
    print(f"Saved memory: {record_id}")
    export_to_parquet()

def query_memory(query_text):
    table = get_or_create_table()
    df = table.to_pandas()
    
    if df.empty:
        print(json.dumps([]))
        return
        
    # Simple substring search in text and metadata
    results = df[
        df['text'].astype(str).str.contains(query_text, case=False, na=False) |
        df['metadata'].astype(str).str.contains(query_text, case=False, na=False)
    ]
    
    output = []
    for _, row in results.iterrows():
        output.append({
            "id": row['id'],
            "text": row['text'],
            "metadata": json.loads(row['metadata']),
            "timestamp": row['timestamp']
        })
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory Manager for Project Memory Bank")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Save command
    save_parser = subparsers.add_parser("save", help="Save a new memory")
    save_parser.add_argument("--text", required=True, help="Text conclusion or learning")
    save_parser.add_argument("--metadata", required=True, help="JSON string of metadata")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query memories")
    query_parser.add_argument("--query", required=True, help="Text to search for")
    
    args = parser.parse_args()
    
    if args.command == "save":
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("Error: metadata must be a valid JSON string.")
            exit(1)
        save_memory(args.text, metadata)
    elif args.command == "query":
        query_memory(args.query)
    else:
        parser.print_help()
