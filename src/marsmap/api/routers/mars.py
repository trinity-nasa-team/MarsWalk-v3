"""Datos de todo Marte (016): puntos de interés globales y clima espacial (DONKI), servidos desde caché."""

from __future__ import annotations

import logging
import urllib.error

from fastapi import APIRouter, Request

from marsmap.api.deps import ApiError
from marsmap.data.mars_pois import load_mars_pois

router = APIRouter()
log = logging.getLogger("marsmap.api.mars")


@router.get("/mars/pois")
def mars_pois(request: Request) -> dict:
    """Zonas de Exploración (NASA 2015) y nombres IAU de todo el planeta (lon −180..180 E)."""
    state = request.app.state
    if getattr(state, "mars_pois", None) is None:
        cache = state.settings.data_dir.parent / "raw" / "mars_pois.json"
        try:
            state.mars_pois = load_mars_pois(cache, state.mars_fetch)
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            OSError,
            KeyError,
            TypeError,
        ) as exc:
            log.warning("no se pudieron cargar los POIs de Marte: %s", exc)
            raise ApiError(
                502, "upstream_unavailable", "No se pudo consultar NASA Mars Trek."
            ) from exc
    return state.mars_pois


@router.get("/mars/space-weather")
def space_weather(request: Request) -> dict:
    """NASA DONKI resumido: SEP cerca de la Tierra (72 h) y CME con llegada MODELADA a Marte (30 días).

    Nunca falla: si CCMC no responde, devuelve la copia incluida con `status: "snapshot"` y su fecha.
    """
    return request.app.state.space_weather.get()
