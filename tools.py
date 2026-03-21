"""
Tools for querying ISTAT (Istituto Nazionale di Statistica) open data
via the SDMX REST API.

No authentication required — the API is fully public.

RATE LIMIT: STRICT — 5 requests per minute per IP.
Exceeding this triggers a block of 1-2 days. All HTTP calls go through
_rate_limited_get() which enforces this limit.
"""

import csv
import io
import threading
import time
import xml.etree.ElementTree as ET

import httpx

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"

# SDMX 2.1 XML namespaces
NS_STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
NS_COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
NS_MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"

# Accept headers
ACCEPT_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"

# ─────────────────────────────────────────────
# Rate limiter (5 req / 60 sec)
# ─────────────────────────────────────────────

_last_request_times: list[float] = []
_rate_lock = threading.Lock()
RATE_LIMIT = 5  # requests per minute


def _rate_limited_get(
    url: str,
    headers: dict = None,
    params: dict = None,
) -> httpx.Response:
    """
    Make a rate-limited GET request. Max 5 requests/minute.

    Sleeps as needed to stay within the ISTAT rate limit.
    Logs any sleep so the operator can see throttling.
    """
    with _rate_lock:
        now = time.time()
        # Drop timestamps older than 60 seconds
        _last_request_times[:] = [t for t in _last_request_times if now - t < 60]

        if len(_last_request_times) >= RATE_LIMIT:
            sleep_time = 60 - (now - _last_request_times[0]) + 0.1
            if sleep_time > 0:
                print(
                    f"[ISTAT rate limit] Sleeping {sleep_time:.1f}s to respect 5 req/min cap"
                )
                time.sleep(sleep_time)

        _last_request_times.append(time.time())

    # SSL verify=False: ISTAT cert sometimes causes issues
    with httpx.Client(timeout=120.0, follow_redirects=True, verify=False) as client:
        return client.get(url, headers=headers or {}, params=params)


# ─────────────────────────────────────────────
# Caches
# ─────────────────────────────────────────────

_dataflow_cache: list[dict] | None = None
_dataflow_cache_time: float = 0.0
_CACHE_TTL = 86400  # 24 hours

_structure_cache: dict[str, tuple[dict, float]] = {}  # key: dataflow_id
_codelist_cache: dict[str, tuple[list, float]] = {}   # key: codelist_id


def _get_dataflows() -> list[dict]:
    """
    Fetch and cache the full list of ISTAT dataflows (~4700 datasets).

    Refreshes at most once per 24 hours to avoid burning rate-limit quota.
    Returns list of {"id": str, "names": {"en": str, "it": str}} dicts.
    """
    global _dataflow_cache, _dataflow_cache_time

    now = time.time()
    if _dataflow_cache is not None and (now - _dataflow_cache_time) < _CACHE_TTL:
        return _dataflow_cache

    print("[ISTAT] Fetching full dataflow list (cached for 24h)…")
    url = f"{BASE_URL}/dataflow/IT1"
    try:
        resp = _rate_limited_get(url, headers={"Accept": "application/xml"})
        resp.raise_for_status()
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        print(f"[ISTAT] Failed to fetch dataflows: {exc}")
        return _dataflow_cache or []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        print(f"[ISTAT] XML parse error on dataflow list: {exc}")
        return _dataflow_cache or []

    flows = []
    # <str:Dataflows> → <str:Dataflow id="..."> → <com:Name xml:lang="...">
    for df in root.iter(f"{{{NS_STRUCTURE}}}Dataflow"):
        df_id = df.get("id", "")
        names: dict[str, str] = {}
        for name_el in df.iter(f"{{{NS_COMMON}}}Name"):
            lang = name_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang and name_el.text:
                names[lang] = name_el.text.strip()
        if df_id:
            flows.append({"id": df_id, "names": names})

    _dataflow_cache = flows
    _dataflow_cache_time = now
    print(f"[ISTAT] Cached {len(flows)} dataflows")
    return flows


# ─────────────────────────────────────────────
# Tool 1 — search_datasets
# ─────────────────────────────────────────────


def search_datasets(query: str, lang: str = "en") -> dict:
    """
    Search ISTAT datasets by keyword. Call this automatically whenever the user asks
    about any Italian statistic — do not ask for permission first.
    Returns up to 30 results with dataset IDs needed for the next steps.

    SEARCH TIPS — many ISTAT datasets only have Italian names. Try:
    - English first, then Italian if no results (e.g. 'population' → 'popolazione')
    - Common translations: population=popolazione, employment=occupazione,
      unemployment=disoccupazione, births=natalità/nascite, deaths=mortalità/decessi,
      income=reddito, GDP=PIL, housing=abitazioni, crime=delitti, school=scuole,
      health=salute/sanità, waste=rifiuti, tourism=turismo, agriculture=agricoltura
    - Multi-word queries match ALL words (AND logic), order doesn't matter

    args:
        query: Keywords to search for (e.g. 'population', 'tasso occupazione')
        lang: Language for dataset names, 'it' or 'en' (default: 'en')

    returns:
        Dict with total_results, results list, and search tips if no matches
    """
    try:
        flows = _get_dataflows()
    except Exception as exc:
        return {"error": "Failed to retrieve dataset list", "details": str(exc)}

    # Split query into words — ALL must match (AND logic)
    query_words = query.lower().split()
    results = []

    for flow in flows:
        names = flow.get("names", {})
        # Search across BOTH languages for better recall
        en_name = (names.get("en") or "").lower()
        it_name = (names.get("it") or "").lower()
        search_text = f"{en_name} {it_name}"

        if all(word in search_text for word in query_words):
            display_name = names.get(lang) or names.get("it") or names.get("en") or ""
            results.append({"id": flow["id"], "name": display_name})
        if len(results) >= 30:
            break

    response: dict = {
        "query": query,
        "total_results": len(results),
        "results": results,
    }

    if not results:
        response["tip"] = (
            "No datasets matched. Try: (1) Italian keywords — e.g. 'popolazione' "
            "instead of 'population'; (2) shorter/broader terms — e.g. 'occupaz' "
            "instead of 'employment rate'; (3) single keyword instead of a phrase."
        )

    return response


# ─────────────────────────────────────────────
# Tool 2 — get_dataset_structure
# ─────────────────────────────────────────────


def get_dataset_structure(dataflow_id: str) -> dict:
    """
    Get the structure of a specific ISTAT dataset: its dimensions and their codelist IDs.
    Call this immediately after search_datasets — do not ask the user first.
    Then call get_dimension_values for each dimension you need codes for.
    Results are cached — subsequent calls for the same dataset cost 0 API calls.

    args:
        dataflow_id: The dataset ID from search_datasets (e.g. '22_289')

    returns:
        Dict with dataset name, structure_id, and list of dimensions (id, position, name, codelist_id)
    """
    now = time.time()
    if dataflow_id in _structure_cache:
        cached, ts = _structure_cache[dataflow_id]
        if now - ts < _CACHE_TTL:
            return cached

    # ?references=children returns dataflow + DSD structure (17KB) without
    # embedding full codelist content (?references=all would be 9.5MB+).
    url = f"{BASE_URL}/dataflow/IT1/{dataflow_id}"
    try:
        resp = _rate_limited_get(
            url,
            headers={"Accept": "application/xml"},
            params={"references": "children"},
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {"error": "Request timed out fetching dataflow", "dataflow_id": dataflow_id}
    except httpx.HTTPError as exc:
        return {"error": f"HTTP error: {exc}", "dataflow_id": dataflow_id}

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        return {"error": f"XML parse error: {exc}", "dataflow_id": dataflow_id}

    # Extract dataset name from Dataflow element
    dataset_name = dataflow_id
    structure_id = ""
    for df_el in root.iter(f"{{{NS_STRUCTURE}}}Dataflow"):
        # Prefer English name
        for name_el in df_el.iter(f"{{{NS_COMMON}}}Name"):
            lang = name_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang == "en" and name_el.text:
                dataset_name = name_el.text.strip()
                break
        # Fall back to Italian if no English name found
        if dataset_name == dataflow_id:
            for name_el in df_el.iter(f"{{{NS_COMMON}}}Name"):
                if name_el.text:
                    dataset_name = name_el.text.strip()
                    break
        # Extract structure reference (Ref has no XML namespace)
        for struct_el in df_el.iter(f"{{{NS_STRUCTURE}}}Structure"):
            ref = struct_el.find("Ref")
            if ref is not None:
                structure_id = ref.get("id", "")

    # Extract dimensions from embedded DataStructure
    dimensions = []
    for dsd_el in root.iter(f"{{{NS_STRUCTURE}}}DataStructure"):
        if not structure_id:
            structure_id = dsd_el.get("id", "")
        for dim_el in dsd_el.iter(f"{{{NS_STRUCTURE}}}Dimension"):
            dim_id = dim_el.get("id", "")
            dim_pos = int(dim_el.get("position", 0))

            # Get dimension name from ConceptIdentity
            # Note: <Ref> tag has no XML namespace
            dim_name = dim_id
            for concept_ref in dim_el.iter(f"{{{NS_STRUCTURE}}}ConceptIdentity"):
                ref = concept_ref.find("Ref")
                if ref is not None:
                    concept_name = ref.get("id", "")
                    if concept_name:
                        dim_name = concept_name

            # Get codelist ID from Enumeration
            # Note: <Ref> tag inside <Enumeration> has no XML namespace
            codelist_id = ""
            for enum_el in dim_el.iter(f"{{{NS_STRUCTURE}}}Enumeration"):
                ref = enum_el.find("Ref")
                if ref is not None:
                    codelist_id = ref.get("id", "")

            if dim_id and dim_pos:  # skip empty entries from ?references=children
                dimensions.append({
                    "id": dim_id,
                    "position": dim_pos,
                    "name": dim_name,
                    "codelist_id": codelist_id,
                })

    # Sort by position
    dimensions.sort(key=lambda d: d["position"])

    if not dimensions:
        return {
            "error": "No dimensions found — dataset may not exist or structure is non-standard",
            "dataflow_id": dataflow_id,
        }

    # Build key_filter template so the agent knows exactly how many dots
    template_parts = []
    for dim in dimensions:
        template_parts.append(f"<{dim['id']}>")
    key_template = ".".join(template_parts)

    result = {
        "dataflow_id": dataflow_id,
        "structure_id": structure_id,
        "dataset_name": dataset_name,
        "dimension_count": len(dimensions),
        "dimensions": dimensions,
        "key_filter_template": key_template,
        "note": (
            f"Dataset has {len(dimensions)} dimensions. "
            f"Key filter template: {key_template} — replace <DIM> with a code or leave empty for wildcard. "
            "IMPORTANT: To avoid huge responses, pin as many dimensions as possible. "
            "Use get_dimension_values to find codes for 'total' or 'all ages' rather than wildcarding. "
            "Example: 'A.037006.1.9.TOTAL.99' is much better than 'A.037006.....' "
            "(the latter returns thousands of rows for every sex×age×status combination)."
        ),
    }

    _structure_cache[dataflow_id] = (result, now)
    return result


# ─────────────────────────────────────────────
# Tool 3 — get_dimension_values
# ─────────────────────────────────────────────


def get_dimension_values(
    dataflow_id: str,
    dimension_id: str,
    search: str = None,
    max_results: int = 50,
) -> dict:
    """
    Look up valid codes for a specific dimension of an ISTAT dataset.
    Always call this for REF_AREA before fetching data — never guess territory codes.
    Also call this for SEX, AGE, DATA_TYPE to find 'total'/'all' codes for dimension
    pinning (critical to avoid getting thousands of rows back from get_dataset_data).

    Common searches for finding totals:
    - SEX: search='total' → usually code '9' or 'T'
    - AGE: search='total' → usually code 'TOTAL' or 'Y_GE15'
    - DATA_TYPE: search='total' or search='population' or search='rate'

    Codelist results are cached — repeated calls cost 0 API calls.

    args:
        dataflow_id: Dataset ID (e.g. '22_289')
        dimension_id: Dimension ID from get_dataset_structure (e.g. 'REF_AREA', 'SEX', 'AGE')
        search: Substring to filter codes by name (case-insensitive, e.g. 'Bologna', 'total')
        max_results: Max codes to return when no search filter (default 50)

    returns:
        Dict with dimension_id, codelist_id, total_codes, returned, and list of {code, name}
    """
    # Step 1: get structure (cached after first call)
    structure = get_dataset_structure(dataflow_id)
    if "error" in structure:
        return {"error": f"Could not get dataset structure: {structure['error']}"}

    # Step 2: find the codelist_id for the requested dimension
    codelist_id = None
    for dim in structure.get("dimensions", []):
        if dim["id"].upper() == dimension_id.upper():
            codelist_id = dim.get("codelist_id", "")
            dimension_id = dim["id"]  # normalise case
            break

    if codelist_id is None:
        available = [d["id"] for d in structure.get("dimensions", [])]
        return {
            "error": f"Dimension '{dimension_id}' not found in dataset {dataflow_id}",
            "available_dimensions": available,
        }

    if not codelist_id:
        return {
            "error": f"Dimension '{dimension_id}' has no associated codelist (may use inline enumeration)",
            "dimension_id": dimension_id,
        }

    # Step 3: check codelist cache
    now = time.time()
    if codelist_id in _codelist_cache:
        cached_codes, ts = _codelist_cache[codelist_id]
        if now - ts < _CACHE_TTL:
            return _filter_codes(dimension_id, codelist_id, cached_codes, search, max_results)

    # Step 4: fetch codelist from ISTAT API
    url = f"{BASE_URL}/codelist/IT1/{codelist_id}"
    try:
        resp = _rate_limited_get(url, headers={"Accept": "application/xml"})
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {"error": f"Request timed out fetching codelist {codelist_id}"}
    except httpx.HTTPError as exc:
        return {"error": f"HTTP error fetching codelist {codelist_id}: {exc}"}

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        return {"error": f"XML parse error on codelist: {exc}"}

    # Step 5: parse Code elements
    codes = []
    for code_el in root.iter(f"{{{NS_STRUCTURE}}}Code"):
        code_id = code_el.get("id", "")
        if not code_id:
            continue
        en_name = ""
        it_name = ""
        for name_el in code_el:
            if name_el.tag == f"{{{NS_COMMON}}}Name":
                lang = name_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                text = (name_el.text or "").strip()
                if lang == "en":
                    en_name = text
                elif lang == "it":
                    it_name = text
        name = en_name or it_name or code_id
        codes.append({"code": code_id, "name": name})

    if not codes:
        return {
            "error": f"Codelist {codelist_id} returned 0 codes — may be empty or non-standard",
            "dimension_id": dimension_id,
            "codelist_id": codelist_id,
        }

    # Cache the full list
    _codelist_cache[codelist_id] = (codes, now)

    return _filter_codes(dimension_id, codelist_id, codes, search, max_results)


def _filter_codes(
    dimension_id: str,
    codelist_id: str,
    all_codes: list[dict],
    search: str,
    max_results: int,
) -> dict:
    """Apply search filter and max_results cap, return structured result."""
    if search:
        search_lower = search.lower()
        filtered = [c for c in all_codes if search_lower in c["name"].lower() or search_lower in c["code"].lower()]
    else:
        filtered = all_codes

    total = len(all_codes)
    matched = len(filtered)
    returned = filtered[:max_results]

    note = None
    if search and matched == 0:
        note = (
            f"No codes matched '{search}'. "
            f"Try a broader term or call without search to browse all {total} codes."
        )
    elif not search and total > max_results:
        note = (
            f"Showing first {max_results} of {total} codes. "
            f"Use search parameter to filter by name."
        )

    result = {
        "dimension_id": dimension_id,
        "codelist_id": codelist_id,
        "total_codes": total,
        "returned": len(returned),
        "codes": returned,
    }
    if note:
        result["note"] = note
    if search:
        result["search"] = search
        result["matched"] = matched
    return result


# ─────────────────────────────────────────────
# Tool 4 — get_dataset_data
# ─────────────────────────────────────────────


def get_dataset_data(
    dataflow_id: str,
    last_n_observations: int = 5,
    start_period: str = None,
    end_period: str = None,
    key_filter: str = None,
) -> dict:
    """
    Fetch data from an ISTAT dataset. Call this as the final step after looking up
    codes with get_dimension_values. NEVER guess codes — always look them up first.

    CRITICAL: Pin as many dimensions as possible in key_filter. Wildcarding all
    dimensions returns thousands of rows (every sex×age×status combination) and
    the response will be truncated at 25 rows. Use get_dimension_values to find
    'total'/'all' codes for dimensions you don't need broken down.

    GOOD:  'A.037006.1.9.TOTAL.99'  → ~1 row/year (total pop of Bologna)
    BAD:   'A.037006.....'           → 15,000+ rows (every combination), truncated

    Format: dot-separated values matching dimension positions from key_filter_template.
    Empty between dots = wildcard. Number of dots must match number of dimensions.

    NOTE: ISTAT endPeriod bug (returns +1 year) is corrected automatically.

    args:
        dataflow_id: Dataset ID (e.g. '22_289')
        last_n_observations: Most recent observations per series (default 5, max 20)
        start_period: Start year 'YYYY' (optional)
        end_period: End year 'YYYY' — bug workaround applied automatically (optional)
        key_filter: SDMX key filter, e.g. 'A.037006.1.9.TOTAL.99' (optional but strongly recommended)

    returns:
        Dict with data rows (max 25), truncation warning if applicable
    """
    # Enforce max cap to prevent downloading hundreds of MB
    last_n_observations = min(last_n_observations, 20)

    # Build URL
    key_part = key_filter if key_filter else ""
    url = f"{BASE_URL}/data/{dataflow_id}/{key_part}"

    params: dict = {}
    if last_n_observations:
        params["lastNObservations"] = last_n_observations
    if start_period:
        params["startPeriod"] = start_period
    if end_period:
        # KNOWN BUG: ISTAT endPeriod returns one extra year.
        # Workaround: subtract 1 from the requested year.
        try:
            corrected = str(int(end_period) - 1)
            params["endPeriod"] = corrected
            print(
                f"[ISTAT] endPeriod workaround applied: requested {end_period} → sending {corrected}"
            )
        except ValueError:
            params["endPeriod"] = end_period  # Non-year format — pass as-is

    try:
        resp = _rate_limited_get(
            url,
            headers={"Accept": ACCEPT_CSV},
            params=params,
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {
            "error": "Request timed out (ISTAT can be slow — try reducing last_n_observations)",
            "dataflow_id": dataflow_id,
        }
    except httpx.HTTPError as exc:
        return {"error": f"HTTP error: {exc}", "dataflow_id": dataflow_id}

    # Parse CSV response
    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        all_rows = list(reader)
        columns = reader.fieldnames or []
    except Exception as exc:
        return {
            "error": f"CSV parse error: {exc}",
            "dataflow_id": dataflow_id,
            "raw_preview": resp.text[:500],
        }

    # ── Compact output: strip redundant columns that waste context ──
    DROP_COLS = {"DATAFLOW", "STRUCTURE", "STRUCTURE_ID", "STRUCTURE_NAME"}
    keep_cols = [c for c in columns if c not in DROP_COLS]

    # ── Hard row cap: never return more than MAX_ROWS to the LLM ──
    MAX_ROWS = 25
    total_rows = len(all_rows)
    truncated = total_rows > MAX_ROWS
    rows_out = all_rows[:MAX_ROWS]

    # Strip dropped columns from each row
    compact_rows = [{k: row[k] for k in keep_cols if k in row} for row in rows_out]

    result: dict = {
        "dataflow_id": dataflow_id,
        "key_filter": key_filter or "(all)",
        "total_rows": total_rows,
        "rows_returned": len(compact_rows),
        "columns": keep_cols,
        "data": compact_rows,
    }

    if truncated:
        result["warning"] = (
            f"Response truncated: {total_rows} rows available but only {MAX_ROWS} returned. "
            "To get fewer, more relevant rows: pin more dimensions in the key_filter "
            "instead of using wildcards. Use get_dimension_values to find the 'total' or "
            "'all ages' code for each dimension you don't need broken down."
        )

    return result
