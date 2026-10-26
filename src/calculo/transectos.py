"""Línea base, transectos e intersecciones con las líneas de costa (método DSAS, Himmelstoss et al., 2021).

* ``generar_linea_base``: desplaza la línea de referencia hacia tierra (o mar) y la suaviza.
* ``generar_transectos``: emite transectos perpendiculares a la línea base cada ``espaciado`` m; la orientación se toma
  de la línea base suavizada con una ventana de ``suavizado`` m (DSAS: *smoothing distance*), y el transecto se lanza
  hacia el lado del mar (el lado donde está la línea de referencia).
* ``intersecciones``: para cada transecto y fecha, punto de corte con la línea de costa y distancia desde la línea base
  (DSAS *Distance*; positiva hacia el mar).

Convención de la geometría de los transectos (la de DSAS exportado por la tesis): vértice 0 = extremo mar,
último vértice = punto sobre la línea base.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, MultiLineString
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree


def _partes(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            out.extend(_partes(g))
        return out
    return []


def unir_lineas(g: gpd.GeoDataFrame | gpd.GeoSeries) -> list[LineString]:
    """Fusiona los tramos de una capa de líneas en el menor número posible de LineStrings continuas."""
    partes = []
    for geom in (g.geometry if hasattr(g, "geometry") else g):
        partes.extend(_partes(geom))
    if not partes:
        return []
    m = linemerge(MultiLineString(partes)) if len(partes) > 1 else partes[0]
    return _partes(m)


def suavizar_linea(ln: LineString, ventana_m: float, paso_m: float = 10.0) -> LineString:
    """Remuestrea la línea cada ``paso_m`` y aplica una media móvil de ``ventana_m`` a las coordenadas."""
    if ln.length < paso_m * 3:
        return ln
    d = np.arange(0, ln.length, paso_m)
    d = np.append(d, ln.length)
    xy = np.array([ln.interpolate(x).coords[0][:2] for x in d])
    k = max(1, int(round(ventana_m / paso_m)))
    if k <= 1:
        return LineString(xy)
    ker = np.ones(k) / k
    pad = k // 2
    xp = np.pad(xy, ((pad, pad), (0, 0)), mode="edge")
    xs = np.convolve(xp[:, 0], ker, mode="valid")
    ys = np.convolve(xp[:, 1], ker, mode="valid")
    n = len(xy)
    return LineString(np.c_[xs[:n], ys[:n]])


def generar_linea_base(linea_ref: gpd.GeoDataFrame, desplazamiento_m: float = 300.0, hacia: str = "tierra",
                       suavizado_m: float = 500.0, lado_tierra: str | None = None) -> gpd.GeoDataFrame:
    """Línea base paralela a la línea de referencia, desplazada ``desplazamiento_m`` hacia tierra (o mar).

    ``lado_tierra``: 'izquierda' o 'derecha' respecto del sentido de digitalización de la línea; si es None se
    estima con el centroide de la capa (tierra = lado donde está el centroide de la envolvente... no siempre válido),
    por lo que conviene fijarlo. La línea se suaviza antes del desplazamiento para evitar lazos."""
    partes = unir_lineas(linea_ref)
    out = []
    for ln in partes:
        s = suavizar_linea(ln, suavizado_m)
        lado = lado_tierra or "derecha"
        signo = 1.0 if lado == "izquierda" else -1.0
        if hacia == "mar":
            signo = -signo
        off = s.offset_curve(signo * desplazamiento_m, join_style=1)
        for p in _partes(off):
            if p.length > desplazamiento_m:
                out.append(p)
    if not out:
        raise ValueError("No se pudo generar la línea base (pruebe otro lado o un desplazamiento menor)")
    return gpd.GeoDataFrame({"id_base": range(1, len(out) + 1)}, geometry=out, crs=linea_ref.crs)


@dataclass
class ParamTransectos:
    espaciado_m: float = 100.0
    longitud_m: float = 1000.0
    suavizado_m: float = 500.0      # ventana para la orientación (DSAS smoothing distance)
    hacia_tierra_m: float = 0.0     # prolongación del transecto por detrás de la línea base (para las franjas)


def generar_transectos(linea_base: gpd.GeoDataFrame, linea_ref: gpd.GeoDataFrame, p: ParamTransectos) -> gpd.GeoDataFrame:
    """Transectos perpendiculares a la línea base, orientados hacia el lado donde está la línea de referencia."""
    ref_union = unary_union(list(linea_ref.geometry))
    filas, geoms = [], []
    orden = 0
    for id_base, ln in enumerate(unir_lineas(linea_base), start=1):
        s = suavizar_linea(ln, p.suavizado_m)
        pasos = np.arange(0, ln.length + 1e-6, p.espaciado_m)
        for d in pasos:
            pb = ln.interpolate(d)
            # dirección local de la línea base suavizada (proyección del punto)
            ds = s.project(pb)
            a = s.interpolate(max(0, ds - p.suavizado_m / 2)).coords[0]
            b = s.interpolate(min(s.length, ds + p.suavizado_m / 2)).coords[0]
            t = np.array([b[0] - a[0], b[1] - a[1]])
            if np.hypot(*t) == 0:
                continue
            t /= np.hypot(*t)
            n = np.array([-t[1], t[0]])
            base = np.array(pb.coords[0][:2])
            # lado del mar: el rayo que corta (o se acerca más) a la línea de referencia
            c1, c2 = base + n * p.longitud_m, base - n * p.longitud_m
            d1, d2 = LineString([base, c1]).distance(ref_union), LineString([base, c2]).distance(ref_union)
            if d1 == 0 and d2 == 0:
                d1, d2 = Point(c1).distance(ref_union), Point(c2).distance(ref_union)
            nmar = n if d1 <= d2 else -n
            mar = base + nmar * p.longitud_m
            tierra = base - nmar * p.hacia_tierra_m if p.hacia_tierra_m > 0 else base
            orden += 1
            az = (np.degrees(np.arctan2(nmar[0], nmar[1])) + 360) % 360
            filas.append({"BaselineID": id_base, "TransOrder": orden, "Azimuth": round(az, 2), "Length": p.longitud_m,
                          "x_base": base[0], "y_base": base[1], "ux": -nmar[0], "uy": -nmar[1]})
            geoms.append(LineString([mar, tierra]))
    g = gpd.GeoDataFrame(filas, geometry=geoms, crs=linea_base.crs)
    g["id_t"] = np.arange(1, len(g) + 1)
    return g


def normalizar_transectos(tr: gpd.GeoDataFrame, linea_base: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Transectos importados (p. ej. DSAS): asegura id_t, x_base/y_base y el vector unitario hacia tierra (ux, uy).

    Si viene ``linea_base``, el extremo que toca (o está más cerca de) la línea base se toma como base; si no,
    se asume la convención DSAS (vértice 0 = mar, último = base)."""
    t = tr.copy()
    if "id_t" not in t.columns:
        if {"BaselineID", "TransOrder"} <= set(t.columns):
            t = t.sort_values(["BaselineID", "TransOrder"]).reset_index(drop=True)
        t["id_t"] = np.arange(1, len(t) + 1)
    base_u = unary_union(list(linea_base.geometry)) if linea_base is not None else None
    xb, yb, ux, uy = [], [], [], []
    for geom in t.geometry:
        c = np.asarray(geom.coords)[:, :2]
        mar, base = c[0], c[-1]
        if base_u is not None and Point(c[0]).distance(base_u) < Point(c[-1]).distance(base_u):
            mar, base = c[-1], c[0]
        u = base - mar
        u = u / np.linalg.norm(u)
        xb.append(base[0]); yb.append(base[1]); ux.append(u[0]); uy.append(u[1])
    t["x_base"], t["y_base"], t["ux"], t["uy"] = xb, yb, ux, uy
    return t


def anio_decimal(fechas: pd.Series) -> np.ndarray:
    """Año decimal como DSAS: año + día del año / 365."""
    f = pd.to_datetime(fechas)
    return (f.dt.year + f.dt.dayofyear / 365.0).to_numpy()


def intersecciones(tr: gpd.GeoDataFrame, lineas: gpd.GeoDataFrame, campo_fecha: str, campo_unc: str | None = None,
                   unc_defecto: float = 10.0, criterio: str = "cercana") -> pd.DataFrame:
    """Puntos de corte transecto × línea de costa.

    ``criterio``: 'cercana' (a la línea base, valor por defecto de DSAS), 'lejana', 'mar' (= lejana), 'tierra' (= cercana).
    Devuelve una fila por (id_t, fecha): distancia desde la base (m, + hacia el mar), x, y, incertidumbre."""
    if campo_fecha not in lineas.columns:
        raise ValueError(f"La capa de líneas no tiene el campo de fecha '{campo_fecha}'")
    L = lineas.copy()
    L["_fecha"] = pd.to_datetime(L[campo_fecha], errors="coerce")
    L = L[L["_fecha"].notna()]
    if campo_unc and campo_unc in L:
        u = pd.to_numeric(L[campo_unc], errors="coerce")
        L["_unc"] = u.where(u > 0).fillna(unc_defecto)   # nulos y ceros → incertidumbre por defecto (como DSAS); 1/0² no es un peso válido
    else:
        L["_unc"] = unc_defecto
    arbol = STRtree(list(L.geometry))
    filas = []
    lejana = criterio in ("lejana", "mar")
    for _, r in tr.iterrows():
        geom = r.geometry
        base = np.array([r.x_base, r.y_base])
        u = np.array([r.ux, r.uy])            # hacia tierra
        cand = arbol.query(geom, predicate="intersects")
        if len(cand) == 0:
            continue
        por_fecha: dict = {}
        for i in cand:
            fila = L.iloc[i]
            inter = geom.intersection(fila.geometry)
            pts = []
            if inter.is_empty:
                continue
            if inter.geom_type == "Point":
                pts = [inter]
            elif hasattr(inter, "geoms"):
                for g in inter.geoms:
                    if g.geom_type == "Point":
                        pts.append(g)
                    elif g.geom_type == "LineString":
                        pts.append(g.interpolate(0.5, normalized=True))
            elif inter.geom_type == "LineString":
                pts = [inter.interpolate(0.5, normalized=True)]
            for pt in pts:
                v = np.array(pt.coords[0][:2]) - base
                dist = float(-(v @ u))        # + hacia el mar
                key = fila["_fecha"]
                prev = por_fecha.get(key)
                if prev is None or (lejana and dist > prev[0]) or (not lejana and dist < prev[0]):
                    por_fecha[key] = (dist, pt.x, pt.y, float(fila["_unc"]))
        for f, (dist, x, y, unc) in por_fecha.items():
            filas.append({"id_t": r.id_t, "fecha": f, "distancia_m": dist, "x": x, "y": y, "unc_m": unc})
    out = pd.DataFrame(filas)
    if len(out):
        out["anio_dec"] = anio_decimal(out["fecha"])
    return out.sort_values(["id_t", "fecha"]).reset_index(drop=True)


def p0_de_referencia(tr: gpd.GeoDataFrame, inter: pd.DataFrame, fecha_ref=None) -> gpd.GeoDataFrame:
    """Punto P0 (línea de referencia) por transecto: la fecha indicada o la más reciente disponible.
    Añade x_p0, y_p0, fecha_p0, dist_costa_km (distancia acumulada a lo largo de la costa) e id_ivc."""
    t = tr.copy()
    if len(inter) == 0:
        raise ValueError("No hay intersecciones")
    if fecha_ref is not None:
        f = pd.Timestamp(fecha_ref)
        sel = inter[inter["fecha"] == f]
    else:
        sel = inter.iloc[0:0]
    ult = inter.sort_values("fecha").groupby("id_t").tail(1)
    sel = pd.concat([sel, ult]).drop_duplicates("id_t", keep="first").set_index("id_t")
    t = t.merge(sel[["x", "y", "fecha", "distancia_m"]].rename(columns={"x": "x_p0", "y": "y_p0", "fecha": "fecha_p0", "distancia_m": "dist_p0_m"}), left_on="id_t", right_index=True, how="left")
    falta = t["x_p0"].isna()
    # transectos sin corte con ninguna línea: P0 = punto de la base (se marcan)
    t.loc[falta, "x_p0"] = t.loc[falta, "x_base"]
    t.loc[falta, "y_p0"] = t.loc[falta, "y_base"]
    t["sin_linea_ref"] = falta.astype(int)
    d = np.hypot(np.diff(t["x_p0"]), np.diff(t["y_p0"]))
    t["dist_costa_km"] = np.r_[0, np.cumsum(d)] / 1000
    t["id_ivc"] = np.arange(1, len(t) + 1)
    return t
