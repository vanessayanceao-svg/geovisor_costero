"""Pruebas del control temporal: fechas reales, selección, navegación y rangos."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src import temporal
from tests.conftest import requiere


def _sintetico():
    fechas = ["1984/09/02 14:46:59", "1984/09/02 14:46:59", "1990/01/15 14:50:00", "2026/09/06 15:16:45"]
    return gpd.GeoDataFrame({
        "fecha": fechas, "satname": ["L5", "L5", "L5", "L8"], "lado": ["este", "oeste", "oeste", "este"],
        "cob_pct": [100.0, 93.8, 80.0, 99.0], "largo_m": [4049.5, 58519.5, 60000.0, 4100.0],
    }, geometry=[LineString([(0, 0), (1, 1)])] * 4, crs="EPSG:32618")


def test_parseo_formato_declarado():
    s = temporal.parsear_fechas(pd.Series(["1984/09/02 14:46:59"]), "%Y/%m/%d %H:%M:%S")
    assert s.iloc[0] == pd.Timestamp("1984-09-02 14:46:59")


def test_parseo_formato_inesperado_no_inventa():
    s = temporal.parsear_fechas(pd.Series(["no es fecha"]), "%Y/%m/%d %H:%M:%S")
    assert s.isna().all()


def test_observaciones_agrupan_lados():
    g = _sintetico()
    g["fecha_dt"] = temporal.parsear_fechas(g["fecha"], "%Y/%m/%d %H:%M:%S")
    obs = temporal.observaciones(g)
    assert len(obs) == 3  # 4 entidades, 3 fechas reales
    assert obs[0].n_entidades == 2 and obs[0].lados == ("este", "oeste")
    assert obs[0].largo_m == 4049.5 + 58519.5
    assert obs[-1].fecha.year == 2026


def test_filtrar_rango_y_mas_cercano():
    g = _sintetico()
    g["fecha_dt"] = temporal.parsear_fechas(g["fecha"], "%Y/%m/%d %H:%M:%S")
    obs = temporal.observaciones(g)
    r = temporal.filtrar_rango(obs, "1985-01-01", "2000-01-01")
    assert [o.fecha.year for o in r] == [1990]
    assert temporal.indice_mas_cercano(obs, "1991-06-01") == 1
    assert temporal.fechas_por_anio(obs)[1984][0].fecha.year == 1984
    assert len(temporal.seleccionar_fecha(g, obs[0].fecha)) == 2


def test_lineas_anuales_dsas_fuente_principal(cfg):
    """La capa principal del control temporal es lineas_anuales_dsas.shp: 38 épocas × 2 lados, fechas de DATE_."""
    requiere(cfg, "lineas_anuales_dsas")
    g = temporal.cargar_lineas_fecha(cfg)
    assert g["clave_capa"].iloc[0] == "lineas_anuales_dsas"
    assert len(g) == 76 and g["epoca"].nunique() == 38
    obs = temporal.observaciones(g)
    assert len(obs) == 38 and obs[0].fecha == pd.Timestamp("1984-11-28") and obs[-1].fecha == pd.Timestamp("2026-05-04")
    assert all(o.lados == ("este", "oeste") for o in obs)
    assert obs[0].epoca == "1984-1985" and obs[0].sensor == "época 1984-1985"
    assert (g["largo_fuente"] == "geovisor").all() and g["largo_m"].gt(0).all()
    assert g["cob_pct"].isna().all()  # el archivo no trae cobertura: no se inventa


def test_no_se_asume_una_observacion_por_anio(cfg):
    requiere(cfg, "lineas_fecha")
    g = temporal.cargar_lineas_fecha(cfg, clave="lineas_fecha")
    obs = temporal.observaciones(g)
    por_anio = temporal.fechas_por_anio(obs)
    anios = sorted(por_anio)
    # hay años sin observación (p. ej. 1988, 1992) y años con varias
    assert set(range(anios[0], anios[-1] + 1)) - set(anios), "Se esperaban años sin observación"
    assert max(len(v) for v in por_anio.values()) > 1
    ini, fin = temporal.rango_disponible(obs, cfg)
    assert ini == obs[0].fecha and fin == obs[-1].fecha


def test_fechas_lineas_anuales_coinciden_con_dsas(cfg):
    """Las 38 fechas del informe DSAS deben ser exactamente las de las líneas anuales (no se convierten fechas)."""
    requiere(cfg, "lineas_anuales")
    requiere(cfg, "dsas_informe")
    from src import dsas

    an = temporal.cargar_lineas_anuales(cfg)
    inf = dsas.leer_informe_dsas(cfg)
    fechas_dsas = {pd.Timestamp(f.strip()) for f in inf["fechas"].split(",")}
    fechas_anuales = set(pd.to_datetime(an["DATE_"]).dt.normalize())
    assert fechas_dsas == fechas_anuales
