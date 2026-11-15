# 2026-11-14 — 015 Todo Marte en vivo, ficha de suelo y ruta a 30 m

## Qué se hizo
- El usuario pidió dejar de bajar cosas pesadas: se borraron ~516 MB de data/raw (GIS SIM 3464, DEM 20 m
  completo, caché de tiles, GeoTIFF CTX). Ver memoria «no descargas pesadas».
- **Todo Marte en vivo** (`marswalk/src/lib/marsTiles.js`): protocolo MapLibre `mars://capa/z/x/y` que pide los
  mosaicos globales geográficos y los reproyecta a Web Mercator en el navegador. Capas: CTX global ~5 m
  (Caltech/Murray Lab vía Esri astro.arcgis.com) con color Viking MDIM 2.1 por inyección de detalle (el CTX de
  Esri tiene desv. típica 4–7/255, se amplifica ×5, ×3 de cerca), MOLA color, THEMIS IR noche, geología USGS
  SIM 3292. CORS verificado. Se quitó el «cuadro» CTX local; queda la ventana HiRISE desde zoom 11.
- **Ficha del punto** al clic: unidad geológica (consulta ArcGIS en vivo), tipo de superficie por THEMIS
  nocturno (lectura cualitativa), terreno de la API, muestra de Perseverance más cercana, alcance a pie, y
  botón «Agregar como parada».
- **Ruta**: relieve CTX DEM 20 m de USGS (Mars 2020) leído por ventana remota (`fetch_dem --bbox`, 9 MB en
  data/raw) y remuestreado a **30 m** (1185×988) para el núcleo 77.15–77.75 E, 18.2–18.7 N; material fino
  (THEMIS ≤ 75/255) marcado como riesgo. Rutas en 77–540 ms. La ruta de demo sigue de cerca el recorrido real
  de Perseverance.
- `build.py`: `--dem-resolution-m`, `--dataset`, `--instrument`, `--themis`; conserva subcarpetas (ortho/).

## Verificación
- pytest 225 passed, ruff OK; Vitest 25/25; build OK; navegador sin errores.

## Pendiente (pedido por el usuario, en este orden)
- O₂ y punto de no retorno (Pandolf/Santee), alerta solar DONKI, robot real por MQTT, capas de ciencia.
- Elevación global por punto (no hay servicio con valores; solo dentro de Jezero).
- El servicio de dunas de Trek está mal configurado (devuelve geología): no se usa.
