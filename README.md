# Google Antigravity Memory Bank

A standalone, local-first persistent memory module for Google Antigravity agents. 

## The Problem
By default, AI coding agents like Google Antigravity can lose context between deep work sessions or rapidly evolving project structures. They understand what they are currently looking at, but they forget the *why*—architectural decisions, hard-fought bug solutions, and established conventions.

## The Solution
This repository provides a drop-in **Memory Bank** capability for any Antigravity workspace. It leverages **LanceDB** as a fast, embedded vector database and exports all conclusions to a portable `.parquet` file for easy version control and syncing.

When you finish a task, you simply type `/sync`. The agent will summarize its learnings, decisions, and outcomes, and autonomously serialize them into the database securely in the background.

## Features
- **Local-First & Private:** Embedded LanceDB inside your `.agent` folder. No third-party API keys or external SaaS dependencies required.
- **True Autonomy:** Integrates with VS Code/Editor Terminal Allow Lists to execute Python saves seamlessly without triggering security prompts.
- **Git Friendly:** Manually back up memories to `conclusions_backup.parquet` with the `export` command, ensuring your team can share the agent's knowledge through standard pull requests.
- **High Performance FTS:** Leverages LanceDB native full-text search capability (`tantivy` powered) instead of slow Pandas dataframe lookups.
- **Full CRUD Support:** Provides robust `save`, `query`, `update`, and `delete` commands so the agent can continually groom and refine its knowledge.
- **Beautiful Formatting:** Memory query results are printed in easy-to-read Markdown, keeping the AI's terminal context windows organized and parsable.
- **Proven Test Suite:** Includes a full `pytest` suite simulating the agent executing isolated test banks to guarantee stability.

## Quickstart

### 1. Installation
Drop the script into your target project and run it to scaffold the agent skills. You can optionally specify a branch or tag name (defaults to `main`).
```bash
cd /path/to/your/project
curl -sO https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/main/install.sh
chmod +x install.sh
./install.sh v1.0.0
```

### 2. Allow List Configuration
To make the agent fully autonomous, you must add the execution script to your IDE/Editor's **Terminal Command Allow List**. 
The agent auto-executes commands matched by an allow list entry:
- For Unix shells, an allow list entry matches a command if its space-separated tokens form a prefix of the command's tokens. 
- For PowerShell, the entry tokens may match any contiguous subsequence of the command tokens.

Add the following prefix to the allow list:
```text
uv run .agent/skills/memory-manager/bridge.py
```

### 3. Usage
Simply chat with your agent! When you want it to remember something important, say:
- *"Save this architectural decision to your memory bank"*
- Or just type `/sync` to trigger the automatic workflow script.

The agent handles saving (`save`), retrieving (`query`), editing (`update`), and purging (`delete`) its conclusions autonomously. You can also tell the agent to "Snapshot the memory bank" to generate the Parquet file via the `export` command.