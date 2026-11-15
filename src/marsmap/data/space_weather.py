"""Clima espacial de NASA DONKI para el panel de radiación (servido por el backend, sin clave en el navegador).

Fuente: NASA CCMC DONKI API (`https://ccmc.gsfc.nasa.gov/DONKI-API/get/{SEP|CME}`), sin clave; el rango máximo
por consulta es de 60 días. Antes, el navegador consultaba `api.nasa.gov` con DEMO_KEY (≈10 consultas/h por IP):
en un wifi compartido el panel mostraba "DONKI no disponible".

Qué se resume y cómo se etiqueta (ver `06-datos/donki/README.md`):
- **SEP** (partículas solares) de las últimas 72 h. Son detecciones **cerca de la Tierra** (GOES, SOHO, STEREO-A);
  DONKI no reporta SEP medidos en Marte. No decir que "llegan a Marte".
- **CME con llegada a Marte**: impacto **modelado** por WSA-ENLIL (`enlilList[].impactList[].location == "Mars"`),
  no medido. Se da la más reciente y cuántas hubo en 30 días.

Si CCMC no responde, se sirve la copia incluida (`donki_snapshot.json`, descargada el 2026-11-14), marcada como tal.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marsmap.terrain.fetch import check_url

log = logging.getLogger("marsmap.space_weather")

BASE_URL = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
SOURCE = "NASA CCMC DONKI (ccmc.gsfc.nasa.gov/DONKI-API)"
SEP_WINDOW_H = 72
CME_WINDOW_D = 30
TTL_OK_S = 3600  # una consulta por hora por instancia
TTL_FAIL_S = 300  # si CCMC falla, no reintentar en cada petición
SNAPSHOT = Path(__file__).with_name("donki_snapshot.json")

Fetcher = Callable[[str], bytes]


def http_get(url: str) -> bytes:
    check_url(url)
    req = urllib.request.Request(  # noqa: S310 (https y host en lista blanca: check_url)
        url, headers={"User-Agent": "marsmap/0.1 (NASA Space Apps)"}
    )
    # 6 s por socket: las dos consultas van en paralelo, así que el peor caso en frío es ~6 s, no 16 s.
    with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310
        return r.read()


def _url(kind: str, start: datetime, end: datetime) -> str:
    return f"{BASE_URL}/{kind}?startDate={start:%Y-%m-%d}&endDate={end:%Y-%m-%d}"


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    # Sin zona (p. ej. "2026-11-09T18:15"): DONKI siempre es UTC. `astimezone` sobre un naive usaría la hora local.
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def mars_impacts(cmes: list[dict]) -> list[dict]:
    """CME con llegada a Marte según WSA-ENLIL. Usa el análisis `isMostAccurate` si lo hay."""
    out = []
    for c in cmes or []:
        analyses = c.get("cmeAnalyses") or []
        best = [a for a in analyses if a.get("isMostAccurate")] or analyses
        hits = [
            i
            for a in best
            for en in (a.get("enlilList") or [])
            for i in (en.get("impactList") or [])
            if i.get("location") == "Mars"
        ]
        if not hits:
            continue
        arrivals = sorted(i["arrivalTime"] for i in hits if i.get("arrivalTime"))
        out.append(
            {
                "id": c.get("activityID"),
                "start": c.get("startTime"),
                "arrival": arrivals[0] if arrivals else None,
                "glancing": all(bool(i.get("isGlancingBlow")) for i in hits),
            }
        )
    return sorted(out, key=lambda x: x["start"] or "")


def summarize(seps: list[dict], cmes_mars: list[dict], now: datetime) -> dict:
    sep_from = now - timedelta(hours=SEP_WINDOW_H)
    cme_from = now - timedelta(days=CME_WINDOW_D)
    sep = [
        {"id": e.get("sepID"), "time": e.get("eventTime")}
        for e in seps or []
        if (t := _parse_time(e.get("eventTime"))) and sep_from <= t <= now
    ]
    recent = [c for c in cmes_mars if (t := _parse_time(c["start"])) and cme_from <= t <= now]
    return {
        "as_of": now.strftime("%Y-%m-%dT%H:%MZ"),
        "source": SOURCE,
        "sep_window_h": SEP_WINDOW_H,
        "sep": sorted(sep, key=lambda e: e["time"] or ""),
        "mars_cme": recent[-1] if recent else None,
        "mars_cme_30d": len(recent),
        "cme_window_d": CME_WINDOW_D,
    }


def _as_list(raw: bytes) -> list[dict]:
    data = json.loads(raw or b"[]")
    if not isinstance(
        data, list
    ):  # CCMC devuelve una lista; cualquier otra cosa es una página de error
        raise ValueError(f"respuesta inesperada de CCMC: {type(data).__name__}")
    return data


def fetch_live(fetch: Fetcher, now: datetime) -> dict:
    urls = [
        _url("SEP", now - timedelta(hours=SEP_WINDOW_H), now),
        _url("CME", now - timedelta(days=CME_WINDOW_D), now),
    ]
    with ThreadPoolExecutor(
        max_workers=2
    ) as pool:  # las dos consultas a la vez: ~6 s en el peor caso
        seps, cmes = (_as_list(raw) for raw in pool.map(fetch, urls))
    return {"status": "live", **summarize(seps, mars_impacts(cmes), now)}


def from_snapshot(path: Path | None = None) -> dict:
    snap = json.loads((path or SNAPSHOT).read_text())
    now = _parse_time(snap["as_of"])
    if now is None:
        raise ValueError("as_of inválido en la copia de DONKI")
    return {"status": "snapshot", **summarize(snap["sep"], snap["mars_cmes"], now)}


def unavailable(now: datetime) -> dict:
    """Último recurso (ni CCMC ni la copia): el endpoint sigue respondiendo 200 y la UI muestra 'no disponible'."""
    return {
        "status": "down",
        "as_of": now.strftime("%Y-%m-%dT%H:%MZ"),
        "source": SOURCE,
        "sep_window_h": SEP_WINDOW_H,
        "sep": [],
        "mars_cme": None,
        "mars_cme_30d": 0,
        "cme_window_d": CME_WINDOW_D,
    }


class SpaceWeather:
    """Caché en memoria: en vivo cada hora; si CCMC falla, la copia (reintento a los 5 min).

    Con candado: en frío, N peticiones concurrentes hacen UNA consulta a CCMC, no N (FastAPI ejecuta los
    endpoints síncronos en un threadpool).
    """

    def __init__(self, fetch: Fetcher = http_get, clock: Callable[[], float] = time.time):
        self.fetch = fetch
        self.clock = clock
        self._value: dict | None = None
        self._until = 0.0
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            t = self.clock()
            if self._value is not None and t < self._until:
                return self._value
            now = datetime.fromtimestamp(t, UTC)
            try:
                value, ttl = fetch_live(self.fetch, now), TTL_OK_S
            except Exception as exc:  # noqa: BLE001 — cualquier fallo de red/HTTP/JSON/forma cae a la copia
                # (URLError, HTTPError, timeout, http.client.IncompleteRead, JSONDecodeError, KeyError...)
                log.warning(
                    "DONKI (CCMC) no disponible, se sirve la copia: %s: %s", type(exc).__name__, exc
                )
                try:
                    value = from_snapshot()
                except Exception:  # noqa: BLE001 — copia ausente o corrupta: nunca 500
                    log.exception("la copia de DONKI tampoco se pudo leer")
                    value = unavailable(now)
                ttl = TTL_FAIL_S
            self._value, self._until = value, t + ttl
            return value
