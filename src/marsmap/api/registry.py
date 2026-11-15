"""Lista blanca de regiones y capas cargada al arrancar. Nunca se arma una ruta con texto del cliente."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from marsmap.config.regions import Region, load_regions
from marsmap.planning.constraints import load_forbidden_zones
from marsmap.planning.mission.poi import PointOfInterest, load_pois
from marsmap.planning.terrain_grid import TerrainGrid, load_grid
from marsmap.terrain.metadata import LayerMetadata, read_metadata

log = logging.getLogger("marsmap.registry")


@dataclass
class RegionData:
    region: Region
    folder: Path
    layers: dict[str, LayerMetadata]
    layer_files: dict[str, Path]
    _grid: TerrainGrid | None = None
    pois: list[PointOfInterest] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)
    traverse: dict | None = None
    ortho: dict | None = None

    @property
    def grid(self) -> TerrainGrid:
        if self._grid is None:
            self._grid = load_grid(self.folder)
        return self._grid


def _read_traverse(path: Path) -> dict | None:
    """Recorrido real de Perseverance (opcional; lo genera `python -m marsmap.data.mars2020`)."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("recorrido ilegible en %s (%s): se omite", path, exc)
        return None


def _read_ortho(folder: Path) -> dict | None:
    """Ortomosaico real (opcional; lo genera `python scripts/fetch_ortho.py`). Solo trozos que existen."""
    path = folder / "ortho" / "ortho.json"
    if not path.is_file():
        return None
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ortomosaico ilegible en %s (%s): se omite", path, exc)
        return None
    files = {}
    for layer in m.get("layers", []):
        layer["chunks"] = [
            c for c in layer.get("chunks", []) if (folder / "ortho" / c["file"]).is_file()
        ]
        files.update({c["id"]: folder / "ortho" / c["file"] for c in layer["chunks"]})
    ov = m.get("overview")
    if ov and (folder / "ortho" / ov["file"]).is_file():
        files["overview"] = folder / "ortho" / ov["file"]
    else:
        m["overview"] = None
    m["_files"] = files
    return m


class Registry:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.regions: dict[str, RegionData] = {}
        for region in load_regions().values():
            self.load(region)

    def load(self, region: Region) -> RegionData | None:
        """Carga una región (de regions.yaml o un sitio creado por el servidor, 016)."""
        region_id = region.region_id
        folder = self.data_dir / region_id
        try:
            meta = read_metadata(folder)
        except (FileNotFoundError, ValueError) as exc:
            log.warning("región %s sin capas procesadas (%s): se omite", region_id, exc)
            return None
        layers, files = {}, {}
        for layer in meta.layers:
            f = folder / layer.file
            if f.is_file():
                layers[layer.layer_id], files[layer.layer_id] = layer, f
            else:
                log.warning("capa %s/%s declarada pero ausente en disco", region_id, layer.layer_id)
        self.regions[region_id] = RegionData(
            region, folder, layers, files,
            pois=load_pois(folder / "poi.geojson"),
            zones=load_forbidden_zones(folder / "forbidden_zones.geojson"),
            traverse=_read_traverse(folder / "traverse.geojson"),
            ortho=_read_ortho(folder),
        )  # fmt: skip
        return self.regions[region_id]

    def get(self, region_id: str) -> RegionData | None:
        return self.regions.get(region_id)
