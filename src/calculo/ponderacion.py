"""Ponderación de las variables.

* **EWM** – entropía de Shannon (Shannon, 1948; Zou et al., 2006), como ivc_multicriterio_v2.pesos_ewm de la tesis:
  p_ij = x_ij / Σ_i x_ij; e_j = −(1/ln m) Σ_i p_ij ln p_ij; d_j = 1 − e_j; w_j = d_j / Σ d. Con IC95 por bootstrap de
  bloques espaciales (Kunsch, 1989) o de transectos (iid).
* **FAHP** – proceso analítico jerárquico difuso con números triangulares (TFN). Entrada: matriz de comparación por
  pares en la escala de Saaty (1‑9 y recíprocos), que se fuzzifica como (a−1, a, a+1) (1 → (1,1,1); recíprocos
  invertidos). Dos métodos: media geométrica difusa de Buckley (1985), defuzzificada por centroide, y análisis
  extendido de Chang (1996). Razón de consistencia CR de Saaty (1980) sobre la matriz nítida (valor medio).
* **Pesos iguales**, **pesos manuales** y **combinación FAHP‑EWM**: multiplicativa w_j = wF_j·wE_j / Σ (la habitual en
  la literatura de índices híbridos) o lineal w = α·wF + (1−α)·wE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# índice aleatorio de Saaty (n = 1 … 15)
RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49, 11: 1.51, 12: 1.48, 13: 1.56, 14: 1.57, 15: 1.59}


# ---------------------------------------------------------------------------
# EWM
# ---------------------------------------------------------------------------
def pesos_ewm(X: np.ndarray) -> np.ndarray:
    """Pesos por entropía de Shannon. Una columna constante (o de suma 0) tiene entropía máxima ⇒ divergencia 0 ⇒ peso 0."""
    X = np.asarray(X, float)
    s = X.sum(0)
    p = np.divide(X, s, out=np.zeros_like(X), where=s > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = -np.nansum(np.where(p > 0, p * np.log(p), 0), 0) / np.log(len(X))
    d = 1 - e
    d = np.where((s > 0) & (d > 1e-12), d, 0.0)   # constante ⇒ e = 1 (salvo redondeo) ⇒ d = 0
    if d.sum() <= 0:
        raise ValueError("Todas las variables son constantes: la entropía no define pesos (use pesos iguales o manuales)")
    return d / d.sum()


def ewm_con_ic(X: np.ndarray, bloques: np.ndarray | None = None, n_boot: int = 1000, semilla: int = 2026) -> pd.DataFrame:
    """Pesos EWM, entropía, divergencia e IC95 por bootstrap (de bloques si se dan, si no de filas)."""
    X = np.asarray(X, float)
    ok = np.isfinite(X).all(1)
    if ok.sum() < 5:
        raise ValueError("Menos de 5 transectos con todas las variables: revise las variables con valores vacíos")
    Xo = X[ok]
    p = Xo / Xo.sum(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = -np.nansum(np.where(p > 0, p * np.log(p), 0), 0) / np.log(len(Xo))
    w = pesos_ewm(Xo)
    rng = np.random.default_rng(semilla)
    ws = []
    if bloques is not None:
        b = np.asarray(bloques)[ok]
        ub = np.unique(b)
        idx = {k: np.flatnonzero(b == k) for k in ub}
        for _ in range(n_boot):
            s = np.concatenate([idx[k] for k in rng.choice(ub, len(ub), replace=True)])
            ws.append(pesos_ewm(Xo[s]))
    else:
        for _ in range(n_boot):
            ws.append(pesos_ewm(Xo[rng.integers(0, len(Xo), len(Xo))]))
    ws = np.array(ws)
    out = pd.DataFrame({"entropia_e": e, "divergencia_d": 1 - e, "peso": w, "IC95_inf": np.percentile(ws, 2.5, 0), "IC95_sup": np.percentile(ws, 97.5, 0)})
    if bloques is not None:  # IC iid (transectos) además del de bloques, como en la tesis
        wi = np.array([pesos_ewm(Xo[rng.integers(0, len(Xo), len(Xo))]) for _ in range(n_boot)])
        out["IC95_iid_inf"] = np.percentile(wi, 2.5, 0); out["IC95_iid_sup"] = np.percentile(wi, 97.5, 0)
    return out


# ---------------------------------------------------------------------------
# FAHP
# ---------------------------------------------------------------------------
def matriz_saaty_valida(A: np.ndarray) -> None:
    A = np.asarray(A, float)
    n = A.shape[0]
    if A.shape != (n, n):
        raise ValueError("La matriz debe ser cuadrada")
    if not np.allclose(np.diag(A), 1):
        raise ValueError("La diagonal debe ser 1")
    if not np.isfinite(A).all():
        raise ValueError("La matriz tiene celdas vacías o no numéricas")
    if (A <= 0).any() or (A > 9 + 1e-9).any() or (A < 1 / 9 - 1e-9).any():
        raise ValueError("Juicios fuera de la escala de Saaty (1/9 … 9)")
    if not np.allclose(A * A.T, 1, atol=1e-6):
        raise ValueError("La matriz debe ser recíproca (a_ji = 1/a_ij)")


def consistencia(A: np.ndarray) -> dict:
    """λmáx, CI y CR de Saaty (1980) de la matriz nítida."""
    A = np.asarray(A, float)
    n = A.shape[0]
    vals, vecs = np.linalg.eig(A)
    k = np.argmax(vals.real)
    lam = float(vals[k].real)
    w = np.abs(vecs[:, k].real); w = w / w.sum()
    ci = (lam - n) / (n - 1) if n > 1 else 0.0
    ri = RI.get(n, 1.59)
    cr = ci / ri if ri > 0 else 0.0
    return {"lambda_max": lam, "CI": ci, "CR": cr, "n": n, "pesos_eigen": w, "consistente": cr <= 0.10}


def fuzzificar(A: np.ndarray, delta: float = 1.0) -> np.ndarray:
    """TFN (l, m, u) de cada juicio nítido de Saaty: a>1 → (a−δ, a, a+δ); 1 → (1,1,1); 1/a → (1/(a+δ), 1/a, 1/(a−δ))."""
    A = np.asarray(A, float)
    n = A.shape[0]
    F = np.zeros((n, n, 3))
    for i in range(n):
        for j in range(n):
            a = A[i, j]
            if np.isclose(a, 1):
                F[i, j] = (1, 1, 1)
            elif a > 1:
                F[i, j] = (max(a - delta, 1), a, min(a + delta, 9))
            else:
                b = 1 / a
                F[i, j] = (1 / min(b + delta, 9), 1 / b, 1 / max(b - delta, 1))
    return F


def fahp_buckley(F: np.ndarray) -> pd.DataFrame:
    """Media geométrica difusa (Buckley, 1985): r_i = (Π_j ã_ij)^(1/n); w̃_i = r_i ⊗ (Σ r)^−1; centroide (l+m+u)/3 y normalización."""
    n = F.shape[0]
    r = np.exp(np.log(F).sum(1) / n)                       # (n, 3): l, m, u
    S = r.sum(0)                                            # Σ r = (Σl, Σm, Σu)
    w = np.c_[r[:, 0] / S[2], r[:, 1] / S[1], r[:, 2] / S[0]]
    cr = w.mean(1)
    return pd.DataFrame({"l": w[:, 0], "m": w[:, 1], "u": w[:, 2], "peso_centroide": cr, "peso": cr / cr.sum()})


def fahp_chang(F: np.ndarray) -> pd.DataFrame:
    """Análisis extendido de Chang (1996): S_i = Σ_j ã_ij ⊗ (Σ_i Σ_j ã_ij)^−1; grado de posibilidad V(S_i ≥ S_k); w_i = mín_k V."""
    n = F.shape[0]
    S = F.sum(1)                                           # (n, 3)
    tot = S.sum(0)
    Si = np.c_[S[:, 0] / tot[2], S[:, 1] / tot[1], S[:, 2] / tot[0]]

    def V(a, b):  # posibilidad de a >= b
        la, ma, ua = a; lb, mb, ub = b
        if ma >= mb:
            return 1.0
        if lb >= ua:
            return 0.0
        return (lb - ua) / ((ma - ua) - (mb - lb))

    d = np.array([min(V(Si[i], Si[k]) for k in range(n) if k != i) if n > 1 else 1.0 for i in range(n)])
    w = d / d.sum() if d.sum() > 0 else np.full(n, 1 / n)
    return pd.DataFrame({"l": Si[:, 0], "m": Si[:, 1], "u": Si[:, 2], "grado_minimo": d, "peso": w})


def pesos_fahp(A: np.ndarray, metodo: str = "buckley", delta: float = 1.0) -> tuple[pd.DataFrame, dict]:
    matriz_saaty_valida(A)
    F = fuzzificar(A, delta)
    tab = fahp_buckley(F) if metodo == "buckley" else fahp_chang(F)
    return tab, consistencia(A)


def matriz_desde_tabla(df: pd.DataFrame) -> np.ndarray:
    """Matriz de Saaty desde una tabla cuadrada (índice y columnas = variables); completa los recíprocos faltantes."""
    A = np.array(df.to_numpy(float), dtype=float, copy=True)
    n = A.shape[0]
    for i in range(n):
        A[i, i] = 1.0
        for j in range(n):
            if i != j and (not np.isfinite(A[i, j]) or A[i, j] <= 0) and np.isfinite(A[j, i]) and A[j, i] > 0:
                A[i, j] = 1 / A[j, i]
    return A


# ---------------------------------------------------------------------------
# Otros esquemas y combinaciones
# ---------------------------------------------------------------------------
def pesos_iguales(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n)


def combinar(w_fahp: np.ndarray, w_ewm: np.ndarray, modo: str = "multiplicativa", alfa: float = 0.5) -> np.ndarray:
    a, b = np.asarray(w_fahp, float), np.asarray(w_ewm, float)
    if modo == "multiplicativa":
        w = a * b
        return w / w.sum()
    w = alfa * a + (1 - alfa) * b
    return w / w.sum()
