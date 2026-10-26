"""Control temporal: fechas reales de observación, selección y navegación.

Las fechas provienen del campo ``fecha`` de las líneas de costa por fecha
(fecha y hora de adquisición de la imagen Landsat). No se interpola ni se
asume una observación por año: el selector trabaja sobre la lista real.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import geopandas as gpd
import pandas as pd

from .cachear import cachear_datos, firma_archivo
from .catalogo_datos import CAPAS
from .vectores import leer_capa


@dataclass
class Observacion:
    fecha: pd.Timestamp
    satelites: tuple
    lados: tuple
    n_entidades: int
    cobertura_media: float | None
    largo_m: float | None
    epoca: str = ""
    uncy_m: float | None = None

    @property
    def sensor(self) -> str:
        """Texto corto: sensor Landsat (líneas por fecha) o época (líneas anuales)."""
        if self.satelites and self.satelites != ("anual",):
            return "/".join(self.satelites)
        return f"época {self.epoca}" if self.epoca else "—"

    @property
    def etiqueta(self) -> str:
        return f"{self.fecha:%Y-%m-%d} · {self.sensor} · {'+'.join(self.lados)}"

    @property
    def clave(self) -> str:
        return self.fecha.strftime("%Y-%m-%d %H:%M:%S")


def parsear_fechas(serie: pd.Series, formato: str | None) -> pd.Series:
    """Convierte el campo 'fecha' a datetime; ante un formato inesperado, intenta inferirlo sin inventar."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    if formato:
        try:
            return pd.to_datetime(serie, format=formato, errors="raise")
        except (ValueError, TypeError):
            pass
    return pd.to_datetime(serie, errors="coerce")


def cargar_lineas_fecha(cfg: dict, clave: str | None = None) -> gpd.GeoDataFrame:
    """Líneas de costa del control temporal con columnas normalizadas: fecha_dt, anio, lado, satname, cob_pct, largo_m, epoca.

    ``clave`` = capa del catálogo; por defecto ``cfg['temporal']['capa_lineas']`` (lineas_anuales_dsas).
    Las columnas que el archivo no trae se dejan vacías (NaN), nunca se inventan; 'largo_m' se recalcula en el CRS métrico
    cuando falta y se marca en 'largo_fuente'.
    """
    clave = clave or cfg.get("temporal", {}).get("capa_lineas", "lineas_anuales_dsas")
    g = leer_capa(cfg, clave).copy()
    t = cfg.get("temporal", {})
    if "fecha" in g.columns:
        g["fecha_dt"] = parsear_fechas(g["fecha"], t.get("formato_fecha_archivo"))
    elif "DATE_" in g.columns:
        g["fecha_dt"] = parsear_fechas(g["DATE_"], t.get("formato_fecha_dsas", "%m/%d/%Y"))
    elif "fecha_med" in g.columns:
        g["fecha_dt"] = pd.to_datetime(g["fecha_med"], errors="coerce")
    else:
        raise ValueError(f"La capa {clave} no tiene un campo de fecha reconocible (fecha, DATE_ o fecha_med)")
    g = g[g["fecha_dt"].notna()].copy()
    g["anio"] = g["fecha_dt"].dt.year
    if "epoca" not in g.columns:
        g["epoca"] = g["anio"].astype(str)
    if "lado" not in g.columns:
        g["lado"] = "—"
    if "satname" not in g.columns:
        g["satname"] = "anual" if "epoca" in g.columns else "—"
    if "cob_pct" not in g.columns:
        g["cob_pct"] = pd.NA
    if "largo_m" in g.columns:
        g["largo_fuente"] = "importado"
    else:
        from .vectores import a_metrico

        g["largo_m"] = a_metrico(g, cfg).geometry.length.round(1)
        g["largo_fuente"] = "geovisor"
    g["clave_capa"] = clave
    return g


def observaciones(g: gpd.GeoDataFrame) -> list[Observacion]:
    """Lista ordenada de fechas reales con su resumen (una entrada por fecha, agrupando lados)."""
    obs: list[Observacion] = []
    for fecha, grp in g.groupby("fecha_dt", sort=True):
        obs.append(Observacion(
            fecha=pd.Timestamp(fecha),
            satelites=tuple(sorted(grp["satname"].dropna().unique())) if "satname" in grp else (),
            lados=tuple(sorted(grp["lado"].dropna().unique())) if "lado" in grp else (),
            n_entidades=int(len(grp)),
            cobertura_media=float(grp["cob_pct"].mean()) if "cob_pct" in grp and grp["cob_pct"].notna().any() else None,
            largo_m=float(grp["largo_m"].sum()) if "largo_m" in grp and grp["largo_m"].notna().any() else None,
            epoca=str(grp["epoca"].iloc[0]) if "epoca" in grp else "",
            uncy_m=float(grp["UNCY"].mean()) if "UNCY" in grp and grp["UNCY"].notna().any() else None,
        ))
    return obs


def filtrar_rango(obs: list[Observacion], inicio, fin) -> list[Observacion]:
    ini = pd.Timestamp(inicio) if inicio is not None else None
    fi = pd.Timestamp(fin) if fin is not None else None
    out = []
    for o in obs:
        if ini is not None and o.fecha < ini:
            continue
        if fi is not None and o.fecha > fi + pd.Timedelta(days=1) - pd.Timedelta(seconds=1):
            continue
        out.append(o)
    return out


def indice_mas_cercano(obs: list[Observacion], fecha) -> int:
    if not obs:
        return -1
    f = pd.Timestamp(fecha)
    difs = [abs((o.fecha - f).total_seconds()) for o in obs]
    return int(min(range(len(obs)), key=lambda i: difs[i]))


def seleccionar_fecha(g: gpd.GeoDataFrame, fecha) -> gpd.GeoDataFrame:
    f = pd.Timestamp(fecha)
    return g[g["fecha_dt"] == f]


def fechas_por_anio(obs: list[Observacion]) -> dict[int, list[Observacion]]:
    d: dict[int, list[Observacion]] = {}
    for o in obs:
        d.setdefault(o.fecha.year, []).append(o)
    return d


def rango_disponible(obs: list[Observacion], cfg: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Primera y última observación reales, acotadas por config si allí se fijan fechas."""
    if not obs:
        raise ValueError("No hay observaciones")
    ini, fin = obs[0].fecha, obs[-1].fecha
    t = cfg.get("temporal", {})
    if t.get("fecha_inicial"):
        ini = max(ini, pd.Timestamp(t["fecha_inicial"]))
    if t.get("fecha_final"):
        fin = min(fin, pd.Timestamp(t["fecha_final"]))
    return ini, fin


def serie_longitud(obs: list[Observacion]) -> pd.DataFrame:
    """Longitud total (campo 'largo_m' importado del archivo) por fecha."""
    return pd.DataFrame({
        "fecha": [o.fecha for o in obs],
        "largo_m": [o.largo_m for o in obs],
        "satelite": [o.sensor for o in obs],
        "cobertura_pct": [o.cobertura_media for o in obs],
        "n_lados": [len(o.lados) for o in obs],
    })


def cargar_lineas_anuales(cfg: dict, corregidas: bool = True) -> gpd.GeoDataFrame:
    g = leer_capa(cfg, "lineas_anuales" if corregidas else "lineas_anuales_sin_marea").copy()
    if "fecha_med" in g.columns:
        g["fecha_dt"] = pd.to_datetime(g["fecha_med"], errors="coerce")
    g["anio"] = pd.to_numeric(g["anio"], errors="coerce").astype("Int64")
    return g
