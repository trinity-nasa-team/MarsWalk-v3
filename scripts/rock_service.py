"""Servicio local de segmentación de rocas (pipeline Grounding DINO + SAM + U-Net AI4Mars) para el visor MarsWalk-web.

No corre en el navegador: es Python en la GPU de este equipo. El visor le manda el cuadro de la cámara (JPEG) y recibe una
máscara PNG (roca amarilla semitransparente). Solo local: escucha en 127.0.0.1.

Uso:
    pip install -r scripts/requirements-rocks.txt
    python scripts/rock_service.py                 # puerto 8765
    ROCAS_MARTE_DIR=otra/carpeta python scripts/rock_service.py   # si el pipeline está en otro lado

Variables: ROCAS_MARTE_DIR (carpeta con rocas_marte.py; por defecto scripts/rocas_marte/), ROCK_PORT.
El primer arranque descarga ~3.5 GB de Hugging Face (Grounding DINO base y SAM ViT-H); revisar sus licencias antes de uso comercial.
Límite conocido: ~10 s por cuadro en modo «full» (mosaico 3×3) y ~1–2 s en «fast» (una pasada, pierde rocas pequeñas), en una RTX 5060.
"""

import os
import sys
import threading
import time

import cv2
import numpy as np
import torch
import torchvision
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.environ.get("ROCAS_MARTE_DIR") or os.path.join(
    HERE, "rocas_marte"
)  # por defecto: scripts/rocas_marte/
if not os.path.exists(os.path.join(PIPE, "rocas_marte.py")):
    sys.exit(f"No encuentro rocas_marte.py en {PIPE}. Define ROCAS_MARTE_DIR.")
sys.path.insert(0, PIPE)
t0 = time.time()
print("Cargando Grounding DINO + SAM + U-Net (la primera vez descarga ~3.5 GB)…", flush=True)
import rocas_marte as rm  # noqa: E402  (carga los modelos al importar)

print(f"Modelos listos en {time.time() - t0:.0f} s · dispositivo: {rm.DEV}", flush=True)

app = FastAPI(title="Servicio de rocas", docs_url=None, redoc_url=None)
gpu = threading.Lock()  # un cuadro a la vez


def sam_masks(pil, boxes_scores):
    """Cajas (Grounding DINO) → unión de máscaras SAM, como en rocas_marte.rocas()."""
    H0, W0 = pil.size[1], pil.size[0]
    m = np.zeros((H0, W0), bool)
    if not boxes_scores:
        return m
    b = torch.tensor([x[0] for x in boxes_scores])
    s = torch.tensor([x[1] for x in boxes_scores])
    boxes = b[torchvision.ops.nms(b, s, 0.5)].tolist()
    for i in range(0, len(boxes), 64):
        si = rm.sproc(pil, input_boxes=[boxes[i : i + 64]], return_tensors="pt").to(rm.DEV)
        with torch.no_grad():
            so = rm.samm(**si, multimask_output=False)
        ms = rm.sproc.image_processor.post_process_masks(
            so.pred_masks.cpu(), si["original_sizes"].cpu(), si["reshaped_input_sizes"].cpu()
        )[0]
        m |= ms[:, 0].any(0).numpy()
    return m


def rocks_fast(img):
    """Una sola pasada sobre la imagen completa (sin mosaico): rápido, pierde rocas pequeñas."""
    pil = Image.fromarray(img)
    m = sam_masks(pil, rm.detect(pil)).astype(np.uint8)
    t = rm.terreno(img)
    m[(t == 4) | (t == 5)] = 0  # quita rover y cielo/lejano
    return m


@app.get("/health")
def health():
    return {
        "ok": True,
        "device": rm.DEV,
        "modelos": "grounding-dino-base + sam-vit-huge + unet-ai4mars",
    }


@app.post("/analyze")
async def analyze(request: Request, mode: str = "fast"):
    data = await request.body()
    if not data or len(data) > 8_000_000:
        raise HTTPException(400, "cuerpo vacío o mayor de 8 MB")
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(400, "no es una imagen JPEG/PNG")
    if max(arr.shape[:2]) > 1280:  # tope de tamaño: protege la memoria de la GPU
        f = 1280 / max(arr.shape[:2])
        arr = cv2.resize(arr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    t1 = time.time()
    with gpu:
        m = rm.rocas(img) if mode == "full" else rocks_fast(img)
    n_regions = max(0, cv2.connectedComponents(m.astype(np.uint8))[0] - 1)
    rgba = np.zeros((*m.shape, 4), np.uint8)
    rgba[m == 1] = (255, 220, 0, 150)
    edge = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    rgba[edge] = (255, 255, 0, 255)  # contorno marcado
    ok, png = cv2.imencode(".png", cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    return Response(
        png.tobytes(),
        media_type="image/png",
        headers={
            "X-Rock-Count": str(n_regions),
            "X-Rock-Share": f"{float(m.mean()):.4f}",
            "X-Ms": str(int((time.time() - t1) * 1000)),
            "Cache-Control": "no-store",
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        app, host="127.0.0.1", port=int(os.environ.get("ROCK_PORT", "8765")), log_level="warning"
    )
