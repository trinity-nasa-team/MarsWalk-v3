"""Sitios en cualquier lugar de Marte (016): región temporal alrededor de un hábitat elegido.

Relieve: DEM global MOLA–HRSC Blend 200 m v2 de USGS, leído por ventana remota (`/vsicurl/`): se
transfieren solo las filas del recorte (~20 MB) y se guardan capas pequeñas (~1 MB) en
`data/processed/<site_id>/`.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from marsmap.config.regions import Region
from marsmap.terrain.build import build

GLOBAL_DEM = (
    "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/"
    "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif"
)
GLOBAL_INFO = ("Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2 (USGS)", "MGS MOLA + MEX HRSC")
HALF_KM = 22.0  # radio de regreso a pie (10 km) + margen para rodeos
MARS_R_M = 3_396_190


def site_id(lat: float, lon: float) -> str:
    """Id determinista y seguro (solo [a-z0-9_]) a 0.01° (~600 m)."""

    def f(v: float) -> str:
        return ("m" if v < 0 else "p") + f"{abs(v):.2f}".replace(".", "d")

    return f"site_{f(lat)}_{f(lon)}"


SITE_ID_RE = re.compile(r"^site_([mp])(\d{1,2})d(\d{2})_([mp])(\d{1,3})d(\d{2})$")


def parse_site_id(sid: str) -> tuple[float, float] | None:
    """Inverso de site_id: (lat, lon) del centro, o None si no es un id de sitio válido."""
    m = SITE_ID_RE.match(sid)
    if not m:
        return None
    lat = (-1 if m[1] == "m" else 1) * float(f"{m[2]}.{m[3]}")
    lon = (-1 if m[4] == "m" else 1) * float(f"{m[5]}.{m[6]}")
    if not (-85 <= lat <= 85 and -180 <= lon <= 180):
        return None
    return lat, lon


def site_bbox(
    lat: float, lon: float, half_km: float = HALF_KM
) -> tuple[float, float, float, float]:
    dlat = math.degrees(half_km * 1000 / MARS_R_M)
    dlon = dlat / max(0.05, math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def build_site(lat: float, lon: float, out_root: Path, source: str = GLOBAL_DEM) -> Region:
    """Construye (o reutiliza) las capas de terreno del sitio. Devuelve la región."""
    # Centro redondeado a 0.01° (como el id): cualquier instancia que reconstruya el sitio obtiene la misma región.
    lat, lon = round(lat, 2), round(lon, 2)
    sid = site_id(lat, lon)
    region = Region(
        region_id=sid,
        name=f"Sitio {lat:.2f}°, {lon:.2f}° E",
        bbox=site_bbox(lat, lon),
        description="Región temporal creada desde el DEM global MOLA–HRSC 200 m (USGS).",
    )
    if not (out_root / sid / "metadata.json").is_file():
        build(sid, out_root, source=source, source_info=GLOBAL_INFO, region_obj=region)
    return region
