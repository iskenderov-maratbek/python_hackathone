# MongoDB Agent Hackathon Project

This repository contains a Python-based JSON-RPC 2.0 microservice built for a hackathon agent submission. It demonstrates a backend agent pattern with MongoDB integration, tool execution, structured logging, and a partner-ready MCP-style architecture.

## Project Overview

This project is a FastAPI application that exposes a JSON-RPC 2.0 interface for agent-style tool calls. 
The service provides:

- JSON-RPC 2.0 support over HTTP POST
- standard JSON-RPC methods: `initialize`, `tools/list`, and `tools/call`
- two main tool implementations:
  - `get_db_schema` — returns collection structure and validation metadata
  - `execute_mongodb_query` — executes MongoDB operations such as `find`, `aggregate`, `insert`, and `update`
- structured logs for request tracing and tool execution behavior

## Hackathon Context

This project is built for a hackathon where the goal is to create agents that do more than chat. It is especially suitable for a partner track that uses MongoDB as a backend service and integrates with a Model Context Protocol (MCP)-style architecture.

### Partner Track

This submission is aligned with the **MongoDB** partner track and demonstrates a practical integration with MongoDB collections and query execution. It is designed as a backend service for an agent that can reason, plan, and execute data operations.

## Key Files

- `main.py` — FastAPI app and JSON-RPC router
- `tools.py` — tool logic for MongoDB operations and secure logging
- `config.py` — MongoDB connection configuration and collection references
- `normalize_pipeline.py` — request normalization helpers for pipeline and query parameters
- `requirements.txt` — project dependencies

## Tech Stack

- Python 3.x
- FastAPI
- Uvicorn
- PyMongo
- MongoDB

## Installation

Install dependencies from `requirements.txt`:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Running the Service

Start the service directly:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe main.py
```

Or run with Uvicorn for local development:

```bash
c:/Users/king/Documents/projects/python_hackathone/.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## JSON-RPC Usage Examples

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

## Architecture Notes

- The server is built on JSON-RPC 2.0 and returns one response per request.
- Batch requests are supported by collecting individual responses into a single JSON array.
- Notifications are supported and do not return a response.
- Tool processing runs synchronously inside FastAPI routes, so the client receives the final result after execution completes.

## Hackathon Alignment

This project meets key hackathon goals:

- **Beyond chat**: the backend performs real tool execution and database operations
- **Multi-step capability**: the agent can plan and run workflows through JSON-RPC tool calls
- **Partner integration**: demonstrates MongoDB partner alignment and MCP-style tool execution

## Security and Deployment Notes

- `config.py` contains a MongoDB connection string. For production or public submission, move secrets to environment variables or a secure vault.
- This repository is designed as a hackathon submission and can be extended with additional MCP or partner-specific features.