"""Pruebas de los módulos de análisis: DSAS, IVC, predicciones, métricas y ausencia de datos ficticios."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src import dsas, ivc, metricas_modelos, predicciones, rasteres
from src.catalogo_datos import CAPAS
from tests.conftest import requiere


def test_dsas_valores_importados_coinciden_con_informe(cfg):
    requiere(cfg, "dsas_tasas")
    requiere(cfg, "dsas_informe")
    g = dsas.cargar_tasas_dsas(cfg)
    inf = dsas.leer_informe_dsas(cfg)
    assert len(g) == 671
    r = dsas.resumen_tasas(g, "LRR")
    assert abs(r["media"] - inf["media_LRR"]) < 0.01
    r = dsas.resumen_tasas(g, "NSM")
    assert abs(r["media"] - inf["media_NSM"]) < 0.01
    assert inf["version"].startswith("v6.1")
    assert "procedencia" in g.columns and (g["procedencia"] == "DSAS v6.1").all()


def test_dsas_sin_datos(cfg):
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["rutas"]["exportar_coastsat"] = "Z:/no/existe"
    assert dsas.leer_informe_dsas(cfg2) is None
    assert dsas.comparacion_script_dsas(cfg2) is None


def test_ivc_clasificacion_documentada_reproduce_clases(cfg):
    requiere(cfg, "ivc_transectos")
    t = ivc.cargar_transectos_ivc(cfg)
    for v in ("ewm_total", "ewm_2005", "ssp585_2100"):
        c_ivc, c_cl = ivc.columnas_version(t, v)
        assert c_ivc and c_cl, v
        rep = ivc.clasificar(t[c_ivc], cfg).astype(float)
        ok = t[c_ivc].notna()
        assert (rep[ok] == t.loc[ok, c_cl].astype(float)).all(), f"La clasificación de config no reproduce la del archivo en {v}"
        assert rep[~ok].isna().all()  # sin dato -> sin clase (no se rellena)


def test_ivc_estadisticas_y_rasters(cfg):
    requiere(cfg, "ivc_transectos")
    t = ivc.cargar_transectos_ivc(cfg)
    est = ivc.estadisticas(t, "ivc_ewm_total", "clase_ewm_total", cfg)
    assert est["n"] == 671 and 0 <= est["media"] <= 1
    assert sum(est["clases"].values()) == 671
    calor, valor = ivc.rasters_version(cfg, "ewm_total")
    if calor is None:
        pytest.skip("Sin rásteres del IVC")
    s = rasteres.superponer_rgba(cfg, calor)
    assert s.ancho > 0 and s.bounds[0][0] < s.bounds[1][0]
    s2, e = rasteres.superponer_valor(cfg, valor, cortes=cfg["ivc"]["cortes_1_5"], colores=[cfg["ivc"]["clases"][k]["color"] for k in range(1, 6)])
    assert 1 <= e["min"] <= e["max"] <= 5
    assert ivc.rasters_version(cfg, "version_inexistente") == (None, None)


def test_ivc_sin_datos_no_inventa(cfg):
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["rutas"]["resultados_tesis"] = "Z:/no/existe"
    cfg2["rutas"]["exportar_coastsat"] = "Z:/no/existe"
    assert not CAPAS["ivc_transectos"].disponible(cfg2)
    assert ivc.versiones(cfg2).empty
    assert ivc.cargar_pesos(cfg2) is None
    assert ivc.transectos_con_variables(cfg2) is None
    assert "GeoPackage" in ivc.requisitos_para_activar()


def test_predicciones_solo_anios_procesados(cfg):
    requiere(cfg, "proy_amortiguada")
    g = predicciones.cargar_lineas(cfg, "proy_amortiguada")
    anios = predicciones.anios_procesados(g)
    assert anios == [2050, 2100]
    estados = predicciones.estado_horizontes(cfg, anios)
    assert {e["anio"]: e["estado"] for e in estados}[2075] == "no procesado"
    assert {e["anio"]: e["estado"] for e in estados}[2100] == "procesado"
    assert set(g["tipo"]) <= set(predicciones.TIPOS_LINEA)
    meta = predicciones.metadatos(cfg, "proy_amortiguada")
    assert meta and "modelo" in meta and meta["n_mc"] == 2000


def test_predicciones_sin_datos(cfg):
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["rutas"]["resultados_tesis"] = "Z:/no/existe"
    assert predicciones.variantes_disponibles(cfg2) == {}
    assert predicciones.metadatos(cfg2, "proy_amortiguada") is None
    assert predicciones.estado_horizontes(cfg2, []) == [{"anio": a, "estado": "no procesado"} for a in cfg["predicciones"]["horizontes_previstos"]]


def test_metricas_modelos(cfg):
    requiere(cfg, "metricas_anidadas")
    m = metricas_modelos.cargar_metricas_anidadas(cfg)
    assert "modelo" in m.columns and "habilidad_vs_persistencia" in m.columns
    pers = m[m["modelo"] == "persistencia"].iloc[0]
    assert pers["habilidad_vs_persistencia"] == 0
    meta = metricas_modelos.metadatos_evaluacion(metricas_modelos.cargar_config_anidada(cfg))
    assert "Conjunto de prueba" in meta


def test_importar_tabla_metricas_exige_columna_modelo():
    with pytest.raises(ValueError):
        metricas_modelos.importar_tabla_metricas(b"a,b\n1,2\n", "x.csv")
    df = metricas_modelos.importar_tabla_metricas(b"modelo,MAE\nrf,1.2\n", "x.csv")
    assert list(df["modelo"]) == ["rf"]


def test_ausencia_de_datos_ficticios():
    """Ningún módulo genera valores sintéticos: las funciones de carga devuelven None/[] sin archivos."""
    import inspect

    from src import dsas as m1, ivc as m2, predicciones as m3, metricas_modelos as m4

    fuente = "".join(inspect.getsource(m) for m in (m1, m2, m3, m4))
    for prohibido in ("np.random", "random.", "demo", "dummy", "ejemplo_ficticio", "interp("):
        assert prohibido not in fuente, f"Encontrado '{prohibido}' en los módulos de análisis"


def test_landsat_escena(cfg):
    import glob

    from src.configuracion import ruta

    escenas = glob.glob(str(ruta(cfg, "coastsat_data") / "**" / "*_ms.tif"), recursive=True)
    if not escenas:
        pytest.skip("Sin escenas Landsat")
    s = rasteres.superponer_escena_landsat(cfg, escenas[0])
    assert s.crs_origen.endswith("32618") and s.bounds[0][1] < -74 and s.bounds[0][0] > 10


def test_priorizacion_ruta90_v4(cfg):
    """La priorización de la Ruta 90 se lee del CSV v4 de la tesis (44 tramos: 5 alta, 13 media) y el trazado reproduce la Figura 37."""
    requiere(cfg, "ruta90_priorizacion")
    from src import ruta90

    d = ruta90.cargar_priorizacion(cfg)
    r = ruta90.resumen(d)
    assert r["n_tramos"] == 44 and r["n_alta"] == 5 and r["n_media"] == 13 and r["n_baja"] == 26
    assert r["primer_tramo"] == "km 28–29" and abs(r["primer_anio"] - 2027.75) < 1e-6
    seg = ruta90.segmentos_ruta(cfg, d)
    assert seg.crs.to_epsg() == 32618 and set(seg["prioridad"]) <= set(ruta90.COLORES)
    # los tramos de prioridad alta (km 26-30 y 36-37) deben aparecer sobre la vía
    assert (seg["prioridad"].str.startswith("Alta")).sum() > 0
    assert set(seg.loc[seg["prioridad"].str.startswith("Alta"), "km_costa"].dropna().astype(int)) <= {26, 27, 28, 29, 36}


def test_ivc_2005_reconstruido(cfg):
    """La versión ewm_2005 del GeoPackage es la reconstruida (22‑10‑2026): 650 transectos, IVC medio 0,372, 37 en clase alta,
    81 % de coincidencia de clase con 2026; y las clases por variable de 2005 se leen del CSV sin recalcular nada."""
    requiere(cfg, "ivc_transectos")
    requiere(cfg, "ivc_clases_2005")
    from src import ivc

    t = ivc.cargar_transectos_ivc(cfg)
    ci, cc = ivc.columnas_version(t, "ewm_2005")
    x = pd.to_numeric(t[ci], errors="coerce")
    k = pd.to_numeric(t[cc], errors="coerce")
    assert x.notna().sum() == 650 and abs(x.mean() - 0.372) < 0.002 and int((k >= 4).sum()) == 37
    ci26, cc26 = ivc.columnas_version(t, "ewm_2026")
    k26 = pd.to_numeric(t[cc26], errors="coerce")
    ok = k.notna() & k26.notna()
    assert 80 < (k[ok] == k26[ok]).mean() * 100 < 82.5
    cam = ivc.cambio_clases_2005_2026(cfg)
    assert cam is not None and set(cam["variable"]) == set(ivc.DIMENSIONES_VARIABLES)
    fijas = cam[~cam["recalculada_desde_2005"]]
    assert (fijas["pct_cambia"] == 0).all(), "las variables sin dato de 2005 deben conservar la clase actual"
    assert cam.set_index("variable").loc["c_cambio_costa", "pct_cambia"] > 0
