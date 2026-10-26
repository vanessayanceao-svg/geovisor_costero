"""Módulo de línea de costa y erosión: resultados DSAS existentes y métricas del postproceso.

Se distinguen tres procedencias y se etiquetan en la interfaz:
* ``DSAS``       — valores calculados por DSAS v6.1 (dsas_tasas.shp, informe .txt).
* ``script``     — tasas recalculadas por el script de postproceso (tasas_transectos_*).
* ``geovisor``   — métricas que recalcula este geovisor a partir de las geometrías
                   (longitudes en el CRS métrico, número de líneas, etc.).
No se extrapolan tasas al futuro.
"""
from __future__ import annotations

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .catalogo_datos import CAPAS
from .vectores import CapaNoDisponible, a_metrico, leer_capa

CAMPOS_TASAS = {
    "LRR": ("Tasa de regresión lineal (LRR)", "m/año"),
    "WLR": ("Regresión lineal ponderada (WLR)", "m/año"),
    "EPR": ("Tasa de punto final (EPR)", "m/año"),
    "NSM": ("Movimiento neto (NSM)", "m"),
    "SCE": ("Envolvente de cambio (SCE)", "m"),
}
DESCRIPCION_METRICAS = {
    "LRR": "Pendiente de la regresión lineal de la distancia línea‑base→costa frente al tiempo, con todas las líneas del transecto. Negativo = retroceso.",
    "WLR": "Como LRR, ponderando cada línea por 1/incertidumbre². Negativo = retroceso.",
    "EPR": "(distancia última − distancia primera) / años transcurridos. Negativo = retroceso.",
    "NSM": "Distancia entre la línea más antigua y la más reciente (m). Negativo = retroceso.",
    "SCE": "Distancia entre la línea más alejada y la más cercana a la línea base (m); siempre ≥ 0.",
}


def cargar_tasas_dsas(cfg: dict) -> gpd.GeoDataFrame:
    g = leer_capa(cfg, "dsas_tasas").copy()
    g["procedencia"] = "DSAS v6.1"
    g["id_transecto"] = g["TransOrder"].astype(int)
    return g


def cargar_tasas_script(cfg: dict, resolucion: str = "100m") -> gpd.GeoDataFrame:
    clave = "tasas_script_100m" if resolucion == "100m" else "tasas_script_100m"
    g = leer_capa(cfg, clave).copy()
    g["procedencia"] = "script postproceso"
    return g


def unir_distancia_km(tasas: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    """Añade 'dist_costa_km' (desde Bocas de Ceniza) uniendo con transectos_100m_dsas por TransOrder+BaselineID si existe."""
    try:
        t = leer_capa(cfg, "ivc_transectos", columnas=("BaselineID", "TransOrder", "id_ivc", "dist_costa_km", "zona"))
    except CapaNoDisponible:
        return tasas
    t = pd.DataFrame(t.drop(columns="geometry"))
    out = tasas.merge(t, on=["BaselineID", "TransOrder"], how="left")
    return gpd.GeoDataFrame(out, geometry="geometry", crs=tasas.crs)


def resumen_tasas(g: gpd.GeoDataFrame, campo: str = "LRR") -> dict:
    """Resumen descriptivo de un campo de tasa (importado; no se recalcula nada)."""
    s = pd.to_numeric(g[campo], errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    return {
        "n": int(s.size), "media": float(s.mean()), "mediana": float(s.median()), "min": float(s.min()), "max": float(s.max()),
        "p10": float(s.quantile(0.1)), "p90": float(s.quantile(0.9)),
        "n_erosion": int((s < 0).sum()), "pct_erosion": float((s < 0).mean() * 100),
        "n_acrecion": int((s > 0).sum()), "pct_acrecion": float((s > 0).mean() * 100),
    }


def sectores_criticos(g: gpd.GeoDataFrame, campo: str = "LRR", n: int = 10) -> pd.DataFrame:
    cols = [c for c in ("id_transecto", "TransOrder", "BaselineID", "dist_costa_km", "zona", campo, "LCI95", "EPR", "NSM", "SCE", "ShrCount") if c in g.columns]
    d = pd.DataFrame(g[cols]).copy()
    d[campo] = pd.to_numeric(d[campo], errors="coerce")
    return d.nsmallest(n, campo)


def leer_informe_dsas(cfg: dict) -> dict | None:
    capa = CAPAS["dsas_informe"]
    p = capa.ruta(cfg)
    if not p.exists():
        return None
    texto = p.read_text(encoding="utf-8", errors="replace")
    info = {"texto": texto}
    for clave, patron in {
        "version": r"DSAS version:\s*(\S+)", "fecha_calculo": r"Timestamp of rate calculation:\s*([^\n]+)",
        "fechas": r"Shoreline dates used \(mm/dd/yyyy\):\s*([^\n]+)", "espaciado_m": r"Transect spacing length:\s*(\d+)",
        "crs": r"Coordinate system:\s*([^\n]+)", "intervalo_confianza": r"Confidence Interval \(CI\) selected:\s*([^\n]+)",
        "incertidumbre_defecto": r"Default Uncertainty:\s*(\S+)", "suavizado_m": r"Smoothing distance:\s*(\d+)",
    }.items():
        m = re.search(patron, texto)
        info[clave] = m.group(1).strip() if m else None
    if info.get("fechas"):
        info["n_fechas"] = len([f for f in info["fechas"].split(",") if f.strip()])
    # medias oficiales
    for rate in ("EPR", "LRR", "WLR", "NSM", "SCE"):
        m = re.search(rate + r" OVERALL AVERAGES:.*?average (?:rate|distance):\s*(-?[\d.]+)", texto, re.S)
        if m:
            info[f"media_{rate}"] = float(m.group(1))
    return info


def comparacion_script_dsas(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["dsas_comparacion"].ruta(cfg)
    if not p.exists():
        return None
    return pd.read_csv(p)


def metricas_geovisor_lineas(g: gpd.GeoDataFrame, cfg: dict) -> dict:
    """Métricas que recalcula el geovisor sobre geometrías (CRS métrico)."""
    if g.empty:
        return {"n_lineas": 0, "longitud_m": float("nan")}
    gm = a_metrico(g, cfg)
    return {"n_lineas": int(len(gm)), "longitud_m": float(gm.geometry.length.sum()), "longitud_media_m": float(gm.geometry.length.mean())}


def tabla_tasas_exportable(g: gpd.GeoDataFrame) -> pd.DataFrame:
    cols = [c for c in g.columns if c != "geometry"]
    return pd.DataFrame(g[cols])
