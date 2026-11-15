# Plan — 013 Marswalk: interfaces

- App nueva `marswalk/` (Vite + React 19, pnpm). Proxy `/api` → uvicorn :8000. Puerto 5174.
- `src/lib/`: lógica pura y probada (geo con R = 3 396 190 m, simulación de EVA como reducer, cola
  «guarda y reenvía», i18n ES/EN, cliente de API que nunca lanza).
- `src/state/`: contexto React + reducer; reloj de simulación; sincronización entre pestañas por
  `BroadcastChannel` (la pestaña que corre la EVA es líder, las demás reflejan y mandan acciones).
- `src/components/`: Starfield (ETH), Orbits (RS69), MapView (MapLibre con capas reales de la API),
  Viewfinder + Terrain3D (Claude on Mars, three.js sobre `terrain-grid`), Marquee, Profile, cards.
- `src/views/`: Plan (núcleo: capas + ruta + walkback 10 km), HUD (tablet), Hábitat (telemetría,
  visor, aprobación), Tierra (cola con retraso, esquema orbital).
- Ciclo: robot 300 m por delante → obstáculo → `POST /route` con `obstacles` → ruta pendiente en HUD →
  hábitat aprueba → astronauta sigue → evento a la Tierra con retraso.
- Supuestos marcados en pantalla: velocidad de marcha 3 km/h (supuesto de demo), O₂ «modelo pendiente».
