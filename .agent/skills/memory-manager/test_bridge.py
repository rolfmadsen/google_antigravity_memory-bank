import os
import json
import pytest
from unittest.mock import patch
import lancedb

# Set environment variable before importing bridge
# This ensures it uses the tmp_path immediately if any paths are evaluated at import
# though we already refactored it to be safer.

@pytest.fixture
def temp_memory_dir(tmp_path):
    os.environ['MEMORY_BANK_DIR'] = str(tmp_path)
    yield tmp_path
    del os.environ['MEMORY_BANK_DIR']

def test_save_and_query_memory(temp_memory_dir, capsys):
    # Import inside the test function to ensure the env var is set
    from bridge import save_memory, query_memory, EXPORT_PATH

    # Test saving
    test_text = "This is a test conclusion."
    test_meta = {"type": "test", "status": "active"}
    
    save_memory(test_text, test_meta)
    
    # We need the ID for update and delete logic.
    # We can calculate it exactly as bridge.py does
    import hashlib
    from datetime import datetime
    
    # In a real scenario we wouldn't easily know the timestamp the function used,
    # so we'll grab the ID directly from the LanceDB table for testing updates
    from bridge import get_or_create_table
    table = get_or_create_table()
    saved_record = table.to_pandas().iloc[0]
    record_id = saved_record['id']
    
    # Decoupled export, so parquet won't exist yet. We can manually export it.
    from bridge import export_to_parquet
    export_to_parquet()
    
    # Check if parquet file was created
    assert os.path.exists(EXPORT_PATH)
    
    # Test querying with json format explicitly
    query_memory("test conclusion", format_type="json")
    captured = capsys.readouterr()
    
    # The output should be a JSON string representing the search results
    output_lines = captured.out.strip().split('\n')
    
    # bridge.py prints "Saved memory: <id>" and "Exported X records..."
    # we need to find the json block at the end. We assume it's the last block of text.
    # A cleaner way is to parse the raw json string
    json_output = ""
    for line in output_lines:
        if line.startswith('[') or line.startswith('{') or json_output:
            json_output += line + "\n"
            
    try:
        results = json.loads(json_output)
        assert len(results) == 1
        assert results[0]['id'] == record_id
        assert results[0]['text'] == test_text
        assert results[0]['metadata'] == test_meta
    except json.JSONDecodeError:
        pytest.fail(f"Failed to parse JSON output: {json_output}")

    # Clear captured output
    captured = capsys.readouterr()

    # Test updating
    from bridge import update_memory, delete_memory
    
    updated_text = "This is an updated conclusion."
    updated_meta = {"type": "test", "status": "updated"}
    
    update_memory(record_id, updated_text, updated_meta)
    
    query_memory("updated conclusion", format_type="json")
    captured = capsys.readouterr()
    
    json_output = ""
    for line in captured.out.strip().split('\n'):
        if line.startswith('[') or line.startswith('{') or json_output:
            json_output += line + "\n"
            
    try:
        results = json.loads(json_output)
        assert len(results) == 1
        assert results[0]['id'] == record_id
        assert results[0]['text'] == updated_text
        assert results[0]['metadata'] == updated_meta
    except json.JSONDecodeError:
        pytest.fail(f"Failed to parse JSON output: {json_output}")
        
    # Clear captured output
    captured = capsys.readouterr()
        
    # Test deleting
    delete_memory(record_id)
    
    query_memory("updated conclusion", format_type="json")
    captured = capsys.readouterr()
    
    # The output should be the empty array since nothing should be found
    json_output = ""
    for line in captured.out.strip().split('\n'):
        if line.startswith('[') or line.startswith('{') or json_output:
            json_output += line + "\n"
            
    try:
        results = json.loads(json_output)
        assert len(results) == 0
    except json.JSONDecodeError:
        pytest.fail(f"Failed to parse JSON output: {json_output}")

