# 2026-11-14 — Integración del planificador v4 (Josué) en el monorepo

## Qué se hizo
- `planificador/` (git subtree de `trinity-nasa-team/planificador@marswalk-v4`, con el historial de Josué).
- Backend: `src/marsmap/eva/planner.py` (adaptador lon/lat ↔ malla de 20 m del planificador) y
  `src/marsmap/api/routers/eva.py`:
  - `POST /api/regions/jezero/eva/replan-leg`: ruta A → B (~0.1 s) compatible con `RouteOut`, más
    `segments` (procedencia ORBIT / HIRISE_TEXTURE / AI / SCOUT_VERIFIED), `sand_m`, `energy_wh`, `o2_l`.
    Los peligros del robot (`obstacles`) entran como celdas de arena verificadas.
  - `POST /api/regions/jezero/eva/return-profile`: energía gastada, energía para volver, margen y punto de
    no retorno a lo largo de la EVA (astronauta, kit en kg).
  - `GET /api/regions/jezero/eva/sand-layer` (+ `.png`): capa de arena por textura HiRISE con bbox lon/lat.
- Frontend: `api.route` usa `/eva/replan-leg` en Jezero (Plan, simulación de la EVA y Compare, este último
  en modo rover). Capa «Sand (HiRISE texture)» encendida por defecto. `routeFromApi` conserva los campos v4.
- Pruebas: `tests/eva/test_planner_adapter.py` (7); backend y frontend en verde.

## Pendiente
- Mostrar en el HUD el margen de regreso y el punto de no retorno (`api.returnProfile`).
- Colorear la ruta por procedencia (`segments`) y la ruta fantasma.
- Sustituir la capa de textura por la segmentación de Dani cuando esté lista (`prob_arena`).
- Fase 0 de la revisión del frontend (10 → 15 km, 22 → 24 min, etiquetas honestas, chat).

## Decisiones
- D8 en `docs/decisiones.md`.

## Revisión de código (Fable) y arreglos aplicados
- Peligro del robot fuera de la malla daba 500 → slices acotados; se ignora si no toca la malla.
- Paradas fuera de la malla del planificador (o tramos > 15 km) → el frontend cae al A* legado de la región.
- Tope de 15 km por tramo (`leg_too_long`); `return-profile` con radio a la medida (sin PNR falso por NaN)
  y caché de `costo_regreso` (4 entradas) para acotar memoria y tiempo en Vercel.
- Compare vuelve al A* legado (misma base que la columna NSGA; contrato 02b §4.1).
- **Santee:** en bajada `M = MP − CF` (Kim et al. 2024, ec. 1); la primera versión lo sumaba.
- Pendiente: explicaciones es/en; velocidad de marcha unificada (2 km/h del planificador vs 3 km/h de la
  simulación) antes de mostrar O₂ y margen en el HUD; nombres del contrato (`outside_grid`, `from_idx`).
