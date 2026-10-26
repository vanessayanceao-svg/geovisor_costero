"""Sección 8 — Calculadora IVC: asistente que calcula un índice de vulnerabilidad costera a partir de insumos propios.

Pasos: 1 Insumos · 2 Transectos y tasas · 3 Variables · 4 Ponderación · 5 Índice y validación · 6 Proyección · 7 Exportar.
El estado vive en ``st.session_state["calc"] = {"p": proyecto, "res": resultados}``; los resultados se escriben en
``resultados/calculadora/<nombre>/``. El motor está en ``src/calculo`` y reproduce el método de la tesis (ver README).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from .. import graficos, mapas, vectores
from ..calculo import proyecto as PJ, ejemplos, indice as IN, ponderacion as PO
from ..configuracion import rutas_salida
from . import comunes as ui
from .visor import _cfg

PASOS = ["Insumos", "Transectos y tasas", "Variables", "Ponderación", "Índice y validación", "Proyección", "Exportar"]
COLS_VAR = ["activa", "codigo", "nombre", "dimension", "metodo", "fuente", "capa", "campo", "estadistico", "d0", "d1", "umbral", "normalizacion", "cortes", "clases", "cerrado", "mapa_clases",
            "mayor_mas_vulnerable", "rol", "filtro", "ventana", "constante"]


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
def _estado() -> dict:
    if "calc" not in st.session_state:
        st.session_state["calc"] = {"p": PJ.nuevo_proyecto(), "res": {}}
    return st.session_state["calc"]


def K(nombre: str) -> str:
    """Clave de widget con número de versión del proyecto: al cargar otro proyecto cambian todas las claves y los widgets
    se reinician desde la configuración nueva (borrar session_state no basta: el navegador reenvía el valor anterior)."""
    return f"{nombre}_v{st.session_state.get('calc_ver', 0)}"


def _reset_widgets() -> None:
    st.session_state["calc_ver"] = st.session_state.get("calc_ver", 0) + 1


def _cargar(p_nuevo: dict) -> None:
    """Callback (se ejecuta antes de dibujar los widgets): sustituye el proyecto y reinicia los widgets."""
    st.session_state["calc"] = {"p": p_nuevo, "res": {}}
    _reset_widgets()


def _carpeta(p: dict) -> Path:
    cfg = _cfg()
    base = Path(rutas_salida(cfg).get("reportes", "resultados/reportes")).parent / "calculadora"
    return base / (p.get("nombre") or "proyecto")


def _invalidar(res: dict, desde: str) -> None:
    """Borra los resultados de los pasos posteriores al que cambia."""
    orden = ["transectos", "variables", "pesos", "indice", "proyeccion"]
    for k in orden[orden.index(desde):]:
        res.pop(k, None)


def _ok(res: dict, paso: str) -> bool:
    return paso in res


_SECCIONES_FIRMA = {
    "transectos": ("epsg", "lineas", "linea_base", "transectos"),
    "variables": ("epsg", "lineas", "linea_base", "transectos", "variables"),
    "pesos": ("variables", "ponderacion"),
    "indice": ("variables", "ponderacion", "indice"),
    "proyeccion": ("variables", "ponderacion", "indice", "proyeccion"),
}


def _firma(p: dict, paso: str) -> str:
    """Huella de los parámetros del proyecto que determinan el resultado de un paso (trazabilidad)."""
    import hashlib

    def canon(o):  # misma huella aunque un widget devuelva 325 en vez de 325.0 o una tupla en vez de una lista
        if isinstance(o, bool):
            return o
        if isinstance(o, (int, float, np.integer, np.floating)):
            return None if (isinstance(o, float) and o != o) else round(float(o), 9)
        if isinstance(o, dict):
            return {str(k): canon(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0])) if not str(k).startswith("_")}
        if isinstance(o, (list, tuple, np.ndarray)):
            return [canon(v) for v in o]
        return o if o is None or isinstance(o, str) else str(o)

    sub = {k: canon(p.get(k)) for k in _SECCIONES_FIRMA[paso]}
    return hashlib.md5(json.dumps(sub, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _sellar(p: dict, res: dict, paso: str) -> None:
    if paso in res and isinstance(res[paso], dict):
        res[paso]["_firma"] = _firma(p, paso)


def _comprobar_vigencia(p: dict, res: dict) -> bool:
    """Descarta los resultados calculados con parámetros que ya no coinciden con los del proyecto (y los pasos posteriores)."""
    for paso in ("transectos", "variables", "pesos", "indice", "proyeccion"):
        if paso in res and isinstance(res[paso], dict) and res[paso].get("_firma") and res[paso]["_firma"] != _firma(p, paso):
            logging.getLogger("geovisor").info("Calculadora: parámetros del paso %s cambiados; se descarta el resultado", paso)
            _invalidar(res, paso)
            st.session_state["calc_aviso_vigencia"] = paso
            return True
    return False


def _badge(ok: bool, texto: str) -> str:
    return f'<span class="gv-chip" style="background:{"#19B3A6" if ok else "#E6EBF5"};color:{"#fff" if ok else "#55596a"};padding:2px 10px;border-radius:999px;font-size:.72rem;font-weight:700">{texto}</span>'


# ---------------------------------------------------------------------------
# Mapas auxiliares
# ---------------------------------------------------------------------------
def _mapa_base(cfg, g):
    b = vectores.bounds_visual(g, cfg)
    return mapas.crear_mapa(cfg, bounds=b, mapa_base="Esri World Imagery")


def _lineas_geojson(cfg, g, campo="_fecha"):
    gs = vectores.simplificar_para_mapa(g.assign(fecha_txt=g[campo].astype(str)), cfg, 3.0)
    return vectores.a_geojson(gs, cfg, ["fecha_txt"])


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
def render(cfg: dict) -> None:
    ui.seccion("Calculadora IVC", "cerebro", "calcule un índice de vulnerabilidad costera con sus propios insumos: transectos, tasas, variables, ponderación, validación y proyección")
    est = _estado(); p, res = est["p"], est["res"]

    with st.container():
        c = st.columns([2.2, 1, 1, 1, 1])
        with c[0]:
            nombre = st.text_input("Nombre del proyecto", p.get("nombre", "proyecto"), key=K("calc_nombre"), help="Carpeta de salida: resultados/calculadora/<nombre>")
            if nombre != p.get("nombre"):
                p["nombre"] = nombre.strip().replace(" ", "_") or "proyecto"
        with c[1]:
            epsg = st.number_input("EPSG métrico", 2000, 99999, int(p.get("epsg", 32618)), key=K("calc_epsg"), help="CRS proyectado en metros para todas las operaciones (p. ej. 32618 = UTM 18N)")
            if epsg != p.get("epsg"):
                p["epsg"] = int(epsg); _invalidar(res, "transectos")
        with c[2]:
            ui.hueco_etiqueta()
            st.button("Cargar ejemplo (tesis)", use_container_width=True, key=K("calc_ejemplo"), help="Rellena el proyecto con los insumos de la tesis (DSAS + tabla de variables)",
                      on_click=lambda: _cargar(ejemplos.ejemplo_salamanca(cfg)))
        with c[3]:
            ui.hueco_etiqueta()
            st.button("Nuevo proyecto", use_container_width=True, key=K("calc_nuevo"), on_click=lambda: _cargar(PJ.nuevo_proyecto()))
        with c[4]:
            ui.hueco_etiqueta()
            sub = st.file_uploader("Abrir proyecto.json", type=["json"], key="calc_abrir_json", label_visibility="collapsed")
            if sub is not None and st.session_state.get("_calc_json_cargado") != sub.name + str(sub.size):
                try:
                    st.session_state["_calc_json_cargado"] = sub.name + str(sub.size)
                    _cargar(json.load(sub)); st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo leer: {e}")
    st.caption(f"Salida: {_ruta_corta(_carpeta(p))}")
    if st.session_state.get("calc_aviso_vigencia"):
        st.warning(f"Cambió un parámetro del paso «{st.session_state.pop('calc_aviso_vigencia')}»: ese resultado y los posteriores se descartaron; vuelva a calcularlos.", icon="⚠️")

    hechos = {1: "_lineas" in res, 2: _ok(res, "transectos"), 3: _ok(res, "variables"), 4: _ok(res, "pesos"), 5: _ok(res, "indice"), 6: _ok(res, "proyeccion"), 7: bool(st.session_state.get("calc_escritos"))}
    st.markdown(_css_pasos(hechos), unsafe_allow_html=True)
    with st.container(key="calc_pasos"):
        tabs = st.tabs(PASOS)
    with tabs[0]:
        _paso_insumos(cfg, p, res)
    with tabs[1]:
        _paso_transectos(cfg, p, res)
    with tabs[2]:
        _paso_variables(cfg, p, res)
    with tabs[3]:
        _paso_ponderacion(cfg, p, res)
    with tabs[4]:
        _paso_indice(cfg, p, res)
    with tabs[5]:
        _paso_proyeccion(cfg, p, res)
    with tabs[6]:
        _paso_exportar(cfg, p, res)
    if _comprobar_vigencia(p, res) or (("_lineas" in res) != hechos[1]):   # el asistente se redibuja con el estado final de este ciclo
        st.rerun()


def _css_pasos(hechos: dict) -> str:
    """Pestañas del asistente como pasos numerados: círculo con el número, teal si está completo, degradado si está activo."""
    base = """
<style>
.st-key-calc_pasos [role="tablist"] { gap:8px; background:var(--card); padding:8px; border-radius:16px; border:1px solid var(--borde); box-shadow:var(--sombra); flex-wrap:wrap; }
.st-key-calc_pasos .react-aria-SelectionIndicator { display:none !important; }
.st-key-calc_pasos [data-testid="stTab"] { border-radius:12px !important; padding:7px 14px 7px 7px !important; background:var(--card2); border:1px solid var(--borde); height:auto !important; transition:all .2s; cursor:pointer; }
.st-key-calc_pasos [data-testid="stTab"] p { font-size:.86rem !important; font-weight:600 !important; color:var(--texto2) !important; display:flex; align-items:center; gap:9px; margin:0; }
.st-key-calc_pasos [data-testid="stTab"] p::before { content:"•"; display:inline-flex; width:26px; height:26px; border-radius:50%; align-items:center; justify-content:center; background:#E6EBF5; color:#55596a; font-weight:800; font-size:.8rem; flex:none; }
.st-key-calc_pasos [data-testid="stTab"][aria-selected="true"] { background:linear-gradient(135deg,#3B6CF0,#7C5CF6) !important; border-color:transparent; box-shadow:0 8px 20px rgba(59,108,240,.3); }
.st-key-calc_pasos [data-testid="stTab"][aria-selected="true"] p { color:#fff !important; }
.st-key-calc_pasos [data-testid="stTab"][aria-selected="true"] p::before { background:rgba(255,255,255,.25); color:#fff; }
.st-key-calc_pasos [data-testid="stTab"]:hover { border-color:#3B6CF0; }
.st-key-calc_pasos [data-testid="stTab"][aria-selected="true"]::after { display:none; }
/* pestañas internas de cada paso: estilo general (sin numeración) */
.st-key-calc_pasos [class*="st-key-calc_sub"] [role="tablist"] { gap:4px; background:var(--card2); padding:5px; border-radius:14px; box-shadow:inset 0 1px 3px rgba(27,36,64,.06); }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"] { padding:7px 15px !important; background:transparent !important; border:1px solid transparent !important; border-radius:10px !important; box-shadow:none; }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"] p { font-size:.82rem !important; gap:0; }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"] p::before { content:none !important; display:none !important; }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"]:hover { background:var(--pill) !important; }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"][aria-selected="true"] { background:var(--card) !important; border-color:var(--borde) !important; box-shadow:0 4px 12px rgba(27,36,64,.10); }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"][aria-selected="true"] p { color:#3B6CF0 !important; }
.st-key-calc_pasos [class*="st-key-calc_sub"] [data-testid="stTab"][aria-selected="true"]::after { display:block; }
"""
    for i in range(1, 8):
        marca = "✓" if hechos.get(i) else str(i)
        base += f'.st-key-calc_pasos [data-testid="stTab"]:nth-child({i}) p::before {{ content:"{marca}"; }}\n'
        if hechos.get(i):
            base += f'.st-key-calc_pasos [data-testid="stTab"]:nth-child({i}):not([aria-selected="true"]) p::before {{ background:#19B3A6; color:#fff; }}\n'
            base += f'.st-key-calc_pasos [data-testid="stTab"]:nth-child({i}):not([aria-selected="true"]) {{ border-color:#19B3A6; }}\n'
    return base + "</style>"


# ---------------------------------------------------------------------------
# Paso 1
# ---------------------------------------------------------------------------
TIPOS_VECTOR = ["gpkg", "geojson", "json", "shp", "dbf", "shx", "prj", "cpg", "zip", "kml"]
TIPOS_RASTER = ["tif", "tiff"]
TIPOS_TABLA = ["csv", "xlsx"]


def _ruta_corta(r: Path) -> str:
    """Ruta relativa a la carpeta del geovisor cuando es posible (no se muestran rutas absolutas del equipo)."""
    try:
        return str(Path(r).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(r)


def _carpeta_insumos(p: dict) -> Path:
    d = _carpeta(p) / "insumos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _guardar_subidos(p: dict, archivos) -> str | None:
    """Guarda los archivos subidos en resultados/calculadora/<proyecto>/insumos y devuelve la ruta principal.
    Un shapefile se sube con sus 3‑5 archivos (o un .zip); se devuelve el .shp / .gpkg / .tif / .csv."""
    import zipfile

    if not archivos:
        return None
    d = _carpeta_insumos(p)
    rutas = []
    for a in archivos:
        destino = d / a.name
        with open(destino, "wb") as f:
            f.write(a.getbuffer())
        if a.name.lower().endswith(".zip"):
            with zipfile.ZipFile(destino) as z:
                z.extractall(d)
                rutas.extend(d / n for n in z.namelist() if not n.endswith("/"))
        else:
            rutas.append(destino)
    for ext in (".shp", ".gpkg", ".geojson", ".json", ".kml", ".tif", ".tiff", ".csv", ".xlsx"):
        for r in rutas:
            if str(r).lower().endswith(ext):
                return str(r)
    return str(rutas[0]) if rutas else None


def _selector_archivo(p: dict, etiqueta: str, valor: str, key: str, tipos: list[str], ayuda: str = "") -> str:
    """Dos formas de indicar un archivo: subirlo (se copia a la carpeta del proyecto) o escribir su ruta en el equipo."""
    c1, c2 = st.columns([1.3, 1.7])
    with c1:
        sub = st.file_uploader(f"{etiqueta} — subir archivo(s)", type=tipos, accept_multiple_files=True, key=key + "_up",
                               help=(ayuda + " " if ayuda else "") + "Shapefile: seleccione .shp + .dbf + .shx + .prj a la vez (o un .zip). Recomendado: GeoPackage, GeoJSON, GeoTIFF o CSV.")
        if sub:
            firma = ";".join(f"{a.name}:{a.size}" for a in sub)
            if st.session_state.get(key + "_firma") != firma:
                r = _guardar_subidos(p, sub)
                if r:
                    st.session_state[key + "_firma"] = firma
                    st.session_state[key + "_ruta"] = r
                    valor = r
    with c2:
        r = st.text_input(f"{etiqueta} — o ruta en el equipo", st.session_state.get(key + "_ruta", valor) or "", key=key + "_txt", help="p. ej. D:/datos/mi_capa.gpkg")
        if r and not os.path.exists(r):
            st.caption(f"⚠️ No existe: {r}")
        elif r:
            st.caption(f"✔ {os.path.basename(r)}")
    return r


def _ruta_input(etiqueta, valor, key, ayuda=""):
    r = st.text_input(etiqueta, valor or "", key=key, help=ayuda)
    if r and not os.path.exists(r):
        st.caption(f"⚠️ No existe: {r}")
    return r


@st.cache_data(ttl=600, show_spinner=False)
def _info_archivo(ruta: str, capa: str | None = None) -> dict:
    """Campos, capas y categorías de un archivo (para rellenar los desplegables)."""
    out = {"tipo": "", "capas": [], "campos": [], "numericos": [], "categorias": {}, "crs": "", "error": ""}
    try:
        low = ruta.lower()
        if low.endswith((".tif", ".tiff")):
            import rasterio

            with rasterio.open(ruta) as src:
                out.update(tipo="raster", crs=str(src.crs), bandas=src.count, res=float(src.res[0]), nodata=src.nodata)
            return out
        if low.endswith((".csv", ".xlsx")):
            d = pd.read_csv(ruta, nrows=2000, encoding="utf-8-sig") if low.endswith(".csv") else pd.read_excel(ruta, nrows=2000)
            out.update(tipo="tabla", campos=list(d.columns), numericos=[c for c in d.columns if pd.api.types.is_numeric_dtype(d[c])])
            return out
        import geopandas as gpd
        import pyogrio

        if low.endswith(".gpkg"):
            out["capas"] = [x[0] for x in pyogrio.list_layers(ruta)]
            if not capa:
                capa = out["capas"][0] if out["capas"] else None
        g = gpd.read_file(ruta, layer=capa) if capa else gpd.read_file(ruta)
        out.update(tipo="vector", crs=str(g.crs), geom=str(g.geom_type.mode().iloc[0]) if len(g) else "", n=len(g))
        out["campos"] = [c for c in g.columns if c != "geometry"]
        out["numericos"] = [c for c in out["campos"] if pd.api.types.is_numeric_dtype(g[c])]
        for c in out["campos"]:
            if not pd.api.types.is_numeric_dtype(g[c]):
                u = g[c].dropna().astype(str).str.strip().unique()
                if 0 < len(u) <= 40:
                    out["categorias"][c] = sorted(u.tolist())
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _paso_insumos(cfg, p, res):
    ui.panel("Líneas de costa (obligatorio)", "lineas", "una entidad por fecha; shapefile, GeoPackage o GeoJSON con CRS")
    l = p["lineas"]
    r = _selector_archivo(p, "Líneas de costa", l["ruta"], K("calc_lin_ruta"), TIPOS_VECTOR, "Una entidad (línea) por fecha, con un campo de fecha.")
    if r != l["ruta"]:
        l["ruta"] = r; _invalidar(res, "transectos")
    info = _info_archivo(r) if r and os.path.exists(r) else {"campos": []}
    c = st.columns(4)
    with c[0]:
        if info.get("campos"):
            opc = info["campos"]
            l["campo_fecha"] = st.selectbox("Campo de fecha", opc, index=opc.index(l["campo_fecha"]) if l["campo_fecha"] in opc else 0, key=K("calc_lin_fecha"))
        else:
            l["campo_fecha"] = st.text_input("Campo de fecha", l["campo_fecha"], key=K("calc_lin_fecha"))
    with c[1]:
        l["formato_fecha"] = st.text_input("Formato de fecha", l.get("formato_fecha", ""), key=K("calc_lin_fmt"), help="Formato strftime, p. ej. %m/%d/%Y o %Y-%m-%d; vacío = detección automática")
    with c[2]:
        if info.get("campos"):
            opc = ["(ninguno)"] + info["campos"]
            sel = st.selectbox("Campo de incertidumbre", opc, index=opc.index(l.get("campo_unc")) if l.get("campo_unc") in opc else 0, key=K("calc_lin_unc"), help="Opcional; se usa en WLR y EPRUNC")
            l["campo_unc"] = "" if sel == "(ninguno)" else sel
        else:
            l["campo_unc"] = st.text_input("Campo de incertidumbre", l.get("campo_unc", ""), key=K("calc_lin_unc"), help="Opcional; se usa en WLR y EPRUNC")
    with c[3]:
        l["unc_defecto"] = st.number_input("Incertidumbre por defecto (m)", 0.0, 500.0, float(l.get("unc_defecto", 10)), key=K("calc_lin_uncd"))
    if l["ruta"] and os.path.exists(l["ruta"]) and l["campo_fecha"]:
        try:
            L = PJ.cargar_lineas(p)
            fechas = sorted(L["_fecha"].dt.date.unique())
            cc = st.columns(4)
            with cc[0]:
                ui.kpi("Entidades", len(L), "", "", 0, ic="lineas", tono="azul")
            with cc[1]:
                ui.kpi("Fechas", len(fechas), "", f"{fechas[0]} → {fechas[-1]}", 0, ic="calendario", tono="teal")
            with cc[2]:
                ui.kpi("CRS de origen", str(gpd_crs(l, p)), "", "", ic="globo", tono="gris")
            with cc[3]:
                fr = st.selectbox("Fecha de referencia (P0)", [str(f) for f in fechas], index=len(fechas) - 1 if not l.get("fecha_ref") else max(0, [str(f) for f in fechas].index(l["fecha_ref"]) if l["fecha_ref"] in [str(f) for f in fechas] else len(fechas) - 1),
                                  key=K("calc_lin_ref"), help="Línea desde la que se miden las franjas de variables y se proyecta")
                if fr != l.get("fecha_ref"):
                    l["fecha_ref"] = fr; _invalidar(res, "transectos")
            res["_lineas"] = L
        except Exception as e:  # noqa: BLE001
            st.error(f"Líneas de costa: {e}")
    ui.panel("Línea base", "regla", "desde la que se emiten los transectos")
    b = p["linea_base"]
    c = st.columns([1.3, 4.7])
    with c[0]:
        b["modo"] = st.radio("Origen", ["generar", "archivo"], index=0 if b["modo"] == "generar" else 1, key=K("calc_base_modo"), horizontal=True, help="Generar: se desplaza la línea de referencia hacia tierra y se suaviza. Importar: archivo propio (p. ej. la línea base de DSAS).", format_func=lambda k: "Generar" if k == "generar" else "Importar")
    with c[1]:
        if b["modo"] == "archivo":
            r = _selector_archivo(p, "Línea base", b.get("ruta", ""), K("calc_base_ruta"), TIPOS_VECTOR)
            if r != b.get("ruta"):
                b["ruta"] = r; _invalidar(res, "transectos")
        else:
            d = st.columns(4)
            with d[0]:
                b["desplazamiento_m"] = st.number_input("Desplazamiento (m)", 10.0, 5000.0, float(b["desplazamiento_m"]), 10.0, key=K("calc_base_desp"), help="Distancia de la línea base respecto de la línea de referencia")
            with d[1]:
                b["hacia"] = st.selectbox("Hacia", ["tierra", "mar"], index=0 if b["hacia"] == "tierra" else 1, key=K("calc_base_hacia"))
            with d[2]:
                b["lado_tierra"] = st.selectbox("Lado de tierra", ["derecha", "izquierda"], index=0 if b["lado_tierra"] == "derecha" else 1, key=K("calc_base_lado"), help="Respecto del sentido de digitalización de la línea de referencia")
            with d[3]:
                b["suavizado_m"] = st.number_input("Suavizado (m)", 0.0, 5000.0, float(b["suavizado_m"]), 50.0, key=K("calc_base_suav"))
    ui.panel("Transectos", "capas", "perpendiculares a la línea base")
    t = p["transectos"]
    c = st.columns([1.3, 4.7])
    with c[0]:
        t["modo"] = st.radio("Origen ", ["generar", "archivo"], index=0 if t["modo"] == "generar" else 1, key=K("calc_tr_modo"), horizontal=True, help="Importar: shapefile de transectos propio (p. ej. los de DSAS)", format_func=lambda k: "Generar" if k == "generar" else "Importar")
    with c[1]:
        if t["modo"] == "archivo":
            r = _selector_archivo(p, "Transectos", t.get("ruta", ""), K("calc_tr_ruta"), TIPOS_VECTOR, "Convención DSAS: primer vértice en el mar, último en la línea base.")
            if r != t.get("ruta"):
                t["ruta"] = r; _invalidar(res, "transectos")
            d = st.columns(4)
            with d[0]:
                t["espaciado_m"] = st.number_input("Espaciado (m)", 5.0, 5000.0, float(t["espaciado_m"]), key=K("calc_tr_esp2"), help="Ancho de las franjas de muestreo de las variables")
            with d[1]:
                t["umbral_lineas"] = st.number_input("Mín. líneas", 2, 100, int(t.get("umbral_lineas", 10)), key=K("calc_tr_umb"), help="Transectos con menos líneas no reciben tasa LRR")
            with d[2]:
                t["criterio"] = st.selectbox("Intersección", ["cercana", "lejana"], index=0 if t.get("criterio", "cercana") == "cercana" else 1, key=K("calc_tr_crit"), help="Si una línea corta varias veces el transecto: la intersección más cercana a la línea base (DSAS) o la más lejana")
        else:
            d = st.columns(5)
            with d[0]:
                t["espaciado_m"] = st.number_input("Espaciado (m)", 5.0, 5000.0, float(t["espaciado_m"]), 5.0, key=K("calc_tr_esp"))
            with d[1]:
                t["longitud_m"] = st.number_input("Longitud (m)", 50.0, 20000.0, float(t["longitud_m"]), 50.0, key=K("calc_tr_len"))
            with d[2]:
                t["suavizado_m"] = st.number_input("Suavizado (m)", 0.0, 5000.0, float(t["suavizado_m"]), 50.0, key=K("calc_tr_suav"), help="DSAS smoothing distance")
            with d[3]:
                t["umbral_lineas"] = st.number_input("Mín. líneas", 2, 100, int(t.get("umbral_lineas", 10)), key=K("calc_tr_umb"), help="Transectos con menos líneas no reciben tasa LRR")
            with d[4]:
                t["criterio"] = st.selectbox("Intersección", ["cercana", "lejana"], index=0 if t.get("criterio", "cercana") == "cercana" else 1, key=K("calc_tr_crit"), help="Si una línea corta varias veces el transecto: la intersección más cercana a la línea base (DSAS) o la más lejana")
    ui.nota("Método: Himmelstoss et al. (2021), DSAS v5/v6: transectos perpendiculares a la línea base suavizada, distancia desde la base a cada línea (+ mar) y tasas NSM, SCE, EPR, LRR (con IC95 y R²) y WLR (1/σ²). Verificado: con los transectos y líneas de la tesis reproduce las 671 tasas DSAS con error < 0,001 m/año.")


def gpd_crs(l, p):
    try:
        import geopandas as gpd

        return gpd.read_file(l["ruta"], rows=1).crs.to_string()
    except Exception:  # noqa: BLE001
        return "—"


# ---------------------------------------------------------------------------
# Paso 2
# ---------------------------------------------------------------------------
def _paso_transectos(cfg, p, res):
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("▶ Calcular transectos y tasas", type="primary", use_container_width=True, key=K("calc_run_tr"), disabled="_lineas" not in res):
            with st.spinner("Intersectando líneas y calculando tasas…"):
                try:
                    res["transectos"] = PJ.paso_transectos(p, res["_lineas"]); _invalidar(res, "variables"); _sellar(p, res, "transectos"); st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"{type(e).__name__}: {e}")
    with c2:
        if "_lineas" not in res:
            ui.nota("Complete el paso 1 (líneas de costa con campo de fecha válido).")
    if not _ok(res, "transectos"):
        return
    r = res["transectos"]; t = r["transectos"]; rs = r["resumen"]
    k = st.columns(6)
    with k[0]:
        ui.kpi("Transectos", len(t), "", f"{int(t['LRR'].notna().sum())} con ≥ {p['transectos']['umbral_lineas']} líneas", 0, "geovisor", ic="capas", tono="azul")
    with k[1]:
        ui.kpi("Intersecciones", len(r["inter"]), "", f"{r['inter']['fecha'].nunique()} fechas", 0, "geovisor", ic="lineas", tono="teal")
    with k[2]:
        ui.kpi("LRR media", rs.get("media"), "m/año", "regresión lineal", 2, "geovisor", ic="trend_down", tono="coral")
    with k[3]:
        ui.kpi("LRR mediana", rs.get("mediana"), "m/año", "", 2, "geovisor", ic="grafico", tono="gris")
    with k[4]:
        ui.kpi("En retroceso", rs.get("pct_retroceso"), "%", "LRR < 0", 1, "geovisor", ic="alerta", tono="ambar")
    with k[5]:
        ui.kpi("Línea de referencia", f"{r['fecha_ref']:%Y-%m-%d}", "", f"{int(t['sin_linea_ref'].sum())} transectos sin corte", ic="calendario", tono="azul")
    with st.container(key=K("calc_sub1")):
        sub = st.tabs(["Mapa", "Perfil de tasas", "Tabla", "Comparar con DSAS"])
    with sub[0]:
        m = _mapa_base(cfg, t)
        L = res["_lineas"]
        mapas.agregar_geojson(m, _lineas_geojson(cfg, L), "Líneas de costa", color="#ffd166", grosor=1.0, opacidad=0.6, campos_tooltip=["fecha_txt"])
        mapas.agregar_geojson(m, vectores.a_geojson(r["base"], cfg, []), "Línea base", color="#ffffff", grosor=2, dash="6 4")
        gt = t[["id_ivc", "dist_costa_km", "LRR", "LCI95", "EPR", "NSM", "n_lineas", "geometry"]].copy()
        gj = vectores.a_geojson(gt, cfg, ["id_ivc", "dist_costa_km", "LRR", "LCI95", "EPR", "NSM", "n_lineas"])
        lrr = pd.to_numeric(gt["LRR"], errors="coerce")
        rampa = mapas.rampa_divergente(float(lrr.min()), float(lrr.max()), "LRR (m/año)")
        mapas.agregar_geojson(m, gj, "Transectos (LRR)", grosor=2, campos_tooltip=["id_ivc", "LRR"], campos_popup=["id_ivc", "dist_costa_km", "LRR", "LCI95", "EPR", "NSM", "n_lineas"],
                              alias={"id_ivc": "Transecto", "dist_costa_km": "Km", "LRR": "LRR (m/año)", "LCI95": "IC95", "EPR": "EPR", "NSM": "NSM (m)", "n_lineas": "N.º líneas"},
                              funcion_estilo=lambda f, rp=rampa: {"color": rp(f["properties"]["LRR"]) if f["properties"].get("LRR") is not None else "#999"})
        mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, "LRR (m/año)", "{:.1f}"), "bottomright")
        mapas.finalizar(m)
        ui.mostrar_mapa(m, 520, "mapa_calc_tr", vista=mapas.vista_para_bounds(vectores.bounds_visual(t, cfg), 1000, 520))
    with sub[1]:
        ui.grafico(graficos.tasa_por_transecto(pd.DataFrame(t.drop(columns="geometry")), "LRR", "m/año", ci="LCI95"))
    with sub[2]:
        cols = ["id_ivc", "dist_costa_km", "n_lineas", "NSM", "SCE", "EPR", "EPRUNC", "LRR", "LR2", "LSE", "LCI95", "WLR", "WR2", "WCI"]
        ui.tabla(pd.DataFrame(t[[c for c in cols if c in t.columns]]).round(3), hide_index=True, use_container_width=True, height=360)
        ui.descargas(t, f"{p['nombre']}_transectos_tasas", cfg, "calc_tr_exp")
    with sub[3]:
        rd = st.text_input("Capa DSAS con tasas (opcional, para comparar)", p.get("_dsas_ref", ""), key=K("calc_dsas_ref"), help="Shapefile de tasas DSAS con campos LRR/EPR; se empareja por transecto más cercano")
        if rd and os.path.exists(rd):
            try:
                import geopandas as gpd
                from shapely.strtree import STRtree

                d = gpd.read_file(rd).to_crs(t.crs)
                arb = STRtree(list(d.geometry))
                idx = [int(arb.nearest(g)) for g in t.geometry]
                comp = pd.DataFrame({"id_ivc": t["id_ivc"], "LRR_calc": t["LRR"].values, "LRR_dsas": d["LRR"].values[idx]})
                comp["dif"] = comp["LRR_calc"] - comp["LRR_dsas"]
                k = st.columns(3)
                with k[0]:
                    ui.kpi("Diferencia media |Δ|", float(comp["dif"].abs().mean()), "m/año", "", 4, "geovisor", ic="check", tono="teal")
                with k[1]:
                    ui.kpi("Diferencia máxima", float(comp["dif"].abs().max()), "m/año", "", 4, "geovisor", ic="alerta", tono="ambar")
                with k[2]:
                    ui.kpi("Correlación", float(comp[["LRR_calc", "LRR_dsas"]].corr().iloc[0, 1]), "", "", 4, "geovisor", ic="grafico", tono="azul")
                ui.grafico(graficos.observado_vs_predicho(comp, "LRR_dsas", "LRR_calc", "LRR DSAS frente a calculada (m/año)"))
            except Exception as e:  # noqa: BLE001
                st.error(f"Comparación: {e}")


# ---------------------------------------------------------------------------
# Paso 3
# ---------------------------------------------------------------------------
TIPOS_FUENTE = {
    "raster": ("Ráster (GeoTIFF): DEM, pendiente, distancia, etc.", TIPOS_RASTER),
    "vector_cat": ("Polígonos con categorías (geomorfología, suelos, cobertura, usos…)", TIPOS_VECTOR),
    "vector_num": ("Polígonos con un campo numérico (densidad de población, etc.)", TIPOS_VECTOR),
    "distancia": ("Líneas/polígonos a los que medir la distancia (vía, poblado, infraestructura)", TIPOS_VECTOR),
    "puntos": ("Puntos/estaciones con un valor (oleaje, granulometría…) → valor más cercano", TIPOS_VECTOR),
    "ancho_barra": ("Ancho de la barra: DEM con agua = NoData, o polígonos de agua", TIPOS_RASTER + TIPOS_VECTOR),
    "tabla": ("Tabla CSV ya calculada por transecto (id + valor)", TIPOS_TABLA),
    "tasa": ("Tasa de cambio de la línea de costa (del paso 2, sin archivo)", []),
    "constante": ("Valor constante para toda la costa (sin archivo)", []),
}
METODO_DE_TIPO = {"raster": "raster_estadistico", "vector_cat": "vector_categorico", "vector_num": "vector_numerico", "distancia": "distancia_a", "puntos": "mas_cercano",
                  "ancho_barra": "ancho_barra", "tabla": "tabla_por_id", "tasa": "tasa", "constante": "constante"}
TIPO_DE_METODO = {v: k for k, v in METODO_DE_TIPO.items()} | {"raster_pendiente": "raster"}
CLASIF = {"umbrales": "Umbrales: 4 cortes → clases 1‑5 (p. ej. elevación, distancia)", "categorias": "Cada categoría recibe una clase 1‑5 (p. ej. geomorfología)",
          "ponderado_area": "Promedio de clases ponderado por el % de área de cada categoría (p. ej. cobertura, usos)",
          "difusa": "Difusa 0‑1 (mín‑máx), sin umbrales", "quintiles": "Quintiles de la muestra (estilo CVI de Gornitz)", "directa": "El valor ya es una clase 1‑5"}

# Plantilla de variables habituales con los umbrales usados en la tesis (editables)
PLANTILLAS = {
    "Cambio de la línea de costa (LRR)": dict(codigo="c_cambio_costa", dimension="Dinámica litoral", metodo="tasa", campo="LRR", rol="tasa", cortes="-2;-1;1;2", mayor_mas_vulnerable=False),
    "Geomorfología (categorías)": dict(codigo="c_geomorfologia", dimension="Geomorfología", metodo="vector_categorico", normalizacion="categorias", d0=0, d1=200),
    "Elevación del terreno (DEM, m)": dict(codigo="c_elevacion", dimension="Geomorfología", metodo="raster_estadistico", estadistico="mediana", d0=0, d1=200, cortes="0.33;0.81;1.03;1.31", mayor_mas_vulnerable=False),
    "Pendiente del terreno (DEM, °)": dict(codigo="c_pendiente", dimension="Geomorfología", metodo="raster_pendiente", d0=0, d1=200, cortes="0.16;0.28;0.44;0.68", mayor_mas_vulnerable=False),
    "Oleaje Hs (estaciones/boyas, m)": dict(codigo="c_oleaje", dimension="Oceanografía", metodo="mas_cercano", cortes="", mayor_mas_vulnerable=True),
    "% de terreno bajo el nivel del mar (DEM)": dict(codigo="c_nivel_mar", dimension="Clima", metodo="raster_estadistico", estadistico="pct_bajo", umbral=0.33, d0=0, d1=500, cortes="20;40;60;80", mayor_mas_vulnerable=True, rol="nivel_mar"),
    "Tamaño de grano d50 (estaciones, mm)": dict(codigo="c_granulometria", dimension="Geotecnia", metodo="mas_cercano", cortes="0.126;0.25;0.5;1.0", mayor_mas_vulnerable=False, rol="d50"),
    "Sustrato / suelos (categorías)": dict(codigo="c_sustrato", dimension="Geotecnia", metodo="vector_categorico", normalizacion="categorias", d0=0, d1=200),
    "Cobertura de la tierra (% de área)": dict(codigo="c_cobertura", dimension="Ambiental", metodo="vector_categorico", normalizacion="ponderado_area", d0=0, d1=500),
    "Uso del suelo (% de área)": dict(codigo="c_uso_suelo", dimension="Socioeconómica", metodo="vector_categorico", normalizacion="ponderado_area", d0=0, d1=500),
    "Distancia a infraestructura/vía (m)": dict(codigo="c_dist_infra", dimension="Infraestructura", metodo="distancia_a", rol="distancia_infra", cortes="250;500;1000;1500", mayor_mas_vulnerable=False),
    "Área construida (% de área, polígonos)": dict(codigo="c_vivienda", dimension="Socioeconómica", metodo="vector_categorico", normalizacion="ponderado_area", d0=0, d1=500),
    "Densidad de población (hab/km², polígonos)": dict(codigo="c_densidad_pob", dimension="Socioeconómica", metodo="vector_numerico", estadistico="media_area", d0=0, d1=500, cortes="40;80;120;160", mayor_mas_vulnerable=True),
    "Ancho de la barra (m)": dict(codigo="c_ancho_barra", dimension="Geomorfología", metodo="ancho_barra", rol="ancho_barra", cortes="90;180;260;350", mayor_mas_vulnerable=False),
    "Variable en blanco": dict(codigo="c_nueva", dimension="Geomorfología", metodo="raster_estadistico"),
}


def _clases_desde_sentido(mayor: bool) -> str:
    return "1;2;3;4;5" if mayor else "5;4;3;2;1"


def _tarjeta_variable(cfg, p, res, i: int, v: dict) -> bool:
    """Formulario de una variable (dentro de un expander). Devuelve True si hay que borrarla."""
    kv = f"calc_v{i}_"
    cambiado = False

    def set_(k, val):
        nonlocal cambiado
        if v.get(k) != val:
            v[k] = val; cambiado = True

    c = st.columns([1.6, 1.2, 1.2, 0.5])
    with c[0]:
        set_("nombre", st.text_input("Nombre", v.get("nombre", ""), key=K(kv + "nombre")))
    with c[1]:
        set_("codigo", st.text_input("Código (sin espacios)", v.get("codigo", ""), key=K(kv + "codigo"), help="Identificador de la columna, p. ej. c_elevacion").strip().replace(" ", "_"))
    with c[2]:
        set_("dimension", st.selectbox("Dimensión", PJ.DIMENSIONES, index=PJ.DIMENSIONES.index(v.get("dimension")) if v.get("dimension") in PJ.DIMENSIONES else 0, key=K(kv + "dim")))
    with c[3]:
        set_("activa", st.toggle("Activa", bool(v.get("activa", True)), key=K(kv + "activa")))

    # --- 1. tipo de dato y archivo
    st.markdown("**1 · ¿Qué tipo de dato es y dónde está?**")
    tipo_act = TIPO_DE_METODO.get(v.get("metodo", "raster_estadistico"), "raster")
    tipo = st.selectbox("Tipo de dato", list(TIPOS_FUENTE), index=list(TIPOS_FUENTE).index(tipo_act), key=K(kv + "tipo"), format_func=lambda k: TIPOS_FUENTE[k][0])
    if tipo != tipo_act:
        set_("metodo", METODO_DE_TIPO[tipo])
        if tipo == "vector_cat" and v.get("normalizacion") not in ("categorias", "ponderado_area"):
            set_("normalizacion", "categorias")
    info = {}
    if TIPOS_FUENTE[tipo][1]:
        r = _selector_archivo(p, "Archivo (ya recortado al área de estudio)", v.get("fuente", ""), K(kv + "fuente"), TIPOS_FUENTE[tipo][1])
        set_("fuente", r)
        if r and os.path.exists(r):
            info = _info_archivo(r, v.get("capa") or None)
            if info.get("error"):
                st.error(info["error"])
            else:
                st.caption(f"{info.get('tipo', '')} · CRS {info.get('crs', '—')}" + (f" · {info.get('n')} entidades" if info.get("n") else "") + (f" · {info.get('bandas')} banda(s), resolución {info.get('res'):.1f}" if info.get("bandas") else ""))
    cc = st.columns(4)
    if info.get("capas"):
        with cc[0]:
            set_("capa", st.selectbox("Capa del GeoPackage", info["capas"], index=info["capas"].index(v.get("capa")) if v.get("capa") in info["capas"] else 0, key=K(kv + "capa")))
            if v.get("capa") and v.get("capa") not in info["capas"]:
                set_("capa", info["capas"][0])
    # campo
    if tipo in ("vector_cat", "vector_num", "puntos", "tabla"):
        with cc[1]:
            opc = info.get("numericos" if tipo in ("vector_num", "puntos") else "campos") or []
            if opc:
                set_("campo", st.selectbox("Campo con el valor", opc, index=opc.index(v.get("campo")) if v.get("campo") in opc else 0, key=K(kv + "campo")))
            else:
                set_("campo", st.text_input("Campo con el valor", v.get("campo", ""), key=K(kv + "campo")))
        if tipo == "tabla":
            with cc[2]:
                opc = info.get("campos") or []
                set_("capa", st.selectbox("Columna con el id del transecto", opc, index=opc.index(v.get("capa")) if v.get("capa") in opc else 0, key=K(kv + "idcol")) if opc else st.text_input("Columna id", v.get("capa") or "id_ivc", key=K(kv + "idcol")))
    if tipo == "raster":
        with cc[1]:
            est_opc = ["mediana", "media", "p90", "p10", "min", "max", "pct_bajo", "pendiente"]
            act = "pendiente" if v.get("metodo") == "raster_pendiente" else (v.get("estadistico") or "mediana")
            e = st.selectbox("Qué extraer de la franja", est_opc, index=est_opc.index(act) if act in est_opc else 0, key=K(kv + "est"),
                             format_func=lambda k: {"pct_bajo": "% de celdas por debajo de un umbral", "pendiente": "pendiente media (°) del DEM", "p90": "percentil 90", "p10": "percentil 10"}.get(k, k))
            if e == "pendiente":
                set_("metodo", "raster_pendiente")
            else:
                set_("metodo", "raster_estadistico"); set_("estadistico", e)
        if v.get("estadistico") == "pct_bajo" and v.get("metodo") == "raster_estadistico":
            with cc[2]:
                set_("umbral", st.number_input("Umbral (unidades del ráster)", value=float(v.get("umbral") or 0.0), key=K(kv + "umb"), help="p. ej. nivel del mar proyectado en m"))
    if tipo == "vector_num":
        with cc[2]:
            set_("estadistico", st.selectbox("Cómo resumir", ["media_area", "cercano"], index=0 if v.get("estadistico") != "cercano" else 1, key=K(kv + "estn"), format_func=lambda k: "media ponderada por área en la franja" if k == "media_area" else "valor del polígono más cercano a P0"))
    if tipo == "tasa":
        with cc[0]:
            opc = ["LRR", "EPR", "WLR", "ventana"]
            set_("campo", st.selectbox("Tasa", opc, index=opc.index(v.get("campo")) if v.get("campo") in opc else 0, key=K(kv + "tasa"), format_func=lambda k: {"LRR": "LRR (regresión, todo el periodo)", "EPR": "EPR (punto final)", "WLR": "WLR (ponderada)", "ventana": "LRR de una ventana de años"}[k]))
        if v.get("campo") == "ventana":
            with cc[1]:
                set_("ventana", st.text_input("Ventana (año inicial;año final)", v.get("ventana") or "1984;2005", key=K(kv + "vent")))
    if tipo == "constante":
        with cc[1]:
            set_("constante", st.number_input("Valor", value=float(v.get("constante") or 0.0), key=K(kv + "cte")))
    if tipo in ("raster", "vector_cat", "vector_num"):
        with cc[3]:
            d0, d1 = st.columns(2)
            set_("d0", float(d0.number_input("Franja desde (m)", 0.0, 5000.0, float(v.get("d0") or 0), 50.0, key=K(kv + "d0"))))
            set_("d1", float(d1.number_input("hasta (m)", 50.0, 10000.0, float(v.get("d1") or 200), 50.0, key=K(kv + "d1"), help="Distancia tierra adentro desde la línea de referencia")))
    if tipo == "vector_cat" and info.get("categorias", {}).get(v.get("campo")):
        cats = info["categorias"][v["campo"]]
        excl = st.multiselect("Categorías que NO son del terreno (se ignoran para la dominante, p. ej. área urbana)", cats, default=[x for x in str(v.get("filtro") or "").split(";") if x in cats], key=K(kv + "excl"))
        set_("filtro", ";".join(excl))
    if tipo == "distancia":
        set_("filtro", st.text_input("Filtro opcional (expresión pandas, p. ej. tipo == 'primaria')", v.get("filtro") or "", key=K(kv + "filtro")))

    # --- 2. clasificación
    st.markdown("**2 · ¿Cómo se convierte en clase de vulnerabilidad?**")
    opc_norm = list(CLASIF) if tipo != "vector_cat" else ["categorias", "ponderado_area"]
    if tipo == "constante":
        opc_norm = ["directa", "umbrales"]
    n_act = v.get("normalizacion", "umbrales")
    if n_act not in opc_norm:
        n_act = opc_norm[0]; set_("normalizacion", n_act)
    c1, c2 = st.columns([1.4, 2.6])
    with c1:
        set_("normalizacion", st.selectbox("Método de clasificación", opc_norm, index=opc_norm.index(n_act), key=K(kv + "norm"), format_func=lambda k: CLASIF[k]))
    norm = v["normalizacion"]
    with c2:
        if norm == "umbrales":
            cortes = PJ._lista(v.get("cortes"))
            cols = st.columns([1, 1, 1, 1, 1.6])
            nuevos = []
            for j in range(4):
                nuevos.append(cols[j].number_input(f"Corte {j + 1}", value=float(cortes[j]) if j < len(cortes) else float(j + 1), key=K(kv + f"c{j}"), format="%.4g"))
            cl_act = PJ._lista(v.get("clases"))
            mayor_ini = (cl_act[0] < cl_act[-1]) if len(cl_act) == 5 else bool(v.get("mayor_mas_vulnerable", True))
            with cols[4]:
                ui.hueco_etiqueta()
                mayor = st.toggle("Mayor = más vulnerable", mayor_ini, key=K(kv + "sent"), help="Apagado: valores altos = clase 1 (p. ej. elevación, distancia a la vía, ancho de barra)")
            set_("cortes", ";".join(f"{x:g}" for x in nuevos)); set_("mayor_mas_vulnerable", bool(mayor)); set_("clases", _clases_desde_sentido(mayor))
            set_("cerrado", st.radio("Intervalos", ["derecha", "izquierda"], index=0 if v.get("cerrado", "derecha") == "derecha" else 1, horizontal=True, key=K(kv + "cerr"),
                                     format_func=lambda k: "(c1, c2] — el corte pertenece al intervalo inferior" if k == "derecha" else "[c1, c2) — el corte pertenece al superior"))
            if any(np.diff(nuevos) <= 0):
                st.warning("Los cortes deben ser crecientes")
        elif norm in ("categorias", "ponderado_area"):
            cats = info.get("categorias", {}).get(v.get("campo")) if tipo == "vector_cat" else None
            mapa = PJ._mapa(v.get("mapa_clases"))
            if cats:
                st.caption("Clase 1‑5 de cada categoría (0 = ignorar)")
                cols = st.columns(min(4, len(cats)))
                nuevo = {}
                for j, cat in enumerate(cats):
                    val = cols[j % len(cols)].number_input(cat, 0, 5, int(mapa.get(cat, mapa.get(cat.lower(), 0))), key=K(kv + f"cat{j}"))
                    if val:
                        nuevo[cat] = val
                set_("mapa_clases", ";".join(f"{k}:{int(x)}" for k, x in nuevo.items()))
            else:
                set_("mapa_clases", st.text_area("Categoría:clase separadas por ; (p. ej. playas:5;manglar:5;laguna:4)", v.get("mapa_clases") or "", key=K(kv + "mapa"), height=80))
        elif norm in ("difusa", "quintiles"):
            set_("mayor_mas_vulnerable", bool(st.toggle("Mayor valor = más vulnerable", bool(v.get("mayor_mas_vulnerable", True)), key=K(kv + "sent2"))))
        else:
            st.caption("El valor del archivo ya es una clase entre 1 y 5; se usa tal cual.")
    # --- 3. rol
    roles = list(PJ.ROLES)
    set_("rol", st.selectbox("Papel en la proyección (opcional)", roles, index=roles.index(v.get("rol", "")) if v.get("rol", "") in roles else 0, key=K(kv + "rol"), format_func=lambda k: PJ.ROLES[k],
                              help="Las variables con rol dinámico se reclasifican en los escenarios futuros; d50, H12 y elevación p90 alimentan la regla de Bruun"))
    if cambiado:
        _invalidar(res, "variables")
    return st.button("🗑 Quitar esta variable", key=K(kv + "del"))


def _paso_variables(cfg, p, res):
    ui.panel("Variables del índice", "capas", "una tarjeta por variable: suba el archivo ya recortado al área de estudio, diga qué es y cómo se clasifica; el geovisor la reparte a los transectos")
    if not _ok(res, "transectos"):
        ui.nota("Primero calcule los transectos (paso 2): las variables se distribuyen sobre ellos.")
    c1, c2, c3 = st.columns([2, 1, 1.2])
    with c1:
        plantilla = st.selectbox("Añadir variable", list(PLANTILLAS), key=K("calc_plantilla"), label_visibility="collapsed")
    with c2:
        if st.button("＋ Añadir", use_container_width=True, key=K("calc_add_var")):
            base = PLANTILLAS[plantilla]
            v = PJ.variable_nueva(base["codigo"], plantilla.split(" (")[0])
            v.update(base)
            if "clases" not in base:
                v["clases"] = _clases_desde_sentido(bool(base.get("mayor_mas_vulnerable", True)))
            cods = {x["codigo"] for x in p["variables"]}
            k = 2
            while v["codigo"] in cods:
                v["codigo"] = f"{base['codigo']}_{k}"; k += 1
            p["variables"].append(v); _invalidar(res, "variables"); st.rerun()
    with c3:
        if st.button("▶ Distribuir y clasificar todas", type="primary", use_container_width=True, key=K("calc_run_vars"), disabled=not _ok(res, "transectos") or not p["variables"]):
            barra = st.progress(0.0, "Calculando variables…")
            try:
                res["variables"] = PJ.paso_variables(p, res["transectos"]["transectos"], res["transectos"]["inter"], progreso=lambda i, n, c: barra.progress((i + 1) / max(n, 1), f"{c} ({i + 1}/{n})")); _invalidar(res, "pesos"); _sellar(p, res, "variables"); st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"{type(e).__name__}: {e}")
            barra.empty()
    if not p["variables"]:
        ui.vacio("Sin variables", "Elija una de la lista (traen los umbrales de la literatura usados en la tesis) o «Variable en blanco», y pulse Añadir.")
        return
    rv = res.get("variables")
    borrar = None
    for i, v in enumerate(p["variables"]):
        estado = "○"
        if rv is not None:
            if v["codigo"] in rv.get("errores", {}):
                estado = "⚠️"
            elif v["codigo"] in rv["clases"].columns:
                estado = "✅"
        titulo = f"{estado} {v.get('nombre') or v.get('codigo')}  ·  {TIPOS_FUENTE.get(TIPO_DE_METODO.get(v.get('metodo'), 'raster'), ('',))[0].split(':')[0].split(' (')[0]}  ·  {CLASIF.get(v.get('normalizacion', 'umbrales'), '').split(':')[0].split(' (')[0]}"
        with st.expander(titulo, expanded=False):
            if rv is not None and v["codigo"] in rv.get("errores", {}):
                st.error(rv["errores"][v["codigo"]])
            if _tarjeta_variable(cfg, p, res, i, v):
                borrar = i
    if borrar is not None:
        p["variables"].pop(borrar); _invalidar(res, "variables"); st.rerun()
    if rv is None:
        return
    cl = rv["clases"]; va = rv["valores"]
    cods = [v["codigo"] for v in p["variables"] if v.get("activa", True) and v["codigo"] in cl.columns]
    if not cods:
        return
    st.markdown("---")
    resumen = pd.DataFrame({"variable": cods, "n_con_dato": [int(pd.to_numeric(cl[c], errors="coerce").notna().sum()) for c in cods],
                            "clase_media": [float(pd.to_numeric(cl[c], errors="coerce").mean()) for c in cods], "clase_min": [float(pd.to_numeric(cl[c], errors="coerce").min()) for c in cods],
                            "clase_max": [float(pd.to_numeric(cl[c], errors="coerce").max()) for c in cods]})
    with st.container(key=K("calc_sub2")):
        sub = st.tabs(["Resumen de clases", "Valores brutos", "Clases por transecto", "Mapa de una variable"])
    with sub[0]:
        ui.tabla(resumen.round(2), hide_index=True, use_container_width=True)
        import plotly.graph_objects as go

        fig = go.Figure()
        for k in range(1, 6):
            fig.add_bar(x=cods, y=[float(100 * np.mean(np.round(pd.to_numeric(cl[c], errors="coerce").dropna()) == k)) if pd.to_numeric(cl[c], errors="coerce").notna().any() else 0 for c in cods],
                        name=f"{k} · {cfg['ivc']['clases'][k]['nombre']}", marker_color=cfg["ivc"]["clases"][k]["color"])
        fig.update_layout(barmode="stack", yaxis_title="% de transectos", xaxis_tickangle=-35)
        ui.grafico(graficos._estilo(fig, "Reparto de clases 1‑5 por variable (clases redondeadas)", 380))
    with sub[1]:
        ui.tabla(va.round(3), hide_index=True, use_container_width=True, height=360)
        ui.descargas(va, f"{p['nombre']}_variables_valores", cfg, "calc_var_exp1", formatos=("csv",))
    with sub[2]:
        ui.tabla(cl.round(3), hide_index=True, use_container_width=True, height=360)
        ui.descargas(cl, f"{p['nombre']}_variables_clases", cfg, "calc_var_exp2", formatos=("csv",))
    with sub[3]:
        var = st.selectbox("Variable", cods, key=K("calc_var_mapa"))
        t = res["transectos"]["transectos"]
        g = t[["id_ivc", "dist_costa_km", "geometry"]].merge(cl[["id_ivc", var]], on="id_ivc").rename(columns={var: "clase"})
        g["clase"] = pd.to_numeric(g["clase"], errors="coerce").round()
        gj = vectores.a_geojson(g, cfg, ["id_ivc", "dist_costa_km", "clase"])
        m = _mapa_base(cfg, t)
        col = {k: cfg["ivc"]["clases"][k]["color"] for k in cfg["ivc"]["clases"]}
        mapas.agregar_geojson(m, gj, var, grosor=3, campos_tooltip=["id_ivc", "clase"], funcion_estilo=lambda f, c=col: {"color": c.get(int(f["properties"]["clase"]) if f["properties"].get("clase") is not None else 0, "#999")})
        mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, f"Clase de {var}"), "bottomright"); mapas.finalizar(m)
        ui.mostrar_mapa(m, 460, "mapa_calc_var", vista=mapas.vista_para_bounds(vectores.bounds_visual(t, cfg), 1000, 460))


# ---------------------------------------------------------------------------
# Paso 4
# ---------------------------------------------------------------------------
def _paso_ponderacion(cfg, p, res):
    if not _ok(res, "variables"):
        ui.nota("Complete el paso 3."); return
    cl = res["variables"]["clases"]
    cods = [v["codigo"] for v in p["variables"] if v.get("activa", True) and v["codigo"] in cl.columns]
    pp = p["ponderacion"]
    c = st.columns([1.5, 1, 1, 1])
    with c[0]:
        pp["esquema_principal"] = st.selectbox("Esquema principal", ["ewm", "fahp", "fahp_ewm", "iguales", "manual"], index=["ewm", "fahp", "fahp_ewm", "iguales", "manual"].index(pp.get("esquema_principal", "ewm")),
                                               key=K("calc_esq"), format_func=lambda k: {"ewm": "EWM (entropía)", "fahp": "FAHP (panel de expertos)", "fahp_ewm": "FAHP‑EWM combinado", "iguales": "Pesos iguales", "manual": "Pesos manuales"}[k])
    with c[1]:
        pp["fahp"]["metodo"] = st.selectbox("Método FAHP", ["buckley", "chang"], index=0 if pp["fahp"].get("metodo", "buckley") == "buckley" else 1, key=K("calc_fahp_met"),
                                            format_func=lambda k: "Buckley (media geométrica difusa)" if k == "buckley" else "Chang (análisis extendido)")
    with c[2]:
        pp["fahp"]["delta"] = st.number_input("Amplitud TFN (δ)", 0.0, 3.0, float(pp["fahp"].get("delta", 1.0)), 0.5, key=K("calc_fahp_delta"), help="Número difuso triangular (a−δ, a, a+δ) de cada juicio de Saaty")
    with c[3]:
        pp["combinacion"] = st.selectbox("Combinación FAHP‑EWM", ["multiplicativa", "lineal"], index=0 if pp.get("combinacion", "multiplicativa") == "multiplicativa" else 1, key=K("calc_comb"),
                                         format_func=lambda k: "w = wF·wE / Σ" if k == "multiplicativa" else "w = α·wF + (1−α)·wE")
        if pp["combinacion"] == "lineal":
            pp["alfa"] = st.slider("α (peso del FAHP)", 0.0, 1.0, float(pp.get("alfa", 0.5)), 0.05, key=K("calc_alfa"))
    with st.expander("Matriz de comparación por pares (FAHP) — escala de Saaty 1‑9; basta rellenar el triángulo superior", expanded=pp["esquema_principal"] in ("fahp", "fahp_ewm")):
        M = pp["fahp"].get("matriz") or []
        if len(M) != len(cods):
            M = np.ones((len(cods), len(cods))).tolist()
        dfm = pd.DataFrame(M, index=cods, columns=cods)
        edm = st.data_editor(dfm, use_container_width=True, key=K("calc_fahp_matriz"))
        try:
            A = PO.matriz_desde_tabla(edm.astype(float))
            pp["fahp"]["matriz"] = A.tolist()
            cons = PO.consistencia(A)
            st.markdown(f"λmáx = {cons['lambda_max']:.3f} · CI = {cons['CI']:.3f} · **CR = {cons['CR']:.3f}** → {'consistente (CR ≤ 0,10)' if cons['consistente'] else '⚠️ inconsistente (CR > 0,10): revise los juicios'}")
        except Exception as e:  # noqa: BLE001
            st.warning(f"Matriz no válida: {e}")
        sub = st.file_uploader("…o cargar la matriz desde CSV (cuadrada, con encabezados = códigos)", type=["csv"], key=K("calc_fahp_csv"))
        if sub is not None:
            try:
                dfc = pd.read_csv(sub, index_col=0)
                dfc = dfc.reindex(index=cods, columns=cods)
                pp["fahp"]["matriz"] = PO.matriz_desde_tabla(dfc.astype(float)).tolist(); st.success("Matriz cargada"); st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"CSV: {e}")
    with st.expander("Pesos manuales", expanded=pp["esquema_principal"] == "manual"):
        man = pp.get("manual") or {}
        dfw = pd.DataFrame({"variable": cods, "peso": [float(man.get(c, 1.0)) for c in cods]})
        edw = st.data_editor(dfw, hide_index=True, key=K("calc_manual"), use_container_width=True)
        pp["manual"] = {r["variable"]: float(r["peso"]) for _, r in edw.iterrows()}
    if st.button("▶ Calcular pesos", type="primary", key=K("calc_run_pesos")):
        try:
            blo = IN.bloques_contiguos(cl["dist_costa_km"].to_numpy(float), int(p["indice"].get("n_bloques", 8)))
            res["pesos"] = PJ.paso_pesos(p, cl, blo); _invalidar(res, "indice"); _sellar(p, res, "pesos"); st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"{type(e).__name__}: {e}")
    if not _ok(res, "pesos"):
        return
    rp = res["pesos"]
    if rp.get("fahp_error"):
        st.warning(f"FAHP: {rp['fahp_error']}")
    tab = pd.DataFrame({"variable": rp["variables"]})
    for k, w in rp["pesos"].items():
        tab[k] = w
    import plotly.graph_objects as go

    fig = go.Figure()
    colores = {"ewm": "#3B6CF0", "fahp": "#F2745F", "fahp_ewm": "#7C5CF6", "iguales": "#B9B7B1", "manual": "#F5B544"}
    for k in rp["pesos"]:
        kw = {}
        if k == "ewm":
            kw = dict(error_y=dict(type="data", symmetric=False, array=rp["ewm"]["IC95_sup"] - rp["ewm"]["peso"], arrayminus=rp["ewm"]["peso"] - rp["ewm"]["IC95_inf"], thickness=1))
        fig.add_bar(x=rp["variables"], y=rp["pesos"][k], name=k, marker_color=colores.get(k, "#999"), **kw)
    fig.update_layout(barmode="group", xaxis_tickangle=-35, yaxis_title="Peso")
    ui.grafico(graficos._estilo(fig, "Pesos por esquema (EWM con IC95 por bootstrap de bloques)", 400))
    ui.tabla(tab.round(4), hide_index=True, use_container_width=True)
    if "fahp" in rp:
        with st.expander("Detalle FAHP (números difusos de cada peso)"):
            ui.tabla(rp["fahp"].round(4), hide_index=True, use_container_width=True)
    ui.nota("EWM: Shannon (1948), Zou et al. (2006); IC95 por bootstrap de bloques espaciales (Kunsch, 1989). FAHP: Buckley (1985) o Chang (1996) con TFN; CR de Saaty (1980). "
            "La combinación multiplicativa w_j = wF_j·wE_j/Σ es la usada en la literatura de índices híbridos subjetivo‑objetivo.")


# ---------------------------------------------------------------------------
# Paso 5
# ---------------------------------------------------------------------------
def _paso_indice(cfg, p, res):
    if not _ok(res, "pesos"):
        ui.nota("Complete el paso 4."); return
    c = st.columns([2, 1, 1, 1])
    with c[0]:
        cortes_txt = st.text_input("Cortes de clase del índice (0‑1)", ";".join(str(x) for x in p["indice"].get("cortes", [0.2, 0.4, 0.6, 0.8])), key=K("calc_cortes"))
        try:
            p["indice"]["cortes"] = [float(x) for x in cortes_txt.replace(",", ";").split(";")]
        except ValueError:
            st.warning("Cortes no válidos")
    with c[1]:
        t = res["transectos"]["transectos"]
        opc = [k for k in ("LRR", "EPR", "WLR") if k in t.columns]
        p["indice"]["tasa_validacion"] = st.selectbox("Tasa para validar", opc, index=opc.index(p["indice"].get("tasa_validacion", "LRR")) if p["indice"].get("tasa_validacion", "LRR") in opc else 0, key=K("calc_tasa_val"))
    with c[2]:
        p["indice"]["n_bloques"] = st.number_input("Bloques espaciales", 2, 30, int(p["indice"].get("n_bloques", 8)), key=K("calc_nblo"), help="Bloques contiguos para el bootstrap y la validación")
    with c[3]:
        ui.hueco_etiqueta()
        if st.button("▶ Calcular índice", type="primary", use_container_width=True, key=K("calc_run_ind")):
            with st.spinner("Índice, validación, concordancia, sensibilidad y estabilidad…"):
                try:
                    res["indice"] = PJ.paso_indice(p, res["variables"]["clases"], res["pesos"], t, res["variables"]["valores"]); _invalidar(res, "proyeccion"); _sellar(p, res, "indice"); st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"{type(e).__name__}: {e}")
    if not _ok(res, "indice"):
        return
    ri = res["indice"]; R = ri["tabla"]
    esq = p["ponderacion"].get("esquema_principal", "ewm")
    col = f"ivc_{esq}" if f"ivc_{esq}" in R.columns else "ivc_ewm"
    ccl = col.replace("ivc_", "clase_")
    v = pd.to_numeric(R[col], errors="coerce"); k_ = pd.to_numeric(R[ccl], errors="coerce")
    k = st.columns(5)
    with k[0]:
        ui.kpi("IVC medio", float(v.mean()), "0‑1", f"esquema {esq} · escala {ri['escala']}", 3, "geovisor", ic="escudo", tono="coral", progreso=float(v.mean()))
    with k[1]:
        ui.kpi("Clase alta + muy alta", float(100 * (k_ >= 4).mean()), "% transectos", "", 1, "geovisor", ic="alerta", tono="ambar")
    with k[2]:
        fila = ri["validacion"][ri["validacion"]["indice"] == col]
        ui.kpi("ρ con la tasa (−)", float(fila["rho"].iloc[0]) if len(fila) and "rho" in fila else None, "", f"IC95 {fila['IC95_inf'].iloc[0]:.2f}–{fila['IC95_sup'].iloc[0]:.2f}" if len(fila) and "IC95_inf" in fila else "", 3, "geovisor", ic="check", tono="teal")
    with k[3]:
        fe = ri["validacion"][ri["validacion"]["indice"] == "ivc_ewm_estructural"]
        ui.kpi("ρ estructural (no circular)", float(fe["rho"].iloc[0]) if len(fe) and "rho" in fe else None, "", "índice sin la variable de tasa", 3, "geovisor", ic="check", tono="azul")
    with k[4]:
        ui.kpi("Estabilidad media de la clase", float(R["estabilidad_clase_ewm_pct"].mean()), "%", "bootstrap de bloques sobre los pesos EWM", 1, "geovisor", ic="radar", tono="gris")
    with st.container(key=K("calc_sub3")):
        sub = st.tabs(["Mapa", "Perfil", "Distribución", "Validación y concordancia", "Redundancia y sensibilidad", "Tabla"])
    with sub[0]:
        esc = st.selectbox("Índice a mapear", [c_ for c_ in R.columns if c_.startswith("ivc_") or c_ == "cvi_gornitz"], index=[c_ for c_ in R.columns if c_.startswith("ivc_") or c_ == "cvi_gornitz"].index(col), key=K("calc_ind_mapa"))
        ccl2 = esc.replace("ivc_", "clase_") if esc != "cvi_gornitz" else "clase_cvi_gornitz"
        g = t[["id_ivc", "geometry"]].merge(R[["id_ivc", "dist_costa_km", esc, ccl2]], on="id_ivc").rename(columns={esc: "ivc", ccl2: "clase"})
        gj = vectores.a_geojson(g, cfg, ["id_ivc", "dist_costa_km", "ivc", "clase"])
        m = _mapa_base(cfg, t)
        colc = {k: cfg["ivc"]["clases"][k]["color"] for k in cfg["ivc"]["clases"]}
        mapas.agregar_geojson(m, gj, esc, grosor=3, campos_tooltip=["id_ivc", "ivc", "clase"], campos_popup=["id_ivc", "dist_costa_km", "ivc", "clase"],
                              alias={"id_ivc": "Transecto", "dist_costa_km": "Km", "ivc": "Índice", "clase": "Clase"},
                              funcion_estilo=lambda f, c=colc: {"color": c.get(int(f["properties"]["clase"]) if f["properties"].get("clase") is not None else 0, "#999")})
        mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, esc), "bottomright"); mapas.finalizar(m)
        ui.mostrar_mapa(m, 500, "mapa_calc_ind", vista=mapas.vista_para_bounds(vectores.bounds_visual(t, cfg), 1000, 500))
    with sub[1]:
        ui.grafico(graficos.ivc_por_km(R, col, cfg, titulo=f"{col} a lo largo de la costa"))
    with sub[2]:
        pct = {int(k): float(100 * (k_ == k).mean()) for k in range(1, 6)}
        c1, c2 = st.columns(2)
        ui.grafico_en(c1, graficos.histograma(v, f"Distribución de {col}", "0‑1", 30, p["indice"]["cortes"]))
        ui.grafico_en(c2, graficos.barras_clases(pct, cfg))
    with sub[3]:
        st.markdown("**Validación contra la tasa de cambio** (ρ de Spearman del índice frente a −tasa; IC95 por bootstrap de bloques). "
                    "«circular = sí» cuando el índice incluye la propia tasa como variable; la fila *estructural* es la validación no circular.")
        ui.tabla(ri["validacion"].round(3), hide_index=True, use_container_width=True)
        vb = ri.get("validacion_bloques")
        if vb is not None and len(vb):
            with st.expander("ρ por bloque espacial"):
                ui.tabla(vb[vb["indice"].isin(["ivc_ewm", "ivc_ewm_estructural"])].round(3), hide_index=True, use_container_width=True)
        st.markdown("**Concordancia entre esquemas** (κ ponderado cuadrático y % de coincidencia de clase)")
        ui.tabla(ri["concordancia"].round(3), hide_index=True, use_container_width=True)
    with sub[4]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**VIF** (> 10 indica redundancia)")
            ui.tabla(ri["vif"].round(2), hide_index=True, use_container_width=True)
        with c2:
            st.markdown("**Sensibilidad** a la perturbación de un peso (EWM)")
            ui.tabla(ri["sensibilidad"].round(3), hide_index=True, use_container_width=True, height=300)
        import plotly.express as px

        ui.grafico(graficos._estilo(px.imshow(ri["redundancia_rho"].round(2), text_auto=True, color_continuous_scale="RdBu", zmin=-1, zmax=1), "ρ de Spearman entre variables", 480))
    with sub[5]:
        ui.tabla(R.round(3), hide_index=True, use_container_width=True, height=360)
        gi = t[["id_ivc", "geometry"]].merge(R, on="id_ivc")
        ui.descargas(gi, f"{p['nombre']}_indice", cfg, "calc_ind_exp")


# ---------------------------------------------------------------------------
# Paso 6
# ---------------------------------------------------------------------------
def _paso_proyeccion(cfg, p, res):
    if not _ok(res, "indice"):
        ui.nota("Complete el paso 5."); return
    pr = p["proyeccion"]
    c = st.columns([1, 1, 1.4, 1, 1, 1])
    with c[0]:
        pr["ventana_anios"] = st.number_input("Ventana (años)", 5, 60, int(pr.get("ventana_anios", 21)), key=K("calc_pr_vent"), help="Longitud de las ventanas históricas y futuras")
    with c[1]:
        htxt = st.text_input("Horizontes", ";".join(str(h) for h in pr.get("horizontes", [2050, 2100])), key=K("calc_pr_h"))
        try:
            pr["horizontes"] = [int(x) for x in htxt.replace(",", ";").split(";")]
        except ValueError:
            st.warning("Horizontes no válidos")
    with c[2]:
        pr["modelo"] = st.selectbox("Modelo de transición", ["persistencia", "amortiguada", "ridge", "rf"], index=["persistencia", "amortiguada", "ridge", "rf"].index(pr.get("modelo", "amortiguada")), key=K("calc_pr_mod"),
                                    format_func=lambda k: {"persistencia": "Persistencia (Δ = 0)", "amortiguada": "Persistencia amortiguada", "ridge": "Ridge (8 rasgos)", "rf": "Random Forest (8 rasgos)"}[k])
    with c[3]:
        pr["n_mc"] = st.number_input("Monte Carlo", 100, 5000, int(pr.get("n_mc", 1000)), 100, key=K("calc_pr_mc"))
    with c[4]:
        pr["n_bloques"] = st.number_input("Bloques", 2, 30, int(pr.get("n_bloques", 8)), key=K("calc_pr_blo"))
    with c[5]:
        pr["buffer_km"] = st.number_input("Exclusión (km)", 0.0, 20.0, float(pr.get("buffer_km", 3.0)), 0.5, key=K("calc_pr_buf"), help="Zona de exclusión alrededor del bloque de prueba")
    with st.expander("Escenarios de nivel del mar y regla de Bruun", expanded=False):
        dfe = pd.DataFrame(pr.get("escenarios", []))
        ede = st.data_editor(dfe, num_rows="dynamic", hide_index=True, use_container_width=True, key=K("calc_pr_esc"),
                             column_config={"clave": "clave", "nombre": "escenario", "anio": st.column_config.NumberColumn("año"), "slr_mm": st.column_config.NumberColumn("SLR (mm) respecto del año base")})
        pr["escenarios"] = [{"clave": str(r["clave"]), "nombre": str(r["nombre"]), "anio": int(r["anio"]), "slr_mm": float(r["slr_mm"])} for _, r in ede.iterrows() if pd.notna(r.get("anio"))]
        br = pr.setdefault("bruun", {})
        b = st.columns(6)
        with b[0]:
            br["activo"] = st.checkbox("Aplicar Bruun", bool(br.get("activo", False)), key=K("calc_br_on"))
        with b[1]:
            br["anio_base_slr"] = st.number_input("Año base SLR", 1950, 2100, int(br.get("anio_base_slr", 2005)), key=K("calc_br_base"))
        with b[2]:
            br["H12_m"] = st.number_input("H12 (m)", 0.5, 15.0, float(br.get("H12_m", 4.0)), 0.1, key=K("calc_br_h12"), help="Hs superada 12 h/año; se usa la variable con rol H12 si existe")
        with b[3]:
            br["H12_max_m"] = st.number_input("H12 máx (m)", 0.5, 15.0, float(br.get("H12_max_m", 4.6)), 0.1, key=K("calc_br_h12m"))
        with b[4]:
            br["d50_mm"] = st.number_input("d50 (mm)", 0.05, 5.0, float(br.get("d50_mm", 0.2)), 0.01, key=K("calc_br_d50"), help="se usa la variable con rol d50 si existe")
        with b[5]:
            br["B_m"] = st.number_input("Berma B (m)", 0.0, 20.0, float(br.get("B_m", 1.0)), 0.1, key=K("calc_br_b"), help="se usa la variable con rol elevacion_p90 si existe")
        ui.nota("R = E·ΔS·L*/(h* + B): h* de Hallermeier (1981), L* = (h*/A)^1,5 con A = 0,067·w^0,44 (Dean, 1991; Ferguson y Church, 2004), E ~ triangular(0,1; 0,75; 1,0) (Vousdoukas et al., 2020); "
                "ΔS = SLR − r_h·años, con r_h ~ U(3,4; 6,15) mm/año (ritmo histórico ya contenido en la tendencia).")
    if st.button("▶ Proyectar", type="primary", key=K("calc_run_pr")):
        with st.spinner("Ventanas, modelo de transición, Monte Carlo, líneas e IVC futuro…"):
            try:
                esq = p["ponderacion"].get("esquema_principal", "ewm")
                if esq not in res["pesos"]["pesos"]:
                    esq = "ewm"
                res["proyeccion"] = PJ.paso_proyeccion(p, res["transectos"]["transectos"], res["transectos"]["inter"], res["variables"]["clases"], res["variables"]["valores"], res["pesos"], esq); _sellar(p, res, "proyeccion"); st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"{type(e).__name__}: {e}")
    if not _ok(res, "proyeccion"):
        return
    rp = res["proyeccion"]; aj = rp["ajuste"]; met = aj.get("metricas", {})
    k = st.columns(5)
    with k[0]:
        ui.kpi("Ventanas históricas", len(rp["ventanas"]), "", " · ".join(f"{a:.0f}–{b:.0f}" for a, b in rp["ventanas"]), 0, "geovisor", ic="calendario", tono="azul")
    with k[1]:
        ui.kpi("R²_OS del modelo", met.get("R2_OS"), "", f"IC95 {met['R2_OS_IC95'][0]:.2f}–{met['R2_OS_IC95'][1]:.2f} · {met.get('bloques_mejora')}/{met.get('n_bloques')} bloques mejoran" if "R2_OS_IC95" in met else met.get("nota", ""), 3, "modelo", ic="cerebro", tono="coral")
    with k[2]:
        ui.kpi("RMSE Δ modelo / persistencia", f"{met['RMSE_modelo']:.2f} / {met['RMSE_persistencia']:.2f}" if "RMSE_modelo" in met else None, "m/año", "", ic="regla", tono="gris")
    with k[3]:
        T = rp["config"].horizontes[-1]
        d = rp["tabla"][f"desplaz_m_{T}"]
        ui.kpi(f"Retroceso mediano a {T}", float(-d[d < 0].median()) if (d < 0).any() else 0.0, "m", f"{float(100 * (d < 0).mean()):.0f} % de transectos en retroceso", 0, "modelo", ic="trend_down", tono="ambar")
    with k[4]:
        ui.kpi("σ regional", rp.get("sigma_regional"), "m/año", "cambio medio regional aleatorio por paso (estimado de las ventanas si hay ≥ 3; si no, 1,0)", 2, "modelo", ic="info", tono="gris")
    with st.container(key=K("calc_sub4")):
        sub = st.tabs(["Mapa de líneas", "Escenarios del IVC", "Modelo de transición", "Tabla"])
    with sub[0]:
        t = res["transectos"]["transectos"]
        m = _mapa_base(cfg, t)
        gl = rp["lineas"]
        gj = vectores.a_geojson(vectores.simplificar_para_mapa(gl, cfg, 2.0), cfg, ["linea", "tipo", "anio"])
        est = {"observada": ("#ffd166", None, 2.5), "central": ("#ff7f00", None, 3.0), "p05": ("#ff7f00", "4 6", 1.5), "p95": ("#ff7f00", "4 6", 1.5), "persistencia": ("#984ea3", "10 6", 2.0)}
        mapas.agregar_geojson(m, gj, "Líneas proyectadas", grosor=2, campos_tooltip=["linea"], alias={"linea": "Línea"},
                              funcion_estilo=lambda f, e=est: {"color": e[f["properties"]["tipo"]][0], "dashArray": e[f["properties"]["tipo"]][1], "weight": e[f["properties"]["tipo"]][2]})
        mapas.agregar_leyenda_html(m, "<b>Líneas proyectadas</b><br>" + "<br>".join(f'<span style="display:inline-block;width:26px;border-top:3px {"dashed" if d_ else "solid"} {c_};vertical-align:middle;margin-right:6px"></span>{n_}' for n_, (c_, d_, _) in est.items()), "bottomright")
        mapas.finalizar(m)
        ui.mostrar_mapa(m, 500, "mapa_calc_pr", vista=mapas.vista_para_bounds(vectores.bounds_visual(t, cfg), 1000, 500))
    with sub[1]:
        ui.tabla(rp["resumen"].round(2), hide_index=True, use_container_width=True)
        import plotly.graph_objects as go

        fig = go.Figure()
        for kk in range(1, 6):
            fig.add_bar(x=rp["resumen"]["escenario"], y=rp["resumen"][f"pct_clase_{kk}"], name=f"{kk} · {cfg['ivc']['clases'][kk]['nombre']}", marker_color=cfg["ivc"]["clases"][kk]["color"])
        fig.update_layout(barmode="stack", yaxis_title="% de transectos")
        ui.grafico(graficos._estilo(fig, "Reparto de clases del IVC por escenario", 380))
        roles = [v["codigo"] for v in p["variables"] if v.get("rol") in ("tasa", "distancia_infra", "ancho_barra", "nivel_mar")]
        ui.nota("Variables reclasificadas en el futuro (roles dinámicos): " + (", ".join(roles) if roles else "ninguna — asigne roles en el paso 3 para que el IVC cambie con la proyección") + ". Pesos fijos del presente.")
    with sub[2]:
        if "por_bloque" in aj and len(aj["por_bloque"]):
            ui.tabla(aj["por_bloque"].round(3), hide_index=True, use_container_width=True)
        if aj.get("beta"):
            st.markdown(f"Persistencia amortiguada: Δ = {aj['beta'][0]:.3f} + {aj['beta'][1]:.3f}·(r − media de vecinos 2 km)")
        if aj.get("coeficientes"):
            ui.tabla(pd.DataFrame({"rasgo": list(aj["coeficientes"]), "coeficiente_estandarizado": list(aj["coeficientes"].values())}).round(3), hide_index=True)
        if aj.get("importancia"):
            ui.tabla(pd.DataFrame({"rasgo": list(aj["importancia"]), "importancia": list(aj["importancia"].values())}).round(3), hide_index=True)
        if "oof" in aj:
            y, oof = aj["y"], aj["oof"]; ok = np.isfinite(y) & np.isfinite(oof)
            import plotly.express as px

            ui.grafico(graficos._estilo(px.scatter(x=y[ok], y=oof[ok], labels={"x": "Δ observado (m/año)", "y": "Δ predicho fuera de bloque"}), "Δ observado frente a predicho (validación en bloques)", 380))
    with sub[3]:
        ui.tabla(rp["tabla"].round(2), hide_index=True, use_container_width=True, height=360)
        ui.descargas(rp["tabla"], f"{p['nombre']}_proyeccion", cfg, "calc_pr_exp", formatos=("csv",))


# ---------------------------------------------------------------------------
# Paso 7
# ---------------------------------------------------------------------------
def _entregables_proyecto(cfg, p, carpeta: Path) -> None:
    """Mapa integrado del proyecto exportado, mapa HTML autónomo, informe PDF tipo dashboard y atlas de la tesis."""
    from ..calculo import capas_proyecto as CP
    from ..catalogo_datos import CAPAS

    if not carpeta.exists() or not CP.capas_de(carpeta):
        ui.nota("Tras «Guardar todo» aparecen aquí el mapa integrado del proyecto, su versión HTML autónoma y el informe PDF; las capas quedan además disponibles en el Visor geoespacial (grupo «Calculadora»).", abierta=True)
        return
    ui.panel("Entregables del proyecto", "mapa", "mapa integrado, mapa HTML autónomo e informe PDF tipo dashboard con cita del aplicativo")
    c = st.columns([1.4, 1, 1, 1, 1])
    with c[0]:
        bases = [b["nombre"] for b in cfg["mapa"]["mapas_base"]]
        base = st.selectbox("Mapa base", bases, index=min(2, len(bases) - 1), key=K("calc_ent_base"))
    with c[1]:
        campo = st.selectbox("Tasa", CP.TASAS, key=K("calc_ent_campo"))
    with c[2]:
        esq = st.selectbox("Esquema", ["ewm", "iguales", "fahp", "fahp_ewm", "manual"], index=0, key=K("calc_ent_esq"))
    escs = CP.escenarios_de(carpeta)
    with c[3]:
        esc = st.selectbox("Escenario", escs, key=K("calc_ent_esc")) if escs else None
    with c[4]:
        ui.hueco_etiqueta()
        try:
            html = CP.html_autonomo(cfg, carpeta, mapa_base=base, campo_tasa=campo, esquema=esq, escenario=esc)
            st.download_button("⬇ Mapa HTML", html.encode("utf-8"), file_name=f"mapa_{p['nombre']}.html", mime="text/html", use_container_width=True, key=K("calc_ent_html"),
                               help="Mapa interactivo autónomo (Leaflet) con todas las capas del proyecto; se abre en cualquier navegador")
        except Exception as e:  # noqa: BLE001
            st.error(f"Mapa HTML: {e}")
    try:
        m, grupos, stats = CP.mapa_integrado(cfg, carpeta, base, campo, esq, esc, 560)
        ui.mostrar_mapa(m, 560, "mapa_calc_integrado", vista=mapas.vista_para_bounds(CP.bounds_proyecto(carpeta, cfg) or [[10.9, -74.8], [11.1, -74.3]], 1000, 560), capas=grupos)
        st.markdown(mapas.leyendas_html(m), unsafe_allow_html=True)
    except Exception as e:  # noqa: BLE001
        st.error(f"Mapa integrado: {e}")
    d = st.columns([1.2, 1, 1, 1.6])
    with d[0]:
        fondos = {"auto": "Automático (ArcGIS → DEM → tierra/agua)", "arcgis": "Imagen satelital Esri/ArcGIS (internet)", "delta": "DEM DeltaDTM sombreado", "fondo": "Mosaico tierra/agua", "ninguno": "Sin fondo"}
        fondo_inf = st.selectbox("Fondo de los mapas del informe", list(fondos), format_func=lambda k: fondos[k], key=K("calc_ent_fondo"))
    with d[1]:
        ui.hueco_etiqueta()
        if st.button("📄 Generar informe PDF", use_container_width=True, key=K("calc_ent_pdf"), help="Informe estilo «informe anual»: portada, resumen ejecutivo, capítulos con mapas sobre fondo cartográfico, pesos, validación, proyección, escenarios, metodología y cita del aplicativo"):
            from .. import informe_pdf

            with st.spinner("Componiendo el informe…"):
                try:
                    r = informe_pdf.generar_informe(cfg, carpeta, carpeta / f"informe_{p['nombre']}.pdf", p["nombre"], esquema=esq, campo_tasa=campo, fondo=fondo_inf)
                    st.session_state["calc_informe_pdf"] = str(r)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Informe: {e}")
    with d[2]:
        ui.hueco_etiqueta()
        r = st.session_state.get("calc_informe_pdf")
        if r and Path(r).exists():
            st.download_button("⬇ Informe PDF", Path(r).read_bytes(), file_name=Path(r).name, mime="application/pdf", use_container_width=True, key=K("calc_ent_pdf_dl"))
    with d[3]:
        ui.hueco_etiqueta()
        atlas = CAPAS.get("atlas_ivc_pdf")
        if atlas is not None and atlas.disponible(cfg):
            ra = atlas.ruta(cfg)
            st.download_button("⬇ Atlas IVC de la tesis (PDF)", ra.read_bytes(), file_name=ra.name, mime="application/pdf", use_container_width=True, key=K("calc_ent_atlas"),
                               help="Atlas de mapas del IVC de la Barra de Salamanca (producto de la tesis)")


def _paso_exportar(cfg, p, res):
    carpeta = _carpeta(p)
    st.markdown(f"Los productos se escriben en `{_ruta_corta(carpeta)}` (CSV, GeoPackage y `proyecto.json` con toda la configuración, reutilizable con «Abrir proyecto»).")
    hechos = [k for k in ("transectos", "variables", "pesos", "indice", "proyeccion") if k in res]
    st.markdown(" ".join(_badge(True, k) for k in hechos) or "Nada calculado todavía.", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("💾 Guardar todo", type="primary", use_container_width=True, key=K("calc_save"), disabled=not hechos):
            try:
                escritos = PJ.exportar_todo(p, carpeta, {k: res[k] for k in hechos})
                st.success(f"{len(escritos)} archivos escritos en {_ruta_corta(carpeta)}")
                st.session_state["calc_escritos"] = [str(x) for x in escritos]
            except Exception as e:  # noqa: BLE001
                st.error(f"{type(e).__name__}: {e}")
    with c2:
        st.download_button("⬇ proyecto.json", json.dumps(p, ensure_ascii=False, indent=1, default=PJ._json_default), file_name=f"{p['nombre']}_proyecto.json", mime="application/json", key=K("calc_dl_json"))
    if st.session_state.get("calc_escritos"):
        with st.expander(f"{len(st.session_state['calc_escritos'])} archivos escritos"):
            for x in st.session_state["calc_escritos"]:
                st.caption(_ruta_corta(Path(x)))
    _entregables_proyecto(cfg, p, carpeta)
    with st.expander("Metodología implementada (para citar en la tesis)"):
        st.markdown(
            "1. **Transectos y tasas**: perpendiculares a la línea base suavizada; intersección más cercana a la base; NSM, SCE, EPR, LRR (IC95, R²) y WLR (Himmelstoss et al., 2021). "
            "Validado: reproduce las tasas DSAS de la tesis con error < 0,001 m/año.\n"
            "2. **Variables**: franjas contiguas desde P0 (ancho = espaciado) con estadísticos de ráster, % de área por categoría, distancias y valores más cercanos (ivc_variables.py).\n"
            "3. **Normalización**: clases 1‑5 por umbrales (M1), categorías→clase, promedio por área, difusa 0‑1 (M2) o quintiles.\n"
            "4. **Ponderación**: EWM con IC95 por bootstrap de bloques; FAHP (Buckley 1985 / Chang 1996, CR de Saaty); iguales; manual; FAHP‑EWM combinado.\n"
            "5. **Índice**: IVC = (Σ w c − 1)/4; TOPSIS (Hwang y Yoon, 1981); CVI de Gornitz (1991). Validación: ρ de Spearman con IC95 por bloques contra la tasa (y versión estructural no circular), "
            "κ ponderado entre esquemas, VIF, sensibilidad de pesos y estabilidad de la clase por bootstrap.\n"
            "6. **Proyección**: ventanas de L años; transición Δ por persistencia, persistencia amortiguada, ridge o RF con validación en bloques y zona de exclusión (R²_OS, Campbell y Thompson, 2008); "
            "Monte Carlo con residuos fuera de muestra; regla de Bruun (Bruun, 1962; Dean, 1991; Vousdoukas et al., 2020); IVC futuro con pesos fijos y variables dinámicas reclasificadas.")
