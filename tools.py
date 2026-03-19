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
ACCEPT_STRUCT_JSON = "application/vnd.sdmx.structure+json;version=2.0.0"

# Known convenience dataflows
POPULATION_DATAFLOW = "DCIS_POPORESBIL1"
EMPLOYMENT_DATAFLOW = "DCCV_TAXOCCU1"

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
# Dataflow cache (one fetch per server lifetime)
# ─────────────────────────────────────────────

_dataflow_cache: list[dict] | None = None
_dataflow_cache_time: float = 0.0
_CACHE_TTL = 86400  # 24 hours


def _get_dataflows() -> list[dict]:
    """
    Fetch and cache the full list of ISTAT dataflows (~450 datasets).

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


def search_datasets(query: str, lang: str = "en") -> list[dict]:
    """
    Search ISTAT datasets by keyword. Returns matching datasets with their ID and name.

    Use this before fetching data — you need a dataset ID to query data.
    Returns up to 50 results. Language can be 'it' (Italian) or 'en' (English).

    args:
        query: Keyword to search for (e.g. 'population', 'employment', 'municipality')
        lang: Language for dataset names, 'it' or 'en' (default: 'en')

    returns:
        List of matching datasets with 'id' and 'name' fields
    """
    try:
        flows = _get_dataflows()
    except Exception as exc:
        return [{"error": "Failed to retrieve dataset list", "details": str(exc)}]

    query_lower = query.lower()
    results = []

    for flow in flows:
        names = flow.get("names", {})
        # Try requested lang, fall back to the other
        name = names.get(lang) or names.get("it") or names.get("en") or ""
        if query_lower in name.lower():
            results.append({"id": flow["id"], "name": name})
        if len(results) >= 50:
            break

    return results


# ─────────────────────────────────────────────
# Tool 2 — get_dataset_structure
# ─────────────────────────────────────────────


def get_dataset_structure(dataflow_id: str) -> dict:
    """
    Get the structure (dimensions and their codes) of a specific ISTAT dataset.

    Call this after search_datasets to understand what filters are available
    before fetching actual data. Returns dimension names, codes, and available values.

    args:
        dataflow_id: The dataset ID from search_datasets (e.g. '22_289')

    returns:
        Dict with dataset name, dimensions list, and available code values
    """
    # Step 1 — resolve datastructure ID from dataflow
    df_url = f"{BASE_URL}/dataflow/IT1/{dataflow_id}"
    try:
        resp = _rate_limited_get(
            df_url,
            headers={"Accept": ACCEPT_STRUCT_JSON},
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {"error": "Request timed out fetching dataflow", "dataflow_id": dataflow_id}
    except httpx.HTTPError as exc:
        return {"error": f"HTTP error fetching dataflow: {exc}", "dataflow_id": dataflow_id}

    structure_id = None
    dataset_name = ""

    # Try JSON first
    try:
        data = resp.json()
        dfs = (
            data.get("data", {})
            .get("dataflows", [])
        )
        if dfs:
            df = dfs[0]
            dataset_name = (
                df.get("name", {}).get("en")
                or df.get("name", {}).get("it")
                or dataflow_id
            )
            ref = df.get("structure", {})
            structure_id = ref.get("id") or ref.get("ref", {}).get("id")
    except Exception:
        pass

    # Fall back to XML if JSON didn't give us what we need
    if not structure_id:
        try:
            root = ET.fromstring(resp.text)
            for df_el in root.iter(f"{{{NS_STRUCTURE}}}Dataflow"):
                for name_el in df_el.iter(f"{{{NS_COMMON}}}Name"):
                    if name_el.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
                        dataset_name = name_el.text or dataflow_id
                for ref_el in df_el.iter(f"{{{NS_STRUCTURE}}}Structure"):
                    ref = ref_el.find(f"{{{NS_COMMON}}}Ref")
                    if ref is not None:
                        structure_id = ref.get("id")
        except ET.ParseError as exc:
            return {"error": f"XML parse error: {exc}", "dataflow_id": dataflow_id}

    if not structure_id:
        return {
            "error": "Could not resolve structure ID from dataflow",
            "dataflow_id": dataflow_id,
        }

    # Step 2 — fetch the data structure definition
    struct_url = f"{BASE_URL}/datastructure/IT1/{structure_id}"
    try:
        resp2 = _rate_limited_get(
            struct_url,
            headers={"Accept": ACCEPT_STRUCT_JSON},
        )
        resp2.raise_for_status()
    except httpx.TimeoutException:
        return {"error": "Request timed out fetching structure", "structure_id": structure_id}
    except httpx.HTTPError as exc:
        return {"error": f"HTTP error fetching structure: {exc}", "structure_id": structure_id}

    dimensions = []
    try:
        sdata = resp2.json()
        dsds = sdata.get("data", {}).get("dataStructures", [])
        if dsds:
            dsd = dsds[0]
            if not dataset_name:
                dataset_name = (
                    dsd.get("name", {}).get("en")
                    or dsd.get("name", {}).get("it")
                    or dataflow_id
                )
            dim_list = (
                dsd.get("dataStructureComponents", {})
                .get("dimensionList", {})
                .get("dimensions", [])
            )
            for dim in dim_list:
                dim_name = (
                    dim.get("name", {}).get("en")
                    or dim.get("name", {}).get("it")
                    or dim.get("id", "")
                )
                codelist_ref = (
                    dim.get("localRepresentation", {})
                    .get("enumeration", {})
                    .get("id", "")
                )
                dimensions.append(
                    {
                        "id": dim.get("id", ""),
                        "name": dim_name,
                        "position": dim.get("position", 0),
                        "codelist": codelist_ref,
                    }
                )
    except Exception:
        # Fall back to XML parsing
        try:
            root2 = ET.fromstring(resp2.text)
            for dsd_el in root2.iter(f"{{{NS_STRUCTURE}}}DataStructure"):
                for name_el in dsd_el.iter(f"{{{NS_COMMON}}}Name"):
                    if name_el.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
                        dataset_name = name_el.text or dataflow_id
                for dim_el in root2.iter(f"{{{NS_STRUCTURE}}}Dimension"):
                    dim_id = dim_el.get("id", "")
                    dim_pos = dim_el.get("position", "")
                    cl_ref = ""
                    for enum_ref in dim_el.iter(f"{{{NS_STRUCTURE}}}Enumeration"):
                        ref = enum_ref.find(f"{{{NS_COMMON}}}Ref")
                        if ref is not None:
                            cl_ref = ref.get("id", "")
                    dimensions.append(
                        {
                            "id": dim_id,
                            "name": dim_id,
                            "position": dim_pos,
                            "codelist": cl_ref,
                        }
                    )
        except ET.ParseError as exc:
            return {"error": f"XML parse error on structure: {exc}"}

    return {
        "dataflow_id": dataflow_id,
        "structure_id": structure_id,
        "dataset_name": dataset_name,
        "dimensions": dimensions,
        "note": (
            "Use dimension 'id' values to build key_filter strings for get_dataset_data. "
            "Format: 'val1.val2.val3' matching dimension positions."
        ),
    }


# ─────────────────────────────────────────────
# Tool 3 — get_dataset_data
# ─────────────────────────────────────────────


def get_dataset_data(
    dataflow_id: str,
    last_n_observations: int = 5,
    start_period: str = None,
    end_period: str = None,
    key_filter: str = None,
) -> dict:
    """
    Fetch data from an ISTAT dataset. Always use last_n_observations to limit
    response size unless you specifically need a time range.

    IMPORTANT: Due to a known ISTAT API bug, end_period returns one extra year.
    This function automatically applies the workaround (subtracts 1 from year).

    args:
        dataflow_id: Dataset ID from search_datasets (e.g. '22_289')
        last_n_observations: Number of most recent observations to return (default 5, max 20)
        start_period: Start year filter, format 'YYYY' (optional)
        end_period: End year filter, format 'YYYY' — workaround applied automatically (optional)
        key_filter: SDMX key filter string for dimension filtering, e.g. 'A.IT..' (optional, advanced)

    returns:
        Dict with dataset metadata and parsed rows from CSV response
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
        rows = list(reader)
        columns = reader.fieldnames or []
    except Exception as exc:
        return {
            "error": f"CSV parse error: {exc}",
            "dataflow_id": dataflow_id,
            "raw_preview": resp.text[:500],
        }

    return {
        "dataflow_id": dataflow_id,
        "key_filter": key_filter or "(all)",
        "rows_returned": len(rows),
        "columns": list(columns),
        "data": rows,
        "note": (
            "endPeriod bug workaround applied automatically. "
            "Rows capped at last_n_observations (max 20) per series."
        ),
    }


# ─────────────────────────────────────────────
# Tool 4 — get_population_data
# ─────────────────────────────────────────────


def get_population_data(
    territory_code: str = None,
    last_n_years: int = 5,
) -> dict:
    """
    Get Italian population data by territory. This is a convenience wrapper
    around the main population dataset (DCIS_POPORESBIL1).

    Territory codes follow ISTAT municipality codes (e.g. '001272' for Turin,
    '015146' for Milan, '058091' for Rome). Use None for national totals.

    args:
        territory_code: ISTAT municipality or region code (None = national total)
        last_n_years: Number of recent years to return (default 5)

    returns:
        Population data with annual figures
    """
    # Build key filter if a territory code is supplied.
    # DCIS_POPORESBIL1 key structure: FREQ.ITTER107.SEXISTAT1.ETA1.STATCIV2.TIPO_DATO15
    # For a simple territory filter we fix the territory position and leave others as wildcards.
    key_filter = None
    if territory_code:
        # Position 2 is ITTER107 (territory). Use dots as wildcards for other positions.
        key_filter = f"A.{territory_code}...."

    return get_dataset_data(
        dataflow_id=POPULATION_DATAFLOW,
        last_n_observations=last_n_years,
        key_filter=key_filter,
    )


# ─────────────────────────────────────────────
# Tool 5 — get_employment_data
# ─────────────────────────────────────────────


def get_employment_data(
    region_code: str = None,
    last_n_years: int = 5,
) -> dict:
    """
    Get Italian employment and labour market data.
    Returns employment rate, unemployment rate, and active population figures.

    args:
        region_code: ISTAT region code (None = national data)
        last_n_years: Number of recent years (default 5)

    returns:
        Employment statistics
    """
    # DCCV_TAXOCCU1 key: FREQ.ITTER107.SESSO.ETA1.TITOLO_STUDIO.TIPO_DATO15
    key_filter = None
    if region_code:
        key_filter = f"A.{region_code}...."

    return get_dataset_data(
        dataflow_id=EMPLOYMENT_DATAFLOW,
        last_n_observations=last_n_years,
        key_filter=key_filter,
    )
