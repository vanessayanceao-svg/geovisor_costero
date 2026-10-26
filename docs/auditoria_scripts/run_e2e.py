"""Ejecuta el flujo completo y guarda los objetos intermedios en pickle."""
import sys, pickle, time
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from src.configuracion import cargar_config, rutas_salida
from src.calculo import proyecto as PJ, ejemplos, indice as IN

cfg = cargar_config(); rutas_salida(cfg)
p = ejemplos.ejemplo_salamanca(cfg)
t0 = time.time()
L = PJ.cargar_lineas(p)
r1 = PJ.paso_transectos(p, L); print("transectos", time.time() - t0, len(r1["transectos"]), len(r1["inter"]))
r3 = PJ.paso_variables(p, r1["transectos"], r1["inter"]); print("variables", time.time() - t0, r3["errores"])
blo = IN.bloques_contiguos(r3["clases"]["dist_costa_km"].to_numpy(float), 8)
r4 = PJ.paso_pesos(p, r3["clases"], blo); print("pesos", time.time() - t0)
r5 = PJ.paso_indice(p, r3["clases"], r4, r1["transectos"], r3["valores"]); print("indice", time.time() - t0)
p["proyeccion"]["n_mc"] = 300
r6 = PJ.paso_proyeccion(p, r1["transectos"], r1["inter"], r3["clases"], r3["valores"], r4); print("proyeccion", time.time() - t0)
OUT = "docs/auditoria_scripts/_trabajo/e2e.pkl"
with open(OUT, "wb") as f:
    pickle.dump({"p": p, "L": L, "r1": r1, "r3": r3, "r4": r4, "r5": r5, "r6": r6, "blo": blo}, f)
print(r5["validacion"])
print(r6["ajuste"]["metricas"])
print(r6["resumen"])
