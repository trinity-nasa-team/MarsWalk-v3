# 2026-11-14 — Fixes de la auditoría del backend

Origen: auditoría de solo lectura de `src/marsmap/api`, `eva/`, `planning/` y la integración con `planificador/`.

## Qué se corrigió
| Sev. | Archivo | Bug | Arreglo |
|---|---|---|---|
| Alta | `eva/planner.py` | `return-profile` respondía 500: NaN (celdas sin regreso posible) en `return_wh`/`margin_wh` y JSON no admite NaN | `_finite()`: NaN/inf → `null` |
| Alta | `api/deps.py`, `terrain/site.py` | Sitios de `POST /sites` solo existen en la instancia que los creó: 404 intermitente en Vercel (y tras reiniciar) | `get_region` reconstruye el sitio desde su id determinista (`parse_site_id`); centro redondeado a 0.01° |
| Media | `routers/habitat.py` | La IA del hábitat usaba umbrales viejos (10 km, 15°) | Riesgo ≥10°, bloqueo ≥20° (planificador), regreso de emergencia ~15 km (NASA DRA 5.0); regla anti cambio de rol |
| Media | `data/mars_pois.py`, `routers/mars.py` | 2 × 60 s de timeout > maxDuration 60 s; `KeyError/TypeError` del parseo → 500 | timeout 15 s; esos errores → 502 ErrorOut |
| Media | `api/main.py` | `LruCache(16)` de mapas de costos (~28 MB c/u) ≈ 450 MB | `costmaps` 4, `plans` 8 |
| Media-baja | `eva/planner.py` | `eva_too_far` se revisaba después de todos los Dijkstra (4.4 s para rechazar) | Rechazo antes del cálculo |
| Baja | `server.py` | `/vsicurl` sin timeout | `GDAL_HTTP_TIMEOUT=20`, 1 reintento |

## Verificación
- `pytest -m "not slow"`: 239 passed, 15 skipped (DEM real) — 236 antes + 3 de regresión.
- `pytest planificador/tests`: 61 passed (no se tocó `planificador/`).
- `ruff check .`: 78 errores, los mismos que había antes (ninguno nuevo).

## Pendiente (decisión del equipo o infraestructura)
- **Velocidad de marcha**: backend 2 km/h (1 en riesgo/arena) vs frontend 3 km/h → O₂ y tiempo no cuadran. Decidir con Josué.
- **Rate limit compartido**: en memoria por instancia; en Vercel el límite real es N×. Opción: regla WAF de Vercel o Upstash Redis.
- **Groq `gpt-oss-120b` con `max_tokens: 180`**: posible respuesta vacía por el razonamiento (no verificado en vivo).
- `/missions`: `timeout_s` 30 + matriz + import en frío puede acercarse a 60 s; acotar `pop_size`/`n_generations`.
- Textos de `replan-leg` en inglés; versionar `mars_pois.json` como respaldo; tope LRU de sitios en `/tmp`.
- `return-profile` y `segments` existen pero el frontend aún no los usa (sin PNR ni margen de O₂ en el HUD).
- 78 errores de ruff preexistentes.
