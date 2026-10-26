"""Índice de Vulnerabilidad Costera (IVC): acceso a las versiones calculadas en la tesis.

El geovisor NO calcula un IVC propio: lee los resultados de
``Mapas_IVC/ivc_versiones.py`` (transectos con IVC 0‑1 y clase 1‑5 por
versión) y los rásteres ``QGIS_IVC/rasters/ivc_<version>*.tif``.

Clasificación (documentada en LEEME_mapas.txt): IVC = Σ w_j·c_j con clases
c_j ∈ {1..5} y pesos EWM; se reescala (IVC−1)/4 a 0‑1 y se corta en intervalos
iguales de 0,2 → clases 1 (muy baja) … 5 (muy alta). Los cortes están en
config.yaml (``ivc.cortes``) y se muestran en la leyenda.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .catalogo_datos import CAPAS
from .vectores import CapaNoDisponible, leer_capa

# Grupos de versiones (según QGIS_IVC/LEEME_QGIS.txt)
GRUPOS_VERSIONES = {
    "Índice principal": ["ewm_total"],
    "Métodos de agregación": ["ewm_estructural", "topsis_ewm", "pesos_iguales", "cvi_gornitz"],
    "Estado 2005 y 2026 (modelos)": ["ewm_2005", "ewm_2026", "persistencia_2026", "rf_2026", "ridge_2026", "cnn_lstm_2026", "apilamiento_2026"],
    "Escenarios SSP": ["ssp245_2050", "ssp585_2050", "ssp245_2100", "ssp585_2100"],
}
ESCENARIOS = {"ssp245_2050": ("SSP2-4.5", 2050), "ssp585_2050": ("SSP5-8.5", 2050), "ssp245_2100": ("SSP2-4.5", 2100), "ssp585_2100": ("SSP5-8.5", 2100)}

# Variables (clases 1‑5) y su dimensión metodológica
DIMENSIONES_VARIABLES = {
    "c_cambio_costa": ("Cambio de la línea de costa (LRR)", "Dinámica litoral"),
    "c_geomorfologia": ("Geomorfología", "Físicas y geomorfológicas"),
    "c_elevacion": ("Elevación", "Físicas y geomorfológicas"),
    "c_pendiente": ("Pendiente del terreno", "Físicas y geomorfológicas"),
    "c_pendiente_playa": ("Pendiente de playa", "Físicas y geomorfológicas"),
    "c_ancho_barra": ("Ancho de la barra", "Físicas y geomorfológicas"),
    "c_granulometria": ("Granulometría", "Geotécnicas"),
    "c_sustrato": ("Sustrato", "Geotécnicas"),
    "c_oleaje": ("Oleaje (Hs)", "Oceanográficas"),
    "c_nivel_mar": ("Nivel del mar (AR6)", "Oceanográficas"),
    "c_cobertura": ("Cobertura de la tierra", "Ambientales"),
    "c_uso_suelo": ("Uso del suelo", "Ambientales"),
    "c_dist_ruta90": ("Distancia a la Ruta 90", "Infraestructura"),
    "c_vivienda": ("Edificaciones", "Infraestructura"),
    "c_densidad_pob": ("Densidad de población", "Socioeconómicas"),
}


def versiones(cfg: dict) -> pd.DataFrame:
    p = CAPAS["ivc_versiones"].ruta(cfg)
    if p.exists():
        return pd.read_csv(p, encoding="utf-8-sig")
    return pd.DataFrame(columns=["version", "titulo"])


def titulo_version(cfg: dict, v: str) -> str:
    df = versiones(cfg)
    m = df[df["version"] == v]
    return str(m["titulo"].iloc[0]) if not m.empty else v


def cargar_transectos_ivc(cfg: dict) -> gpd.GeoDataFrame:
    return leer_capa(cfg, "ivc_transectos")


def cargar_costa_ivc(cfg: dict) -> gpd.GeoDataFrame:
    return leer_capa(cfg, "ivc_costa")


def columnas_version(g: gpd.GeoDataFrame, v: str) -> tuple[str | None, str | None]:
    """(columna IVC 0‑1, columna de clase) para una versión; None si no existen."""
    if v in ESCENARIOS:
        c_ivc, c_cl = f"ivc_ewm_total_{v}", f"clase_ivc_ewm_total_{v}"
    else:
        c_ivc, c_cl = f"ivc_{v}", f"clase_{v}"
    return (c_ivc if c_ivc in g.columns else None, c_cl if c_cl in g.columns else None)


def columnas_incertidumbre(g: gpd.GeoDataFrame, v: str) -> tuple[str | None, str | None]:
    if v not in ESCENARIOS:
        return None, None
    a, b = f"ivc_ewm_total_{v}_inf", f"ivc_ewm_total_{v}_sup"
    return (a if a in g.columns else None, b if b in g.columns else None)


def clasificar(valores: pd.Series, cfg: dict) -> pd.Series:
    """Reproduce la clasificación documentada (intervalos iguales de 0,2 en 0‑1). Solo se usa para verificar/leyendas."""
    cortes = cfg["ivc"]["cortes"]
    v = pd.to_numeric(valores, errors="coerce")
    clase = pd.Series(np.digitize(v.fillna(-1), cortes, right=False) + 1, index=v.index).astype("float")
    clase[v.isna()] = np.nan
    return clase.clip(1, 5).astype("Int64")


def estadisticas(g: gpd.GeoDataFrame, col_ivc: str, col_clase: str | None, cfg: dict) -> dict:
    s = pd.to_numeric(g[col_ivc], errors="coerce")
    out = {"n": int(s.notna().sum()), "n_sin_dato": int(s.isna().sum()), "media": float(s.mean()), "mediana": float(s.median()),
           "min": float(s.min()), "max": float(s.max()), "desv": float(s.std())}
    if col_clase:
        cl = pd.to_numeric(g[col_clase], errors="coerce")
        conteo = cl.value_counts().sort_index()
        out["clases"] = {int(k): int(v) for k, v in conteo.items()}
        out["pct_clases"] = {int(k): float(v) for k, v in (conteo / cl.notna().sum() * 100).items()}
        # longitud de costa por clase (transectos cada 100 m -> 0,1 km por transecto)
        out["km_por_clase"] = {int(k): float(v * 0.1) for k, v in conteo.items()}
        out["pct_alta_muy_alta"] = float(((cl >= 4).sum() / max(cl.notna().sum(), 1)) * 100)
    return out


def sectores_altos(g: gpd.GeoDataFrame, col_ivc: str, col_clase: str | None, n: int = 15) -> pd.DataFrame:
    cols = [c for c in ("id_ivc", "dist_costa_km", "zona", col_ivc, col_clase) if c and c in g.columns]
    d = pd.DataFrame(g[cols]).copy()
    d[col_ivc] = pd.to_numeric(d[col_ivc], errors="coerce")
    return d.nlargest(n, col_ivc)


def rasters_version(cfg: dict, v: str) -> tuple[Path | None, Path | None]:
    carpeta = CAPAS["ivc_rasters_dir"].ruta(cfg)
    calor, valor = carpeta / f"ivc_{v}.tif", carpeta / f"ivc_{v}_valor.tif"
    return (calor if calor.exists() else None, valor if valor.exists() else None)


def cargar_pesos(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["ivc_pesos"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_clases_variables(cfg: dict, estado: str = "2026") -> pd.DataFrame | None:
    """Clases 1‑5 de cada variable por transecto: estado 2026 (tabla_clases_1_5_ivc.csv) o 2005 reconstruido (clases_2005_reconstruidas.csv)."""
    p = CAPAS["ivc_clases_2005" if str(estado) == "2005" else "ivc_clases_variables"].ruta(cfg)
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


def cambio_clases_2005_2026(cfg: dict) -> pd.DataFrame | None:
    """Por variable: % de transectos (con línea de 2005) cuya clase 1‑5 cambia entre 2005 reconstruido y 2026, y cambio medio de clase.

    Cálculo del geovisor a partir de los dos archivos de clases (no recalcula ninguna variable)."""
    a, b = cargar_clases_variables(cfg, "2005"), cargar_clases_variables(cfg, "2026")
    if a is None or b is None:
        return None
    m = a.merge(b, on="id_ivc", suffixes=("_2005", "_2026"))
    m = m[m.filter(like="_2005").notna().all(axis=1)]  # solo transectos con línea de 2005 (650)
    filas = []
    for v, (nombre, dim) in DIMENSIONES_VARIABLES.items():
        c05, c26 = f"{v}_2005", f"{v}_2026"
        if c05 not in m or c26 not in m:
            continue
        x, y = pd.to_numeric(m[c05], errors="coerce"), pd.to_numeric(m[c26], errors="coerce")
        ok = x.notna() & y.notna()
        filas.append({"variable": v, "nombre": nombre, "dimensión": dim, "n": int(ok.sum()), "pct_cambia": float((x[ok] != y[ok]).mean() * 100) if ok.any() else None,
                      "media_2005": float(x[ok].mean()) if ok.any() else None, "media_2026": float(y[ok].mean()) if ok.any() else None,
                      "recalculada_desde_2005": v in ("c_cambio_costa", "c_ancho_barra", "c_dist_ruta90", "c_geomorfologia", "c_sustrato", "c_uso_suelo")})
    return pd.DataFrame(filas)


def cargar_variables(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["ivc_variables"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_diccionario(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["ivc_diccionario"].ruta(cfg)
    return pd.read_csv(p, encoding="utf-8", encoding_errors="replace") if p.exists() else None


def cargar_concordancia(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["ivc_concordancia"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def cargar_validacion_indices(cfg: dict) -> pd.DataFrame | None:
    p = CAPAS["multicriterio_validacion"].ruta(cfg)
    return pd.read_csv(p) if p.exists() else None


def transectos_con_variables(cfg: dict, estado: str = "2026") -> gpd.GeoDataFrame | None:
    """Une la geometría de los transectos del IVC con las clases 1‑5 de cada variable (por id_ivc)."""
    try:
        g = cargar_transectos_ivc(cfg)[["id_ivc", "dist_costa_km", "zona", "geometry"]]
    except CapaNoDisponible:
        return None
    cl = cargar_clases_variables(cfg, estado)
    if cl is None:
        return None
    cols = ["id_ivc"] + [c for c in cl.columns if c.startswith("c_")]
    return gpd.GeoDataFrame(g.merge(cl[cols], on="id_ivc", how="left"), geometry="geometry", crs=g.crs)


def requisitos_para_activar() -> str:
    return (
        "Para activar este módulo se necesita al menos uno de:\n"
        "• **Vector por transecto**: GeoPackage/Shapefile/GeoJSON con CRS declarado y columnas `ivc_<version>` (0–1) y `clase_<version>` (1–5), "
        "como `QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg` (capa `transectos_ivc`).\n"
        "• **Ráster**: GeoTIFF de una banda con el valor del IVC (nodata declarado) o RGBA ya coloreado, como `QGIS_IVC/rasters/ivc_<version>_valor.tif`.\n"
        "• **Tabla**: CSV con `id_ivc` y columnas `c_<variable>` (clases 1–5) para los componentes, como `exportar_coastsat/ivc/tabla_clases_1_5_ivc.csv`.\n"
        "Además, `QGIS_IVC/datos/versiones.csv` con las columnas `version,titulo` da nombre a cada versión."
    )
