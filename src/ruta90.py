"""Priorización de tramos de la Ruta 90 (Troncal del Caribe).

Fuente de la prioridad: ``Multicriterio/priorizacion_ruta90_v4.csv`` (fig_escenarios_v4.py → ruta90_v4): para cada tramo de
1 km de costa con la vía a ≤ 1000 m, año en que la línea de costa proyectada (persistencia amortiguada por ventanas de
21 años + regla de Bruun SSP5‑8.5, interpolada entre 2026, 2050 y 2100) iguala la distancia costa‑vía de 2026.
Prioridad: Alta (≤ 2050), Media (2050–2100), Baja (> 2100 o sin alcance).

El geovisor NO recalcula los años: solo reproduce el trazado del mapa de la Figura 37 (``segmentos_ruta``): la vía se
divide en segmentos de ~50 m y cada uno toma la prioridad del tramo de 1 km de costa más cercano (por el punto P0 de 2026
del transecto IVC más próximo); a más de 1,3 km de la costa o fuera de los tramos analizados queda «sin análisis».
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from shapely.strtree import STRtree

from .catalogo_datos import CAPAS
from .vectores import leer_capa, a_metrico, CapaNoDisponible

COLORES = {"Alta (antes de 2050)": "#D62F2F", "Media (2050–2100)": "#F28E1C", "Baja (después de 2100 o sin alcance)": "#A6A29A", "Sin análisis (> 1,3 km de la costa)": "#6b6a64"}
ORDEN_PRIORIDAD = list(COLORES)


def cargar_priorizacion(cfg: dict, version: str = "v4") -> pd.DataFrame:
    clave = "ruta90_priorizacion" if version == "v4" else "ruta90_priorizacion_v3"
    c = CAPAS[clave]
    if not c.disponible(cfg):
        raise CapaNoDisponible(f"{c.titulo}: no se encontró {c.relativa}")
    d = pd.read_csv(c.ruta(cfg), encoding="utf-8-sig")
    for col in ("anio_alcance", "anio_alcance_erosion_rapida", "anio_alcance_erosion_lenta"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    d["prioridad"] = d["prioridad"].astype(str)
    return d.sort_values("km_inicio").reset_index(drop=True)


def resumen(d: pd.DataFrame) -> dict:
    fin = d[np.isfinite(d["anio_alcance"])]
    primero = fin.sort_values("anio_alcance").iloc[0] if len(fin) else None
    return {
        "n_tramos": int(len(d)),
        "n_alta": int((d["prioridad"].str.startswith("Alta")).sum()),
        "n_media": int((d["prioridad"].str.startswith("Media")).sum()),
        "n_baja": int((d["prioridad"].str.startswith("Baja")).sum()),
        "km_alta": float((d["prioridad"].str.startswith("Alta")).sum()),  # tramos de 1 km
        "primer_tramo": None if primero is None else str(primero["tramo"]),
        "primer_anio": None if primero is None else float(primero["anio_alcance"]),
        "primer_dist": None if primero is None else float(primero["dist_min_ruta90_m"]),
        "n_sin_alcance": int((~np.isfinite(d["anio_alcance"])).sum()),
    }


def segmentos_ruta(cfg: dict, d: pd.DataFrame, paso_m: float = 50.0, umbral_m: float = 1300.0) -> gpd.GeoDataFrame:
    """Segmentos de ~50 m de la Ruta 90 (EPSG:32618) con la prioridad del tramo de costa más cercano."""
    ruta = a_metrico(leer_capa(cfg, "ruta90"), cfg)
    costa = a_metrico(leer_capa(cfg, "ivc_costa"), cfg)
    if "x_p0" in costa.columns and "y_p0" in costa.columns:
        p0 = gpd.GeoSeries(gpd.points_from_xy(costa["x_p0"], costa["y_p0"]), crs=costa.crs)
        if costa.crs is None or p0.isna().any() or (p0.x.abs() < 1000).any():  # coordenadas no métricas: usar el centroide
            p0 = costa.geometry.centroid
    else:
        p0 = costa.geometry.centroid
    arbol = STRtree(list(p0.geometry if hasattr(p0, "geometry") else p0))
    km = costa["dist_costa_km"].to_numpy()
    prio = dict(zip(d["km_inicio"].astype(int), d["prioridad"]))
    anio = dict(zip(d["km_inicio"].astype(int), d["anio_alcance"]))
    tramo_txt = dict(zip(d["km_inicio"].astype(int), d["tramo"]))
    filas = []
    for geom in ruta.geometry:
        partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        for ln in partes:
            n = max(1, int(np.ceil(ln.length / paso_m)))
            dist = np.linspace(0, ln.length, n + 1)
            pts = [ln.interpolate(x) for x in dist]
            for a, b in zip(pts[:-1], pts[1:]):
                seg = LineString([a, b])
                m = seg.interpolate(0.5, normalized=True)
                i = int(arbol.nearest(m))
                dm = float(m.distance(p0.iloc[i]))
                tr = int(np.floor(km[i]))
                if dm <= umbral_m and tr in prio:
                    filas.append({"geometry": seg, "prioridad": prio[tr], "tramo": tramo_txt[tr], "km_costa": tr,
                                  "anio_alcance": anio[tr], "dist_costa_m": round(dm)})
                else:
                    filas.append({"geometry": seg, "prioridad": "Sin análisis (> 1,3 km de la costa)", "tramo": None, "km_costa": None,
                                  "anio_alcance": np.nan, "dist_costa_m": round(dm)})
    g = gpd.GeoDataFrame(filas, geometry="geometry", crs=ruta.crs)
    g["anio_txt"] = g["anio_alcance"].map(lambda v: "—" if pd.isna(v) else ("> 2110 (sin alcance)" if not np.isfinite(v) else f"{v:.1f}"))
    return g


def tramos_costa(cfg: dict, d: pd.DataFrame) -> gpd.GeoDataFrame:
    """Segmentos de la línea de costa 2026 (ivc_costa) agrupados por tramo de 1 km con su prioridad (para dibujar junto a la vía)."""
    costa = leer_capa(cfg, "ivc_costa")
    costa = costa[["id_ivc", "dist_costa_km", "geometry"]].copy()
    costa["km_costa"] = np.floor(costa["dist_costa_km"]).astype(int)
    d2 = d[["km_inicio", "tramo", "prioridad", "anio_alcance", "dist_min_ruta90_m"]].rename(columns={"km_inicio": "km_costa"})
    g = costa.merge(d2, on="km_costa", how="inner")
    g["anio_txt"] = g["anio_alcance"].map(lambda v: "> 2110 (sin alcance)" if not np.isfinite(v) else f"{v:.1f}")
    return gpd.GeoDataFrame(g, geometry="geometry", crs=costa.crs)
