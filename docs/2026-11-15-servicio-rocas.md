# 2026-11-15 · Servicio local de rocas (visión sobre la cámara del robot)

**Qué se hizo**
- `scripts/rock_service.py`: servicio FastAPI **local** (127.0.0.1:8765) que segmenta rocas en un cuadro JPEG con el pipeline Grounding DINO + SAM + U-Net AI4Mars. Devuelve una máscara PNG (roca amarilla) y las cabeceras `X-Rock-Count`, `X-Rock-Share`, `X-Ms`.
  - `POST /analyze?mode=fast|full` (fast: una pasada; full: mosaico 3×3, ~10 s por cuadro medido en una RTX 5060, más rocas pequeñas).
  - `GET /health`.
- `scripts/rocas_marte/`: el pipeline (`rocas_marte.py`, U-Net `Mars_AI4Mars_Unet_mbv2_int8.onnx` de 7 MB, LEEME). Excluido de ruff (script de investigación).
- `scripts/requirements-rocks.txt`: dependencias **opcionales** (torch, transformers…); no son del backend principal.
- El visor (`MarsWalk-web`, rama `feat/rock-models`) lo consume por el proxy `/rocks` de Vite.

**Cómo correrlo**
```
pip install -r scripts/requirements-rocks.txt
python scripts/rock_service.py        # primera vez: descarga ~3.5 GB de Hugging Face
```
Variables: `ROCAS_MARTE_DIR`, `ROCK_PORT`.

**Pendiente / decisiones**
- Esto **no** alimenta al planificador. El contrato 02b espera, para evitar rocas, un GeoTIFF de probabilidad orbital (HiRISE, Dani → `perception_to_grid.py` de Paul) o un reporte `camera_ai` por MQTT con confianza ≥ 0.7 (§3.3). Hay que decidir con Paul y Josué cuál; el servicio ya entrega la máscara por cuadro.
- Licencias: Grounding DINO (IDEA-Research) y SAM (Meta) se descargan de Hugging Face; revisar sus términos antes de uso comercial. La U-Net se entrenó con AI4Mars (NASA/JPL, CC0).
- Un cuadro a la vez (GPU con candado); solo escucha en localhost, sin autenticación. No exponerlo a la red.
