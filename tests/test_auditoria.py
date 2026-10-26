"""Pruebas de regresión derivadas de la auditoría del motor de cálculo (25‑10‑2026).

Cada prueba cubre un defecto corregido (D1–D9 del informe docs/AUDITORIA_CALCULADORA.md) con datos sintéticos de
respuesta conocida, sin depender de los archivos de la tesis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.calculo import indice as IN, ponderacion as PO, proyeccion as PR, normalizacion as NO


def _X(n=60, k=4, semilla=1):
    rng = np.random.default_rng(semilla)
    return rng.integers(1, 6, (n, k)).astype(float)


def test_d1_topsis_con_nan_no_altera_el_resto():
    """D1: un NaN en una columna no debe cambiar el TOPSIS de los demás transectos (norma sobre filas válidas)."""
    X = _X(); w = PO.pesos_ewm(X)
    c0, _ = IN.topsis(X, w)
    X2 = X.copy(); X2[0, 1] = np.nan
    c1, _ = IN.topsis(X2, w)
    assert np.isnan(c1[0])
    assert np.nanmax(np.abs(c1[1:] - c0[1:])) < 0.02   # solo cambia por quitar una fila de la norma


def test_d2_tasa_L_incluye_el_tramo_observado():
    """D2: para un horizonte a menos de L años, la tasa media de los L años previos integra la tasa observada."""
    n = 30
    km = np.linspace(0, 2.9, n)
    r0 = np.full(n, -4.0)
    H = pd.DataFrame({c: np.zeros(n) for c in PR.RASGOS}); H["tasa"] = r0
    aj = {"tipo": "persistencia", "residuos_oof": np.zeros(n), "mediana_rasgos": np.zeros(len(PR.RASGOS)), "metricas": {}}
    cfg = PR.ConfigProyeccion(ventana_anios=21, horizontes=(2030, 2050), n_mc=5, sigma_regional=0.0)
    out = PR.proyectar(r0, H, aj, km, 2026.0, cfg)["tabla"]
    # persistencia: la tasa no cambia ⇒ la media de los 21 años previos a 2030 debe ser −4,0 (no −4·3,66/21)
    assert np.allclose(out["tasaL_2030"], -4.0, atol=1e-9)
    assert np.allclose(out["tasaL_2050"], -4.0, atol=1e-9)
    assert np.allclose(out["desplaz_m_2030"], -4.0 * 4.0, atol=1e-9)


def test_d3_sensibilidad_y_estabilidad_usan_los_cortes_del_proyecto():
    X = _X(200, 5, 3); w = PO.pesos_ewm(X)
    s1 = IN.sensibilidad_pesos(X, w, list("abcde"), cortes=(0.2, 0.4, 0.6, 0.8))
    s2 = IN.sensibilidad_pesos(X, w, list("abcde"), cortes=(0.1, 0.3, 0.5, 0.7))
    assert not np.allclose(s1["pct_cambia_clase"], s2["pct_cambia_clase"])
    assert (s1["perturbacion"] == "excluida (EWM sin la variable)").sum() == 5
    blo = IN.bloques_contiguos(np.arange(200, dtype=float), 4)
    e1 = IN.estabilidad_clase_bootstrap(X, blo, 50, cortes=(0.2, 0.4, 0.6, 0.8))
    e2 = IN.estabilidad_clase_bootstrap(X, blo, 50, cortes=(0.1, 0.3, 0.5, 0.7))
    assert not np.allclose(e1, e2)


def test_d4_estabilidad_nan_para_transecto_sin_dato():
    X = _X(80, 3, 5); X[3, 0] = np.nan
    blo = IN.bloques_contiguos(np.arange(80, dtype=float), 4)
    e = IN.estabilidad_clase_bootstrap(X, blo, 20)
    assert np.isnan(e[3]) and np.isfinite(e[[0, 1, 2, 4]]).all()


def test_d5_incertidumbre_cero_usa_el_valor_por_defecto():
    import geopandas as gpd
    from shapely.geometry import LineString
    from src.calculo import transectos as TR

    # línea base y transectos sintéticos: costa paralela al eje x que retrocede 2 m/año
    fechas = pd.to_datetime(["2000-01-01", "2005-01-01", "2010-01-01", "2015-01-01", "2020-01-01"])
    lineas = gpd.GeoDataFrame({"fecha": fechas, "unc": [0.0, 10.0, 10.0, 10.0, 10.0]},
                              geometry=[LineString([(0, 100 - 2 * i * 5), (1000, 100 - 2 * i * 5)]) for i in range(5)], crs="EPSG:32618")
    base = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1000, 0)])], crs="EPSG:32618")
    tr = TR.generar_transectos(base, lineas.iloc[[4]], TR.ParamTransectos(100, 500, 100))
    inter = TR.intersecciones(tr, lineas, "fecha", "unc", unc_defecto=10.0)
    assert len(inter) >= 5
    assert (inter["unc_m"] > 0).all() and np.isclose(inter["unc_m"].min(), 10.0)


def test_d6_vector_categorico_solapes_y_mayusculas():
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon
    from src.calculo import transectos as TR, muestreo as MU

    base = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (300, 0)])], crs="EPSG:32618")
    ref = gpd.GeoDataFrame({"fecha": [pd.Timestamp("2020-01-01")]}, geometry=[LineString([(0, 50), (300, 50)])], crs="EPSG:32618")
    tr = TR.generar_transectos(base, ref, TR.ParamTransectos(100, 400, 100))
    tr = TR.p0_de_referencia(tr, TR.intersecciones(tr, ref, "fecha"), None)
    caja = Polygon([(-50, -50), (350, -50), (350, 400), (-50, 400)])
    capa = gpd.GeoDataFrame({"cat": ["A", "a", "B"]}, geometry=[caja, caja, caja], crs="EPSG:32618")  # A duplicada (misma categoría) + B solapada
    tab, dom = MU.vector_categorico(tr, capa, "cat", 0, 100, 100, excluir=("b",))
    assert np.allclose(tab["A"], 100, atol=1) and np.allclose(tab["B"], 100, atol=1)   # disuelta: A no cuenta 200 %
    assert (tab["solape_pct"] > 90).all()                                             # solape entre A y B queda expuesto
    assert (dom == "A").all()                                                           # 'b' excluida sin distinguir mayúsculas


def test_d7_tabla_por_id_duplicados(tmp_path):
    import geopandas as gpd
    from src.calculo import muestreo as MU

    csv = tmp_path / "t.csv"; pd.DataFrame({"id": [1, 1, 2], "v": [3, 4, 5]}).to_csv(csv, index=False)
    t = gpd.GeoDataFrame({"id_ivc": [1, 2]}, geometry=gpd.points_from_xy([0, 1], [0, 1]), crs="EPSG:32618")
    with pytest.raises(ValueError, match="repetidos"):
        MU.tabla_por_id(t, str(csv), "id", "v")


def test_d8_ewm_columnas_constantes():
    X = np.c_[np.arange(1, 11, dtype=float), np.zeros(10), np.ones(10)]
    w = PO.pesos_ewm(X)
    assert np.isclose(w[0], 1.0) and np.isclose(w[1], 0.0) and np.isclose(w[2], 0.0)
    with pytest.raises(ValueError):
        PO.pesos_ewm(np.ones((10, 2)))


def test_d9_matriz_saaty_rango_y_signo():
    with pytest.raises(ValueError):
        PO.matriz_saaty_valida(np.array([[1, -2], [-0.5, 1]]))
    with pytest.raises(ValueError):
        PO.matriz_saaty_valida(np.array([[1, 12], [1 / 12, 1]]))
    with pytest.raises(ValueError, match="vacías"):
        PO.matriz_saaty_valida(np.array([[1, np.nan], [np.nan, 1]]))
    PO.matriz_saaty_valida(np.array([[1, 9], [1 / 9, 1]]))


def test_clase_de_indice_bordes():
    assert list(NO.clase_de_indice_01([0.0, 0.2, 0.39, 0.4, 0.8, 1.0])) == [1, 2, 2, 3, 5, 5]
