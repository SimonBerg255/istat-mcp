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
DCIS_POPORESBIL1   Resident population by municipality — annual balance (births, deaths, migration)
DCIS_POPTOT1       Total resident population by municipality and age class
DCIS_NATASSI1      Live births by municipality of residence
DCIS_MORTIT1       Deaths by municipality, sex, and age
DCIS_MIGRAZIONI1   Internal and international migration flows by municipality

EMPLOYMENT & LABOUR MARKET
---------------------------
DCCV_TAXOCCU1      Employment rate by region, sex, and age group (ISTAT Labour Force Survey)
DCCV_TAXDISOC1     Unemployment rate by region, sex, and age group
DCCV_OCCUPATIT1    Number of employed persons by sector and region
DCCV_INATTIVIT1    Inactive population and inactivity rate by region

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

Note: Dataset IDs may change with ISTAT restructuring. Use search_datasets
tool to verify IDs or discover new datasets.
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

LIMITING RESPONSE SIZE
-----------------------
ISTAT datasets can span decades with thousands of rows per series.
ALWAYS use lastNObservations (or last_n_years in convenience tools) to limit data.
• Recommended: lastNObservations=5 (default) for recent trends
• Maximum enforced by this server: lastNObservations=20
• Requests without a limit can download hundreds of MB and time out.

RECOMMENDED WORKFLOW
---------------------
1. search_datasets("keyword")          — find the dataset ID you need
2. get_dataset_structure("DATASET_ID") — understand dimensions & available filters
3. get_dataset_data("DATASET_ID", ...) — fetch actual data with filters applied

TERRITORY CODE FORMAT
----------------------
ISTAT uses its own coding system for territories:
• Municipalities (comuni): 6-digit code, e.g. "058091" = Rome, "015146" = Milan
• Provinces: 3-digit code, e.g. "058" = Rome province
• Regions (NUTS2): 2-digit code prefixed with "ITC1", "ITF3", etc.
  - "ITC1" = Piemonte, "ITC4" = Lombardia, "ITI4" = Lazio
  - Full list: use get_territory_codes resource

KEY FILTER SYNTAX
------------------
The key_filter parameter follows SDMX key syntax:
• Dimensions are separated by dots: "A.IT.M.TOTAL"
• Wildcards (any value) use empty string between dots: "A..M."
• Example: "A.ITC4..1" = annual data for Lombardia, all sexes, type 1

RESPONSE FORMAT
----------------
Data: CSV (application/vnd.sdmx.data+csv;version=1.0.0)
Metadata/structure: JSON (application/vnd.sdmx.structure+json;version=2.0.0)
XML: used internally for dataflow list (default format)

COMMON ERRORS
-------------
• 404 Not Found: dataset ID does not exist or has been renamed
• 413 / empty response: query returned too much data — add lastNObservations
• Timeout: ISTAT servers are slow; 120s timeout is set. Try reducing data volume.
• SSL errors: verify=False is set on the HTTP client to work around cert issues.
"""


# ─────────────────────────────────────────────
# Resource 3 — get_territory_codes
# ─────────────────────────────────────────────

_TERRITORY_DATA = {
    "regions": """\
ITALIAN REGIONS — ISTAT NUTS2 Codes
=====================================
Code      Region
--------  ---------------------------
ITC1      Piemonte
ITC2      Valle d'Aosta / Vallée d'Aoste
ITC3      Liguria
ITC4      Lombardia
ITH1      Provincia Autonoma Bolzano/Bozen
ITH2      Provincia Autonoma Trento
ITH3      Veneto
ITH4      Friuli-Venezia Giulia
ITH5      Emilia-Romagna
ITI1      Toscana
ITI2      Umbria
ITI3      Marche
ITI4      Lazio
ITF1      Abruzzo
ITF2      Molise
ITF3      Campania
ITF4      Puglia
ITF5      Basilicata
ITF6      Calabria
ITG1      Sicilia
ITG2      Sardegna

Note: For municipal-level datasets use 6-digit ISTAT municipality codes.
""",
    "metro_cities": """\
ITALIAN METROPOLITAN CITIES — ISTAT Codes
==========================================
Code    City
------  --------------------------
201     Torino
215     Genova
202     Milano (Città Metropolitana)
237     Venezia
239     Bologna
248     Firenze
258     Roma
263     Napoli
272     Bari
275     Reggio Calabria
282     Palermo
292     Catania
204     Cagliari
217     Messina

Note: These are province-level codes. For municipality data, use the
6-digit comune codes (e.g., 058091 for Roma Capitale).
""",
    "provinces": """\
ITALIAN PROVINCES — ISTAT Numeric Codes (selection)
=====================================================
Code  Province              Region
----  --------------------  ------------------
001   Torino                Piemonte
003   Novara                Piemonte
004   Cuneo                 Piemonte
006   Alessandria           Piemonte
010   Genova                Liguria
015   Milano                Lombardia
016   Bergamo               Lombardia
017   Brescia               Lombardia
019   Como                  Lombardia
020   Cremona               Lombardia
021   Lecco                 Lombardia
022   Lodi                  Lombardia
023   Mantova               Lombardia
025   Monza e Brianza       Lombardia
026   Pavia                 Lombardia
027   Sondrio               Lombardia
028   Varese                Lombardia
021   Bolzano/Bozen         Trentino-Alto Adige
022   Trento                Trentino-Alto Adige
023   Belluno               Veneto
024   Vicenza               Veneto
026   Padova                Veneto
027   Rovigo                Veneto
028   Treviso               Veneto
029   Venezia               Veneto
030   Verona                Veneto
032   Gorizia               Friuli-Venezia Giulia
031   Pordenone             Friuli-Venezia Giulia
032   Trieste               Friuli-Venezia Giulia
033   Udine                 Friuli-Venezia Giulia
035   Bologna               Emilia-Romagna
036   Ferrara               Emilia-Romagna
037   Forlì-Cesena          Emilia-Romagna
038   Modena                Emilia-Romagna
039   Parma                 Emilia-Romagna
040   Piacenza              Emilia-Romagna
041   Ravenna               Emilia-Romagna
042   Reggio Emilia         Emilia-Romagna
043   Rimini                Emilia-Romagna
045   Arezzo                Toscana
046   Firenze               Toscana
047   Grosseto              Toscana
048   Livorno               Toscana
049   Lucca                 Toscana
050   Massa-Carrara         Toscana
051   Pisa                  Toscana
052   Pistoia               Toscana
053   Prato                 Toscana
054   Siena                 Toscana
055   Perugia               Umbria
056   Terni                 Umbria
057   Ancona                Marche
058   Roma                  Lazio
059   Frosinone             Lazio
060   Latina                Lazio
061   Rieti                 Lazio
062   Viterbo               Lazio
063   Chieti                Abruzzo
064   L'Aquila              Abruzzo
065   Pescara               Abruzzo
066   Teramo                Abruzzo
067   Campobasso            Molise
070   Caserta               Campania
063   Napoli                Campania
065   Salerno               Campania
066   Avellino              Campania
067   Benevento             Campania
072   Bari                  Puglia
073   Brindisi              Puglia
074   Foggia                Puglia
075   Lecce                 Puglia
076   Taranto               Puglia
077   Potenza               Basilicata
076   Matera                Basilicata
079   Catanzaro             Calabria
080   Cosenza               Calabria
081   Crotone               Calabria
082   Reggio Calabria       Calabria
083   Vibo Valentia         Calabria
084   Agrigento             Sicilia
085   Caltanissetta         Sicilia
086   Catania               Sicilia
087   Enna                  Sicilia
088   Messina               Sicilia
082   Palermo               Sicilia
089   Ragusa                Sicilia
090   Siracusa              Sicilia
091   Trapani               Sicilia
092   Cagliari              Sardegna
095   Nuoro                 Sardegna
091   Oristano              Sardegna
090   Sassari               Sardegna
111   Sud Sardegna          Sardegna

Note: Use these 3-digit codes for province-level queries in SDMX key filters.
For municipality-level data use 6-digit comune codes.
""",
}


def get_territory_codes(territory_type: str) -> str:
    """
    Returns common ISTAT territory codes for a given type.
    Types: 'regions', 'metro_cities', or 'provinces'

    args:
        territory_type: One of 'regions', 'metro_cities', 'provinces'

    returns:
        Formatted lookup table as plain text
    """
    key = territory_type.lower().strip()
    if key not in _TERRITORY_DATA:
        valid = ", ".join(_TERRITORY_DATA.keys())
        return (
            f"Unknown territory type '{territory_type}'. "
            f"Valid types are: {valid}"
        )
    return _TERRITORY_DATA[key]
