"""Sección 1 — Visor geoespacial: mapa central, panel de capas, control temporal y panel de estadísticas."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from .. import dsas, graficos, ivc as mod_ivc, mapas, predicciones as mod_pred, rasteres, temporal, vectores
from ..catalogo_datos import CAPAS
from ..calculo import capas_proyecto as CP
from ..configuracion import ruta as ruta_cfg
from ..inventario import cargar_catalogo
from ..vectores import CapaNoDisponible
from . import comunes as ui
from ..estilos import icono

_log = logging.getLogger("geovisor.visor")



class _fmt_anio:  # etiqueta de año sin redondear hacia arriba
    @staticmethod
    def format(v):
        return str(int(v))


# ---------------------------------------------------------------------------
# Cargas cacheadas (claves hashables)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def _lineas_fecha(_v: int):
    cfg = _cfg()
    return temporal.cargar_lineas_fecha(cfg)


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_fecha(clave_fecha: str, tol: float) -> dict:
    cfg = _cfg()
    g = temporal.seleccionar_fecha(_lineas_fecha(0), clave_fecha)
    gs = vectores.simplificar_para_mapa(g, cfg, tol)
    gs = gs.assign(fecha_txt=gs["fecha_dt"].dt.strftime("%Y-%m-%d %H:%M" if (gs["fecha_dt"].dt.hour != 0).any() else "%Y-%m-%d"))
    return vectores.a_geojson(gs, cfg, ["fecha_txt", "epoca", "satname", "lado", "cob_pct", "largo_m", "UNCY", "n_tramos", "clase"])


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_rango(ini: str, fin: str, tol: float) -> dict:
    cfg = _cfg()
    g = _lineas_fecha(0)
    g = g[(g["fecha_dt"] >= pd.Timestamp(ini)) & (g["fecha_dt"] <= pd.Timestamp(fin) + pd.Timedelta(days=1))]
    gs = vectores.simplificar_para_mapa(g, cfg, tol)
    gs = gs.assign(fecha_txt=gs["fecha_dt"].dt.strftime("%Y-%m-%d"), anio_dec=gs["fecha_dt"].dt.year + gs["fecha_dt"].dt.dayofyear / 366)
    return vectores.a_geojson(gs, cfg, ["fecha_txt", "epoca", "satname", "lado", "cob_pct", "largo_m", "UNCY", "anio_dec"])


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_capa(clave: str, tol: float, campos: tuple) -> dict:
    cfg = _cfg()
    g = vectores.leer_capa(cfg, clave)
    gs = vectores.simplificar_para_mapa(g, cfg, tol)
    return vectores.a_geojson(gs, cfg, list(campos) if campos else None)


@st.cache_data(ttl=3600, show_spinner=False)
def _bounds_datos(_v: int):
    cfg = _cfg()
    return vectores.bounds_visual(_lineas_fecha(0), cfg)


def _cfg() -> dict:
    from ..contexto import cfg_app

    return cfg_app()


ALIAS_LINEA = {"fecha_txt": "Fecha", "epoca": "Época", "satname": "Sensor", "lado": "Lado", "cob_pct": "Cobertura (%)", "largo_m": "Longitud (m)", "UNCY": "Incertidumbre (m)", "n_tramos": "N.º tramos", "clase": "Clase"}


def _campos(gj: dict, deseados: list[str]) -> list[str]:
    """Solo los campos presentes en las propiedades (evita errores de Leaflet con campos inexistentes)."""
    if not gj or not gj.get("features"):
        return []
    props = gj["features"][0]["properties"]
    return [c for c in deseados if c in props]


@st.cache_data(ttl=3600, show_spinner=False)
def _geojson_coastsat_rango(ini: str, fin: str, tol: float) -> dict:
    """Líneas CoastSat por fecha de imagen (capa secundaria) dentro del intervalo."""
    cfg = _cfg()
    g = temporal.cargar_lineas_fecha(cfg, clave="lineas_fecha")
    g = g[(g["fecha_dt"] >= pd.Timestamp(ini)) & (g["fecha_dt"] <= pd.Timestamp(fin) + pd.Timedelta(days=1))]
    gs = vectores.simplificar_para_mapa(g, cfg, tol)
    gs = gs.assign(fecha_txt=gs["fecha_dt"].dt.strftime("%Y-%m-%d"), anio_dec=gs["fecha_dt"].dt.year + gs["fecha_dt"].dt.dayofyear / 366)
    return vectores.a_geojson(gs, cfg, ["fecha_txt", "satname", "lado", "cob_pct", "largo_m", "anio_dec"])


# ---------------------------------------------------------------------------
# Control temporal (compartido con «Evolución histórica»)
# ---------------------------------------------------------------------------
def _ir_a(clave: str, obs_rango: list, idx: int) -> None:
    """Pide cambiar la observación seleccionada; se aplica al inicio de la siguiente ejecución (antes de crear los widgets)."""
    st.session_state[f"{clave}_pendiente"] = max(0, min(idx, len(obs_rango) - 1))
    st.rerun()


def _aplicar_pendiente(clave: str, obs_rango: list) -> None:
    ss = st.session_state
    idx = ss.pop(f"{clave}_pendiente", None)
    if idx is None:
        return
    idx = max(0, min(int(idx), len(obs_rango) - 1))
    ss[f"{clave}_idx"] = idx
    nuevo = obs_rango[idx]
    ss[f"{clave}_anio"] = int(nuevo.fecha.year)
    for k in [k for k in ss if k.startswith(f"{clave}_fecha_")]:
        del ss[k]
    ss[f"{clave}_slider_anio"] = int(nuevo.fecha.year)


def control_temporal(cfg: dict, obs: list[temporal.Observacion], clave: str = "visor") -> dict:
    """Dibuja el selector temporal y devuelve el estado (observación seleccionada, rango, modo)."""
    ini_d, fin_d = temporal.rango_disponible(obs, cfg)
    ss = st.session_state
    ss.setdefault(f"{clave}_ini", ini_d.date())
    ss.setdefault(f"{clave}_fin", fin_d.date())
    ui.panel("Control temporal", "calendario", "fechas reales de observación")
    c1, c2 = st.columns(2)
    ini = c1.date_input("Fecha inicial", value=ss[f"{clave}_ini"], min_value=ini_d.date(), max_value=fin_d.date(), key=f"{clave}_di")
    fin = c2.date_input("Fecha final", value=ss[f"{clave}_fin"], min_value=ini_d.date(), max_value=fin_d.date(), key=f"{clave}_df")
    if fin < ini:
        st.warning("La fecha final es anterior a la inicial; se intercambian.")
        ini, fin = fin, ini
    obs_rango = temporal.filtrar_rango(obs, ini, fin)
    if not obs_rango:
        st.warning("No hay observaciones en el intervalo.")
        obs_rango = obs
    _aplicar_pendiente(clave, obs_rango)
    por_anio = temporal.fechas_por_anio(obs_rango)
    anios = sorted(por_anio)
    ss.setdefault(f"{clave}_idx", len(obs_rango) - 1)
    idx = min(max(ss[f"{clave}_idx"], 0), len(obs_rango) - 1)

    # Año -> fecha dentro del año (si hay varias)
    anio_actual = obs_rango[idx].fecha.year
    ca, cf = st.columns([1, 1.6])
    anio = ca.selectbox("Año", anios, index=anios.index(anio_actual) if anio_actual in anios else len(anios) - 1, key=f"{clave}_anio")
    fechas_anio = por_anio[anio]
    if obs_rango[idx].fecha.year != anio:
        idx = obs_rango.index(fechas_anio[-1])
    etiquetas = [o.etiqueta for o in fechas_anio]
    pos = fechas_anio.index(obs_rango[idx]) if obs_rango[idx] in fechas_anio else len(fechas_anio) - 1
    sel = cf.selectbox(f"Fecha ({len(fechas_anio)} en {anio})", etiquetas, index=pos, key=f"{clave}_fecha_{anio}")
    idx = obs_rango.index(fechas_anio[etiquetas.index(sel)])

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("⏮", use_container_width=True, key=f"{clave}_first", disabled=idx <= 0, help="Primera observación del intervalo"):
        _ir_a(clave, obs_rango, 0)
    if b2.button("◀", use_container_width=True, key=f"{clave}_prev", disabled=idx <= 0, help="Observación anterior"):
        _ir_a(clave, obs_rango, idx - 1)
    if b3.button("▶", use_container_width=True, key=f"{clave}_next", disabled=idx >= len(obs_rango) - 1, help="Observación siguiente"):
        _ir_a(clave, obs_rango, idx + 1)
    if b4.button("⏭", use_container_width=True, key=f"{clave}_last", disabled=idx >= len(obs_rango) - 1, help="Última observación del intervalo"):
        _ir_a(clave, obs_rango, len(obs_rango) - 1)
    modo = st.radio("Líneas en el mapa", ["Solo la fecha", "Todas del intervalo"], horizontal=True, key=f"{clave}_modo")
    ss[f"{clave}_idx"] = idx
    o = obs_rango[idx]
    st.markdown(f'<div class="gv-nota">Observación real: <b>{o.fecha:%Y-%m-%d}</b> · {o.sensor} · {idx + 1}/{len(obs_rango)} del intervalo</div>', unsafe_allow_html=True)
    return {"obs": o, "idx": idx, "obs_rango": obs_rango, "ini": ini, "fin": fin, "modo": modo}


def avance_automatico(estado: dict, clave: str = "visor", segundos: float = 0.8) -> None:
    """Si «▶ Recorrer» está activo, espera y pasa a la siguiente observación. Debe llamarse al FINAL de la página:
    si se re-ejecuta antes de dibujar el mapa, el mapa y las estadísticas nunca se actualizan."""
    if estado.get("auto"):
        import time

        time.sleep(segundos)
        _ir_a(clave, estado["obs_rango"], (estado["idx"] + 1) % len(estado["obs_rango"]))


def barra_tiempo(cfg: dict, obs: list[temporal.Observacion], estado: dict, clave: str = "visor") -> None:
    """Barra deslizable de años (1984 → 2026) sobre el mapa. Salta solo a observaciones reales y muestra la densidad por año."""
    obs_r = estado["obs_rango"]
    por_anio = temporal.fechas_por_anio(obs_r)
    anios = sorted(por_anio)
    o = estado["obs"]
    a0, a1 = anios[0], anios[-1]
    ss = st.session_state
    c1, c2 = st.columns([4.2, 1])
    with c1:
        kw = {} if f"{clave}_slider_anio" in ss else {"value": int(o.fecha.year)}
        anio_sel = st.slider(f"Año (arrastre para recorrer {a0} → {a1})", a0, a1, step=1, key=f"{clave}_slider_anio", help="Solo hay observaciones en los años con barra; al elegir un año sin imagen se salta a la observación real más cercana.", **kw)
    with c2:
        ui.hueco_etiqueta()
        auto = st.toggle("▶ Recorrer", value=False, key=f"{clave}_auto", help="Avanza automáticamente una observación por segundo (pulse de nuevo para detener)")
    if anio_sel != o.fecha.year:
        if anio_sel in por_anio:
            nuevo = por_anio[anio_sel][-1]
        else:
            nuevo = obs_r[temporal.indice_mas_cercano(obs_r, pd.Timestamp(year=anio_sel, month=7, day=1))]
        _ir_a(clave, obs_r, obs_r.index(nuevo))
    estado["auto"] = bool(auto)  # el avance automático se ejecuta al final de la página, cuando el mapa y las cifras ya se dibujaron
    # densidad de observaciones por año (barras reales; punteado = año sin imagen)
    todos = list(range(a0, a1 + 1))
    maxn = max(len(v) for v in por_anio.values())
    celdas = []
    for a in todos:
        n = len(por_anio.get(a, []))
        h = 4 + 26 * n / maxn if n else 2
        cls = "a sel" if a == o.fecha.year else ("a" if n else "a vacio")
        celdas.append(f'<div class="{cls}" title="{a}: {n} observaciones"><div class="b" style="height:{h:.0f}px"></div><span>{str(a)[2:]}</span></div>')
    st.markdown(
        f'<div class="gv-timeline"><div class="cab"><b>Línea de tiempo · {len(obs_r)} observaciones reales</b>'
        f'<span class="fecha">{o.fecha:%d %b %Y}</span><span class="gv-nota" style="margin:0">{o.sensor} · {len(por_anio.get(o.fecha.year, []))} línea(s) en {o.fecha.year} · {estado["idx"] + 1}/{len(obs_r)}</span></div>'
        f'<div class="anios">{"".join(celdas)}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Panel de capas
# ---------------------------------------------------------------------------
DEF_CAPAS = [
    # clave interna, etiqueta corta (chip), clave catálogo, visible por defecto, grupo, descripción (tooltip)
    ("linea_sel", "Fecha seleccionada", "lineas_anuales_dsas", True, "Línea de costa", "Línea anual DSAS de la fecha elegida (amarilla)"),
    ("linea_ref", "Referencia (1.ª del intervalo)", "lineas_anuales_dsas", True, "Línea de costa", "Primera observación del intervalo, punteada blanca, fija para comparar"),
    ("lineas_rango", "Otras fechas del intervalo", "lineas_anuales_dsas", False, "Línea de costa", "Todas las líneas anuales del intervalo, con rampa cronológica"),
    ("lineas_anuales", "CoastSat por imagen (360)", "lineas_fecha", False, "Línea de costa", "Líneas CoastSat por fecha de imagen Landsat dentro del intervalo"),
    ("transectos", "Transectos", "dsas_transectos", True, "DSAS", "671 transectos DSAS"),
    ("tasas", "Tasas LRR", "dsas_tasas", True, "DSAS", "Tasas de cambio por transecto (campo elegible en Opciones)"),
    ("linea_base", "Línea base", "linea_base", False, "DSAS", "Línea base DSAS"),
    ("ivc_raster", "Mapa de calor", "ivc_rasters_dir", False, "IVC", "Ráster del IVC de la versión elegida en Opciones"),
    ("ivc_poligonos", "Franjas por transecto", "ivc_franjas", False, "IVC", "Franjas de muestreo clasificadas por IVC"),
    ("pred_lineas", "Líneas 2050 · 2100", "proy_amortiguada", False, "Predicciones", "Líneas de costa proyectadas (variante y año en Opciones)"),
    ("pred_ivc", "IVC futuro (SSP)", "ivc_rasters_dir", False, "Predicciones", "Mapa de calor del IVC bajo el escenario elegido"),
    ("ruta90_prio", "Ruta 90 priorizada", "ruta90_priorizacion", False, "Predicciones", "Tramos de la vía por prioridad de intervención (v4)"),
    ("calc_tasas", "Tasas del proyecto", "calc:calc_tasas", False, "Calculadora", "Transectos con tasas de un proyecto calculado con la Calculadora IVC (elija el proyecto en Opciones)"),
    ("calc_ivc", "IVC del proyecto", "calc:calc_ivc", False, "Calculadora", "Índice por transecto del proyecto (esquema de pesos en Opciones)"),
    ("calc_lineas", "Líneas proyectadas", "calc:calc_lineas", False, "Calculadora", "Líneas de costa proyectadas por el proyecto"),
    ("calc_escenario", "IVC futuro", "calc:calc_escenario", False, "Calculadora", "IVC futuro del proyecto bajo el escenario elegido en Opciones"),
    ("calc_base", "Línea base", "calc:calc_base", False, "Calculadora", "Línea base del proyecto"),
    ("area", "Sectores", "sectores_roi", False, "Contexto", "Límites del área de estudio y sectores"),
    ("boca", "Boca de la Ciénaga", "boca_cienaga", False, "Contexto", "Zona excluida en DSAS"),
    ("ruta90", "Ruta 90", "ruta90", False, "Contexto", "Troncal del Caribe (IGAC/OSM)"),
    ("edificaciones", "Edificaciones", "osm_edificaciones", False, "Contexto", "OpenStreetMap"),
    ("geomorfologia", "Geomorfología", "geomorfologia", False, "Contexto", "INVEMAR"),
    ("manglar", "Hidrografía y manglar", "manglar", False, "Contexto", "OpenStreetMap"),
    ("fondo", "Fondo tierra/agua", "fondo_rgb", False, "Imágenes", "Imagen de referencia tierra/agua"),
    ("escena", "Escena Landsat", None, False, "Imágenes", "Escena CoastSat (elija sector y fecha en Opciones)"),
]
GRUPOS_CAPAS = ["Línea de costa", "DSAS", "IVC", "Predicciones", "Calculadora", "Contexto", "Imágenes"]
ICONO_GRUPO = {"Línea de costa": "lineas", "DSAS": "regla", "IVC": "escudo", "Predicciones": "cristal", "Calculadora": "grafico", "Contexto": "mapa", "Imágenes": "satelite"}


def _capa_calculadora_disponible(cfg: dict, k: str) -> bool:
    """Hay algún proyecto exportado por la Calculadora con esa capa."""
    try:
        return any(k in CP.capas_de(c) for c in CP.proyectos(cfg).values())
    except Exception:  # noqa: BLE001
        return False


def panel_capas(cfg: dict, clave: str = "visor") -> dict:
    """Listado compacto de capas: chips (st.pills) agrupados por tema; las capas sin datos no se ofrecen y se cuentan en el pie."""
    ui.panel("Capas", "capas", "pulse un chip para activar o desactivar")
    activas = {}
    faltan = []
    for grupo in GRUPOS_CAPAS:
        filas = [c for c in DEF_CAPAS if c[4] == grupo]
        disp, defecto = [], []
        ayuda = []
        for k, et, clave_cat, defecto_k, _, desc in filas:
            if clave_cat is None:
                ok = _hay_escenas(cfg)
            elif clave_cat.startswith("calc:"):
                ok = _capa_calculadora_disponible(cfg, clave_cat[5:])
            else:
                ok = CAPAS[clave_cat].disponible(cfg)
            if ok:
                disp.append(k)
                if defecto_k:
                    defecto.append(k)
                ayuda.append(f"{et}: {desc}")
            else:
                faltan.append(et)
        if not disp:
            continue
        etiquetas = {k: et for k, et, *_ in filas}
        key = f"{clave}_capas_{grupo}"
        st.markdown(f'<div class="gv-grupo-capas">{icono(ICONO_GRUPO[grupo], tam=13)}<span>{grupo}</span></div>', unsafe_allow_html=True)
        sel = st.pills(grupo, disp, selection_mode="multi", default=defecto if key not in st.session_state else None, key=key,
                       format_func=lambda k, e=etiquetas: e[k], label_visibility="collapsed", help="\n\n".join(ayuda))
        for k in disp:
            activas[k] = k in (sel or [])
    for k, *_ in DEF_CAPAS:
        activas.setdefault(k, False)
    if faltan:
        st.markdown(f'<div class="gv-nota" style="margin-top:4px">Sin datos: {", ".join(faltan)}</div>', unsafe_allow_html=True)
    return activas


@st.cache_data(ttl=600, show_spinner=False)
def _escenas(_v: int) -> pd.DataFrame | None:
    cfg = _cfg()
    cat = cargar_catalogo(ruta_cfg(cfg, "catalogo"))
    if cat is None or cat.empty or "categoria" not in cat:
        return None
    e = cat[(cat["categoria"] == "escena_landsat") & (cat["tipo_geometria"] == "escena ms")].copy()
    if e.empty:
        return None
    e["fecha"] = pd.to_datetime(e["fechas_nombre"].apply(lambda v: v[0] if isinstance(v, list) and v else None), errors="coerce")
    return e.dropna(subset=["fecha"]).sort_values("fecha")


def _hay_escenas(cfg: dict) -> bool:
    e = _escenas(0)
    return e is not None and not e.empty


# ---------------------------------------------------------------------------
# Construcción del mapa
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def _distancia_media(clave_a: str, clave_b: str) -> dict:
    """Distancia media/máxima (m, sin signo) de la línea A a la línea B, muestreando A cada 100 m en el CRS métrico."""
    import numpy as np

    cfg = _cfg()
    g = _lineas_fecha(0)
    ga = vectores.a_metrico(temporal.seleccionar_fecha(g, pd.Timestamp(clave_a)), cfg)
    gb = vectores.a_metrico(temporal.seleccionar_fecha(g, pd.Timestamp(clave_b)), cfg)
    if ga.empty or gb.empty:
        return {}
    ref = gb.geometry.union_all() if hasattr(gb.geometry, "union_all") else gb.geometry.unary_union
    dists = []
    for geom in ga.geometry:
        partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        for ln in partes:
            for d in np.arange(0, ln.length, 100.0):
                dists.append(ln.interpolate(d).distance(ref))
    if not dists:
        return {}
    return {"media": float(np.mean(dists)), "max": float(np.max(dists)), "n": len(dists)}


@st.cache_data(ttl=3600, show_spinner=False)
def _sectores_zoom() -> dict:
    """Encuadres por sector (EPSG:4326) a partir de los sectores CoastSat; vacío si la capa no existe."""
    cfg = _cfg()
    try:
        g = vectores.a_visual(vectores.leer_capa(cfg, "sectores_roi"), cfg)
    except (CapaNoDisponible, ValueError):
        return {}
    out = {}
    campo = "sector" if "sector" in g.columns else None
    for i, (_, fila) in enumerate(g.iterrows(), start=1):
        b = fila.geometry.bounds
        nombre = f"Sector {fila[campo]}" if campo else f"Sector {i}"
        out[nombre] = [[b[1], b[0]], [b[3], b[2]]]
    return out


def construir_mapa(cfg: dict, estado: dict, activas: dict, mapa_base: str, bounds, opciones: dict) -> tuple:
    vis = cfg["visualizacion"]
    col, gro, opa = vis["colores"], vis["grosor"], vis["opacidad"]
    m = mapas.crear_mapa(cfg, bounds=bounds, mapa_base=mapa_base)
    stats = {}
    leyendas = []
    capas: list = []  # FeatureGroups dinámicos: se actualizan sin recrear el mapa (ver comunes.mostrar_mapa)

    def fg(nombre: str):
        import folium

        g = folium.FeatureGroup(name=nombre, show=True)
        capas.append(g)
        return g

    # Imagen de referencia
    if activas.get("fondo"):
        try:
            s = rasteres.superponer_rgba(cfg, CAPAS["fondo_rgb"].ruta(cfg))
            mapas.agregar_superposicion(fg("Fondo tierra/agua"), s, "Fondo tierra/agua", opacidad=opa["raster_referencia"], zindex=1)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Fondo no dibujado: {e}")
    if activas.get("escena") and opciones.get("escena_ruta"):
        try:
            s = rasteres.superponer_escena_landsat(cfg, opciones["escena_ruta"])
            mapas.agregar_superposicion(fg(f"Landsat {opciones.get('escena_nombre', '')}"), s, f"Landsat {opciones.get('escena_nombre', '')}", opacidad=1.0, zindex=2)
            stats["escena"] = opciones.get("escena_nombre")
        except Exception as e:  # noqa: BLE001
            st.warning(f"Escena no dibujada: {e}")

    # Rásteres del IVC
    if activas.get("ivc_raster"):
        calor, _ = mod_ivc.rasters_version(cfg, opciones.get("ivc_version", cfg["ivc"]["version_principal"]))
        if calor:
            s = rasteres.superponer_rgba(cfg, calor)
            mapas.agregar_superposicion(fg(f"IVC — {mod_ivc.titulo_version(cfg, opciones.get('ivc_version', cfg['ivc']['version_principal']))}"), s, f"IVC — {mod_ivc.titulo_version(cfg, opciones.get('ivc_version', cfg['ivc']['version_principal']))}", opacidad=opa["raster_ivc"], zindex=3)
            leyendas.append(mapas.leyenda_clases(cfg, "IVC (mapa de calor)"))
        else:
            st.info("Ráster del IVC no disponible para esa versión.")
    if activas.get("pred_ivc"):
        calor, _ = mod_ivc.rasters_version(cfg, opciones.get("escenario", "ssp245_2050"))
        if calor:
            s = rasteres.superponer_rgba(cfg, calor)
            mapas.agregar_superposicion(fg(f"IVC futuro — {mod_ivc.titulo_version(cfg, opciones.get('escenario', 'ssp245_2050'))}"), s, f"IVC futuro — {mod_ivc.titulo_version(cfg, opciones.get('escenario', 'ssp245_2050'))}", opacidad=opa["raster_ivc"], zindex=4)
            stats["escenario"] = mod_ivc.titulo_version(cfg, opciones.get("escenario", "ssp245_2050"))
            if "IVC (mapa de calor)" not in "".join(leyendas):
                leyendas.append(mapas.leyenda_clases(cfg, "IVC futuro (mapa de calor)"))

    # Polígonos / líneas de referencia
    if activas.get("area"):
        for clave, nombre, color in (("sectores_roi", "Sectores CoastSat", col["area_estudio"]), ("sectores_atlas", "Sectores del atlas", "#8fb4d1")):
            if CAPAS[clave].disponible(cfg):
                gj = _geojson_capa(clave, vis["simplificacion_m"]["poligonos"], ("sector", "nombre", "km_inicio", "km_fin"))
                mapas.agregar_geojson(fg(nombre), gj, nombre, color=color, grosor=1.2, opacidad=0.8, relleno=color, opacidad_relleno=0.04,
                                      campos_tooltip=[c for c in ("sector", "nombre") if any(c in f["properties"] for f in gj["features"][:1])], dash="6 4")
    if activas.get("boca"):
        gj = _geojson_capa("boca_cienaga", 0, ("nombre", "nota"))
        mapas.agregar_geojson(fg("Boca de la Ciénaga (excluida)"), gj, "Boca de la Ciénaga (excluida)", color=col["boca_cienaga"], relleno=col["boca_cienaga"], opacidad_relleno=0.25, campos_tooltip=["nombre"], campos_popup=["nombre", "nota"])
    if activas.get("geomorfologia"):
        gj = _geojson_capa("geomorfologia", vis["simplificacion_m"]["poligonos"], None)
        campos = [c for c in list(gj["features"][0]["properties"].keys())[:6]] if gj.get("features") else []
        mapas.agregar_geojson(fg("Geomorfología (INVEMAR)"), gj, "Geomorfología (INVEMAR)", color="#b08968", relleno="#b08968", opacidad_relleno=0.25, grosor=0.8, campos_tooltip=campos[:3], campos_popup=campos)
    if activas.get("manglar"):
        gj = _geojson_capa("manglar", vis["simplificacion_m"]["poligonos"], None)
        campos = list(gj["features"][0]["properties"].keys())[:6] if gj.get("features") else []
        mapas.agregar_geojson(fg("Hidrografía y manglar (OSM)"), gj, "Hidrografía y manglar (OSM)", color="#2a9d8f", relleno="#2a9d8f", opacidad_relleno=0.3, grosor=0.6, campos_popup=campos)
    if activas.get("edificaciones"):
        gj = _geojson_capa("osm_edificaciones", 0, None)
        campos = list(gj["features"][0]["properties"].keys())[:6] if gj.get("features") else []
        mapas.agregar_geojson(fg("Edificaciones (OSM)"), gj, "Edificaciones (OSM)", color="#f4a261", relleno="#f4a261", opacidad_relleno=0.5, grosor=0.5, campos_popup=campos)
        stats["n_edificaciones"] = len(gj.get("features", []))
    if activas.get("ruta90"):
        gj = _geojson_capa("ruta90", 0, None)
        mapas.agregar_geojson(fg("Ruta 90"), gj, "Ruta 90", color=col["ruta90"], grosor=2.5, opacidad=0.9)

    # Transectos y tasas
    if activas.get("transectos"):
        gj = _geojson_capa("dsas_transectos", 0, ("TransOrder", "BaselineID", "Azimuth", "Length"))
        mapas.agregar_geojson(fg("Transectos DSAS"), gj, "Transectos DSAS", color=col["transectos_dsas"], grosor=gro["transectos"], opacidad=opa["transectos"],
                              campos_tooltip=["TransOrder"], campos_popup=["TransOrder", "BaselineID", "Azimuth", "Length"], alias={"TransOrder": "Transecto", "BaselineID": "Línea base", "Azimuth": "Azimut (°)", "Length": "Longitud (m)"})
        stats["n_transectos"] = len(gj.get("features", []))
    if activas.get("linea_base"):
        gj = _geojson_capa("linea_base", 0, ("ID", "lado"))
        mapas.agregar_geojson(fg("Línea base DSAS"), gj, "Línea base DSAS", color=col["linea_base"], grosor=1.5, dash="2 6", campos_tooltip=["lado"])
    if activas.get("tasas"):
        campo = opciones.get("campo_tasa", "LRR")
        gj = _geojson_capa("dsas_tasas", 0, ("TransOrder", "BaselineID", "ShrCount", "LRR", "LCI95", "LR2", "EPR", "EPRUNC", "NSM", "SCE", "WLR"))
        vals = [f["properties"].get(campo) for f in gj["features"] if f["properties"].get(campo) is not None]
        if vals:
            rampa = mapas.rampa_divergente(min(vals), max(vals), f"{campo} DSAS ({dsas.CAMPOS_TASAS.get(campo, ('', ''))[1]})")
            mapas.agregar_geojson(fg(f"Tasas DSAS ({campo})"), gj, f"Tasas DSAS ({campo})", grosor=3, opacidad=0.9, campos_tooltip=["TransOrder", campo],
                                  campos_popup=["TransOrder", "ShrCount", "LRR", "LCI95", "LR2", "EPR", "NSM", "SCE", "WLR"],
                                  alias={"TransOrder": "Transecto", "ShrCount": "N.º líneas", "LRR": "LRR (m/año)", "LCI95": "IC95 LRR", "LR2": "R² LRR", "EPR": "EPR (m/año)", "NSM": "NSM (m)", "SCE": "SCE (m)", "WLR": "WLR (m/año)"},
                                  funcion_estilo=lambda f, r=rampa, c=campo: {"color": r(f["properties"][c]) if f["properties"].get(c) is not None else col["sin_dato"]})
            mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption, _fmt_anio), "bottomleft")
            stats["n_transectos"] = len(gj["features"])
            stats[f"media_{campo}"] = sum(vals) / len(vals)
            stats["campo_tasa"] = campo

    # Polígonos clasificados por IVC (franjas 0‑500 m unidas a la clase de la versión)
    if activas.get("ivc_poligonos"):
        gj, n_sin = _franjas_ivc(opciones.get("ivc_version", cfg["ivc"]["version_principal"]))
        if gj:
            clases = cfg["ivc"]["clases"]
            mapas.agregar_geojson(fg("Franjas por clase de IVC"), gj, "Franjas por clase de IVC", grosor=0.4, opacidad=0.8, relleno="#999", opacidad_relleno=0.55,
                                  campos_tooltip=["id_ivc", "ivc", "clase"], campos_popup=["id_ivc", "dist_costa_km", "zona", "ivc", "clase"],
                                  alias={"id_ivc": "Transecto IVC", "dist_costa_km": "km desde Bocas de Ceniza", "ivc": "IVC (0‑1)", "clase": "Clase (1‑5)"},
                                  funcion_estilo=lambda f, cl=clases: {"fillColor": cl.get(int(f["properties"]["clase"]), {"color": col["sin_dato"]})["color"] if f["properties"].get("clase") is not None else col["sin_dato"],
                                                                        "color": cl.get(int(f["properties"]["clase"]), {"color": col["sin_dato"]})["color"] if f["properties"].get("clase") is not None else col["sin_dato"]})
            leyendas.append(mapas.leyenda_clases(cfg))
            stats["ivc_version"] = opciones.get("ivc_version", cfg["ivc"]["version_principal"])

    if activas.get("ruta90_prio"):
        from .predicciones import agregar_ruta90_prioridad

        res = agregar_ruta90_prioridad(fg("Ruta 90 por prioridad (v4)"), cfg, m)
        if res:
            stats["ruta90"] = res
    # Predicciones
    if activas.get("pred_lineas"):
        try:
            gp = mod_pred.cargar_lineas(cfg, opciones.get("variante", cfg["predicciones"]["variante_defecto"]))
            anio = opciones.get("anio_pred")
            sel = gp[(gp["anio"] == anio) | (gp["tipo"] == "observada")] if anio else gp
            gs = vectores.simplificar_para_mapa(sel, cfg, 2.0)
            gj = vectores.a_geojson(gs, cfg, ["linea", "tipo", "anio"])
            estilos = {"observada": (col["linea_seleccionada"], None, 2.0), "central": (col["prediccion_central"], None, gro["prediccion"]),
                       "p05": (col["prediccion_banda"], "4 6", 1.5), "p95": (col["prediccion_banda"], "4 6", 1.5), "persistencia": (col["prediccion_persistencia"], "10 6", 2.0)}
            mapas.agregar_geojson(fg(f"Líneas proyectadas ({anio or 'todas'})"), gj, f"Líneas proyectadas ({anio or 'todas'})", grosor=2, campos_tooltip=["linea", "tipo"],
                                  alias={"linea": "Línea", "tipo": "Tipo"},
                                  funcion_estilo=lambda f, e=estilos: {"color": e[f["properties"]["tipo"]][0], "dashArray": e[f["properties"]["tipo"]][1], "weight": e[f["properties"]["tipo"]][2]})
            stats["anio_pred"] = anio
            leyendas.append("<b>Líneas proyectadas</b><br>" + "<br>".join(
                f'<span style="display:inline-block;width:26px;border-top:3px {"dashed" if d else "solid"} {c};vertical-align:middle;margin-right:6px"></span>{mod_pred.TIPOS_LINEA[k][0]}'
                for k, (c, d, _) in estilos.items()))
        except CapaNoDisponible as e:
            st.info(str(e))

    # Líneas de costa
    tol = vis["simplificacion_m"]["lineas_fecha"]
    if activas.get("lineas_anuales"):
        gj = _geojson_coastsat_rango(str(estado["ini"]), str(estado["fin"]), tol)
        n = len(gj.get("features", []))
        if n > vis.get("max_lineas_todas", 800):
            gj["features"] = gj["features"][: vis["max_lineas_todas"]]
        if n:
            dec = [f["properties"]["anio_dec"] for f in gj["features"]]
            rampa = mapas.rampa_cronologica(cfg, min(dec), max(dec), "Año de imagen (CoastSat)")
            mapas.agregar_geojson(fg(f"Líneas CoastSat por fecha ({n})"), gj, f"Líneas CoastSat por fecha ({n})", grosor=gro["linea_anual"], opacidad=0.6, campos_tooltip=["fecha_txt", "satname", "lado"],
                                  campos_popup=["fecha_txt", "satname", "lado", "cob_pct", "largo_m"],
                                  alias={"fecha_txt": "Fecha de imagen", "satname": "Sensor", "lado": "Lado", "cob_pct": "Cobertura (%)", "largo_m": "Longitud (m)"},
                                  funcion_estilo=lambda f, r=rampa: {"color": r(f["properties"]["anio_dec"])})
            mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption, _fmt_anio), "bottomleft")
        stats["n_lineas_anuales"] = n
    if activas.get("lineas_rango") or estado["modo"] == "Todas del intervalo":
        gj = _geojson_rango(str(estado["ini"]), str(estado["fin"]), tol)
        n = len(gj.get("features", []))
        if n > vis.get("max_lineas_todas", 800):
            st.warning(f"{n} líneas en el intervalo; se dibujan solo las primeras {vis['max_lineas_todas']} por rendimiento. Reduzca el intervalo.")
            gj["features"] = gj["features"][: vis["max_lineas_todas"]]
        if n:
            dec = [f["properties"]["anio_dec"] for f in gj["features"]]
            rampa = mapas.rampa_cronologica(cfg, min(dec), max(dec), "Año de observación")
            mapas.agregar_geojson(fg(f"Líneas anuales del intervalo ({n})"), gj, f"Líneas anuales del intervalo ({n})", grosor=1.4, opacidad=0.75, campos_tooltip=["fecha_txt", "lado"],
                                  campos_popup=_campos(gj, ["fecha_txt", "epoca", "satname", "lado", "cob_pct", "largo_m", "UNCY"]), alias=ALIAS_LINEA,
                                  funcion_estilo=lambda f, r=rampa: {"color": r(f["properties"]["anio_dec"])})
            mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption, _fmt_anio), "bottomleft")
            stats["n_lineas_rango"] = n
    if activas.get("linea_ref") and estado["obs_rango"] and estado["obs_rango"][0].clave != estado["obs"].clave:
        o0 = estado["obs_rango"][0]
        gj = _geojson_fecha(o0.clave, tol)
        mapas.agregar_geojson(fg(f"Referencia {o0.fecha:%Y-%m-%d}"), gj, f"Referencia {o0.fecha:%Y-%m-%d}", color="#ffffff", grosor=2.0, opacidad=0.9, dash="6 5",
                              campos_tooltip=_campos(gj, ["fecha_txt", "epoca", "lado"]), campos_popup=_campos(gj, ["fecha_txt", "epoca", "lado", "largo_m", "UNCY"]), alias=ALIAS_LINEA)
        stats["ref"] = o0
        leyendas.append(f'<b>Líneas de costa</b><br><span style="display:inline-block;width:26px;border-top:3px dashed #ffffff;background:#4a5568;vertical-align:middle;margin-right:6px"></span>Referencia {o0.fecha:%Y}'
                        f'<br><span style="display:inline-block;width:26px;border-top:3px solid {col["linea_seleccionada"]};vertical-align:middle;margin-right:6px"></span>Seleccionada {estado["obs"].fecha:%Y}')
    if activas.get("linea_sel"):
        gj = _geojson_fecha(estado["obs"].clave, tol)
        mapas.agregar_geojson(fg(f"Línea de costa {estado['obs'].fecha:%Y-%m-%d}"), gj, f"Línea de costa {estado['obs'].fecha:%Y-%m-%d}", color=col["linea_seleccionada"], grosor=gro["linea_fecha"], opacidad=opa["lineas"],
                              campos_tooltip=_campos(gj, ["fecha_txt", "epoca", "lado"]), campos_popup=_campos(gj, ["fecha_txt", "epoca", "satname", "lado", "cob_pct", "largo_m", "UNCY", "n_tramos", "clase"]),
                              alias=ALIAS_LINEA)
        stats["n_lineas_sel"] = len(gj.get("features", []))

    # Proyectos de la Calculadora IVC (capas exportadas en resultados/calculadora/<proyecto>)
    if any(activas.get(k) for k in CP.ARCHIVOS):
        proys = CP.proyectos(cfg)
        nombre_p = opciones.get("calc_proyecto") or (next(iter(proys)) if proys else None)
        if nombre_p in proys:
            try:
                st_calc = CP.agregar_capas(fg, m, cfg, proys[nombre_p], activas, opciones.get("calc_campo", "LRR"), opciones.get("calc_esquema", "ewm"), opciones.get("calc_escenario"),
                                           prefijo=f"[{nombre_p}] ")
                stats["calculadora"] = {"proyecto": nombre_p, **st_calc}
            except Exception as e:  # noqa: BLE001
                logging.getLogger("geovisor").warning("Capas del proyecto %s: %s", nombre_p, e)
                stats["calculadora_error"] = str(e)

    for ly in leyendas:
        mapas.agregar_leyenda_html(m, ly, "bottomright")
    stats["_leyendas_html"] = mapas.leyendas_html(m)
    return m, capas, stats


@st.cache_data(ttl=3600, show_spinner=False)
def _franjas_ivc(version: str) -> tuple[dict | None, int]:
    cfg = _cfg()
    try:
        fr = vectores.leer_capa(cfg, "ivc_franjas")
        tr = mod_ivc.cargar_transectos_ivc(cfg)
    except CapaNoDisponible:
        return None, 0
    c_ivc, c_cl = mod_ivc.columnas_version(tr, version)
    if not c_ivc:
        return None, 0
    cols = ["id_ivc", "dist_costa_km", "zona", c_ivc] + ([c_cl] if c_cl else [])
    t = pd.DataFrame(tr[cols]).rename(columns={c_ivc: "ivc", c_cl: "clase"} if c_cl else {c_ivc: "ivc"})
    if "clase" not in t:
        t["clase"] = mod_ivc.clasificar(t["ivc"], cfg)
    id_fr = "id_ivc" if "id_ivc" in fr.columns else fr.columns[0]
    u = fr[[id_fr, "geometry"]].merge(t, left_on=id_fr, right_on="id_ivc", how="left")
    import geopandas as gpd

    u = gpd.GeoDataFrame(u, geometry="geometry", crs=fr.crs)
    if id_fr != "id_ivc":
        u = u.drop(columns=[id_fr])
    gs = vectores.simplificar_para_mapa(u, cfg, cfg["visualizacion"]["simplificacion_m"]["poligonos"])
    return vectores.a_geojson(gs, cfg, ["id_ivc", "dist_costa_km", "zona", "ivc", "clase"]), int(u["ivc"].isna().sum())


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
def render(cfg: dict) -> None:
    try:
        g = _lineas_fecha(0)
    except CapaNoDisponible as e:
        ui.vacio("Sin líneas de costa por fecha", f"{e}. Configure `rutas.exportar_coastsat` en config.yaml.")
        return
    obs = temporal.observaciones(g)
    if not obs:
        ui.vacio("No se identificaron fechas válidas", "El campo 'fecha' no pudo interpretarse.")
        return

    izq, centro, der = st.columns([1.05, 2.7, 1.0], gap="small")
    with izq:
        estado = control_temporal(cfg, obs, "visor")
        activas = panel_capas(cfg, "visor")
        opciones = {}
        with st.expander("Opciones de capas", expanded=False):
            if any(activas.get(k) for k in CP.ARCHIVOS):
                proys = CP.proyectos(cfg)
                if proys:
                    opciones["calc_proyecto"] = st.selectbox("Proyecto de la Calculadora", list(proys), key="visor_calc_proyecto")
                    carpeta_p = proys[opciones["calc_proyecto"]]
                    if activas.get("calc_tasas"):
                        opciones["calc_campo"] = st.selectbox("Tasa del proyecto", CP.TASAS, key="visor_calc_campo")
                    if activas.get("calc_ivc"):
                        meta = CP.metadatos(carpeta_p)
                        esq = ["ewm", "iguales", "fahp", "fahp_ewm", "manual", "topsis_ewm"]
                        opciones["calc_esquema"] = st.selectbox("Esquema de pesos", esq, index=esq.index(meta.get("ponderacion", {}).get("esquema_principal", "ewm")) if meta.get("ponderacion", {}).get("esquema_principal", "ewm") in esq else 0, key="visor_calc_esquema")
                    if activas.get("calc_escenario"):
                        escs = CP.escenarios_de(carpeta_p)
                        if escs:
                            opciones["calc_escenario"] = st.selectbox("Escenario del proyecto", escs, key="visor_calc_escenario")
            if activas.get("tasas"):
                opciones["campo_tasa"] = st.selectbox("Campo de tasa DSAS", list(dsas.CAMPOS_TASAS), index=0, key="visor_campo_tasa")
            if activas.get("ivc_raster") or activas.get("ivc_poligonos"):
                vers = mod_ivc.versiones(cfg)
                opc = [v for v in vers["version"] if v not in mod_ivc.ESCENARIOS] or [cfg["ivc"]["version_principal"]]
                opciones["ivc_version"] = st.selectbox("Versión del IVC", opc, index=0, key="visor_ivc_version", format_func=lambda v: mod_ivc.titulo_version(cfg, v))
            if activas.get("pred_ivc"):
                opciones["escenario"] = st.selectbox("Escenario SSP", list(mod_ivc.ESCENARIOS), key="visor_escenario", format_func=lambda v: mod_ivc.titulo_version(cfg, v))
            if activas.get("pred_lineas"):
                vd = mod_pred.variantes_disponibles(cfg)
                opciones["variante"] = st.selectbox("Variante de proyección", list(vd), key="visor_variante", format_func=lambda k: vd[k])
                try:
                    anios = mod_pred.anios_procesados(mod_pred.cargar_lineas(cfg, opciones["variante"]))
                except CapaNoDisponible:
                    anios = []
                opciones["anio_pred"] = st.selectbox("Año objetivo (solo procesados)", anios, key="visor_anio_pred") if anios else None
            if activas.get("escena"):
                esc = _escenas(0)
                sitios = sorted(esc["sitio"].dropna().unique())
                sitio = st.selectbox("Sector CoastSat", sitios, key="visor_sitio")
                e2 = esc[esc["sitio"] == sitio]
                # la escena más próxima a la fecha seleccionada se propone por defecto
                dif = (e2["fecha"] - estado["obs"].fecha).abs()
                idx_def = int(dif.argmin()) if len(e2) else 0
                nombres = e2["nombre"].tolist()
                nom = st.selectbox("Escena (fecha de adquisición)", nombres, index=idx_def, key=f"visor_escena_{sitio}")
                fila = e2[e2["nombre"] == nom].iloc[0]
                opciones["escena_ruta"], opciones["escena_nombre"] = fila["ruta"], nom
                if abs((fila["fecha"] - estado["obs"].fecha).days) > 0:
                    ui.nota(f"La escena ({fila['fecha']:%Y-%m-%d}) no coincide con la fecha de la línea seleccionada ({estado['obs'].fecha:%Y-%m-%d}); se muestra solo como referencia.")
        if not _hay_escenas(cfg):
            ui.nota("Las escenas Landsat aparecen tras generar el catálogo en «Datos y metodología».")

    with centro:
        barra_tiempo(cfg, obs, estado, "visor")
        c1, c2, c3, c4 = st.columns([1.6, 1.4, 1, 1])
        bases = [b["nombre"] for b in cfg["mapa"]["mapas_base"]]
        mapa_base = c1.selectbox("Mapa base", bases, index=bases.index(cfg["mapa"]["mapa_base_defecto"]) if cfg["mapa"]["mapa_base_defecto"] in bases else 0, key="visor_base", label_visibility="collapsed")
        sectores = _sectores_zoom()
        zona = c2.selectbox("Acercar a", ["Toda la barra"] + list(sectores), key="visor_zona", label_visibility="collapsed", help="Encuadra un sector para apreciar el cambio de la línea de costa (decenas a cientos de metros)")
        vista = None  # ((lat, lon), zoom) que se aplica una sola vez al mapa ya dibujado
        if zona != st.session_state.get("visor_zona_prev"):
            primera_vez = "visor_zona_prev" not in st.session_state
            st.session_state["visor_zona_prev"] = zona
            if not primera_vez:
                vista = mapas.vista_para_bounds(sectores[zona] if zona in sectores else _bounds_datos(0))
        if c3.button("Encuadrar datos", use_container_width=True, key="visor_fit"):
            vista = mapas.vista_para_bounds(_bounds_datos(0))
        if c4.button("Restablecer vista", use_container_width=True, key="visor_reset"):
            mc = cfg["mapa"]
            vista = mapas.vista_para_bounds(_bounds_datos(0)) if mc.get("ajustar_a_datos") else ((mc["centro"][1], mc["centro"][0]), mc.get("zoom_inicial", 11))
        bounds = _bounds_datos(0) if cfg["mapa"].get("ajustar_a_datos") else None
        with st.spinner("Dibujando el mapa…"):
            m, capas, stats = construir_mapa(cfg, estado, activas, mapa_base, bounds, opciones)
        ui.mostrar_mapa(m, 640, "mapa_visor", vista=vista, capas=capas)
        if stats.get("_leyendas_html"):
            st.markdown(stats["_leyendas_html"], unsafe_allow_html=True)
        ui.nota("El encuadre y el zoom se conservan al cambiar de fecha · línea punteada blanca = primera observación del intervalo (referencia) · línea amarilla = fecha seleccionada · clic en una entidad para ver sus atributos.")
        with st.expander("Tabla de atributos de la línea seleccionada"):
            sel = temporal.seleccionar_fecha(g, estado["obs"].fecha)
            ui.tabla_atributos(sel.drop(columns=["fecha_dt"]))
            ui.descargas(sel.drop(columns=["fecha_dt"]), f"linea_costa_{estado['obs'].fecha:%Y%m%d}", cfg, "visor_exp")

    with der:
        panel_estadisticas(cfg, g, estado, stats, activas)
    avance_automatico(estado, "visor")


def panel_estadisticas(cfg: dict, g, estado: dict, stats: dict, activas: dict) -> None:
    ui.panel("Estadísticas de la vista", "grafico", "se actualizan con la fecha y las capas")
    o = estado["obs"]
    sel = temporal.seleccionar_fecha(g, o.fecha)
    obs_r = estado["obs_rango"]
    serie_largo = [x.largo_m for x in obs_r[-40:]]
    serie_cob = [x.cobertura_media for x in obs_r[-40:]]
    es_anual = o.satelites == ("anual",)
    ui.kpi("Fecha seleccionada", f"{o.fecha:%Y-%m-%d}", "", "Fecha representativa de la línea anual (campo DATE_ de DSAS)" if es_anual else "Fecha y hora de adquisición de la imagen (UTC)", ic="calendario", tono="azul")
    if es_anual:
        ui.kpi("Época", o.epoca or None, "", "Época de la línea anual (mediana de las imágenes del año, corregida por marea)", ic="capas", tono="teal")
        ui.kpi("Incertidumbre DSAS", o.uncy_m, "m", "Campo UNCY usado por DSAS para ponderar (WLR) y el IC95", 1, "DSAS", ic="regla", tono="gris")
    else:
        ui.kpi("Sensor", "/".join(o.satelites) or None, "", "Satélite Landsat", ic="satelite", tono="teal")
    n_vis = (stats.get("n_lineas_sel", 0) if activas.get("linea_sel") else 0) + stats.get("n_lineas_rango", 0) + stats.get("n_lineas_anuales", 0)
    ui.kpi("Líneas visibles", int(n_vis) if n_vis else None, "entidades", "", ic="lineas", tono="ambar")
    fuente_largo = str(sel["largo_fuente"].iloc[0]) if "largo_fuente" in sel and len(sel) else "geovisor"
    ui.kpi("Longitud de la línea", o.largo_m, "m", ("Campo 'largo_m' del archivo" if fuente_largo == "importado" else "Longitud calculada por el geovisor en EPSG:32618 (ambos lados)") + "; mini‑gráfico: últimas 40 observaciones del intervalo", 0, fuente_largo, ic="regla", tono="azul", serie=serie_largo)
    if fuente_largo == "importado":
        mg = dsas.metricas_geovisor_lineas(sel, cfg)
        ui.kpi("Longitud (recalculada)", mg.get("longitud_m"), "m", "Longitud geodésica calculada por el geovisor en EPSG:32618", 0, "geovisor", ic="regla", tono="gris")
    if o.cobertura_media is not None and o.cobertura_media == o.cobertura_media:
        ui.kpi("Cobertura media", o.cobertura_media, "%", "Porcentaje de la costa cubierto por la línea (campo 'cob_pct')", 1, "importado", ic="porcentaje", tono="teal", serie=serie_cob, progreso=(o.cobertura_media or 0) / 100)
    if stats.get("ref") is not None:
        r = stats["ref"]
        d = _distancia_media(o.clave, r.clave)
        ui.kpi(f"Distancia media a {r.fecha:%Y}", d.get("media"), "m", f"Distancia (sin signo) entre la línea seleccionada y la de referencia, muestreada cada 100 m en EPSG:32618 (máx. {d.get('max', 0):.0f} m)", 1, "geovisor", ic="regla", tono="coral")
        if o.largo_m is not None and r.largo_m is not None:
            ui.kpi(f"Cambio de longitud vs {r.fecha:%Y}", o.largo_m - r.largo_m, "m", "Longitud de la línea seleccionada menos la de referencia", 0, "geovisor", ic="lineas", tono="gris")
    ui.kpi("Transectos", stats.get("n_transectos"), "", "Transectos DSAS dibujados", ic="capas", tono="gris")
    campo = stats.get("campo_tasa")
    tasa = stats.get(f"media_{campo}") if campo else None
    ui.kpi(f"Tasa media {campo or 'LRR'}", tasa, dsas.CAMPOS_TASAS.get(campo or "LRR", ("", "m/año"))[1], "Media aritmética de los transectos DSAS dibujados", 2, "DSAS" if campo else None, ic="trend_down" if (tasa or 0) < 0 else "trend", tono="coral" if (tasa or 0) < 0 else "teal")
    if activas.get("ivc_raster") or activas.get("ivc_poligonos"):
        try:
            tr = mod_ivc.cargar_transectos_ivc(cfg)
            v = stats.get("ivc_version", cfg["ivc"]["version_principal"])
            c_ivc, c_cl = mod_ivc.columnas_version(tr, v)
            est = mod_ivc.estadisticas(tr, c_ivc, c_cl, cfg) if c_ivc else {}
            ui.kpi(f"IVC medio ({v})", est.get("media"), "0‑1", "Media del IVC por transecto (671 transectos cada 100 m)", 3, "modelo", ic="escudo", tono="coral", progreso=est.get("media"))
            if est.get("km_por_clase"):
                ui.kpi("Costa en clase alta/muy alta", est.get("km_por_clase", {}).get(4, 0) + est.get("km_por_clase", {}).get(5, 0), "km", "Transectos ×0,1 km", 1, ic="alerta", tono="ambar")
        except CapaNoDisponible:
            pass
    sc = stats.get("calculadora")
    if sc:
        ui.kpi(f"Proyecto «{sc['proyecto']}»: tasa media {sc.get('campo_tasa', '')}", sc.get("tasa_media"), "m/año", "Media de los transectos del proyecto calculado", 2, "calculadora", ic="trend", tono="teal")
        ui.kpi(f"Proyecto «{sc['proyecto']}»: IVC medio", sc.get("ivc_medio"), "0‑1", f"{sc.get('pct_alta', 0):.1f} % de transectos en clase alta/muy alta", 3, "calculadora", ic="escudo", tono="coral", progreso=sc.get("ivc_medio"))
    ui.kpi("Año / escenario de predicción", (f"{stats['anio_pred']}" if stats.get("anio_pred") else None) or stats.get("escenario"), "", "Solo horizontes procesados", ic="cristal", tono="azul")
    ui.nota("Solo se muestran los indicadores con dato para la vista actual (p. ej. el IVC medio al activar una capa del IVC); nunca se sustituye un dato ausente por cero.")
    with st.expander("Gráfico temporal"):
        df = temporal.serie_longitud(estado["obs_rango"])
        if df["largo_m"].notna().any():
            ui.grafico(graficos.longitud_por_fecha(df, o.fecha))
        else:
            ui.vacio("Sin datos de longitud", "El campo 'largo_m' no está disponible.")
