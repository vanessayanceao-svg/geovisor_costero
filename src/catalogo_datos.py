"""Catálogo de capas conocidas y adaptadores por formato.

Cada capa del geovisor se declara aquí con su origen (raíz + ruta relativa),
formato, capa interna (GPKG), campos relevantes y procedencia metodológica.
La disponibilidad se comprueba en tiempo de ejecución: si el archivo no
existe, la capa queda marcada como «Datos no disponibles» y la interfaz
deshabilita su control. Ninguna capa se inventa ni se rellena con datos de
demostración.

Las rutas relativas fueron verificadas en la inspección del 18‑10‑2026 de
``D:/COASTSAS/CoastSat-master`` y ``D:/TRABAJO DE INVESTIGACION/Resultados tesis``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .configuracion import ruta


@dataclass(frozen=True)
class Capa:
    clave: str
    titulo: str
    raiz: str                    # clave de cfg['rutas']
    relativa: str                # ruta relativa a esa raíz
    formato: str                 # vector | raster | tabla | imagen | documento
    capa: str | None = None      # capa interna (GeoPackage)
    grupo: str = "Referencia"
    procedencia: str = ""        # "CoastSat", "DSAS v6.1", "script postproceso", "modelo", ...
    descripcion: str = ""
    campos: tuple = field(default_factory=tuple)
    unidades: str = ""
    visible_defecto: bool = False
    opcional: bool = True

    def ruta(self, cfg: dict) -> Path:
        return ruta(cfg, self.raiz) / self.relativa

    def disponible(self, cfg: dict) -> bool:
        return self.ruta(cfg).exists()


# ---------------------------------------------------------------------------
# Registro de capas (clave -> Capa)
# ---------------------------------------------------------------------------
CAPAS: dict[str, Capa] = {}


def _reg(c: Capa) -> Capa:
    CAPAS[c.clave] = c
    return c


# --- Líneas de costa (CoastSat + postproceso) -------------------------------
_reg(Capa(
    "lineas_fecha", "Líneas de costa por fecha (CoastSat)", "exportar_coastsat",
    "postproceso/lineas_fechas_completas.shp", "vector", grupo="Línea de costa",
    procedencia="CoastSat 2.x + postproceso (coastsat_postproceso.py)",
    descripcion="Una entidad por fecha de imagen y lado (oeste/este). Campo 'fecha' = fecha y hora reales de adquisición; 'satname' = sensor Landsat; 'cob_pct' = cobertura de la línea.",
    campos=("fecha", "DATE_", "satname", "lado", "cob_pct", "clase", "n_tramos", "largo_m"), unidades="m", visible_defecto=True, opcional=False,
))
_reg(Capa(
    "lineas_anuales", "Líneas anuales (mediana, corregidas por marea)", "exportar_coastsat",
    "postproceso/lineas_anuales_marea_corregida.geojson", "vector", grupo="Línea de costa",
    procedencia="postproceso CoastSat: mediana anual de posiciones corregidas por marea",
    descripcion="Línea representativa de cada época (1984‑1985 … 2026) usada como insumo de DSAS. 'fecha_med' = fecha mediana de las imágenes del año.",
    campos=("epoca", "anio", "fecha_med", "lado", "n_imagenes", "cobertura", "largo_m", "iqr_med_m", "marea_corr"), unidades="m", visible_defecto=False,
))
_reg(Capa(
    "lineas_anuales_sin_marea", "Líneas anuales (sin corrección de marea)", "exportar_coastsat",
    "postproceso/lineas_anuales_sin_marea.geojson", "vector", grupo="Línea de costa",
    procedencia="postproceso CoastSat (sin corrección de marea)", campos=("epoca", "anio", "fecha_med", "lado"),
))
_reg(Capa(
    "lineas_anuales_dsas", "Líneas de costa anuales (insumo DSAS)", "exportar_coastsat",
    "dsas/lineas_anuales_dsas.shp", "vector", grupo="Línea de costa",
    procedencia="postproceso CoastSat → DSAS v6.1 (mediana anual corregida por marea)",
    descripcion="38 épocas (1984‑1985 … 2026) × 2 lados (oeste/este). 'DATE_' = fecha representativa usada por DSAS; 'UNCY' = incertidumbre de posición (m).",
    campos=("ID", "epoca", "lado", "DATE_", "UNCY"), unidades="m", visible_defecto=True, opcional=False,
))

# --- DSAS --------------------------------------------------------------------
_reg(Capa(
    "dsas_tasas", "Transectos DSAS con tasas (v6.1)", "exportar_coastsat",
    "dsas/dsas_tasas.shp", "vector", grupo="Erosión",
    procedencia="DSAS v6.1.177 (USGS), cálculo del 26‑09‑2026",
    descripcion="671 transectos cada 100 m. Tasas en m/año: EPR, LRR, WLR; distancias en m: NSM, SCE. LCI95/WCI = intervalo de confianza 95 %.",
    campos=("TransOrder", "BaselineID", "ShrCount", "LRR", "LR2", "LCI95", "EPR", "EPRUNC", "NSM", "SCE", "WLR", "WCI"), unidades="m/año; m",
))
_reg(Capa(
    "dsas_transectos", "Transectos DSAS (geometría)", "exportar_coastsat", "dsas/dsas_transectos.shp", "vector", grupo="Erosión",
    procedencia="DSAS v6.1.177", campos=("TransOrder", "BaselineID", "Azimuth", "Length"),
))
_reg(Capa(
    "linea_base", "Línea base DSAS", "exportar_coastsat", "dsas/linea_base_dsas.shp", "vector", grupo="Erosión",
    procedencia="construida para DSAS", campos=("ID", "lado"),
))
_reg(Capa(
    "tasas_script_100m", "Tasas recalculadas por script (100 m, marea corregida)", "exportar_coastsat",
    "postproceso/tasas_transectos_100m_marea_corregida.geojson", "vector", grupo="Erosión",
    procedencia="script postproceso (coastsat_postproceso.py): regresión sobre posiciones corregidas por marea",
    descripcion="712 transectos de 100 m del script; sirve para contrastar con DSAS (ver dsas/comparacion_script_vs_dsas.csv).",
    campos=("id", "lado", "dist_km", "sector", "zona", "n_lineas", "fecha_ini", "fecha_fin", "SCE", "NSM", "EPR", "LRR", "LR2", "WLR"), unidades="m/año; m",
))
_reg(Capa(
    "transectos_25m", "Transectos del script (25 m)", "exportar_coastsat",
    "postproceso/transectos_barra_salamanca.geojson", "vector", grupo="Erosión",
    procedencia="script postproceso", campos=("id", "lado", "dist_km", "sector"),
))
_reg(Capa(
    "dsas_comparacion", "Comparación script vs DSAS", "exportar_coastsat", "dsas/comparacion_script_vs_dsas.csv", "tabla", grupo="Erosión",
    procedencia="tabla de verificación",
))
_reg(Capa(
    "dsas_informe", "Informe resumen DSAS", "exportar_coastsat",
    "dsas/DSAS_summary_report_Transectos_Dsas_rates_20260926_092033.txt", "tabla", grupo="Erosión", procedencia="DSAS v6.1.177",
))
_reg(Capa("cobertura_anio", "Cobertura de líneas por año", "exportar_coastsat", "postproceso/cobertura_por_anio.csv", "tabla", grupo="Línea de costa", procedencia="postproceso"))
_reg(Capa("cobertura_fecha", "Cobertura de líneas por fecha", "exportar_coastsat", "postproceso/cobertura_por_fecha.csv", "tabla", grupo="Línea de costa", procedencia="postproceso"))
_reg(Capa("inventario_imagenes", "Inventario de imágenes CoastSat", "exportar_coastsat", "barra_salamanca_inventario.csv", "tabla", grupo="Línea de costa", procedencia="CoastSat"))
_reg(Capa("ciclo_estacional", "Tasas y ciclo estacional por transecto (25 m)", "exportar_coastsat", "postproceso/tasas_y_ciclo_estacional_marea_corregida.csv", "tabla", grupo="Erosión", procedencia="script postproceso"))

# --- Área de estudio y referencia -------------------------------------------
_reg(Capa("sectores_roi", "Sectores de procesamiento CoastSat (s01–s04)", "exportar_coastsat", "sectores_roi.geojson", "vector", grupo="Área de estudio", procedencia="CoastSat", campos=("sector",), visible_defecto=False))
_reg(Capa("boca_cienaga", "Boca de la Ciénaga (zona excluida en DSAS)", "exportar_coastsat", "boca_de_cienaga.geojson", "vector", grupo="Área de estudio", procedencia="digitalizado en QGIS 2026‑09‑24", campos=("nombre", "nota")))
_reg(Capa("sectores_atlas", "Sectores del atlas (km 0‑17 … 51‑68)", "resultados_tesis", "QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", "vector", capa="sectores_atlas", grupo="Área de estudio", procedencia="Mapas_IVC/qgis_exportar_datos.py", campos=("sector", "nombre", "km_inicio", "km_fin")))
_reg(Capa("puntos_km", "Kilometraje desde Bocas de Ceniza", "resultados_tesis", "QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", "vector", capa="puntos_km", grupo="Área de estudio", procedencia="Mapas_IVC", campos=("km", "rotulo")))
_reg(Capa("ruta90", "Ruta 90 / Troncal del Caribe", "resultados_tesis", "QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", "vector", capa="ruta90", grupo="Infraestructura", procedencia="IGAC 1:10.000 y OpenStreetMap"))
_reg(Capa("fondo_rgb", "Fondo tierra/agua (IDEAM 2025, DeltaDTM, NDWI S2 2026)", "resultados_tesis", "QGIS_IVC/rasters/fondo_rgb.tif", "raster", grupo="Imagen de referencia", procedencia="Mapas_IVC/mapas_ivc_comun.py"))

# --- Variables ambientales e infraestructura (fuentes del IVC) --------------
_reg(Capa("geomorfologia", "Geomorfología (INVEMAR)", "exportar_coastsat", "ivc/datos_fuente/geomorfologia_bs.shp", "vector", grupo="Variables ambientales", procedencia="INVEMAR"))
_reg(Capa("costas_bajas", "Costas bajas (INVEMAR)", "exportar_coastsat", "ivc/datos_fuente/invemar_costas_bajas.shp", "vector", grupo="Variables ambientales", procedencia="INVEMAR"))
_reg(Capa("usos_suelo", "Usos del suelo (área de estudio)", "exportar_coastsat", "ivc/datos_fuente/usos_recortado/USOS_recortado_Area_Estudio.shp", "vector", grupo="Variables ambientales", procedencia="fuente oficial recortada"))
_reg(Capa("poblacion", "Centros poblados", "exportar_coastsat", "ivc/datos_fuente/pob_salamanca.shp", "vector", grupo="Infraestructura", procedencia="DANE/IGAC"))
_reg(Capa("densidad_dane", "Densidad de población (DANE)", "exportar_coastsat", "ivc/datos_fuente/dane_densidad_recortada.geojson", "vector", grupo="Infraestructura", procedencia="DANE"))
_reg(Capa("osm_edificaciones", "Edificaciones (OpenStreetMap)", "exportar_coastsat", "ivc/datos_fuente/osm_barra_salamanca.gpkg", "vector", capa="edificaciones_poligonos", grupo="Infraestructura", procedencia="OpenStreetMap"))
_reg(Capa("osm_vias", "Vías (OpenStreetMap)", "exportar_coastsat", "ivc/datos_fuente/osm_barra_salamanca.gpkg", "vector", capa="vias_lineas", grupo="Infraestructura", procedencia="OpenStreetMap"))
_reg(Capa("manglar", "Hidrografía y manglar (OSM)", "exportar_coastsat", "ivc/datos_fuente/osm_barra_salamanca.gpkg", "vector", capa="hidrografia_manglar_poligonos", grupo="Variables ambientales", procedencia="OpenStreetMap"))
_reg(Capa("dem", "Modelo digital de elevación (barra)", "exportar_coastsat", "ivc/datos_fuente/slr/DEM_barra_salamanca.tif", "raster", grupo="Variables ambientales", procedencia="DeltaDTM/Copernicus (ver metodología)", unidades="m"))
_reg(Capa("inundacion_ssp585_2100", "Área bajo el nivel del mar SSP5‑8.5 2100", "exportar_coastsat", "ivc/datos_fuente/slr/inundacion_ssp585_2100.tif", "raster", grupo="Escenarios", procedencia="DEM vs. nivel del mar AR6"))

# --- IVC ---------------------------------------------------------------------
_reg(Capa(
    "ivc_transectos", "IVC por transecto (todas las versiones)", "resultados_tesis",
    "QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", "vector", capa="transectos_ivc", grupo="IVC",
    procedencia="Mapas_IVC/ivc_versiones.py (v4, 12‑10‑2026)",
    descripcion="671 transectos con el IVC (0‑1) y la clase (1‑5) de cada versión: ivc_<version>, clase_<version>; escenarios: ivc_ewm_total_<ssp>_<año> con _inf/_sup.",
    opcional=True,
))
_reg(Capa("ivc_costa", "Línea de costa 2026 clasificada por IVC", "resultados_tesis", "QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg", "vector", capa="costa_ivc", grupo="IVC", procedencia="Mapas_IVC/qgis_exportar_datos.py"))
_reg(Capa("ivc_versiones", "Códigos y títulos de las versiones del IVC", "resultados_tesis", "QGIS_IVC/datos/versiones.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC"))
_reg(Capa("ivc_pesos", "Pesos por entropía (EWM)", "resultados_tesis", "Mapas_IVC/pesos_ewm_ivc.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC/ivc_versiones.py"))
_reg(Capa("ivc_concordancia", "Concordancia entre versiones del IVC", "resultados_tesis", "Mapas_IVC/concordancia_versiones.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC"))
_reg(Capa("ivc_clases_variables", "Clases 1‑5 de cada variable por transecto", "exportar_coastsat", "ivc/tabla_clases_1_5_ivc.csv", "tabla", grupo="IVC", procedencia="ivc_clasificacion.py"))
_reg(Capa("ivc_variables", "Variables del IVC por transecto (valores)", "exportar_coastsat", "ivc/tabla_variables_ivc_transectos.csv", "tabla", grupo="IVC", procedencia="ivc_variables.py"))
_reg(Capa("ivc_clases_2005", "Clases 1‑5 de cada variable por transecto, estado 2005 reconstruido", "resultados_tesis", "Mapas_IVC/clases_2005_reconstruidas.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC/ivc_2005_reconstruido.py (22‑10‑2026)",
          descripcion="Variables de posición (ancho de barra, distancia a la Ruta 90, geomorfología, sustrato, uso del suelo) medidas desde la línea DSAS de 2005; tasa = LRR 1984‑2005; el resto conserva el valor actual. 650 transectos con línea de 2005."))
_reg(Capa("ivc_variables_2005", "Variables brutas por transecto, estado 2005 reconstruido", "resultados_tesis", "Mapas_IVC/variables_2005_reconstruidas.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC/ivc_2005_reconstruido.py"))
_reg(Capa("ivc_variables_2026_control", "Variables brutas 2026 (control de la reconstrucción)", "resultados_tesis", "Mapas_IVC/variables_2026_control.csv", "tabla", grupo="IVC", procedencia="Mapas_IVC/ivc_2005_reconstruido.py"))
_reg(Capa("ivc_diccionario", "Diccionario de variables del IVC", "exportar_coastsat", "ivc/diccionario_variables_ivc.csv", "tabla", grupo="IVC", procedencia="ivc_variables.py"))
_reg(Capa("ivc_franjas", "Franjas de muestreo 0‑500 m por transecto", "exportar_coastsat", "ivc/tabla_variables_ivc_transectos.gpkg", "vector", capa="franjas_0_500m", grupo="IVC", procedencia="ivc_variables.py"))
_reg(Capa("ivc_rasters_dir", "Rásteres del IVC (mapa de calor y valor)", "resultados_tesis", "QGIS_IVC/rasters", "raster", grupo="IVC", procedencia="Mapas_IVC/qgis_exportar_datos.py",
          descripcion="ivc_<version>.tif = RGBA (franja de 1,5 km, suavizado gaussiano de 150 m SOLO para el dibujo); ivc_<version>_valor.tif = IVC en escala 1‑5 (nodata −9999)."))
_reg(Capa("ruta90_priorizacion", "Priorización de tramos de la Ruta 90 (v4)", "resultados_tesis", "Multicriterio/priorizacion_ruta90_v4.csv", "tabla", grupo="Predicciones", procedencia="Multicriterio/fig_escenarios_v4.py (ruta90_v4)",
          descripcion="44 tramos de 1 km de costa con la vía a ≤ 1000 m: año en que la costa proyectada (persistencia amortiguada + Bruun SSP5‑8.5) alcanza la vía, con intervalo rápida/lenta, y prioridad Alta (< 2050) / Media (2050–2100) / Baja.",
          campos=("orden", "tramo", "km_inicio", "dist_min_ruta90_m", "anio_alcance", "prioridad", "km_via_inicio", "km_via_fin")))
_reg(Capa("ruta90_priorizacion_v3", "Priorización de la Ruta 90 (v3, LRR lineal, solo comparación)", "resultados_tesis", "Multicriterio/priorizacion_ruta90.csv", "tabla", grupo="Predicciones", procedencia="Multicriterio/fig_multicriterio_v2.py"))
_reg(Capa("figura_ruta90", "Figura 37 · Priorización de tramos de la Ruta 90", "resultados_tesis", "Figuras/Figura_37_priorizacion_Ruta90.png", "imagen", grupo="Figuras", procedencia="Multicriterio/fig_escenarios_v4.py"))
_reg(Capa("mapas_individuales_dir", "Mapas individuales del IVC (Mapa_01 … Mapa_18)", "resultados_tesis", "Mapas_IVC/mapas_individuales", "imagen", grupo="Figuras", procedencia="Mapas_IVC/ivc_mapas.py · ivc_mapas_escenarios.py"))
_reg(Capa("figuras_ivc_dir", "Figuras de síntesis del IVC (Figura_26 … Figura_30)", "resultados_tesis", "Mapas_IVC", "imagen", grupo="Figuras", procedencia="Mapas_IVC/ivc_versiones.py"))
_reg(Capa("atlas_ivc_pdf", "Atlas del IVC (PDF)", "resultados_tesis", "Mapas_IVC/Atlas_IVC_Barra_Salamanca.pdf", "documento", grupo="Figuras", procedencia="Mapas_IVC"))
_reg(Capa("comparacion_m1_m2_pesos", "Pesos EWM con normalización M1 (clases 1‑5) frente a M2 (difusa 0‑1)", "resultados_tesis", "Multicriterio/comparacion_M1_M2_pesos.csv", "tabla", grupo="IVC", procedencia="Multicriterio/comparacion_normalizaciones_M1_M2.py"))
_reg(Capa("comparacion_m1_m2_validacion", "Validación M1 frente a M2 (ρ, κ de quintiles)", "resultados_tesis", "Multicriterio/comparacion_M1_M2_validacion.csv", "tabla", grupo="IVC", procedencia="Multicriterio/comparacion_normalizaciones_M1_M2.py"))
_reg(Capa("tablas_10_r2os", "Tablas 10 · validación anidada y escenarios (v4, R²_OS)", "resultados_tesis", "Tablas/Tablas_10_Validacion_anidada_y_escenarios_v4_R2OS.xlsx", "tabla", grupo="Evaluación", procedencia="Tablas (2026‑10‑20)"))
_reg(Capa("tablas_09_topsis", "Tablas 09 · TOPSIS", "resultados_tesis", "Tablas/Tablas_09_TOPSIS.xlsx", "tabla", grupo="IVC", procedencia="Tablas (2026‑10‑20)"))
_reg(Capa("multicriterio_validacion", "Validación de los índices contra DSAS", "resultados_tesis", "Multicriterio/validacion_indices_dsas.csv", "tabla", grupo="IVC", procedencia="Multicriterio/ivc_multicriterio_v2.py"))

# --- Predicciones y escenarios -----------------------------------------------
for clave, rel, titulo in (
    ("proy_amortiguada", "Modelos/07_Proyecciones/resultados_amortiguada", "Persistencia amortiguada (variante recomendada)"),
    ("proy_ridge", "Modelos/07_Proyecciones/resultados", "Ridge, tendencia regional centrada"),
    ("proy_tendencia", "Modelos/07_Proyecciones/resultados_tendencia_aprendida", "Ridge, tendencia regional aprendida"),
):
    _reg(Capa(clave, f"Líneas de costa proyectadas — {titulo}", "resultados_tesis", rel + "/lineas_costa_proyectadas.gpkg", "vector", capa="lineas",
              grupo="Predicciones", procedencia="Modelos/07_Proyecciones/proyeccion_modelos.py (v4, corregido 12‑10‑2026)",
              descripcion="Campo 'linea': 2026 (observada), 2050, 2100 (central), *_p05/*_p95 (Monte Carlo, 2000 réplicas) y *_persistencia.",
              campos=("linea", "BaselineID")))
    _reg(Capa(clave + "_config", f"Metadatos de la proyección — {titulo}", "resultados_tesis", rel + "/configuracion_proyeccion.json", "tabla", grupo="Predicciones"))
    _reg(Capa(clave + "_resumen", f"Resumen de la proyección — {titulo}", "resultados_tesis", rel + "/proyeccion_resumen.csv", "tabla", grupo="Predicciones"))
    _reg(Capa(clave + "_transectos", f"Proyección por transecto — {titulo}", "resultados_tesis", rel + "/proyeccion_transectos.csv", "tabla", grupo="Predicciones"))
_reg(Capa("escenarios_resumen_v4", "Resumen de escenarios SSP (v4)", "resultados_tesis", "Mapas_IVC/escenarios_v4_resumen.csv", "tabla", grupo="Predicciones", procedencia="Multicriterio/fig_escenarios_v4.py"))
_reg(Capa("escenarios_resumen", "Resumen de escenarios SSP (detalle)", "resultados_tesis", "Multicriterio/escenarios_resumen.csv", "tabla", grupo="Predicciones", procedencia="Multicriterio"))
_reg(Capa("bruun_resumen", "Regla de Bruun — resumen", "resultados_tesis", "Modelos/07_Proyecciones/resultados_amortiguada/bruun/bruun_resumen.csv", "tabla", grupo="Predicciones", procedencia="bruun_proyeccion.py"))

# --- Evaluación de modelos ---------------------------------------------------
_reg(Capa("metricas_anidadas", "Métricas de validación anidada (v4, vigente)", "resultados_tesis", "Modelos/06_Validacion_anidada/resultados/metricas_anidadas.csv", "tabla", grupo="Evaluación", procedencia="Modelos/06_Validacion_anidada/apilamiento_anidado.py"))
_reg(Capa("comparacion_pareada", "Comparación pareada de modelos (v4)", "resultados_tesis", "Modelos/06_Validacion_anidada/resultados/comparacion_pareada.csv", "tabla", grupo="Evaluación"))
_reg(Capa("conformal_resumen", "Cobertura conformal por modelo (v4)", "resultados_tesis", "Modelos/06_Validacion_anidada/figuras_v4/fig46_cobertura_conformal_resumen.csv", "tabla", grupo="Evaluación"))
_reg(Capa("config_anidada", "Configuración de la validación anidada", "resultados_tesis", "Modelos/06_Validacion_anidada/resultados/configuracion_anidada.json", "tabla", grupo="Evaluación"))
_reg(Capa("mse_bloque", "MSE por bloque espacial (v4)", "resultados_tesis", "Modelos/06_Validacion_anidada/resultados/mse_por_bloque.csv", "tabla", grupo="Evaluación"))
_reg(Capa("predicciones_anidadas", "Predicciones fuera de bloque (v4)", "resultados_tesis", "Modelos/06_Validacion_anidada/resultados/predicciones_anidadas.csv", "tabla", grupo="Evaluación"))
_reg(Capa("bloques", "Bloques espaciales de validación", "resultados_tesis", "Modelos/00_comun/resumen_bloques.csv", "tabla", grupo="Evaluación"))
_reg(Capa("tabla_r2_v2", "R² de modelos v2 (histórico, no vigente)", "resultados_tesis", "Modelos/03_Apilamiento/v2_residual/tabla_R2_modelos_v2.csv", "tabla", grupo="Evaluación"))
_reg(Capa("validacion_coastsat_manual", "Validación CoastSat vs. línea manual 2026", "exportar_coastsat", "postproceso/validacion_coastsat_vs_manual_2026.csv", "tabla", grupo="Evaluación", procedencia="postproceso"))


def estado_capas(cfg: dict) -> dict[str, bool]:
    return {k: c.disponible(cfg) for k, c in CAPAS.items()}


def capas_por_grupo(cfg: dict, solo_mapa: bool = True) -> dict[str, list[Capa]]:
    grupos: dict[str, list[Capa]] = {}
    for c in CAPAS.values():
        if solo_mapa and c.formato in ("tabla", "imagen", "documento"):
            continue
        grupos.setdefault(c.grupo, []).append(c)
    return grupos


def estado_modulos(cfg: dict) -> dict[str, dict]:
    """Disponibilidad real de cada módulo a partir de los archivos presentes."""
    e = estado_capas(cfg)
    return {
        "Histórico": {"ok": e["lineas_anuales_dsas"] or e["lineas_fecha"], "detalle": "líneas anuales DSAS" if e["lineas_anuales_dsas"] else ("líneas por fecha" if e["lineas_fecha"] else "faltan líneas de costa")},
        "DSAS": {"ok": e["dsas_tasas"], "detalle": "tasas DSAS v6.1" if e["dsas_tasas"] else "faltan tasas DSAS"},
        "IVC": {"ok": e["ivc_transectos"], "detalle": "16 versiones" if e["ivc_transectos"] else "falta IVC_Barra_Salamanca.gpkg"},
        "Predicciones": {"ok": e["proy_amortiguada"] or e["proy_ridge"], "detalle": "2050 y 2100" if (e["proy_amortiguada"] or e["proy_ridge"]) else "faltan líneas proyectadas"},
        "Evaluación": {"ok": e["metricas_anidadas"], "detalle": "métricas v4" if e["metricas_anidadas"] else "faltan métricas"},
    }
