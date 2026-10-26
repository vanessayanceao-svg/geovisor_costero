"""Pruebas de lectura de CRS, transformación, geometrías vacías y exportación."""
from __future__ import annotations

import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from src import exportaciones, vectores
from src.vectores import CapaNoDisponible
from tests.conftest import requiere


def test_lectura_crs_lineas(cfg):
    requiere(cfg, "lineas_fecha")
    g = vectores.leer_capa(cfg, "lineas_fecha")
    assert g.crs is not None and g.crs.to_epsg() == 32618
    assert len(g) > 0
    assert set(["fecha", "satname", "lado"]).issubset(g.columns)


def test_transformacion_a_visual(cfg):
    requiere(cfg, "sectores_roi")
    g = vectores.leer_capa(cfg, "sectores_roi")
    gv = vectores.a_visual(g, cfg)
    assert gv.crs.to_epsg() == 4326
    b = gv.total_bounds
    # Barra de Salamanca: lon ≈ −74,9 … −74,2 ; lat ≈ 10,9 … 11,2
    assert -75.0 < b[0] < -74.0 and 10.8 < b[1] < 11.3
    # las operaciones métricas conservan el CRS métrico
    assert vectores.a_metrico(gv, cfg).crs.to_epsg() == 32618


def test_capas_fuente_otros_crs_se_reproyectan(cfg):
    requiere(cfg, "geomorfologia")
    g = vectores.leer_capa(cfg, "geomorfologia")
    assert g.crs is not None
    gv = vectores.a_visual(g, cfg)
    b = gv.total_bounds
    assert -76 < b[0] < -73 and 10 < b[1] < 12


def test_geometrias_vacias_y_nulas(cfg):
    g = gpd.GeoDataFrame({"a": [1, 2, 3, 4]}, geometry=[LineString([(0, 0), (1, 1)]), None, LineString(), Polygon()], crs="EPSG:32618")
    limpio = vectores.limpiar(g)
    assert len(limpio) == 1
    vacio = gpd.GeoDataFrame({"a": []}, geometry=[], crs="EPSG:32618")
    assert vectores.bounds_visual(vacio, cfg) is None
    assert vectores.simplificar_para_mapa(vacio, cfg, 5).empty
    import math

    assert math.isnan(vectores.longitud_m(vacio, cfg))


def test_sin_crs_no_se_reproyecta(cfg):
    g = gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs=None)
    with pytest.raises(ValueError):
        vectores.a_visual(g, cfg)
    with pytest.raises(ValueError):
        exportaciones.exportar_geojson(g, "x", cfg, guardar=False)


def test_simplificacion_solo_visual(cfg):
    g = gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(0, 0), (1, 0.4), (2, 0), (3, 0.4), (4, 0)])], crs="EPSG:32618")
    gs = vectores.simplificar_para_mapa(g, cfg, 1.0)
    assert gs.crs.to_epsg() == 4326
    assert len(gs.geometry.iloc[0].coords) < len(g.geometry.iloc[0].coords)
    assert len(g.geometry.iloc[0].coords) == 5  # el original no se toca


def test_capa_no_disponible(cfg):
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["rutas"]["exportar_coastsat"] = "Z:/no/existe"
    with pytest.raises(CapaNoDisponible):
        vectores.leer_capa(cfg2, "lineas_fecha")


def test_exportaciones_conservan_atributos_y_crs(cfg, tmp_path):
    g = gpd.GeoDataFrame({"id": [1, 2], "nombre": ["a", "b"]}, geometry=[LineString([(516000, 1213000), (517000, 1214000)]), LineString([(518000, 1215000), (519000, 1216000)])], crs="EPSG:32618")
    datos, archivo, crs = exportaciones.exportar_geojson(g, "prueba", cfg, guardar=False)
    assert crs == "EPSG:4326" and archivo.endswith(".geojson")
    gj = json.loads(datos)
    assert len(gj["features"]) == 2 and gj["features"][0]["properties"]["nombre"] == "a"
    lon, lat = gj["features"][0]["geometry"]["coordinates"][0]
    assert -75 < lon < -74 and 10 < lat < 12
    datos, archivo, crs = exportaciones.exportar_gpkg(g, "prueba", cfg, guardar=False)
    assert crs == "EPSG:32618" and len(datos) > 0
    datos, archivo, crs = exportaciones.exportar_csv(g, "prueba", cfg, con_wkt=True, guardar=False)
    assert b"wkt" in datos and crs == "EPSG:32618"


def test_exportacion_lineas_reales(cfg):
    requiere(cfg, "lineas_fecha")
    from src import temporal

    g = temporal.cargar_lineas_fecha(cfg, clave="lineas_fecha")
    obs = temporal.observaciones(g)
    sel = temporal.seleccionar_fecha(g, obs[-1].fecha).drop(columns=["fecha_dt"])
    datos, archivo, crs = exportaciones.exportar_geojson(sel, "ultima", cfg, guardar=False)
    gj = json.loads(datos)
    assert len(gj["features"]) == len(sel)
    assert gj["features"][0]["properties"]["satname"] == sel["satname"].iloc[0]
