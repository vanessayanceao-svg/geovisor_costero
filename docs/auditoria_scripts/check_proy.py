"""Comprobación 9: proyección (ventanas, VC en bloques con buffer, R2_OS, MC, Bruun, IVC futuro) y comparación con la tesis."""
import sys, pickle, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from src.calculo import proyeccion as PR, normalizacion as NO, indice as IN
e2e = pickle.load(open("docs/auditoria_scripts/_trabajo/e2e.pkl", "rb"))
r1, r3, r4, r6, p = e2e["r1"], e2e["r3"], e2e["r4"], e2e["r6"], e2e["p"]
inter = r1["inter"]; t = r1["transectos"]; km = t["dist_costa_km"].to_numpy(float)
TES = "/mnt/user-data/uploads/Resultados tesis/Modelos/07_Proyecciones/resultados_amortiguada/"

print("=== ventanas ===")
print("históricas:", r6["ventanas"], " anio_ref:", r6["anio_ref"])
tab = r6["tabla"]; print([c for c in tab.columns if c.startswith("tasa_")][:12])
# cobertura de ventanas: ¿todas las intersecciones caen en alguna ventana?
v = r6["ventanas"]; a = inter["anio_dec"]
cub = np.zeros(len(a), bool)
for i, (x, y) in enumerate(v):
    cub |= (a >= x) & (a < y + (1e-6 if i == len(v) - 1 else 0))
print("intersecciones fuera de toda ventana:", (~cub).sum(), " solapes entre ventanas: ventanas disjuntas por construcción")
# comparación de tasa_ventana (cerrada) vs rasgos_ventana (semiabierta)
from src.calculo import tasas as TA
tv = TA.tasa_ventana(inter, v[0][0], v[0][1]); H0 = r6["rasgos"][0]["tasa"].to_numpy()
tv2 = tv.reindex(t["id_t"]).to_numpy()
print("tasa_ventana [a0,a1] vs rasgos_ventana [t0,t1): max diff", np.nanmax(np.abs(tv2 - H0)), " n distintos >1e-9:", int(np.nansum(np.abs(tv2 - H0) > 1e-9)))

print("\n=== bloques y buffer ===")
aj = r6["ajuste"]; b = aj["bloques"]; cfg = r6["config"]
print("bloques igual n:", np.bincount(b)[1:], " buffer_km:", cfg.buffer_km)
fugas = 0
for k in np.unique(b):
    tr = PR.mascara_entrenamiento(km, b, k, cfg.buffer_km); te = b == k
    dmin = np.abs(km[tr][:, None] - km[te][None, :]).min()
    fugas += dmin < cfg.buffer_km - 1e-9
    if k == 1: print(f"  bloque {k}: n_test {te.sum()}, n_train {tr.sum()}, distancia mínima train-test {dmin:.3f} km")
print("bloques con fuga (train a < buffer del test):", fugas)
# R2_OS indep
y, oof, ok = aj["y"], aj["oof"], aj["ok"]; e = ok & np.isfinite(oof)
print("R2_OS indep:", 1 - np.sum((y[e] - oof[e]) ** 2) / np.sum(y[e] ** 2), " geovisor:", aj["metricas"]["R2_OS"], " n:", e.sum(), " beta:", aj["beta"])
# ¿OOF de la amortiguada realmente excluye al bloque? recalcula para bloque 3
k = 3; tr = ok & PR.mascara_entrenamiento(km, b, k, cfg.buffer_km); te = ok & (b == k)
an = np.where(np.isnan(r6["rasgos"][0]["anomalia_2km"].to_numpy()), np.nanmedian(r6["rasgos"][0]["anomalia_2km"].to_numpy()[ok]), r6["rasgos"][0]["anomalia_2km"].to_numpy())
beta = np.linalg.lstsq(np.column_stack([np.ones(tr.sum()), an[tr]]), y[tr], rcond=None)[0]
print("OOF bloque 3 recalculado max diff:", np.abs(beta[0] + beta[1] * an[te] - oof[te]).max())
print("tesis: R2_OS amortiguada reportado +10,0 % (IC95 +1,0 a +24,3 %, 7/8 bloques); geovisor:", round(aj["metricas"]["R2_OS"] * 100, 1), [round(x * 100, 1) for x in aj["metricas"]["R2_OS_IC95"]], aj["metricas"]["bloques_mejora"])

print("\n=== recursión y MC ===")
# desplazamiento = Σ tasa × duración (central)
L = cfg.ventana_anios; ar = r6["anio_ref"]
vent = []; x = ar
while x < 2100: vent.append((x, x + L)); x += L
d2100 = sum(tab[f"tasa_{int(a_)}_{int(z_)}"].to_numpy() * (min(2100, z_) - a_) for a_, z_ in vent)
print("desplaz_m_2100 = Σ tasa·dur ? max diff:", np.nanmax(np.abs(d2100 - tab["desplaz_m_2100"])))
d2050 = sum(tab[f"tasa_{int(a_)}_{int(z_)}"].to_numpy() * max(0, min(2050, z_) - a_) for a_, z_ in vent)
print("desplaz_m_2050 max diff:", np.nanmax(np.abs(d2050 - tab["desplaz_m_2050"])))
# tasaL_2100 = tasa media en [2079, 2100]
tl = sum(tab[f"tasa_{int(a_)}_{int(z_)}"].to_numpy() * max(0, min(2100, z_) - max(a_, 2100 - L)) for a_, z_ in vent) / L
print("tasaL_2100 max diff:", np.nanmax(np.abs(tl - tab["tasaL_2100"])))
# tendencia centrada: la media regional de la tasa central no cambia
print("media tasa actual / W3 / W6 (central):", [round(float(np.nanmean(tab[c])), 4) for c in ["tasa_actual"] + [c for c in tab.columns if c.startswith("tasa_2") and not c.endswith(("p05", "p95"))]])
# bandas MC
print("sigma_regional usado:", r6["sigma_regional"], " (tesis: std([0.320,1.882,-0.717], ddof=1) =", round(float(np.std([0.320, 1.882, -0.717], ddof=1)), 3), ")")
ref = pd.read_csv(TES + "proyeccion_transectos.csv").set_index("id_ivc")
d = tab.set_index("id_ivc")
for c in ["desplaz_m_2050", "desplaz_m_2100", "desplaz_m_2100_p05", "desplaz_m_2100_p95", "tasa21_2100"]:
    cg = c if c in d.columns else c.replace("tasa21", "tasaL")
    if c in ref.columns:
        a_, b_ = d[cg].to_numpy(float), ref.loc[d.index, c].to_numpy(float)
        okc = np.isfinite(a_) & np.isfinite(b_)
        print(f"  {c:22s} corr {np.corrcoef(a_[okc], b_[okc])[0,1]:.4f}  media geo {np.mean(a_[okc]):8.2f}  media tesis {np.mean(b_[okc]):8.2f}  mediana|dif| {np.median(np.abs(a_[okc]-b_[okc])):.2f}")
print("anchura banda p95-p05 2100: geovisor", float(np.nanmedian(d["desplaz_m_2100_p95"] - d["desplaz_m_2100_p05"])), " tesis", float(np.nanmedian(ref["desplaz_m_2100_p95"] - ref["desplaz_m_2100_p05"])))
cfgj = json.load(open(TES + "configuracion_proyeccion.json")); print("tesis config:", {k_: cfgj[k_] for k_ in cfgj if k_ in ("b0_b1_persistencia_amortiguada", "n_mc", "sigma_regional_m_anio", "ventanas")})
# transectos sin tasa actual
print("transectos con tasa_actual NaN:", int(tab["tasa_actual"].isna().sum()), " desplaz NaN:", int(tab["desplaz_m_2100"].isna().sum()))

print("\n=== resumen escenarios vs tesis ===")
res = r6["resumen"].set_index("clave"); rt = pd.read_csv("/mnt/user-data/uploads/Resultados tesis/Mapas_IVC/escenarios_v4_resumen.csv").set_index("clave")
for k in ["actual", "ssp245_2050", "ssp585_2050", "ssp245_2100", "ssp585_2100"]:
    print(f"  {k:12s} % alta+muy alta: geovisor {res.loc[k, 'pct_alta_muy_alta']:.2f}  tesis sin Bruun {rt.loc[k, 'pct_alta_sin_bruun'] if k != 'actual' else rt.loc[k, 'pct_alta_muy_alta']}")
# ¿coinciden las clases por escenario con la tesis?
from src import ivc as mod
from src.configuracion import cargar_config
T = mod.cargar_transectos_ivc(cargar_config()).set_index("id_ivc")
for k in ["ssp245_2050", "ssp585_2100"]:
    e_ = r6["escenarios"][k].set_index("id_ivc")
    col = f"ivc_ewm_total_{k}"
    if col in T.columns:
        dd = e_[f"ivc_{k}"].to_numpy(float) - T.loc[e_.index, col].to_numpy(float)
        print(f"  ivc_{k} vs tesis {col}: mediana|dif| {np.nanmedian(np.abs(dd)):.4f} max {np.nanmax(np.abs(dd)):.4f} (la tesis incluye Bruun en ret.)")
    print("  variables reclasificadas en", k, ":", [c for c in e_.columns if c.startswith("c_")])

print("\n=== Bruun ===")
# hand calc: H12=4.3, T12=9.5, d50=0.2 mm, B=1, SLR 0.81 m, años 95, rh 4.775 mm/a, E=0.75
D = 0.2e-3; wf = 1.65 * 9.81 * D ** 2 / (18e-6 + np.sqrt(0.75 * 1.65 * 9.81 * D ** 3)); A = 0.067 * (wf * 100) ** 0.44
hc = 2.28 * 4.3 - 68.5 * 4.3 ** 2 / (9.81 * 9.5 ** 2); Ls = (hc / A) ** 1.5; dS = max(0.81 - 4.775e-3 * 95, 0); Rh = 0.75 * dS * Ls / (hc + 1)
bm = PR.bruun_mc(np.array([0.81]), 95, np.array([4.3]), np.array([0.2]), np.array([1.0]), 2000, H12_max_m=np.array([4.3]))
print(f"w={wf:.4f} m/s  A={A:.4f}  hc={hc:.3f} m  L*={Ls:.0f} m  ΔS neto={dS:.3f} m  R manual={Rh:.2f} m  geovisor central={bm['bruun_m'].iloc[0]:.2f}  p05/p95={bm['bruun_m_p05'].iloc[0]:.1f}/{bm['bruun_m_p95'].iloc[0]:.1f}")
print("Hallermeier con H12=4.3,T=9.5: hc =", round(hc, 2), "m (orden 8-9 m, razonable)")
# SLR menor que el ritmo histórico → R = 0
print("SLR 0.1 m en 95 años (< rh·años) -> R:", PR.bruun_mc(np.array([0.1]), 95, np.array([4.3]), np.array([0.2]), np.array([1.0]), 200)["bruun_m"].iloc[0])
# el escenario 'anio_base_slr' 2005 y slr_mm del horizonte: tesis usa 325/350/794/1009 mm; geovisor por defecto 330/350/810/1030
print("slr_mm por defecto geovisor:", [e["slr_mm"] for e in p["proyeccion"]["escenarios"]], " tesis:", rt["ascenso_nivel_mar_mm"].dropna().tolist())

print("\n=== ivc_futuro ===")
cols = r4["variables"]; w = r4["pesos"]["ewm"]; X = r3["clases"][cols].to_numpy(float)
roles = {v["rol"]: v["codigo"] for v in p["variables"] if v.get("rol") in ("tasa", "distancia_infra", "ancho_barra", "nivel_mar")}
print("roles:", roles)
clasif = {v["codigo"]: ([float(x) for x in v["cortes"].split(";")], [float(x) for x in v["clases"].split(";")], v.get("cerrado", "derecha")) for v in p["variables"] if v.get("normalizacion") == "umbrales"}
vals = {c: pd.to_numeric(r3["valores"][c], errors="coerce").to_numpy(float) for c in cols if c in r3["valores"].columns}
tasaL = tab["tasaL_2100"].to_numpy(); ret = np.maximum(-tab["desplaz_m_2100"].to_numpy(), 0)
v_, Xt = PR.ivc_futuro(X, w, cols, roles, clasif, vals, tasaL, ret, None, "1-5")
j = cols.index("c_cambio_costa"); print("clase tasa 2100 == por_umbrales(tasaL)?", np.array_equal(np.nan_to_num(Xt[:, j], nan=-1), np.nan_to_num(NO.por_umbrales(tasaL, *clasif["c_cambio_costa"]), nan=-1)))
j = cols.index("c_ancho_barra"); esp = NO.por_umbrales(np.maximum(vals["c_ancho_barra"] - ret, 0), *clasif["c_ancho_barra"])
print("clase ancho 2100 == por_umbrales(ancho-ret)?", np.array_equal(np.nan_to_num(Xt[:, j], nan=-1), np.nan_to_num(esp, nan=-1)), " ancho_barra: % censurados 'minimo' no se distinguen (sin columna censura en tabla_por_id)")
j = cols.index("c_nivel_mar"); print("c_nivel_mar sin pct_nivel: igual al actual?", np.array_equal(Xt[:, j], X[:, j]))
# en paso_proyeccion con campos_escenario sí cambia:
e_ = r6["escenarios"]["ssp585_2100"]; print("c_nivel_mar ssp585_2100 distinto del actual en", int((e_["c_nivel_mar_ssp585_2100"].to_numpy() != X[:, j]).sum()), "transectos")
# transectos con tasa NaN -> clase de tasa NaN -> IVC NaN
print("IVC 2100 NaN:", int(np.isnan(v_).sum()), " (transectos sin tasa en la última ventana:", int(np.isnan(tab['tasa_actual']).sum()), ")")
