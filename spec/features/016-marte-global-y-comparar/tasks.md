# Tasks — 016

- [x] A. `/api/mars/pois` (51 Zonas de Exploración NASA 2015 + 1 783 nombres IAU, caché 154 KB) + capa en el mapa,
      tooltips y buscador con vuelo
- [x] B. `POST /api/sites`: región de sitio ~44×44 km desde el DEM global MOLA–HRSC 200 m (lectura por ventana,
      ~40 s la primera vez, ~550 KB guardados, ignorados en git); «Poner hábitat aquí» y «Mover» en cualquier lugar;
      rutas, EVA y visor 3D en la región activa
- [x] C. Vista «Comparar con Perseverance»: real (odómetro) vs mismo orden + A* vs NSGA-II solo-ida + A*, animación,
      métricas, órdenes y aviso de honestidad. NSGA-II con `open_path` (sin regreso al inicio)
