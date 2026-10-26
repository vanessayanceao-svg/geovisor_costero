"""Tasas de cambio de la línea de costa por transecto, con las definiciones de DSAS (Himmelstoss et al., 2021):

* NSM: movimiento neto (última − primera distancia, m); SCE: envolvente (máx − mín, m).
* EPR: tasa de punto final (NSM / años entre la primera y la última línea), con su incertidumbre
  EPRUNC = sqrt(unc1² + unc2²) / años.
* LRR: pendiente de la regresión lineal ordinaria de la distancia sobre el año decimal; LR2 = R²; LSE = error
  estándar de la estimación; LCI95 = t(0,975; n−2) · error estándar de la pendiente.
* WLR: regresión ponderada con pesos 1/unc²; WR2, WSE, WCI análogos.
* Tasas por ventana (p. ej. 1984‑2005, 2005‑2026) con el mismo estimador LRR, para la validación y las proyecciones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _ols(t, d, w=None) -> dict:
    n = len(t)
    if n < 2:
        return {}
    if w is None:
        w = np.ones(n)
    W = w / w.sum()
    tm, dm = (W * t).sum(), (W * d).sum()
    sxx = (W * (t - tm) ** 2).sum()
    if sxx <= 0:
        return {}
    b = (W * (t - tm) * (d - dm)).sum() / sxx
    a = dm - b * tm
    res = d - (a + b * t)
    sst = (w * (d - dm) ** 2).sum()
    sse = (w * res ** 2).sum()
    r2 = 1 - sse / sst if sst > 0 else np.nan
    if n > 2:
        s2 = sse / (n - 2)
        se_b = np.sqrt(s2 / (w * (t - tm) ** 2).sum())
        se_est = np.sqrt(s2)
        ci = stats.t.ppf(0.975, n - 2) * se_b
    else:
        se_b = se_est = ci = np.nan
    return {"tasa": b, "r2": r2, "se": se_est, "ci95": ci}


def tasas_por_transecto(inter: pd.DataFrame, umbral_lineas: int = 10) -> pd.DataFrame:
    """Tabla con NSM, SCE, EPR, EPRUNC, LRR, LR2, LSE, LCI95, WLR, WR2, WSE, WCI, n_lineas, fecha_ini, fecha_fin."""
    filas = []
    for id_t, g in inter.groupby("id_t"):
        g = g.sort_values("anio_dec")
        t, d, unc = g["anio_dec"].to_numpy(float), g["distancia_m"].to_numpy(float), g["unc_m"].to_numpy(float)
        n = len(g)
        fila = {"id_t": id_t, "n_lineas": n, "fecha_ini": g["fecha"].iloc[0], "fecha_fin": g["fecha"].iloc[-1],
                "NSM": d[-1] - d[0], "SCE": d.max() - d.min()}
        anos = t[-1] - t[0]
        if anos > 0:
            fila["EPR"] = (d[-1] - d[0]) / anos
            fila["EPRUNC"] = np.sqrt(unc[0] ** 2 + unc[-1] ** 2) / anos
        if n >= umbral_lineas:
            o = _ols(t, d)
            fila.update({"LRR": o.get("tasa"), "LR2": o.get("r2"), "LSE": o.get("se"), "LCI95": o.get("ci95")})
            w = 1.0 / np.where(unc > 0, unc, np.nan) ** 2
            if np.isfinite(w).all():
                o = _ols(t, d, w)
                fila.update({"WLR": o.get("tasa"), "WR2": o.get("r2"), "WSE": o.get("se"), "WCI": o.get("ci95")})
        filas.append(fila)
    return pd.DataFrame(filas)


def tasa_ventana(inter: pd.DataFrame, a0: float, a1: float, minimo: int = 3) -> pd.Series:
    """LRR de las líneas con año decimal en [a0, a1] por transecto (NaN si hay menos de ``minimo`` líneas)."""
    sub = inter[(inter["anio_dec"] >= a0) & (inter["anio_dec"] <= a1)]
    out = {}
    for id_t, g in sub.groupby("id_t"):
        if len(g) >= minimo:
            o = _ols(g["anio_dec"].to_numpy(float), g["distancia_m"].to_numpy(float))
            out[id_t] = o.get("tasa", np.nan)
    return pd.Series(out, name=f"LRR_{int(a0)}_{int(a1)}")


def resumen_tasas(T: pd.DataFrame, campo: str = "LRR") -> dict:
    x = pd.to_numeric(T.get(campo), errors="coerce").dropna()
    if x.empty:
        return {}
    return {"n": int(len(x)), "media": float(x.mean()), "mediana": float(x.median()), "min": float(x.min()), "max": float(x.max()),
            "pct_retroceso": float((x < 0).mean() * 100), "pct_erosion_mayor_1": float((x < -1).mean() * 100)}
