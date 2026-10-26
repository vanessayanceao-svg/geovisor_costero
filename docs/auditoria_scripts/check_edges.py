"""Comprobaciones 10-11: exportación completa, serialización y casos límite."""
import sys, pickle, warnings, os, json, copy
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd, geopandas as gpd
from src.calculo import proyecto as PJ, tasas as TA, transectos as TR, indice as IN, ponderacion as PO, normalizacion as NO
e2e = pickle.load(open("docs/auditoria_scripts/_trabajo/e2e.pkl", "rb"))
p, L, r1, r3, r4, r5, r6 = (e2e[k] for k in ("p", "L", "r1", "r3", "r4", "r5", "r6"))
OUT = "docs/auditoria_scripts/_trabajo/export"

print("=== 10. exportar_todo ===")
res = {"transectos": r1, "variables": r3, "pesos": r4, "indice": r5, "proyeccion": r6}
esc = PJ.exportar_todo(p, OUT, res)
print(len(esc), "archivos:", sorted(os.path.basename(str(x)) for x in esc))
for f in ("transectos_tasas.gpkg", "indice_transectos.gpkg", "lineas_proyectadas.gpkg", "linea_base.gpkg"):
    g = gpd.read_file(f"{OUT}/{f}"); print(f"  {f}: CRS {g.crs.to_epsg()}  n={len(g)}  cols={len(g.columns)}")
print("  no exportado: redundancia_rho (Spearman entre variables):", "redundancia_rho" in r5, "| por_bloque (R2_OS por bloque):", "por_bloque" in r6["ajuste"], "| rasgos de ventanas:", "rasgos" in r6,
      "| tablas % categoría:", list(r3["tablas"].keys()), "| fahp_consistencia:", "fahp_consistencia" in r4, "| franjas de muestreo (geometría): no existe función", "| escenarios en GPKG: no")
pj = json.load(open(f"{OUT}/proyecto.json")); print("  proyecto.json claves:", list(pj.keys()), " n_mc guardado:", pj["proyeccion"]["n_mc"])
pm = json.load(open(f"{OUT}/proyeccion_modelo.json")); print("  proyeccion_modelo.json:", list(pm.keys()))
print("  ¿se exporta la semilla, ventanas, sigma_regional, horizontes?", {k: (k in pm or k in pj["proyeccion"]) for k in ("semilla", "ventanas", "sigma_regional", "horizontes")})
# proyecto.json: ¿parámetros derivados de datos se guardan? el esquema principal se respeta en paso_indice?
print("  paso_indice ignora 'esquema_principal' (calcula todos; topsis/estructural/sensibilidad solo con EWM):", "esquema_principal" not in open("./src/calculo/proyecto.py").read().split("def paso_indice")[1].split("def paso_proyeccion")[0])

print("\n=== 11. casos límite ===")
# a) un NaN en una clase -> TOPSIS de TODOS los transectos cambia
cl = r3["clases"].copy(); cl.loc[0, "c_oleaje"] = np.nan
r5b = PJ.paso_indice(p, cl, r4, r1["transectos"], r3["valores"])
dt = (r5b["tabla"]["ivc_topsis_ewm"] - r5["tabla"]["ivc_topsis_ewm"]).abs()
print("a) 1 NaN en c_oleaje: transectos cuyo TOPSIS cambia:", int((dt > 1e-9).sum()), " max cambio:", round(float(dt.max()), 4), " | ivc_ewm cambia en:", int(((r5b['tabla']['ivc_ewm'] - r5['tabla']['ivc_ewm']).abs() > 1e-9).sum()))
print("   kappa con NaN:", r5b["concordancia"].iloc[0]["kappa_cuadratico"], " estabilidad fila NaN:", r5b["tabla"]["estabilidad_clase_ewm_pct"].iloc[0])
# b) todas las clases NaN en un transecto -> IVC NaN, clase NaN, cvi NaN
cl2 = r3["clases"].copy(); cl2.loc[5, [c for c in r4["variables"]]] = np.nan
r5c = PJ.paso_indice(p, cl2, r4, r1["transectos"], r3["valores"])
print("b) fila toda NaN: ivc", r5c["tabla"]["ivc_ewm"].iloc[5], "clase", r5c["tabla"]["clase_ewm"].iloc[5], "gornitz", r5c["tabla"]["cvi_gornitz"].iloc[5], "clase_gornitz", r5c["tabla"]["clase_cvi_gornitz"].iloc[5])
# c) tasas: un solo punto / dos puntos / unc 0 / fechas duplicadas
it = pd.DataFrame({"id_t": [1, 1, 2, 3, 3, 3], "fecha": pd.to_datetime(["2000-01-01", "2000-01-01", "2001-01-01", "2000-01-01", "2010-01-01", "2020-01-01"]),
                   "distancia_m": [10, 20, 5, 100, 80, 60], "unc_m": [10, 10, 10, 0, 10, 10]})
it["anio_dec"] = TR.anio_decimal(it["fecha"])
T = TA.tasas_por_transecto(it, umbral_lineas=3); print("c)", T.to_string())
print("   (id 1: fechas duplicadas -> años=0 -> EPR ausente; id 3: unc=0 -> WLR omitido en vez de usar unc por defecto)")
# d) _ols con n=2 y umbral 2
print("d) _ols n=2:", TA._ols(np.array([2000., 2001.]), np.array([0., 3.])), " (LSE/LCI95 NaN correctos)")
# e) EWM con columna categórica (texto) que llega a clases
cl3 = r3["clases"].copy(); cl3["c_sustrato"] = "arenoso"
try:
    PJ.paso_pesos(p, cl3, e2e["blo"])
except Exception as e:
    print("e) columna de texto en clases ->", type(e).__name__, e)
# f) cortes del índice distintos de los de la tesis: ¿la sensibilidad/estabilidad usan los del proyecto?
p2 = copy.deepcopy(p); p2["indice"]["cortes"] = [0.1, 0.3, 0.5, 0.7]
r5d = PJ.paso_indice(p2, r3["clases"], r4, r1["transectos"], r3["valores"])
cb_def = NO.clase_de_indice_01(r5d["tabla"]["ivc_ewm"]); cb_p = NO.clase_de_indice_01(r5d["tabla"]["ivc_ewm"], p2["indice"]["cortes"])
print("f) cortes [0.1,0.3,0.5,0.7]: clase_ewm usa cortes del proyecto:", np.array_equal(r5d["tabla"]["clase_ewm"], cb_p),
      "| sensibilidad idéntica a la de cortes por defecto (ignora cortes):", np.allclose(r5d["sensibilidad"]["pct_cambia_clase"], r5["sensibilidad"]["pct_cambia_clase"]),
      "| estabilidad idéntica:", np.allclose(r5d["tabla"]["estabilidad_clase_ewm_pct"], r5["tabla"]["estabilidad_clase_ewm_pct"]))
# g) división por cero en bloques_contiguos con km constante
print("g) bloques con km constante:", IN.bloques_contiguos(np.zeros(5), 8))
# h) rho con tasa NaN parcial
print("h) rho con 50 % NaN en tasa:", IN.rho_ic_bloques(np.arange(20.), np.r_[np.arange(10.), np.full(10, np.nan)], np.repeat([0, 1, 2, 3], 5))["n"])
# i) EWM escala 0-1 (difusa) con valor 0 en la columna (mínimo) y constante 0
Xd = np.c_[np.linspace(0, 1, 20), np.zeros(20), np.ones(20)]
print("i) EWM difusa [x, 0, 1]:", PO.pesos_ewm(Xd).round(4), " <-- la constante 0 recibe peso 0.5 y la constante 1 recibe 0")
# j) proyección: horizonte anterior a anio_ref o ventana sin datos
pp = copy.deepcopy(p); pp["proyeccion"]["horizontes"] = [2030, 2050]; pp["proyeccion"]["n_mc"] = 50
r6b = PJ.paso_proyeccion(pp, r1["transectos"], r1["inter"], r3["clases"], r3["valores"], r4)
print("j) horizonte 2030 (< fin de W3 2047): desplaz_2030 = tasa_2026_2047 * 3.66?", np.allclose(r6b["tabla"]["desplaz_m_2030"], r6b["tabla"]["tasa_2026_2047"] * (2030 - r6b["anio_ref"]), equal_nan=True),
      " | escenarios con anio 2100 omitidos:", list(r6b["escenarios"].keys()))
print("   tasaL_2030 (media 2009-2030) mezcla tasa observada? solo ventanas futuras:", float(np.nanmean(r6b["tabla"]["tasaL_2030"])), "vs tasa W3", float(np.nanmean(r6b["tabla"]["tasa_2026_2047"])), " <-- tasaL para T−L < anio_ref sólo integra (anio_ref,T) y divide por L")
# k) una sola ventana (L=45)
pp2 = copy.deepcopy(p); pp2["proyeccion"]["ventana_anios"] = 45; pp2["proyeccion"]["n_mc"] = 50
try:
    r6c = PJ.paso_proyeccion(pp2, r1["transectos"], r1["inter"], r3["clases"], r3["valores"], r4)
    print("k) una ventana L=45: modelo", r6c["ajuste"]["tipo"], " métricas", r6c["ajuste"]["metricas"], " banda p05/p95 2100 mediana:", float(np.nanmedian(r6c["tabla"]["desplaz_m_2100_p95"] - r6c["tabla"]["desplaz_m_2100_p05"])), " (sin residuos OOF: solo ruido regional σ=1)")
except Exception as e:
    print("k) una ventana ->", type(e).__name__, e)
# l) ventana L=10 (5 ventanas) -> sigma_regional estimado
pp3 = copy.deepcopy(p); pp3["proyeccion"]["ventana_anios"] = 10; pp3["proyeccion"]["n_mc"] = 50
r6d = PJ.paso_proyeccion(pp3, r1["transectos"], r1["inter"], r3["clases"], r3["valores"], r4)
print("l) L=10:", r6d["ventanas"], " sigma_regional estimado:", r6d["sigma_regional"], " R2_OS:", round(r6d["ajuste"]["metricas"]["R2_OS"], 3), " n:", r6d["ajuste"]["metricas"]["n"])
print("   ¡el modelo se ajusta solo con el último par de ventanas (H[-2]→H[-1]) aunque haya 5!")
# m) kappa con clases no enteras (ponderado_area produce clases continuas → clase_de_indice las discretiza; OK). kappa con clase 0?
print("m) kappa con clase fuera de 1..5:", end=" ")
try:
    print(IN.kappa_ponderado([1, 2, 6], [1, 2, 5]))
except Exception as e:
    print(type(e).__name__, e)
# n) fuzzificar con delta > a-1 para a=2 → l = 1 (recorte), u para 1/a: 1/max(b−δ,1)
print("n) fuzzificar a=2, δ=2:", PO.fuzzificar(np.array([[1, 2], [0.5, 1]]), 2.0)[0, 1], PO.fuzzificar(np.array([[1, 2], [0.5, 1]]), 2.0)[1, 0])
# o) matriz FAHP con fila de NaN (UI data_editor vacío) → matriz_desde_tabla
print("o) matriz_desde_tabla con NaN triángulo inferior:", PO.matriz_desde_tabla(pd.DataFrame([[1, 3], [np.nan, 1]])).tolist(), " con ambos NaN:", PO.matriz_desde_tabla(pd.DataFrame([[1, np.nan], [np.nan, 1]])).tolist(), "<-- NaN permanece → consistencia() devuelve NaN")
try:
    print("   pesos_fahp con NaN:", PO.pesos_fahp(PO.matriz_desde_tabla(pd.DataFrame([[1, np.nan], [np.nan, 1]]))))
except Exception as e:
    print("   pesos_fahp con NaN ->", type(e).__name__, e)
# p) serialización JSON de un proyecto con numpy
pp4 = copy.deepcopy(p); pp4["x"] = np.float64(np.nan); pp4["y"] = np.int64(3)
PJ.guardar_proyecto(pp4, OUT + "/json"); print("p) JSON con numpy:", json.load(open(OUT + "/json/proyecto.json"))["x"], json.load(open(OUT + "/json/proyecto.json"))["y"])
# q) por_umbrales con cortes no crecientes / clases con 4 valores
for c_, k_ in [("1;2;2;3", "5;4;3;2;1"), ("1;2;3;4", "5;4;3;2")]:
    try:
        PJ.normalizar_variable({"codigo": "z", "normalizacion": "umbrales", "cortes": c_, "clases": k_}, pd.Series([1.0]), None, np.array([0.]))
    except ValueError as e:
        print("q)", c_, k_, "->", e)
# r) 'directa' con todos NaN -> nanmin de vacío
try:
    PJ.normalizar_variable({"codigo": "z", "normalizacion": "directa"}, pd.Series([np.nan, np.nan]), None, np.array([0., 1.]))
    print("r) directa todo NaN: sin error (devuelve NaN)")
except Exception as e:
    print("r) directa todo NaN ->", type(e).__name__, e)
