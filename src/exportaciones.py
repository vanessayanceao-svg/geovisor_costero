"""Exportación de capas y tablas sin tocar los originales.

* GeoJSON: siempre en EPSG:4326 (requisito de la especificación RFC 7946); se informa el CRS.
* GeoPackage: conserva el CRS original del archivo fuente.
* CSV: atributos sin geometría (opcionalmente con WKT en el CRS original).
Los archivos se escriben en ``resultados/exportaciones`` y también se devuelven
en memoria para el botón de descarga.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .configuracion import ruta as ruta_cfg


def _nombre_seguro(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s.strip())
    return s.strip("_")[:80] or "capa"


def _sello() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def exportar_geojson(g: gpd.GeoDataFrame, nombre: str, cfg: dict, guardar: bool = True) -> tuple[bytes, str, str]:
    """Devuelve (bytes, nombre_archivo, crs_exportado)."""
    if g.crs is None:
        raise ValueError("La capa no tiene CRS; no se exporta para no producir coordenadas ambiguas.")
    g4326 = g.to_crs("EPSG:4326") if g.crs.to_epsg() != 4326 else g
    g4326 = _serializable(g4326)
    datos = g4326.to_json(drop_id=True).encode("utf-8")
    archivo = f"{_nombre_seguro(nombre)}_{_sello()}.geojson"
    if guardar:
        p = ruta_cfg(cfg, "exportaciones") / archivo
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
    return datos, archivo, "EPSG:4326"


def exportar_gpkg(g: gpd.GeoDataFrame, nombre: str, cfg: dict, guardar: bool = True) -> tuple[bytes, str, str]:
    if g.crs is None:
        raise ValueError("La capa no tiene CRS; no se exporta.")
    archivo = f"{_nombre_seguro(nombre)}_{_sello()}.gpkg"
    p = ruta_cfg(cfg, "exportaciones") / archivo
    p.parent.mkdir(parents=True, exist_ok=True)
    _serializable(g).to_file(p, driver="GPKG", layer=_nombre_seguro(nombre), engine="pyogrio")
    datos = p.read_bytes()
    if not guardar:
        p.unlink(missing_ok=True)
    return datos, archivo, g.crs.to_string()


def exportar_csv(df: pd.DataFrame | gpd.GeoDataFrame, nombre: str, cfg: dict, con_wkt: bool = False, guardar: bool = True) -> tuple[bytes, str, str | None]:
    d = pd.DataFrame(df).copy()
    crs = None
    if isinstance(df, gpd.GeoDataFrame) and "geometry" in d.columns:
        crs = df.crs.to_string() if df.crs is not None else None
        if con_wkt:
            d["wkt"] = df.geometry.to_wkt()
        d = d.drop(columns="geometry")
    datos = d.to_csv(index=False).encode("utf-8-sig")
    archivo = f"{_nombre_seguro(nombre)}_{_sello()}.csv"
    if guardar:
        p = ruta_cfg(cfg, "exportaciones") / archivo
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
    return datos, archivo, crs


def exportar_png_mapa(capas: list[tuple[gpd.GeoDataFrame, dict]], titulo: str, cfg: dict, guardar: bool = True, dpi: int | None = None) -> tuple[bytes, str]:
    """Mapa estático PNG (matplotlib) de las capas vectoriales indicadas, en el CRS métrico."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dpi = dpi or int(cfg["exportacion"].get("png_dpi", 150))
    fig, ax = plt.subplots(figsize=(11, 5), dpi=dpi)
    fig.patch.set_facecolor("#0b1a2a")
    ax.set_facecolor("#0b1a2a")
    crs = cfg["crs"]["metrico"]
    for g, estilo in capas:
        if g is None or g.empty or g.crs is None:
            continue
        g.to_crs(crs).plot(ax=ax, **estilo)
    ax.set_title(titulo, color="#e8eef5", fontsize=11, loc="left")
    ax.tick_params(colors="#aab7c4", labelsize=7)
    for s in ax.spines.values():
        s.set_color("#334")
    ax.set_xlabel(f"Este (m) — {crs}", color="#aab7c4", fontsize=8)
    ax.set_ylabel("Norte (m)", color="#aab7c4", fontsize=8)
    ax.set_aspect("equal")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7, loc="lower right", facecolor="#102234", edgecolor="#334", labelcolor="#e8eef5")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    datos = buf.getvalue()
    archivo = f"{_nombre_seguro(titulo)}_{_sello()}.png"
    if guardar:
        p = ruta_cfg(cfg, "exportaciones") / archivo
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
    return datos, archivo


def _serializable(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g.copy()
    for c in g.columns:
        if c == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(g[c]):
            g[c] = g[c].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif str(g[c].dtype) == "Int64":
            g[c] = g[c].astype("float")
    return g
