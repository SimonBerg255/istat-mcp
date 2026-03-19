"""
ISTAT Open Data MCP Server

Provides access to Italian national statistics from ISTAT (Istituto Nazionale
di Statistica) via the SDMX REST API.

No authentication required — the API is fully public.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from fastmcp import FastMCP

from tools import (
    search_datasets,
    get_dataset_structure,
    get_dataset_data,
    get_population_data,
    get_employment_data,
)
from resources import (
    get_dataset_catalog,
    get_api_usage_guide,
    get_territory_codes,
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
    (IPAllowlistMiddleware, {}),
]

# ─────────────────────────────────────────────
# FastMCP server
# ─────────────────────────────────────────────

mcp = FastMCP(
    name="ISTAT Open Data Server",
    instructions=(
        "Provides access to Italian national statistics from ISTAT (Istituto Nazionale di "
        "Statistica) via the SDMX REST API. Use this server to query demographic, economic, "
        "social, and territorial data for Italian municipalities, regions, and national "
        "aggregates.\n\n"
        "IMPORTANT — Rate limit: ISTAT allows only 5 requests per minute. The server enforces "
        "this automatically but you must not issue many tool calls in rapid succession.\n\n"
        "Recommended workflow:\n"
        "1. search_datasets — find dataset IDs by keyword\n"
        "2. get_dataset_structure — understand available dimensions and filters\n"
        "3. get_dataset_data — fetch actual data with filters\n\n"
        "Convenience wrappers: get_population_data, get_employment_data\n\n"
        "Static resources (no API call needed): dataset_catalog, api_usage_guide, "
        "territory_codes/{type}"
    ),
    version="1.0.0",
    website_url="https://esploradati.istat.it",
)

# ─────────────────────────────────────────────
# Register tools
# ─────────────────────────────────────────────

mcp.tool(name="search_datasets")(search_datasets)
mcp.tool(name="get_dataset_structure")(get_dataset_structure)
mcp.tool(name="get_dataset_data")(get_dataset_data)
mcp.tool(name="get_population_data")(get_population_data)
mcp.tool(name="get_employment_data")(get_employment_data)

# ─────────────────────────────────────────────
# Register resources
# ─────────────────────────────────────────────

mcp.resource("resource://istat/catalog")(get_dataset_catalog)
mcp.resource("resource://istat/api_guide")(get_api_usage_guide)
mcp.resource("resource://istat/territory/{territory_type}")(get_territory_codes)

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
