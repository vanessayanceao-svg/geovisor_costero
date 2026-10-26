"""Comprobaciones unitarias 4-8: normalización, EWM, FAHP, índice, validación."""
import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score
from src.calculo import normalizacion as NO, ponderacion as PO, indice as IN, proyecto as PJ

print("=== 4. Normalización ===")
c = [1, 2, 3, 4]; k = [5, 4, 3, 2, 1]
x = [0.5, 1.0, 1.5, 2.0, 4.0, 4.5, np.nan]
print("por_umbrales cerrado=derecha  x=", x, "->", NO.por_umbrales(x, c, k, "derecha"), " (esperado 5,5,4,4,2,1,nan: (−∞,1],(1,2],…)")
print("por_umbrales cerrado=izquierda x=", x, "->", NO.por_umbrales(x, c, k, "izquierda"), " (esperado 5,4,4,3,1,1,nan: [1,2),[2,3),…)")
print("clase_de_indice_01 [0,0.2,0.4,0.6,0.8,1.0,-0.1,1.2,nan] ->", NO.clase_de_indice_01([0, .2, .4, .6, .8, 1.0, -0.1, 1.2, np.nan]))
print("quintiles 10 valores ->", NO.quintiles(np.arange(10)), " inverso ->", NO.quintiles(np.arange(10), False))
print("quintiles con NaN y 4 válidos ->", NO.quintiles([1, 2, 3, 4, np.nan]))
print("difusa constante ->", NO.difusa_01([2, 2, 2]), " difusa inversa ->", NO.difusa_01([0, 5, 10], False))
print("categorias_a_clase ->", NO.categorias_a_clase(pd.Series(["Playas", " playas ", "Laguna costera", "XXX", None]), {"playas": 5, "laguna costera": 4}))
# directa: valores fuera de 1-5
try:
    PJ.normalizar_variable({"codigo": "z", "normalizacion": "directa"}, pd.Series([1, 5.5]), None, np.array([0, 1]))
except ValueError as e:
    print("directa fuera de rango -> ValueError OK:", e)

print("\n=== 5. EWM ===")
X = np.array([[1, 5, 3], [2, 5, 3], [3, 5, 3], [4, 5, 3], [5, 5, 3]], float)
print("EWM con 2 columnas constantes (no nulas):", PO.pesos_ewm(X), " (esperado [1,0,0])")
X0 = np.array([[1, 0.0], [2, 0.0], [3, 0.0], [4, 0.0]])
print("EWM con columna toda 0 (escala 0-1):", PO.pesos_ewm(X0), " <-- columna constante 0 recibe peso")
Xc = np.array([[3, 3], [3, 3], [3, 3]], float)
print("EWM con todas constantes:", PO.pesos_ewm(Xc), " <-- 0/0")
# verificación independiente de la fórmula con los datos reales
e2e = pickle.load(open("docs/auditoria_scripts/_trabajo/e2e.pkl", "rb"))
r3, r4, r5, p = e2e["r3"], e2e["r4"], e2e["r5"], e2e["p"]
cols = r4["variables"]; Xr = r3["clases"][cols].to_numpy(float); ok = np.isfinite(Xr).all(1)
print("filas con NaN en clases:", (~ok).sum(), "de", len(Xr), " columnas con NaN:", {c_: int(np.isnan(r3['clases'][c_]).sum()) for c_ in cols if np.isnan(r3['clases'][c_]).any()})
P = Xr[ok] / Xr[ok].sum(0); E = -(P * np.log(P)).sum(0) / np.log(ok.sum()); W = (1 - E) / (1 - E).sum()
print("EWM independiente vs geovisor max diff:", np.abs(W - r4["ewm"]["peso"].to_numpy()).max())
pes = pd.read_csv("/mnt/user-data/uploads/Resultados tesis/Mapas_IVC/pesos_ewm_ivc.csv").set_index("variable")
print("EWM vs tesis (peso_total) max diff:", np.abs(r4["ewm"]["peso"].to_numpy() - pes.loc[cols, "peso_total"].to_numpy()).max())
print("IC95 EWM:", r4["ewm"][["variable", "peso", "IC95_inf", "IC95_sup"]].to_string(index=False))
# ¿el peso puntual está dentro del IC?
print("pesos fuera de su IC95:", int(((r4["ewm"]["peso"] < r4["ewm"]["IC95_inf"]) | (r4["ewm"]["peso"] > r4["ewm"]["IC95_sup"])).sum()))

print("\n=== 6. FAHP ===")
A = np.array([[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]])
F = PO.fuzzificar(A, 1.0)
print("fuzzificar a=3 ->", F[0, 1], " recíproco 1/3 ->", F[1, 0], " (esperado (1/4,1/3,1/2))", " a=5 ->", F[0, 2], " 1/5 ->", F[2, 0], " a=9:", PO.fuzzificar(np.array([[1, 9], [1 / 9, 1]]))[0, 1])
# Buckley independiente
r = np.exp(np.log(F).sum(1) / 3); S = r.sum(0)
wl, wm, wu = r[:, 0] / S[2], r[:, 1] / S[1], r[:, 2] / S[0]
cen = (wl + wm + wu) / 3; wB = cen / cen.sum()
tab, cons = PO.pesos_fahp(A, "buckley")
print("Buckley indep vs geovisor max diff:", np.abs(wB - tab["peso"].to_numpy()).max(), " pesos:", tab["peso"].round(4).tolist())
print("consistencia:", {k_: (round(v, 4) if isinstance(v, float) else v) for k_, v in cons.items() if k_ != "pesos_eigen"})
# λmax de la matriz [1,3,5;1/3,1,3;1/5,1/3,1] = 3.0385 (CI 0.0193, CR 0.033)
# Chang independiente
Ssum = F.sum(1); tot = Ssum.sum(0); Si = np.c_[Ssum[:, 0] / tot[2], Ssum[:, 1] / tot[1], Ssum[:, 2] / tot[0]]
def V(a, b):
    la, ma, ua = a; lb, mb, ub = b
    if ma >= mb: return 1.0
    if lb >= ua: return 0.0
    return (lb - ua) / ((ma - ua) - (mb - lb))
d = np.array([min(V(Si[i], Si[j]) for j in range(3) if j != i) for i in range(3)]); wC = d / d.sum()
tabc, _ = PO.pesos_fahp(A, "chang")
print("Chang indep vs geovisor max diff:", np.abs(wC - tabc["peso"].to_numpy()).max(), " pesos:", tabc["peso"].round(4).tolist())
# Chang degenerado: todos los grados mínimos 0 salvo uno
A2 = np.array([[1, 9, 9], [1 / 9, 1, 1], [1 / 9, 1, 1]])
print("Chang extremo:", PO.pesos_fahp(A2, "chang")[0]["peso"].round(4).tolist(), " (Chang asigna 0 a los dominados)")
# validación de matriz: valores negativos pasan?
try:
    PO.matriz_saaty_valida(np.array([[1, -2], [-0.5, 1]])); print("matriz con negativos ACEPTADA <-- fallo de validación")
except ValueError as e:
    print("matriz negativa rechazada:", e)
try:
    PO.matriz_saaty_valida(np.array([[1, 12], [1 / 12, 1]])); print("matriz con a=12 (>9) ACEPTADA <-- sin control de rango Saaty")
except ValueError as e:
    print("a=12 rechazada:", e)
# fuzzificación de un juicio no entero (p. ej. 1.5) y delta 0
print("fuzzificar a=1.5, δ=1 ->", PO.fuzzificar(np.array([[1, 1.5], [1 / 1.5, 1]]))[0, 1], PO.fuzzificar(np.array([[1, 1.5], [1 / 1.5, 1]]))[1, 0])
print("Buckley δ=0 == eigen/geométrica nítida?", np.abs(PO.pesos_fahp(A, 'buckley', 0.0)[0]['peso'].to_numpy() - (lambda g: g / g.sum())(np.exp(np.log(A).mean(1)))).max())
# RI Saaty
print("RI:", PO.RI)

print("\n=== 7. Índice ===")
w = r4["pesos"]["ewm"]
v = IN.ivc_lineal(Xr, w, "1-5")
print("ivc_lineal indep max diff:", np.nanmax(np.abs(v - ((Xr @ w) - 1) / 4)))
print("rango IVC:", np.nanmin(v), np.nanmax(v))
# TOPSIS independiente (sin NaN)
nrm = np.sqrt((Xr ** 2).sum(0)); Vm = w * Xr / nrm; Ap = w * 5 / nrm; Am = w * 1 / nrm
C = np.sqrt(((Vm - Am) ** 2).sum(1)) / (np.sqrt(((Vm - Ap) ** 2).sum(1)) + np.sqrt(((Vm - Am) ** 2).sum(1)))
tp, _ = IN.topsis(Xr, w, True, "1-5")
print("TOPSIS indep max diff:", np.nanmax(np.abs(C - tp)))
# TOPSIS con un NaN en la matriz
Xn = Xr.copy(); Xn[0, 0] = np.nan
tpn, nrmn = IN.topsis(Xn, w, True, "1-5")
print("TOPSIS con 1 NaN en la col 0: nrm col0 =", nrmn[0], " (sin NaN:", nrm[0], ") -> max|cambio| en filas válidas:", np.nanmax(np.abs(tpn[1:] - tp[1:])), " <-- un NaN altera todas las filas")
# Gornitz
g = IN.cvi_gornitz(Xr, False)
print("Gornitz indep max diff:", np.nanmax(np.abs(g - np.sqrt(np.prod(Xr, 1) / Xr.shape[1]))))
print("Gornitz con clase 0 (escala 0-1):", IN.cvi_gornitz(np.array([[0.0, 1.0]]), False))
# clases del IVC vs tesis
import geopandas as gpd
tt = gpd.read_file("/mnt/user-data/uploads/Resultados tesis/QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", layer=None) if False else None
from src import ivc as mod
from src.configuracion import cargar_config
cfg = cargar_config()
T = mod.cargar_transectos_ivc(cfg).set_index("id_ivc")
R = r5["tabla"].set_index("id_ivc")
print("columnas tesis:", [c_ for c_ in T.columns if "clase" in c_.lower() or "ivc" in c_.lower()][:40])
for a, b in [("clase_ewm", "clase_ewm_total"), ("ivc_topsis_ewm", "ivc_topsis_ewm")]:
    if b in T.columns:
        d_ = R[a].to_numpy(float) - T.loc[R.index, b].to_numpy(float)
        print(f"{a} vs tesis {b}: max |diff| =", np.nanmax(np.abs(d_)), " n distintos:", int((np.abs(d_) > 1e-9).sum()))
# cortes 1-5 de config vs 0-1
print("cortes 0-1 -> 1-5:", [1 + 4 * c_ for c_ in [0.2, 0.4, 0.6, 0.8]], " config cortes_1_5: [1.8,2.6,3.4,4.2]")

print("\n=== 8. Validación ===")
t = e2e["r1"]["transectos"].set_index("id_ivc")
tasa = t.loc[R.index, "LRR"].to_numpy(float)
rho, pv = spearmanr(R["ivc_ewm"], -tasa)
print("rho indep (ivc_ewm, −LRR):", rho, " geovisor:", r5["validacion"].set_index("indice").loc["ivc_ewm", "rho"], " tesis Multicriterio: ver validacion_indices_dsas.csv")
vt = pd.read_csv("/mnt/user-data/uploads/Resultados tesis/Multicriterio/validacion_indices_dsas.csv"); print(vt.head(12).to_string())
# kappa cuadrático vs sklearn
a_, b_ = R["clase_ewm"].to_numpy(), R["clase_iguales"].to_numpy()
okk = np.isfinite(a_) & np.isfinite(b_)
print("kappa cuadrático geovisor:", IN.kappa_ponderado(a_, b_), " sklearn:", cohen_kappa_score(a_[okk].astype(int), b_[okk].astype(int), weights="quadratic", labels=[1, 2, 3, 4, 5]))
# VIF vs statsmodels-style
Xo = r3["clases"][cols].dropna().to_numpy(float)
def vif_ref(X, j):
    y = X[:, j]; Z = np.column_stack([np.ones(len(X)), np.delete(X, j, 1)])
    b = np.linalg.lstsq(Z, y, rcond=None)[0]; r2 = 1 - ((y - Z @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum(); return 1 / (1 - r2)
print("VIF max diff vs ref:", np.abs(IN.vif(Xo) - np.array([vif_ref(Xo, j) for j in range(Xo.shape[1])])).max(), " VIF:", dict(zip(cols, IN.vif(Xo).round(2))))
print("VIF columna constante:", IN.vif(np.c_[np.ones(10), np.arange(10)]), " <-- 1.0 para constante (indefinido)")
# bloques contiguos
km = R["dist_costa_km"].to_numpy(float); blo = IN.bloques_contiguos(km, 8)
print("bloques: n por bloque", np.bincount(blo), " km máx por bloque", [round(km[blo == k].max(), 2) for k in range(8)])
# sensibilidad: cortes por defecto aunque el proyecto use otros
p2 = dict(p);
s1 = IN.sensibilidad_pesos(Xr[ok], w, cols, "1-5")
print("sensibilidad usa cortes por defecto (sin parámetro 'cortes'):", "cortes" in IN.sensibilidad_pesos.__code__.co_varnames)
print("estabilidad: parámetro cortes?", "cortes" in IN.estabilidad_clase_bootstrap.__code__.co_varnames)
# estabilidad con NaN
Xn2 = Xr.copy(); Xn2[3, 2] = np.nan
est = IN.estabilidad_clase_bootstrap(Xn2, blo, 20)
print("estabilidad fila con NaN:", est[3], " (debería ser NaN)")
# tasa_validacion 'ventana' documentada en proyecto.py no implementada
print("'ventana' en paso_indice:", "ventana" in open("./src/calculo/proyecto.py").read().split("def paso_indice")[1].split("def paso_proyeccion")[0])
