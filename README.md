# ISTAT MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that gives AI assistants live access to Italian national statistics from **ISTAT** (Istituto Nazionale di Statistica) via the public SDMX REST API.

Connect any MCP-compatible AI assistant to 4,700+ Italian statistical datasets covering demographics, employment, education, health, economy, territory, and more — with no API key required.

---

## What is ISTAT?

ISTAT is Italy's National Statistics Institute. It publishes authoritative data on:

- Population and demographics (births, deaths, migration, age structure)
- Employment and labour market
- Education and schools
- Health and healthcare
- Municipal finance and public spending
- Housing and construction
- Environment and territory
- Crime and justice
- Immigration and foreign residents
- Regional GDP and economic indicators

Data portal: **https://esploradati.istat.it**

---

## No API Key Required

The ISTAT SDMX REST API is fully public. No registration or credentials needed.

---

## ⚠️ Rate Limit — Read This First

**ISTAT enforces a hard limit of 5 requests per minute per IP address.**

Exceeding this triggers an IP block lasting 1–2 days. The server enforces the rate limit automatically with a sliding-window throttle. You will see log messages like:

```
[ISTAT rate limit] Sleeping 12.3s to respect 5 req/min cap
```

This is expected behaviour. Do not disable the rate limiter.

---

## Tools

The server exposes four generic tools that let an AI agent navigate the full ISTAT catalogue:

| Tool | Purpose |
|------|---------|
| `search_datasets` | Search ~4,700 datasets by keyword. Returns dataset IDs needed for the other tools. |
| `get_dataset_structure` | Inspect all dimensions of a dataset (e.g. territory, age, sex, time frequency) and their codelist IDs. Cached after first call. |
| `get_dimension_values` | Look up valid codes for any dimension — territory names, age groups, sex codes, etc. Pass `search=` to filter. Cached. |
| `get_dataset_data` | Fetch actual data using a dot-separated key filter built from codes discovered above. |

### Workflow the AI follows automatically

```
1. search_datasets("unemployment by region")   → get dataset ID
2. get_dataset_structure("151_914")            → inspect dimensions, find codelist IDs
3. get_dimension_values("151_914", "REF_AREA", search="Lazio")  → get territory code
4. get_dataset_data("151_914", key_filter="A.ITE4.......", last_n_observations=5)
```

Steps 2 and 3 are cached — no extra API calls after first use per dataset.

---

## Resources

| URI | Description |
|-----|-------------|
| `resource://istat/catalog` | Curated list of high-value datasets for public sector use |
| `resource://istat/api_guide` | Rate limit rules, key filter format, known bugs, query patterns |

---

## Running Locally

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

MCP endpoint: `http://localhost:8000/mcp`

Health check: `http://localhost:8000/health`

---

## Deploy to Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template)

1. Fork this repo
2. Create a new Railway project from your fork
3. Railway auto-detects the `Procfile` and deploys with no configuration needed
4. Copy the Railway URL and add `/mcp` — that's your MCP endpoint

No environment variables required.

---

## Connecting to Intric

In your Intric assistant configuration, set the MCP server URL to:

```
https://your-railway-app.railway.app/mcp
```

The server instructions tell the AI to execute tool chains automatically — you do not need to configure tool-call behaviour manually.

---

## Example Questions

Once connected, an AI assistant can answer questions like:

- *"What is the population of Milan?"*
- *"Show me unemployment trends in Calabria over the last 5 years."*
- *"How many births were registered in Rome recently?"*
- *"Which Italian regions have the highest employment rates?"*
- *"Find datasets about school enrolment in Italy."*
- *"Compare immigration permit data across northern regions."*

---

## Known API Behaviour

**`endPeriod` returns one extra year** — when `endPeriod=2023` is sent, the API returns data through 2024. This server applies the workaround automatically (subtracts 1 from the requested end year).

**Occasional API degradation** — ISTAT's infrastructure periodically experiences slowdowns or partial outages, particularly on the `/dataflow/IT1/all` (catalogue) and `/data/...` endpoints. When this happens, `search_datasets` and `get_dataset_data` will time out. Metadata endpoints (`get_dataset_structure`, `get_dimension_values`) typically remain available. Recovery is usually within a few hours to two days.

---

## Architecture

- **Framework**: [FastMCP](https://github.com/jlowin/fastmcp) (Python)
- **HTTP client**: `httpx` with 120s timeout and `verify=False` (ISTAT SSL quirks)
- **XML parsing**: `xml.etree.ElementTree` (stdlib — no lxml)
- **Rate limiter**: thread-safe sliding window, auto-sleeps before each request
- **Dataflow cache**: full catalogue fetched once, cached 24 hours
- **Structure cache**: per-dataset DSD cached in memory indefinitely
- **Codelist cache**: per-codelist values cached in memory indefinitely

---

## SDMX API Reference

Base URL: `https://esploradati.istat.it/SDMXWS/rest/`

Key endpoints used:
- `GET /dataflow/IT1/all` — list all datasets
- `GET /dataflow/IT1/{id}?references=all` — dataset metadata + full structure in one call
- `GET /codelist/IT1/{codelist_id}` — valid codes for a dimension
- `GET /data/IT1,{id},1.0/{key_filter}` — time-series data

---

## License

MIT — see [LICENSE](LICENSE).
