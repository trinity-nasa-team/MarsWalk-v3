"""Puntos de interés de todo Marte (016): Zonas de Exploración para humanos (NASA 2015) y nombres IAU.

Fuentes (NASA Mars Trek, verificadas 2026-11-14):
- EZMars (ArcGIS): 51 Zonas de Exploración del «First Landing Site/Exploration Zone Workshop» (2015).
- Índice de Trek `itemType=nomenclature`: 1 783 nombres oficiales de la IAU.

Se piden una vez y se guardan compactos en `data/raw/mars_pois.json` (~100 KB). Longitudes a −180..180 E.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path

from marsmap.geo.coords import normalize_lon
from marsmap.terrain.fetch import check_url

log = logging.getLogger("marsmap.mars_pois")

EZ_URL = (
    "https://trek.nasa.gov/mars/trekarcgis/rest/services/EZMars/MapServer/0/query"
    "?where=1%3D1&outFields=name,lat,lon,elev,abstract_l&returnGeometry=false&f=json"
)
NOMEN_URL = (
    "https://trek.nasa.gov/mars/TrekServices/ws/index/eq/searchItems"
    "?proj=urn:ogc:def:crs:EPSG::104905&start=0&rows=3000&facetKeys=itemType&facetValues=nomenclature"
)
POINT_RE = re.compile(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")

Fetcher = Callable[[str], bytes]


def http_get(url: str) -> bytes:
    check_url(url)
    req = urllib.request.Request(  # noqa: S310 (https y host en lista blanca: check_url)
        url, headers={"User-Agent": "marsmap/0.1 (NASA Space Apps)"}
    )
    # timeout 15 s: son 2 peticiones y la función de Vercel tiene maxDuration 60 s
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return r.read()


def parse_zones(raw: dict) -> list[dict]:
    out = []
    for f in raw.get("features", []):
        a = f.get("attributes", {})
        try:
            lat, lon = float(a["lat"]), normalize_lon(float(a["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        out.append(
            {
                "name": str(a.get("name", "")).strip(),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "elev_km": a.get("elev"),
                "url": a.get("abstract_l") or None,
            }
        )
    return out


def parse_nomenclature(raw: dict) -> list[dict]:
    out = []
    for d in raw.get("response", {}).get("docs", []):
        m = POINT_RE.search(d.get("shape", ""))
        if not m:
            continue
        lon, lat = normalize_lon(float(m.group(1))), float(m.group(2))
        out.append(
            {
                "name": str(d.get("title", "")).strip(),
                "type": str(d.get("productCat2", "")).strip(),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
            }
        )
    out.sort(key=lambda p: p["name"])
    return out


def load_mars_pois(cache: Path, fetch: Fetcher = http_get) -> dict:
    """Devuelve {exploration_zones, nomenclature, sources}; usa la caché si existe."""
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("caché de POIs ilegible; se vuelve a pedir")
    data = {
        "exploration_zones": parse_zones(json.loads(fetch(EZ_URL))),
        "nomenclature": parse_nomenclature(json.loads(fetch(NOMEN_URL))),
        "sources": {
            "exploration_zones": "NASA Mars Trek · EZMars (First Landing Site/Exploration Zone Workshop, 2015)",
            "nomenclature": "NASA Mars Trek · nomenclatura IAU (Gazetteer of Planetary Nomenclature)",
        },
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
