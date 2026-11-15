# 2026-11-15 — v3: fechas corregidas al periodo del reto (14–15 nov) y CI funcionando

## Problema
- **Fechas fuera del reto:** varios docs, specs y comentarios traían fechas anteriores al reto
  (2026-10-09, 2026-11-06, 2026-11-09 a 11-12), aunque todo el trabajo se hizo el 14 y 15 de noviembre.
- **Ejecuciones del notebook:** `notebooks/Mars_Scout_demo.ipynb` tenía marcas de ejecución del 2026-10-10.
- **Fechas de descarga:** `retrieved_at` en `poi.geojson` decía 2026-10-09 y en `ortho/ortho.json`, 2026-11-06.
- **CI fuera de main:** el workflow anterior nunca llegó a `main`, porque solo existía en una rama de trabajo.
  Hubo 4 ejecuciones el 14 nov y las 4 fallaron:
  - Gitleaks exigía `GITLEAKS_LICENSE`;
  - Semgrep se agotaba en `draco_decoder.js`.

## Qué se hizo (MarsWalk-v3)
- **Notebook re-ejecutado de verdad** con `scripts/build_notebook.py` (datos reales):
  - las 11 celdas quedan con fecha 2026-11-15 y sin errores;
  - el HTML se regeneró.
- **Datos re-descargados** en lugar de editar las fechas a mano:
  - DEM con `fetch_dem.py`, recorte MOLA–HRSC 200 m;
  - sitios con `marsmap.data.mars2020`:
    - `poi.geojson`: solo cambia `retrieved_at`;
    - `traverse.geojson`: pasa de 703 a 708 puntos, porque NASA publicó waypoints nuevos.
  - ortofoto con `fetch_ortho.py`: las `.webp` quedan idénticas byte a byte; solo cambia `retrieved_at`.
- **Fechas de bitácora pasadas a 2026-11-14:**
  - `CLAUDE.md`, `docs/decisiones.md`, `docs/README.md`;
  - "revisado / aprobado" en `spec/features/*`;
  - comentarios en `terrain/build.py`, `terrain/ortho.py` y `data/mars_pois.py`;
  - 9 docs renombrados de `2026-10-09-*`, `2026-11-06-*` y `2026-11-09-*` a `2026-11-14-*`.
- **Fechas que NO se tocaron** porque son datos reales o de prueba:
  - eventos de DONKI (`donki_snapshot.json`, el doc de clima espacial);
  - fixtures de `tests/api/test_space_weather.py`;
  - la ventana de `scripts/donki_snapshot.py`.
- **Nuevo `.github/workflows/ci.yml`**, que corre en push a main, en PRs y a mano (`workflow_dispatch`):
  - ruff y pytest;
  - Gitleaks como CLI, sin licencia;
  - Semgrep solo sobre `src`, `scripts` y `server.py`.

## Validación local
- ruff: limpio.
- pytest: 280 pasan, incluidos los de DEM real.
- Gitleaks: 33 commits, sin fugas.
- Semgrep: 188 reglas, 0 hallazgos.

## Pendiente
- Publicar `MarsWalk-v3` y confirmar la primera ejecución verde en GitHub Actions.
- MarsWalk-web tiene las mismas fechas en 2 docs y 3 comentarios (`marsTiles.js`, `marsTilesCore.js`,
  `tokens.css`).
