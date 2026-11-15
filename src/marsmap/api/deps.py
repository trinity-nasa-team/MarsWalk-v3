"""Errores de API, límites de uso y dependencias compartidas."""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Annotated

from fastapi import Depends, Path, Request

from marsmap.api.registry import RegionData

log = logging.getLogger("marsmap.api.deps")

REGION_ID = Annotated[str, Path(pattern=r"^[a-z0-9_]+$", max_length=64)]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class LruCache:
    """Caché LRU de tamaño fijo (acota la memoria aunque lleguen parámetros arbitrarios)."""

    def __init__(self, size: int):
        self.size, self._d = size, OrderedDict()

    def get(self, key):
        if key in self._d:
            self._d.move_to_end(key)
            return self._d[key]
        return None

    def put(self, key, value):
        self._d[key] = value
        self._d.move_to_end(key)
        while len(self._d) > self.size:
            self._d.popitem(last=False)

    def __len__(self):
        return len(self._d)


def client_ip(request: Request) -> str:
    # Sin confiar en X-Forwarded-For: cualquiera podría falsearlo para evadir el límite.
    # Excepción: en Vercel el cliente ASGI es el proxy (todos compartirían un límite); ahí Vercel sobrescribe
    # x-real-ip / x-vercel-forwarded-for con la IP real, y el cliente no puede falsearlas.
    if os.environ.get("VERCEL"):
        ip = request.headers.get("x-real-ip") or request.headers.get("x-vercel-forwarded-for", "")
        if ip:
            return ip.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_compute(request: Request) -> None:
    if not request.app.state.limiter.allow(client_ip(request)):
        raise ApiError(429, "rate_limited", "Demasiadas solicitudes; espera un minuto.")


def limit_mission(request: Request) -> None:
    if not request.app.state.mission_limiter.allow(client_ip(request)):
        raise ApiError(429, "rate_limited", "Demasiadas misiones solicitadas; espera un minuto.")


def get_region(request: Request, region_id: REGION_ID) -> RegionData:
    registry = request.app.state.registry
    data = registry.get(region_id) or _rebuild_site(request, region_id)
    if data is None:
        raise ApiError(404, "region_not_found", "Región no encontrada.")
    return data


def _rebuild_site(request: Request, region_id: str) -> RegionData | None:
    """Un sitio creado con POST /sites vive en la memoria y el /tmp de UNA instancia. En serverless la siguiente
    petición puede caer en otra: el id es determinista, así que se reconstruye aquí en vez de responder 404."""
    from marsmap.terrain.site import build_site, parse_site_id  # noqa: PLC0415

    center = parse_site_id(region_id)
    if center is None:
        return None
    state = request.app.state
    try:
        region = build_site(*center, state.settings.data_dir, state.site_dem)
    except Exception as exc:  # noqa: BLE001 (red/GDAL: cualquier fallo es "no disponible", nunca 500)
        log.warning("no se pudo reconstruir el sitio %s: %s", region_id, type(exc).__name__)
        return None
    return state.registry.load(region)


RegionDep = Annotated[RegionData, Depends(get_region)]
