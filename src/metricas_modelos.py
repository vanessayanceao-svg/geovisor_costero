"""Evaluación de modelos: tablas de métricas verificadas (validación anidada v4) e importación de tablas externas.

Solo se muestran métricas que existen en los archivos de resultados. El
geovisor no declara un modelo «ganador»: presenta las métricas con su IC95 y
la comparación pareada tal como fueron calculadas.
"""
from __future__ import annotations

import io
import json

import pandas as pd

from .catalogo_datos import CAPAS

NOMBRES_MODELOS = {
    "persistencia": "Persistencia (Δ = 0)", "media": "Cambio medio del entrenamiento", "ridge": "Ridge (historia)",
    "rf_hist": "Random Forest (historia)", "rf_ivc": "Random Forest (variables IVC + historia)", "ts": "CNN‑LSTM timestack",
    "ts_hist": "CNN‑LSTM timestack + historia", "serie": "LSTM (serie)", "ts_hist_do05": "CNN‑LSTM + historia (dropout 0,5)",
    "ts_hist_l2": "CNN‑LSTM + historia (L2)", "apil_nnls_todos": "Apilamiento NNLS (todas las bases)", "prom_historia": "Promedio de modelos de historia",
    "persistencia_amortiguada": "Persistencia amortiguada",
}
METRICAS = {
    "habilidad_vs_persistencia": ("R²_OS frente a persistencia", "—", "Reducción relativa del MSE respecto de la persistencia (Campbell y Thompson, 2008). >0 mejora."),
    "RMSE_Delta": ("RMSE de Δ", "m/año", "Raíz del error cuadrático medio del cambio de tasa (2005‑2026 − 1984‑2005), fuera de bloque."),
    "MAE_Delta": ("MAE de Δ", "m/año", "Error absoluto medio del cambio de tasa, fuera de bloque."),
    "R2_Delta": ("R² de Δ", "—", "Coeficiente de determinación del cambio de tasa (fuera de bloque)."),
    "rho_Delta": ("ρ de Spearman de Δ", "—", "Correlación de rangos entre Δ observado y predicho."),
    "RMSE_tasa": ("RMSE de la tasa 2005‑2026", "m/año", "Error de la tasa reconstruida (LRR 1984‑2005 + Δ)."),
    "MAE_tasa": ("MAE de la tasa 2005‑2026", "m/año", ""),
    "R2_tasa_2005_2026": ("R² de la tasa 2005‑2026", "—", ""),
    "coincidencia_clase_cambio_pct": ("Coincidencia de clase de cambio", "%", "Porcentaje de transectos cuya clase de la variable de cambio coincide con la observada."),
    "coincidencia_clase_IVC_2026_pct": ("Coincidencia de clase del IVC 2026", "%", ""),
    "MAE_IVC_2026": ("MAE del IVC 2026", "0‑1", ""),
}


def cargar_metricas_anidadas(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["metricas_anidadas"].ruta(cfg)
    if not p.exists():
        return None
    d = pd.read_csv(p)
    d["nombre"] = d["modelo"].map(NOMBRES_MODELOS).fillna(d["modelo"])
    return d


def cargar_comparacion(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["comparacion_pareada"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_conformal(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["conformal_resumen"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_mse_bloque(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["mse_bloque"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_predicciones_anidadas(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["predicciones_anidadas"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_config_anidada(cfg: dict) -> dict | None:
    p = CAPAS["config_anidada"].ruta(cfg)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cargar_bloques(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["bloques"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_validacion_coastsat(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["validacion_coastsat_manual"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def importar_tabla_metricas(contenido: bytes, nombre: str) -> pd.DataFrame:
    """Importa una tabla de métricas externa (CSV o Excel). Se exige una columna 'modelo'."""
    if nombre.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(contenido))
    else:
        df = pd.read_csv(io.BytesIO(contenido))
    if "modelo" not in {c.lower() for c in df.columns}:
        raise ValueError("La tabla debe tener una columna 'modelo'.")
    return df


def metadatos_evaluacion(cfg_anidada: dict | None) -> dict:
    """Metadatos de la validación tal como están en configuracion_anidada.json (sin completar vacíos)."""
    if not cfg_anidada:
        return {}
    return {
        "Conjunto de prueba": f"{cfg_anidada.get('n_bloques', '?')} bloques espaciales contiguos (validación anidada, fuera de bloque)",
        "Zona de exclusión": f"{cfg_anidada.get('buffer_km', '?')} km alrededor del bloque de prueba",
        "Réplicas bootstrap (IC95)": cfg_anidada.get("n_boot"),
        "Semilla": cfg_anidada.get("semilla"),
        "Variable objetivo": "Δ = LRR 2005‑2026 − LRR 1984‑2005 (m/año); referencia: persistencia (Δ = 0)",
        "Método de referencia": "Tasa observada 2005‑2026 por DSAS v6.1 sobre líneas anuales corregidas por marea",
        "Modelo principal predeclarado": cfg_anidada.get("principal_predeclarado"),
        "Unidades": "m/año (tasas); IVC en 0‑1; porcentajes de coincidencia de clase",
    }
