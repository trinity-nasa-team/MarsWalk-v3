# 2026-11-14 — Lint limpio y pruebas completas tras la separación

**Qué se hizo**
- `ruff check` y `ruff format --check` en verde (antes: 78 errores, 6 archivos sin formato).
  - `pyproject.toml`: `planificador/` añadido a `extend-exclude` (es subtree; se lintea en su repo de origen y editarlo aquí rompería el próximo `subtree pull`).
  - `server.py`: `# noqa: S108` en `/tmp/marsmap/processed` (Vercel solo permite escribir en /tmp).
  - `src/marsmap/api/deps.py`: orden de imports. Formato de ruff en `api/routers/eva.py`, `api/routers/mars.py`, `eva/planner.py` y dos tests (sin cambios de lógica).
- Verificación: backend **265/265** (incluye `tests/real` con DEM real MOLA–HRSC 200 m recortado de USGS y waypoints de Mars 2020); planificador 61/61. Frontend (MarsWalk-web): 32/32 y build OK.
- Contrato front↔back: los 15 endpoints que usa `MarsWalk-web/src/lib/api.js` existen en el OpenAPI; los GET responden 200. CORS verificado para origen configurado (GET, PNG, preflight POST).

**Pendiente**
- Vercel: proyecto de MarsWalk-web con `VITE_API_URL` y `CORS_ORIGINS` en el backend.
- El `.venv` local apunta al repo viejo: correr con `PYTHONPATH=src` o reinstalar con `pip install -e ".[dev]"` aquí.

**Decisiones**
- No modificar el subtree `planificador/` desde este repo.
