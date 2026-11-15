# Spec — 013 Marswalk: interfaces (mapa, HUD, hábitat, Tierra)

**Estado: LISTO PARA IMPLEMENTAR** (revisado el 2026-11-14 con el usuario)

Fuente: *Trinity-Propuesta-Resumen.pdf* (junta del 5 nov) y tres referencias visuales elegidas por el
usuario. Todo dato de diseño de abajo sale del CSS/JS publicado de esas referencias (ver §7); nada se
inventa.

## 1. Qué hace

Marswalk cierra el ciclo entre la órbita y el suelo en una caminata (EVA) por Jezero. Son cuatro piezas
y una sola historia de demo:

| Pieza | Dispositivo | Qué hace |
|---|---|---|
| 1 · Mapa por capas + ruta (**núcleo**) | web | Capas reales (relieve, pendiente, rugosidad, transitabilidad), ruta A* más segura según esfuerzo y O₂, anillo de alcance «hasta dónde puedo ir y volver», recorrido real de Perseverance. |
| 2 · HUD del astronauta | tablet | Mini-mapa, ruta de regreso, anillo de alcance por O₂, alertas por color (y voz), siguiendo requisitos NASA SUITS. |
| 3 · Consola del hábitat (propia, sin Open MCT) | laptop | Telemetría de la EVA, aprueba rutas recalculadas, visor del robot explorador. Vista «Tierra» con 4–22 min de retraso. |
| 4 · Robot explorador | (fuera de este spec) | Publica obstáculos por MQTT; si falla, un explorador simulado publica los mismos eventos. Este spec solo **consume** esos eventos. |

### El ciclo de la demo (criterio rector)
1. El robot detecta un obstáculo que la órbita no veía → 2. el servidor recalcula la ruta (A*, O₂, punto de
no retorno) → 3. el HUD avisa (nueva ruta, anillo) → 4. el hábitat lo ve al instante y aprueba →
5. la Tierra lo ve 4–22 min después («dato de hace 14 min»).

**Funcional significa**: cada paso del ciclo usa la API real (`/route`, `/missions`, obstáculos) y se puede
correr en vivo de principio a fin sin datos fingidos en pantalla. Lo que todavía no tenga modelo
(O₂, punto de no retorno) se muestra marcado como «propuesta» hasta que exista su spec.

## 2. Sistema visual (tomado de las referencias)

### Tipografía (todas con licencia libre, archivos locales, sin CDN)
| Uso | Fuente | De qué referencia |
|---|---|---|
| Títulos / rótulos de pantalla | **Michroma** | ETH Zürich Space (`--michroma`, 26 usos) |
| Texto y UI | **Eudoxus Sans** (Light/Regular/Medium/Bold) | ETH Zürich Space (`--eudoxus-*`) |
| Datos, captions, telemetría | **JetBrains Mono** | Claude on Mars (`--jetbrains-mono`) |

Anthropic Sans/Serif/Mono (Claude on Mars) son propietarias: **no se usan**. Orbitron/Exo 2 (RS69) no se
usan porque de RS69 solo se pidieron los colores. Licencia de Eudoxus Sans: verificar OFL antes de empaquetar.

### Color
- **Base de pantallas (Claude on Mars):** fondo `#000` (`--mars-black`); texto `#faf9f5` (`--mars-white`);
  UI inactiva `#87867f` (`--mars-ui-default`) que pasa a blanco al activarse (`--mars-ui-active`);
  escala `#e8e6dc` · `#3d3d3a` · `#262624` · `#1a1918`.
- **Atmósfera espacial (ETH):** azules profundos `#050117` · `#070B1D` · `#101533` · `#253054` ·
  `#34416F`, acentos `#A3B8FF` · `#C2DDFF` · `#214DFF`. Solo en fondos, transiciones entre vistas y
  la vista «Tierra».
- **Órbitas (RS69):** las tres paletas de galaxia del sitio, con un significado cada una:
  - **Órbita / datos satelitales** → azul: core `rgb(240,250,255)`, bright `(150,210,255)`,
    mid `(70,150,240)`, dark `(30,80,180)`; acento `#60a5fa`.
  - **Suelo / robot / astronauta** → ámbar: core `(255,250,230)`, bright `(255,210,140)`,
    mid `(240,150,70)`, dark `(180,80,30)`.
  - **Tierra (enlace con retraso)** → violeta: core `(255,240,255)`, bright `(210,170,255)`,
    mid `(150,90,220)`; acento `#a78bfa` / `#7c3aed`.
- Los colores de las capas del mapa (pendiente, transitabilidad) son **datos**, no decoración: se quedan
  como están en la API.

### Componentes (Claude on Mars)
- Captions en mono 13 px (`--mars-caption`) en mayúsculas tipo «FRONT HAZCAM · SOL 1215».
- **Visor del robot**: retícula de 72×72 px con flechas (`viewfinder`, `cross`), indicador que
  parpadea `1s step-end infinite`.
- Tarjetas con borde 1 px, radio 4 px, líneas finas.
- Barra de eventos en marquesina `12s linear infinite`.
- Señal que pulsa `4s ease-in-quart infinite` (escala 1 → 1.2).

### Movimiento
| Qué | Valor | Referencia |
|---|---|---|
| Hover / estados | `opacity .2s` | Claude on Mars |
| Paneo de cámara / mapa | `.6s cubic-bezier(.4,0,.2,1)` | Claude on Mars |
| Cambio de vista grande | `cubic-bezier(.77,0,.175,1)` | Claude on Mars |
| Entrada de paneles | `transform 1s cubic-bezier(.25,1,.5,1)`, `opacity 1.15s ease` | ETH |
| Fondo de estrellas | partículas (particles.js) | ETH |
| Órbitas y halos | gradientes radiales y pulso de galaxia | RS69 |
| Todo | se respeta `prefers-reduced-motion` | — |

### Superficie marciana
Claude on Mars muestra fotos reales de las cámaras de Perseverance. Aquí: relieve 3D del DEM real de
Jezero (grises tipo navcam) y, si se aprueba, fotos crudas de Mars 2020 (NASA/JPL-Caltech, dominio
público) en el visor del robot, con sol, cámara y crédito visibles.

## 3. Módulos que toca
- [x] Frontend (`frontend/`): app nueva con 3 vistas (mapa, HUD, hábitat + Tierra).
- [ ] Backend: solo lo que ya existe (`/route` con `obstacles`, `/missions`, `/traverse`,
  `terrain-grid`). Los modelos nuevos van en sus propios specs (§5).

## 4. Criterios de aceptación
1. Las tres vistas cargan con la API real en local y sin conexión a internet (fuentes y librerías locales).
2. **Mapa**: muestra las capas de la 002 con su ficha de fuente, la ruta A* entre dos puntos y el
   recorrido real de Perseverance con su fuente (NASA/JPL).
3. **HUD**: en una tablet (≥ 768 px, táctil) muestra mini-mapa, ruta de regreso, anillo de alcance y alertas
   por color legibles a 50 cm. Los botones táctiles miden al menos 44 px.
4. **Ciclo completo**: al llegar un obstáculo (del robot o del explorador simulado), el servidor recalcula
   con `obstacles`, el HUD muestra la nueva ruta en menos de 2 s, el hábitat la aprueba y la Tierra recibe
   el evento con el retraso configurado (4–22 min, acelerable para la demo) y lo rotula «dato de hace N min».
5. Sin conexión al robot, el explorador simulado corre el mismo ciclo (modo réplica).
6. Todo valor sin modelo (O₂, punto de no retorno, EVA 8 h) aparece con la etiqueta «propuesta» o
   «por confirmar», igual que en el PDF.
7. Interfaz en **inglés y español** (el jurado global ve todo en inglés).
8. El texto de la API se inserta con `textContent`. Ninguna afirmación sin fuente («más eficiente que NASA»
   está prohibido).
9. Cada token de diseño en el CSS cita su referencia en un comentario.
10. Pruebas: Vitest de la lógica (cola con retraso, alertas, i18n) y un E2E del ciclo completo.

## 5. Depende de / fuera de alcance
- **Specs nuevos necesarios** (backend, no en este spec): modelo metabólico Pandolf/Santee y O₂; punto de
  no retorno; cola «guarda y reenvía» (imita DTN) y puente MQTT; alerta solar DONKI → refugio.
- Fuera de alcance: hardware del robot, video de 29 s, página del proyecto.

## 6. Decisiones del usuario (2026-11-14)
1. Se construye **ahora** como maqueta funcional («como tú lo harías»).
2. **Sin Open MCT**: consola del hábitat propia con el estilo completo de las referencias.
3. **React** (Vite) en una app nueva `marswalk/`, con **pnpm** (npm no se usa).
4. Dependencias: `react`, `react-dom`, `maplibre-gl`, `three`, `@fontsource/michroma`,
   `@fontsource/jetbrains-mono`; dev: `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`.
   Estrellas y órbitas con canvas propio (sin particles.js). Eudoxus Sans: OFL 1.1 verificada en
   github.com/stijndevries/Eudoxus-Sans, archivos locales.
5. Visor del robot: relieve 3D del DEM real (sin fotos de Mars 2020 por ahora: la app debe funcionar sin red).
6. Robot y HUD en el mismo navegador se sincronizan por `BroadcastChannel` (pestañas). Entre dispositivos
   distintos hace falta el puente MQTT/WebSocket del backend (spec aparte).

## 7. Referencias analizadas (2026-11-14)
- ETH Zürich Space — https://space.ethz.ch (`themes/ETH/css/style.css`, `js/bundle.js`).
- RS69 Rogue Signal — https://rs69.dev (`styles.min.css`, `script.min.js`: paletas de galaxia).
- Claude on Mars — https://www.anthropic.com/features/claude-on-mars (CSS de `_next/static`).
- No se copian logos, imágenes ni código de esos sitios: solo valores de diseño (fuentes libres, colores,
  tiempos y curvas de animación).
