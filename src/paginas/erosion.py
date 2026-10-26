"""Sección 3 — Línea de costa y erosión: resultados DSAS existentes, tasas del script y métricas del geovisor."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import dsas, graficos, mapas, temporal, vectores
from ..catalogo_datos import CAPAS
from ..vectores import CapaNoDisponible
from . import comunes as ui
from .visor import _bounds_datos, _geojson_capa, _lineas_fecha


@st.cache_data(ttl=3600, show_spinner=False)
def _tasas(_v: int):
    from .visor import _cfg

    cfg = _cfg()
    g = dsas.cargar_tasas_dsas(cfg)
    return dsas.unir_distancia_km(g, cfg)


def render(cfg: dict) -> None:
    ui.seccion("Línea de costa y erosión", "regla", "tasas de cambio DSAS v6.1 y métricas de las líneas de costa")
    try:
        g = _lineas_fecha(0)
        obs = temporal.observaciones(g)
    except CapaNoDisponible:
        g, obs = None, []
    hay_dsas = CAPAS["dsas_tasas"].disponible(cfg)

    # --- Resumen del conjunto de líneas (métricas del geovisor) -----------------
    c = st.columns(5)
    with c[0]:
        ui.kpi("Épocas con línea (DSAS)", len(obs) if obs else None, "", "Líneas anuales usadas en DSAS (lineas_anuales_dsas.shp)", procedencia="geovisor", ic="calendario", tono="azul")
    with c[1]:
        ui.kpi("Entidades (líneas)", int(len(g)) if g is not None else None, "", "Una por fecha y lado", ic="lineas", tono="teal")
    with c[2]:
        ui.kpi("Primera observación", f"{obs[0].fecha:%Y-%m-%d}" if obs else None, ic="satelite", tono="gris")
    with c[3]:
        ui.kpi("Última observación", f"{obs[-1].fecha:%Y-%m-%d}" if obs else None, ic="satelite", tono="ambar")
    with c[4]:
        try:
            an = temporal.cargar_lineas_anuales(cfg)
            ui.kpi("Épocas anuales (DSAS)", int(an["epoca"].nunique()), "", "Líneas anuales corregidas por marea usadas en DSAS", ic="capas", tono="coral")
        except CapaNoDisponible:
            ui.kpi("Épocas anuales (DSAS)", None, ic="capas")

    if not hay_dsas:
        ui.vacio("Resultados DSAS no disponibles", "Se esperaba `exportar_coastsat/dsas/dsas_tasas.shp`. Mientras tanto puede explorar las líneas de costa en el visor.")
        return

    t = _tasas(0)
    informe = dsas.leer_informe_dsas(cfg)
    izq, der = st.columns([1.1, 2.9], gap="small")
    with izq:
        ui.panel("Indicador", "trend", "tasas y distancias de DSAS")
        campo = st.selectbox("Tasa / distancia", list(dsas.CAMPOS_TASAS), format_func=lambda k: dsas.CAMPOS_TASAS[k][0], key="ero_campo")
        unidad = dsas.CAMPOS_TASAS[campo][1]
        ui.nota(dsas.DESCRIPCION_METRICAS[campo])
        st.markdown(f'<span class="gv-proc dsas">DSAS {informe.get("version", "v6.1") if informe else "v6.1"}</span> valores importados de dsas_tasas.shp; el geovisor no los recalcula.', unsafe_allow_html=True)
        r = dsas.resumen_tasas(t, campo)
        perfil = pd.to_numeric(t.sort_values("dist_costa_km" if "dist_costa_km" in t.columns else "TransOrder")[campo], errors="coerce").tolist()
        ui.kpi(f"{campo} medio", r.get("media"), unidad, "Media de los transectos; mini‑gráfico: perfil a lo largo de la costa", 2, "DSAS", ic="trend_down" if (r.get("media") or 0) < 0 else "trend", tono="coral" if (r.get("media") or 0) < 0 else "teal", serie=perfil[::6])
        ui.kpi(f"{campo} mediano", r.get("mediana"), unidad, "", 2, "DSAS", ic="grafico", tono="azul")
        ui.kpi("Mínimo (máximo retroceso)", r.get("min"), unidad, "", 2, "DSAS", ic="trend_down", tono="coral")
        ui.kpi("Máximo (máximo avance)", r.get("max"), unidad, "", 2, "DSAS", ic="trend", tono="teal")
        if campo != "SCE":
            ui.kpi("Transectos en retroceso", f"{r.get('n_erosion')} ({r.get('pct_erosion', 0):.1f} %)", "", "valor < 0", ic="alerta", tono="coral", progreso=r.get("pct_erosion", 0) / 100)
            ui.kpi("Transectos en avance", f"{r.get('n_acrecion')} ({r.get('pct_acrecion', 0):.1f} %)", "", "valor > 0", ic="check", tono="teal", progreso=r.get("pct_acrecion", 0) / 100)
        if informe and informe.get(f"media_{campo}") is not None:
            ui.kpi(f"{campo} medio (informe DSAS)", informe[f"media_{campo}"], unidad, "Valor del informe oficial DSAS_summary_report", 2, "DSAS", ic="db", tono="gris")
        ui.kpi("Transectos", int(len(t)), "", "Espaciado 100 m", ic="capas", tono="azul")
        if informe:
            ui.kpi("Líneas usadas", informe.get("n_fechas"), "épocas", informe.get("fechas", ""), ic="calendario", tono="ambar")
        mostrar_script = st.checkbox("Comparar con tasas del script (100 m)", value=False, key="ero_script", disabled=not CAPAS["tasas_script_100m"].disponible(cfg))

    with der:
        tabs = st.tabs(["Mapa", "Perfil a lo largo de la costa", "Distribución", "Sectores críticos", "Tabla y descarga", "Informe DSAS", "Script vs DSAS"])
        with tabs[0]:
            m = mapas.crear_mapa(cfg, bounds=_bounds_datos(0) if g is not None else None)
            gj = _geojson_capa("dsas_tasas", 0, ("TransOrder", "BaselineID", "ShrCount", "LRR", "LCI95", "LR2", "EPR", "EPRUNC", "NSM", "SCE", "WLR", "WCI"))
            vals = [f["properties"].get(campo) for f in gj["features"] if f["properties"].get(campo) is not None]
            if campo == "SCE":
                import branca.colormap as cm

                rampa = cm.LinearColormap(["#f7fbff", "#6baed6", "#08306b"], vmin=min(vals), vmax=max(vals), caption=f"SCE ({unidad})")
            else:
                rampa = mapas.rampa_divergente(min(vals), max(vals), f"{campo} ({unidad}) — rojo: retroceso, azul: avance")
            sin = cfg["visualizacion"]["colores"]["sin_dato"]
            mapas.agregar_geojson(m, gj, f"{campo} por transecto", grosor=3.5, opacidad=0.95, campos_tooltip=["TransOrder", campo],
                                  campos_popup=["TransOrder", "BaselineID", "ShrCount", "LRR", "LCI95", "LR2", "EPR", "EPRUNC", "NSM", "SCE", "WLR", "WCI"],
                                  alias={"TransOrder": "Transecto", "BaselineID": "Línea base", "ShrCount": "N.º líneas", "LRR": "LRR (m/año)", "LCI95": "IC95 LRR", "LR2": "R² LRR", "EPR": "EPR (m/año)", "EPRUNC": "Incert. EPR", "NSM": "NSM (m)", "SCE": "SCE (m)", "WLR": "WLR (m/año)", "WCI": "IC95 WLR"},
                                  funcion_estilo=lambda f, r=rampa, c=campo, s=sin: {"color": r(f["properties"][c]) if f["properties"].get(c) is not None else s})
            mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption), "bottomleft")
            if CAPAS["linea_base"].disponible(cfg):
                mapas.agregar_geojson(m, _geojson_capa("linea_base", 0, ("ID", "lado")), "Línea base", color="#ffffff", grosor=1, dash="2 6")
            if CAPAS["lineas_anuales"].disponible(cfg):
                gja = _geojson_capa("lineas_anuales", cfg["visualizacion"]["simplificacion_m"]["lineas_anuales"], ("epoca", "lado"))
                mapas.agregar_geojson(m, gja, "Líneas anuales (insumo DSAS)", color="#3fa7d6", grosor=0.8, opacidad=0.5, mostrar=False, campos_tooltip=["epoca"])
            if mostrar_script:
                gjs = _geojson_capa("tasas_script_100m", 0, ("id", "lado", "dist_km", "n_lineas", "LRR", "EPR", "NSM", "SCE", "WLR"))
                mapas.agregar_geojson(m, gjs, f"{campo} script (100 m)", grosor=1.5, opacidad=0.8, dash="3 3", campos_tooltip=["id", campo],
                                      funcion_estilo=lambda f, r=rampa, c=campo, s=sin: {"color": r(f["properties"][c]) if f["properties"].get(c) is not None else s})
            mapas.finalizar(m)
            ui.mostrar_mapa(m, 560, "mapa_ero")
        with tabs[1]:
            ci = {"LRR": "LCI95", "WLR": "WCI", "EPR": "EPRUNC"}.get(campo)
            x = "dist_costa_km" if "dist_costa_km" in t.columns else "TransOrder"
            ui.grafico(graficos.tasa_por_transecto(pd.DataFrame(t.drop(columns="geometry")), campo, unidad, x=x, ci=ci))
            ui.nota("Banda = intervalo de confianza del 95 % calculado por DSAS (LCI95/WCI) o incertidumbre del EPR (EPRUNC).")
            if mostrar_script and CAPAS["tasas_script_100m"].disponible(cfg):
                ts = dsas.cargar_tasas_script(cfg)
                ui.grafico(graficos.tasa_por_transecto(pd.DataFrame(ts.drop(columns="geometry")), campo, unidad, x="dist_km"))
                st.markdown('<span class="gv-proc script">script</span> tasas recalculadas por el postproceso sobre posiciones corregidas por marea (transectos de 100 m del script, 712).', unsafe_allow_html=True)
        with tabs[2]:
            cA, cB = st.columns([2, 1])
            ui.grafico_en(cA, graficos.histograma(pd.to_numeric(t[campo], errors="coerce"), campo, unidad, cortes=[0] if campo != "SCE" else None))
            if campo != "SCE":
                from ..estilos import CORAL, TEAL

                ui.grafico_en(cB, graficos.donut(["Retroceso", "Avance"], [r.get("pct_erosion", 0), r.get("pct_acrecion", 0)], [CORAL, TEAL], "Transectos por sentido", f"{r.get('pct_erosion', 0):.0f} %<br><span style='font-size:11px'>retroceso</span>"))
            if "ShrCount" in t:
                ui.grafico(graficos.histograma(pd.to_numeric(t["ShrCount"], errors="coerce"), "N.º de líneas por transecto (ShrCount)", "líneas", nbins=20, color="#19B3A6"))
        with tabs[3]:
            n = st.slider("N.º de transectos", 5, 40, 15, key="ero_n")
            if campo != "SCE":
                st.markdown(f"**Mayor retroceso** ({campo} más negativo)")
                ui.tabla(dsas.sectores_criticos(t, campo, n), use_container_width=True, hide_index=True)
                st.markdown(f"**Mayor avance** ({campo} más positivo)")
                d = pd.DataFrame(t.drop(columns="geometry"))
                d[campo] = pd.to_numeric(d[campo], errors="coerce")
                cols = [c for c in ("id_transecto", "dist_costa_km", "zona", campo, "LCI95", "EPR", "NSM", "ShrCount") if c in d.columns]
                ui.tabla(d.nlargest(n, campo)[cols], use_container_width=True, hide_index=True)
            else:
                d = pd.DataFrame(t.drop(columns="geometry"))
                cols = [c for c in ("id_transecto", "dist_costa_km", "zona", "SCE", "NSM", "ShrCount") if c in d.columns]
                ui.tabla(d.nlargest(n, "SCE")[cols], use_container_width=True, hide_index=True)
        with tabs[4]:
            ui.tabla_atributos(t)
            ui.descargas(t, "tasas_dsas_transectos", cfg, "ero_exp")
        with tabs[5]:
            if informe:
                st.code(informe["texto"], language=None)
            else:
                ui.vacio("Informe DSAS no encontrado")
        with tabs[6]:
            comp = dsas.comparacion_script_dsas(cfg)
            if comp is None:
                ui.vacio("Sin tabla de comparación", "Se esperaba dsas/comparacion_script_vs_dsas.csv")
            else:
                ui.tabla(comp, use_container_width=True, hide_index=True, height=360)
                num = comp.select_dtypes("number")
                if not num.empty:
                    ui.tabla(num.describe().T, use_container_width=True)
                ui.nota("Diferencias entre las tasas del script de postproceso y las de DSAS para los mismos transectos; sirve para verificar la implementación, no para elegir un valor «mejor».")
