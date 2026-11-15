# 2026-11-15 — Clima espacial (NASA DONKI) servido por el backend

## Por qué
- **Antes:** el navegador de cada visitante consultaba `api.nasa.gov/DONKI` con `DEMO_KEY`, que permite unas 10 consultas por hora por IP.
- **El problema:** en el wifi compartido del pitch, el panel de radiación mostraba "NASA DONKI no disponible". En la prueba en producción del 15 nov ya dio 429.
- **Riesgo extra:** cualquier `VITE_NASA_API_KEY` quedaba pública en el bundle.

## Qué se hizo
- **`GET /api/mars/space-weather`** (`src/marsmap/data/space_weather.py`):
  - consulta NASA CCMC DONKI (`ccmc.gsfc.nasa.gov/DONKI-API`, sin clave);
  - guarda la respuesta en caché 1 h por instancia.
- **Qué devuelve:**
  - **SEP de las últimas 72 h.** Son detecciones cerca de la Tierra; DONKI no reporta SEP medidos en Marte.
  - **La CME más reciente con llegada a Marte según WSA-ENLIL**, más cuántas hubo en 30 días. Es un dato **modelado**, no medido; la UI debe decir "modelada".
- **Si CCMC falla:**
  - el endpoint devuelve la copia `src/marsmap/data/donki_snapshot.json` (8 KB, del 2026-11-14) con `status: "snapshot"`;
  - reintenta a los 5 min;
  - nunca devuelve error.
- **Cómo se regenera la copia:** `scripts/donki_snapshot.py <carpeta con SEP.json y CME.json>`. La carpeta es la descarga completa en `06-datos/donki/` del archivo del equipo.
- **Pruebas:** 6 nuevas en `tests/api/test_space_weather.py`, sin red. Cubren el filtro de Marte, el análisis más preciso, las ventanas de tiempo, la caché, el respaldo y el endpoint.

## Dato en vivo al 15 nov 03:46 UTC
- 0 SEP en las últimas 72 h.
- Última CME con llegada modelada a Marte: salió el 2026-11-09 18:15Z y llegó (rozando) el 2026-11-13 12:00Z.
- 10 CME de ese tipo en 30 días.

## Pendiente
- El frontend (MarsWalk-web) debe consumir este endpoint en lugar de `api.nasa.gov`; va en un PR aparte.
