"""Sección 2 — Evolución histórica: comparación temporal, acumulación cronológica y animación con fechas reales."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from folium import plugins

from .. import graficos, mapas, temporal, vectores
from ..catalogo_datos import CAPAS
from ..configuracion import ruta as ruta_cfg
from ..vectores import CapaNoDisponible
from . import comunes as ui
from .visor import _bounds_datos, _geojson_fecha, _geojson_rango, _lineas_fecha, control_temporal



class _fmt_anio:  # etiqueta de año sin redondear hacia arriba
    @staticmethod
    def format(v):
        return str(int(v))


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_animacion(ini: str, fin: str, tol: float, solo_completas: bool) -> dict:
    from .visor import _cfg

    cfg = _cfg()
    g = _lineas_fecha(0)
    g = g[(g["fecha_dt"] >= pd.Timestamp(ini)) & (g["fecha_dt"] <= pd.Timestamp(fin) + pd.Timedelta(days=1))]
    if solo_completas and "clase" in g:
        g = g[g["clase"] == "completa"]
    gs = vectores.simplificar_para_mapa(g, cfg, max(tol, 5.0))
    gj = vectores.a_geojson(gs.assign(fecha_txt=gs["fecha_dt"].dt.strftime("%Y-%m-%d")), cfg, ["fecha_txt", "epoca", "satname", "lado"])
    for f, fecha in zip(gj["features"], gs["fecha_dt"]):
        f["properties"]["time"] = fecha.strftime("%Y-%m-%dT%H:%M:%S")
        f["properties"]["style"] = {"color": "#ffd166", "weight": 2.5, "opacity": 0.95}
    return gj


def render(cfg: dict) -> None:
    try:
        g = _lineas_fecha(0)
    except CapaNoDisponible as e:
        ui.vacio("Sin líneas de costa por fecha", str(e))
        return
    obs = temporal.observaciones(g)
    ui.seccion("Evolución histórica", "play", "comparación de fechas, acumulación cronológica y animación con observaciones reales")
    izq, centro = st.columns([1.05, 3.7], gap="small")
    with izq:
        estado = control_temporal(cfg, obs, "evo")
        ui.panel("Modo de visualización", "play")
        modo = st.radio("Modo", ["A · Comparación temporal", "B · Acumulación histórica", "C · Animación (fechas reales)"], label_visibility="collapsed", key="evo_modo_sel")
        mostrar_anuales = st.checkbox("Superponer líneas anuales (mediana)", value=False, key="evo_anuales", disabled=not CAPAS["lineas_anuales"].disponible(cfg))
        comparar = None
        if modo.startswith("A"):
            etiquetas = [f"{o.fecha:%Y-%m-%d} · {o.sensor}" for o in estado["obs_rango"]]
            i2 = st.selectbox("Comparar con (segunda fecha)", ["— ninguna —"] + etiquetas, key="evo_cmp")
            comparar = estado["obs_rango"][etiquetas.index(i2)] if i2 != "— ninguna —" else None
        solo_completas = False
        if modo.startswith("C"):
            solo_completas = st.checkbox("Solo líneas con clase 'completa'", value=True, key="evo_completas", disabled="clase" not in g.columns, help="Solo aplica a las líneas CoastSat por fecha de imagen")
            periodo_ms = st.slider("Duración por fotograma (ms)", 100, 1500, 400, 50, key="evo_ms")
        bases = [b["nombre"] for b in cfg["mapa"]["mapas_base"]]
        base = st.selectbox("Mapa base", bases, index=bases.index(cfg["mapa"]["mapa_base_defecto"]), key="evo_base")

    vis = cfg["visualizacion"]
    col = vis["colores"]
    tol = vis["simplificacion_m"]["lineas_fecha"]
    with centro:
        m = mapas.crear_mapa(cfg, bounds=_bounds_datos(0), mapa_base=base)
        if mostrar_anuales:
            from .visor import _geojson_capa

            gj = _geojson_capa("lineas_anuales", vis["simplificacion_m"]["lineas_anuales"], ("epoca", "anio", "fecha_med", "lado"))
            mapas.agregar_geojson(m, gj, "Líneas anuales", color=col["linea_anual"], grosor=1.2, opacidad=0.6, campos_tooltip=["epoca", "lado"])
        o = estado["obs"]
        if modo.startswith("A"):
            gj = _geojson_fecha(o.clave, tol)
            mapas.agregar_geojson(m, gj, f"Línea {o.fecha:%Y-%m-%d}", color=col["linea_seleccionada"], grosor=3, campos_tooltip=["fecha_txt", "satname", "lado"])
            if comparar:
                gj2 = _geojson_fecha(comparar.clave, tol)
                mapas.agregar_geojson(m, gj2, f"Línea {comparar.fecha:%Y-%m-%d}", color="#3fa7d6", grosor=3, campos_tooltip=["fecha_txt", "satname", "lado"])
                mapas.agregar_leyenda_html(m, f'<b>Comparación</b><br><span style="color:{col["linea_seleccionada"]}">━</span> {o.fecha:%Y-%m-%d} ({o.sensor})<br><span style="color:#3fa7d6">━</span> {comparar.fecha:%Y-%m-%d} ({comparar.sensor})')
        elif modo.startswith("B"):
            gj = _geojson_rango(str(estado["ini"]), str(estado["fin"]), tol)
            n = len(gj.get("features", []))
            if n > vis.get("max_lineas_todas", 800):
                st.warning(f"{n} líneas; se dibujan {vis['max_lineas_todas']}. Reduzca el intervalo.")
                gj["features"] = gj["features"][: vis["max_lineas_todas"]]
            if n:
                dec = [f["properties"]["anio_dec"] for f in gj["features"]]
                rampa = mapas.rampa_cronologica(cfg, min(dec), max(dec), f"Año de observación ({estado['ini']} → {estado['fin']})")
                mapas.agregar_geojson(m, gj, f"Líneas {estado['ini']} → {estado['fin']} ({n})", grosor=1.4, opacidad=0.8, campos_tooltip=["fecha_txt", "satname", "lado"],
                                      campos_popup=[c for c in ("fecha_txt", "epoca", "lado", "largo_m", "UNCY") if gj["features"] and c in gj["features"][0]["properties"]], funcion_estilo=lambda f, r=rampa: {"color": r(f["properties"]["anio_dec"])})
                mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption, _fmt_anio), "bottomleft")
            gj_sel = _geojson_fecha(o.clave, tol)
            mapas.agregar_geojson(m, gj_sel, f"Línea seleccionada {o.fecha:%Y-%m-%d}", color=col["linea_seleccionada"], grosor=3.2)
        else:
            gj = _geojson_animacion(str(estado["ini"]), str(estado["fin"]), tol, solo_completas)
            n = len(gj.get("features", []))
            if n:
                plugins.TimestampedGeoJson(gj, period="P1D", duration="P1D", transition_time=periodo_ms, auto_play=False, loop=False,
                                           add_last_point=False, date_options="YYYY-MM-DD", time_slider_drag_update=True).add_to(m)
                ui.nota(f"Animación con {n} líneas reales entre {estado['ini']} y {estado['fin']} (sin posiciones interpoladas). Use ▶ en el mapa.")
            else:
                ui.vacio("Sin líneas en el intervalo")
        mapas.finalizar(m)
        ui.mostrar_mapa(m, 600, "mapa_evo")

        t0, t1, t2 = st.tabs(["▶ Animación anual", "Longitud por fecha", "Observaciones por año"])
        with t0:
            try:
                an = temporal.cargar_lineas_anuales(cfg)
                serie = an.groupby("anio", as_index=False)["largo_m"].sum().rename(columns={"largo_m": "valor"})
                serie = serie[(serie["anio"] >= estado["ini"].year) & (serie["anio"] <= estado["fin"].year)]
                ui.grafico(graficos.evolucion_animada(serie, "Longitud de la línea anual (mediana corregida por marea) — pulse ▶", "m"))
                ui.nota("Cada fotograma añade un año real de las líneas anuales (campo 'largo_m'); los años sin línea (1988, 1992, …) no aparecen ni se interpolan.")
            except CapaNoDisponible:
                ui.vacio("Sin líneas anuales para animar")
        with t1:
            df = temporal.serie_longitud(estado["obs_rango"])
            ui.grafico(graficos.longitud_por_fecha(df, o.fecha))
        with t2:
            p = CAPAS["cobertura_anio"].ruta(cfg)
            if p.exists():
                ui.grafico(graficos.observaciones_por_anio(pd.read_csv(p)))
            else:
                ui.vacio("cobertura_por_anio.csv no disponible")
        _videos_existentes(cfg)


def _videos_existentes(cfg: dict) -> None:
    """Enlaza animaciones ya generadas en CoastSat-master/video_evolucion_costa sin duplicarlas."""
    carpeta = ruta_cfg(cfg, "coastsat_raiz") / "video_evolucion_costa"
    if not carpeta.exists():
        return
    archivos = [p for p in carpeta.iterdir() if p.suffix.lower() in (".mp4", ".gif", ".webm")]
    if not archivos:
        return
    with st.expander(f"Animaciones generadas previamente ({len(archivos)})"):
        for p in archivos[:10]:
            st.caption(f"{p.name} · {p.stat().st_size / 1e6:.1f} MB")
            if p.suffix.lower() == ".gif":
                st.image(str(p))
            else:
                st.video(str(p))
