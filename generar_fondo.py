"""Genera la imagen de fondo transparente del geovisor a partir de los datos reales.

Salida: assets/fondo_mapa_claro.png y assets/fondo_mapa_oscuro.png (PNG RGBA).
Contenido: mapa general del mundo en puntos hexagonales (tierra de Natural Earth 1:110m, dominio público,
assets/tierra_mundo_110m.geojson) con el Caribe colombiano resaltado y un marcador en la Barra de Salamanca.
Sin línea de costa, sin ejes ni texto. Si falta el GeoJSON se genera un patrón de olas.

Uso:  python generar_fondo.py        (se ejecuta también automáticamente al abrir la app si no existen los PNG)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.configuracion import RAIZ_GEOVISOR, cargar_config

_log = logging.getLogger("geovisor.fondo")
ASSETS = RAIZ_GEOVISOR / "assets"


def _puntos_mundo(paso: float = 1.0):
    """Malla de puntos sobre la tierra del mundo (Natural Earth 1:110m vía world-atlas, dominio público)."""
    import geopandas as gpd
    import shapely

    p = ASSETS / "tierra_mundo_110m.geojson"
    if not p.exists():
        return None
    partes = gpd.read_file(p).geometry.explode(ignore_index=True).buffer(0)
    b = partes.bounds
    # fuera: trozos degenerados que cruzan el antimeridiano como una franja (Fiyi, isla Wrangel) y polígonos diminutos
    partes = partes[(partes.area > 0.05) & ~(((b.maxx - b.minx) > 300) & ((b.maxy - b.miny) < 5))]
    lons = np.arange(-180 + paso / 2, 180, paso)
    lats = np.arange(-60 + paso / 2, 84, paso)
    LON, LAT = np.meshgrid(lons, lats)
    puntos = shapely.points(LON.ravel(), LAT.ravel())
    arbol = shapely.STRtree(partes.values)
    idx_pts, _ = arbol.query(puntos, predicate="within")
    dentro = np.zeros(len(puntos), dtype=bool)
    dentro[np.unique(idx_pts)] = True
    return LON.ravel()[dentro], LAT.ravel()[dentro]


def generar(cfg: dict | None = None, forzar: bool = False) -> dict[str, Path]:
    """Mapa general del mundo en puntos hexagonales (sin línea de costa), centrado en el Caribe."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cfg = cfg or cargar_config()
    ASSETS.mkdir(exist_ok=True)
    salidas = {"claro": ASSETS / "fondo_mapa_claro.png", "oscuro": ASSETS / "fondo_mapa_oscuro.png"}
    if not forzar and all(p.exists() for p in salidas.values()):
        return salidas
    pts = _puntos_mundo(1.0)
    for tema, ruta in salidas.items():
        col = (0.11, 0.14, 0.25) if tema == "claro" else (1, 1, 1)
        fig = plt.figure(figsize=(16, 8), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        fig.patch.set_alpha(0)
        ax.patch.set_alpha(0)
        if pts is not None:
            lon, lat = pts
            # resaltar suavemente el Caribe colombiano (Barra de Salamanca ≈ -74.6, 11.0)
            d = np.hypot((lon + 74.6) / 18, (lat - 11.0) / 12)
            alpha = np.clip(0.30 - 0.19 * d, 0.07, 0.30) if tema == "claro" else np.clip(0.24 - 0.15 * d, 0.05, 0.24)
            colores = np.column_stack([np.full(len(lon), col[0]), np.full(len(lon), col[1]), np.full(len(lon), col[2]), alpha])
            ax.scatter(lon, lat, s=9, c=colores, linewidths=0, marker="h")
            ax.scatter([-74.6], [11.0], s=120, c=[(0.23, 0.42, 0.94, 0.35)], linewidths=0, marker="o")
            ax.scatter([-74.6], [11.0], s=28, c=[(0.10, 0.70, 0.65, 0.9)], linewidths=0, marker="o")
            ax.set_xlim(-180, 180)
            ax.set_ylim(-60, 84)
        else:
            t = np.linspace(0, 1, 400)
            for k in range(6):
                ax.plot(t, 0.5 + 0.06 * k + 0.02 * np.sin(40 * t + k), color=col, alpha=0.2, lw=1.5)
        ax.set_aspect("auto")
        fig.savefig(ruta, transparent=True)
        plt.close(fig)
    return salidas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for k, v in generar(forzar=True).items():
        print(k, v, f"{v.stat().st_size / 1024:.0f} KB")
