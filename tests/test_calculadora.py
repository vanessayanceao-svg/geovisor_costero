"""Pruebas del motor de cálculo (src/calculo): reproduce DSAS, las clases, los pesos EWM, el IVC y la validación de la tesis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.calculo import proyecto as PJ, ejemplos, indice as IN, ponderacion as PO, transectos as TR, tasas as TA
from tests.conftest import requiere


@pytest.fixture(scope="module")
def ejemplo(cfg):
    requiere(cfg, "lineas_anuales_dsas")
    requiere(cfg, "dsas_transectos")
    requiere(cfg, "ivc_clases_variables")
    p = ejemplos.ejemplo_salamanca(cfg)
    L = PJ.cargar_lineas(p)
    r1 = PJ.paso_transectos(p, L)
    r3 = PJ.paso_variables(p, r1["transectos"], r1["inter"])
    return p, L, r1, r3


def test_tasas_reproducen_dsas(cfg, ejemplo):
    """Con los transectos y líneas de la tesis, LRR/WLR/EPR/NSM/SCE coinciden con dsas_tasas.shp (error < 0,001)."""
    requiere(cfg, "dsas_tasas")
    import geopandas as gpd
    from src.catalogo_datos import CAPAS

    p, L, r1, _ = ejemplo
    t = r1["transectos"]
    ref = gpd.read_file(CAPAS["dsas_tasas"].ruta(cfg))
    c = t.merge(ref[["BaselineID", "TransOrder", "LRR", "WLR", "EPR", "NSM", "SCE", "LCI95"]], on=["BaselineID", "TransOrder"], suffixes=("", "_dsas"))
    assert len(c) == 671 and len(r1["inter"]) == 25068
    for k in ("LRR", "WLR", "EPR", "LCI95"):
        assert (c[k] - c[f"{k}_dsas"]).abs().max() < 1e-3, k
    for k in ("NSM", "SCE"):
        assert (c[k] - c[f"{k}_dsas"]).abs().max() < 0.01, k


def test_transectos_generados_coinciden_con_dsas(cfg, ejemplo):
    """Generar transectos desde la línea base DSAS (100 m, suavizado 500 m) reproduce la geometría DSAS (azimut mediano < 0,1°)."""
    import geopandas as gpd
    from shapely.strtree import STRtree
    from src.catalogo_datos import CAPAS

    p, L, r1, _ = ejemplo
    ref = r1["transectos"]
    lref = L[L["_fecha"] == r1["fecha_ref"]]
    g = TR.generar_transectos(r1["base"], lref, TR.ParamTransectos(100, 1000, 500))
    assert abs(len(g) - len(ref)) <= 2
    arb = STRtree(list(ref.geometry))
    idx = [int(arb.nearest(x)) for x in g.geometry]
    dif = np.abs(((g["Azimuth"].values - ref["Azimuth"].values[idx]) + 180) % 360 - 180)
    assert np.median(dif) < 0.1 and np.percentile(dif, 95) < 1.0


def test_variables_reproducen_clases_de_la_tesis(cfg, ejemplo):
    p, L, r1, r3 = ejemplo
    assert not r3["errores"], r3["errores"]
    from src.catalogo_datos import CAPAS

    K = pd.read_csv(CAPAS["ivc_clases_variables"].ruta(cfg))
    for v in p["variables"]:
        c = v["codigo"]
        a = pd.to_numeric(r3["clases"][c], errors="coerce").to_numpy(float); b = K[c].to_numpy(float)
        ok = np.isfinite(a) & np.isfinite(b)
        assert ok.sum() == np.isfinite(b).sum(), c
        assert np.allclose(a[ok], b[ok], atol=1e-6), c


def test_pesos_e_indice_reproducen_la_tesis(cfg, ejemplo):
    requiere(cfg, "ivc_pesos")
    requiere(cfg, "ivc_transectos")
    from src import ivc as mod
    from src.catalogo_datos import CAPAS

    p, L, r1, r3 = ejemplo
    blo = IN.bloques_contiguos(r3["clases"]["dist_costa_km"].to_numpy(float), 8)
    r4 = PJ.paso_pesos(p, r3["clases"], blo)
    pes = pd.read_csv(CAPAS["ivc_pesos"].ruta(cfg)).set_index("variable")
    assert np.abs(r4["ewm"]["peso"].to_numpy() - pes.loc[r4["variables"], "peso_total"].to_numpy()).max() < 1e-9
    r5 = PJ.paso_indice(p, r3["clases"], r4, r1["transectos"], r3["valores"])
    t = mod.cargar_transectos_ivc(cfg).set_index("id_ivc")
    R = r5["tabla"]
    assert np.nanmax(np.abs(R["ivc_ewm"].to_numpy() - t.loc[R["id_ivc"], "ivc_ewm_total"].to_numpy(float))) < 1e-9
    assert np.nanmax(np.abs(R["ivc_topsis_ewm"].to_numpy() - t.loc[R["id_ivc"], "ivc_topsis_ewm"].to_numpy(float))) < 1e-9
    val = r5["validacion"].set_index("indice")
    assert abs(val.loc["ivc_ewm", "rho"] - 0.619) < 0.005 and abs(val.loc["ivc_ewm_estructural", "rho"] - 0.536) < 0.005


def test_proyeccion_reproduce_persistencia_amortiguada(cfg, ejemplo):
    requiere(cfg, "proy_amortiguada_transectos")
    from src.catalogo_datos import CAPAS

    p, L, r1, r3 = ejemplo
    blo = IN.bloques_contiguos(r3["clases"]["dist_costa_km"].to_numpy(float), 8)
    r4 = PJ.paso_pesos(p, r3["clases"], blo)
    p["proyeccion"]["n_mc"] = 200
    r6 = PJ.paso_proyeccion(p, r1["transectos"], r1["inter"], r3["clases"], r3["valores"], r4)
    m = r6["ajuste"]["metricas"]
    assert 0.08 < m["R2_OS"] < 0.12 and m["bloques_mejora"] >= 6
    ref = pd.read_csv(CAPAS["proy_amortiguada_transectos"].ruta(cfg)).set_index("id_ivc")
    d = r6["tabla"].set_index("id_ivc")
    c = np.corrcoef(np.nan_to_num(d["desplaz_m_2100"].to_numpy()), np.nan_to_num(ref.loc[d.index, "desplaz_m_2100"].to_numpy()))[0, 1]
    assert c > 0.999
    res = r6["resumen"].set_index("clave")
    assert abs(res.loc["ssp245_2050", "pct_alta_muy_alta"] - 12.97) < 0.5


def test_fahp_buckley_consistencia():
    A = np.array([[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]])
    tab, cons = PO.pesos_fahp(A, "buckley")
    assert cons["consistente"] and abs(tab["peso"].sum() - 1) < 1e-9
    assert tab["peso"].iloc[0] > tab["peso"].iloc[1] > tab["peso"].iloc[2]
    with pytest.raises(ValueError):
        PO.pesos_fahp(np.array([[1, 2], [3, 1]]))


def test_capas_proyecto_e_informe(cfg, ejemplo, tmp_path):
    """Las capas exportadas de un proyecto se leen para el mapa y el informe PDF se genera."""
    from src.calculo import capas_proyecto as CP
    from src import informe_pdf

    p, L, r1, r3 = ejemplo
    blo = IN.bloques_contiguos(r3["clases"]["dist_costa_km"].to_numpy(float), 8)
    r4 = PJ.paso_pesos(p, r3["clases"], blo)
    r5 = PJ.paso_indice(p, r3["clases"], r4, r1["transectos"], r3["valores"])
    carpeta = tmp_path / "proy"
    PJ.exportar_todo(p, carpeta, {"transectos": r1, "variables": r3, "pesos": r4, "indice": r5})
    assert {"calc_tasas", "calc_ivc", "calc_base"} <= set(CP.capas_de(carpeta))
    m, grupos, stats = CP.mapa_integrado(cfg, carpeta, capas={"calc_tasas": True, "calc_ivc": True})
    assert stats["n_transectos"] == 671 and abs(stats["ivc_medio"] - 0.394) < 0.002 and len(grupos) == 2
    html = CP.html_autonomo(cfg, carpeta, capas={"calc_ivc": True})
    assert "leaflet" in html.lower() and "gv-leyenda" in html
    pdf = informe_pdf.generar_informe(cfg, carpeta, tmp_path / "informe.pdf", "prueba")
    assert pdf.exists() and pdf.stat().st_size > 50_000
