"""Sección 4 — Índice de Vulnerabilidad Costera: versiones calculadas, componentes, clases y comparación temporal."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import graficos, ivc as mod_ivc, mapas, rasteres, vectores
from ..catalogo_datos import CAPAS
from ..vectores import CapaNoDisponible
from . import comunes as ui
from .visor import _bounds_datos, _franjas_ivc, _geojson_capa


@st.cache_data(ttl=3600, show_spinner=False)
def _transectos(_v: int):
    from .visor import _cfg

    return mod_ivc.cargar_transectos_ivc(_cfg())


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_transectos(col_ivc: str, col_cl: str | None, col_inf: str | None, col_sup: str | None) -> dict:
    from .visor import _cfg

    cfg = _cfg()
    g = _transectos(0)
    cols = ["id_ivc", "dist_costa_km", "zona", col_ivc] + [c for c in (col_cl, col_inf, col_sup) if c]
    gs = g[cols + ["geometry"]].rename(columns={col_ivc: "ivc", col_cl: "clase", col_inf: "ivc_inf", col_sup: "ivc_sup"})
    if "clase" not in gs:
        gs["clase"] = mod_ivc.clasificar(gs["ivc"], cfg)
    return vectores.a_geojson(gs, cfg, [c for c in ("id_ivc", "dist_costa_km", "zona", "ivc", "clase", "ivc_inf", "ivc_sup") if c in gs.columns])


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_variable(var: str, estado: str = "2026") -> dict | None:
    from .visor import _cfg

    cfg = _cfg()
    g = mod_ivc.transectos_con_variables(cfg, estado)
    if g is None or var not in g.columns:
        return None
    return vectores.a_geojson(g[["id_ivc", "dist_costa_km", "zona", var, "geometry"]].rename(columns={var: "clase"}), cfg, ["id_ivc", "dist_costa_km", "zona", "clase"])


def render(cfg: dict) -> None:
    ui.seccion("Índice de Vulnerabilidad Costera", "escudo", "16 versiones del IVC, componentes por variable y clasificación documentada")
    if not CAPAS["ivc_transectos"].disponible(cfg):
        ui.vacio("IVC no disponible todavía", mod_ivc.requisitos_para_activar().replace("\n", "<br>"))
        return
    t = _transectos(0)
    vers = mod_ivc.versiones(cfg)
    clases_cfg = cfg["ivc"]["clases"]

    izq, der = st.columns([1.1, 2.9], gap="small")
    with izq:
        ui.panel("Qué representar", "capas", "índice total o una variable")
        tipo = st.radio("Tipo", ["IVC total (por versión)", "Componente (variable, clase 1‑5)"], label_visibility="collapsed", key="ivc_tipo")
        if tipo.startswith("IVC"):
            grupos = {g: [v for v in vs if mod_ivc.columnas_version(t, v)[0]] for g, vs in mod_ivc.GRUPOS_VERSIONES.items()}
            grupo = st.selectbox("Grupo", [g for g in grupos if grupos[g]], key="ivc_grupo")
            version = st.selectbox("Versión / fecha", grupos[grupo], key=f"ivc_version_{grupo}", format_func=lambda v: mod_ivc.titulo_version(cfg, v))
            col_ivc, col_cl = mod_ivc.columnas_version(t, version)
            col_inf, col_sup = mod_ivc.columnas_incertidumbre(t, version)
            variable = None
        else:
            variable = st.selectbox("Variable", list(mod_ivc.DIMENSIONES_VARIABLES), key="ivc_variable", format_func=lambda v: f"{mod_ivc.DIMENSIONES_VARIABLES[v][0]} · {mod_ivc.DIMENSIONES_VARIABLES[v][1]}")
            opc_estado = ["2026"] + (["2005"] if CAPAS["ivc_clases_2005"].disponible(cfg) else [])
            estado_var = st.radio("Estado de las clases", opc_estado, horizontal=True, key="ivc_estado_var", format_func=lambda e: "2026 (observado)" if e == "2026" else "2005 (reconstruido)",
                                  help="2005: variables de posición medidas desde la línea DSAS de 2005 (Mapas_IVC/clases_2005_reconstruidas.csv)")
            version, col_ivc, col_cl, col_inf, col_sup = None, None, None, None, None
        capa_mapa = st.radio("Capa en el mapa", ["Transectos coloreados", "Franjas 0‑500 m", "Mapa de calor (ráster)", "Ráster de valor (1‑5)"], key="ivc_capa")
        ui.panel("Clasificación", "info", "método y umbrales declarados")
        cortes = cfg["ivc"]["cortes"]
        st.markdown(
            f"<div class='gv-nota'>Método: <b>{cfg['ivc']['metodo_clasificacion']}</b> sobre la escala 0‑1 ((IVC−1)/4). "
            f"Cortes: {' · '.join(str(c) for c in cortes)} (equivalen a {' · '.join(str(c) for c in cfg['ivc']['cortes_1_5'])} en 1‑5). "
            f"Fuente: Mapas_IVC/LEEME_mapas.txt. Los valores y clases se leen del archivo de resultados; el geovisor no recalcula el índice.</div>",
            unsafe_allow_html=True,
        )
        if col_ivc:
            est = mod_ivc.estadisticas(t, col_ivc, col_cl, cfg)
            perfil = pd.to_numeric(t.sort_values("dist_costa_km")[col_ivc], errors="coerce").tolist()
            ui.kpi("Transectos con dato", est["n"], "", f"{est['n_sin_dato']} sin dato", procedencia="modelo" if "2026" in version and version not in ("ewm_2026",) else None, ic="capas", tono="azul")
            ui.kpi("IVC medio", est["media"], "0‑1", "mini‑gráfico: perfil a lo largo de la costa", 3, ic="escudo", tono="coral", serie=perfil[::6], progreso=est["media"])
            ui.kpi("Mediana", est["mediana"], "0‑1", "", 3, ic="grafico", tono="teal")
            ui.kpi("Mín – máx", f"{est['min']:.3f} – {est['max']:.3f}", ic="regla", tono="gris")
            ui.kpi("Clase alta + muy alta", est.get("pct_alta_muy_alta"), "% transectos", "", 1, ic="alerta", tono="ambar", progreso=(est.get("pct_alta_muy_alta") or 0) / 100)
            if est.get("km_por_clase"):
                ui.kpi("Costa en clase alta/muy alta", est["km_por_clase"].get(4, 0) + est["km_por_clase"].get(5, 0), "km", "transectos × 0,1 km", 1, ic="pin", tono="coral")

    with der:
        tabs = st.tabs(["Mapa", "Perfil", "Distribución", "Comparación temporal", "Sectores altos", "Pesos y validación", "Mapas de la tesis", "Tabla y descarga"])
        with tabs[0]:
            m = mapas.crear_mapa(cfg, bounds=_bounds_datos(0) if CAPAS["lineas_fecha"].disponible(cfg) else None)
            sin = cfg["visualizacion"]["colores"]["sin_dato"]

            def color_clase(f):
                c = f["properties"].get("clase")
                try:
                    return {"color": clases_cfg[int(round(float(c)))]["color"], "fillColor": clases_cfg[int(round(float(c)))]["color"]} if c is not None else {"color": sin, "fillColor": sin}
                except (KeyError, ValueError):
                    return {"color": sin, "fillColor": sin}

            if variable:
                gj = _geojson_variable(variable, st.session_state.get("ivc_estado_var", "2026"))
                if gj:
                    mapas.agregar_geojson(m, gj, mod_ivc.DIMENSIONES_VARIABLES[variable][0], grosor=3.5, campos_tooltip=["id_ivc", "clase"], campos_popup=["id_ivc", "dist_costa_km", "zona", "clase"],
                                          alias={"id_ivc": "Transecto", "dist_costa_km": "km", "clase": "Clase 1‑5"}, funcion_estilo=color_clase)
                    mapas.agregar_leyenda_html(m, "<b>Clase de la variable (1‑5)</b><br>" + "<br>".join(f'<span style="color:{clases_cfg[k]["color"]}">■</span> {k} · {clases_cfg[k]["nombre"]}' for k in sorted(clases_cfg)))
                else:
                    ui.vacio("Variable no disponible", "Falta exportar_coastsat/ivc/tabla_clases_1_5_ivc.csv")
            elif capa_mapa == "Transectos coloreados":
                gj = _geojson_transectos(col_ivc, col_cl, col_inf, col_sup)
                mapas.agregar_geojson(m, gj, mod_ivc.titulo_version(cfg, version), grosor=3.5, campos_tooltip=["id_ivc", "ivc", "clase"],
                                      campos_popup=[c for c in ("id_ivc", "dist_costa_km", "zona", "ivc", "clase", "ivc_inf", "ivc_sup") if gj["features"] and c in gj["features"][0]["properties"]],
                                      alias={"id_ivc": "Transecto", "dist_costa_km": "km desde Bocas de Ceniza", "ivc": "IVC (0‑1)", "clase": "Clase", "ivc_inf": "IVC inf", "ivc_sup": "IVC sup"}, funcion_estilo=color_clase)
                mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg))
            elif capa_mapa == "Franjas 0‑500 m":
                gj, _ = _franjas_ivc(version)
                if gj:
                    mapas.agregar_geojson(m, gj, "Franjas por clase", grosor=0.4, opacidad_relleno=0.6, relleno="#999", campos_tooltip=["id_ivc", "ivc", "clase"], funcion_estilo=color_clase)
                    mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg))
                else:
                    ui.vacio("Franjas no disponibles")
            else:
                calor, valor = mod_ivc.rasters_version(cfg, version)
                if capa_mapa.startswith("Mapa de calor") and calor:
                    s = rasteres.superponer_rgba(cfg, calor)
                    mapas.agregar_superposicion(m, s, f"Mapa de calor — {mod_ivc.titulo_version(cfg, version)}", opacidad=cfg["visualizacion"]["opacidad"]["raster_ivc"])
                    mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, "IVC (franja 1,5 km, suavizado 150 m solo para el dibujo)"))
                elif valor:
                    colores = [clases_cfg[k]["color"] for k in sorted(clases_cfg)]
                    s, est_r = rasteres.superponer_valor(cfg, valor, cortes=cfg["ivc"]["cortes_1_5"], colores=colores)
                    mapas.agregar_superposicion(m, s, f"Valor (1‑5) — {mod_ivc.titulo_version(cfg, version)}", opacidad=cfg["visualizacion"]["opacidad"]["raster_ivc"])
                    mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, "IVC valor 1‑5 (cortes 1,8 / 2,6 / 3,4 / 4,2)"))
                    ui.nota(f"Ráster de valor: mín {est_r['min']:.2f}, máx {est_r['max']:.2f}, media {est_r['media']:.2f} (celdas válidas {est_r['n_valid']})")
                else:
                    ui.vacio("Ráster no disponible para esta versión")
            if CAPAS["ruta90"].disponible(cfg):
                mapas.agregar_geojson(m, _geojson_capa("ruta90", 0, None), "Ruta 90", color=cfg["visualizacion"]["colores"]["ruta90"], grosor=2, mostrar=False)
            mapas.finalizar(m)
            ui.mostrar_mapa(m, 560, "mapa_ivc")
        with tabs[1]:
            if col_ivc:
                ui.grafico(graficos.ivc_por_km(pd.DataFrame(t.drop(columns="geometry")), col_ivc, cfg, col_inf, col_sup, f"{mod_ivc.titulo_version(cfg, version)} a lo largo de la costa"))
                if col_inf:
                    ui.nota("La banda inf–sup proviene de los percentiles de la proyección (ver Predicciones y escenarios).")
            elif variable:
                gv = mod_ivc.transectos_con_variables(cfg)
                if gv is not None:
                    d = pd.DataFrame(gv.drop(columns="geometry")).sort_values("dist_costa_km")
                    import plotly.graph_objects as go

                    fig = go.Figure(go.Bar(x=d["dist_costa_km"], y=d[variable], marker_color=[clases_cfg.get(int(v), {"color": "#999"})["color"] if pd.notna(v) else "#999" for v in d[variable].round()], width=0.1))
                    fig.update_layout(xaxis_title="km desde Bocas de Ceniza", yaxis_title="Clase (1‑5)", yaxis_range=[0, 5.5])
                    ui.grafico(graficos._estilo(fig, f"{mod_ivc.DIMENSIONES_VARIABLES[variable][0]} — clase por transecto", 300))
        with tabs[2]:
            if col_ivc:
                est = mod_ivc.estadisticas(t, col_ivc, col_cl, cfg)
                c1, c2, c3 = st.columns([1.3, 1, 1])
                ui.grafico_en(c1, graficos.histograma(pd.to_numeric(t[col_ivc], errors="coerce"), "IVC", "0‑1", nbins=30, cortes=cfg["ivc"]["cortes"]))
                if est.get("pct_clases"):
                    ui.grafico_en(c2, graficos.barras_clases(est["pct_clases"], cfg))
                    ks = sorted(est["pct_clases"])
                    ui.grafico_en(c3, graficos.donut([f"{k} · {clases_cfg[k]['nombre']}" for k in ks], [est["pct_clases"][k] for k in ks], [clases_cfg[k]["color"] for k in ks], "Reparto por clase", f"{est['media']:.2f}<br><span style='font-size:11px'>IVC medio</span>"))
                ui.tabla(pd.DataFrame({"estadístico": ["n", "media", "mediana", "desv. típica", "mín", "máx"], "valor": [est["n"], est["media"], est["mediana"], est["desv"], est["min"], est["max"]]}), hide_index=True)
            elif variable:
                cl = mod_ivc.cargar_clases_variables(cfg, st.session_state.get("ivc_estado_var", "2026"))
                if cl is not None and variable in cl:
                    pct = (cl[variable].round().value_counts(normalize=True) * 100).to_dict()
                    ui.grafico(graficos.barras_clases({int(k): float(v) for k, v in pct.items()}, cfg, f"Transectos por clase — {mod_ivc.DIMENSIONES_VARIABLES[variable][0]}"))
        with tabs[3]:
            disp = [v for v in ("ewm_2005", "ewm_2026", "ewm_total", "ssp245_2050", "ssp585_2050", "ssp245_2100", "ssp585_2100") if mod_ivc.columnas_version(t, v)[0]]
            sel = st.multiselect("Versiones/fechas a comparar", disp, default=[v for v in ("ewm_2005", "ewm_2026") if v in disp], key="ivc_cmp", format_func=lambda v: mod_ivc.titulo_version(cfg, v))
            if sel:
                cols = {mod_ivc.titulo_version(cfg, v): mod_ivc.columnas_version(t, v)[0] for v in sel}
                ui.grafico(graficos.comparacion_versiones(pd.DataFrame(t.drop(columns="geometry")), cols))
                filas = []
                for v in sel:
                    ci, cc = mod_ivc.columnas_version(t, v)
                    e = mod_ivc.estadisticas(t, ci, cc, cfg)
                    filas.append({"versión": mod_ivc.titulo_version(cfg, v), "media": e["media"], "mediana": e["mediana"], **{f"% clase {k}": e.get("pct_clases", {}).get(k, 0) for k in range(1, 6)}})
                ui.tabla(pd.DataFrame(filas).round(3), hide_index=True, use_container_width=True)
                conc = mod_ivc.cargar_concordancia(cfg)
                if conc is not None:
                    with st.expander("Concordancia entre versiones (Mapas_IVC/concordancia_versiones.csv)"):
                        ui.tabla(conc, hide_index=True, use_container_width=True)
            _bloque_2005(cfg, t)
        with tabs[4]:
            if col_ivc:
                n = st.slider("N.º de transectos", 5, 50, 15, key="ivc_n")
                ui.tabla(mod_ivc.sectores_altos(t, col_ivc, col_cl, n).round(3), hide_index=True, use_container_width=True)
        with tabs[5]:
            cl = mod_ivc.cargar_clases_variables(cfg)
            if cl is not None and col_cl:
                vars_ = [v for v in mod_ivc.DIMENSIONES_VARIABLES if v in cl.columns]
                etiq = [mod_ivc.DIMENSIONES_VARIABLES[v][0] for v in vars_]
                base = cl.merge(pd.DataFrame(t[["id_ivc", col_cl]]), on="id_ivc", how="left")
                series = {"Todos los transectos (clase media)": [float(base[v].mean()) for v in vars_]}
                altos = base[pd.to_numeric(base[col_cl], errors="coerce") >= 4]
                if len(altos):
                    series[f"Transectos clase alta/muy alta (n={len(altos)})"] = [float(altos[v].mean()) for v in vars_]
                ui.grafico(graficos.radar(etiq, series, f"Perfil de las 15 variables (clase media 1‑5) — {mod_ivc.titulo_version(cfg, version)}", (0, 5), 440))
                ui.nota("Radar calculado por el geovisor a partir de exportar_coastsat/ivc/tabla_clases_1_5_ivc.csv (medias aritméticas de la clase 1‑5 de cada variable).")
            pesos = mod_ivc.cargar_pesos(cfg)
            if pesos is not None:
                st.markdown("**Pesos por entropía (EWM)** — Mapas_IVC/pesos_ewm_ivc.csv")
                p = pesos.copy()
                p["variable_nombre"] = p["variable"].map(lambda v: mod_ivc.DIMENSIONES_VARIABLES.get(v, (v, ""))[0])
                p["dimensión"] = p["variable"].map(lambda v: mod_ivc.DIMENSIONES_VARIABLES.get(v, (v, ""))[1])
                ui.tabla(p[["variable", "variable_nombre", "dimensión", "entropia_e", "divergencia_d", "peso_total", "peso_estructural"]].round(4), hide_index=True, use_container_width=True)
                import plotly.express as px

                fig = px.bar(p.sort_values("peso_total"), x="peso_total", y="variable_nombre", color="dimensión", orientation="h")
                ui.grafico(graficos._estilo(fig, "Peso EWM de cada variable (IVC total)", 380))
            val = mod_ivc.cargar_validacion_indices(cfg)
            if val is not None:
                st.markdown("**Validación contra la tasa DSAS** (ρ de Spearman con IC95) — Multicriterio/validacion_indices_dsas.csv")
                ui.tabla(val.round(3), hide_index=True, use_container_width=True)
            if CAPAS["comparacion_m1_m2_pesos"].disponible(cfg):
                with st.expander("Normalización M1 (clases 1‑5) frente a M2 (difusa 0‑1): pesos y validación (Multicriterio, 18‑10‑2026)"):
                    pm = pd.read_csv(CAPAS["comparacion_m1_m2_pesos"].ruta(cfg), encoding="utf-8-sig")
                    pm["variable"] = pm["variable"].astype(str)
                    import plotly.graph_objects as go

                    fig = go.Figure()
                    fig.add_bar(x=pm["variable"], y=pm["peso_M1"], name="M1 (clases 1‑5)", marker_color="#3B6CF0", error_y=dict(type="data", symmetric=False, array=pm["M1_IC95_sup"] - pm["peso_M1"], arrayminus=pm["peso_M1"] - pm["M1_IC95_inf"], thickness=1))
                    fig.add_bar(x=pm["variable"], y=pm["peso_M2"], name="M2 (difusa 0‑1)", marker_color="#19B3A6", error_y=dict(type="data", symmetric=False, array=pm["M2_IC95_sup"] - pm["peso_M2"], arrayminus=pm["peso_M2"] - pm["M2_IC95_inf"], thickness=1))
                    fig.add_hline(y=float(pm["peso_igual"].iloc[0]), line_dash="dot", line_color="#888", annotation_text="pesos iguales (1/14)", annotation_position="top left", annotation_font=dict(size=10, color="#888"))
                    fig.update_layout(barmode="group", xaxis_tickangle=-35, yaxis_title="Peso EWM")
                    ui.grafico(graficos._estilo(fig, "Pesos EWM con IC95 (bootstrap) según la normalización", 380))
                    if CAPAS["comparacion_m1_m2_validacion"].disponible(cfg):
                        vm = pd.read_csv(CAPAS["comparacion_m1_m2_validacion"].ruta(cfg), encoding="utf-8-sig")
                        ui.tabla(vm.round(3), hide_index=True, use_container_width=True)
                    ui.nota("M1 es la normalización vigente de la tesis; M2 se incluye como análisis de sensibilidad (misma jerarquía de pesos, ρ = 0,91 y κ de quintiles = 0,89 entre ambos IVC).")
            dic = mod_ivc.cargar_diccionario(cfg)
            if dic is not None:
                with st.expander("Diccionario de variables (exportar_coastsat/ivc/diccionario_variables_ivc.csv)"):
                    ui.tabla(dic, hide_index=True, use_container_width=True)
        with tabs[6]:
            _tab_mapas_tesis(cfg, version)
        with tabs[7]:
            if col_ivc:
                cols = ["id_ivc", "BaselineID", "TransOrder", "dist_costa_km", "zona", col_ivc] + [c for c in (col_cl, col_inf, col_sup) if c]
                sub = t[cols + ["geometry"]]
                ui.tabla_atributos(sub)
                ui.descargas(sub, f"ivc_{version}", cfg, "ivc_exp")
            with st.expander("Exportar todas las versiones (671 transectos, todas las columnas)"):
                ui.descargas(t, "ivc_todas_versiones", cfg, "ivc_exp_all")


# ---------------------------------------------------------------------------
# Mapas de la tesis (imágenes generadas por Mapas_IVC/ivc_mapas*.py)
# ---------------------------------------------------------------------------
def _listar_imagenes(carpeta, patron: str) -> list:
    import glob
    from pathlib import Path

    return sorted(Path(x) for x in glob.glob(str(Path(carpeta) / patron)))


def _tab_mapas_tesis(cfg: dict, version: str) -> None:
    """Galería de los mapas individuales del IVC (Mapa_01 … Mapa_18), las figuras de síntesis (26–30) y el Atlas PDF."""
    cap_m, cap_f, cap_a = CAPAS["mapas_individuales_dir"], CAPAS["figuras_ivc_dir"], CAPAS["atlas_ivc_pdf"]
    mapas_png = _listar_imagenes(cap_m.ruta(cfg), "Mapa_*.png") if cap_m.disponible(cfg) else []
    figs_png = _listar_imagenes(cap_f.ruta(cfg), "Figura_*.png") if cap_f.disponible(cfg) else []
    if not mapas_png and not figs_png:
        ui.vacio("Sin mapas de la tesis", "No se encontró Mapas_IVC/mapas_individuales/*.png ni Mapas_IVC/Figura_*.png.")
        return
    import re
    from datetime import datetime

    c1, c2 = st.columns([1.2, 1])
    with c1:
        ui.kpi("Mapas individuales", len(mapas_png) or None, "PNG", "Mapas_IVC/mapas_individuales (uno por versión y escenario)", 0, "importado", ic="mapa", tono="azul")
    with c2:
        ui.kpi("Figuras de síntesis", len(figs_png) or None, "PNG", "Figura_26 … Figura_30 (Mapas_IVC)", 0, "importado", ic="grafico", tono="teal")
    todos = [("Mapa", x) for x in mapas_png] + [("Figura", x) for x in figs_png]
    etiquetas = {str(x): f"{t} · {x.stem.replace('_', ' ')}" for t, x in todos}
    # el mapa de la versión activa se propone por defecto
    pred = next((str(x) for _, x in todos if version and version.replace("esc_", "") in x.stem), str(todos[0][1]))
    sel = st.selectbox("Imagen", list(etiquetas), index=list(etiquetas).index(pred), key="ivc_img", format_func=lambda k: etiquetas[k])
    ruta = next(x for _, x in todos if str(x) == sel)
    st.image(str(ruta), use_container_width=True)
    mt = datetime.fromtimestamp(ruta.stat().st_mtime)
    st.markdown(f'<div class="gv-nota">{ruta.name} · {ruta.stat().st_size / 1e6:.1f} MB · generado {mt:%Y-%m-%d %H:%M} · {cap_m.procedencia if ruta in mapas_png else cap_f.procedencia}</div>', unsafe_allow_html=True)
    with open(ruta, "rb") as f:
        st.download_button("Descargar PNG", f.read(), file_name=ruta.name, mime="image/png", key="ivc_img_dl")
    if cap_a.disponible(cfg):
        ra = cap_a.ruta(cfg)
        with open(ra, "rb") as f:
            st.download_button(f"Descargar Atlas del IVC (PDF, {ra.stat().st_size / 1e6:.1f} MB)", f.read(), file_name=ra.name, mime="application/pdf", key="ivc_atlas_dl")
    with st.expander("Miniaturas de todos los mapas"):
        cols = st.columns(3)
        for i, (t, x) in enumerate(todos):
            with cols[i % 3]:
                st.image(str(x), caption=x.stem.replace("_", " "), use_container_width=True)


def _bloque_2005(cfg: dict, t) -> None:
    """IVC 2005 reconstruido frente a 2026: cifras por transecto y cambio de clase por variable."""
    ci05, cc05 = mod_ivc.columnas_version(t, "ewm_2005")
    ci26, cc26 = mod_ivc.columnas_version(t, "ewm_2026")
    if not ci05 or not ci26:
        return
    st.markdown("**IVC 2005 reconstruido frente a IVC 2026** — Mapas_IVC/ivc_2005_reconstruido.py (22‑10‑2026)")
    x, y = pd.to_numeric(t[ci05], errors="coerce"), pd.to_numeric(t[ci26], errors="coerce")
    k05, k26 = pd.to_numeric(t[cc05], errors="coerce"), pd.to_numeric(t[cc26], errors="coerce")
    ok = x.notna() & y.notna()
    c = st.columns(4)
    with c[0]:
        ui.kpi("IVC medio 2005", float(x[ok].mean()), "0‑1", f"{int(ok.sum())} transectos con línea de 2005", 3, "modelo", ic="escudo", tono="teal")
    with c[1]:
        ui.kpi("IVC medio 2026", float(y[ok].mean()), "0‑1", "mismos transectos", 3, "importado", ic="escudo", tono="coral")
    with c[2]:
        ui.kpi("Clase alta/muy alta", f"{int((k05[ok] >= 4).sum())} → {int((k26[ok] >= 4).sum())}", "transectos", "2005 → 2026", 0, "geovisor", ic="alerta", tono="ambar")
    with c[3]:
        ui.kpi("Coincidencia de clase", float((k05[ok] == k26[ok]).mean() * 100), "%", "Transectos con la misma clase en 2005 y 2026", 1, "geovisor", ic="check", tono="azul")
    cam = mod_ivc.cambio_clases_2005_2026(cfg)
    if cam is not None and len(cam):
        import plotly.graph_objects as go

        cam = cam.sort_values("pct_cambia", ascending=True)
        fig = go.Figure(go.Bar(x=cam["pct_cambia"], y=cam["nombre"], orientation="h",
                               marker_color=["#F2745F" if r else "#B9B7B1" for r in cam["recalculada_desde_2005"]],
                               customdata=cam[["media_2005", "media_2026", "n"]].round(2).values,
                               hovertemplate="<b>%{y}</b><br>%{x:.1f} % de transectos cambia de clase<br>clase media 2005: %{customdata[0]} · 2026: %{customdata[1]} · n=%{customdata[2]}<extra></extra>"))
        fig.update_layout(xaxis_title="% de transectos cuya clase 1‑5 cambia entre 2005 y 2026")
        ui.grafico(graficos._estilo(fig, "Qué variables cambian entre el estado 2005 reconstruido y 2026", 420))
        ui.nota("Coral = variables recalculadas desde la línea de 2005 (tasa LRR 1984‑2005, ancho de la barra, distancia a la Ruta 90, geomorfología, sustrato, uso del suelo); "
                "gris = variables que conservan el valor actual por falta de datos de 2005 (elevación, pendientes, % bajo el nivel del mar, cobertura, área construida, población, oleaje, granulometría). "
                "Pesos EWM fijos del IVC total. Cálculo del geovisor sobre clases_2005_reconstruidas.csv y tabla_clases_1_5_ivc.csv.")
        with st.expander("Tabla por variable"):
            ui.tabla(cam.round(2), hide_index=True, use_container_width=True)
