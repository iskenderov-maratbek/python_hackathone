# tools.py
import json
import logging
import re
from typing import Any, Dict

from config import db, client
from bson.objectid import ObjectId
from normalize_pipeline import (
    detect_and_normalize,
    normalize_pipeline,
    normalize_find_params,
    normalize_insert_doc,
)

# -------------------------
# Logger configuration
# -------------------------
logger = logging.getLogger("mcp_tools")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '{"ts":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
handler.setFormatter(formatter)
logger.handlers = [handler]


def _log(event: str, message_obj: Dict[str, Any], level: str = "info"):
    """
    Унифицированный логгер: сериализует message_obj в JSON и пишет в поток.
    Поля PII должны быть предварительно замаскированы.
    """
    try:
        message_json = json.dumps(message_obj, ensure_ascii=False, default=str)
    except Exception:
        # На случай, если в message_obj есть несерилизуемые объекты
        message_json = json.dumps({"note": "unserializable message"}, ensure_ascii=False)
    extra = {"event": event}
    if level == "info":
        logger.info(message_json, extra=extra)
    elif level == "warning":
        logger.warning(message_json, extra=extra)
    else:
        logger.error(message_json, extra=extra)


# -------------------------
# Helpers
# -------------------------
PII_EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
PII_PHONE_RE = re.compile(r"(\+?\d[\d\-\s]{6,}\d)")


def _mask_pii_in_str(s: str) -> str:
    s = PII_EMAIL_RE.sub(r"\1@***", s)
    s = PII_PHONE_RE.sub("***REDACTED_PHONE***", s)
    return s


def _mask_params(params: Any) -> Any:
    """
    Простая маскировка PII в параметрах запроса.
    Поддерживает dict/list/str/primitive.
    """
    if isinstance(params, dict):
        masked = {}
        for k, v in params.items():
            if k.lower() in ("email", "phone", "contact", "phone_number"):
                masked[k] = "***REDACTED***"
            else:
                masked[k] = _mask_params(v)
        return masked
    if isinstance(params, list):
        return [_mask_params(x) for x in params]
    if isinstance(params, str):
        return _mask_pii_in_str(params)
    return params


# -------------------------
# DB helper functions
# -------------------------
def check_db_health() -> bool:
    try:
        client.admin.command("ping", maxTimeMS=2000)
        _log("db_health", {"status": "ok"}, "info")
        return True
    except Exception as e:
        _log("db_health", {"status": "unreachable", "error": str(e)}, "error")
        return False


# -------------------------
# Tools API
# -------------------------
def get_db_schema(arguments: dict = None) -> str:
    """
    Возвращает JSON-строку с описанием коллекций и правил валидации.
    Не логируем полные схемы в сыром виде — только метаданные и количество коллекций.
    """
    _log("get_db_schema.start", {"note": "Fetching database schema"}, "info")
    try:
        collections = db.list_collection_names()
        full_schema_report = {
            "database_description": "All available collections and their validation rules.",
            "collections": {}
        }

        for coll_name in collections:
            if coll_name.startswith("system."):
                continue

            coll_info = db.command("listCollections", filter={"name": coll_name})
            cursor = coll_info.get("cursor", {}).get("firstBatch", [])

            if cursor:
                options = cursor[0].get("options", {})
                validator = options.get("validator", {})

                # Для безопасности — не логируем полные правила, только факт их наличия и краткую структуру
                validation_summary = "No constraints defined"
                if validator:
                    jschema = validator.get("$jsonSchema", validator)
                    # Составляем краткую сводку: перечислим ключи верхнего уровня
                    if isinstance(jschema, dict):
                        validation_summary = {"top_keys": list(jschema.keys())[:10]}
                    else:
                        validation_summary = "Validator present"

                full_schema_report["collections"][coll_name] = {
                    "validation_rules_summary": validation_summary
                }

        result = json.dumps(full_schema_report, ensure_ascii=False, indent=2)
        _log("get_db_schema.success", {"collections_count": len(full_schema_report["collections"])}, "info")
        return result
    except Exception as e:
        _log("get_db_schema.error", {"error": str(e)}, "error")
        raise


def get_tools_manifest():
    _log("get_tools_manifest", {"note": "Returning tools manifest"}, "info")
    return [
        {
            "name": "get_db_schema",
            "description": "REQUIRED: Call this at the very beginning of every new request to retrieve the full database map (all collections and their structures).",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "execute_mongodb_query",
            "description": "Execute MongoDB operations on any collection. Always call get_db_schema first to verify the collection name and structure.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "The name of the collection. Use a name discovered via get_db_schema."
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["find", "aggregate", "insert", "update"]
                    },
                    "query_params": {
                        "type": "object",
                        "description": "The operation payload. Use standard MongoDB query syntax."
                    }
                },
                "required": ["collection_name", "operation", "query_params"]
            }
        }
    ]


def execute_mongodb_query(arguments: dict) -> str:
    """
    Универсальная точка выполнения MongoDB операций.
    Возвращает JSON-строку с результатом или ошибкой.
    Логи минимальны: маскируем PII и логируем только метаданные (counts, status).
    """
    masked_args = _mask_params(arguments)
    _log("execute_mongodb_query.start", {"arguments_preview": {"collection_name": masked_args.get("collection_name"), "operation": masked_args.get("operation")}}, "info")

    # Явно берём params — это то, что нужно передать детектору/нормализаторам
    params = arguments.get("query_params", {}) or {}

    # --- Нормализация / детекция входа ---
    try:
        # detect_and_normalize ожидает структуру с параметрами операции
        mode, payload = detect_and_normalize(params)
    except ValueError as e:
        _log("execute_mongodb_query.invalid_input", {"error": str(e)}, "warning")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # логируем кратко результат детекции
    _log("execute_mongodb_query.detected", {"detected_mode": mode, "payload_type": str(type(payload))}, "info")

    # Если клиент явно указал operation, используем его как hint, но payload остаётся нормализованным
    coll_name = arguments.get("collection_name")
    operation = arguments.get("operation")  # может быть None, тогда используем mode

    # Если operation задан и не совпадает с детектированным mode — логируем предупреждение, но всё равно пытаемся выполнить
    if operation and operation != mode:
        _log("execute_mongodb_query.operation_mismatch", {"declared": operation, "detected": mode}, "warning")

    # выбираем фактический режим выполнения: предпочитаем declared operation, иначе детектированный
    exec_mode = operation if operation else mode

    allowed_collections = ["employees", "expenses", "contracts", "tasks"]
    if coll_name not in allowed_collections:
        msg = f"Collection '{coll_name}' is not authorized."
        _log("execute_mongodb_query.unauthorized", {"collection": coll_name}, "warning")
        return f"Error: {msg}"

    collection = db[coll_name]

    try:
        # -------------------------
        # AGGREGATE
        # -------------------------
        if exec_mode == "aggregate":
            if not isinstance(payload, list):
                # попытка восстановить pipeline из raw params
                try:
                    pipeline = normalize_pipeline(params.get("pipeline", params))
                    payload = pipeline
                    _log("execute_mongodb_query.recovered", {"note": "normalized pipeline from raw params"}, "warning")
                except Exception as e:
                    _log("aggregate.invalid_payload", {"type": str(type(payload)), "error": str(e)}, "warning")
                    return json.dumps({"status": "error", "message": "Invalid pipeline format"}, ensure_ascii=False)

            pipeline = payload
            _log("aggregate.query", {"collection": coll_name, "pipeline_preview": pipeline[:2], "stages_count": len(pipeline)}, "info")
            data = list(collection.aggregate(pipeline))
            _log("aggregate.result", {"collection": coll_name, "returned": len(data)}, "info")
            return json.dumps(data, ensure_ascii=False, default=str)

        # -------------------------
        # FIND
        # -------------------------
        elif exec_mode == "find":
            if not isinstance(payload, dict):
                try:
                    # normalize_find_params expects (filter_obj, full_args)
                    filter_obj = params.get("filter") if isinstance(params, dict) and "filter" in params else ({} if not isinstance(params, dict) else {})
                    payload = normalize_find_params(filter_obj, params if isinstance(params, dict) else {})
                    _log("execute_mongodb_query.recovered", {"note": "normalized find params from raw params"}, "warning")
                except Exception as e:
                    _log("find.invalid_payload", {"type": str(type(payload)), "error": str(e)}, "warning")
                    return json.dumps({"status": "error", "message": "Invalid payload for find"}, ensure_ascii=False)

            # payload — normalized find params: {"filter":..., "limit":..., "skip":..., "projection":..., "sort":...}
            query = payload.get("filter", {})
            limit = int(payload.get("limit", 20))
            skip = int(payload.get("skip", 0))
            projection = payload.get("projection", None)
            sort = payload.get("sort", None)

            _log("find.query", {"collection": coll_name, "filter_preview": _mask_params(query), "limit": limit, "skip": skip}, "info")

            cursor = collection.find(query, projection)
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)

            data = list(cursor)
            _log("find.result", {"collection": coll_name, "returned": len(data)}, "info")
            return json.dumps(data, ensure_ascii=False, default=str)

        # -------------------------
        # INSERT
        # -------------------------
        elif exec_mode == "insert":
            # payload должен быть dict или list
            docs = payload
            if not isinstance(docs, (dict, list)):
                try:
                    docs = normalize_insert_doc(params)
                    _log("execute_mongodb_query.recovered", {"note": "normalized insert docs from raw params"}, "warning")
                except Exception as e:
                    _log("insert.invalid_payload", {"type": str(type(payload)), "error": str(e)}, "warning")
                    return json.dumps({"status": "error", "message": "Invalid insert payload"}, ensure_ascii=False)

            # теперь docs — либо dict, либо list
            if isinstance(docs, dict):
                doc = docs
                _log("insert.attempt", {"collection": coll_name, "doc_keys": list(doc.keys())[:10]}, "info")
                result = collection.insert_one(doc)
                _log("insert.success", {"collection": coll_name, "inserted_id": str(result.inserted_id)}, "info")
                return json.dumps({"status": "success", "inserted_id": str(result.inserted_id)}, ensure_ascii=False)
            elif isinstance(docs, list):
                if len(docs) == 0:
                    return json.dumps({"status": "error", "message": "No documents to insert"}, ensure_ascii=False)
                if len(docs) == 1:
                    doc = docs[0]
                    _log("insert.attempt", {"collection": coll_name, "doc_keys": list(doc.keys())[:10]}, "info")
                    result = collection.insert_one(doc)
                    _log("insert.success", {"collection": coll_name, "inserted_id": str(result.inserted_id)}, "info")
                    return json.dumps({"status": "success", "inserted_id": str(result.inserted_id)}, ensure_ascii=False)
                else:
                    _log("insert.attempt_many", {"collection": coll_name, "docs_count": len(docs)}, "info")
                    result = collection.insert_many(docs)
                    inserted = [str(x) for x in result.inserted_ids]
                    _log("insert.success_many", {"collection": coll_name, "inserted_count": len(inserted)}, "info")
                    return json.dumps({"status": "success", "inserted_ids": inserted}, ensure_ascii=False)
            else:
                _log("insert.invalid_payload", {"type": str(type(docs))}, "warning")
                return json.dumps({"status": "error", "message": "Invalid insert payload"}, ensure_ascii=False)

        # -------------------------
        # UPDATE
        # -------------------------
        elif exec_mode == "update":
            # payload — ожидаем canonical: {"filter": {...}, "update": {...}} или {"_id": "...", "update": {...}} или похожая структура
            update_payload = payload
            if not isinstance(update_payload, dict):
                _log("update.invalid_payload_type", {"type": str(type(update_payload))}, "warning")
                return json.dumps({"status": "error", "message": "Invalid payload for update"}, ensure_ascii=False)

            _log("update.attempt", {"collection": coll_name, "params_preview": _mask_params(update_payload)}, "info")

            # Попытка извлечь _id
            task_id = update_payload.get("_id") or (update_payload.get("filter") or {}).get("_id")
            update_data = update_payload.get("update") or {k: v for k, v in update_payload.items() if k not in ["_id", "filter", "update", "collection_name", "operation"]}

            if not task_id and not update_payload.get("filter"):
                _log("update.missing_id_or_filter", {"collection": coll_name}, "warning")
                return json.dumps({"status": "error", "message": "Missing _id or filter"}, ensure_ascii=False)

            # Если указан filter вместо _id, используем его
            if update_payload.get("filter") and not task_id:
                filter_doc = update_payload.get("filter")
            else:
                try:
                    oid = ObjectId(task_id)
                    filter_doc = {"_id": oid}
                except Exception:
                    _log("update.invalid_id", {"provided_id": str(task_id)}, "warning")
                    return json.dumps({"status": "error", "message": "Invalid _id format"}, ensure_ascii=False)

            # Выполняем обновление и логируем только счётчики
            result = collection.update_one(filter_doc, {"$set": update_data})
            _log("update.result", {"collection": coll_name, "matched": result.matched_count, "modified": result.modified_count}, "info")
            return json.dumps({"status": "success", "matched": result.matched_count, "modified": result.modified_count}, ensure_ascii=False)

        else:
            _log("execute_mongodb_query.unsupported", {"operation": exec_mode}, "warning")
            return f"Error: Unsupported operation '{exec_mode}'"

    except Exception as e:
        # Логируем ошибку, но не раскрываем чувствительные данные
        _log("execute_mongodb_query.error", {"collection": coll_name, "operation": exec_mode, "error": str(e)}, "error")
        return f"Error: {str(e)}"
