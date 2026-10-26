"""Lectura, transformación y preparación de capas vectoriales.

Reglas:
* El CRS se toma SIEMPRE del archivo; si falta, la capa se marca como
  «CRS desconocido» y no se dibuja hasta que se declare en config.
* Las operaciones métricas (longitud, área, simplificación) se hacen en el CRS
  métrico configurado (EPSG:32618); la visualización web en EPSG:4326.
* La simplificación es exclusivamente para dibujar; las exportaciones reciben
  la geometría original.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from .cachear import cachear_datos, firma_archivo
from .catalogo_datos import CAPAS, Capa

_log = logging.getLogger("geovisor.vectores")


class CapaNoDisponible(Exception):
    pass


@cachear_datos(ttl=3600, max_entries=48)
def _leer(firma: tuple, capa_interna: str | None, columnas: tuple | None, bbox: tuple | None) -> gpd.GeoDataFrame:
    ruta = firma[0]
    kw = {}
    if capa_interna:
        kw["layer"] = capa_interna
    if columnas:
        kw["columns"] = list(columnas)
    if bbox:
        kw["bbox"] = bbox
    g = gpd.read_file(ruta, engine="pyogrio", **kw)
    if g.crs is None:
        _log.warning("CRS ausente en %s", ruta)
    return g


def leer_capa(cfg: dict, clave: str, columnas: tuple | None = None, bbox: tuple | None = None) -> gpd.GeoDataFrame:
    """Lee una capa del catálogo. Lanza CapaNoDisponible si el archivo no existe."""
    capa = CAPAS[clave]
    ruta = capa.ruta(cfg)
    if not ruta.exists():
        raise CapaNoDisponible(f"{capa.titulo}: archivo no encontrado")
    g = _leer(firma_archivo(ruta), capa.capa, columnas, bbox)
    g.attrs["clave"] = clave
    g.attrs["titulo"] = capa.titulo
    g.attrs["crs_origen"] = str(g.crs) if g.crs is not None else None
    return g


def leer_archivo(ruta: str | Path, capa_interna: str | None = None) -> gpd.GeoDataFrame:
    ruta = Path(ruta)
    if not ruta.exists():
        raise CapaNoDisponible(f"{ruta.name}: archivo no encontrado")
    return _leer(firma_archivo(ruta), capa_interna, None, None)


def a_metrico(g: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    crs = cfg["crs"]["metrico"]
    if g.crs is None:
        raise ValueError("La capa no declara CRS; no se puede reproyectar con seguridad.")
    return g if g.crs.to_string() == crs or (g.crs.to_epsg() and f"EPSG:{g.crs.to_epsg()}" == crs) else g.to_crs(crs)


def a_visual(g: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    crs = cfg["crs"]["visualizacion"]
    if g.crs is None:
        raise ValueError("La capa no declara CRS; no se puede reproyectar con seguridad.")
    if g.crs.to_epsg() == 4326 and crs.upper() == "EPSG:4326":
        return g
    return g.to_crs(crs)


def limpiar(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Quita geometrías nulas/vacías e intenta reparar inválidas."""
    if g.empty:
        return g
    g = g[g.geometry.notna()]
    g = g[~g.geometry.is_empty]
    if (~g.geometry.is_valid).any():
        g = g.copy()
        g["geometry"] = g.geometry.buffer(0) if g.geom_type.isin(["Polygon", "MultiPolygon"]).all() else g.geometry
    return g


def simplificar_para_mapa(g: gpd.GeoDataFrame, cfg: dict, tolerancia_m: float) -> gpd.GeoDataFrame:
    """Simplifica en metros (CRS métrico) y devuelve en CRS de visualización. Solo para dibujar."""
    g = limpiar(g)
    if g.empty:
        return a_visual(g, cfg) if g.crs is not None else g
    if tolerancia_m and tolerancia_m > 0:
        gm = a_metrico(g, cfg).copy()
        gm["geometry"] = gm.geometry.simplify(tolerancia_m, preserve_topology=True)
        return a_visual(gm, cfg)
    return a_visual(g, cfg)


def longitud_m(g: gpd.GeoDataFrame, cfg: dict) -> float:
    if g.empty:
        return float("nan")
    return float(a_metrico(g, cfg).geometry.length.sum())


def area_m2(g: gpd.GeoDataFrame, cfg: dict) -> float:
    if g.empty:
        return float("nan")
    return float(a_metrico(g, cfg).geometry.area.sum())


def bounds_visual(g: gpd.GeoDataFrame, cfg: dict) -> list[list[float]] | None:
    """[[lat_min, lon_min], [lat_max, lon_max]] para folium.fit_bounds."""
    if g is None or g.empty:
        return None
    b = a_visual(g, cfg).total_bounds
    if not np.all(np.isfinite(b)):
        return None
    return [[float(b[1]), float(b[0])], [float(b[3]), float(b[2])]]


def a_geojson(g: gpd.GeoDataFrame, cfg: dict, campos: list[str] | None = None, decimales: int = 6) -> dict:
    """GeoJSON (EPSG:4326) con los atributos indicados, listo para folium."""
    gv = a_visual(g, cfg)
    if campos is not None:
        cols = [c for c in campos if c in gv.columns]
        gv = gv[cols + ["geometry"]]
    gv = _serializable(gv)
    return json.loads(gv.to_json(drop_id=True, to_wgs84=False))


def _serializable(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g.copy()
    for c in g.columns:
        if c == "geometry":
            continue
        s = g[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            g[c] = s.dt.strftime("%Y-%m-%d %H:%M:%S")
        elif s.dtype == object:
            g[c] = s.apply(lambda v: v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
        elif pd.api.types.is_float_dtype(s):
            g[c] = s.round(4).astype(object).where(s.notna(), None)
        elif pd.api.types.is_integer_dtype(s):
            g[c] = s.astype(object).where(s.notna(), None)
    return g


def bbox_a_poligono(b: list[float], crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[box(*b)], crs=crs)


def resumen_capa(g: gpd.GeoDataFrame, cfg: dict) -> dict:
    out = {
        "entidades": int(len(g)),
        "crs": str(g.crs) if g.crs is not None else "desconocido",
        "tipos": ", ".join(sorted(g.geom_type.dropna().unique())) if not g.empty else "—",
    }
    if not g.empty and g.crs is not None:
        gm = a_metrico(g, cfg)
        if gm.geom_type.isin(["LineString", "MultiLineString"]).any():
            out["longitud_total_m"] = float(gm.geometry.length.sum())
        if gm.geom_type.isin(["Polygon", "MultiPolygon"]).any():
            out["area_total_m2"] = float(gm.geometry.area.sum())
        out["bounds_metrico"] = [float(x) for x in gm.total_bounds]
    return out
