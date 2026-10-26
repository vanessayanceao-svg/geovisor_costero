"""Sección 6 — Evaluación del modelo: métricas verificadas de la validación anidada (v4) e importación de tablas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import graficos, metricas_modelos as mm
from ..catalogo_datos import CAPAS
from . import comunes as ui


def render(cfg: dict) -> None:
    ui.seccion("Evaluación del modelo", "cerebro", "métricas de la validación anidada v4 (fuera de bloque) e importación de tablas")
    met = mm.cargar_metricas_anidadas(cfg)
    if met is None:
        ui.vacio("Sin métricas de modelos", "Se esperaba Modelos/06_Validacion_anidada/resultados/metricas_anidadas.csv. Puede importar una tabla abajo.")
    izq, der = st.columns([1.1, 2.9], gap="small")
    with izq:
        ui.panel("Metadatos de la validación", "info", "configuracion_anidada.json")
        cfa = mm.cargar_config_anidada(cfg)
        icon_meta = {"Conjunto de prueba": ("capas", "azul"), "Zona de exclusión": ("pin", "coral"), "Réplicas bootstrap (IC95)": ("grafico", "teal"), "Semilla": ("db", "gris"), "Variable objetivo": ("trend", "ambar"), "Método de referencia": ("regla", "azul"), "Modelo principal predeclarado": ("cerebro", "coral"), "Unidades": ("info", "gris")}
        for k, v in mm.metadatos_evaluacion(cfa).items():
            ic, tono = icon_meta.get(k, ("info", "gris"))
            ui.kpi(k, v if v not in (None, "") else None, ic=ic, tono=tono)
        ui.nota("Métricas de pronóstico del cambio de tasa (Δ) y de la tasa reconstruida, fuera de bloque. Los modelos de extracción de línea de costa (CoastSat frente a línea manual) se evalúan en la pestaña «Extracción».")
        ui.panel("Importar tabla de métricas", "descarga", "CSV o Excel con columna 'modelo'")
        arch = st.file_uploader("CSV/XLSX con columna 'modelo'", type=["csv", "xlsx"], key="eval_upload")
        tabla_ext = None
        if arch is not None:
            try:
                tabla_ext = mm.importar_tabla_metricas(arch.getvalue(), arch.name)
                st.success(f"{len(tabla_ext)} filas importadas (no se guardan en disco).")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))

    with der:
        tabs = st.tabs(["Comparación de modelos", "Comparación pareada", "Por bloque", "Cobertura conformal", "Extracción (CoastSat)", "Tabla importada", "Tablas de la tesis e histórico"])
        with tabs[0]:
            if met is not None:
                opciones = {k: v for k, v in mm.METRICAS.items() if k in met.columns}
                metrica = st.selectbox("Métrica", list(opciones), key="eval_metrica", format_func=lambda k: f"{opciones[k][0]} [{opciones[k][1]}]")
                inf, sup = (("habilidad_IC95_inf", "habilidad_IC95_sup") if metrica == "habilidad_vs_persistencia" else (None, None))
                ui.grafico(graficos.metricas_modelos(met, metrica, f"{opciones[metrica][0]} ({opciones[metrica][1]})", inf, sup))
                ui.nota(opciones[metrica][2] or "")
                cols = ["nombre", "n"] + [c for c in ("habilidad_vs_persistencia", "habilidad_IC95_inf", "habilidad_IC95_sup", "P_habilidad_menor_o_igual_0", "RMSE_Delta", "MAE_Delta", "R2_Delta", "rho_Delta", "RMSE_tasa", "MAE_tasa", "R2_tasa_2005_2026", "coincidencia_clase_cambio_pct", "coincidencia_clase_IVC_2026_pct") if c in met.columns]
                ui.tabla(met[cols].rename(columns={"habilidad_vs_persistencia": "R2_OS", "habilidad_IC95_inf": "R2_OS IC95 inf", "habilidad_IC95_sup": "R2_OS IC95 sup", "P_habilidad_menor_o_igual_0": "P(R2_OS ≤ 0)"}).round(3), hide_index=True, use_container_width=True, height=420)
                ui.nota("Según LEEME_version4.txt no se elige un modelo principal: las comparaciones deben leerse con su IC95 y con la comparación pareada. La columna 'habilidad' del CSV equivale a R²_OS.")
                prom = CAPAS["metricas_anidadas"].ruta(cfg).parent / "promedios_sin_fuga_temporal.csv"
                if prom.exists():
                    with st.expander("Promedios post hoc sin fuga temporal"):
                        ui.tabla(pd.read_csv(prom).round(3), hide_index=True, use_container_width=True)
        with tabs[1]:
            comp = mm.cargar_comparacion(cfg)
            if comp is not None:
                ref = st.selectbox("Referencia", sorted(comp["referencia"].unique()), key="eval_ref")
                d = comp[comp["referencia"] == ref].copy()
                d["nombre"] = d["modelo"].map(mm.NOMBRES_MODELOS).fillna(d["modelo"])
                import plotly.graph_objects as go

                fig = go.Figure(go.Bar(x=d["nombre"], y=d["dR2"], error_y=dict(type="data", symmetric=False, array=(d["dR2_IC95_sup"] - d["dR2"]).clip(lower=0), arrayminus=(d["dR2"] - d["dR2_IC95_inf"]).clip(lower=0)),
                                       marker_color=["#4ade80" if p <= 0.05 else "#3fa7d6" for p in d["P_dR2_menor_o_igual_0"]]))
                fig.add_hline(y=0, line_color="rgba(255,255,255,.5)")
                fig.update_layout(yaxis_title=f"ΔR² frente a {ref}", xaxis_tickangle=-30)
                ui.grafico(graficos._estilo(fig, f"Diferencia de R² frente a «{ref}» con IC95 (verde: P(ΔR² ≤ 0) ≤ 0,05)", 380))
                ui.tabla(d.drop(columns="nombre").round(3), hide_index=True, use_container_width=True)
            else:
                ui.vacio("Sin comparación pareada")
        with tabs[2]:
            mb = mm.cargar_mse_bloque(cfg)
            bl = mm.cargar_bloques(cfg)
            if mb is not None:
                ui.tabla(mb.round(3), hide_index=True, use_container_width=True, height=360)
                num = [c for c in mb.columns if pd.api.types.is_numeric_dtype(mb[c]) and c != "bloque"]
                if "bloque" in mb.columns and num:
                    import plotly.express as px

                    sel = st.multiselect("Modelos", num, default=num[:4], key="eval_bl_sel")
                    if sel:
                        fig = px.line(mb, x="bloque", y=sel, markers=True)
                        ui.grafico(graficos._estilo(fig, "MSE por bloque espacial", 320))
            if bl is not None:
                with st.expander("Bloques espaciales (km y LRR medio)"):
                    ui.tabla(bl.round(3), hide_index=True, use_container_width=True)
            if mb is None and bl is None:
                ui.vacio("Sin resultados por bloque")
        with tabs[3]:
            cf = mm.cargar_conformal(cfg)
            if cf is not None:
                d = cf.copy()
                d["nombre"] = d["modelo"].map(mm.NOMBRES_MODELOS).fillna(d["modelo"])
                import plotly.express as px

                fig = px.bar(d, x="nombre", y="cobertura_global", color=d["nivel_nominal"].astype(str), barmode="group", labels={"color": "Nivel nominal"})
                for nv in sorted(d["nivel_nominal"].unique()):
                    fig.add_hline(y=nv, line_dash="dot", line_color="rgba(255,255,255,.4)")
                fig.update_layout(yaxis_title="Cobertura observada", xaxis_tickangle=-30, yaxis_range=[0.5, 1.02])
                ui.grafico(graficos._estilo(fig, "Cobertura de los intervalos conformales (líneas punteadas = nivel nominal)", 360))
                ui.tabla(d.drop(columns="nombre").round(3), hide_index=True, use_container_width=True)
                ui.nota("'ancho_medio' en m/año: anchura media del intervalo de predicción.")
            else:
                ui.vacio("Sin cobertura conformal")
        with tabs[4]:
            vc = mm.cargar_validacion_coastsat(cfg)
            if vc is not None:
                st.markdown("**CoastSat frente a línea manual 2026** — postproceso/validacion_coastsat_vs_manual_2026.csv")
                ui.tabla(vc.head(300), use_container_width=True, height=300)
                num = vc.select_dtypes("number")
                if not num.empty:
                    ui.tabla(num.describe().T.round(3), use_container_width=True)
                    col_err = [c for c in num.columns if "dist" in c.lower() or "err" in c.lower() or "desv" in c.lower()]
                    if col_err:
                        c = st.selectbox("Columna de error / desplazamiento", col_err, key="eval_vc_col")
                        ui.grafico(graficos.histograma(num[c], c, "m"))
                ui.nota("Métrica de extracción: desplazamiento entre la línea CoastSat y una línea de referencia digitalizada manualmente (misma fecha). Unidades en metros.")
            else:
                ui.vacio("Sin validación de extracción", "No se encontró validacion_coastsat_vs_manual_2026.csv. No hay resultados de U‑Net, Random Forest de segmentación ni CNN de extracción en los archivos; esta sección los admitirá cuando existan (tabla con columna 'modelo').")
        with tabs[5]:
            if tabla_ext is not None:
                ui.tabla(tabla_ext, use_container_width=True)
                num = [c for c in tabla_ext.columns if pd.api.types.is_numeric_dtype(tabla_ext[c])]
                if num:
                    c = st.selectbox("Métrica a graficar", num, key="eval_ext_col")
                    import plotly.express as px

                    colm = [x for x in tabla_ext.columns if x.lower() == "modelo"][0]
                    fig = px.bar(tabla_ext, x=colm, y=c)
                    ui.grafico(graficos._estilo(fig, f"{c} (tabla importada)", 320))
                ui.nota("Verifique que las métricas importadas correspondan al mismo conjunto de prueba, periodo y unidades antes de compararlas con las de la tesis.")
            else:
                ui.vacio("Ninguna tabla importada")
        with tabs[6]:
            for clave in ("tablas_10_r2os", "tablas_09_topsis"):
                c = CAPAS[clave]
                if c.disponible(cfg):
                    r = c.ruta(cfg)
                    from datetime import datetime

                    with open(r, "rb") as f:
                        st.download_button(f"⬇ {c.titulo} ({datetime.fromtimestamp(r.stat().st_mtime):%d‑%m‑%Y})", f.read(), file_name=r.name,
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_{clave}")
            ui.nota("Tablas 10 (R²_OS): misma versión v4 de la validación anidada; desde el 20‑10‑2026 la «habilidad frente a persistencia» se denomina R²_OS (Campbell y Thompson, 2008) en tablas y figuras.")
            st.markdown("---")
            p = CAPAS["tabla_r2_v2"].ruta(cfg)
            if p.exists():
                ui.tabla(pd.read_csv(p), hide_index=True, use_container_width=True)
                ui.nota("Versión 2 (04‑10‑2026): NO vigente; se conserva como historial (ver Modelos/LEEME.txt).")
            else:
                ui.vacio("Sin tabla histórica v2")
