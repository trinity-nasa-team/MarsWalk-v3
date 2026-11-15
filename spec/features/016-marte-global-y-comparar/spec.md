# Spec — 016 POIs de todo Marte, hábitat en cualquier lugar y «Comparar con Perseverance»

**Estado: LISTO PARA IMPLEMENTAR** (aprobado por el usuario el 2026-11-14)

## A. Puntos de interés de todo el planeta (en vivo, sin descargas)
- **51 Zonas de Exploración para humanos** (NASA, First Landing Site/Exploration Zone Workshop 2015), del
  servicio ArcGIS de Mars Trek `EZMars` (nombre, lat, lon, elevación, enlace al abstract).
- **1 783 nombres oficiales IAU** (cráteres, valles, montes…), del índice de Mars Trek (`itemType=nomenclature`).
- Se muestran en el mapa con el nivel de zoom adecuado, con un buscador por nombre que vuela al lugar.
  Al hacer clic se abre la ficha (geología, superficie…) y aparece la opción «poner hábitat aquí».
- Longitudes 0–360 se normalizan a −180..180 E al cargar.

## B. Hábitat en cualquier lugar de Marte
- Con «poner hábitat aquí» fuera de Jezero, el backend arma una región temporal de ~44 × 44 km
  (radio de regreso de 10 km + margen) con el **DEM global MOLA–HRSC Blend 200 m** de USGS. Lo lee por ventana
  remota (`/vsicurl/`, ~20 MB transferidos, nada pesado guardado) y deriva pendiente, rugosidad y transitabilidad.
- La región tiene un id determinista (`site_<lat>_<lon>`, en lista blanca generada por el servidor), queda en
  caché de memoria y se puede pedir ruta con el mismo `/route`.
- Jezero conserva su relieve de 30 m.

## C. «Comparar con Perseverance» (sección simulada)
- Eliges 3–8 sitios de muestras reales.
- **Real:** orden de visita por sol, distancia por el odómetro del recorrido real (NASA/JPL waypoints) y
  recorrido dibujado.
- **Marswalk:** orden que elige el NSGA-II (004) con A* exacto por tramo, sobre el mismo terreno.
- Animación simultánea de ambos (dos marcadores), métricas lado a lado (distancia, tiempo a pie supuesto,
  pendiente máx., % de riesgo) y explicación de dónde sale la diferencia.
- **Honestidad:** se declara que Perseverance tuvo restricciones que no modelamos (objetivos científicos,
  ventanas de comunicación, operaciones, desplazamientos de días distintos). No se dice «más eficiente que
  NASA». Frase de la propuesta: «el orden histórico ya está cerca del óptimo; nuestro planificador lo alcanza
  automáticamente».

## Criterios de aceptación
1. Las Zonas de Exploración y los nombres IAU se ven en todo el planeta; el buscador encuentra «Gusev» y vuela ahí.
2. Poner hábitat en Gusev (−14.57°, 175.46° E) genera la región y una ruta A* válida en < 30 s la primera vez.
3. El modo comparar muestra dos órdenes, métricas y animación, sin errores, y con el aviso de honestidad visible.
4. Pruebas con datos sintéticos (sin red) para región dinámica y comparación.
