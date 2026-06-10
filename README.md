# MongoDB Agent Hackathon Project

Backend that demonstrates a JSON-RPC 2.0 agent service built on FastAPI and MongoDB. This project is tailored for an MCP-enabled agent architecture and aligns with the MongoDB partner track.

## Project Summary

This service exposes a JSON-RPC 2.0 interface for agent-driven tool execution. It is designed to operate as the backend for a task-oriented agent that can:

- discover database schema metadata
- execute MongoDB queries and updates
- handle tool requests via a standard JSON-RPC pipeline
- provide structured logs for traceability

## What the Project Does

The application supports the following flows:

- `initialize` — basic handshake for agent startup
- `tools/list` — returns the available tool manifest
- `tools/call` — invokes a tool with structured arguments
- `get_db_schema` — returns a safe summary of MongoDB collections and validation rules
- `execute_mongodb_query` — performs `find`, `aggregate`, `insert`, and `update` operations on authorized collections

## Why This Fits the Hackathon

This implementation is built for the agent challenge by focusing on:

- **Actionable intelligence** — not just answers, but tool execution
- **Partner integration** — MongoDB serves as the backend and partner data service
- **Multi-step operations** — the agent can sequence database discovery and execution
- **MCP-style compatibility** — supports a tool manifest and request/response model for agent orchestration

## Key Files

- `main.py` — FastAPI JSON-RPC endpoint, request routing, and logging
- `tools.py` — implementation of tool actions and MongoDB operations
- `config.py` — MongoDB client configuration and collection access
- `normalize_pipeline.py` — normalization helpers for query payloads and aggregation pipelines
- `requirements.txt` — dependency list for the Python environment

## Supported MongoDB Operations

`execute_mongodb_query` supports:

- `find` — query documents with filter, sort, skip, limit, and projection
- `aggregate` — run MongoDB aggregation pipelines
- `insert` — insert a single document or a batch of documents
- `update` — update documents by `_id` or by explicit filter

## Installation

Install the required packages:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Running the Service

Start the application directly:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe main.py
```

Or run with Uvicorn:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Example JSON-RPC Requests

### Initialize the agent

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

### List available tools

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

### Call `get_db_schema`

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_db_schema",
    "arguments": {}
  }
}
```

### Call `execute_mongodb_query`

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "execute_mongodb_query",
    "arguments": {
      "collection_name": "expenses",
      "operation": "find",
      "query_params": {
        "filter": {},
        "limit": 10
      }
    }
  }
}
```

## Architectural Highlights

### Dynamic Data Integration
Unlike static agent implementations that require hardcoded schema definitions, our agent utilizes **Dynamic Schema Discovery**.  
Upon initialization, the agent retrieves the current database structure, allowing seamless integration of new collections and fields without requiring manual updates to the MCP server manifest or core logic.  

This ensures maximum scalability for growing municipal datasets.



