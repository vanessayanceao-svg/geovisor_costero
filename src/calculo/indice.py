"""Agregación del índice y métricas de validación/sensibilidad (ivc_multicriterio_v2.py de la tesis, generalizado).

* ``ivc_lineal``: clases 1‑5 → IVC = (Σ w_j c_j − 1)/4 en 0‑1; escala 0‑1 → IVC = Σ w_j x_j.
* ``topsis``: C = D⁻/(D⁺ + D⁻) con normalización vectorial; ideal fijo (clase 5 / valor 1) o relativo.
* ``cvi_gornitz``: raíz cuadrada del producto de las clases dividido por el número de variables (Gornitz, 1991),
  normalizado opcionalmente a 0‑1 por su máximo teórico.
* Validación: ρ de Spearman del índice contra la tasa de cambio (signo invertido: más erosión = más vulnerable) con IC95
  por bootstrap de bloques espaciales; κ ponderado cuadrático entre clasificaciones (Cohen, 1968); VIF y Spearman entre
  variables (redundancia); sensibilidad por perturbación de un peso a la vez (±10 %, ±20 %).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .normalizacion import clase_de_indice_01


def ivc_lineal(X: np.ndarray, w: np.ndarray, escala: str = "1-5") -> np.ndarray:
    X = np.asarray(X, float); w = np.asarray(w, float)
    v = X @ w
    return (v - 1) / 4 if escala == "1-5" else v


def topsis(X: np.ndarray, w: np.ndarray, absoluto: bool = True, escala: str = "1-5", nrm=None) -> tuple[np.ndarray, np.ndarray]:
    X = np.asarray(X, float); w = np.asarray(w, float)
    if nrm is None:
        nrm = np.sqrt(np.nansum(X ** 2, 0))          # norma sobre las alternativas válidas (Hwang y Yoon, 1981)
    nrm = np.where(np.isfinite(nrm) & (nrm > 0), nrm, 1)
    V = w * X / nrm
    if absoluto:
        hi, lo = (5, 1) if escala == "1-5" else (1, 0)
        Amax, Amin = w * hi / nrm, w * lo / nrm
    else:
        Amax, Amin = V.max(0), V.min(0)
    dp = np.sqrt(((V - Amax) ** 2).sum(1)); dm = np.sqrt(((V - Amin) ** 2).sum(1))
    with np.errstate(invalid="ignore", divide="ignore"):
        c = dm / (dp + dm)
    return c, nrm


def cvi_gornitz(X: np.ndarray, normalizar: bool = True) -> np.ndarray:
    X = np.asarray(X, float)
    n = X.shape[1]
    v = np.sqrt(np.exp(np.log(X).sum(1)) / n)
    if normalizar:
        v = v / np.sqrt(5.0 ** n / n)
    return v


def bloques_contiguos(km, n_bloques: int = 8) -> np.ndarray:
    """Bloques espaciales contiguos de igual longitud a lo largo de la costa (para bootstrap y validación)."""
    km = np.asarray(km, float)
    lim = np.linspace(np.nanmin(km), np.nanmax(km) + 1e-9, n_bloques + 1)
    return np.clip(np.searchsorted(lim, km, side="right") - 1, 0, n_bloques - 1)


def rho_ic_bloques(a, b, bloques, n_boot: int = 1000, semilla: int = 2026) -> dict:
    a, b, blo = np.asarray(a, float), np.asarray(b, float), np.asarray(bloques)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b, blo = a[ok], b[ok], blo[ok]
    if ok.sum() < 5:
        return {"rho": np.nan, "IC95_inf": np.nan, "IC95_sup": np.nan, "n": int(ok.sum()), "p": np.nan}
    r, p = spearmanr(a, b)
    rng = np.random.default_rng(semilla)
    ub = np.unique(blo)
    idx = {k: np.flatnonzero(blo == k) for k in ub}
    rs = []
    for _ in range(n_boot):
        s = np.concatenate([idx[k] for k in rng.choice(ub, len(ub), replace=True)])
        rs.append(spearmanr(a[s], b[s])[0])
    return {"rho": float(r), "IC95_inf": float(np.nanpercentile(rs, 2.5)), "IC95_sup": float(np.nanpercentile(rs, 97.5)), "n": int(ok.sum()), "p": float(p)}


def kappa_ponderado(a, b, k: int = 5) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a = a[ok].astype(int) - 1; b = b[ok].astype(int) - 1
    if not len(a):
        return np.nan
    O = np.zeros((k, k))
    for i, j in zip(a, b):
        O[i, j] += 1
    O /= O.sum()
    E = np.outer(O.sum(1), O.sum(0))
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    den = (W * E).sum()
    return float(1 - (W * O).sum() / den) if den > 0 else np.nan


def vif(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, float)
    out = []
    for j in range(X.shape[1]):
        y = X[:, j]; Z = np.column_stack([np.ones(len(X)), np.delete(X, j, 1)])
        b, *_ = np.linalg.lstsq(Z, y, rcond=None)
        sst = ((y - y.mean()) ** 2).sum()
        r2 = 1 - ((y - Z @ b) ** 2).sum() / sst if sst > 0 else 0
        out.append(1 / (1 - r2) if r2 < 1 else np.inf)
    return np.array(out)


def redundancia(X: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(matriz de Spearman entre variables, tabla VIF)."""
    Xo = X.dropna()
    rho = Xo.corr(method="spearman")
    v = pd.DataFrame({"variable": Xo.columns, "VIF": vif(Xo.to_numpy(float))})
    return rho, v


def sensibilidad_pesos(X: np.ndarray, w: np.ndarray, nombres, escala: str = "1-5", deltas=(-0.2, -0.1, 0.1, 0.2), cortes=(0.2, 0.4, 0.6, 0.8)) -> pd.DataFrame:
    """Perturba un peso a la vez (renormalizando) y mide el cambio del índice: media |ΔIVC|, % de transectos que cambian de clase.

    Incluye además la exclusión de cada variable (jackknife, «−100 %»): pesos EWM recalculados sin ella.
    """
    from .ponderacion import pesos_ewm

    cortes = list(cortes)
    base = ivc_lineal(X, w, escala)
    cb = clase_de_indice_01(base, cortes)
    filas = []
    for j, nom in enumerate(nombres):
        for d in deltas:
            w2 = w.copy(); w2[j] = w2[j] * (1 + d); w2 = w2 / w2.sum()
            v = ivc_lineal(X, w2, escala)
            ok = np.isfinite(v) & np.isfinite(base)
            filas.append({"variable": nom, "perturbacion": f"{d:+.0%}", "media_abs_delta_ivc": float(np.mean(np.abs(v[ok] - base[ok]))),
                          "pct_cambia_clase": float(100 * np.mean(clase_de_indice_01(v, cortes)[ok] != cb[ok]))})
        if len(nombres) > 1:
            keep = [k for k in range(len(nombres)) if k != j]
            Xk = X[:, keep]
            okk = np.isfinite(Xk).all(1)
            wk = pesos_ewm(Xk[okk]) if okk.sum() >= 5 else np.full(len(keep), 1 / len(keep))
            v = ivc_lineal(Xk, wk, escala)
            ok = np.isfinite(v) & np.isfinite(base)
            rho = float(pd.Series(v[ok]).corr(pd.Series(base[ok]), method="spearman")) if ok.sum() > 2 else np.nan
            filas.append({"variable": nom, "perturbacion": "excluida (EWM sin la variable)", "media_abs_delta_ivc": float(np.mean(np.abs(v[ok] - base[ok]))),
                          "pct_cambia_clase": float(100 * np.mean(clase_de_indice_01(v, cortes)[ok] != cb[ok])), "rho_con_indice_completo": rho})
    return pd.DataFrame(filas)


def estabilidad_clase_bootstrap(X: np.ndarray, bloques, n_boot: int = 500, semilla: int = 2026, escala: str = "1-5", cortes=(0.2, 0.4, 0.6, 0.8)) -> np.ndarray:
    """% de réplicas (bootstrap de bloques → pesos EWM) en que cada transecto conserva la clase del IVC central (NaN sin dato)."""
    from .ponderacion import pesos_ewm

    cortes = list(cortes)
    X = np.asarray(X, float)
    ok = np.isfinite(X).all(1)
    w0 = pesos_ewm(X[ok])
    c0 = clase_de_indice_01(ivc_lineal(X, w0, escala), cortes)
    blo = np.asarray(bloques)
    ub = np.unique(blo[ok]); idx = {k: np.flatnonzero((blo == k) & ok) for k in ub}
    rng = np.random.default_rng(semilla)
    igual = np.zeros(len(X))
    for _ in range(n_boot):
        s = np.concatenate([idx[k] for k in rng.choice(ub, len(ub), replace=True)])
        w = pesos_ewm(X[s])
        igual += (clase_de_indice_01(ivc_lineal(X, w, escala), cortes) == c0)
    out = 100 * igual / n_boot
    out[~ok] = np.nan
    return out
