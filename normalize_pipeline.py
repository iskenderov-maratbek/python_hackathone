import json, re, time
QUOTED_KEY_RE = re.compile(r'^"(.*)"$')

def try_parse(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v

def clean_keys(d):
    return {
        (QUOTED_KEY_RE.match(k).group(1) if isinstance(k, str) and QUOTED_KEY_RE.match(k) else k): v
        for k, v in d.items()
    }

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

def detect_and_normalize(arguments):
    """
    Returns (mode, payload) where:
      - mode in {"aggregate","find","insert"}
      - payload is canonical: list[dict] for aggregate, dict for find, list|dict for insert
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

    # 2) find-like: presence of hint keys
    if isinstance(args, dict):
        if any(k in args for k in FIND_HINT_KEYS):
            # choose explicit filter if present
            filter_obj = args.get("filter") or args.get("filters") or args.get("query") or {}
            return "find", normalize_find_params(filter_obj, args)

    # 3) find-like: first dict-like value (fallback)
    if isinstance(args, dict):
        for v in args.values():
            v2 = try_parse(v)
            if isinstance(v2, dict):
                return "find", normalize_find_params(v2, args)

    # 4) insert: treat dict as document(s)
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
    """
    filter_obj: dict or JSON string or None
    full_args: dict with optional limit/skip/projection/sort
    Returns canonical dict: {"filter":..., "limit":..., "skip":..., "projection":..., "sort":...}
    """
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
