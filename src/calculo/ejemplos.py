"""Proyecto de ejemplo: Barra de Salamanca con los insumos de la tesis (rutas de config.yaml).

Las variables con fuente exportada se calculan desde la capa (tasa DSAS, geomorfología, distancia a la Ruta 90,
densidad DANE); las demás se importan por transecto desde ``exportar_coastsat/ivc/tabla_variables_ivc_transectos.csv``
(DeltaDTM, oleaje, granulometría, suelos IGAC, cobertura 2025, usos INVEMAR, huella construida), porque sus fuentes
originales no están en la carpeta de exportación. Los umbrales y puntajes son los de ivc_clasificacion.py.
"""
from __future__ import annotations

from pathlib import Path

from ..configuracion import ruta
from .proyecto import nuevo_proyecto, variable_nueva


def ejemplo_salamanca(cfg: dict) -> dict:
    exp = Path(ruta(cfg, "exportar_coastsat"))
    res = Path(ruta(cfg, "resultados_tesis"))
    dsas, ivc = exp / "dsas", exp / "ivc"
    tabla = str(ivc / "tabla_variables_ivc_transectos.csv")
    tabla_clases = str(ivc / "tabla_clases_1_5_ivc.csv")
    p = nuevo_proyecto("barra_salamanca_ejemplo", 32618)
    p["lineas"].update({"ruta": str(dsas / "lineas_anuales_dsas.shp"), "campo_fecha": "DATE_", "formato_fecha": "%m/%d/%Y", "campo_unc": "UNCY", "unc_defecto": 10.0, "fecha_ref": "2026-05-04"})
    p["linea_base"].update({"modo": "archivo", "ruta": str(dsas / "linea_base_dsas.shp")})
    p["transectos"].update({"modo": "archivo", "ruta": str(dsas / "dsas_transectos.shp"), "espaciado_m": 100.0, "longitud_m": 1000.0, "suavizado_m": 500.0, "umbral_lineas": 10})

    def var(codigo, nombre, dim, **kw):
        v = variable_nueva(codigo, nombre); v["dimension"] = dim; v.update(kw); return v

    def tab(campo, **kw):
        return dict(metodo="tabla_por_id", fuente=tabla, capa="id_ivc", campo=campo, **kw)

    p["variables"] = [
        var("c_cambio_costa", "Cambio de la línea de costa (LRR 1984‑2026)", "Dinámica litoral", metodo="tasa", campo="LRR", rol="tasa", cortes="-2;-1;1;2", clases="5;4;3;2;1"),
        var("c_geomorfologia", "Geomorfología (unidad natural dominante 0‑200 m)", "Geomorfología", metodo="vector_categorico", fuente=str(ivc / "datos_fuente" / "geomorfologia_bs.shp"), campo="geomflgia_", d0=0, d1=200,
            filtro="Area urbana", normalizacion="categorias", mapa_clases="playas:5;campos de dunas:5;pantano de manglar:5;playones:5;laguna costera:4;salares y zonas de inundacion:4"),
        var("c_elevacion", "Elevación mediana 0‑200 m (DeltaDTM, m)", "Geomorfología", **tab("elev_mediana_0_200"), cortes="0.33;0.81;1.03;1.31", clases="5;4;3;2;1"),
        var("c_pendiente", "Pendiente del terreno 0‑200 m (°)", "Geomorfología", **tab("pend_terreno_media_0_200"), cortes="0.16;0.28;0.44;0.68", clases="5;4;3;2;1"),
        var("c_pendiente_playa", "Pendiente de la cara de playa (°)", "Geomorfología", **tab("pend_playa_grados"), cortes="1;4;8;12", clases="1;2;3;4;5", cerrado="izquierda"),
        var("c_oleaje", "Oleaje Hs p95 (m)", "Oceanografía", **tab("hs_p95_m"), cortes="2.95;3.01;3.09;3.16", clases="1;2;3;4;5"),   # Hs p95 no es H12: Bruun usa el parámetro H12_m explícito
        var("c_nivel_mar", "% del terreno 0‑500 m bajo el nivel AR6 SSP2‑4.5 2050", "Clima", **tab("pct_bajo_slr_ssp245_2050"), cortes="20;40;60;80", clases="1;2;3;4;5", rol="nivel_mar",
            campos_escenario={"ssp245_2050": "pct_bajo_slr_ssp245_2050", "ssp585_2050": "pct_bajo_slr_ssp585_2050", "ssp245_2100": "pct_bajo_slr_ssp245_2100", "ssp585_2100": "pct_bajo_slr_ssp585_2100"}),
        var("c_granulometria", "Tamaño medio de grano (mm)", "Geotecnia", **tab("tmg_mm"), cortes="0.126;0.25;0.5;1.0", clases="5;4;3;2;1", rol="d50"),
        var("c_sustrato", "Sustrato (grupo natural dominante 0‑200 m)", "Geotecnia", **tab("sust_dominante_nat_0_200"), normalizacion="categorias",
            mapa_clases="arenoso_no_cohesivo:5;agua:5;fino_cohesivo:4;fluviomarino_medio:4"),
        var("c_cobertura", "Cobertura de la tierra 2025 (promedio por área 0‑500 m)", "Ambiental", metodo="tabla_por_id", fuente=tabla_clases, capa="id_ivc", campo="c_cobertura", normalizacion="directa"),
        var("c_uso_suelo", "Uso del suelo (promedio por área 0‑500 m)", "Socioeconómica", metodo="tabla_por_id", fuente=tabla_clases, capa="id_ivc", campo="c_uso_suelo", normalizacion="directa"),
        var("c_dist_ruta90", "Distancia a la Ruta 90 (m)", "Infraestructura", metodo="distancia_a", fuente=str(res / "QGIS_IVC" / "datos" / "IVC_Barra_Salamanca.gpkg"), capa="ruta90",
            rol="distancia_infra", cortes="250;500;1000;1500", clases="5;4;3;2;1"),
        var("c_vivienda", "Área construida 0‑500 m (%)", "Socioeconómica", **tab("pct_huella_constr_0_500"), cortes="5;15;30;50", clases="1;2;3;4;5"),
        var("c_densidad_pob", "Densidad poblacional (hab/km²)", "Socioeconómica", **tab("dens_pob_dane_2026"), cortes="40;80;120;160", clases="1;2;3;4;5"),
        var("c_ancho_barra", "Ancho de la barra (m)", "Geomorfología", **tab("ancho_barra_m"), rol="ancho_barra", cortes="90;180;260;350", clases="5;4;3;2;1"),
    ]
    p["indice"].update({"tasa_validacion": "LRR", "n_bloques": 8})
    p["proyeccion"]["bruun"].update({"activo": False, "H12_m": 4.3, "H12_max_m": 4.7, "B_m": 1.0})
    p["proyeccion"]["sigma_regional"] = 1.308   # desviación del cambio medio regional entre las 4 ventanas de la validación temporal de la tesis (m/año)
    p["_nota"] = ("Cobertura y uso del suelo entran como el promedio ponderado por área ya calculado en la tesis (columnas c_cobertura/c_uso_suelo de "
                  "tabla_clases_1_5_ivc.csv); el ejemplo las lee de ahí porque las capas fuente (IDEAM 2025, INVEMAR usos) no están exportadas.")
    return p
