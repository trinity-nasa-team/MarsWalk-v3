# 2026-11-14 — 016 POIs de todo Marte, hábitat en cualquier lugar y comparar con Perseverance

## Qué se hizo
- **A. POIs globales**: `src/marsmap/data/mars_pois.py` + `GET /api/mars/pois` (los nombres IAU no tienen CORS en
  Trek, por eso pasan por el backend). 51 Zonas de Exploración (EZMars) + 1 783 nombres IAU, lon normalizada;
  caché `data/raw/mars_pois.json` (154 KB). En Marswalk: capa «Lugares», tooltips y buscador que vuela al sitio
  y abre la ficha (p. ej. Gusev → «eHv · Early Hesperian volcanic unit», superficie rocosa).
- **B. Hábitat en cualquier lugar**: `src/marsmap/terrain/site.py` + `POST /api/sites`. Construye la región
  `site_<lat>_<lon>` (id generado por el servidor, lista blanca) desde el DEM global MOLA–HRSC Blend 200 m de
  USGS leído por ventana remota. Primera vez ~40 s (Mawrth Vallis), ~550 KB en `data/processed/site_*/`
  (ignorado en git). `Registry.load()` registra regiones en caliente. Frontend: `plan.regionId/regionBbox`,
  «Poner hábitat aquí» en la ficha, «Mover» usa el mismo flujo; rutas, EVA y visor 3D usan la región activa.
  Probado de punta a punta en Gusev (2 paradas, EVA corriendo).
- **C. Comparar con Perseverance** (`marswalk/src/views/CompareView.jsx`, `lib/compare.js`): tres caminos —
  real (orden por sol, distancia por odómetro de los waypoints NASA/JPL), mismo orden + A*, y NSGA-II + A*.
  El NSGA-II evaluaba misiones de ida y vuelta: se agregó `open_path` (config, objetivos, 2-opt, legs/geometría,
  `MissionRequest.open_path`). Con 5 muestras (Roubion → Kukaklek) el genético eligió **el mismo orden que
  Perseverance**; A* en ese orden: 5.10 km vs odómetro real 11.46 km (el odómetro incluye ciencia y maniobras).
  Aviso de honestidad visible; nunca «mejor que NASA».

## Verificación
- pytest 235 passed (nuevas: mars_pois, sites, open_path, fines), ruff OK; Vitest 29/29; build OK.
- Navegador: buscador, ficha, comparar con animación y EVA en Gusev sin errores de consola.

## Pendiente (orden pedido por el usuario)
- O₂ y punto de no retorno (Pandolf/Santee), alerta solar DONKI, robot real por MQTT, capas de ciencia.
- Textura real en el visor 3D fuera de Jezero (hoy gris tipo navcam).
