"""Aplicación FastAPI de Mars Scout."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from marsmap.api.deps import ApiError, LruCache
from marsmap.api.ratelimit import RateLimiter
from marsmap.api.registry import Registry
from marsmap.api.routers import assistant, eva, habitat, mars, missions, regions, routes, sites
from marsmap.api.settings import Settings
from marsmap.data.mars_pois import http_get
from marsmap.data.space_weather import SpaceWeather
from marsmap.terrain.site import GLOBAL_DEM

log = logging.getLogger("marsmap.api")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": message, "code": code}, status_code=status)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Mars Scout API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.registry = Registry(settings.data_dir)
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.mission_limiter = RateLimiter(settings.mission_rate_limit_per_minute)
    app.state.chat_limiter = RateLimiter(settings.chat_rate_limit_per_minute)
    app.state.costmaps = LruCache(4)  # ~28 MB c/u en Jezero: con 16 llegaba a ~450 MB
    app.state.plans = LruCache(8)
    app.state.mars_pois = None
    app.state.mars_fetch = http_get  # las pruebas lo sustituyen (sin red)
    app.state.space_weather = (
        SpaceWeather()
    )  # DONKI con caché de 1 h; las pruebas sustituyen su `fetch`
    app.state.llm_chat = habitat.groq_chat  # idem: la IA del hábitat se finge en pruebas
    app.state.llm_json = (
        assistant.groq_json_chat
    )  # asistente de voz: LLM en modo JSON (se finge en pruebas)
    app.state.llm_transcribe = (
        assistant.groq_translate
    )  # asistente de voz: Whisper → inglés (se finge en pruebas)
    app.state.site_dem = GLOBAL_DEM  # idem: DEM local sintético en pruebas

    # Respuestas grandes (terrain-grid.f32 ~4.3 MB) bajo el límite de 4.5 MB de las funciones de Vercel.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _err(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # Mensaje genérico con los campos afectados; no se devuelve el valor recibido.
        fields = sorted(
            {".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()}
        )
        return _err(422, "validation_error", f"Entrada inválida en: {', '.join(fields)}")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _err(
            exc.status_code,
            code,
            "Recurso no encontrado." if exc.status_code == 404 else "Solicitud no válida.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("error no controlado", exc_info=exc)  # el detalle va solo al log
        return _err(500, "internal_error", "Error interno del servidor.")

    app.include_router(regions.router, prefix="/api")
    app.include_router(routes.router, prefix="/api")
    app.include_router(eva.router, prefix="/api")
    app.include_router(missions.router, prefix="/api")
    app.include_router(mars.router, prefix="/api")
    app.include_router(sites.router, prefix="/api")
    app.include_router(habitat.router, prefix="/api")
    app.include_router(assistant.router, prefix="/api")

    if settings.frontend_dist and settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
