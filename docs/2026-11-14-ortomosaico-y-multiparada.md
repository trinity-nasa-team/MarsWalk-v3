# 2026-11-14 — 014 Ortomosaico real de Jezero, EVA con varias paradas y transiciones

## Qué se hizo
- `src/marsmap/terrain/ortho.py` + `scripts/fetch_ortho.py`: baja tiles WMTS de NASA Mars Trek (caché en
  `data/raw/jezero/ortho_tiles/`, reintentos, lista blanca de hosts), los empata en su fila/columna exacta,
  recorta a la región y genera trozos WebP ≤ 2048 px + `ortho.json` con metadatos.
  - Base: *MRO CTX, Jezero Mosaic, Preliminary* a z = 12 (10.18 m/px), toda la región (9 trozos).
  - Detalle: *MRO HiRISE, Jezero Mosaic, Controlled* (USGS, Mars 2020 TRN) a z = 15 (1.27 m/px), ventana de
    5 km alrededor del sitio de aterrizaje (6 trozos).
  - Color aproximado: *Viking MDIM 2.1* (z = 7, ~330 m/px) por pansharpening (Y de CTX/HiRISE + Cb/Cr de Viking).
  - GeoTIFF completo en `data/raw/jezero/ortho_ctx_z12.tif` (53 MB, fuera de git). Procesado: 13 MB, ningún archivo > 3.5 MB.
- API: `GET /api/regions/{id}/ortho` (manifiesto) y `/ortho/{trozo}` (WebP, ids en lista blanca, `ErrorOut`).
- Marswalk: capa «Imagen real (CTX + HiRISE)» encendida por defecto con su ficha y la etiqueta «color aproximado
  (Viking)»; textura real sobre el DEM en el visor 3D; 2–8 paradas con A* exacto por tramo, reordenables, con
  marcadores numerados; la simulación recorre las paradas y recalcula el siguiente tramo si el robot vio peligros.
- Transiciones: entrada «aterrizaje» 3 s [CoM], View Transitions con barrido cubic-bezier(.77,0,.175,1) [CoM],
  paneles escalonados 1 s cubic-bezier(.25,1,.5,1) [ETH], vuelo del mapa de órbita al cráter, fundido de color
  de la ruta al aprobar (.6 s), aparición de paradas y del aviso del HUD.

## Decisiones
- Color: Viking (real, baja resolución) en vez de inventar un tinte; se declara como aproximado.
- HiRISE solo en ventana (toda la cobertura serían ~4 400 tiles y ~260 MB).
- Orden de paradas: el de selección; NSGA-II queda como opción futura.

## Verificación
- pytest 224 passed (10 nuevas de ortomosaico con tiles sintéticos), ruff OK; Vitest 20/20; build OK.
- Ciclo con 3 paradas en Chromium contra la API real, sin errores de consola.

## Notas / pendiente
- El backend que corría con `--reload` se reinició para cargar el ortomosaico (lo carga al arrancar).
- Durante una transición de vista (~1 s) el navegador no acepta clics (comportamiento de View Transitions).
- Hay una costura de brillo en el borde este del CTX preliminar (mosaico de tomas distintas); está en las limitaciones.
- Vite no detectó un cambio hecho por script en OneDrive; si pasa, reiniciar con `--force`.
