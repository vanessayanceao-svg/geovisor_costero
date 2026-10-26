"""Distribución de las variables a los transectos (geometría de ivc_variables.py de la tesis).

Cada transecto tiene un punto P0 (corte con la línea de referencia) y un vector unitario hacia tierra (ux, uy).
La franja de muestreo de un transecto es el rectángulo entre ``d0`` y ``d1`` m tierra adentro desde P0 y de ancho
igual al espaciado de transectos (franjas contiguas, sin solapes). Métodos disponibles:

* ``raster_estadistico``   mediana / media / p90 / mín / máx / % bajo un umbral de un ráster en la franja (malla de puntos).
* ``raster_pendiente``     pendiente media (grados) de un DEM en la franja (diferencias centrales).
* ``vector_categorico``    % de área de cada categoría de una capa de polígonos en la franja y categoría dominante.
* ``vector_numerico``      media ponderada por área de un campo numérico de polígonos (o valor del más cercano a P0).
* ``distancia_a``          distancia (m) desde P0 a la entidad más cercana de una capa (vía, poblado, etc.).
* ``mas_cercano``          valor de un campo del punto/entidad más cercana a P0 (estaciones, boyas).
* ``ancho_barra``          ancho de la barra/isla barrera: desde P0 hacia tierra hasta el primer tramo continuo de agua,
                           con agua = NoData del DEM (DeltaDTM) o una capa de polígonos de agua.
* ``tabla_por_id``         valores ya calculados por transecto (CSV con id y valor).

Todas las capas se reproyectan al CRS métrico de los transectos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point, box


# ---------------------------------------------------------------------------
# Geometría de muestreo
# ---------------------------------------------------------------------------
def _normal(t: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    ux, uy = t["ux"].to_numpy(float), t["uy"].to_numpy(float)
    return -uy, ux


def franjas(t: gpd.GeoDataFrame, d0: float, d1: float, ancho_m: float) -> gpd.GeoDataFrame:
    nx, ny = _normal(t)
    h = ancho_m / 2
    geoms = []
    for i, r in enumerate(t.itertuples()):
        p0 = np.array([r.x_p0, r.y_p0]); u = np.array([r.ux, r.uy]); n = np.array([nx[i], ny[i]])
        geoms.append(Polygon([p0 + d0 * u + h * n, p0 + d1 * u + h * n, p0 + d1 * u - h * n, p0 + d0 * u - h * n]))
    return gpd.GeoDataFrame({"id_ivc": t["id_ivc"].values}, geometry=geoms, crs=t.crs)


def malla(r, d0: float, d1: float, ancho_m: float, paso: float = 10.0, nx: float = 0.0, ny: float = 0.0):
    a = np.arange(d0 + paso / 2, d1, paso)
    b = np.arange(-ancho_m / 2 + paso / 2, ancho_m / 2, paso)
    A, B = np.meshgrid(a, b)
    x = r.x_p0 + A.ravel() * r.ux + B.ravel() * nx
    y = r.y_p0 + A.ravel() * r.uy + B.ravel() * ny
    return x, y


# ---------------------------------------------------------------------------
# Rásteres
# ---------------------------------------------------------------------------
def raster_a_crs(ruta: str, epsg: int, res: float | None = None, metodo: str = "bilinear", bbox=None):
    """Lee un ráster (banda 1) reproyectado al CRS métrico; NoData → NaN. Devuelve (array, transform, dentro)."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.windows import from_bounds

    with rasterio.open(ruta) as src:
        if bbox is not None:
            from pyproj import Transformer

            tf = Transformer.from_crs(f"EPSG:{epsg}", src.crs, always_xy=True)
            xs, ys = tf.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
            win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            a = src.read(1, window=win).astype("float64")
            src_tr = src.window_transform(win)
            w0, h0 = int(win.width), int(win.height)
            bounds = rasterio.windows.bounds(win, src.transform)
        else:
            a = src.read(1).astype("float64"); src_tr = src.transform; w0, h0 = src.width, src.height; bounds = src.bounds
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        if res is None:
            res = max(abs(src.res[0]), abs(src.res[1]))
            if src.crs and src.crs.is_geographic:
                res = res * 111000
        tr, w, h = calculate_default_transform(src.crs, f"EPSG:{epsg}", w0, h0, *bounds, resolution=res)
        dst = np.full((h, w), np.nan)
        reproject(a, dst, src_transform=src_tr, src_crs=src.crs, dst_transform=tr, dst_crs=f"EPSG:{epsg}",
                  resampling=getattr(Resampling, metodo), src_nodata=np.nan, dst_nodata=np.nan)
    return dst, tr, res


def muestrear(arr, tr, x, y):
    col = np.floor((np.asarray(x) - tr.c) / tr.a).astype(int)
    fil = np.floor((np.asarray(y) - tr.f) / tr.e).astype(int)
    ok = (fil >= 0) & (fil < arr.shape[0]) & (col >= 0) & (col < arr.shape[1])
    v = np.full(len(col), np.nan)
    v[ok] = arr[fil[ok], col[ok]]
    return v


ESTADISTICOS = {"mediana": np.nanmedian, "media": np.nanmean, "p90": lambda v: np.nanpercentile(v, 90),
                "p10": lambda v: np.nanpercentile(v, 10), "min": np.nanmin, "max": np.nanmax}


def raster_estadistico(t: gpd.GeoDataFrame, ruta: str, d0: float, d1: float, ancho_m: float, estadistico: str = "mediana",
                       umbral: float | None = None, paso: float = 10.0, res: float | None = None, metodo: str = "bilinear") -> pd.Series:
    """Estadístico del ráster en la franja [d0, d1]; 'pct_bajo' = % de celdas ≤ umbral; 'pct_nodata' = % sin dato."""
    epsg = t.crs.to_epsg()
    fr = franjas(t, d0, d1, ancho_m)
    arr, tr, _ = raster_a_crs(ruta, epsg, res, metodo, bbox=tuple(fr.total_bounds + np.array([-500, -500, 500, 500])))
    nx, ny = _normal(t)
    out = []
    for i, r in enumerate(t.itertuples()):
        x, y = malla(r, d0, d1, ancho_m, paso, nx[i], ny[i])
        v = muestrear(arr, tr, x, y)
        if estadistico == "pct_nodata":
            out.append(100 * np.mean(~np.isfinite(v)))
            continue
        vv = v[np.isfinite(v)]
        if not vv.size:
            out.append(np.nan)
        elif estadistico == "pct_bajo":
            out.append(100 * np.mean(vv <= (umbral if umbral is not None else 0)))
        else:
            out.append(float(ESTADISTICOS[estadistico](vv)))
    return pd.Series(out, index=t["id_ivc"].values, name="valor")


def raster_pendiente(t: gpd.GeoDataFrame, ruta: str, d0: float, d1: float, ancho_m: float, res: float = 30.0, paso: float = 10.0) -> pd.Series:
    """Pendiente media del terreno (grados) en la franja, por diferencias centrales sobre el DEM remuestreado a ``res``."""
    epsg = t.crs.to_epsg()
    fr = franjas(t, d0, d1, ancho_m)
    z, tr, _ = raster_a_crs(ruta, epsg, res, "nearest", bbox=tuple(fr.total_bounds + np.array([-500, -500, 500, 500])))
    gy, gx = np.gradient(z, res)
    s = np.degrees(np.arctan(np.hypot(gx, gy)))
    nx, ny = _normal(t)
    out = []
    for i, r in enumerate(t.itertuples()):
        x, y = malla(r, d0, d1, ancho_m, paso, nx[i], ny[i])
        v = muestrear(s, tr, x, y); v = v[np.isfinite(v)]
        out.append(float(v.mean()) if v.size else np.nan)
    return pd.Series(out, index=t["id_ivc"].values, name="valor")


# ---------------------------------------------------------------------------
# Vectores
# ---------------------------------------------------------------------------
def _leer_vector(capa, crs) -> gpd.GeoDataFrame:
    g = capa if isinstance(capa, gpd.GeoDataFrame) else gpd.read_file(capa)
    if g.crs is None:
        raise ValueError("La capa no declara CRS")
    return g.to_crs(crs)


def vector_categorico(t: gpd.GeoDataFrame, capa, campo: str, d0: float, d1: float, ancho_m: float, excluir: tuple = ()) -> tuple[pd.DataFrame, pd.Series]:
    """(tabla % de área por categoría, categoría dominante) en la franja; 'sin_dato' = parte de la franja sin polígono."""
    g = _leer_vector(capa, t.crs)
    if campo not in g.columns:
        raise ValueError(f"La capa no tiene el campo '{campo}'")
    fr = franjas(t, d0, d1, ancho_m)
    g = g[[campo, "geometry"]].copy()
    g[campo] = g[campo].astype(str).str.strip()
    g["geometry"] = g.geometry.buffer(0)
    g = g.dissolve(by=campo, as_index=False)             # evita contar dos veces polígonos solapados de una misma categoría
    inter = gpd.overlay(fr, g, how="intersection", keep_geom_type=True)
    inter["a"] = inter.area
    tab = inter.pivot_table(index="id_ivc", columns=campo, values="a", aggfunc="sum", fill_value=0)
    area = fr.set_index("id_ivc").area
    tab = tab.reindex(area.index, fill_value=0).div(area, axis=0) * 100
    solape = (tab.sum(axis=1) - 100).clip(lower=0)      # solape entre categorías distintas (capas no topológicas)
    tab["sin_dato"] = (100 - tab.sum(axis=1)).clip(lower=0)
    tab["solape_pct"] = solape
    excluir = tuple(str(x).strip().lower() for x in excluir)
    cols = [c for c in tab.columns if c not in ("sin_dato", "solape_pct") and str(c).lower() not in excluir]
    sub = tab[cols] if cols else tab[[]]
    dom = sub.idxmax(axis=1) if cols else pd.Series("sin_dato", index=tab.index)
    if cols:
        dom[sub.max(axis=1) <= 0] = "sin_dato"
    return tab.round(2), dom.rename("valor")


def vector_numerico(t: gpd.GeoDataFrame, capa, campo: str, d0: float, d1: float, ancho_m: float, modo: str = "media_area") -> pd.Series:
    """Media ponderada por área del campo en la franja ('media_area') o valor del polígono más cercano a P0 ('cercano')."""
    g = _leer_vector(capa, t.crs)
    g[campo] = pd.to_numeric(g[campo], errors="coerce")
    if modo == "cercano":
        return mas_cercano(t, g, campo)
    fr = franjas(t, d0, d1, ancho_m)
    g = g[[campo, "geometry"]].copy(); g["geometry"] = g.geometry.buffer(0)
    inter = gpd.overlay(fr, g, how="intersection", keep_geom_type=True)
    inter["a"] = inter.area
    inter = inter[inter[campo].notna()]
    num = (inter["a"] * inter[campo]).groupby(inter["id_ivc"]).sum()
    den = inter["a"].groupby(inter["id_ivc"]).sum()
    return (num / den).reindex(t["id_ivc"].values).rename("valor")


def distancia_a(t: gpd.GeoDataFrame, capa, filtro: str | None = None) -> pd.Series:
    """Distancia (m) desde P0 a la entidad más cercana de la capa (opcionalmente filtrada con una expresión pandas)."""
    g = _leer_vector(capa, t.crs)
    if filtro:
        g = g.query(filtro)
    from shapely.strtree import STRtree

    geoms = list(g.geometry)
    arbol = STRtree(geoms)
    out = []
    for r in t.itertuples():
        p = Point(r.x_p0, r.y_p0)
        i = arbol.nearest(p)
        out.append(float(p.distance(geoms[int(i)])) if i is not None else np.nan)
    return pd.Series(out, index=t["id_ivc"].values, name="valor")


def mas_cercano(t: gpd.GeoDataFrame, capa, campo: str, max_dist_m: float | None = None) -> pd.Series:
    """Valor del campo de la entidad más cercana a P0."""
    g = _leer_vector(capa, t.crs)
    P0 = gpd.GeoDataFrame({"id_ivc": t["id_ivc"].values}, geometry=gpd.points_from_xy(t["x_p0"], t["y_p0"]), crs=t.crs)
    j = gpd.sjoin_nearest(P0, g[[campo, "geometry"]], how="left", max_distance=max_dist_m).drop_duplicates("id_ivc").set_index("id_ivc")
    return j[campo].reindex(t["id_ivc"].values).rename("valor")


def tabla_por_id(t: gpd.GeoDataFrame, ruta_csv: str, campo_id: str, campo_valor: str) -> pd.Series:
    d = pd.read_csv(ruta_csv, encoding="utf-8-sig")
    if campo_id not in d.columns or campo_valor not in d.columns:
        raise ValueError(f"La tabla no tiene las columnas '{campo_id}' y '{campo_valor}'")
    if d[campo_id].duplicated().any():
        rep = d.loc[d[campo_id].duplicated(), campo_id].unique()[:5]
        raise ValueError(f"La columna '{campo_id}' tiene ids repetidos (p. ej. {', '.join(map(str, rep))}); debe haber una fila por transecto")
    s = d.set_index(campo_id)[campo_valor]
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().sum() >= 0.5 * s.notna().sum():      # columna numérica; si es categórica se conserva el texto
        s = num
    return s.reindex(t["id_ivc"].values).rename("valor")


# ---------------------------------------------------------------------------
# Ancho de la barra / isla barrera
# ---------------------------------------------------------------------------
def ancho_barra(t: gpd.GeoDataFrame, dem: str | None = None, agua: str | gpd.GeoDataFrame | None = None, rayo_max_m: float = 6000.0,
                agua_continua_m: float = 60.0, paso: float = 10.0, res: float = 30.0) -> pd.DataFrame:
    """Ancho (m) desde P0 hacia tierra hasta el primer tramo continuo de agua de ≥ ``agua_continua_m``.

    Agua = NoData del DEM (DeltaDTM marca mar y lagunas como NoData), o una capa de polígonos de agua.
    Devuelve ancho_m y censura ('', 'minimo' = no se encontró agua en el rayo, 'sin_tierra')."""
    if dem is None and agua is None:
        raise ValueError("Indique un DEM (agua = NoData) o una capa de agua")
    epsg = t.crs.to_epsg()
    n_run = max(1, int(agua_continua_m / paso))
    d = np.arange(0, rayo_max_m, paso)
    if dem is not None:
        caja = tuple(np.array([t["x_p0"].min(), t["y_p0"].min(), t["x_p0"].max(), t["y_p0"].max()]) + np.array([-rayo_max_m, -rayo_max_m, rayo_max_m, rayo_max_m]))
        z, tr, _ = raster_a_crs(dem, epsg, res, "nearest", bbox=caja)
        import rasterio

        with rasterio.open(dem) as src:
            cob = gpd.GeoSeries([box(*src.bounds)], crs=src.crs).to_crs(epsg).iloc[0]
        from rasterio.features import rasterize

        dentro = rasterize([(cob, 1)], out_shape=z.shape, transform=tr, fill=0).astype(bool)
        es_agua = lambda x, y: (muestrear((dentro & ~np.isfinite(z)).astype(float), tr, x, y) == 1)  # noqa: E731
        fuera_f = lambda x, y: (muestrear(dentro.astype(float), tr, x, y) != 1)  # noqa: E731
    else:
        g = _leer_vector(agua, t.crs)
        from shapely.strtree import STRtree
        from shapely.ops import unary_union

        u = unary_union(list(g.geometry.buffer(0)))
        es_agua = lambda x, y: np.array([u.contains(Point(a, b)) for a, b in zip(x, y)])  # noqa: E731
        fuera_f = lambda x, y: np.zeros(len(x), bool)  # noqa: E731
    anchos, cens = [], []
    for r in t.itertuples():
        xr, yr = r.x_p0 + d * r.ux, r.y_p0 + d * r.uy
        ag = es_agua(xr, yr)
        tierra = ~ag
        idx = np.flatnonzero(tierra)
        if not idx.size:
            anchos.append(0.0); cens.append("sin_tierra"); continue
        i0 = idx[0]
        corr = np.convolve(ag[i0:].astype(int), np.ones(n_run, int), "valid")
        k = np.flatnonzero(corr == n_run)
        if k.size:
            anchos.append(float(d[i0 + k[0]])); cens.append("")
        else:
            fuera = np.flatnonzero(fuera_f(xr, yr)[i0:])
            anchos.append(float(d[i0 + fuera[0]]) if fuera.size else rayo_max_m); cens.append("minimo")
    return pd.DataFrame({"valor": anchos, "censura": cens}, index=t["id_ivc"].values)
