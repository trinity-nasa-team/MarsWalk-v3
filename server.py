"""Punto de entrada del backend para Vercel (servicio `api` en vercel.json).

Vercel importa `server:app`. El paquete vive en src/ (layout src), así que se agrega al path, y DATA_DIR se fija
en ruta absoluta para que no dependa del directorio de trabajo de la función.
En local se sigue usando `uvicorn marsmap.api.main:app --app-dir src`.
"""

import ctypes
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# rasterio (GDAL) necesita libexpat.so.1 del sistema y el runtime de Vercel no la trae. El buildCommand del
# servicio `api` la copia desde la imagen de build a vendor_libs/; precargarla con RTLD_GLOBAL hace que el
# cargador la reutilice cuando GDAL la pida por su soname. En local (donde el sistema ya la tiene) no hace nada.
_expat = RAIZ / "vendor_libs" / "libexpat.so.1"
if _expat.exists():
    ctypes.CDLL(str(_expat), mode=ctypes.RTLD_GLOBAL)
sys.path.insert(0, str(RAIZ / "src"))
# /vsicurl sin timeout puede pasar de los 60 s de la función: que falle rápido y responda 422.
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "1")

if os.environ.get("VERCEL"):
    # En Vercel solo /tmp es escribible: DATA_DIR va a /tmp con un enlace a los datos versionados de Jezero.
    # Así la caché de POIs (DATA_DIR/../raw/mars_pois.json) y los sitios creados al vuelo (/api/sites) sí se
    # pueden escribir (caché efímera por instancia).
    _tmp = Path("/tmp/marsmap/processed")  # noqa: S108 (Vercel solo permite escribir en /tmp)
    _tmp.mkdir(parents=True, exist_ok=True)
    for _region in (RAIZ / "data" / "processed").iterdir():
        _link = _tmp / _region.name
        if _region.is_dir() and not _link.exists():
            _link.symlink_to(_region)
    os.environ.setdefault("DATA_DIR", str(_tmp))
else:
    os.environ.setdefault("DATA_DIR", str(RAIZ / "data" / "processed"))

from marsmap.api.main import app  # noqa: E402,F401
