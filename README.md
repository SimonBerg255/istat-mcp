# ISTAT Open Data MCP Server

An MCP (Model Context Protocol) server that gives AI assistants live access to Italian national statistics from **ISTAT** (Istituto Nazionale di Statistica) via the public SDMX REST API.

Italian public sector AI assistants can use this server to query demographic, economic, social, and territorial data across all Italian municipalities, provinces, and regions — with no API key required.

---

## What is ISTAT?

ISTAT is the Italian National Statistics Institute. It publishes authoritative data on:

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

Official data portal: **https://esploradati.istat.it**

---

## No API Key Needed

The ISTAT SDMX REST API is fully public. No registration, no credentials.

---

## ⚠️ Rate Limit Warning — Read This

**ISTAT enforces a strict limit of 5 requests per minute per IP address.**

Exceeding this limit triggers an IP block lasting **1–2 days**. The server enforces the rate limit automatically with a sliding-window throttle — you will see log messages like:

```
[ISTAT rate limit] Sleeping 12.3s to respect 5 req/min cap
```

This is normal. Do not disable or bypass the rate limiter.

---

## How to Run

### Install dependencies

```bash
pip install -r requirements.txt
```

### Start the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

The MCP endpoint will be available at:

```
http://localhost:8000/mcp
```

---

## Connecting to Intric

In the Intric assistant configuration, set the MCP server URL to:

```
http://your-server-host:8000/mcp
```

No API key field is needed — leave it blank.

---

## Available Tools

| Tool | Description |
|------|-------------|
| `search_datasets` | Search ~450 ISTAT datasets by keyword |
| `get_dataset_structure` | Inspect dimensions and filters for a dataset |
| `get_dataset_data` | Fetch data with optional time range and dimension filters |
| `get_population_data` | Convenience wrapper for population data by municipality |
| `get_employment_data` | Convenience wrapper for employment/unemployment rates by region |

## Available Resources

| Resource URI | Description |
|---|---|
| `resource://istat/catalog` | Curated list of ~20 high-value datasets for public sector |
| `resource://istat/api_guide` | Rate limit rules, known bugs, and query patterns |
| `resource://istat/territory/regions` | All 20 Italian regions with NUTS2 codes |
| `resource://istat/territory/metro_cities` | 14 metropolitan cities with ISTAT codes |
| `resource://istat/territory/provinces` | Italian provinces with numeric ISTAT codes |

---

## Example Questions an AI Can Now Answer

- *"What is the current population of Milan?"*
- *"Show me the unemployment rate trend in Calabria over the last 5 years."*
- *"How many births were registered in Rome in recent years?"*
- *"Which Italian regions have the highest employment rates?"*
- *"Find datasets about school enrollment in Italy."*
- *"What is the population of Turin municipality?"*
- *"Show immigration permit data for Lombardia."*

---

## Recommended Query Workflow

```
1. search_datasets("population")         → find dataset ID
2. get_dataset_structure("DCIS_POPORESBIL1")  → understand dimensions
3. get_dataset_data("DCIS_POPORESBIL1", last_n_observations=5)  → fetch data
```

For common use cases, skip steps 1–2 and use convenience tools directly:

```
get_population_data(territory_code="015146", last_n_years=5)   # Milan
get_employment_data(region_code="ITC4", last_n_years=5)        # Lombardia
```

---

## Known API Bug: endPeriod Returns One Extra Year

When `endPeriod=2023` is sent to the ISTAT API, it returns data up to 2024.

**This server applies the workaround automatically.** The `get_dataset_data` tool subtracts 1 from your requested end year before sending the request. You do not need to account for this manually.

---

## Architecture Notes

- XML parsing: `xml.etree.ElementTree` (stdlib — no lxml dependency)
- CSV parsing: `csv.DictReader` (stdlib — no pandas dependency)
- HTTP client: `httpx` with 120s timeout and `verify=False` for ISTAT SSL cert quirks
- Dataflow cache: the full list of ~450 datasets is fetched once and cached for 24 hours
- Rate limiter: thread-safe sliding window, sleeps as needed before each request

---

## SDMX API Reference

Base URL: `https://esploradati.istat.it/SDMXWS/rest/`

Key endpoints:
- `GET /dataflow/IT1` — list all datasets
- `GET /data/{dataflow_id}` — get data (CSV preferred)
- `GET /datastructure/IT1/{structure_id}` — get schema

Official ISTAT open data portal: https://esploradati.istat.it
