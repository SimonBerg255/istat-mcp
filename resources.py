"""
Static resources for the ISTAT MCP server.

These resources provide curated reference information without making API calls,
preserving the strict 5 req/min rate limit for actual data queries.
"""

# ─────────────────────────────────────────────
# Resource 1 — get_dataset_catalog
# ─────────────────────────────────────────────


def get_dataset_catalog() -> str:
    """
    Returns a curated list of the most useful ISTAT datasets for Italian
    public sector use cases, with their IDs and descriptions.
    This is a static resource — use search_datasets tool for live search.
    """
    return """\
ISTAT DATASET CATALOG — Curated selection for Italian public sector
===================================================================

POPULATION & DEMOGRAPHICS
--------------------------
22_289             Resident population on 1st January — by municipality, sex, age, marital status
DCIS_NATASSI1      Live births by municipality of residence
DCIS_MORTIT1       Deaths by municipality, sex, and age
DCIS_MIGRAZIONI1   Internal and international migration flows by municipality

EMPLOYMENT & LABOUR MARKET
---------------------------
150_915            Employment rate — by region, sex, and age group (ISTAT Labour Force Survey)
151_914            Unemployment rate — by region, sex, and age group
DCCV_OCCUPATIT1    Number of employed persons by sector and region

EDUCATION & SCHOOLS
-------------------
DCIS_SCUOLE1       Schools and classes by municipality and school type
DCIS_STUDENTI1     Students enrolled by level of education and region
DCIS_DIPLOMI1      Upper secondary graduates by subject area and region

HEALTH & HEALTHCARE
-------------------
DCIS_OSPEDALI1     Hospital beds and discharges by region
DCIS_MORTALITA1    Cause-of-death mortality rates by region and sex
DCIS_ASPVITA1      Life expectancy at birth by region and sex

MUNICIPAL FINANCE & PUBLIC SPENDING
-------------------------------------
DFPA_ENTRATE1      Municipal revenue by category (taxes, transfers, fees)
DFPA_SPESE1        Municipal expenditure by function and municipality
DFPA_DBITOPUBB1    Public debt stock by level of government

HOUSING & CONSTRUCTION
-----------------------
DCIS_ABITAZIONI1   Dwellings by occupancy status and municipality (Census)
DCSC_COSTRUZIONI1  Building permits issued by municipality and type

ENVIRONMENT & TERRITORY
------------------------
DCIS_SUPERFICI1    Municipal surface area and altitude data
DCCV_RIFIUTI1      Municipal solid waste production and collection by region

CRIME & JUSTICE
---------------
DCIS_DELITTI1      Crimes reported to police by type and province
DCIS_DETENUTI1     Prison population by region and offence category

IMMIGRATION & FOREIGN RESIDENTS
---------------------------------
DCIS_PERMSOR1      Residence permits issued by nationality and region
DCIS_POPSTRBIL1    Foreign resident population by municipality and citizenship

GDP & REGIONAL ECONOMICS
-------------------------
DCCV_PILPRO1       Regional GDP and value added by economic activity (NUTS2)
DCCV_REDPRO1       Household disposable income per capita by region

Note: Numeric IDs (e.g. 22_289, 150_915) are verified against the live API.
Named IDs may require verification — use search_datasets to confirm.
"""


# ─────────────────────────────────────────────
# Resource 2 — get_api_usage_guide
# ─────────────────────────────────────────────


def get_api_usage_guide() -> str:
    """
    Usage guide for querying ISTAT data effectively, including rate limits,
    known bugs, and recommended query patterns.
    """
    return """\
ISTAT SDMX REST API — Usage Guide
===================================

BASE URL
--------
https://esploradati.istat.it/SDMXWS/rest/

AUTHENTICATION
--------------
None required. The API is fully public.

RATE LIMIT — READ THIS CAREFULLY
----------------------------------
• Maximum 5 requests per minute per IP address.
• Exceeding this limit triggers an IP block lasting 1–2 DAYS.
• The server enforces the limit automatically via a sliding-window rate limiter.
• If you see "[ISTAT rate limit] Sleeping Xs" in logs, that is normal and expected.
• Never call tools in a tight loop without allowing the rate limiter to do its job.

KNOWN BUG: endPeriod returns one extra year
--------------------------------------------
When you request endPeriod=2023, ISTAT returns data up to 2024.
Workaround: always request endPeriod = desired_year - 1.
This workaround is applied AUTOMATICALLY by get_dataset_data.
You do not need to subtract 1 yourself when calling tools.

LIMITING RESPONSE SIZE — CRITICAL
-----------------------------------
ISTAT datasets have many cross-tabulated dimensions (territory × sex × age × status).
Wildcarding all dimensions returns THOUSANDS of rows and will be truncated at 25.

Two controls:
1. last_n_observations: limits time points per series (default 5, max 20)
2. key_filter dimension pinning: MUCH more important — pin every dimension
   you don't need broken down by looking up 'total'/'all' codes via
   get_dimension_values. Only wildcard the dimension being compared.

GOOD: key_filter='A.037006.1.9.TOTAL.99' → ~1 row/year (total pop of Bologna)
BAD:  key_filter='A.037006.....'          → 15,000+ rows (truncated to 25)

RECOMMENDED 4-STEP WORKFLOW
-----------------------------
1. search_datasets("keyword")                  — find the dataset ID you need
2. get_dataset_structure("DATASET_ID")         — understand dimensions & codelist IDs
3. get_dimension_values("DATASET_ID", "DIM")   — look up valid codes for any dimension
4. get_dataset_data("DATASET_ID", ...)         — fetch actual data with filters applied

Steps 2 and 3 are cached (24h) — first call costs 1 API call, subsequent calls are free.

BUILDING KEY FILTERS
---------------------
The key_filter parameter follows SDMX key syntax:
• Dimensions are separated by dots matching their position order
• Empty string between dots = wildcard (any value)
• Example: get_dataset_structure returns 6 dimensions for dataset 22_289
  → key_filter "A.037006....." means: FREQ=A(annual), REF_AREA=037006(Bologna), rest=wildcard

WORKFLOW EXAMPLE — Unemployment in Emilia-Romagna
--------------------------------------------------
1. search_datasets("unemployment")
   → returns {"id": "151_914", "name": "Unemployment rate"}

2. get_dataset_structure("151_914")
   → returns 8 dimensions: FREQ, REF_AREA (CL_ITTER107), DATA_TYPE, SEX, AGE, ...

3. get_dimension_values("151_914", "REF_AREA", search="Emilia")
   → returns [{"code": "ITD5", "name": "Emilia-Romagna"}, ...]

4. get_dataset_data("151_914", key_filter="A.ITD5.......", last_n_observations=5)
   → returns unemployment rate data for Emilia-Romagna, last 5 years

RESPONSE FORMAT
----------------
Data: CSV (application/vnd.sdmx.data+csv;version=1.0.0)
Structure/metadata: XML (application/xml)

COMMON ERRORS
-------------
• 404 Not Found: dataset ID does not exist or has been renamed — use search_datasets
• 413 / empty response: query returned too much data — add lastNObservations
• Timeout: ISTAT servers are slow; 120s timeout is set. Try reducing data volume.
• SSL errors: verify=False is set on the HTTP client to work around cert issues.
"""
