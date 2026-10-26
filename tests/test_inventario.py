"""Pruebas del inventario y del catálogo de capas."""
from __future__ import annotations

import json

import pandas as pd

from src import inventario
from src.catalogo_datos import CAPAS, estado_capas, estado_modulos
from src.configuracion import ruta


def test_fechas_en_nombre():
    fechas, anios = inventario.fechas_en_nombre("2023-01-01-15-17-21_L8_009052_bs_2023_2026_s01_ms.tif")
    assert fechas == ["2023-01-01T15:17:21"]
    assert anios == [2023, 2026]
    fechas, anios = inventario.fechas_en_nombre("ivc_ssp245_2050_valor.tif")
    assert fechas == [] and anios == [2050]
    assert inventario.fechas_en_nombre("archivo_sin_fecha.csv") == ([], [])


def test_inventario_y_catalogo(cfg, tmp_path):
    raices = {k: ruta(cfg, k) for k in ("exportar_coastsat", "resultados_tesis")}
    if not any(p.exists() for p in raices.values()):
        import pytest

        pytest.skip("Sin raíces de datos")
    ent = inventario.inventariar(raices)
    assert ent, "El inventario no encontró archivos"
    rj, rc = inventario.guardar_catalogo(ent, tmp_path)
    assert rj.exists() and rc.exists()
    d = json.loads(rj.read_text(encoding="utf-8"))
    assert d["n"] == len(ent)
    df = inventario.cargar_catalogo(tmp_path)
    assert isinstance(df, pd.DataFrame) and len(df) == len(ent)
    # Todo vector inspeccionado declara CRS (ninguna capa se dibuja sin CRS)
    vec = df[(df["categoria"] == "vector") & (df["inspeccionado"] == True)]  # noqa: E712
    sin_crs = vec[vec["epsg"].isna()]
    # un archivo sin CRS legible debe quedar marcado con error explícito, nunca asumirse
    assert sin_crs["error"].notna().all(), sin_crs["ruta"].tolist()
    res = inventario.resumen_catalogo(df)
    assert res["n_total"] == len(ent)


def test_inventario_raiz_inexistente(tmp_path):
    ent = inventario.inventariar({"x": tmp_path / "no_existe"})
    assert ent == []


def test_estado_capas_y_modulos(cfg):
    e = estado_capas(cfg)
    assert set(e) == set(CAPAS)
    m = estado_modulos(cfg)
    assert set(m) == {"Histórico", "DSAS", "IVC", "Predicciones", "Evaluación"}
    for v in m.values():
        assert isinstance(v["ok"], bool)


def test_modulos_sin_datos(cfg):
    """Con rutas inexistentes, ningún módulo se declara disponible y no se produce error."""
    cfg2 = json.loads(json.dumps(cfg))
    for k in ("coastsat_raiz", "coastsat_data", "exportar_coastsat", "resultados_tesis"):
        cfg2["rutas"][k] = "Z:/no/existe"
    m = estado_modulos(cfg2)
    assert not any(v["ok"] for v in m.values())
