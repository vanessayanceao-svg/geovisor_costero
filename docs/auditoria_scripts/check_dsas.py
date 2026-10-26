"""Comprobación 1-2: tasas DSAS e intersecciones. Implementación independiente (no usa src.calculo.tasas)."""
import sys, pickle
sys.path.insert(0, ".")
import numpy as np, pandas as pd, geopandas as gpd
from scipy import stats

D = "D:/COASTSAS/CoastSat-master/exportar_coastsat/dsas/"
e2e = pickle.load(open("docs/auditoria_scripts/_trabajo/e2e.pkl", "rb"))
t = e2e["r1"]["transectos"]; inter = e2e["r1"]["inter"]
ref = gpd.read_file(D + "dsas_tasas.shp")
iref = gpd.read_file(D + "dsas_intersecciones.shp")

# ---- A. intersecciones del geovisor vs DSAS (distancia por transecto y fecha)
iref["fecha"] = pd.to_datetime(iref["ShorelineI"], format="%m/%d/%Y")
m = t[["id_t", "BaselineID", "TransOrder"]]
ii = inter.merge(m, on="id_t").merge(iref[["BaselineID", "TransOrder", "fecha", "Distance", "DecimalYea", "Uncertaint", "IntersectX", "IntersectY"]],
                                     on=["BaselineID", "TransOrder", "fecha"], how="outer", indicator=True)
print("A. intersecciones: geovisor", len(inter), "DSAS", len(iref), "emparejadas", (ii["_merge"] == "both").sum(),
      "solo geovisor", (ii["_merge"] == "left_only").sum(), "solo DSAS", (ii["_merge"] == "right_only").sum())
b = ii[ii["_merge"] == "both"]
print("   max|dist - Distance| =", (b["distancia_m"] - b["Distance"]).abs().max(),
      " max|anio_dec - DecimalYea| =", (b["anio_dec"] - b["DecimalYea"]).abs().max(),
      " max|unc - Uncertaint| =", (b["unc_m"] - b["Uncertaint"]).abs().max(),
      " max|xy| =", np.hypot(b["x"] - b["IntersectX"], b["y"] - b["IntersectY"]).max())
# año decimal en años bisiestos
bis = b[pd.to_datetime(b["fecha"]).dt.is_leap_year]
print("   bisiestos: max|anio_dec - DecimalYea| =", (bis["anio_dec"] - bis["DecimalYea"]).abs().max(), "n=", len(bis))

# ---- B. tasas: implementación independiente
def indep(g):
    g = g.sort_values("anio_dec")
    x = g["anio_dec"].to_numpy(float); y = g["distancia_m"].to_numpy(float); u = g["unc_m"].to_numpy(float)
    n = len(x); out = {"NSM": y[-1] - y[0], "SCE": y.max() - y.min()}
    yrs = x[-1] - x[0]
    out["EPR"] = out["NSM"] / yrs; out["EPRUNC"] = np.sqrt(u[0] ** 2 + u[-1] ** 2) / yrs
    # OLS
    res = stats.linregress(x, y)
    out["LRR"] = res.slope; out["LR2"] = res.rvalue ** 2
    yhat = res.intercept + res.slope * x
    out["LSE"] = np.sqrt(((y - yhat) ** 2).sum() / (n - 2)); out["LCI95"] = stats.t.ppf(0.975, n - 2) * res.stderr
    # WLS (pesos 1/u^2), fórmulas estándar
    w = 1 / u ** 2
    Xm = np.column_stack([np.ones(n), x]); Wm = np.diag(w)
    beta = np.linalg.solve(Xm.T @ Wm @ Xm, Xm.T @ Wm @ y)
    r = y - Xm @ beta
    s2 = (w * r ** 2).sum() / (n - 2)
    cov = s2 * np.linalg.inv(Xm.T @ Wm @ Xm)
    ybar_w = (w * y).sum() / w.sum()
    out["WLR"] = beta[1]; out["WR2"] = 1 - (w * r ** 2).sum() / (w * (y - ybar_w) ** 2).sum()
    out["WSE"] = np.sqrt(s2); out["WCI"] = stats.t.ppf(0.975, n - 2) * np.sqrt(cov[1, 1])
    return pd.Series(out)

T2 = inter.groupby("id_t").apply(indep).reset_index()
c = t.merge(T2, on="id_t", suffixes=("", "_ind")).merge(ref.drop(columns="geometry"), on=["BaselineID", "TransOrder"], suffixes=("", "_dsas"))
print("B. n transectos comparados:", len(c))
print(f"{'campo':8s} {'max|geo-DSAS|':>15s} {'max|indep-DSAS|':>16s} {'max|geo-indep|':>15s}")
for k in ["NSM", "SCE", "EPR", "EPRUNC", "LRR", "LR2", "LSE", "LCI95", "WLR", "WR2", "WSE", "WCI"]:
    print(f"{k:8s} {(c[k] - c[k + '_dsas']).abs().max():15.6f} {(c[k + '_ind'] - c[k + '_dsas']).abs().max():16.6f} {(c[k] - c[k + '_ind']).abs().max():15.3e}")
print("   ShrCount vs n_lineas: max diff", (c["ShrCount"] - c["n_lineas"]).abs().max())
# redondeo DSAS: columnas con 6 decimales?
print("   decimales DSAS LRR ejemplo:", ref["LRR"].head(3).tolist())

# ---- C. convención de signo: Distance DSAS crece hacia el mar? NSM<0 = erosión
print("C. NSM<0 (%):", 100 * (c["NSM"] < 0).mean(), " (informe DSAS: 85.69 %)")
# ¿la distancia aumenta en la dirección mar (= −u)?
r0 = t.iloc[0]; g0 = inter[inter.id_t == r0.id_t].sort_values("anio_dec").iloc[[0, -1]]
print("   transecto 1: dist ini/fin", g0["distancia_m"].tolist(), " coordenadas:", g0[["x", "y"]].values.tolist(), " base:", (r0.x_base, r0.y_base), " u(tierra):", (r0.ux, r0.uy))

# ---- D. umbral de líneas: ¿hay transectos con n<10 en DSAS que tengan LRR?
print("D. n_lineas min:", c["n_lineas"].min(), " transectos con n<10:", (c["n_lineas"] < 10).sum())
print("   transectos de la tesis con LRR nulo en DSAS:", ref["LRR"].isna().sum())

# ---- E. criterio 'cercana' vs 'lejana': ¿cuántas intersecciones múltiples hay?
from src.calculo import transectos as TR
L = e2e["L"]
far = TR.intersecciones(t, L, "_fecha", "UNCY", 10.0, "lejana")
mm = inter.merge(far, on=["id_t", "fecha"], suffixes=("", "_far"))
print("E. pares (transecto, fecha) con cortes múltiples:", ((mm["distancia_m_far"] - mm["distancia_m"]).abs() > 1e-6).sum(), "de", len(mm),
      " max separación (m):", (mm["distancia_m_far"] - mm["distancia_m"]).abs().max())
