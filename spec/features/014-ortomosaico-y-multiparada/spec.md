# Spec — 014 Ortomosaico real de Jezero y EVA con varias paradas

**Estado: LISTO PARA IMPLEMENTAR** (aprobado por el usuario el 2026-11-14)

## 1. Qué hace
Dos mejoras pedidas sobre la maqueta Marswalk (013):

**A. Imagen real de Marte (ortomosaico).** Reemplaza el relieve sombreado gris por imágenes orbitales reales,
armadas con los tiles WMTS públicos de NASA Mars Trek y empatadas en un ortomosaico que cubre **toda** la
región mapeada (bbox 77–78° E, 18–18.9° N):

| Capa | Producto Trek (verificado 2026-11-14) | Cobertura | Nivel / resolución |
|---|---|---|---|
| Base | *MRO CTX, Jezero Mosaic, Preliminary* (`Jezero_CTX_BlockAdj_dd`) | 75.15–78.87° E, 15.91–19.45° N (toda la región) | z = 12 · ~10 m/px |
| Detalle | *MRO HiRISE, Jezero Mosaic, Controlled* (`JEZ_hirise_soc_006_orthoMosaic_25cm…`, USGS para Mars 2020 TRN) | 77.22–77.58° E, 18.31–18.67° N | ventana de ~5×5 km alrededor del hábitat · z = 15 · ~1.2 m/px |

- Tiles: `https://trek.nasa.gov/tiles/Mars/EQ/<capa>/1.0.0/default/default028mm/{z}/{fila}/{col}.png`,
  matriz geográfica (origen −180, 90; nivel z = 2^(z+1) × 2^z tiles de 256 px). Coincide con nuestra
  convención (lon −180..180 E, esfera de 3 396 190 m).
- La descarga se hace **una vez** con un script (red solo ahí). Los tiles crudos y el GeoTIFF completo van a
  `data/raw/` (no se suben a git). A `data/processed/jezero/ortho/` van trozos JPG ≤ 2048 px y un
  `ortho.json` con bbox de cada trozo y metadatos (fuente, instrumento, resolución, fecha, limitaciones).
- La API sirve el manifiesto y los trozos. El mapa los muestra como capa «Imagen real» (encendida por defecto),
  y el visor 3D del robot pinta esa imagen sobre el DEM real.

**B. EVA con varias paradas.** En «Plan» se eligen **varios** puntos de interés (lista o clic en el mapa),
en el orden de selección y reordenables (↑ ↓). Se calcula un A* exacto por tramo (hábitat → P1 → P2 → … ) y
la EVA los recorre. Al llegar a cada parada hay un evento. Si el robot vio peligros, el siguiente tramo se
recalcula con ellos. Al final se regresa al hábitat. Todo debe quedar dentro del radio de 10 km.

## 2. Módulos que toca
- [x] Script `scripts/fetch_ortho.py` + módulo `marsmap/terrain/ortho.py` (empatar tiles, recortar, trozos).
- [x] API: `GET /api/regions/{id}/ortho` (manifiesto) y `GET /api/regions/{id}/ortho/{trozo}` (JPG).
- [x] `marswalk/`: capa de imagen real en el mapa, textura en el visor 3D, plan y simulación multiparada.

## 3. Criterios de aceptación
1. `fetch_ortho.py --region jezero` baja los tiles (con caché y reintentos), los empata sin costuras de
   desplazamiento (cada tile en su fila/columna exacta) y genera los trozos y `ortho.json`.
2. Los trozos están georreferenciados: un punto conocido (sitio de aterrizaje, 18.4446° N 77.4509° E)
   cae en el mismo lugar en el ortomosaico y en el DEM (±1 celda del DEM).
3. `ortho.json` y la ficha de capa muestran fuente (NASA Mars Trek / USGS), instrumento, resolución, fecha y
   limitaciones («imagen visible en escala de grises, iluminación distinta entre tomas»).
4. La API valida el id del trozo con `^[a-z0-9_]+$`, nunca lee fuera de `data/processed/` y devuelve
   `ErrorOut` si falta el ortomosaico. Sin ortomosaico la app sigue funcionando con el relieve sombreado.
5. Las pruebas usan tiles sintéticos deterministas (sin red).
6. En «Plan» se pueden elegir 2–8 paradas. Los tramos son A* exacto (no genético) y se muestran la distancia
   total, el tiempo a pie (supuesto 3 km/h) y el perfil de cada tramo.
7. La EVA recorre las paradas en orden, con un evento al llegar a cada una, y respeta peligros y aprobación
   igual que en la 013.
8. Ningún archivo que se suba a git pesa más de 10 MB.

## 3b. Decisiones del usuario (2026-11-14)
- OK al plan (CTX ~10 m en toda la región + ventana HiRISE ~1.2 m alrededor del hábitat).
- Que «se vea como Marte»: color por *pansharpening* con el mosaico global a color **Viking MDIM 2.1**
  (Trek `Mars_Viking_MDIM21_ClrMosaic_global_232m`, servido hasta z = 7 ≈ 330 m/px). En pantalla se rotula
  «color aproximado (Viking)»; el detalle es de CTX/HiRISE.
- Animaciones en las transiciones, con tiempos y curvas de las referencias: entrada «aterrizaje» 3 s
  [CoM], cambio de vista con View Transitions y cubic-bezier(.77,0,.175,1) [CoM], paneles escalonados 1 s
  cubic-bezier(.25,1,.5,1) [ETH], vuelo del mapa de órbita al cráter, fundido de color de la ruta al aprobar (.6 s).
- Orden de paradas: el de selección (sin NSGA-II por ahora).

## 4. Fuera de alcance
- HiRISE de toda su extensión a máxima resolución (≈ 4 400 tiles, ~260 MB): solo la ventana alrededor del hábitat.
- Color verdadero a alta resolución: no existe para toda la región; se usa color aproximado de Viking.
- Orden óptimo automático de las paradas (podría usar el NSGA-II de la 004; queda como opción).

## 5. Fuentes
- NASA Mars Trek, catálogo `TrekServices/ws/index/eq/searchItems` y `WMTSCapabilities.xml` de cada capa.
- USGS Astrogeology: HiRISE y CTX orthomosaics para Mars 2020 Terrain Relative Navigation
  (descripción en el catálogo de Trek).
