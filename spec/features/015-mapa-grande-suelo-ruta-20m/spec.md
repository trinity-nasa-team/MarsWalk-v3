# Spec — 015 Mapa completo, tipo de suelo al clic y ruta a 20 m

**Estado: LISTO PARA IMPLEMENTAR** (aprobado por el usuario el 2026-11-14: A + B + C)

## Problema (reportado por el usuario con capturas)
1. La imagen real es «solo un cuadrado»: fuera del bbox de cálculo (1° × 0.9°) todo es negro.
2. La ruta «está mal»: cruza dunas y terreno roto que se ven en la foto. Causa: el A* usa el DEM de
   **200 m/px** y solo pendiente; no ve nada menor de 200 m ni el tipo de suelo.
3. Al hacer clic no hay información del **tipo de suelo**.

## Qué hace
**A. Mapa grande sin vacío negro.** Imagen real de todo el mosaico CTX de Trek (75.15–78.87° E,
15.91–19.45° N: Jezero, Nili Planum y el borde de Isidis) a ~40 m/px, y de fondo el mosaico a color
de Viking en un área amplia (~70–86° E, 10–27° N). El detalle de 10 m y la ventana HiRISE se mantienen.

**B. Ruta que sí ve el terreno.**
- Relieve **CTX DEM 20 m** (USGS, Mars 2020, `M20_JezeroCrater_CTXDEM_20m.tif`, 87 MB, verificado):
  10× más fino en el núcleo de Jezero (delta, Séítah, sitio de aterrizaje).
- Costo por **tipo de suelo** del mapa geológico USGS SIM 3464 (Sun & Stack 2020, 1:75 000, dominio
  público). Ejemplo: las unidades eólicas y de dunas (Séítah) cuestan más o quedan prohibidas; el piso
  fracturado es transitable.
- Inercia térmica aproximada con **THEMIS IR nocturno** (incluido en el GIS de SIM 3464):
  frío de noche = polvo o arena fina; caliente = roca.
- Los pesos son nuestros y se declaran en pantalla.

**C. Ficha al clic en cualquier punto.**
- Unidad geológica con su nombre y descripción (SIM 3464).
- Tipo de superficie según THEMIS nocturno.
- Elevación, pendiente, rugosidad y transitabilidad a 20 m.
- Sitio de muestras de Perseverance más cercano, con su tipo de roca.
- Distancia al hábitat y si queda dentro del radio de 10 km.
- Capa conmutable «Mapa geológico» con leyenda.

## Criterios de aceptación
1. Al alejar el mapa no hay vacío negro en ~15° alrededor de Jezero. Cada capa muestra su fuente y su resolución.
2. La ruta de la demo (aterrizaje → Séítah/delta) rodea las unidades de dunas. Sobre la imagen se nota
   que sigue el terreno, no una línea recta. Prueba con terreno sintético: una franja de «dunas» se rodea.
3. Clic en cualquier punto → ficha con los datos de C en < 300 ms. Fuera de cobertura dice «sin dato».
4. Toda capa conserva su metadato (fuente, instrumento, resolución, fecha, limitaciones). Se declara que el
   mapa geológico tiene un desfase de **100–200 m** respecto al mosaico controlado (lo dice su readme).
5. Las pruebas usan datos sintéticos (sin red). Ningún archivo en git pesa más de 10 MB.

## Fuentes (verificadas 2026-11-14)
- CTX DEM 20 m: planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/ (HTTP 200, 90 MB).
- SIM 3464: pubs.usgs.gov/publication/sim3464 (GIS 349 MB; GeoUnits, SurfaceFeatures, THEMIS IR día/noche).
- NASA Mars Trek: mosaicos CTX y Viking (ver 014).
