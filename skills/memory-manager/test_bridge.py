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
    
    # Check if parquet file was created
    assert os.path.exists(EXPORT_PATH)
    
    # Test querying
    query_memory("test conclusion")
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
        assert results[0]['text'] == test_text
        assert results[0]['metadata'] == test_meta
    except json.JSONDecodeError:
        pytest.fail(f"Failed to parse JSON output: {json_output}")

