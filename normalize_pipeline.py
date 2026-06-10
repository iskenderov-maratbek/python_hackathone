import json, re, time
QUOTED_KEY_RE = re.compile(r'^"(.*)"$')

def try_parse(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v

def normalize_key(k):
    if not isinstance(k, str):
        return k

    m = QUOTED_KEY_RE.match(k)
    if m:
        k = m.group(1)

    # remove leading/trailing dashes from quoted/hyphenated keys
    k = re.sub(r'^-+|-+$', '', k)
    return k


def clean_keys(d):
    normalized = {}
    for k, v in d.items():
        nk = normalize_key(k)
        if nk in normalized and nk != k:
            # preserve original key when normalization would collide with an existing key
            normalized[k] = v
        else:
            normalized[nk] = v
    return normalized


def looks_like_pipeline(x):
    # list of stages where first stage has $-operator keys
    if isinstance(x, list) and x and isinstance(x[0], dict):
        return any(str(k).startswith("$") for k in x[0].keys())
    # indexed dict {"0": {...}, "1": {...}} -> pipeline
    if isinstance(x, dict) and all(isinstance(k, str) and k.isdigit() for k in x.keys()):
        return True
    return False

def preprocess(args):
    # parse strings, unwrap single-element containers
    if isinstance(args, str):
        args = try_parse(args)
    return args

# Hint keys that indicate a find-like payload
FIND_HINT_KEYS = {"filter", "filters", "query", "limit", "skip", "sort", "projection"}

# Explicit find parameters (distinguish from bare filter which could be delete or find)
EXPLICIT_FIND_PARAMS = {"limit", "skip", "sort", "projection"}


# Hint keys that indicate an update payload
UPDATE_HINT_KEYS = {"update", "filter"}

def normalize_update_params(update_obj, full_args):
    update_parsed = try_parse(update_obj) if update_obj is not None else {}
    if not isinstance(update_parsed, dict):
        raise ValueError("Update payload must be an object")

    # allow `query` as an alias for filter in update payloads
    filter_obj = update_parsed.get("filter") or update_parsed.get("query") or {}
    if isinstance(filter_obj, str):
        filter_obj = try_parse(filter_obj) if filter_obj else {}

    update_doc = update_parsed.get("update")
    if update_doc is None:
        update_doc = {
            k: v
            for k, v in update_parsed.items()
            if k not in ["filter", "query", "_id", "collection_name", "operation"]
        }

    if not isinstance(update_doc, dict) or not update_doc:
        raise ValueError("Update payload must include a non-empty update object")

    return {"filter": filter_obj, "update": update_doc}

def normalize_delete_params(delete_obj, full_args):
    delete_parsed = try_parse(delete_obj) if delete_obj is not None else {}
    if not isinstance(delete_parsed, dict):
        raise ValueError("Delete payload must be an object")

    # allow `query` as an alias for filter in delete payloads
    filter_obj = delete_parsed.get("filter") or delete_parsed.get("query") or {}
    if isinstance(filter_obj, str):
        filter_obj = try_parse(filter_obj) if filter_obj else {}

    if not filter_obj:
        raise ValueError("Delete payload must include a non-empty filter")

    return {"filter": filter_obj}

def detect_and_normalize(arguments):
    """
    Returns (mode, payload) where:
      - mode in {"aggregate","find","insert","update"}
      - payload is canonical: list[dict] for aggregate, dict for find, list|dict for insert, dict for update
      - NOTE: delete is NOT auto-detected; must be specified via operation="delete" in tools.py
    """
    args = preprocess(arguments)

    # 1) pipeline anywhere
    if looks_like_pipeline(args):
        return "aggregate", normalize_pipeline(args)

    if isinstance(args, dict):
        # pipeline nested in values
        for v in args.values():
            v2 = try_parse(v)
            if looks_like_pipeline(v2):
                return "aggregate", normalize_pipeline(v2)

    # 2) update-like: presence of update key
    if isinstance(args, dict) and "update" in args:
        return "update", normalize_update_params(args, args)

    # 3) find-like: presence of any hint key (filter, query, limit, sort, skip, projection)
    if isinstance(args, dict):
        if any(k in args for k in FIND_HINT_KEYS):
            # choose explicit filter if present
            filter_obj = args.get("filter") or args.get("filters") or args.get("query") or {}
            return "find", normalize_find_params(filter_obj, args)

    # 4) find-like: first dict-like value (fallback)
    if isinstance(args, dict):
        for v in args.values():
            v2 = try_parse(v)
            if isinstance(v2, dict):
                return "find", normalize_find_params(v2, args)

    # 5) insert: treat dict as document(s)
    if isinstance(args, dict):
        return "insert", normalize_insert_doc(args)

    raise ValueError("Не распознано: пришлите pipeline (aggregate) или объект фильтра/документа")

def normalize_pipeline(raw):
    p = try_parse(raw)
    # indexed dict -> list
    if isinstance(p, dict) and all(isinstance(k, str) and k.isdigit() for k in p.keys()):
        p = [p[k] for k in sorted(p.keys(), key=int)]
    # single dict -> single-stage pipeline
    if isinstance(p, dict):
        p = [p]
    if not isinstance(p, list):
        raise ValueError("Pipeline must be a list or indexed dict")
    cleaned = []
    for s in p:
        s = try_parse(s)
        if not isinstance(s, dict):
            raise ValueError("Stage must be object")
        cleaned.append(clean_keys(s))
    return cleaned

def normalize_find_params(filter_obj, full_args):
    # parse filter_obj if it's a string
    filter_parsed = try_parse(filter_obj) if filter_obj is not None else {}
    if not isinstance(filter_parsed, dict):
        # if filter is not a dict, treat as empty filter
        filter_parsed = {}

    # extract control params from full_args without mixing them into filter
    try:
        limit = int(full_args.get("limit", 20)) if "limit" in full_args else 20
    except Exception:
        limit = 20
    try:
        skip = int(full_args.get("skip", 0)) if "skip" in full_args else 0
    except Exception:
        skip = 0
    proj = try_parse(full_args.get("projection")) if "projection" in full_args else None
    sort = try_parse(full_args.get("sort")) if "sort" in full_args else None

    return {"filter": filter_parsed, "limit": limit, "skip": skip, "projection": proj, "sort": sort}

def normalize_insert_doc(doc):
    # minimal: ensure dict or list of dicts
    if isinstance(doc, dict):
        return [doc]
    if isinstance(doc, list) and all(isinstance(x, dict) for x in doc):
        return doc
    raise ValueError("Insert expects object or list of objects")
