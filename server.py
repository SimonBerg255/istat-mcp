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
        "MANDATORY WORKFLOW — execute all steps automatically:\n"
        "1. search_datasets(query) — find the dataset ID. Call this first for any topic.\n"
        "2. get_dataset_structure(dataflow_id) — inspect dimensions and codelist IDs.\n"
        "3. get_dimension_values(dataflow_id, dimension_id, search=<place/category>) — "
        "look up the exact code for the territory or category the user mentioned. "
        "Always call this for REF_AREA before fetching data — never guess codes.\n"
        "4. get_dataset_data(dataflow_id, key_filter=..., last_n_observations=5) — "
        "fetch the data using codes found in step 3.\n\n"
        "Steps 2 and 3 are cached — they cost 0 extra API calls after first use.\n\n"
        "KEY FILTER FORMAT: dot-separated dimension values by position. "
        "Empty string = wildcard. Example for 6-dim dataset, annual data for Bologna: "
        "'A.037006.....' (FREQ=A, REF_AREA=037006, dims 3-6=wildcard).\n\n"
        "RATE LIMIT: max 5 API requests/minute — enforced automatically. Do not abort "
        "if a step takes time; the server is sleeping to respect the limit.\n\n"
        "Static resources available without API calls: "
        "resource://istat/catalog (curated dataset list), "
        "resource://istat/api_guide (full API reference)."
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
