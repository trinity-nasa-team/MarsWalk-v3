"""Genera src/marsmap/data/donki_snapshot.json (copia de respaldo del panel de radiación) desde la descarga completa
de DONKI (SEP.json y CME.json, ene-2024 .. 2026-11-14; ver 06-datos/donki/README.md del archivo del equipo).

Uso: python scripts/donki_snapshot.py <carpeta con SEP.json y CME.json> [as_of, p. ej. 2026-11-14T19:55Z]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from marsmap.data.space_weather import SNAPSHOT, mars_impacts  # noqa: E402

src = Path(sys.argv[1])
as_of = sys.argv[2] if len(sys.argv) > 2 else "2026-11-14T19:55Z"
seps = json.loads((src / "SEP.json").read_text())
cmes = json.loads((src / "CME.json").read_text())
snap = {
    "as_of": as_of,
    "note": "Copia de NASA CCMC DONKI. SEP: últimos 20 eventos (cerca de la Tierra). CME: llegada a Marte MODELADA (WSA-ENLIL), últimos 90 días.",
    "sep": [
        {"sepID": e["sepID"], "eventTime": e["eventTime"]}
        for e in sorted(seps, key=lambda e: e["eventTime"])[-20:]
    ],
    "mars_cmes": [c for c in mars_impacts(cmes) if c["start"] >= "2026-08-16"],
}
SNAPSHOT.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
print(SNAPSHOT, len(snap["sep"]), len(snap["mars_cmes"]), SNAPSHOT.stat().st_size, "bytes")
