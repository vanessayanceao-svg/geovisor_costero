"""Sección 5 — Predicciones y escenarios: líneas proyectadas (2050/2100) e IVC futuro (SSP2‑4.5 / SSP5‑8.5)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import graficos, ivc as mod_ivc, mapas, predicciones as mod_pred, rasteres, ruta90 as mod_r90, vectores
from ..catalogo_datos import CAPAS
from ..vectores import CapaNoDisponible
from . import comunes as ui
from .visor import _bounds_datos, _geojson_capa, _geojson_fecha, _lineas_fecha


@st.cache_data(ttl=3600, show_spinner=False)
def _ruta90_geojson(_v: int) -> tuple[dict, dict, dict]:
    """(segmentos de la vía, tramos de costa, resumen) para el mapa de priorización."""
    from .visor import _cfg

    cfg = _cfg()
    d = mod_r90.cargar_priorizacion(cfg)
    seg = mod_r90.segmentos_ruta(cfg, d)
    tr = mod_r90.tramos_costa(cfg, d)
    gj_seg = vectores.a_geojson(vectores.simplificar_para_mapa(seg, cfg, 1.0), cfg, ["prioridad", "tramo", "km_costa", "anio_txt", "dist_costa_m"])
    gj_tr = vectores.a_geojson(vectores.simplificar_para_mapa(tr, cfg, 2.0), cfg, ["prioridad", "tramo", "anio_txt", "dist_min_ruta90_m", "id_ivc"])
    return gj_seg, gj_tr, mod_r90.resumen(d)


def agregar_ruta90_prioridad(m, cfg: dict, m_leyenda=None, grosor: float = 5.0) -> dict | None:
    """Dibuja la Ruta 90 coloreada por prioridad (y la costa por tramo) en un mapa Folium. Devuelve el resumen o None."""
    try:
        gj_seg, gj_tr, res = _ruta90_geojson(0)
    except CapaNoDisponible:
        return None
    alias = {"prioridad": "Prioridad", "tramo": "Tramo de costa", "km_costa": "Km de costa", "anio_txt": "Año de alcance (SSP5‑8.5)", "dist_costa_m": "Distancia a la costa (m)", "dist_min_ruta90_m": "Distancia mínima a la vía (m)", "id_ivc": "Transecto"}
    mapas.agregar_geojson(m, gj_tr, "Tramos de costa (prioridad Ruta 90)", grosor=3.0, opacidad=0.85, campos_tooltip=["tramo", "prioridad", "anio_txt"],
                          campos_popup=["tramo", "prioridad", "anio_txt", "dist_min_ruta90_m", "id_ivc"], alias=alias,
                          funcion_estilo=lambda f: {"color": mod_r90.COLORES.get(f["properties"]["prioridad"], "#999")})
    mapas.agregar_geojson(m, gj_seg, "Ruta 90 por prioridad (v4)", grosor=grosor, opacidad=0.95, campos_tooltip=["prioridad", "tramo", "anio_txt"],
                          campos_popup=["prioridad", "tramo", "km_costa", "anio_txt", "dist_costa_m"], alias=alias,
                          funcion_estilo=lambda f: {"color": mod_r90.COLORES.get(f["properties"]["prioridad"], "#999"), "weight": grosor if not f["properties"]["prioridad"].startswith("Sin") else max(2.0, grosor * 0.45)})
    mapas.agregar_leyenda_html(m_leyenda if m_leyenda is not None else m, "<b>Ruta 90 · prioridad de intervención</b><br>" + "<br>".join(
        f'<span style="display:inline-block;width:26px;border-top:4px solid {c};vertical-align:middle;margin-right:6px"></span>{k}' for k, c in mod_r90.COLORES.items())
        + '<br><span style="font-size:11px;opacity:.75">Año en que la costa proyectada (SSP5‑8.5) alcanza la vía · Multicriterio/priorizacion_ruta90_v4.csv</span>', "bottomright")
    return res


@st.cache_data(ttl=3600, show_spinner=False)
def _lineas(variante: str):
    from .visor import _cfg

    return mod_pred.cargar_lineas(_cfg(), variante)


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_lineas(variante: str, anio: int | None, tipos: tuple) -> dict:
    from .visor import _cfg

    cfg = _cfg()
    g = _lineas(variante)
    sel = g[g["tipo"].isin(tipos)]
    if anio:
        sel = sel[(sel["anio"] == anio) | (sel["tipo"] == "observada")]
    gs = vectores.simplificar_para_mapa(sel, cfg, 2.0)
    return vectores.a_geojson(gs, cfg, ["linea", "tipo", "anio"])


def render(cfg: dict) -> None:
    ui.seccion("Predicciones y escenarios", "cristal", "líneas de costa proyectadas 2050 · 2100 e IVC futuro bajo SSP2‑4.5 y SSP5‑8.5")
    vd = mod_pred.variantes_disponibles(cfg)
    hay_ivc = CAPAS["ivc_transectos"].disponible(cfg)
    if not vd and not hay_ivc:
        ui.vacio("Sin resultados de predicción", mod_pred.requisitos_para_activar().replace("\n", "<br>"))
        return

    izq, der = st.columns([1.1, 2.9], gap="small")
    with izq:
        ui.panel("Proyección de la línea de costa", "lineas", "modelo, horizonte y elementos")
        variante = st.selectbox("Variante del modelo", list(vd), key="pred_variante", format_func=lambda k: vd[k]) if vd else None
        g = _lineas(variante) if variante else None
        procesados = mod_pred.anios_procesados(g) if g is not None else []
        horizontes = mod_pred.estado_horizontes(cfg, procesados)
        st.markdown("<div class='gv-nota'>Horizontes: " + " · ".join(
            f"<b>{h['anio']}</b>" if h["estado"] == "procesado" else f"<span style='opacity:.5'>{h['anio']} (no procesado)</span>" for h in horizontes) + "</div>", unsafe_allow_html=True)
        anio = st.selectbox("Año objetivo", procesados, index=len(procesados) - 1 if procesados else 0, key="pred_anio") if procesados else None
        tipos = st.multiselect("Elementos", list(mod_pred.TIPOS_LINEA), default=["observada", "central", "p05", "p95", "persistencia"], key="pred_tipos", format_func=lambda k: mod_pred.TIPOS_LINEA[k][0])
        comparar_hist = st.checkbox("Mostrar línea histórica 1984 (primera observación)", value=True, key="pred_hist", disabled=not CAPAS["lineas_fecha"].disponible(cfg))
        ui.panel("Escenario del IVC", "escudo", "nivel del mar AR6 + retroceso")
        esc_disp = [e for e in mod_ivc.ESCENARIOS if hay_ivc and mod_ivc.columnas_version(mod_ivc.cargar_transectos_ivc(cfg), e)[0]] if hay_ivc else []
        escenario = st.selectbox("Escenario SSP y año", esc_disp, key="pred_esc", format_func=lambda v: mod_ivc.titulo_version(cfg, v)) if esc_disp else None
        mostrar_ivc = st.checkbox("Mostrar mapa de calor del IVC futuro", value=bool(escenario), key="pred_ivc_show", disabled=not escenario)
        comparar_actual = st.checkbox("Comparar con el IVC actual (ewm_total)", value=True, key="pred_cmp_actual", disabled=not escenario)
        meta = mod_pred.metadatos(cfg, variante) if variante else None
        if meta:
            ui.panel("Metadatos del modelo", "cerebro", "configuracion_proyeccion.json")
            ui.kpi("Modelo", meta.get("modelo"), "", "", procedencia="modelo", ic="cerebro", tono="coral")
            ui.kpi("Réplicas Monte Carlo", meta.get("n_mc"), ic="grafico", tono="azul")
            ui.kpi("Ventanas", " · ".join(f"{a}–{b}" for a, b in meta.get("ventanas", [])) or None, ic="calendario", tono="teal")
            ui.kpi("Pesos del IVC", meta.get("pesos"), ic="escudo", tono="gris")
            ui.kpi("Regla de Bruun", meta.get("bruun"), ic="ola", tono="ambar")
            ui.kpi("Error", meta.get("error"), ic="info", tono="gris")
            ui.kpi("Generado (mtime archivo)", meta.get("_modificado"), ic="reloj", tono="gris")

    with der:
        tabs = st.tabs(["Mapa", "Priorización Ruta 90", "Estadísticas por sector", "Escenarios SSP", "Incertidumbre", "Metodología y metadatos"])
        with tabs[0]:
            m = mapas.crear_mapa(cfg, bounds=_bounds_datos(0) if CAPAS["lineas_fecha"].disponible(cfg) else None)
            col = cfg["visualizacion"]["colores"]
            if escenario and mostrar_ivc:
                calor, _ = mod_ivc.rasters_version(cfg, escenario)
                if calor:
                    mapas.agregar_superposicion(m, rasteres.superponer_rgba(cfg, calor), f"IVC {mod_ivc.titulo_version(cfg, escenario)}", opacidad=cfg["visualizacion"]["opacidad"]["raster_ivc"])
                if comparar_actual:
                    calor0, _ = mod_ivc.rasters_version(cfg, "ewm_total")
                    if calor0:
                        mapas.agregar_superposicion(m, rasteres.superponer_rgba(cfg, calor0), "IVC actual (ewm_total)", opacidad=cfg["visualizacion"]["opacidad"]["raster_ivc"], mostrar=False)
                mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, "IVC (escenario y actual)"), "bottomleft")
            if comparar_hist and CAPAS["lineas_fecha"].disponible(cfg):
                from .. import temporal

                obs = temporal.observaciones(_lineas_fecha(0))
                if obs:
                    gj0 = _geojson_fecha(obs[0].clave, cfg["visualizacion"]["simplificacion_m"]["lineas_fecha"])
                    mapas.agregar_geojson(m, gj0, f"Histórica {obs[0].fecha:%Y-%m-%d}", color="#3fa7d6", grosor=2, campos_tooltip=["fecha_txt", "satname"])
            if g is not None and tipos:
                gj = _geojson_lineas(variante, anio, tuple(tipos))
                estilos = {"observada": (col["linea_seleccionada"], None, 2.0), "central": (col["prediccion_central"], None, 3.0), "p05": (col["prediccion_banda"], "4 6", 1.5),
                           "p95": (col["prediccion_banda"], "4 6", 1.5), "persistencia": (col["prediccion_persistencia"], "10 6", 2.0)}
                mapas.agregar_geojson(m, gj, f"Proyección {anio}", grosor=2, campos_tooltip=["linea", "tipo"], alias={"linea": "Línea", "tipo": "Tipo"},
                                      funcion_estilo=lambda f, e=estilos: {"color": e[f["properties"]["tipo"]][0], "dashArray": e[f["properties"]["tipo"]][1], "weight": e[f["properties"]["tipo"]][2]})
                mapas.agregar_leyenda_html(m, "<b>Tipos de línea</b><br>" + "<br>".join(
                    f'<span style="display:inline-block;width:26px;border-top:3px {"dashed" if d else "solid"} {c};vertical-align:middle;margin-right:6px"></span>{mod_pred.TIPOS_LINEA[k][0]}'
                    for k, (c, d, _) in estilos.items() if k in tipos) + '<br><span style="display:inline-block;width:26px;border-top:3px solid #3fa7d6;vertical-align:middle;margin-right:6px"></span>Observación histórica 1984')
            if CAPAS["ruta90"].disponible(cfg):
                mapas.agregar_geojson(m, _geojson_capa("ruta90", 0, None), "Ruta 90", color=col["ruta90"], grosor=2)
            mapas.finalizar(m)
            ui.mostrar_mapa(m, 560, "mapa_pred")
            ui.nota("Diferenciación: amarillo = observación 2026; naranja continuo = resultado del modelo; naranja discontinuo = banda p05–p95 (Monte Carlo); violeta = escenario de referencia (persistencia); azul = observación histórica 1984. Nada se interpola entre horizontes.")
        with tabs[1]:
            _tab_ruta90(cfg)
        with tabs[4]:
            if variante:
                res = mod_pred.resumen(cfg, variante)
                if res is not None:
                    st.markdown(f"**Resumen de la proyección** — {vd[variante]}")
                    ui.tabla(res.round(3), hide_index=True, use_container_width=True)
                pt = mod_pred.por_transecto(cfg, variante)
                if pt is not None:
                    num = [c for c in pt.columns if pd.api.types.is_numeric_dtype(pt[c]) and c not in ("id_ivc", "BaselineID", "TransOrder", "bloque")]
                    colx = "dist_costa_km" if "dist_costa_km" in pt.columns else pt.columns[0]
                    coly = st.selectbox("Variable por transecto", num, index=min(5, len(num) - 1), key="pred_var")
                    import plotly.express as px

                    fig = px.line(pt.sort_values(colx), x=colx, y=coly, color_discrete_sequence=["#ff7f00"])
                    ui.grafico(graficos._estilo(fig, f"{coly} por transecto", 320))
                    with st.expander("Tabla por transecto"):
                        ui.tabla(pt, use_container_width=True, height=360)
                        ui.descargas(pt, f"proyeccion_transectos_{variante}", cfg, "pred_exp_t", formatos=("csv",))
            if hay_ivc and escenario:
                t = mod_ivc.cargar_transectos_ivc(cfg)
                ci, cc = mod_ivc.columnas_version(t, escenario)
                e_fut = mod_ivc.estadisticas(t, ci, cc, cfg)
                c0, c1 = mod_ivc.columnas_version(t, "ewm_total")
                e_act = mod_ivc.estadisticas(t, c0, c1, cfg) if c0 else None
                st.markdown(f"**IVC por sector — {mod_ivc.titulo_version(cfg, escenario)}** frente al IVC actual")
                if "sectores_atlas" in CAPAS and CAPAS["sectores_atlas"].disponible(cfg):
                    sec = vectores.leer_capa(cfg, "sectores_atlas")
                    filas = []
                    for _, s in sec.iterrows():
                        sub = t[(t["dist_costa_km"] >= s["km_inicio"]) & (t["dist_costa_km"] < s["km_fin"])]
                        filas.append({"sector": s["nombre"], "n": len(sub), "IVC actual medio": sub[c0].mean() if c0 else None, "IVC futuro medio": sub[ci].mean(),
                                      "% alta/muy alta actual": (sub[c1] >= 4).mean() * 100 if c1 else None, "% alta/muy alta futuro": (sub[cc] >= 4).mean() * 100 if cc else None})
                    ui.tabla(pd.DataFrame(filas).round(3), hide_index=True, use_container_width=True)
                cA, cB = st.columns(2)
                if e_act:
                    ui.grafico_en(cA, graficos.barras_clases(e_act["pct_clases"], cfg, "IVC actual (ewm_total)"))
                ui.grafico_en(cB, graficos.barras_clases(e_fut["pct_clases"], cfg, mod_ivc.titulo_version(cfg, escenario)))
        with tabs[2]:
            er = mod_pred.escenarios_resumen(cfg)
            if er is not None:
                ui.grafico(graficos.escenarios_barras(er))
                ui.tabla(er.round(3), hide_index=True, use_container_width=True)
                ui.nota("Escenarios v4: nivel del mar (mediana AR6 por celda) y ancho de la barra reducido por el retroceso proyectado; resto de variables y pesos EWM 2026 fijos. 'persistencia' = extrapolación de la tendencia histórica como referencia, no resultado de modelo.")
            det = mod_pred.escenarios_detalle(cfg)
            if det is not None:
                with st.expander("Detalle por escenario y tipo de proyección"):
                    ui.tabla(det.round(3), hide_index=True, use_container_width=True)
            br = mod_pred.bruun(cfg)
            if br is not None:
                with st.expander("Regla de Bruun (resumen)"):
                    ui.tabla(br.round(3), hide_index=True, use_container_width=True)
            if er is None and det is None:
                ui.vacio("Sin tablas de escenarios")
        with tabs[3]:
            if hay_ivc and escenario:
                t = mod_ivc.cargar_transectos_ivc(cfg)
                ci, _ = mod_ivc.columnas_version(t, escenario)
                inf, sup = mod_ivc.columnas_incertidumbre(t, escenario)
                if inf and sup:
                    ui.grafico(graficos.ivc_por_km(pd.DataFrame(t.drop(columns="geometry")), ci, cfg, inf, sup, f"{mod_ivc.titulo_version(cfg, escenario)} con banda inf–sup"))
                    d = pd.DataFrame(t.drop(columns="geometry"))
                    ancho = (d[sup] - d[inf])
                    cA, cB = st.columns(2)
                    with cA:
                        ui.kpi("Anchura media de la banda", float(ancho.mean()), "0‑1", "sup − inf, media sobre transectos", 3, ic="regla", tono="azul")
                    with cB:
                        ui.kpi("Transectos cuya clase cambia entre inf y sup", int((mod_ivc.clasificar(d[inf], cfg) != mod_ivc.clasificar(d[sup], cfg)).sum()), "", "clase(inf) ≠ clase(sup)", ic="alerta", tono="ambar")
                else:
                    ui.vacio("Sin columnas de incertidumbre para este escenario")
            else:
                ui.vacio("Seleccione un escenario del IVC")
        with tabs[5]:
            if meta:
                st.json({k: v for k, v in meta.items() if not k.startswith("_")})
            st.markdown(mod_pred.requisitos_para_activar())
            ui.nota("Origen de los resultados: Modelos/07_Proyecciones (v4, 12‑10‑2026). Las líneas proyectadas corregidas sustituyen a las de la entrega del 11‑10 (transecto invertido), según LEEME_version4.txt.")


def _tab_ruta90(cfg: dict) -> None:
    """Mapa de priorización de la Ruta 90 (Troncal del Caribe): reproduce la Figura 37 con datos de priorizacion_ruta90_v4.csv."""
    if not CAPAS["ruta90_priorizacion"].disponible(cfg):
        ui.vacio("Sin priorización de la Ruta 90", "Falta Multicriterio/priorizacion_ruta90_v4.csv (se genera con fig_escenarios_v4.py).")
        return
    d = mod_r90.cargar_priorizacion(cfg)
    res = mod_r90.resumen(d)
    c = st.columns(5)
    with c[0]:
        ui.kpi("Tramos analizados", res["n_tramos"], "de 1 km", "Tramos de costa con la vía a ≤ 1000 m", 0, "modelo", ic="regla", tono="gris")
    with c[1]:
        ui.kpi("Prioridad alta", res["n_alta"], "tramos", "La costa alcanza la vía antes de 2050", 0, "modelo", ic="alerta", tono="coral")
    with c[2]:
        ui.kpi("Prioridad media", res["n_media"], "tramos", "Alcance entre 2050 y 2100", 0, "modelo", ic="reloj", tono="ambar")
    with c[3]:
        ui.kpi("Primer alcance", f"{res['primer_anio']:.0f}" if res["primer_anio"] else None, res["primer_tramo"] or "", f"Tramo más urgente: vía a {res['primer_dist']:.0f} m de la costa 2026" if res["primer_dist"] is not None else "", 0, "modelo", ic="calendario", tono="coral")
    with c[4]:
        ui.kpi("Sin alcance a 2110", res["n_sin_alcance"], "tramos", "La costa proyectada no llega a la vía en el periodo", 0, "modelo", ic="escudo", tono="teal")
    bounds = _bounds_datos(0) if CAPAS["lineas_fecha"].disponible(cfg) or CAPAS["lineas_anuales_dsas"].disponible(cfg) else None
    m = mapas.crear_mapa(cfg, bounds=bounds, mapa_base="Esri Light Gray (claro)")
    if CAPAS["puntos_km"].disponible(cfg):
        import folium

        gj = _geojson_capa("puntos_km", 0, ("km", "rotulo"))
        fg = folium.FeatureGroup(name="Km de la costa (desde Bocas de Ceniza)", show=True)
        for f in gj.get("features", []):
            km = f["properties"].get("km")
            try:
                km_i = int(float(km))
            except (TypeError, ValueError):
                continue
            if km_i % 5:
                continue
            lon, lat = f["geometry"]["coordinates"][:2]
            folium.CircleMarker([lat, lon], radius=3, color="#2b2f3a", fill=True, fill_opacity=1, weight=1, tooltip=f"km {km_i} de la costa").add_to(fg)
            folium.map.Marker([lat, lon], icon=folium.DivIcon(html=f'<div style="font:600 11px Manrope,sans-serif;color:#2b2f3a;transform:translate(6px,-16px);text-shadow:0 0 3px #fff">{km_i}</div>', icon_size=(1, 1))).add_to(fg)
        fg.add_to(m)
    agregar_ruta90_prioridad(m, cfg)
    mapas.finalizar(m)
    # la pestaña está oculta al crear el mapa: fit_bounds no puede calcular el zoom, así que se fija centro/zoom explícitos
    ui.mostrar_mapa(m, 520, "mapa_ruta90", vista=mapas.vista_para_bounds(bounds, 1000, 520) if bounds else None)
    ui.nota("Cada segmento de ~50 m de la vía toma la prioridad del tramo de 1 km de costa más cercano (transecto IVC más próximo, a ≤ 1,3 km); "
            "la costa 2026 se colorea por tramo. Los años provienen del archivo de la tesis: el geovisor no los recalcula.")
    ui.grafico(graficos.alcance_ruta90(d, mod_r90.COLORES))
    ui.nota("Año del tramo = mínimo, entre sus transectos, del primer año en que el retroceso acumulado (persistencia amortiguada por ventanas de 21 años + Bruun SSP5‑8.5, "
            "interpolado linealmente entre 2026, 2050 y 2100) iguala la distancia de la vía a la costa 2026. Intervalo = tasas P5/P95 y Bruun P95/P5 (aproximación, no un IC). "
            "El km de la vía es el abscisado sobre el eje IGAC/OSM desde Barranquilla, no el PR oficial del INVÍAS.")
    with st.expander("Tabla de tramos (priorizacion_ruta90_v4.csv) y descarga", expanded=False):
        cols = [c for c in ("orden", "tramo", "km_via_inicio", "km_via_fin", "dist_min_ruta90_m", "anio_alcance", "anio_alcance_erosion_rapida", "anio_alcance_erosion_lenta", "transecto_critico_id",
                            "IVC_actual_clase_max", "IVC_SSP585_2050_clase_max", "IVC_SSP585_2100_clase_max", "prioridad") if c in d.columns]
        ui.tabla(d.sort_values("orden")[cols].round(2), hide_index=True, use_container_width=True)
        ui.descargas(d.sort_values("orden"), "priorizacion_ruta90_v4", cfg, "r90_exp", formatos=("csv",))
        if CAPAS["ruta90_priorizacion_v3"].disponible(cfg):
            v3 = mod_r90.cargar_priorizacion(cfg, "v3")
            cmp_ = d[["tramo", "km_inicio", "anio_alcance", "prioridad"]].merge(v3[["km_inicio", "anio_alcance", "prioridad"]], on="km_inicio", suffixes=("_v4", "_v3 (LRR lineal)"))
            st.markdown("**Comparación con la versión 3** (LRR 1984–2026 lineal, sin Bruun)")
            ui.tabla(cmp_.round(1), hide_index=True, use_container_width=True)
    if CAPAS["figura_ruta90"].disponible(cfg):
        with st.expander("Figura 37 de la tesis (Figuras/Figura_37_priorizacion_Ruta90.png)"):
            st.image(str(CAPAS["figura_ruta90"].ruta(cfg)), use_container_width=True)
