"""Proyección de la línea de costa y del IVC (generalización de Modelos/07_Proyecciones de la tesis).

1. **Ventanas**: la serie de intersecciones se divide en ventanas consecutivas de ``L`` años (p. ej. 1984‑2005 y
   2005‑2026). En cada ventana se calculan la tasa LRR y los rasgos de la historia (tasa de los últimos 10 años,
   aceleración, variabilidad interanual, media de los vecinos a 2 km y anomalías a 1, 2 y 3 km).
2. **Modelo de transición** Δ = r(W_{k+1}) − r(W_k) en función de los rasgos de W_k:
   * ``persistencia``: Δ = 0 (la tasa se mantiene);
   * ``amortiguada``: Δ = b0 + b1·(r − media de vecinos 2 km) (persistencia amortiguada hacia la tendencia del sector);
   * ``ridge`` / ``rf``: regresión ridge o bosque aleatorio sobre los 8 rasgos, con **validación en bloques espaciales
     contiguos y zona de exclusión** (R²_OS frente a la persistencia, Campbell y Thompson, 2008) y residuos fuera de
     muestra para el Monte Carlo.
   Con una sola ventana histórica solo es posible la persistencia.
3. **Recursión** hacia el futuro por ventanas de ``L`` años hasta cubrir el último horizonte; tendencia «centrada»
   (se conserva la redistribución espacial aprendida, no el cambio medio regional); Monte Carlo con el campo de
   residuos fuera de muestra desplazado circularmente a lo largo de la costa y un cambio regional aleatorio por paso.
4. **Posición**: x(T) = x(ref) + ∫ r dt (m, + = acreción). Líneas proyectadas central / p05 / p95 / persistencia.
5. **Bruun** (opcional): retroceso adicional por el ascenso del nivel del mar por encima del ritmo histórico,
   R = E·ΔS·L*/(h* + B) con h* de Hallermeier (1981), L* del perfil de equilibrio de Dean (1991) y E ~ triangular.
6. **IVC futuro**: con los pesos fijos del presente, se reclasifican las variables «dinámicas» según el rol declarado:
   tasa (tasa media de los L años anteriores a T), distancia a infraestructura y ancho de barra (menos el retroceso
   acumulado) y % de terreno bajo el nivel del mar del escenario (si se dispone del DEM).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString

from .normalizacion import por_umbrales, clase_de_indice_01
from .indice import ivc_lineal

RASGOS = ["tasa", "tasa_10", "aceleracion", "de_residuo", "vecinos_2km", "anomalia_1km", "anomalia_2km", "anomalia_3km"]
NOMBRES_RASGOS = {"tasa": "Tasa de la ventana (persistencia)", "tasa_10": "Tasa de los últimos 10 años", "aceleracion": "Aceleración (m/año²)",
                  "de_residuo": "Variabilidad interanual (m)", "vecinos_2km": "Tasa media de los vecinos a 2 km", "anomalia_1km": "Anomalía a 1 km",
                  "anomalia_2km": "Anomalía a 2 km", "anomalia_3km": "Anomalía a 3 km"}


@dataclass
class ConfigProyeccion:
    ventana_anios: float = 21.0
    horizontes: tuple = (2050, 2100)
    modelo: str = "amortiguada"          # persistencia | amortiguada | ridge | rf
    n_mc: int = 1000
    n_bloques: int = 8
    buffer_km: float = 3.0
    semilla: int = 2026
    sigma_regional: float | None = None  # m/año; None = se estima de las ventanas (si hay ≥ 3) o 1,0
    alfas: tuple = (0.1, 0.3, 1, 3, 10, 30, 100)
    rf_arboles: int = 300


# ---------------------------------------------------------------------------
# Ventanas y rasgos
# ---------------------------------------------------------------------------
def media_vecinos(r: np.ndarray, km: np.ndarray, w: float) -> np.ndarray:
    r2 = np.atleast_2d(np.asarray(r, float))
    D = np.abs(km[:, None] - km[None, :])
    W = ((D <= w) & ~np.eye(len(km), dtype=bool)).astype(float)
    ok = np.isfinite(r2)
    s = np.where(ok, r2, 0) @ W.T
    n = ok.astype(float) @ W.T
    m = np.where(n > 0, s / np.where(n > 0, n, 1), np.nan)
    return m if np.ndim(r) > 1 else m[0]


def rasgos_ventana(inter: pd.DataFrame, ids: np.ndarray, km: np.ndarray, t0: float, t1: float) -> pd.DataFrame:
    """Rasgos de la historia de la ventana [t0, t1) por transecto (mismas definiciones que la tesis)."""
    d = inter[(inter["anio_dec"] >= t0) & (inter["anio_dec"] < t1)]
    cen = t0 + 10
    out = {k: {} for k in ("tasa", "tasa_10", "aceleracion", "de_residuo")}
    for id_t, g in d.groupby("id_t"):
        t, x = g["anio_dec"].to_numpy(float), g["distancia_m"].to_numpy(float)
        if len(t) >= 4 and np.ptp(t) >= min(8, 0.4 * (t1 - t0)):
            b1 = np.polyfit(t - cen, x, 1)
            out["tasa"][id_t] = b1[0]
            out["de_residuo"][id_t] = np.std(x - np.polyval(b1, t - cen), ddof=2) if len(t) > 2 else np.nan
        if len(t) >= 6:
            out["aceleracion"][id_t] = 2 * np.polyfit(t - cen, x, 2)[0]
        r = t >= t1 - 10
        if r.sum() >= 4:
            out["tasa_10"][id_t] = np.polyfit(t[r], x[r], 1)[0]
    H = pd.DataFrame({k: [v.get(i, np.nan) for i in ids] for k, v in out.items()})
    p = H["tasa"].to_numpy(float)
    H["vecinos_2km"] = media_vecinos(p, km, 2.0)
    for w in (1, 2, 3):
        H[f"anomalia_{w}km"] = p - media_vecinos(p, km, float(w))
    return H


def ventanas_historicas(inter: pd.DataFrame, L: float) -> list[tuple[float, float]]:
    """Ventanas consecutivas de L años que terminan en la última fecha (hacia atrás hasta la primera)."""
    a0, a1 = float(inter["anio_dec"].min()), float(inter["anio_dec"].max())
    fin = a1
    out = []
    while fin - L >= a0 - 1.0:      # tolerancia de 1 año en la primera ventana
        out.append((max(fin - L, a0), fin))
        fin -= L
    return list(reversed(out))


# ---------------------------------------------------------------------------
# Bloques y validación espacial
# ---------------------------------------------------------------------------
def bloques_igual_n(km: np.ndarray, n_bloques: int) -> np.ndarray:
    orden = np.argsort(km, kind="stable")
    b = np.empty(len(km), int)
    for k, idx in enumerate(np.array_split(orden, n_bloques), start=1):
        b[idx] = k
    return b


def mascara_entrenamiento(km, b, k, buffer_km):
    te = b == k
    tr = ~te
    if buffer_km > 0:
        tr &= ~((km >= km[te].min() - buffer_km) & (km <= km[te].max() + buffer_km))
    return tr


def _modelo(nombre: str, cfg: ConfigProyeccion, alfa: float | None = None):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import RandomForestRegressor

    if nombre == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=alfa if alfa is not None else 1.0))
    return RandomForestRegressor(n_estimators=cfg.rf_arboles, min_samples_leaf=5, max_features=0.5, random_state=cfg.semilla, n_jobs=-1)


def _alfa_ridge(X, y, km, b, tr, cfg: ConfigProyeccion) -> float:
    err = []
    for a in cfg.alfas:
        e, n = 0.0, 0
        for j in np.unique(b[tr]):
            itr = tr & mascara_entrenamiento(km, b, j, cfg.buffer_km)
            ite = tr & (b == j)
            if itr.sum() < 20 or ite.sum() == 0:
                continue
            p = _modelo("ridge", cfg, a).fit(X[itr], y[itr]).predict(X[ite])
            e += np.sum((y[ite] - p) ** 2); n += ite.sum()
        err.append(e / n if n else np.inf)
    return float(cfg.alfas[int(np.argmin(err))])


def ajustar_transicion(H1: pd.DataFrame, r1: np.ndarray, r2: np.ndarray, km: np.ndarray, cfg: ConfigProyeccion) -> dict:
    """Ajusta el modelo de transición Δ = r2 − r1 ~ f(rasgos de W1) y lo valida en bloques espaciales.

    Devuelve dict con: modelo, tipo, beta (amortiguada), alfa, oof (Δ predicho fuera de bloque), residuos_oof,
    metricas (global y por bloque), ok (máscara de transectos usados)."""
    y = np.asarray(r2, float) - np.asarray(r1, float)
    X = H1[RASGOS].to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(X[:, 0])
    med = np.nanmedian(X[ok], 0)
    X = np.where(np.isnan(X), med, X)
    b = bloques_igual_n(km, cfg.n_bloques)
    n = len(y)
    oof = np.full(n, np.nan)
    res = {"tipo": cfg.modelo, "bloques": b, "ok": ok, "mediana_rasgos": med}
    if cfg.modelo == "persistencia":
        oof[ok] = 0.0
    elif cfg.modelo == "amortiguada":
        a = X[:, RASGOS.index("anomalia_2km")]
        for k in np.unique(b):
            tr = ok & mascara_entrenamiento(km, b, k, cfg.buffer_km); te = ok & (b == k)
            if tr.sum() < 10 or not te.any():
                continue
            beta = np.linalg.lstsq(np.column_stack([np.ones(tr.sum()), a[tr]]), y[tr], rcond=None)[0]
            oof[te] = beta[0] + beta[1] * a[te]
        beta = np.linalg.lstsq(np.column_stack([np.ones(ok.sum()), a[ok]]), y[ok], rcond=None)[0]
        res["beta"] = [float(beta[0]), float(beta[1])]
    else:
        alfa = _alfa_ridge(X, y, km, b, ok, cfg) if cfg.modelo == "ridge" else None
        for k in np.unique(b):
            tr = ok & mascara_entrenamiento(km, b, k, cfg.buffer_km); te = ok & (b == k)
            if tr.sum() < 20 or not te.any():
                continue
            oof[te] = _modelo(cfg.modelo, cfg, alfa).fit(X[tr], y[tr]).predict(X[te])
        m = _modelo(cfg.modelo, cfg, alfa).fit(X[ok], y[ok])
        res["modelo"] = m; res["alfa"] = alfa
        if cfg.modelo == "ridge":
            res["coeficientes"] = dict(zip(RASGOS, map(float, m[-1].coef_)))
        else:
            res["importancia"] = dict(zip(RASGOS, map(float, m.feature_importances_)))
    e = ok & np.isfinite(oof)
    mse_m = np.mean((y[e] - oof[e]) ** 2); mse_p = np.mean(y[e] ** 2)
    filas = []
    for k in np.unique(b):
        kk = e & (b == k)
        if kk.sum() < 3:
            continue
        mm, pp = np.mean((y[kk] - oof[kk]) ** 2), np.mean(y[kk] ** 2)
        filas.append({"bloque": int(k), "n": int(kk.sum()), "RMSE_modelo": float(np.sqrt(mm)), "RMSE_persistencia": float(np.sqrt(pp)),
                      "R2_OS": float(1 - mm / pp) if pp > 0 else np.nan, "km_min": float(km[kk].min()), "km_max": float(km[kk].max())})
    # IC95 del R2_OS por bootstrap de bloques
    rng = np.random.default_rng(cfg.semilla)
    ub = np.unique(b[e]); idx = {k: np.flatnonzero(e & (b == k)) for k in ub}
    sk = []
    for _ in range(1000):
        s = np.concatenate([idx[k] for k in rng.choice(ub, len(ub), replace=True)])
        sk.append(1 - np.mean((y[s] - oof[s]) ** 2) / np.mean(y[s] ** 2))
    res["metricas"] = {"n": int(e.sum()), "RMSE_modelo": float(np.sqrt(mse_m)), "RMSE_persistencia": float(np.sqrt(mse_p)),
                       "MAE_modelo": float(np.mean(np.abs(y[e] - oof[e]))), "MAE_persistencia": float(np.mean(np.abs(y[e]))),
                       "R2_OS": float(1 - mse_m / mse_p) if mse_p > 0 else np.nan,
                       "R2_OS_IC95": [float(np.percentile(sk, 2.5)), float(np.percentile(sk, 97.5))],
                       "P_R2_OS_menor_0": float(np.mean(np.array(sk) <= 0)), "bloques_mejora": int(sum(f["R2_OS"] > 0 for f in filas)), "n_bloques": len(filas)}
    res["por_bloque"] = pd.DataFrame(filas)
    res["oof"] = oof; res["residuos_oof"] = np.where(e, y - oof, np.nan); res["y"] = y
    return res


# ---------------------------------------------------------------------------
# Recursión hacia el futuro
# ---------------------------------------------------------------------------
def proyectar(r_act: np.ndarray, H_act: pd.DataFrame, ajuste: dict, km: np.ndarray, anio_ref: float, cfg: ConfigProyeccion,
              sigma_regional: float | None = None) -> dict:
    """Tasas por ventana futura (central y Monte Carlo) y desplazamientos por horizonte.

    r_act: tasa de la última ventana observada; H_act: sus rasgos; ajuste: salida de ajustar_transicion."""
    L = cfg.ventana_anios
    n = len(r_act)
    hmax = max(cfg.horizontes)
    ventanas = []
    a = anio_ref
    while a < hmax:
        ventanas.append((a, a + L)); a += L
    rng = np.random.default_rng(cfg.semilla)
    res = ajuste["residuos_oof"]
    io = np.flatnonzero(np.isfinite(res))
    if io.size:
        res_full = res[io[np.abs(km[:, None] - km[io][None, :]).argmin(1)]]
    else:
        res_full = np.zeros(n)
    sig = cfg.sigma_regional if cfg.sigma_regional is not None else (sigma_regional if sigma_regional is not None else 1.0)
    X2 = H_act[RASGOS].to_numpy(float)
    X2 = np.where(np.isnan(X2), ajuste["mediana_rasgos"], X2)
    de_res = X2[:, RASGOS.index("de_residuo")]
    despl = rng.integers(len(res_full), size=cfg.n_mc)

    def delta(r, primero):
        m_ = r.shape[0]
        tipo = ajuste["tipo"]
        if tipo == "persistencia":
            return np.zeros_like(r)
        if tipo == "amortiguada":
            b0, b1 = ajuste["beta"]
            return b0 + b1 * (r - media_vecinos(r, km, 2.0))
        if primero:
            X = np.repeat(X2[None], m_, 0)
        else:
            X = np.empty((m_, n, len(RASGOS)))
            X[..., 0] = r; X[..., 1] = r; X[..., 2] = 0.0; X[..., 3] = de_res
            X[..., 4] = media_vecinos(r, km, 2.0)
            for w in (1, 2, 3):
                X[..., 4 + w] = r - media_vecinos(r, km, float(w))
        X = np.where(np.isnan(X), ajuste["mediana_rasgos"], X)
        return ajuste["modelo"].predict(X.reshape(-1, X.shape[-1])).reshape(m_, n)

    def paso(r, primero, mc):
        d = delta(r, primero)
        d = d - np.nanmean(d, axis=1, keepdims=True)              # tendencia centrada
        if mc:
            e = np.stack([np.roll(res_full, k) for k in despl]) - np.nanmean(res_full)
            e = e + rng.normal(0.0, sig, (r.shape[0], 1))
            d = d + e
        return r + d

    r0 = np.asarray(r_act, float)
    r0 = np.where(np.isfinite(r0), r0, np.nan)
    tasas_c = [r0[None]]; tasas_mc = [np.repeat(r0[None], cfg.n_mc, 0)]
    for i in range(len(ventanas)):
        tasas_c.append(paso(tasas_c[-1], i == 0, False))
        tasas_mc.append(paso(tasas_mc[-1], i == 0, True))

    def desplazamiento(R, T):
        tot = 0.0
        for i, (a, z) in enumerate(ventanas, start=1):
            tot = tot + R[i] * max(0, min(T, z) - a)
        return tot

    def tasa_L(R, T):
        """Tasa media de los L años anteriores a T: tramo observado [T−L, año_ref] con la tasa actual + ventanas proyectadas."""
        tot = R[0] * max(0.0, anio_ref - (T - L))
        for i, (a, z) in enumerate(ventanas, start=1):
            tot = tot + R[i] * max(0, min(T, z) - max(a, T - L))
        return tot / L

    out = pd.DataFrame({"tasa_actual": r0})
    for i, (a, z) in enumerate(ventanas, start=1):
        out[f"tasa_{int(a)}_{int(z)}"] = tasas_c[i][0]
        out[f"tasa_{int(a)}_{int(z)}_p05"] = np.nanpercentile(tasas_mc[i], 5, 0)
        out[f"tasa_{int(a)}_{int(z)}_p95"] = np.nanpercentile(tasas_mc[i], 95, 0)
    for T in cfg.horizontes:
        dm = desplazamiento(tasas_mc, T)
        out[f"desplaz_m_{T}"] = desplazamiento(tasas_c, T)[0]
        out[f"desplaz_m_{T}_p05"] = np.nanpercentile(dm, 5, 0)
        out[f"desplaz_m_{T}_p95"] = np.nanpercentile(dm, 95, 0)
        out[f"desplaz_m_{T}_persistencia"] = r0 * (T - anio_ref)
        out[f"tasaL_{T}"] = tasa_L(tasas_c, T)[0]
        out[f"tasaL_{T}_p05"] = np.nanpercentile(tasa_L(tasas_mc, T), 5, 0)
        out[f"tasaL_{T}_p95"] = np.nanpercentile(tasa_L(tasas_mc, T), 95, 0)
    return {"tabla": out, "ventanas": ventanas, "tasas_mc": tasas_mc, "sigma_regional": sig, "desplazamiento_mc": {T: desplazamiento(tasas_mc, T) for T in cfg.horizontes},
            "tasaL_mc": {T: tasa_L(tasas_mc, T) for T in cfg.horizontes}}


def lineas_proyectadas(t: gpd.GeoDataFrame, tabla: pd.DataFrame, horizontes, anio_ref: int) -> gpd.GeoDataFrame:
    """Líneas (observada, central, p05, p95, persistencia) por horizonte, uniendo los puntos desplazados de cada transecto."""
    filas, geoms = [], []
    ux, uy = t["ux"].to_numpy(float), t["uy"].to_numpy(float)
    x0, y0 = t["x_p0"].to_numpy(float), t["y_p0"].to_numpy(float)

    def linea(desp, nombre, T):
        d = np.asarray(desp, float)
        ok = np.isfinite(d)
        if ok.sum() < 2:
            return
        xs, ys = x0[ok] - ux[ok] * d[ok], y0[ok] - uy[ok] * d[ok]   # + = hacia el mar (sentido −u)
        filas.append({"tipo": nombre, "anio": T, "linea": f"{nombre} {T}"}); geoms.append(LineString(np.c_[xs, ys]))

    linea(np.zeros(len(t)), "observada", anio_ref)
    for T in horizontes:
        linea(tabla[f"desplaz_m_{T}"], "central", T)
        linea(tabla[f"desplaz_m_{T}_p05"], "p05", T)
        linea(tabla[f"desplaz_m_{T}_p95"], "p95", T)
        linea(tabla[f"desplaz_m_{T}_persistencia"], "persistencia", T)
    return gpd.GeoDataFrame(filas, geometry=geoms, crs=t.crs)


# ---------------------------------------------------------------------------
# Regla de Bruun
# ---------------------------------------------------------------------------
def velocidad_caida(d50_m):
    """Ferguson y Church (2004): w = R g D² / (C1 ν + √(0,75 C2 R g D³)), R = 1,65, ν = 1e‑6, C1 = 18, C2 = 1."""
    D = np.asarray(d50_m, float); R, g, nu = 1.65, 9.81, 1.0e-6
    return R * g * D ** 2 / (18 * nu + np.sqrt(0.75 * 1.0 * R * g * D ** 3))


def bruun_mc(slr_total_m: np.ndarray, anios: float, H12_m: np.ndarray, d50_mm: np.ndarray, B_m: np.ndarray, n_mc: int = 2000, semilla: int = 2026,
             T12_rango=(8.0, 11.0), E_tri=(0.1, 0.75, 1.0), rh_rango_mm=(3.40, 6.15), H12_max_m: np.ndarray | None = None) -> pd.DataFrame:
    """Retroceso por SLR (m) central, p05 y p95 por transecto.

    slr_total_m: ascenso del escenario en el horizonte respecto del año de referencia; anios: años desde la referencia;
    rh: ritmo histórico (mm/año) ya contenido en la tendencia, que se descuenta."""
    g = 9.81
    rng = np.random.default_rng(semilla)
    n = len(slr_total_m)
    D = np.asarray(d50_mm, float) / 1000.0
    A = 0.067 * (velocidad_caida(D) * 100) ** 0.44
    B = np.clip(np.asarray(B_m, float), 0, None)
    H12c = np.asarray(H12_m, float); H12m = np.asarray(H12_max_m, float) if H12_max_m is not None else H12c
    E = rng.triangular(*E_tri, n_mc)[:, None]; T12 = rng.uniform(*T12_rango, n_mc)[:, None]
    u = rng.uniform(0, 1, n_mc)[:, None]; H12 = H12c[None] + u * (H12m - H12c)[None]
    rh = rng.uniform(rh_rango_mm[0], rh_rango_mm[1], n_mc)[:, None] / 1000.0

    def R(H12, T12, E, rh):
        hc = 2.28 * H12 - 68.5 * H12 ** 2 / (g * T12 ** 2)
        L = (hc / A) ** 1.5
        dS = np.maximum(np.asarray(slr_total_m, float) - rh * anios, 0)
        return E * dS * L / (hc + B)

    mc = R(H12, T12, E, rh)
    cen = R(0.5 * (H12c + H12m)[None], np.array([[np.mean(T12_rango)]]), np.array([[E_tri[1]]]), np.array([[np.mean(rh_rango_mm) / 1000]]))[0]
    return pd.DataFrame({"bruun_m": cen, "bruun_m_p05": np.percentile(mc, 5, 0), "bruun_m_p95": np.percentile(mc, 95, 0)})


# ---------------------------------------------------------------------------
# IVC futuro
# ---------------------------------------------------------------------------
def ivc_futuro(X_act: np.ndarray, w: np.ndarray, nombres: list[str], roles: dict, clasif: dict, valores_act: dict,
               tasa_L: np.ndarray, retroceso_m: np.ndarray, pct_bajo_nivel: np.ndarray | None = None, escala: str = "1-5") -> tuple[np.ndarray, np.ndarray]:
    """Reclasifica las variables dinámicas y devuelve (IVC, matriz de clases).

    roles: {'tasa': var, 'distancia_infra': var, 'ancho_barra': var, 'nivel_mar': var} (las que existan);
    clasif: {var: (cortes, clases, cerrado)}; valores_act: {var: valores actuales (unidades)}; retroceso_m ≥ 0."""
    Xt = X_act.copy()
    ret = np.maximum(np.asarray(retroceso_m, float), 0)

    def pon(var, valores):
        if var in nombres and var in clasif:
            c, k, cerr = clasif[var]
            Xt[:, nombres.index(var)] = por_umbrales(valores, c, k, cerr)

    if roles.get("tasa"):
        pon(roles["tasa"], tasa_L)
    if roles.get("distancia_infra") and roles["distancia_infra"] in valores_act:
        pon(roles["distancia_infra"], np.maximum(np.asarray(valores_act[roles["distancia_infra"]], float) - ret, 0))
    if roles.get("ancho_barra") and roles["ancho_barra"] in valores_act:
        pon(roles["ancho_barra"], np.maximum(np.asarray(valores_act[roles["ancho_barra"]], float) - ret, 0))
    if roles.get("nivel_mar") and pct_bajo_nivel is not None:
        pon(roles["nivel_mar"], pct_bajo_nivel)
    v = ivc_lineal(Xt, w, escala)
    return v, Xt
