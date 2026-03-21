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
from mcp.server.fastmcp import Icon

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
# Server icon
# ─────────────────────────────────────────────

_ISTAT_ICON = Icon(src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASwAAAESCAYAAABHDeioAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3wQJDyMO9XnwSwAAIABJREFUeNrtnXdwVFe+5799O7dyToAkgiSCAkhkgU0GG2wTxmDjxA62Z8Z+M1u779VWbe3u83u1Ve+93a3anXnzPM8BbI8JNiKKIBRIQhJICAUkIVBAElKj1K3UrdB5/xBggkKHe7tvq3+fKsqydMO555z7Pb/fub/zOwKLxWIB4ZYMd6kx0PgQA/VNGGhowVB7NwBAwAgAhoFAIAAjEkIaFAB5eAjkIYGQhwXDL34mZMEBbvWs+rr70BXfhL62Fob792B40AiBUAiBXA6BTA6BQgHGywui6dMhTpgHSVwcxHHxEIaEUEeZQghIsNwDs9EI1e1qKHMKoC6vQX99MwwDWruv5zNrBkKXpmDm7tcRlDKPv0JVU43+P/0Rw5fz7DqfCQiAeM6oeEkXL4ZsRTqE/v7UoUiwCLbR9Q2g/WoxHuUVov1asUMCNRHTNq9Gyn/7HN7TI/gj0MPD6Pnv/xVDZ06z3OMFEM+dB/mqVZCtegXShYsgkEios5FgEfYw0NAC5aUiKHOuQ3W7GnBS80iD/LH2pz/BLy7W5XVgaGxE9+e/gbGhgfsXQCaDdPESyFa9AtnKlZDExVMnJMEiJnL1um5WQJlXiEeXijD48JHLyiIN8seao3+Ef/xM14lV0wN07HwLFo3GJfdngoMhT18N2cp0yFam0xwYCRah6+nDoys3ocwrRMfVYhiHhnlTNlloEDad+xbysGDni/fAADp2vgVjcxNv6kM8Jw6y9FWQrVoN2ZKlEEil1IFJsKY+fbUNUF4qwqO8Qqgrap3m6tmDX8IsrD/5JcReCqfeV/Wf/oChs5n8bUSxGNLUNMhXjVpgkvkLqGOTYE0NTHoDuopuQ5lXhEeXCjH0qMutyh++ajFWf/+/wIhEzqmvvj4oVywBDAa3qSMmIACyFSshX7se8jVrwfj4UMcnwXIfDJpBKC8VoS3rKtqvFsM0onPr55mzbxdSv/iDU+6l+fEH9P7jF+5bWWIxZEuXQbFpM+QbNkIYFEwvBAkW/xhR9aIt5zraLlxFZ1EZLCbTlHm2kCXJWJfxZ6fcq/3NrTDcrZkib5UAkpSFUGzeAsXGzRBNm0YvCgmW69C2tkOZcx2tF646NfTA2QSnJWL9iS85v49Fp0Nr4twpW4/i+IRRy2vTZgqbcBARVYF19Nc1oe1iPlqzrqLvboNnPLSTBMTQ2DhlxQoADPfvof/+PfT/6f9BNH065Bs3Q7FxE6SLUunFIsFiD3XFXbRmXYMy+zo0Ta0e9/wWs9k5L3RDvcfUqbG1FZoD30Bz4BswwcFQbNgI+YZNkC1fAYGIXkcSLBtf0K7iSrRlXUVb9nUMd3R7eH04ycKqu+eR9WtWqaA9egTao0cg8PGBfO06KDZsgmz1K2DkcnohSbBexjSiQ0dBKdqyrkGZWwB9v4Z6hbNdpvoGj68Di0aDoTOnR9dOSiSQr34F8o2boFi3AYyvL3USTxYsw+AQHl0qQtvFfLRfucmrSHNPdAmNyjaq7GfR6zGcl4vhvFz0CIWQLV0G+YZNkG/YCFFYGAmWJ6Dr6YMytxCtWVfRWVAKs8FIL8akiuUcl9AyNEh1Pa4LYMJIUSFGigrR+w//A5Kk5KdfHMXRMSRYU4lBZSeU2flozbqG7lt3pvSXKHe2sMzDZOFabXzdqYT+TiX6/ve/QDR7NhQbN0OxaQsk8+Z5xPNPuTisgYYWtF68hraL+eituk893AH8EmZhS/b3nN+nNXk+LENDVOEOIIyKGv3iuGkLpItSIWAYEiy+0lN1H21Z19B68Ro0jQ+p97IlWHGx2JL7V87v8zBuJlm/LMIEB0OxadTyki5dNqXEyy1dQovZjO5bdx7HSOW73cJi4pm21OtJrNh2sVUqaA8fgvbwITABAZCv3wjFltemRKyX25T+ufCDS0XQ9/ZTz+RaTJwgJGZyBbmt395eDGb8jMGMnyHw8YFiw0YotrwO2YqVbpkamteCpe/XjIYfZOdPiewH7mjJcn4PmnB3XntqNBg8eQKDJ09A4O0N+Zq1UGx5HfLVr7hNYkLeCdZwpwpt2floy76OrhvlUyr7gfsNz9xbWJYREiyXiJdWi6GzmRg6mwmBQgH5K2tG3cZX1/A6yp4XgjXcqULTiYtou5iPnspa6k2eZGGRS+j6dh4awlDWeQxlnR+Nsn91DRRbXodi8xbezXnxojTK3ALc+ZevqOfwrSM7Yw6LXEJ+oddjOCcbwznZkC0t4d0mHAy1EDG+mtAcFsEvSLAIl7sjBEGCRTguJmRhESRYhPsIFn0lJEiwCLKwnkKBowQJFsGSYjnBwiKXkCDBItzFwrIMk4VFkGARboJ5kASLIMEiWLGwaNKdIMEi3Mb8obAGggSLcBcLyxl5qsyUC4sgwSJYcQnNVAkECRbhLi6hE+awLCSKBAkWQRAkWAS5hGxbcWRhESRYBCvuGk2IEyRYhLtA1g9BgkW4j0vojLAGEkWCBItgRbBITAgSLIJ4xsKieTKCBItgxcQiMSFIsAjiGU0kt5MgwSLYEhSaxyJIsAgSLIIgwSJYFyyO57FIEAkSLIIEhSDBIggSRIIEi+CtS0ihDQQJFuE2gkUWEEGCRbiPy8axhUUWHEGCRZCFRZBgEZ4nWBYKayBIsAiCIEiwCPeygMjlJEiwCBYFhSbFCRIswm0EiywgggSLcBvFokl3ggSLIAuLIEiwCLLgCBIswmMtLBIUggSLIJdwFHI5CRIsgiBIsAgPNLHIJSRIsAhyCZ3jchIkWARBECRYhMdZWKB9CQkSLIIgSLAIz4PisDxYHQQkWATxHALqgjRYkWARLMH1HJaAoS5IkGARbAkW13FYJFgECRbhPi6hgOqAIMEiWILrsAaysAgSLMJtDCwSLIIEi2ALztPLkGARJFiE+5hYNIdFkGARrFlYHM9hiURUyQQJFuEuBhZ1QYIEi2DNxOJ6DotcQoIEi3AXl5Am3QkSLMJ9eiB1QcLdBIs6LY8tLG5dQprDIsjCItyoB9IcFuFmgiWgWBweW1g0h0WQYD0vWNRpPbgHUtsT7uYSklvAYxOL4zksoZDqmCALiyALiyDB4kawaA6LvwYW13NY9JWQcD+XkDotfwWLY5eQ2p5wP5eQLCzP7YHU9oTbCRaNsryFwhoIEqwXBIvmsDwXmsMi3E2wCP5Cu+YQJFjUaYknBhbFYRFu5xLSxCt/LSyawyJIsF4ULOq0ntsDqe0Jd3MJadKdv3C+VT21PUEWFsGaS2jhuvGpkgl3EywaZcklJAh3cQmp0/LYwqJJd4IEi1xCgtqecFPBokl3HptYHM9h0UaqhNu5hIQnm1hUB4SbCRa5BR6sV2RdE+7mElKn5a+gcL10hgYrwv0Eizqtx1pA1PaE27mENOnO4x7CcRehOSyCLCyCtQ7CsUtI0wGEGwoWdVqPtbBosCLIwiLcZjAhl5BwN8GiOSw+Cxa3XUQgogR+BFlYBFttQ2ENBAkWQS4huYSE21pY5BJ6qktIFhbhfhYWdVoeKxa3g4lALKY6JtzMwqJJd/52EI4nxQVSKVUy4W4uIVlY/O0hHH8llMupjgl3cwnJwuKvR8ixSyiTUSUTZGER7tE25BISJFgEe23D9RwWuYSE27mENOlOFhZBuI1gETxWLK7nsMjCIqxHBAAPWx+isvIOuru7odPpYDabIRaLIZFIIBKJxvwnFoshFovAMAwEAsG4/wDAbDbDZDI9/Wc0/vKz2WyGTqPBo9XzYGEYWBgBLELmhZ8FsDAMwAggMJog1Bsh1o7AS9kD71YVGKOJWpKrEY1jl5Ahl5CwRbBa21rx3Xffw2wxu7YksyNsPqUvLhKSgWFMy6uEtG+QWpNcQmKqD6BNTU2uFysH0PvK0TtvGrWku7qEJFiELYIVEhLi9g8hHDFQS3KE2MeL+5tIJFTRhHWCFR8fjwXzF7jtA3i3qRF0p4VakovOIRZBJOc+sJPmsQhrETECBr/atQvJyUkoKbmFhw8fQqfX8bvUFgsUXf0IrH4In5ZuakWuDJ8AP+cIo58/zP39VOHE5IL15Ie4OXGImxMHAFCpVejo6IBKpUJXVzeUSiX6+vtc65poR6Bo74W3Ug0vZQ+EOnIDuUbq7+sclz4yEsaHZCUTNgjWswQHBSM4KPjp/5vMJly/fh35+ddhMjsnhEA0pENQVQvkKg2kPVowBiO1lrMtLDsE62HrQ5SXVyAhIR6zZ8+GkJk8LEIUHgEdVfeUwGA04PLlK/DyUiAxMRF+vuxa6SKrRkBGiFdfeRUhISE4lpHB+UMH1LYhtLQBjIHiq1yJPCzYpuPbO9rx44+HoDfoUVZehl/t2mXV/KgwPJwqe4pw8uQp3K29CwCorq7Bbz79lN3pA1sOnj9vPubPm8/tqD4whPCbdSRWPMB/3myrjzWajDh+/AT0Bv0vAtbeYd2oGRVFlT0FKL1d+lSsAKCrq4t1j8zmqMDk5CROH9q7TQ1YLNT6PCDABsEqLCyESq167nc9PT1WnSsMj6DKdnO0g1rk5uY99zuT2YR+lj+m2CxYM2bM4PTBZWoNtT4PEAiFCExKsOrYAc0A8vOvv/R7i5UDj3TpMjABAVTpbsylS5cxohuxuw9wJlhymfy5CXm2EQ3S9CsfmP3em5AG+lt17LVr+TCa7P8owsjl8Hn/Q6p0N0Xdo0ZFRYVT7mXXQjGFQsGdYA2RYLma4LREJP3dJ1Yd29Pbg7KyMofv6fMf9kPM8fwowQ2XL19x2vI+uwRLyuH6L8Zkph7gIiR+Pkj6L59izeH/a/WSnEuXLrPSWRkvL4T+cAiSpGRqCDfiUfsjVNdUO+1+IntO4lKwBCRYLhGq+E/2IG7fLoi9rLeelY+UrHZWob8/wk+cxvDlS+j/9y+hLy+jxuE5OTm5Tr0f7wQLZvpC6Ax858QgfNVihK9ajNDlC+1aM5idncNJ2eRr10G+dh2MnZ0YKbiOkcLrGCm4DnNvLzUcj6irr0NTcxP/BUskElFruRlCmRThq5cgamM6IlYvsTko9EXu191HC8fLaURhYfDeuQveO3fBYjZDV3wTg2czMXTxAiwa+prsSswW80thDLwVLMI9YKQSxO7cjKgN6QhbsQhCmZS1zupsV0DAMJAtXwHZ8hUI/OIfMVJwHYPnMjGcmwPLyAg1tpOpqKhAV3cXCRbBDtIgf7zyw/9BYGI869cuKyt7KUjUqeIlkTx1Gw0tzVD9/nMY7tZQozsJvUGPy5evuGYQpuqfmiT+7ceciNWIbgRXrlzlzXOKo2MQ9lMGrUd0IgUFhdBoXeOSk2BNQSQBfojdtYWTa+fk5EI7qOWX6yuXw+8//mdqeCfQrepGQUGB69qammDqwEglCFgQh/Sv/ieEEjHr129uacbtstu8fHavN9+C93sfQODjQx2BQ86cyXRaiqmx4N0c1sazX0NissCgHYJxcOjxf4dh0A7CoBl8+juDZhDG4RHAYoHFbIbFaILl8c8wm2ExW2AxmUb/Zn58jMkEi9ky+neLZfScxz+PnmOG2Wj65ZrPXANPrmGxjG5hxjAQiISjW5kxzOh2WI9/z4iEwJPtz0TC0WOFQggYwbg/g2HACB+fxwge//6Xe4z5M8NAEREKv/hY+MXPhPeMSM52uTEYDThzJpO3L5JAJELg3/8DAv/+H2Dq64OxpRnGpiYYWpphVqteCpexmF+I9xsr+PXFY8YIubG8eJ7ZiusAAMM87iOj29dBKBptu8d9AQLmaV+AUPTLz49/P/r/DCASAQLmaR96cu5L5z17zcf9DE+2znv2ms/8jfF7PpdVya0StLa1urSdeSdYiqgweHt501DGM65evYae3h63KKvQ3x9C/xRIk1Oo4Viif6DfJWEM5BISNtPe0Y6ioiKqCA/m7Nlzz+U6I8EieInRZMSpU6fdeu9KwjHKK8pR31DPi7KQYBETkp2dg86uTqoID0WlVuH8+Qu8KQ8JFjEu9+7fQ8mtEqoID7auMzKOw2Dkzw5VJFjEmHR1d+HkyVNUER7MmTOZ6Ojs4FWZSLCIlxgcGsThw0f4v6EuwRnX8q/hTtUd3pWLBIt4DoPRgKNHf3L5xrmE66iqrsLlK1d4WTYSLOIpRpMRR4/+5PLgQMJ13Lt/j9dTAZStgQAwuiXTzz8fQ+ODRqoMFjBbzNDr9TCbzZBIJBAJ+f+qNTQ24NixDF6HsJBgsURffx86OzvR29uL/v4BDAwMQKvVwmAwwGg0wmg0wmQyQSgUPvdPJBJBKpVCLpdDLpdDoZDD29sbAQEBCAwMZH2r7/Esq2PHMlBXX0cNaSUjuhEolUqo1Wqo1T1Qq9Xo7e3F0NAQ9Hr9S7sIMQIGEokEEokEYrEY3t7eCA0NRXh4GEJDQxEaGgqZVOay56mrr8PPPx9z6TpBEiwOR0+lUonGxkY0NTWjo6NjzD3ZWGkgoQjh4eGYMWMGYmKiERsbC4lYwtr19QY9jhw56vRUt+6G3qBHU1MTmpqa0dLSgvb2dlhgsanPjOhGnvYTdY/6pYytYaFhSE5OQmJiInx9fJ32bNU11Thx4qRbBAeTYNlAU3MTyssrUFdXh+GRYafc02gyok3ZhjZlG4puFEEqkSI5ORnLly9DYECgQ9ceHhnGoUOH0aZs48bq7OtDeUW5TecIBALIZDJ4eXkhICDApetKTWYTHjx4gMrKO7h//z7nS1M6uzqRk5uL3Nw8xMbGYvXqVYiNieX0nrfLbuPs2XM2ia8t1NbWwsvLy6ZzxGIxFAoFvLy8EBYa9nz/sNixNeuFrCwUlxRz8oB/97d/y6vFzyO6Edy6dQulpbd59eVMLBJj06aNWJy22K7zNVoNfvzxEK+j2IWMEMuWLcPGDRucel/toBY3btxEWVkZhoaHXFoHy5Yuw/r16yAWsZ8uqLCoEDm5ueAzoSGh2L377aebN5OFNQ6DQ4O4ceMmSkpKeBmPZDAacO78eUgkEiTbuJdfb18v/vrXH3mffcFkNqGwqBCLFi3kdLfxJ/QP9KOgoBBlZWUO7WTNJjeLb6KxsRF7976LAP8A1q6bd+kSrhdc5/172NXdhYKCQrz15pskWOPNNdy+fRt5eZdsmpcKCgxCbGwsgoIC4eXlBYVCAYlEgpGREQwPD0OlUqO1tRVtbW2svgwXLmRhwYIFEDJCq47vVnXjhx/+6rIUt/agVCo5FawnaZ9LSkqsnseRy+SYMWMGfHx84OvrA4FAAI1Gi56eHjQ1NbE6ed2t6sahQ4exf/+vIZfJHb7eufPncav0llu1/xNIsF6YQzh9+gwetT+y6ng/Xz+sXLkCCQkJVn/N0+l1uHPnDoqLS9Ct6mblZevq6kJEeIRVo9XBg985bf6NNWt3cJCza1feqbQ67TMjYJCSkoLExAWIjo4ed5AY0Y2gvLwceXmXWBucVGoVsrNznloa9nLy1ClU3ql02/YnwXpMRWUFzp07b9VCTz9fP6xZ8yqSkpKstmyeIJVIsThtMVJTU3Hjxg1cvnzF4U6t0WgmFSyzxYxTp067nVhxRU9vD06dOo2HrQ+tOn7+vPlYv36dVR86ZFIZli9bjlmzZrE6QJRXlCMtLRXToqbZdX51TbXbidWLeLxgmcwmnDt3HmVWboseHxeP7dvfctg0ZwQMVq5Yibi4OPz44yH0D/Rz+pylpaVWW458w9avTNa8uJmZZ62am5SIJdi5cwcS4hNsvk9oSCh27NiOw0eOsFb2goJC7Nm92+bzdHodsrIuun37e/TSnCcxSNaK1fp16/DuO++wMo/whJDgEOzf/2uEBIdw+qxDQ0Nu206RkZGsXMdgNCDz7FlkHD9ulVj5+/lj//5f2yVWT4ibE4c5s+ewVhf37t2za/5RIBBw6lo7q/09VrBGdCP4619/RENjg1XHb1i/HqvSV3FSFl8fX3z44QecBgsmJibCS+Hldu20dMlSVsRco9XgwIGDVu/680SsXowDsofly5exVh8WWFBfb3v2T4lYgtTUVLdrf38/f6xale7ZLqGti3yXLV2G9JXpnJbJx9sHe/bsxsGD33HyST0oMAh/8zef4+HDh2hvb4dOp4fBYIDBYMCLoXj19fWsxB+Fh4UjLc32l4RhGHh7eyMwMJAVsepWddvkdivkCrz//nvw8WZny7BZM2dBJpWxthqirq4eixYusvm8bVu3Ii0tFQ8fPsTAgOZp+5uf7Bz1mP7+fjS3NLNS1rVr1kChUNh8nlQqha+vL6Kiop6LQfNIwTp9+ozVDRIVGYUtmzc7pVxRkVHYtGkjzl/gJiWtXCZHfFw84uMm3hH6q6+/ZkWwAgIC7A5sZYuWhy04cuSo1WLBCBi8++47rIdRTJs2zWprfjJaW+3PphERHjHpB5q7tXdZE6wFCxYgKDCItXr0OJew6EYRqqqrrD5+y5bNTi1fWloaoiKjQDhOfUM9fvjhrzZZNsuXL8f0adNZL8v06dNYu5Z2UMv5Rxq+4lGC1dHZgby8S9aPDvMXcNJ5Jxvh33hjGwQQkOI4QFNzE3766WebAjgD/AOwZs2rnJQnMDCQ1et1dnrmxiAeI1gmswknTpy0qQMvWrTQJWUNDwtHUlISqY6dPGx9iMOHj9g8F7hp00ZO1uwBgK8vux9Uent7SbCmMuXl5ejq7rL6eLlMjpiYGJeVd/XqVWRl2UFPbw+OHDlq804vAf4BiI+P56xcPj4+7D5nDwnWlEVv0OPKlas2nTN79mybo9jZJDgoGPPnzycFsoHhkWEcPnzErsjyZcuWghFw9zp4e7ObgUSj0XhkG3uEYJWVlVm1VuxZ/P39XV7uZcuWkgrZQEbGcajUKpvPEzJCpKSkcFo2kYjdD/LuHAhMgjUJt26V2jEiuj7Icvq06ax+Ep7KFBQW2J2PPjo6mvP0xEJGyKqL765R6yRYk9Dc0mzXqMv2+jV7SUmZPNeVQODZc13KR0pcunTZ7vNnz57llHKyaWXp9XqPbOspL1h379badZ7JxI9k/MnJyZOOzGKxGJ6KyWzCqVOnHcpHPmuWcwRLKGRvTtRsNntke095wWpstM9N0On4kWXUz9cPcXFxEx4jkUjgqRQXFzuUV0wqkSI8LNwpZWXTEibBmoL0D/Tb5Q4CgFrNn/TBS5cumfilk0o9svNqB7U2f/19EbYyQTgbEqwpiCPRwM+mZXU1s2bOmjBpG1/m25xNUdENh3eyiYqiZVAkWDxBpVLZfW57ezuvsnO+9dabY8aFhYa4dgNOVzGiG0FpaanD14mJiSYVIMHii2Cp7T7XZDahpqaGN88SEhyCPXt2v7SJqj3pW6YClZWVDu9mxAgYzJgxg1TAjZjS6WUcDa67ceMmFi5c6NKI92eJmxOHzz//DPX19dDr9Zg+fbrTF2fzhaqqaoevERkZCalESipAgsUPHP3Sp1KrUFpaiqVL+BNx7ufrh7TUNI/utAOaAauTL07EzJkzSQHIJeQPbATX5eTkcraVO2EfbW3stMeCBbRWkwSLTw/HOP54T9Ipe2rCNH4KluNfcEOCQ1jJ124LfAlGJsHiKWzFJ2kHtTh06DCJFk9gIxdUUlKi08tNgkWCNSEyGXuf+7u6u/DNN9+67d5+U4nhYcfCTcQisUt2kGFz+3oSrClIQEAAq9fTaDU4ePA71N6rpZ7jQgwGg0Pnp6amOn3LM0dDMAgPEKyQkGD2XxajAT/9/DMuZmdzsh0XMTn2bBv1rHW1cuUKp5fZU9PBkGDZQHg4d4tab9y8ga+++hodnR3Ui5yMI9k7N27cwOmGtSRYJFh2ExoSymnn7Oruwtdff4OCwgKH0psQtmFvfvRZM2dhyeIlLilzX18fNRwJ1uTMnj2b0+ubzCbk5uXhq6++ZiWYkZicefPm2nxORHgEfvWrXS4rc0dHJzUcCdbkJCc7Z7usjs4OfHvgAE6dPm1z/njCRlc/LByxMbFWHx8VGYUPPngfcpncZWVmK9iVBGuKExMd49S86BWVFfjXf/0zikuKyU3kkK1bX5808Z5ELMHmTZuwf/+voZArXFbW/oF+tLS0UKOxgMgTHnLZsqU4f+GC0+43ohvBhaws3LpVis2bN2H2rNnU01gmOCgYH3+8Hzdv3kRraxu6urowNDQEHx8fBAQEYP78eZg7dy4vFjefP38BFlio0UiwrCM1NRUlJbccSqVrD92qbvx46BBmz5qNTZs2IjQklHocm51XKEL6ynRel7GwqBD36+5TY5FLaD1CRojXXtvisvs3NDbgyy//grPnzmFwiD5vewpNzU3Iy7tEFUGCZTszY2di2dJlLru/BRaU3i7FH//4J9y4eYOWaUxxqmuqcejQYZrHJMGynw0b1iMiPMKlZdDpdbiYnY0vv/wLGhobqAdOQfKv5yPj+HFaCUGC5RgioQh7974Lfz/Xb0OvUqvw46FDOHL0KHr7eqknTgGMJiNOnjqFS5cvU2WQYLGDj7cP3n//PXh7efOiPPfr7uPPf/435F/PpxHZjVH3qPHttwdQeaeSKoMEi12Cg4Kxf/+vERgQyJuR+dLly/jyy7+gqbmJeqWbUVVdhX//96/Q3tFOlUGCxQ0B/gHYv//XiJ7Bn22e1D1qfP/DD7iQlQWD0UC9k+cYjAacyczE8RMnHN4fkbAOkSc/vJfCCx999CGuXr2G/Px83gT3FZcUo6GhAW+//SunbaNO2EZXdxeOHcsYN7ZPKpFi6dKlSEiIR39/P/Lzr5MFRoLFgokpYLB2zRrExsbgxImT0Gg1vLG2vvnmW7z++mtYtHAR9VQeUVFZgXPnzo9rBc+YPgM7dmxHgP9oAsmoyCiEhobiyy//QuEs5BKyQ2xMLD777HdISU7hTZmMJiPOZGbi1OnT5CLypD0yz56dsD3SV6Zj376PnorVE4KDgpGQkECVSILFHnKZHNvfegvv7d3rkiRvE43oBw4cpCh5F9Lb14tvvz2A22W3xz3mtS1bsGH9ejCCsV+r8PAwqkiTQsXdAAAUZElEQVQSLPaZM3sOPvvsd1icthgCCHhRpvaOdhw4cJB27nEBdfV1+Oqrr8edgxIyQuzauXPSDXfDwkiwSLA4QiaVYevrr+OTTz5GZEQkL8qk7lHjwIGDUKlV1EBO4vKVKzh85AiGR8beqYcRMNi9+20kLph82zC2N0UhwSJeIjIiEh9/vB+vv/YaZFKZy8vTP9CP7777Hn39lHKXS0Z0Izh85Aiu5V8b9xgBBNi1ayfi4+KtuqZIJKKKJcFyQiUJGCxZvAS///3fIC01zeVuonZQi8OHj9DWURzR1d2Fr776GnX1dROK1Y4d2zF/nvXb3ZNgkWA5FS+FF7Zt3Yrf/OZTxETHuPylOnYsg7IBsMzd2rv45ptv0dPbM+Fxb7yxDUmJtqXfJsEiwXIJ4WHh2PfRR9ize/dLn6+dSUNjA+VbYpHLV67g52PHJo1af23LFrti40iwHIdq0AHmJszFnDlzUFJSgmvX8jGiG3F6GYqKijB//jxERUZRg9iJwWjAqVOnUXO3ZtJj161dO+nXwPEQCoVU2WRhuVjxhSKsWL4Cf/jD77Fk8ZJxY3C4wgILTp8+QxHUdqLRanDw4HdWidWK5SuwetVqqjQSLPdHIVfg9ddew2ef/c7pm050dXehoKCAGsFG2jva8fXX3+BR+6NJj01JTsGmjRup0kiwphbBQcF4/733sPvtt+Hn6+e0+xYUFI4bK0S8TENjAw4e/A4DmoFJj42bE4c333yDKo0Ea+oyb+48fP75Z0hfme4UN1Fv0KOkpIQq3grKK8px+PARq1LCBAUGYdeunU539QkSLKcjEUuwYf16fPLJx07Z4uvGjZuUl2kSrl67itNnzlgVDiIWibFnz25e7G1IkGA5jYjwCHz66SdYlb6K06DT4ZFhVFZSit7xuJCVhStXr1p9/LZtW1kdaCwW2kyVBMtNEAlFWL9uHfbufZfTEbu6uoYq+wXMFjPOZGaiuKTY6nPi4+KRnJTMajkMBkoRRILlZsyZPQeffPIxZzv3tLS0QDuopYp+RqxOnjyFsvIyq8+RSWXYtm0r62UxGmmTERIsNyQ4KBj79n3EiWhZYMG9e/eokh9z+vQZVFVX2XTOxo0b4OPtw3pZyMIiwXJb/P38sW/fR5wkCmxoaKQKBnD+wgWbt90KCQ7BwoULOSkPCRYJltuL1p49uyESsrtCqrOz0+Pr9vKVKyi5ZXuYx4YN6zkLYSDBIsFye6Iio7B16+usXrOnt8ejwxuqa6onzGM1UVtYm9vKHmgOiwRrSrAwZSES4tndoMBTraz2jnacPn3GrnOXLVvKadkGByknPwnWFGHbtq2Qy+SsXa+vz/6MpAIBO7FiZrNzc3XpDXocO5Zh1w5D3l7emD9/Pqfl6+3tdYu+yFb7A+zHnpFg8QRvL2+kp69k7XojI/anumEYhpeddTKys3MmTbw3HsnJyRAy3KZ/6enxPMFie9Ca8vmwzBYzampq0NamhJeXAjExMZgxfQYvy7pkyRIUFd1gZTsvRwTLHS2spuYmlN4utfv8uXO53zPQXSwstgYsLgatKS9YJ0+eeikOZ9HCRdi2bSvvFrRKxBKkpqYi/3o+C4Klc3mHdZZgmS1mXLiQ5ZB1O33adM7L6YibThaWB7iE6h71mEGDZeVlyM/P52WZU1LYWQ7iyCd0d3MJb9++ja7uLrvPj4mJcYqouotgsWlhkWDZQHNz87h/u3r12rgbY7qSoMAgVvZBFIvFdp/LVipfZ1hYRpMR+fnXHbpGZGQE5+Xs7Ox0mw1D2EzlTJPuNvDo0fiCZIEF167x08qKjY11+BpSqcQlYudsC6uiosKqJHwTERHBvWBNNHjybTBgq/3JwrIRnW7ieZzae7XoVnXzrtwxMdEu7XRsdVhnBErevFns8DV8fHw4L+eDB02sXs9k4i6HP5uCxXY5p7Rg6fWTR3sXFhbxrtzh4eEOX8Pb23vKC1ZrWysrA45Mxu2O3maLGS0tLR5pYbG9HMmjLSwAqKqqYiWMgE18fXwhFjnWaQIDA13eYbleO1dRwU6yQq73C2xvb2d9l24ud0kiweKxhWU0GXH79m3eld3f37HUM44Ilkwm5WVnfZG6ujpWruNIzJo11NTc5cxy4wKplL0Ek2xb2VNasKyd9C0pucW7ff0UCoXd53opvBxa5sOWi8SlYHV2dTo82f6E4WHudhsyGA0oKyvj5NpcCa1YJGYtgwhZWByg0Wpw9+5dXpXJkVEuOtqxSXu5XM7LzvosbW1trF1LrVZzVs7q6mrOtl/j0jLk66BFgvUYNr428WUeYebMWF50VrPFzMrcTc3dGvT2Pb+sRal8xFpdNzU1u2W/cgfBGhpyXKy7Vd2ob6iHyWya+ktzrB6xlW1QPlIiKjKKF+Wx5oPBeDgax+WIO/oiWq0W0kD7rEWdXofjx0+grr4OAgjw29/+BmGhYaOduJu9cJTGRm4ytDY+aERHZwdnfWRoaMghl/pJXY45reDlBZVa5bj3otE4ZqHWVOP06TMwGA1ISU4hC4uvVpa9nTEsNAzBQcEO3dvPj70dqx3psCdPnkJd/ejEugWW5ybZ2Vzm0tff9/Q+bKE36JGZeZbTPmLvYuozmZn48i9/wY+HDo17jK8vO6m7tVr7N0RpediCEydOPk0XVFtbS4L1LFVVVayMKq4UrIULUxy+t7e3N2sLw+3tsAWFBbh3/96YL5HZYnZ45H4RtuPxcnJy0dfP7dpBtdr2VDrFJcVPdxBqaGwY1wJ0tWBptBocO5bx3JdQPz8/EqxnscCCK1euuq1gMQIGSUlJDt+bETAOBZ4+S0+P7S9VU3MT8vIujWv56XQ6WMDusp/mlmaH0tM8y4OmB7hVeovzPmJrVlmVWoWcnNznrZhxAlr9/f1c1v4mswkZGcdf2q6OBGscn5nLeQdr6FZ125WTPSkpCV4KL1bKEBAQwMp1JlrPORYDmgFkZBwfU5CelMma+Dp7uHgxG51djqWWbnzQiKNHf3JKP2lpabH6o4bJbMLJk6dgND0fFzVexDxb7a/T66Duse0rbG5uHloetoxZJrsEa6pvuX358hWX3r+1tdUuq+iVV1azVoaQkBBWrqNUKq0+1mgy4qeffh5z5UFEeAT8fEdHfTbzNT2LwWjAd999D+UjpV3n36m6g0OHDjttAxCT2YSKigqr+/RYzzWe68dW+9vaB6qqq3Dj5o0x/zZ3boJ9gsXlwks+cL/uPpqam1x2/5aWhzafk5ycjMCAQNbKEBrKTocd0Azgft19q449e/bcuGKRnPyLq8tWnNhYDI8M4/vvf0BxSbHVkeS9fb04e+4cTpw8OeY5UokUsTGxrG/nBgB5eZcmtQpvFt9EQWHBmH8bT7D8/fwdXh72hJIS69xj5SMlzpzJHPNvPt4+iImJsS+sgctFrXzZuy0z8yx+97vfstZo1mK2mPHgwQObzpHL5Fi/fh2r5QgNDWXtWrm5eYiOjoZMKhvXsjl58hTu1o4dvCuAAAsWLHj6/2KRGGKR2K7NJqxBb9DjQlYWSktvIzV1EebOnfvUunuCRquBSqVCaelt1NTUjDunlpKcgs2bN0Euk6OruwvffnuA1XWFeoMe33zzLdatW4vk5GQo5L+EpHR1d+HatXxU11SPa5UHBwdPaGU/anc83q21rRV3qu4gKXH8+dW6+jpkZBwft00TExPBCBgSrPHo6e3B1avXsGH9eqfet7a21uYlJ6+9tgXeXt6sliMyMhICCFiZ3O5WdePQocPYvv0tBAUGPfe3hsYG5OTkTmglzJ8//6Wt4xUKBfoH+jlti67uLmRdvIisixchk8qefojo6+t7aS5oLDZt3IgVy1f8MgiEhGLbtq04fuIE667sxexsZGfnwMfHBwqFAgMDAxganvjDzcyZMydcwjVt2jRWBAsATp06DaPRiJSUlOe+QA8ODSI//zqKi4vH7WuMgEFaWioAO3O6OxJbMemIoefPBqBFRUVITFyA8LBwp93zxo2bNh2fEJ8w4chlL1KJFKGhoQ5PQj87yv75z/+GmJgYBAUFQafTob29fdL0MCKhCBs2vDxoBAQEcC5YzzKiG8GIzvrI8je2bUPqotSXLYUFibh1q3TMSWVHscCCAc2A1QPeggUTb2s2ffo0u3bPHs9zOJOZifz865g2bRrkcjlUKhXa2tomnfNbunTp04HOrjms/v5+jxAss8WMY8cybOqoDs1dPWxBa5v1E+7BQcHYvv0tzsozffp01uvzySf/O1V3rMpltXz5cvj7vZy5wtH1klyyft26McXqCWMJsLMRi8RISJh4p6AZM9jfXaq3rxdV1VUouVWCB00PJhUrhVzx3MckmwVLb9BjYGCAs4pkc30UG1+T1D1qZGQc5zwft96gt2nHYplUhnfffWfceSE2iIub49KXytvLG6tWpY/5t+honm7VtngJVqWvmnggmDbdKbv0TMSKFSsmzejh7+fv8KoJR1mz5tXnymmzYCmVSk5fXjYXtbK1Jq6hsQG5uXmcNkxW1kWrNwEVi8TYs2f3S/NBbBMby82XLasGGwiwY8d2SCXSca0/vm3TFjcnDlu2bLbq2JUrV7isnD7ePlZv2hsXF+eycs6eNRtLFi957nc2t/jdu7WcFtKeGKRxG4bFXN1FN4pwLf8aJ89cVl72dLnEZEjEErz//nuIjYnlvMNIxBKXddh169Zi1sxZE5bt2S+HriYiPAK/+tUuq0U0Pj6e8wFnorqViK3bpGSyeS6u8Pfzx65dO1/6vU2Cpe5Ro7y8nNOCKpXKSb9uuEKwAODylSu4kJXF6jVvFt/EmcxMq46Vy+T48MMPED3DefM3S5cucXpnjY+Ln9StcrWV8iy+Pr7Yu/ddq0UAGP3yZa2Vw7YVuDBlodXHR0VGOT2DiUgowp49u8d0Wa0WrNa2Vnz77QHOYl+eYDQZWVvlPmMG+/MExSXFOJaR4bCoGk1G5F26hKyLF606PjwsHJ9++gmmRU1zaueJiY5BRHiE0+4XFBiEHTu2W10nM2NnulSsFHIF3ntv70thF9aQlJRk13mO1O3OnTtsPm/FiuVOrdNt27aO2+eEX3zxxRcTndzT24OiGzdw9uw51hPpj4dKpYJOp0N0TDSEjP2bOvr7++PWrVLWRba7uxvlZeXw9fVBWFiYzeffr7uPo0d/sjoCPDkpGe+8s4e1dYI2d/TgIFRUVnJ+n+CgYOzb95FNzxkREY7y8gqXbFLq4+2Dffs+QmiIfUG2DMPAAgsabQwUtte9//DDD14KgLWG0NBQ1NfXs54hYyy2vv76hF9YxxQsg9GAqqoqXMjKQnZODloetji9Q7S1taGqqhpCkRAmkwkSqcTmqHNGwECj0aBN2cZ6+QxGA2pra1FXVweTyYjAwMAJs4Q+caezs3NQWFRkVdpcH28fbH/rLaxetdoh4XaUAP8A9Pb22pwdwBZCgkOwb99HNlsc3l7e8Pb2wv26OqfWSVBgED788AOHv6KFhYXhzp0qhxI2ToaQEWL37rcxY7r9X1YjIiNQWVHJqQ68sW0b0lLTJjxGYHlmJXO3qhulpbdRUVHhtNgjW+cKoqKiMGPGdCQnJ1s1Eo/oRvDVV19b/QXOXhgBg/DwcPj5+cHPzw8CgQBarRYajQb9/f0vpfidsFEgQFpaGtavX8dp2IKtAn3gwEG0d7Szfu3QkFB89NGHDlmQx0+cQFV1lVPqYs7sOdi1aydrbaN8pMSBAwc52QhFIpbgnXf2sOI6V1RW4NTp06yXUQAB3nzzDavm1gQms8lSX1+PmzeL8aDpAdwFsUiM9PSVePWVVyc9tqOzwynzb2w0XFJSEl55ZbXLviBNxNDwEH788RBryzWeuLuvvbbF4ZffZDbh7NlzKK/g7qMQI2CwZs2rSE9PZz2kovR2Kc6eO8fqNeUyOd57by+r854lt0pw/sIFVo2Q7dvfslpQhevWrfsi8+xZmywAPmA2m9Hc3AypVDJpRLa3tzfmzpuL1tY2TpcV2YtMKsPChQuxc+cOpC5a9NwCVl4NEmIxEhMXoLe3D13dXQ6/TDt37MDqVatZ2ciUETBISEiAUMigqYn9TBthoWHYu/ddLJi/gJP0NpGRkYiICEdjQyMra3WnRU3D3r3vsr6sLCoqCuHhYWhsfOBwORMXJGLv3ndtmgMU/NM//7OFq22InEF4WDh++5vfWD0KFxcXo6ysnJUtzh2dV4iJicHChSlISEhwelYIR6m5W4OrV6/ZLFwSsQSJiYlYs+ZVzr6QNTU3IScnlxVL0M/XD2vXrkFSUpJTAlX7B/qRkXHcpiVaL9bvhg3rkZaWxml5BzQDuHz5Cu7cuWOzKxsVGYX09JWYN3ee7V7Id99/b3Fl7ieHR6aISHz6ySc2n9fe0Y7q6hq0tbWho6OD8zk7ISNEaGgooqOjMXv2LMTExLidSI3Fg6YHqKm5i4aGhnFzmDMCBmFhYUhNXYSkpKRxo9fZprqmGgUFhTbPuwkgQHR0NJYsWTxqtTn5g4fZYkZDQwOKi0vQ0Nhg1TneXt5ISkrCsmVL7foS6Ihw1dTUoLb2HpRK5bhZLBRyBRISErB4cRoiIyLtnzbRDmotBQWFUCqV6O/vh8FggF6vh9FoBMMwEAqFEIlE4/73xZ9FIhEYhnlqNgsEgqc/WyyWcf+ZTCYYjcZx/z0pl8FggFgshkKhQGRkJNatW8vKeqe+/j50dHSgr68PWu0gBgd/+Tc8PPy0HE/L+UzDiISjzy0WiyGXy+Hr6wsfHx/4+voiKCgQ4eHhCA4OdumXPmcwohuBWq3G8PAw9Ho95HI5AgIC4Ovr69JlNBqtBg0NDWhsfPC4fbXQarUwGA0Qi8RPyxkSEoLp06dhzpw5LgsheRF1jxqVlXegUqnQ09ODnp4eGI1G+Pr6wt/fH4GBgZg7NwGzZs1y+VIls8WM3t5eaDSa0bz7Fgv8/f0REBDA2iD13FdCgiAIPvP/Ab3AiTxiS5XhAAAAAElFTkSuQmCC")

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
        "tools in sequence and return the final answer. Never say \'Should I look that up?\' or "
        "\'Do you want me to search for that?\' — just do it.\n\n"
        "DECISION TREE — follow this for EVERY statistics question:\n"
        "1. search_datasets(query) — find the dataset ID. Call this first.\n"
        "   If no results: try Italian keywords (population→popolazione, employment→occupazione).\n"
        "2. get_dataset_structure(dataflow_id) — get dimensions and key_filter_template.\n"
        "3. get_dimension_values(dataflow_id, dimension_id, search=...) — look up codes.\n"
        "   ALWAYS call this for REF_AREA (territory) before fetching data.\n"
        "   ALSO call this for SEX, AGE, DATA_TYPE etc. to find \'total\'/\'all\' codes.\n"
        "4. get_dataset_data(dataflow_id, key_filter=..., last_n_observations=5) — fetch data.\n\n"
        "CRITICAL — DIMENSION PINNING (prevents timeouts and context overflow)\n"
        "ISTAT datasets have many dimensions (territory × sex × age × marital status × ...).\n"
        "If you wildcard everything, the response will contain THOUSANDS of rows and be truncated.\n"
        "ALWAYS pin dimensions you don't need broken down:\n"
        "- Use get_dimension_values to find the \'total\' or \'all\' code for SEX, AGE, etc.\n"
        "- Only wildcard the dimension the user actually wants to compare across.\n"
        "- Example: user asks \'population of Bologna\' → pin SEX=total, AGE=total, "
        "MARITAL_STATUS=total → get ~1 row per year instead of 15,000.\n"
        "- Example: user asks \'unemployment by region\' → pin SEX=total, AGE=total, "
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
    icons=[_ISTAT_ICON],
)

# ─────────────────────────────────────────────
# Register tools  (requires_permission=False → Intric executes automatically)
# ─────────────────────────────────────────────

mcp.tool(name="search_datasets",       meta={"requires_permission": False})(search_datasets)
mcp.tool(name="get_dataset_structure", meta={"requires_permission": False})(get_dataset_structure)
mcp.tool(name="get_dimension_values",  meta={"requires_permission": False})(get_dimension_values)
mcp.tool(name="get_dataset_data",      meta={"requires_permission": False})(get_dataset_data)

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
