"""Proyecto de cálculo del IVC: configuración serializable (JSON) y ejecución de cada paso.

Un proyecto es un diccionario con estas secciones (todas editables desde la página «Calculadora IVC»):

    nombre, epsg, salida
    lineas:      {ruta, campo_fecha, formato_fecha, campo_unc, unc_defecto, fecha_ref}
    linea_base:  {modo: 'archivo'|'generar', ruta, desplazamiento_m, hacia, lado_tierra, suavizado_m}
    transectos:  {modo: 'generar'|'archivo', ruta, espaciado_m, longitud_m, suavizado_m, umbral_lineas, criterio}
    variables:   [ {codigo, nombre, dimension, metodo, fuente, campo, capa, estadistico, d0, d1, umbral, rol,
                    normalizacion, cortes, clases, cerrado, mapa_clases, mayor_mas_vulnerable, filtro, ventana}, … ]
    ponderacion: {esquema_principal, fahp: {matriz: [[…]], metodo, delta}, manual: {codigo: peso}, combinacion, alfa}
    indice:      {cortes: [0.2,0.4,0.6,0.8], tasa_validacion: 'LRR'|'ventana', n_bloques}
    proyeccion:  {ventana_anios, horizontes, modelo, n_mc, n_bloques, buffer_km, sigma_regional,
                  escenarios: [{clave, nombre, anio, slr_mm}], bruun: {activo, H12_m, H12_max_m, d50_mm|codigo, B_codigo, rh_mm}}

Los resultados de cada paso se guardan en ``resultados/calculadora/<nombre>/`` (CSV, GPKG, JSON).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

from . import transectos as TR, tasas as TA, muestreo as MU, normalizacion as NO, ponderacion as PO, indice as IN, proyeccion as PR

METODOS = {
    "raster_estadistico": "Ráster: estadístico en la franja",
    "raster_pendiente": "Ráster DEM: pendiente media (°)",
    "vector_categorico": "Vector: categoría dominante / % de área",
    "vector_numerico": "Vector: campo numérico (media por área o más cercano)",
    "distancia_a": "Distancia desde P0 a la entidad más cercana",
    "mas_cercano": "Valor del punto/entidad más cercana a P0",
    "ancho_barra": "Ancho de la barra (rayo hacia tierra hasta agua)",
    "tabla_por_id": "Tabla CSV por id de transecto",
    "tasa": "Tasa de cambio del paso 2 (LRR, EPR, WLR o ventana)",
    "constante": "Valor constante",
}
NORMALIZACIONES = {"umbrales": "M1 · clases 1‑5 por umbrales", "directa": "Ya viene como clase 1‑5 (sin transformar)", "categorias": "Categorías → clase 1‑5", "ponderado_area": "% de área × puntaje por categoría",
                   "difusa": "M2 · difusa 0‑1 (mín‑máx)", "quintiles": "Quintiles (CVI de Gornitz)"}
ROLES = {"": "—", "tasa": "Tasa de cambio (variable objetivo/dinámica)", "distancia_infra": "Distancia a infraestructura (dinámica)",
         "ancho_barra": "Ancho de barra (dinámica)", "nivel_mar": "% bajo el nivel del mar (dinámica)", "elevacion_p90": "Elevación p90 (berma para Bruun)",
         "d50": "Tamaño de grano d50 mm (Bruun)", "H12": "Altura de ola H12 m (Bruun)"}
DIMENSIONES = ["Dinámica litoral", "Geomorfología", "Geotecnia", "Oceanografía", "Clima", "Ambiental", "Socioeconómica", "Infraestructura"]


def nuevo_proyecto(nombre: str = "proyecto", epsg: int = 32618) -> dict:
    return {
        "nombre": nombre, "epsg": epsg, "version": 1,
        "lineas": {"ruta": "", "campo_fecha": "", "formato_fecha": "", "campo_unc": "", "unc_defecto": 10.0, "fecha_ref": ""},
        "linea_base": {"modo": "generar", "ruta": "", "desplazamiento_m": 300.0, "hacia": "tierra", "lado_tierra": "derecha", "suavizado_m": 500.0},
        "transectos": {"modo": "generar", "ruta": "", "espaciado_m": 100.0, "longitud_m": 1000.0, "suavizado_m": 500.0, "umbral_lineas": 10, "criterio": "cercana"},
        "variables": [],
        "ponderacion": {"esquema_principal": "ewm", "fahp": {"matriz": [], "metodo": "buckley", "delta": 1.0}, "manual": {}, "combinacion": "multiplicativa", "alfa": 0.5},
        "indice": {"cortes": [0.2, 0.4, 0.6, 0.8], "tasa_validacion": "LRR", "n_bloques": 8},
        "proyeccion": {"ventana_anios": 21, "horizontes": [2050, 2100], "modelo": "amortiguada", "n_mc": 1000, "n_bloques": 8, "buffer_km": 3.0, "sigma_regional": None,
                       "escenarios": [{"clave": "ssp245_2050", "nombre": "SSP2-4.5", "anio": 2050, "slr_mm": 325}, {"clave": "ssp585_2050", "nombre": "SSP5-8.5", "anio": 2050, "slr_mm": 350},
                                      {"clave": "ssp245_2100", "nombre": "SSP2-4.5", "anio": 2100, "slr_mm": 794}, {"clave": "ssp585_2100", "nombre": "SSP5-8.5", "anio": 2100, "slr_mm": 1009}],
                       "bruun": {"activo": False, "H12_m": 4.0, "H12_max_m": 4.6, "d50_mm": 0.2, "B_m": 1.0, "rh_mm": [3.4, 6.15], "anio_base_slr": 2005}},
    }


def variable_nueva(codigo: str = "c_nueva", nombre: str = "Nueva variable") -> dict:
    return {"codigo": codigo, "nombre": nombre, "dimension": "Geomorfología", "metodo": "raster_estadistico", "fuente": "", "campo": "", "capa": "",
            "estadistico": "mediana", "d0": 0.0, "d1": 200.0, "umbral": None, "rol": "", "normalizacion": "umbrales", "cortes": "", "clases": "5;4;3;2;1",
            "cerrado": "derecha", "mapa_clases": "", "mayor_mas_vulnerable": True, "filtro": "", "ventana": "", "constante": None, "activa": True, "campos_escenario": {}}


def guardar_proyecto(p: dict, carpeta: str | os.PathLike) -> Path:
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    ruta = Path(carpeta) / "proyecto.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1, default=_json_default)
    return ruta


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def cargar_proyecto(ruta: str | os.PathLike) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _leer_vector(ruta: str, capa: str | None, epsg: int) -> gpd.GeoDataFrame:
    if not ruta or not os.path.exists(ruta):
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    g = gpd.read_file(ruta, layer=capa or None) if capa else gpd.read_file(ruta)
    if g.crs is None:
        raise ValueError(f"{os.path.basename(ruta)} no declara CRS")
    return g.to_crs(epsg)


# ---------------------------------------------------------------------------
# Paso 1‑2: líneas, línea base, transectos, intersecciones y tasas
# ---------------------------------------------------------------------------
def cargar_lineas(p: dict) -> gpd.GeoDataFrame:
    c = p["lineas"]
    L = _leer_vector(c["ruta"], c.get("capa"), p["epsg"])
    if c["campo_fecha"] not in L.columns:
        raise ValueError(f"Campo de fecha '{c['campo_fecha']}' no existe; campos: {list(L.columns)}")
    f = pd.to_datetime(L[c["campo_fecha"]], format=c.get("formato_fecha") or None, errors="coerce")
    L = L.assign(_fecha=f)
    L = L[L["_fecha"].notna()].copy()
    if L.empty:
        raise ValueError("Ninguna fecha pudo interpretarse (revise el formato, p. ej. %m/%d/%Y)")
    return L


def paso_transectos(p: dict, L: gpd.GeoDataFrame) -> dict:
    """Línea base, transectos, intersecciones, P0 y tasas. Devuelve dict con GeoDataFrames y tablas."""
    c = p["transectos"]; cb = p["linea_base"]
    fref = pd.Timestamp(p["lineas"]["fecha_ref"]) if p["lineas"].get("fecha_ref") else L["_fecha"].max()
    lref = L[L["_fecha"] == fref]
    if lref.empty:
        lref = L[L["_fecha"] == L["_fecha"].max()]; fref = L["_fecha"].max()
    if cb["modo"] == "archivo":
        base = _leer_vector(cb["ruta"], cb.get("capa"), p["epsg"])
    else:
        base = TR.generar_linea_base(lref, cb["desplazamiento_m"], cb["hacia"], cb["suavizado_m"], cb["lado_tierra"])
    if c["modo"] == "archivo":
        tr = TR.normalizar_transectos(_leer_vector(c["ruta"], c.get("capa"), p["epsg"]), base)
    else:
        tr = TR.generar_transectos(base, lref, TR.ParamTransectos(c["espaciado_m"], c["longitud_m"], c["suavizado_m"]))
    inter = TR.intersecciones(tr, L, "_fecha", p["lineas"].get("campo_unc") or None, float(p["lineas"].get("unc_defecto") or 10), c.get("criterio", "cercana"))
    if inter.empty:
        raise ValueError("Ningún transecto corta las líneas de costa: revise la orientación/longitud de los transectos y el lado de la línea base")
    t = TR.p0_de_referencia(tr, inter, fref)
    T = TA.tasas_por_transecto(inter, int(c.get("umbral_lineas", 10)))
    t = t.merge(T, on="id_t", how="left")
    return {"base": base, "transectos": t, "inter": inter, "tasas": T, "fecha_ref": fref, "resumen": TA.resumen_tasas(T, "LRR")}


# ---------------------------------------------------------------------------
# Paso 3: variables
# ---------------------------------------------------------------------------
def _lista(s) -> list[float]:
    if s is None or (isinstance(s, float) and np.isnan(s)) or str(s).strip() == "":
        return []
    return [float(x) for x in str(s).replace(",", ";").split(";") if str(x).strip() != ""]


def _mapa(s) -> dict:
    out = {}
    if s is None or str(s).strip() == "":
        return out
    for par in str(s).split(";"):
        if ":" in par:
            k, v = par.rsplit(":", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


def distribuir_variable(v: dict, t: gpd.GeoDataFrame, inter: pd.DataFrame, ancho_m: float) -> tuple[pd.Series, pd.DataFrame | None]:
    """Valor bruto de la variable por transecto (y tabla de % por categoría si aplica)."""
    m = v["metodo"]
    d0, d1 = float(v.get("d0") or 0), float(v.get("d1") or 200)
    if m == "raster_estadistico":
        return MU.raster_estadistico(t, v["fuente"], d0, d1, ancho_m, v.get("estadistico") or "mediana", v.get("umbral")), None
    if m == "raster_pendiente":
        return MU.raster_pendiente(t, v["fuente"], d0, d1, ancho_m), None
    if m == "vector_categorico":
        capa = gpd.read_file(v["fuente"], layer=v["capa"]) if v.get("capa") else v["fuente"]
        tab, dom = MU.vector_categorico(t, capa, v["campo"], d0, d1, ancho_m, tuple(x.strip() for x in str(v.get("filtro") or "").split(";") if x.strip()))
        return dom, tab
    if m == "vector_numerico":
        capa = gpd.read_file(v["fuente"], layer=v["capa"]) if v.get("capa") else v["fuente"]
        return MU.vector_numerico(t, capa, v["campo"], d0, d1, ancho_m, v.get("estadistico") if v.get("estadistico") in ("media_area", "cercano") else "media_area"), None
    if m == "distancia_a":
        capa = gpd.read_file(v["fuente"], layer=v["capa"]) if v.get("capa") else v["fuente"]
        return MU.distancia_a(t, capa, v.get("filtro") or None), None
    if m == "mas_cercano":
        capa = gpd.read_file(v["fuente"], layer=v["capa"]) if v.get("capa") else v["fuente"]
        return MU.mas_cercano(t, capa, v["campo"]), None
    if m == "ancho_barra":
        r = MU.ancho_barra(t, dem=v["fuente"] if str(v["fuente"]).lower().endswith((".tif", ".tiff")) else None,
                           agua=None if str(v["fuente"]).lower().endswith((".tif", ".tiff")) else v["fuente"])
        return r["valor"], r[["censura"]]
    if m == "tabla_por_id":
        return MU.tabla_por_id(t, v["fuente"], v.get("capa") or "id_ivc", v["campo"]), None
    if m == "tasa":
        campo = v.get("campo") or "LRR"
        if campo == "ventana":
            a0, a1 = _lista(v.get("ventana"))[:2]
            s = TA.tasa_ventana(inter, a0, a1)
            return s.reindex(t["id_t"].values).set_axis(t["id_ivc"].values).rename("valor"), None
        return pd.Series(pd.to_numeric(t[campo], errors="coerce").to_numpy(), index=t["id_ivc"].values, name="valor"), None
    if m == "constante":
        return pd.Series(float(v.get("constante") or 0), index=t["id_ivc"].values, name="valor"), None
    raise ValueError(f"Método desconocido: {m}")


def normalizar_variable(v: dict, valor: pd.Series, tabla: pd.DataFrame | None, km: np.ndarray) -> np.ndarray:
    n = v.get("normalizacion", "umbrales")
    if n == "umbrales":
        cortes, clases = _lista(v.get("cortes")), _lista(v.get("clases"))
        if len(cortes) != 4 or len(clases) != 5:
            raise ValueError(f"{v['codigo']}: se necesitan 4 cortes y 5 clases (p. ej. '0.33;0.81;1.03;1.31' y '5;4;3;2;1')")
        return NO.por_umbrales(pd.to_numeric(valor, errors="coerce").to_numpy(), cortes, clases, v.get("cerrado", "derecha"))
    if n == "categorias":
        s, _ = NO.vecino_costa(valor.astype(str), km)
        return NO.categorias_a_clase(s, _mapa(v.get("mapa_clases")))
    if n == "ponderado_area":
        if tabla is None:
            raise ValueError(f"{v['codigo']}: la normalización por % de área requiere el método vector_categorico")
        x = NO.ponderado_por_area(tabla, _mapa(v.get("mapa_clases")))
        s, _ = NO.vecino_costa(pd.Series(x), km)
        return s.to_numpy(float)
    if n == "directa":
        x = pd.to_numeric(valor, errors="coerce").to_numpy(float)
        if np.nanmin(x) < 1 or np.nanmax(x) > 5:
            raise ValueError(f"{v['codigo']}: los valores 'directos' deben estar entre 1 y 5")
        return x
    if n == "difusa":
        return NO.difusa_01(pd.to_numeric(valor, errors="coerce").to_numpy(), bool(v.get("mayor_mas_vulnerable", True)))
    if n == "quintiles":
        return NO.quintiles(pd.to_numeric(valor, errors="coerce").to_numpy(), bool(v.get("mayor_mas_vulnerable", True)))
    raise ValueError(f"Normalización desconocida: {n}")


def paso_variables(p: dict, t: gpd.GeoDataFrame, inter: pd.DataFrame, solo: list[str] | None = None, progreso=None) -> dict:
    """Distribuye y normaliza todas las variables activas. Devuelve {'valores': DataFrame, 'clases': DataFrame, 'tablas': {codigo: tabla}, 'errores': {codigo: msg}}."""
    ancho = float(p["transectos"].get("espaciado_m") or 100)
    km = t["dist_costa_km"].to_numpy(float)
    valores = pd.DataFrame({"id_ivc": t["id_ivc"].values, "dist_costa_km": km})
    clases = valores.copy()
    tablas, errores = {}, {}
    vars_ = [v for v in p["variables"] if v.get("activa", True) and (solo is None or v["codigo"] in solo)]
    for i, v in enumerate(vars_):
        if progreso:
            progreso(i, len(vars_), v["codigo"])
        try:
            val, tab = distribuir_variable(v, t, inter, ancho)
            valores[v["codigo"]] = val.reindex(t["id_ivc"].values).to_numpy() if hasattr(val, "reindex") else val
            if tab is not None:
                tablas[v["codigo"]] = tab
            clases[v["codigo"]] = normalizar_variable(v, val.reindex(t["id_ivc"].values), tab, km)
        except Exception as e:  # noqa: BLE001
            errores[v["codigo"]] = f"{type(e).__name__}: {e}"
    return {"valores": valores, "clases": clases, "tablas": tablas, "errores": errores}


# ---------------------------------------------------------------------------
# Paso 4‑5: ponderación e índice
# ---------------------------------------------------------------------------
def escala_de(p: dict) -> str:
    """'1-5' si todas las variables se normalizan a clases; '0-1' si todas son difusas; mezcla → error."""
    ns = {v.get("normalizacion", "umbrales") for v in p["variables"] if v.get("activa", True)}
    if ns <= {"umbrales", "categorias", "ponderado_area", "quintiles", "directa"}:
        return "1-5"
    if ns <= {"difusa"}:
        return "0-1"
    raise ValueError("No mezcle normalizaciones de clases 1‑5 con la difusa 0‑1 en el mismo índice")


def paso_pesos(p: dict, clases: pd.DataFrame, bloques: np.ndarray | None = None) -> dict:
    cols = [v["codigo"] for v in p["variables"] if v.get("activa", True) and v["codigo"] in clases.columns]
    X = clases[cols].to_numpy(float)
    ok = np.isfinite(X).all(1)
    out = {"variables": cols, "n": int(ok.sum())}
    ewm = PO.ewm_con_ic(X, bloques, 1000)
    ewm.insert(0, "variable", cols)
    out["ewm"] = ewm
    out["pesos"] = {"ewm": ewm["peso"].to_numpy(), "iguales": PO.pesos_iguales(len(cols))}
    pf = p["ponderacion"].get("fahp", {})
    M = pf.get("matriz") or []
    if len(M) == len(cols) and len(cols) > 1:
        try:
            A = PO.matriz_desde_tabla(pd.DataFrame(M, dtype=float))
            tab, cons = PO.pesos_fahp(A, pf.get("metodo", "buckley"), float(pf.get("delta", 1.0)))
            tab.insert(0, "variable", cols)
            out["fahp"] = tab; out["fahp_consistencia"] = cons
            out["pesos"]["fahp"] = tab["peso"].to_numpy()
            out["pesos"]["fahp_ewm"] = PO.combinar(tab["peso"].to_numpy(), ewm["peso"].to_numpy(), p["ponderacion"].get("combinacion", "multiplicativa"), float(p["ponderacion"].get("alfa", 0.5)))
        except Exception as e:  # noqa: BLE001
            out["fahp_error"] = str(e)
    man = p["ponderacion"].get("manual") or {}
    if man and all(c in man for c in cols):
        w = np.array([float(man[c]) for c in cols]); out["pesos"]["manual"] = w / w.sum()
    return out


def paso_indice(p: dict, clases: pd.DataFrame, pesos: dict, t: gpd.GeoDataFrame, valores: pd.DataFrame) -> dict:
    cols = pesos["variables"]
    X = clases[cols].to_numpy(float)
    escala = escala_de(p)
    cortes = p["indice"].get("cortes", [0.2, 0.4, 0.6, 0.8])
    R = pd.DataFrame({"id_ivc": clases["id_ivc"].values, "dist_costa_km": clases["dist_costa_km"].values})
    for k, w in pesos["pesos"].items():
        R[f"ivc_{k}"] = IN.ivc_lineal(X, w, escala)
        R[f"clase_{k}"] = NO.clase_de_indice_01(R[f"ivc_{k}"], cortes)
    tp, _ = IN.topsis(X, pesos["pesos"]["ewm"], True, escala)
    R["ivc_topsis_ewm"] = tp; R["clase_topsis_ewm"] = NO.clase_de_indice_01(tp, cortes)
    tpr, _ = IN.topsis(X, pesos["pesos"]["ewm"], False, escala)      # ideal relativo (mejor/peor observado)
    R["ivc_topsis_rel_ewm"] = tpr; R["clase_topsis_rel_ewm"] = NO.clase_de_indice_01(tpr, cortes)
    if escala == "1-5":
        g = IN.cvi_gornitz(X, normalizar=False)
        R["cvi_gornitz"] = g; R["clase_cvi_gornitz"] = NO.quintiles(g)
    # validación contra la tasa (signo invertido) y bloques
    km = R["dist_costa_km"].to_numpy(float)
    blo = IN.bloques_contiguos(km, int(p["indice"].get("n_bloques", 8)))
    R["bloque"] = blo
    tasa = None
    cfg_val = p["indice"].get("tasa_validacion", "LRR")
    if cfg_val in t.columns:
        tasa = pd.to_numeric(t.set_index("id_ivc").loc[R["id_ivc"], cfg_val], errors="coerce").to_numpy(float)
    val = []
    rol_tasa = next((v["codigo"] for v in p["variables"] if v.get("rol") == "tasa" and v["codigo"] in cols), None)
    val_bloque = []
    for c in [c for c in R.columns if c.startswith("ivc_") or c == "cvi_gornitz"]:
        fila = {"indice": c, "circular": "sí" if rol_tasa else "no"}
        if tasa is not None:
            fila.update(IN.rho_ic_bloques(R[c].to_numpy(float), -tasa, blo))
            for b in np.unique(blo):
                m = blo == b
                val_bloque.append({"indice": c, "bloque": int(b), "n": int(m.sum()), **{k: v for k, v in IN.rho_ic_bloques(R[c].to_numpy(float)[m], -tasa[m], np.zeros(m.sum()), n_boot=200).items() if k in ("rho", "p")},
                                   "km_ini": float(np.nanmin(km[m])), "km_fin": float(np.nanmax(km[m]))})
        val.append(fila)
    # índice estructural (sin la variable de tasa) para una validación no circular
    if rol_tasa:
        cols_e = [c for c in cols if c != rol_tasa]
        Xe = clases[cols_e].to_numpy(float)
        we = PO.pesos_ewm(Xe[np.isfinite(Xe).all(1)])
        R["ivc_ewm_estructural"] = IN.ivc_lineal(Xe, we, escala); R["clase_ewm_estructural"] = NO.clase_de_indice_01(R["ivc_ewm_estructural"], cortes)
        fila = {"indice": "ivc_ewm_estructural", "circular": "no"}
        if tasa is not None:
            fila.update(IN.rho_ic_bloques(R["ivc_ewm_estructural"].to_numpy(float), -tasa, blo))
        val.append(fila)
    validacion = pd.DataFrame(val)
    # concordancia entre esquemas
    esq = [c for c in R.columns if c.startswith("clase_")]
    conc = []
    for a in esq:
        for b in esq:
            if a < b:
                conc.append({"a": a, "b": b, "kappa_cuadratico": IN.kappa_ponderado(R[a], R[b]), "coincidencia_pct": float(100 * np.nanmean(R[a].to_numpy() == R[b].to_numpy()))})
    rho_v, vif_t = IN.redundancia(clases[cols])
    sens = IN.sensibilidad_pesos(X[np.isfinite(X).all(1)], pesos["pesos"]["ewm"], cols, escala, cortes=cortes)
    estab = IN.estabilidad_clase_bootstrap(X, blo, 300, escala=escala, cortes=cortes)
    R["estabilidad_clase_ewm_pct"] = estab
    return {"tabla": R, "validacion": validacion, "validacion_bloques": pd.DataFrame(val_bloque), "concordancia": pd.DataFrame(conc), "redundancia_rho": rho_v, "vif": vif_t,
            "sensibilidad": sens, "escala": escala, "bloques": blo, "cortes": list(cortes)}


# ---------------------------------------------------------------------------
# Paso 6: proyección
# ---------------------------------------------------------------------------
def paso_proyeccion(p: dict, t: gpd.GeoDataFrame, inter: pd.DataFrame, clases: pd.DataFrame, valores: pd.DataFrame, pesos: dict, esquema: str = "ewm") -> dict:
    c = p["proyeccion"]
    cfg = PR.ConfigProyeccion(float(c["ventana_anios"]), tuple(int(h) for h in c["horizontes"]), c["modelo"], int(c["n_mc"]), int(c["n_bloques"]), float(c["buffer_km"]), 2026,
                              c.get("sigma_regional"))
    km = t["dist_costa_km"].to_numpy(float); ids = t["id_t"].to_numpy()
    vent = PR.ventanas_historicas(inter, cfg.ventana_anios)
    if len(vent) < 1:
        raise ValueError("No hay suficientes años de líneas de costa para una ventana")
    anio_ref = float(inter["anio_dec"].max())
    H = [PR.rasgos_ventana(inter, ids, km, a, b + (1e-6 if i == len(vent) - 1 else 0)) for i, (a, b) in enumerate(vent)]
    if len(vent) >= 2:
        aj = PR.ajustar_transicion(H[-2], H[-2]["tasa"].to_numpy(), H[-1]["tasa"].to_numpy(), km, cfg)
        # sigma regional: desviación del cambio medio entre ventanas consecutivas si hay ≥ 3 ventanas
        if cfg.sigma_regional is None and len(vent) >= 3:
            medias = [np.nanmean(H[i + 1]["tasa"].to_numpy() - H[i]["tasa"].to_numpy()) for i in range(len(vent) - 1)]
            cfg.sigma_regional = float(np.std(medias, ddof=1)) if len(medias) >= 2 else 1.0
    else:
        cfg.modelo = "persistencia"
        aj = {"tipo": "persistencia", "residuos_oof": np.full(len(km), np.nan), "mediana_rasgos": np.zeros(len(PR.RASGOS)), "metricas": {"nota": "una sola ventana: solo persistencia"}, "por_bloque": pd.DataFrame(), "bloques": PR.bloques_igual_n(km, cfg.n_bloques)}
    pr = PR.proyectar(H[-1]["tasa"].to_numpy(), H[-1], aj, km, anio_ref, cfg, cfg.sigma_regional)
    tabla = pr["tabla"]; tabla.insert(0, "id_ivc", t["id_ivc"].values); tabla.insert(1, "dist_costa_km", km)
    lineas = PR.lineas_proyectadas(t, tabla, cfg.horizontes, int(anio_ref))
    # --- Bruun y IVC futuro por escenario
    cols = pesos["variables"]; w = pesos["pesos"][esquema]
    X = clases[cols].to_numpy(float)
    roles = {v["rol"]: v["codigo"] for v in p["variables"] if v.get("rol") in ("tasa", "distancia_infra", "ancho_barra", "nivel_mar") and v["codigo"] in cols}
    clasif = {v["codigo"]: (_lista(v.get("cortes")), _lista(v.get("clases")), v.get("cerrado", "derecha")) for v in p["variables"] if v.get("normalizacion") == "umbrales"}
    vals = {c_: pd.to_numeric(valores[c_], errors="coerce").to_numpy(float) for c_ in cols if c_ in valores.columns}
    escala = escala_de(p)
    cortes = p["indice"].get("cortes", [0.2, 0.4, 0.6, 0.8])
    br = c.get("bruun", {}); resumen = []
    ivc_act = IN.ivc_lineal(X, w, escala)
    resumen.append({"escenario": f"Actual ({int(anio_ref)})", "clave": "actual", **_pcts(NO.clase_de_indice_01(ivc_act, cortes)), "ivc_medio": float(np.nanmean(ivc_act))})
    esc_tab = {}
    for e in c.get("escenarios", []):
        T = int(e["anio"]); k = e["clave"]
        if T not in cfg.horizontes:
            continue
        desp = tabla[f"desplaz_m_{T}"].to_numpy(float)
        ret = np.maximum(-desp, 0)
        bruun = None
        if br.get("activo"):
            slr = float(e.get("slr_mm", 0)) / 1000.0
            anio_base = float(br.get("anio_base_slr", 2005))
            rolv = {v["rol"]: v["codigo"] for v in p["variables"] if v.get("rol") in ("d50", "H12", "elevacion_p90")}
            d50 = valores[rolv["d50"]].to_numpy(float) if "d50" in rolv and rolv["d50"] in valores else np.full(len(km), float(br.get("d50_mm", 0.2)))
            H12 = valores[rolv["H12"]].to_numpy(float) if "H12" in rolv and rolv["H12"] in valores else np.full(len(km), float(br.get("H12_m", 4.0)))
            B = valores[rolv["elevacion_p90"]].to_numpy(float) if "elevacion_p90" in rolv and rolv["elevacion_p90"] in valores else np.full(len(km), float(br.get("B_m", 1.0)))
            d50 = np.where(np.isfinite(d50) & (d50 > 0), d50, np.nanmedian(d50[np.isfinite(d50) & (d50 > 0)]) if np.isfinite(d50).any() else 0.2)
            B = np.where(np.isfinite(B), B, np.nanmedian(B))
            bruun = PR.bruun_mc(np.full(len(km), slr), T - anio_base, H12, d50, B, min(cfg.n_mc, 2000), cfg.semilla, rh_rango_mm=tuple(br.get("rh_mm", [3.4, 6.15])),
                                H12_max_m=np.full(len(km), float(br.get("H12_max_m", br.get("H12_m", 4.0)))) if "H12" not in rolv else None)
            ret = ret + bruun["bruun_m"].to_numpy()
        # % bajo el nivel del mar del escenario: tabla por escenario (campos_escenario) o recálculo sobre el DEM con umbral = SLR
        pct_nivel = None
        if "nivel_mar" in roles:
            vn = next(v_ for v_ in p["variables"] if v_["codigo"] == roles["nivel_mar"])
            ce = vn.get("campos_escenario") or {}
            try:
                if vn["metodo"] == "tabla_por_id" and k in ce:
                    pct_nivel = MU.tabla_por_id(t, vn["fuente"], vn.get("capa") or "id_ivc", ce[k]).to_numpy(float)
                elif vn["metodo"] == "raster_estadistico" and vn.get("estadistico") == "pct_bajo":
                    pct_nivel = MU.raster_estadistico(t, vn["fuente"], float(vn.get("d0") or 0), float(vn.get("d1") or 500), float(p["transectos"].get("espaciado_m") or 100),
                                                      "pct_bajo", float(e.get("slr_mm", 0)) / 1000.0).to_numpy(float)
            except Exception:  # noqa: BLE001
                pct_nivel = None
        v, Xt = PR.ivc_futuro(X, w, cols, roles, clasif, vals, tabla[f"tasaL_{T}"].to_numpy(float), ret, pct_nivel, escala)
        cl = NO.clase_de_indice_01(v, cortes)
        d = pd.DataFrame({"id_ivc": t["id_ivc"].values, f"ivc_{k}": v, f"clase_{k}": cl, f"retroceso_m_{k}": ret})
        if bruun is not None:
            d[f"bruun_m_{k}"] = bruun["bruun_m"].to_numpy()
        for r_, cod in roles.items():
            d[f"{cod}_{k}"] = Xt[:, cols.index(cod)]
        esc_tab[k] = d
        resumen.append({"escenario": f"{e['nombre']}, {T}", "clave": k, **_pcts(cl), "ivc_medio": float(np.nanmean(v)),
                        "retroceso_mediana_m": float(np.nanmedian(ret[desp < 0])) if (desp < 0).any() else 0.0, "pct_en_retroceso": float(100 * np.nanmean(desp < 0)),
                        "bruun_mediana_m": float(np.nanmedian(bruun["bruun_m"])) if bruun is not None else None})
    return {"config": cfg, "ventanas": vent, "ajuste": aj, "tabla": tabla, "lineas": lineas, "escenarios": esc_tab, "resumen": pd.DataFrame(resumen), "anio_ref": anio_ref, "rasgos": H,
            "sigma_regional": pr["sigma_regional"]}


def _pcts(cl) -> dict:
    cl = np.asarray(cl, float); ok = np.isfinite(cl)
    return {f"pct_clase_{k}": float(100 * np.mean(cl[ok] == k)) if ok.any() else np.nan for k in range(1, 6)} | {"pct_alta_muy_alta": float(100 * np.mean(cl[ok] >= 4)) if ok.any() else np.nan}


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------
def exportar_todo(p: dict, carpeta: str | os.PathLike, res: dict) -> list[Path]:
    """Escribe los productos disponibles del proyecto (transectos, tasas, variables, clases, índice, proyección) y el JSON."""
    out = Path(carpeta); out.mkdir(parents=True, exist_ok=True)
    escritos = [guardar_proyecto(p, out)]

    def csv(df, nombre):
        r = out / f"{nombre}.csv"; df.to_csv(r, index=False, encoding="utf-8-sig"); escritos.append(r)

    def gpkg(g, nombre):
        r = out / f"{nombre}.gpkg"
        gg = g.copy()
        for c_ in gg.columns:
            if c_ != "geometry" and pd.api.types.is_datetime64_any_dtype(gg[c_]):
                gg[c_] = gg[c_].astype(str)
        gg.to_file(r, driver="GPKG"); escritos.append(r)

    if "transectos" in res:
        t = res["transectos"]["transectos"]
        gpkg(t, "transectos_tasas"); gpkg(res["transectos"]["base"], "linea_base")
        csv(res["transectos"]["inter"].assign(fecha=lambda d: d["fecha"].astype(str)), "intersecciones")
        csv(res["transectos"]["tasas"].assign(fecha_ini=lambda d: d["fecha_ini"].astype(str), fecha_fin=lambda d: d["fecha_fin"].astype(str)), "tasas")
    if "variables" in res:
        csv(res["variables"]["valores"], "variables_valores"); csv(res["variables"]["clases"], "variables_clases")
    if "pesos" in res:
        csv(res["pesos"]["ewm"], "pesos_ewm")
        if "fahp" in res["pesos"]:
            csv(res["pesos"]["fahp"], "pesos_fahp")
        csv(pd.DataFrame({k: v for k, v in res["pesos"]["pesos"].items()}, index=res["pesos"]["variables"]).reset_index().rename(columns={"index": "variable"}), "pesos_todos")
    if "indice" in res:
        csv(res["indice"]["tabla"], "indice_transectos"); csv(res["indice"]["validacion"], "validacion"); csv(res["indice"]["concordancia"], "concordancia")
        csv(res["indice"]["vif"], "redundancia_vif"); csv(res["indice"]["sensibilidad"], "sensibilidad_pesos")
        if "validacion_bloques" in res["indice"] and len(res["indice"]["validacion_bloques"]):
            csv(res["indice"]["validacion_bloques"], "validacion_por_bloque")
        if "redundancia_rho" in res["indice"]:
            csv(res["indice"]["redundancia_rho"].reset_index().rename(columns={"index": "variable"}), "redundancia_spearman")
        if "transectos" in res:
            g = res["transectos"]["transectos"][["id_ivc", "geometry"]].merge(res["indice"]["tabla"], on="id_ivc")
            gpkg(gpd.GeoDataFrame(g, geometry="geometry", crs=res["transectos"]["transectos"].crs), "indice_transectos")
    if "proyeccion" in res:
        csv(res["proyeccion"]["tabla"], "proyeccion_transectos"); csv(res["proyeccion"]["resumen"], "proyeccion_resumen")
        gpkg(res["proyeccion"]["lineas"], "lineas_proyectadas")
        for k, d in res["proyeccion"]["escenarios"].items():
            csv(d, f"escenario_{k}")
        aj = res["proyeccion"]["ajuste"]
        meta = {k: v for k, v in aj.items() if k in ("tipo", "beta", "alfa", "coeficientes", "importancia", "metricas")}
        meta["parametros"] = {k: v for k, v in p.get("proyeccion", {}).items()}
        meta["sigma_regional_usado"] = res["proyeccion"].get("sigma_regional")
        meta["ventanas_historicas"] = [list(map(float, v)) for v in res["proyeccion"].get("ventanas", [])]
        with open(out / "proyeccion_modelo.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1, default=_json_default)
        escritos.append(out / "proyeccion_modelo.json")
        pb = aj.get("por_bloque")
        if pb is not None and len(pb):
            csv(pd.DataFrame(pb), "proyeccion_r2os_por_bloque")
        if "transectos" in res:
            for k, d in res["proyeccion"]["escenarios"].items():
                g = res["transectos"]["transectos"][["id_ivc", "geometry"]].merge(d, on="id_ivc")
                gpkg(gpd.GeoDataFrame(g, geometry="geometry", crs=res["transectos"]["transectos"].crs), f"escenario_{k}")
    return escritos
