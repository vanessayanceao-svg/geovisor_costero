"""Predicciones y escenarios: líneas de costa proyectadas y mapas del IVC futuro.

Solo se muestran los horizontes realmente procesados (hoy: 2050 y 2100). Los
horizontes previstos en config (2030, 2040, 2075) aparecen como «no procesado»
y no se interpola nada. Las bandas p05–p95 provienen de las 2000 réplicas
Monte Carlo registradas en ``configuracion_proyeccion.json``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .catalogo_datos import CAPAS
from .vectores import CapaNoDisponible, leer_capa

VARIANTES = {
    "proy_amortiguada": "Persistencia amortiguada (recomendada en LEEME_version4)",
    "proy_ridge": "Ridge (8 rasgos), tendencia regional centrada",
    "proy_tendencia": "Ridge (8 rasgos), tendencia regional aprendida",
}

TIPOS_LINEA = {
    "observada": ("Observación histórica (2026)", "solid"),
    "central": ("Resultado del modelo (central)", "solid"),
    "p05": ("Banda de incertidumbre p05 (Monte Carlo)", "4 6"),
    "p95": ("Banda de incertidumbre p95 (Monte Carlo)", "4 6"),
    "persistencia": ("Escenario de referencia: persistencia", "10 6"),
}


def variantes_disponibles(cfg: dict) -> dict[str, str]:
    return {k: v for k, v in VARIANTES.items() if CAPAS[k].disponible(cfg)}


def cargar_lineas(cfg: dict, variante: str) -> gpd.GeoDataFrame:
    g = leer_capa(cfg, variante).copy()
    g["linea"] = g["linea"].astype(str)
    g["anio"] = g["linea"].str.extract(r"^(\d{4})")[0].astype("Int64")
    g["tipo"] = g["linea"].apply(_tipo)
    return g


def _tipo(etiqueta: str) -> str:
    if etiqueta == "2026":
        return "observada"
    if etiqueta.endswith("_p05"):
        return "p05"
    if etiqueta.endswith("_p95"):
        return "p95"
    if etiqueta.endswith("_persistencia"):
        return "persistencia"
    return "central"


def anios_procesados(g: gpd.GeoDataFrame) -> list[int]:
    return sorted(int(a) for a in g.loc[g["tipo"] != "observada", "anio"].dropna().unique())


def estado_horizontes(cfg: dict, procesados: list[int]) -> list[dict]:
    previstos = cfg["predicciones"].get("horizontes_previstos", [])
    todos = sorted(set(previstos) | set(procesados))
    return [{"anio": a, "estado": "procesado" if a in procesados else "no procesado"} for a in todos]


def metadatos(cfg: dict, variante: str) -> dict | None:
    p = CAPAS[variante + "_config"].ruta(cfg)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["_archivo"] = p.name
    d["_modificado"] = pd.Timestamp(p.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")
    return d


def resumen(cfg: dict, variante: str) -> pd.DataFrame | None:
    p = CAPAS[variante + "_resumen"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def por_transecto(cfg: dict, variante: str) -> pd.DataFrame | None:
    p = CAPAS[variante + "_transectos"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def escenarios_resumen(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["escenarios_resumen_v4"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def escenarios_detalle(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["escenarios_resumen"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def bruun(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["bruun_resumen"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def requisitos_para_activar() -> str:
    return (
        "Para activar este módulo se necesita:\n"
        "• **Líneas de costa proyectadas**: GeoPackage con capa `lineas`, CRS declarado y campo `linea` con la etiqueta "
        "`<año>`, `<año>_p05`, `<año>_p95` o `<año>_persistencia` (como `Modelos/07_Proyecciones/*/lineas_costa_proyectadas.gpkg`).\n"
        "• **Metadatos**: `configuracion_proyeccion.json` junto al GeoPackage (modelo, ventanas, réplicas, supuestos).\n"
        "• **IVC futuro**: rásteres `ivc_<ssp>_<año>*.tif` y columnas `ivc_ewm_total_<ssp>_<año>` (con `_inf`/`_sup`) en los transectos del IVC."
    )
