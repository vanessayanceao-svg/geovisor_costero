"""Normalización de las variables a una escala común de vulnerabilidad.

* **M1 – clases 1‑5 por umbrales** (la de la tesis, ivc_clasificacion.py): cuatro cortes crecientes y el puntaje de
  cada intervalo (p. ej. [5,4,3,2,1] cuando un valor mayor es menos vulnerable). ``cerrado='derecha'`` → intervalos
  (−∞,c1], (c1,c2], …; ``'izquierda'`` → [c1,c2), … (como «1 a < 4»).
* **Categorías → clase**: diccionario categoría → puntaje 1‑5 (geomorfología, sustrato…); el promedio ponderado por
  área se usa para coberturas y usos (``ponderado_por_area``).
* **M2 – difusa 0‑1** (mín‑máx con sentido): x' = (x − mín)/(máx − mín) o 1 − eso si un valor mayor es menos vulnerable;
  opcionalmente con percentiles p5/p95 como extremos para resistir valores atípicos.
* **Quintiles** (CVI de Gornitz): clase 1‑5 por quintiles de la muestra.
* ``vecino_costa`` rellena categorías faltantes con la del transecto válido más cercano a lo largo de la costa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def por_umbrales(x, cortes, clases, cerrado: str = "derecha") -> np.ndarray:
    """Igual que ivc_clasificacion.por_umbrales (tesis)."""
    cortes = np.asarray(cortes, float)
    if len(cortes) != len(clases) - 1:
        raise ValueError("Se necesitan n−1 cortes para n clases")
    if np.any(np.diff(cortes) <= 0):
        raise ValueError("Los cortes deben ser crecientes")
    lado = "left" if cerrado == "derecha" else "right"
    xv = np.asarray(x, float)
    idx = np.searchsorted(cortes, xv, side=lado)
    out = np.asarray(clases, float)[np.clip(idx, 0, len(clases) - 1)]
    out[~np.isfinite(xv)] = np.nan
    return out


def categorias_a_clase(cat: pd.Series, mapa: dict, defecto=np.nan) -> np.ndarray:
    m = {str(k).strip().lower(): float(v) for k, v in mapa.items()}
    return cat.astype(str).str.strip().str.lower().map(m).fillna(defecto).to_numpy(float)


def ponderado_por_area(tab: pd.DataFrame, mapa: dict, excluir: tuple = ("sin_dato",)) -> np.ndarray:
    """Promedio de los puntajes de clase ponderado por el % de área de cada categoría (tabla de vector_categorico)."""
    m = {str(k).strip().lower(): float(v) for k, v in mapa.items()}
    cols = [c for c in tab.columns if str(c).strip().lower() in m and c not in excluir]
    if not cols:
        return np.full(len(tab), np.nan)
    a = tab[cols].to_numpy(float)
    w = np.array([m[str(c).strip().lower()] for c in cols])
    tot = a.sum(1)
    return np.where(tot > 0, (a * w).sum(1) / np.where(tot > 0, tot, 1), np.nan)


def difusa_01(x, mayor_mas_vulnerable: bool = True, p_inf: float | None = None, p_sup: float | None = None) -> np.ndarray:
    xv = np.asarray(x, float)
    ok = np.isfinite(xv)
    if not ok.any():
        return np.full(len(xv), np.nan)
    lo = np.nanpercentile(xv, p_inf) if p_inf is not None else np.nanmin(xv)
    hi = np.nanpercentile(xv, p_sup) if p_sup is not None else np.nanmax(xv)
    out = np.full(len(xv), np.nan)
    if hi > lo:
        out[ok] = np.clip((xv[ok] - lo) / (hi - lo), 0, 1)
    else:
        out[ok] = 0.5
    return out if mayor_mas_vulnerable else 1 - out


def quintiles(x, mayor_mas_vulnerable: bool = True) -> np.ndarray:
    v = pd.Series(np.asarray(x, float))
    q = np.full(len(v), np.nan)
    ok = v.notna().values
    if ok.sum() >= 5:
        r = v[ok].rank(method="first")
        q[ok] = pd.qcut(r, 5, labels=False).to_numpy() + 1
    return q if mayor_mas_vulnerable else 6 - q


def vecino_costa(serie: pd.Series, km, invalidos=("sin_dato", "nan", "")) -> tuple[pd.Series, np.ndarray]:
    s = serie.copy()
    km = np.asarray(km, float)
    malo = s.isna() | s.astype(str).str.lower().isin(invalidos)
    ok = np.flatnonzero(~malo.values)
    if not ok.size:
        return s, malo.values.astype(int)
    for i in np.flatnonzero(malo.values):
        s.iloc[i] = s.iloc[ok[np.argmin(np.abs(km[ok] - km[i]))]]
    return s, malo.values.astype(int)


def clase_de_indice_01(v, cortes=(0.2, 0.4, 0.6, 0.8)) -> np.ndarray:
    """Clase 1‑5 de un índice en 0‑1 por intervalos (los de la tesis: iguales de 0,2)."""
    v = np.asarray(v, float)
    out = np.searchsorted(np.asarray(cortes, float), v, side="right") + 1.0
    out[~np.isfinite(v)] = np.nan
    return np.minimum(out, 5)
