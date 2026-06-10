import json
import uuid
import logging
try:
    import uvicorn
except ImportError:
    uvicorn = None
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import tools

app = FastAPI()

# -------------------------
# Logging configuration
# -------------------------
# Use a conservative formatter that does not require custom LogRecord attributes
LOG_FORMAT = (
    '{"ts":"%(asctime)s","level":"%(levelname)s","message":%(message)s}'
)
handler = logging.StreamHandler()
formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z")
handler.setFormatter(formatter)
logger = logging.getLogger("mcp_adk")
logger.setLevel(logging.INFO)
logger.handlers = [handler]


def _log(level: str, event: str, message_obj, request_uuid: str = "-", client: str = "-"):
    """
    Unified logger:
      - Serialize message_obj to JSON and emit it as the log message.
      - Keep custom fields in extra so formatting can include them.
    """
    try:
        message_json = json.dumps(message_obj, ensure_ascii=False)
    except Exception:
        message_json = json.dumps({"note": "unserializable message"}, ensure_ascii=False)

    extra = {"event": event, "request_uuid": request_uuid, "client": client}
    if level == "info":
        logger.info(message_json, extra=extra)
    elif level == "warning":
        logger.warning(message_json, extra=extra)
    elif level == "error":
        logger.error(message_json, extra=extra)
    else:
        logger.debug(message_json, extra=extra)


# -------------------------
# Helpers
# -------------------------
def make_error(code: int, message: str, request_id=None) -> dict:
    _log("error", "make_error", {"code": code, "message": message, "id": request_id}, request_uuid=request_id)
    return {
        "jsonrpc": "2.0",
        "id": request_id if request_id is not None else None,
        "error": {"code": code, "message": message}
    }


def handle_tool_call(params: dict, request_id, is_notification: bool, request_uuid, client_addr):
    _log("info", "handle_tool_call.start", {"id": request_id, "notification": is_notification, "params_preview": (params if isinstance(params, dict) else str(type(params)))}, request_uuid, client_addr)

    if not isinstance(params, dict):
        return None if is_notification else make_error(-32602, "Invalid params", request_id)

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    # get_db_schema
    if tool_name == "get_db_schema":
        try:
            text_result = tools.get_db_schema(arguments.get("collection_name"))
        except Exception as e:
            _log("error", "tool_error", {"tool": tool_name, "error": str(e)}, request_uuid, client_addr)
            return None if is_notification else make_error(-32603, str(e), request_id)

        if is_notification:
            _log("info", "tool_notification_ignored", {"tool": tool_name, "id": request_id}, request_uuid, client_addr)
            return None

        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": text_result}]}
        }
        _log("info", "tool_response", {"tool": tool_name, "id": request_id, "response_length": len(text_result)}, request_uuid, client_addr)
        return response

    # execute_mongodb_query
    if tool_name == "execute_mongodb_query":
        if is_notification:
            try:
                tools.execute_mongodb_query(arguments)
                _log("info", "tool_notification_executed", {"tool": tool_name, "arguments_preview": (arguments if isinstance(arguments, dict) else str(type(arguments)))}, request_uuid, client_addr)
            except Exception as e:
                _log("error", "tool_notification_failed", {"tool": tool_name, "error": str(e)}, request_uuid, client_addr)
            return None

        try:
            text_result = tools.execute_mongodb_query(arguments)
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": text_result}]}
            }
            _log("info", "tool_response", {"tool": tool_name, "id": request_id, "response_length": len(text_result)}, request_uuid, client_addr)
            return response
        except Exception as e:
            _log("error", "tool_error", {"tool": tool_name, "error": str(e)}, request_uuid, client_addr)
            return make_error(-32602, str(e), request_id)

    return None if is_notification else make_error(-32601, "Method not found", request_id)


def handle_single_request(body: dict, request_uuid: str, client_addr: str):
    if not isinstance(body, dict):
        _log("warning", "invalid_request_body", {"body_preview": str(type(body))}, request_uuid, client_addr)
        return make_error(-32600, "Invalid Request", None)

    request_id = body.get("id") if "id" in body else None
    is_notification = "id" not in body
    jsonrpc_version = body.get("jsonrpc")
    method = body.get("method")

    _log("info", "incoming_request", {"method": method, "id": request_id, "notification": is_notification}, request_uuid, client_addr)

    if jsonrpc_version != "2.0" or not isinstance(method, str):
        _log("warning", "invalid_jsonrpc_or_method", {"jsonrpc": jsonrpc_version, "method": method}, request_uuid, client_addr)
        return None if is_notification else make_error(-32600, "Invalid Request", request_id)

    if method == "initialize":
        if is_notification:
            _log("info", "initialize_notification", {"id": request_id}, request_uuid, client_addr)
            return None
        tools_manifest = tools.get_tools_manifest()
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "tools": {
                        "manifest": tools_manifest,
                        "names": [t["name"] for t in tools_manifest]
                    }
                },
                "serverInfo": {"name": "municipal-director-mcp", "version": "1.0.0"}
            }
        }
        _log("info", "initialize_response", {"id": request_id, "tools_count": len(tools_manifest)}, request_uuid, client_addr)
        return response

    if method == "tools/list":
        if is_notification:
            _log("info", "tools_list_notification", {"id": request_id}, request_uuid, client_addr)
            return None
        tools_manifest = tools.get_tools_manifest()
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools_manifest}
        }
        _log("info", "tools_list_response", {"id": request_id, "tools_count": len(tools_manifest)}, request_uuid, client_addr)
        return response

    if method == "tools/call":
        params = body.get("params", {})
        return handle_tool_call(params, request_id, is_notification, request_uuid, client_addr)

    _log("warning", "method_not_found", {"method": method, "id": request_id}, request_uuid, client_addr)
    return None if is_notification else make_error(-32601, "Method not found", request_id)


# -------------------------
# Main route
# -------------------------
@app.post("/")
async def mcp_adk_streaming_router(request: Request):
    request_uuid = str(uuid.uuid4())
    client_addr = request.client.host if request.client else "-"
    _log("info", "incoming_http", {"path": str(request.url.path), "method": "POST"}, request_uuid, client_addr)

    print("================================================================================================")
    _log("info", "attempt_read_body", {"note": "Attempting to read JSON body"}, request_uuid, client_addr)

    try:
        body = await request.json()
    except Exception as e:
        _log("error", "parse_error", {"error": str(e)}, request_uuid, client_addr)
        return JSONResponse(content=make_error(-32700, "Parse error", None))

    # Distinguish batch vs single and log each item with notification flag
    if isinstance(body, list):
        _log("info", "batch_request_received", {"count": len(body)}, request_uuid, client_addr)
        for idx, item in enumerate(body):
            is_notification = "id" not in item
            _log("info", "batch_item", {"index": idx, "method": item.get("method"), "id": item.get("id", "<none>"), "notification": is_notification}, request_uuid, client_addr)
    else:
        is_notification = "id" not in body
        _log("info", "single_request_received", {"method": body.get("method"), "id": body.get("id", "<none>"), "params_preview": (body.get("params", {}) if isinstance(body.get("params", {}), dict) else str(type(body.get("params", {})))), "notification": is_notification}, request_uuid, client_addr)

    # Process requests
    if isinstance(body, list):
        if not body:
            _log("warning", "empty_batch", {}, request_uuid, client_addr)
            return JSONResponse(content=make_error(-32600, "Invalid Request", None))

        responses = []
        for item in body:
            response = handle_single_request(item, request_uuid, client_addr)
            if response is not None:
                responses.append(response)

        if not responses:
            _log("info", "no_responses_batch", {}, request_uuid, client_addr)
            return Response(status_code=204)

        _log("info", "batch_responses_ready", {"responses_count": len(responses)}, request_uuid, client_addr)
        return JSONResponse(content=responses)

    response = handle_single_request(body, request_uuid, client_addr)
    if response is None:
        _log("info", "no_response_single", {}, request_uuid, client_addr)
        return Response(status_code=204)

    _log("info", "single_response_ready", {"id": response.get("id")}, request_uuid, client_addr)
    return JSONResponse(content=response)


if __name__ == "__main__":
    if uvicorn is None:
        raise RuntimeError("uvicorn is required to run this module directly. Install it with 'pip install uvicorn'.")
    uvicorn.run(app, host="127.0.0.1", port=8000)
