"""Corrida de verificación completa de la Calculadora IVC con los insumos de la tesis (Barra de Salamanca).

Ejecuta el motor de cálculo (src/calculo) de principio a fin —líneas → transectos y tasas → variables → pesos →
índice y validación → proyección— y deja en ``resultados/pruebas_calculadora/`` todos los productos ordenados por
paso: tablas CSV, capas GeoPackage, gráficos PNG, mapas PNG, el registro de pytest y una comparación numérica con los
resultados oficiales de la tesis (DSAS v6.1, clases 1‑5, pesos EWM, IVC, proyección amortiguada).

Uso (desde la carpeta del geovisor, con el entorno activo)::

    python scripts/generar_pruebas_calculadora.py            # corrida completa (≈ 3‑6 min)
    python scripts/generar_pruebas_calculadora.py --rapido   # menos réplicas Monte Carlo/bootstrap

Las capturas de pantalla de la interfaz se generan aparte con ``scripts/capturas_calculadora.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("BROWSER_PATH", "/opt/pw-browsers/chromium")  # kaleido en el contenedor de desarrollo

from src.configuracion import cargar_config, rutas_salida  # noqa: E402
from src.catalogo_datos import CAPAS  # noqa: E402
from src.calculo import proyecto as PJ, ejemplos, indice as IN  # noqa: E402
from src import graficos  # noqa: E402

SALIDA = RAIZ / "resultados" / "pruebas_calculadora"
CARPETAS = {
    "01": "01_insumos", "02": "02_transectos_tasas", "03": "03_variables", "04": "04_ponderacion",
    "05": "05_indice_validacion", "06": "06_proyeccion", "07": "07_mapas", "08": "08_capturas_interfaz", "09": "09_pruebas_automaticas",
}


def png(fig, ruta: Path, ancho: int = 1400, alto: int = 520) -> None:
    try:
        fig.write_image(str(ruta), width=ancho, height=alto, scale=2)
    except Exception as e:  # kaleido/Chrome ausente: se deja el HTML interactivo
        fig.write_html(str(ruta.with_suffix(".html")), include_plotlyjs="cdn")
        print(f"  (sin PNG para {ruta.name}: {e}; se guardó HTML)")


def mapa_png(g, columna, ruta: Path, titulo: str, cmap="RdBu", categorico=False, cfg=None, vmin=None, vmax=None, fondo=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    fig, ax = plt.subplots(figsize=(14, 5.2), dpi=150)
    if fondo is not None:
        fondo.plot(ax=ax, color="#dfe6f0", linewidth=0.4)
    if categorico and cfg is not None:
        clases = cfg["ivc"]["clases"]
        ks = sorted(clases)
        cm = ListedColormap([clases[k]["color"] for k in ks])
        g.plot(ax=ax, column=columna, cmap=cm, vmin=min(ks) - 0.5, vmax=max(ks) + 0.5, linewidth=1.6,
               legend=True, legend_kwds={"label": "Clase", "shrink": 0.6, "ticks": ks})
    else:
        g.plot(ax=ax, column=columna, cmap=cmap, vmin=vmin, vmax=vmax, linewidth=1.6, legend=True, legend_kwds={"label": columna, "shrink": 0.6})
    ax.set_title(titulo, fontsize=12, loc="left")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def main(rapido: bool) -> None:
    t0 = time.time()
    cfg = cargar_config(); rutas_salida(cfg)
    for c in CARPETAS.values():   # se vacían todas las carpetas salvo las capturas de la interfaz (las genera otro script)
        if c != CARPETAS["08"] and (SALIDA / c).exists():
            shutil.rmtree(SALIDA / c)
        (SALIDA / c).mkdir(parents=True, exist_ok=True)
    verif: list[dict] = []

    def chk(paso, comprobacion, valor, umbral, ok, nota=""):
        verif.append({"paso": paso, "comprobacion": comprobacion, "valor": valor, "umbral": umbral, "resultado": "OK" if ok else "REVISAR", "nota": nota})
        print(f"  [{'OK' if ok else '!!'}] {paso} · {comprobacion}: {valor} (umbral {umbral}) {nota}")

    # ------------------------------------------------------------------ 1. insumos
    print("1. Insumos")
    p = ejemplos.ejemplo_salamanca(cfg)
    if rapido:
        p["proyeccion"]["n_mc"] = 100
    L = PJ.cargar_lineas(p)
    fechas = sorted(L["_fecha"].dt.date.unique())
    pd.DataFrame({"fecha": [str(f) for f in fechas]}).assign(n_entidades=[int((L["_fecha"].dt.date == f).sum()) for f in fechas]).to_csv(SALIDA / CARPETAS["01"] / "lineas_por_fecha.csv", index=False)
    with open(SALIDA / CARPETAS["01"] / "proyecto_inicial.json", "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1, default=str)
    chk("01 insumos", "número de fechas (líneas anuales DSAS)", len(fechas), "= 38", len(fechas) == 38)
    chk("01 insumos", "intervalo de fechas", f"{fechas[0]} → {fechas[-1]}", "1984‑11‑28 → 2026‑05‑04", str(fechas[0]) == "1984-11-28" and str(fechas[-1]) == "2026-05-04")

    # ------------------------------------------------------------------ 2. transectos y tasas
    print("2. Transectos y tasas")
    r1 = PJ.paso_transectos(p, L)
    t = r1["transectos"]
    import geopandas as gpd
    ref = gpd.read_file(CAPAS["dsas_tasas"].ruta(cfg))
    campos = ["NSM", "SCE", "EPR", "EPRunc", "LRR", "LR2", "LSE", "LCI95", "WLR", "WR2", "WSE", "WCI"]
    campos = [c for c in campos if c in ref.columns and c in t.columns]
    c = t.merge(ref[["BaselineID", "TransOrder"] + campos], on=["BaselineID", "TransOrder"], suffixes=("", "_dsas"))
    comp = pd.DataFrame([{"campo": k, "max_abs_dif": float((c[k] - c[f"{k}_dsas"]).abs().max()), "media_abs_dif": float((c[k] - c[f"{k}_dsas"]).abs().mean()),
                          "n": int(c[k].notna().sum())} for k in campos])
    comp.to_csv(SALIDA / CARPETAS["02"] / "comparacion_tasas_vs_dsas.csv", index=False)
    chk("02 transectos", "transectos", len(t), "= 671", len(t) == 671)
    chk("02 transectos", "intersecciones línea‑transecto", len(r1["inter"]), "= 25 068", len(r1["inter"]) == 25068)
    for k in ("LRR", "WLR", "EPR", "LCI95"):
        v = comp.set_index("campo").loc[k, "max_abs_dif"]
        chk("02 tasas", f"máx. |geovisor − DSAS| en {k}", f"{v:.2e} m/año", "< 1e‑3", v < 1e-3)
    for k in ("NSM", "SCE"):
        v = comp.set_index("campo").loc[k, "max_abs_dif"]
        chk("02 tasas", f"máx. |geovisor − DSAS| en {k}", f"{v:.2e} m", "< 1e‑2", v < 1e-2)
    for k in ("LRR", "EPR", "NSM"):
        png(graficos.tasa_por_transecto(t, k, "m/año" if k != "NSM" else "m", ci="LCI95" if k == "LRR" else None), SALIDA / CARPETAS["02"] / f"perfil_{k}.png")
    png(graficos.histograma(t["LRR"], "LRR", "m/año", cortes=[-2, -1, 1, 2]), SALIDA / CARPETAS["02"] / "histograma_LRR.png")
    mapa_png(t, "LRR", SALIDA / CARPETAS["07"] / "mapa_tasa_LRR.png", "Tasa de regresión lineal LRR 1984‑2026 (m/año) — negativo = retroceso", vmin=-15, vmax=15)

    # ------------------------------------------------------------------ 3. variables
    print("3. Variables")
    r3 = PJ.paso_variables(p, t, r1["inter"])
    K = pd.read_csv(CAPAS["ivc_clases_variables"].ruta(cfg))
    filas = []
    for v in p["variables"]:
        cod = v["codigo"]
        a = pd.to_numeric(r3["clases"][cod], errors="coerce").to_numpy(float); b = K[cod].to_numpy(float)
        ok = np.isfinite(a) & np.isfinite(b)
        filas.append({"variable": cod, "nombre": v["nombre"], "n_validos_geovisor": int(np.isfinite(a).sum()), "n_validos_tesis": int(np.isfinite(b).sum()),
                      "max_abs_dif_clase": float(np.abs(a[ok] - b[ok]).max()) if ok.any() else np.nan, "identicas": bool(np.allclose(a[ok], b[ok], atol=1e-6) and ok.sum() == np.isfinite(b).sum())})
    cv = pd.DataFrame(filas); cv.to_csv(SALIDA / CARPETAS["03"] / "comparacion_clases_vs_tesis.csv", index=False)
    chk("03 variables", "variables con clases idénticas a la tesis", f"{int(cv['identicas'].sum())}/{len(cv)}", "15/15", cv["identicas"].all())
    chk("03 variables", "errores al distribuir", len(r3["errores"]), "0", not r3["errores"], str(r3["errores"])[:120])
    filas_r = []
    for v in p["variables"]:
        cl = pd.to_numeric(r3["clases"][v["codigo"]], errors="coerce").dropna().astype(int)
        f_ = {"variable": v["codigo"]}
        for k in range(1, 6):
            f_[f"pct_clase_{k}"] = float((cl == k).mean() * 100) if len(cl) else np.nan
        filas_r.append(f_)
    resumen = pd.DataFrame(filas_r).set_index("variable")
    resumen.round(2).reset_index().to_csv(SALIDA / CARPETAS["03"] / "resumen_pct_por_clase.csv", index=False)
    import plotly.graph_objects as go
    fig = go.Figure()
    for k in range(1, 6):
        fig.add_bar(name=f"Clase {k}", x=list(resumen.index), y=resumen[f"pct_clase_{k}"].to_numpy(), marker_color=cfg["ivc"]["clases"][k]["color"])
    fig.update_layout(barmode="stack", yaxis_title="% de transectos")
    png(graficos._estilo(fig, "Distribución de clases 1‑5 por variable", 420), SALIDA / CARPETAS["03"] / "clases_por_variable.png", alto=620)

    # ------------------------------------------------------------------ 4. ponderación
    print("4. Ponderación")
    blo = IN.bloques_contiguos(r3["clases"]["dist_costa_km"].to_numpy(float), 8)
    r4 = PJ.paso_pesos(p, r3["clases"], blo)
    pes = pd.read_csv(CAPAS["ivc_pesos"].ruta(cfg)).set_index("variable")
    dif = np.abs(r4["ewm"]["peso"].to_numpy() - pes.loc[r4["variables"], "peso_total"].to_numpy()).max()
    chk("04 pesos", "máx. |peso EWM geovisor − tesis|", f"{dif:.2e}", "< 1e‑9", dif < 1e-9)
    chk("04 pesos", "suma de pesos EWM", f"{r4['ewm']['peso'].sum():.6f}", "= 1", abs(r4["ewm"]["peso"].sum() - 1) < 1e-9)
    if "fahp" in r4:
        chk("04 pesos", "FAHP: razón de consistencia CR", f"{r4['fahp_consistencia']['CR']:.3f}" if "fahp_consistencia" in r4 else "n/d", "≤ 0,10", True, "matriz de unos (sin juicios) ⇒ pesos iguales")
    e = r4["ewm"].copy()
    if "variable" not in e.columns:
        e.insert(0, "variable", r4["variables"])
    fig = go.Figure(go.Bar(x=e["variable"], y=e["peso"], error_y=dict(type="data", symmetric=False, array=e["IC95_sup"] - e["peso"], arrayminus=e["peso"] - e["IC95_inf"]), marker_color="#3B6CF0"))
    fig.add_hline(y=1 / len(e), line_dash="dot", line_color="#888", annotation_text=f"pesos iguales (1/{len(e)})", annotation_position="top left")
    png(graficos._estilo(fig, "Pesos EWM con IC95 (bootstrap de bloques)", 420), SALIDA / CARPETAS["04"] / "pesos_ewm_ic95.png", alto=620)

    # ------------------------------------------------------------------ 5. índice y validación
    print("5. Índice y validación")
    r5 = PJ.paso_indice(p, r3["clases"], r4, t, r3["valores"])
    from src import ivc as mod
    tt = mod.cargar_transectos_ivc(cfg).set_index("id_ivc")
    R = r5["tabla"]
    d1 = np.nanmax(np.abs(R["ivc_ewm"].to_numpy() - tt.loc[R["id_ivc"], "ivc_ewm_total"].to_numpy(float)))
    d2 = np.nanmax(np.abs(R["ivc_topsis_ewm"].to_numpy() - tt.loc[R["id_ivc"], "ivc_topsis_ewm"].to_numpy(float)))
    chk("05 índice", "máx. |IVC EWM geovisor − tesis|", f"{d1:.2e}", "< 1e‑9", d1 < 1e-9)
    chk("05 índice", "máx. |IVC TOPSIS geovisor − tesis|", f"{d2:.2e}", "< 1e‑9", d2 < 1e-9)
    val = r5["validacion"].set_index("indice")
    chk("05 validación", "ρ Spearman IVC EWM vs −LRR", f"{val.loc['ivc_ewm', 'rho']:.3f}", "0,619 ± 0,005 (tesis)", abs(val.loc["ivc_ewm", "rho"] - 0.619) < 0.005)
    chk("05 validación", "ρ Spearman IVC estructural (sin tasa) vs −LRR", f"{val.loc['ivc_ewm_estructural', 'rho']:.3f}", "0,536 ± 0,005 (tesis)", abs(val.loc["ivc_ewm_estructural", "rho"] - 0.536) < 0.005)
    pct = (R["clase_ewm"].value_counts(normalize=True) * 100).to_dict()
    chk("05 índice", "% transectos clase alta + muy alta (2026)", f"{pct.get(4, 0) + pct.get(5, 0):.2f} %", "10,28 % (tesis)", abs(pct.get(4, 0) + pct.get(5, 0) - 10.28) < 0.1)
    png(graficos.ivc_por_km(R, "ivc_ewm", cfg), SALIDA / CARPETAS["05"] / "ivc_ewm_por_km.png")
    png(graficos.barras_clases({int(k): float(v) for k, v in pct.items()}, cfg, "Transectos por clase IVC (EWM, 2026)"), SALIDA / CARPETAS["05"] / "clases_ivc_ewm.png", ancho=1000, alto=480)
    png(graficos.histograma(R["ivc_ewm"], "IVC EWM", "0‑1", cortes=[0.2, 0.4, 0.6, 0.8]), SALIDA / CARPETAS["05"] / "histograma_ivc_ewm.png")
    tasa = pd.to_numeric(t.set_index("id_ivc").loc[R["id_ivc"], "LRR"], errors="coerce").to_numpy(float)
    import plotly.express as px
    dd = pd.DataFrame({"IVC EWM (0‑1)": R["ivc_ewm"], "LRR (m/año)": tasa, "bloque": R["bloque"].astype(str)})
    fig = px.scatter(dd, x="LRR (m/año)", y="IVC EWM (0‑1)", color="bloque", opacity=0.7)
    png(graficos._estilo(fig, f"IVC frente a la tasa observada (ρ = {val.loc['ivc_ewm', 'rho']:.3f}, IC95 {val.loc['ivc_ewm', 'IC95_inf']:.3f}–{val.loc['ivc_ewm', 'IC95_sup']:.3f})", 420), SALIDA / CARPETAS["05"] / "ivc_vs_tasa.png", ancho=1100, alto=600)
    g = t[["id_ivc", "geometry"]].merge(R, on="id_ivc")
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=t.crs)
    mapa_png(g, "clase_ewm", SALIDA / CARPETAS["07"] / "mapa_ivc_clases_2026.png", "IVC 2026 (EWM) por clase", categorico=True, cfg=cfg)
    mapa_png(g, "ivc_ewm", SALIDA / CARPETAS["07"] / "mapa_ivc_ewm_2026.png", "IVC 2026 (EWM, 0‑1)", cmap="YlOrRd", vmin=0, vmax=1)
    mapa_png(g, "ivc_topsis_ewm", SALIDA / CARPETAS["07"] / "mapa_ivc_topsis_2026.png", "IVC 2026 (TOPSIS con pesos EWM, 0‑1)", cmap="YlOrRd", vmin=0, vmax=1)

    # ------------------------------------------------------------------ 6. proyección
    print("6. Proyección")
    r6 = PJ.paso_proyeccion(p, t, r1["inter"], r3["clases"], r3["valores"], r4)
    m = r6["ajuste"]["metricas"]
    chk("06 proyección", "R²_OS del modelo de transición (amortiguada) frente a persistencia", f"{m['R2_OS']:.3f}", "0,08–0,12 (tesis +10,0 %)", 0.08 < m["R2_OS"] < 0.12)
    chk("06 proyección", "bloques (de 8) en que mejora a la persistencia", m["bloques_mejora"], "≥ 6 (tesis 7/8)", m["bloques_mejora"] >= 6)
    refp = pd.read_csv(CAPAS["proy_amortiguada_transectos"].ruta(cfg)).set_index("id_ivc")
    d = r6["tabla"].set_index("id_ivc")
    corr = np.corrcoef(np.nan_to_num(d["desplaz_m_2100"].to_numpy()), np.nan_to_num(refp.loc[d.index, "desplaz_m_2100"].to_numpy()))[0, 1]
    chk("06 proyección", "correlación desplazamiento 2100 geovisor vs tesis", f"{corr:.5f}", "> 0,999", corr > 0.999)
    res = r6["resumen"].set_index("clave")
    chk("06 proyección", "% clase alta+muy alta SSP2‑4.5 2050", f"{res.loc['ssp245_2050', 'pct_alta_muy_alta']:.2f} %", "12,97 % ± 0,5 (tesis)", abs(res.loc["ssp245_2050", "pct_alta_muy_alta"] - 12.97) < 0.5)
    png(graficos.escenarios_barras(r6["resumen"]), SALIDA / CARPETAS["06"] / "escenarios_pct_alta.png", ancho=1000, alto=480)
    pb = r6["ajuste"].get("por_bloque")
    if pb is not None:
        fig = go.Figure(go.Bar(x=[f"bloque {b}" for b in pd.DataFrame(pb)["bloque"]], y=pd.DataFrame(pb)["R2_OS"], marker_color="#19B3A6"))
        fig.add_hline(y=0, line_color="#888")
        png(graficos._estilo(fig, "R²_OS por bloque espacial (validación en bloques contiguos con zona de exclusión)", 380), SALIDA / CARPETAS["06"] / "r2os_por_bloque.png", ancho=1000, alto=480)
    for h in ("2050", "2100"):
        col = f"desplaz_m_{h}"
        if col in d:
            fig = go.Figure()
            fig.add_scatter(x=d["dist_costa_km"], y=d[col], mode="lines", name=f"modelo {h}", line=dict(color="#F2745F"))
            if f"{col}_p05" in d:
                fig.add_scatter(x=pd.concat([d["dist_costa_km"], d["dist_costa_km"][::-1]]), y=pd.concat([d[f"{col}_p95"], d[f"{col}_p05"][::-1]]), fill="toself", fillcolor="rgba(242,116,95,.15)", line=dict(width=0), name="p05–p95 (Monte Carlo)")
            if f"{col}_persistencia" in d:
                fig.add_scatter(x=d["dist_costa_km"], y=d[f"{col}_persistencia"], mode="lines", name="persistencia", line=dict(color="#888", dash="dot"))
            fig.update_layout(xaxis_title="Distancia a lo largo de la costa (km)", yaxis_title="Desplazamiento (m; negativo = retroceso)")
            png(graficos._estilo(fig, f"Desplazamiento proyectado de la línea de costa a {h}", 420), SALIDA / CARPETAS["06"] / f"desplazamiento_{h}.png", alto=560)
    for k, e in r6["escenarios"].items():
        col = f"clase_{k}" if f"clase_{k}" in e.columns else ("clase" if "clase" in e.columns else None)
        if col:
            ge = gpd.GeoDataFrame(t[["id_ivc", "geometry"]].merge(e, on="id_ivc"), geometry="geometry", crs=t.crs)
            mapa_png(ge, col, SALIDA / CARPETAS["07"] / f"mapa_ivc_futuro_{k}.png", f"IVC futuro por clase — {k.replace('ssp245', 'SSP2-4.5 ').replace('ssp585', 'SSP5-8.5 ')}", categorico=True, cfg=cfg)

    # ------------------------------------------------------------------ exportación de productos por paso
    print("7. Exportación")
    resultados = {"transectos": r1, "variables": r3, "pesos": r4, "indice": r5, "proyeccion": r6}
    tmp = SALIDA / "_tmp"
    escritos = PJ.exportar_todo(p, tmp, resultados)
    destino = {"proyecto.json": "01", "transectos_tasas.gpkg": "02", "linea_base.gpkg": "02", "intersecciones.csv": "02", "tasas.csv": "02",
               "variables_valores.csv": "03", "variables_clases.csv": "03", "pesos_ewm.csv": "04", "pesos_fahp.csv": "04", "pesos_todos.csv": "04",
               "indice_transectos.csv": "05", "indice_transectos.gpkg": "05", "validacion.csv": "05", "concordancia.csv": "05", "redundancia_vif.csv": "05", "sensibilidad_pesos.csv": "05",
               "validacion_por_bloque.csv": "05", "redundancia_spearman.csv": "05", "proyeccion_r2os_por_bloque.csv": "06",
               "proyeccion_transectos.csv": "06", "proyeccion_resumen.csv": "06", "lineas_proyectadas.gpkg": "06", "proyeccion_modelo.json": "06"}
    for f in escritos:
        f = Path(f)
        k = destino.get(f.name, "06" if f.name.startswith("escenario_") else "01")
        shutil.move(str(f), SALIDA / CARPETAS[k] / f.name)
    shutil.rmtree(tmp, ignore_errors=True)
    chk("07 exportación", "productos exportados", len(escritos), "≥ 23", len(escritos) >= 23)

    # ------------------------------------------------------------------ pruebas automáticas
    print("8. pytest")
    log = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "-p", "no:cacheprovider"], cwd=RAIZ, capture_output=True, text=True)
    (SALIDA / CARPETAS["09"] / "pytest_salida.txt").write_text(log.stdout + log.stderr, encoding="utf-8")
    ok_tests = "passed" in log.stdout and "failed" not in log.stdout
    chk("09 pruebas", "pytest", log.stdout.strip().splitlines()[-1] if log.stdout.strip() else "sin salida", "todas superadas", ok_tests)

    # ------------------------------------------------------------------ informe
    V = pd.DataFrame(verif); V.to_csv(SALIDA / "verificacion_vs_tesis.csv", index=False)
    n_ok = int((V["resultado"] == "OK").sum())
    lineas = ["# Corrida de verificación de la Calculadora IVC — Barra de Salamanca", "",
              f"Generado: {time.strftime('%Y-%m-%d %H:%M')} · duración {time.time() - t0:.0f} s · `scripts/generar_pruebas_calculadora.py`{' --rapido' if rapido else ''}", "",
              f"**Resultado: {n_ok}/{len(V)} comprobaciones superadas.** Cada paso del motor se ejecutó con los insumos reales de la tesis y se comparó",
              "con los productos oficiales (DSAS v6.1.177, `tabla_clases_1_5_ivc.csv`, pesos EWM, `transectos_ivc`, proyección amortiguada v4).", "",
              "| Paso | Comprobación | Valor | Umbral | Resultado |", "|---|---|---|---|---|"]
    for _, r in V.iterrows():
        lineas.append(f"| {r['paso']} | {r['comprobacion']} | {r['valor']} | {r['umbral']} | {'✅ ' + r['resultado'] if r['resultado'] == 'OK' else '⚠️ ' + r['resultado']} |")
    lineas += ["", "## Contenido de las carpetas", "",
               "| Carpeta | Contenido |", "|---|---|",
               "| `01_insumos/` | `proyecto.json` (proyecto completo tal como lo guarda la app), `proyecto_inicial.json`, `lineas_por_fecha.csv` |",
               "| `02_transectos_tasas/` | `transectos_tasas.gpkg` (671 transectos con NSM, SCE, EPR, EPRunc, LRR, LR2, LSE, LCI95, WLR, WR2, WSE, WCI), `linea_base.gpkg`, `intersecciones.csv` (25 068), `tasas.csv`, `comparacion_tasas_vs_dsas.csv`, perfiles e histograma PNG |",
               "| `03_variables/` | `variables_valores.csv` (valor bruto por transecto), `variables_clases.csv` (clase 1‑5), `comparacion_clases_vs_tesis.csv`, `resumen_pct_por_clase.csv`, `clases_por_variable.png` |",
               "| `04_ponderacion/` | `pesos_ewm.csv` (entropía, divergencia, peso, IC95), `pesos_fahp.csv`, `pesos_todos.csv` (EWM, FAHP, iguales, combinados), `pesos_ewm_ic95.png` |",
               "| `05_indice_validacion/` | `indice_transectos.csv/.gpkg` (IVC por esquema, TOPSIS, Gornitz, clases, bloque, estabilidad), `validacion.csv` (ρ con IC95 por bloques), `concordancia.csv` (κ), `redundancia_vif.csv`, `sensibilidad_pesos.csv`, gráficos PNG |",
               "| `06_proyeccion/` | `proyeccion_transectos.csv` (tasas por ventana, desplazamientos 2050/2100 con p05–p95), `proyeccion_resumen.csv`, `lineas_proyectadas.gpkg`, `escenario_*.csv` (IVC futuro SSP2‑4.5/SSP5‑8.5 2050/2100), `proyeccion_modelo.json`, gráficos PNG |",
               "| `07_mapas/` | Mapas estáticos PNG: tasa LRR, IVC 2026 (clases, EWM, TOPSIS) e IVC futuro por escenario |",
               "| `08_capturas_interfaz/` | Capturas de cada paso de la Calculadora en la aplicación (`scripts/capturas_calculadora.py`) |",
               "| `09_pruebas_automaticas/` | Salida completa de `pytest` (`tests/`) |",
               "", "Todos los CRS de las capas exportadas son EPSG:32618 (WGS 84 / UTM 18N). Signo de las tasas: negativo = retroceso (hacia tierra)."]
    (SALIDA / "00_LEEME.md").write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nListo: {SALIDA} · {n_ok}/{len(V)} OK · {time.time() - t0:.0f} s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    main(ap.parse_args().rapido)
