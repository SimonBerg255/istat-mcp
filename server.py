"""
ISTAT Open Data MCP Server

Provides access to Italian national statistics from ISTAT (Istituto Nazionale
di Statistica) via the SDMX REST API.

No authentication required — the API is fully public.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from fastmcp import FastMCP

from tools import (
    search_datasets,
    get_dataset_structure,
    get_dimension_values,
    get_dataset_data,
)
from resources import (
    get_dataset_catalog,
    get_api_usage_guide,
)

# ─────────────────────────────────────────────
# IP allowlist middleware
# ─────────────────────────────────────────────

ALLOWED_IPS = ["*"]  # Open to all — no authentication required


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if "*" in ALLOWED_IPS:
            return await call_next(request)
        client_ip = request.client.host if request.client else None
        if client_ip not in ALLOWED_IPS:
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return await call_next(request)


middleware = [
    Middleware(IPAllowlistMiddleware),
]

# ─────────────────────────────────────────────
# FastMCP server
# ─────────────────────────────────────────────

mcp = FastMCP(
    name="ISTAT Open Data Server",
    instructions=(
        "You have access to Italian national statistics from ISTAT via the SDMX REST API.\n\n"
        "AUTOMATIC TOOL EXECUTION — CRITICAL RULE\n"
        "Always execute the full tool chain autonomously without asking the user for permission "
        "at each step. When a user asks a statistics question, immediately call the necessary "
        "tools in sequence and return the final answer. Never say 'Should I look that up?' or "
        "'Do you want me to search for that?' — just do it.\n\n"
        "DECISION TREE — follow this for EVERY statistics question:\n"
        "1. search_datasets(query) — find the dataset ID. Call this first.\n"
        "   If no results: try Italian keywords (population→popolazione, employment→occupazione).\n"
        "2. get_dataset_structure(dataflow_id) — get dimensions and key_filter_template.\n"
        "3. get_dimension_values(dataflow_id, dimension_id, search=...) — look up codes.\n"
        "   ALWAYS call this for REF_AREA (territory) before fetching data.\n"
        "   ALSO call this for SEX, AGE, DATA_TYPE etc. to find 'total'/'all' codes.\n"
        "4. get_dataset_data(dataflow_id, key_filter=..., last_n_observations=5) — fetch data.\n\n"
        "CRITICAL — DIMENSION PINNING (prevents timeouts and context overflow)\n"
        "ISTAT datasets have many dimensions (territory × sex × age × marital status × ...).\n"
        "If you wildcard everything, the response will contain THOUSANDS of rows and be truncated.\n"
        "ALWAYS pin dimensions you don't need broken down:\n"
        "- Use get_dimension_values to find the 'total' or 'all' code for SEX, AGE, etc.\n"
        "- Only wildcard the dimension the user actually wants to compare across.\n"
        "- Example: user asks 'population of Bologna' → pin SEX=total, AGE=total, "
        "MARITAL_STATUS=total → get ~1 row per year instead of 15,000.\n"
        "- Example: user asks 'unemployment by region' → pin SEX=total, AGE=total, "
        "wildcard REF_AREA → get ~20 rows (one per region) instead of thousands.\n\n"
        "KEY FILTER FORMAT: see key_filter_template in get_dataset_structure response.\n"
        "Dot-separated values matching dimension positions. Empty = wildcard.\n\n"
        "RATE LIMIT: max 5 API requests/minute — enforced automatically. Do not abort "
        "if a step takes time; the server is sleeping to respect the limit.\n\n"
        "SEARCH TIPS: Many ISTAT datasets only have Italian names. If English search "
        "returns nothing, try Italian: popolazione, occupazione, disoccupazione, reddito, "
        "PIL, nascite, decessi, scuole, turismo, rifiuti, abitazioni, delitti.\n\n"
        "Static resources (no API call): resource://istat/catalog, resource://istat/api_guide"
    ),
    version="2.0.0",
    website_url="https://esploradati.istat.it",
)

# ─────────────────────────────────────────────
# Register tools
# ─────────────────────────────────────────────

mcp.tool(name="search_datasets")(search_datasets)
mcp.tool(name="get_dataset_structure")(get_dataset_structure)
mcp.tool(name="get_dimension_values")(get_dimension_values)
mcp.tool(name="get_dataset_data")(get_dataset_data)

# ─────────────────────────────────────────────
# Register resources
# ─────────────────────────────────────────────

mcp.resource("resource://istat/catalog")(get_dataset_catalog)
mcp.resource("resource://istat/api_guide")(get_api_usage_guide)

# ─────────────────────────────────────────────
# Custom routes
# ─────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


# ─────────────────────────────────────────────
# ASGI app
# ─────────────────────────────────────────────

app = mcp.http_app(middleware=middleware)
