# Inventario del geovisor — dónde está cada cosa

Carpeta raíz: `D:\TRABAJO DE INVESTIGACION\Resultados tesis\geovisor_costero` (copia de desarrollo sincronizada el 25‑10‑2026). Rutas relativas a esa carpeta. El geovisor **no modifica** los datos originales de CoastSat ni de la tesis: solo los lee desde las rutas de `config.yaml`.

```
geovisor_costero/
├── app.py                      aplicación Streamlit (cabecera, menú de secciones, tema)
├── abrir_geovisor.bat          arranque en Windows (entorno conda "coastsat")
├── config.yaml                 configuración (rutas de datos, mapa, colores, módulos)
├── config.local.yaml           rutas propias de este equipo (prioridad sobre config.yaml; no se publica)
├── requirements.txt            dependencias Python
├── README.md                   documentación técnica (arquitectura, cambios, publicación)
├── .streamlit/config.toml      tema Streamlit (fuente Manrope, colores, radios, tablas)
├── .gitignore
├── assets/                     fondo de mapa (PNG claro/oscuro) y costa mundial 110 m
├── docs/                       ← documentación para la autora y los evaluadores
├── scripts/                    utilidades de línea de comandos
├── src/                        código fuente
├── tests/                      pruebas automáticas (pytest)
├── resultados/                 salidas generadas por el geovisor (se pueden borrar y regenerar)
└── logs/                       geovisor.log
```

## docs/ — documentación

| Archivo | Contenido |
|---|---|
| `docs/GUIA_USUARIO.md` · `docs/GUIA_USUARIO.pdf` | Guía de usuario (Markdown y PDF): instalación, pantalla, cada sección, Calculadora IVC paso a paso, entregables, preguntas frecuentes, cómo citar |
| `docs/INVENTARIO.md` | Este inventario |
| `docs/AUDITORIA_CALCULADORA.md` · `.pdf` | Auditoría numérica independiente del motor de cálculo (tabla de 60 comprobaciones, 10 defectos encontrados, advertencias, faltantes) y la sección «Correcciones aplicadas» |
| `docs/auditoria_scripts/` | Scripts de evidencia de la auditoría (`check_dsas.py`, `check_units.py`, `check_muestreo.py`, `check_proy.py`, `check_edges.py`, `run_e2e.py`) con sus salidas `salida_*.txt` y `LEEME.md` |
| `docs/capturas/` | Capturas de cada sección (01 visor … 09 entregables de la calculadora) usadas en la guía |

## scripts/ — utilidades

| Script | Para qué | Resultado |
|---|---|---|
| `scripts/comprobar_entorno.py` | Diagnóstico de dependencias, rutas y módulos disponibles | texto en consola (lo ejecuta el .bat) |
| `scripts/generar_pruebas_calculadora.py` | Corrida completa de verificación de la Calculadora con los insumos de la tesis (`--rapido` para menos réplicas) | `resultados/pruebas_calculadora/` |
| `scripts/capturas_calculadora.py` | Capturas de cada paso de la Calculadora en la interfaz (requiere la app abierta en localhost:8501 y Playwright) | `resultados/pruebas_calculadora/08_capturas_interfaz/` |
| `scripts/generar_guia_pdf.py` | Convierte los .md de `docs/` en PDF (Chromium/Playwright) | `docs/*.pdf` |
| `scripts/generar_fondo.py` | Regenera los PNG de fondo del mapa en `assets/` | `assets/fondo_mapa_*.png` |
| `scripts/preparar_publicacion.py` | Copia ligera de datos y `config.publico.yaml` para publicar en Streamlit Community Cloud | `datos_publicacion/` |

## src/ — código fuente

### Núcleo de la aplicación

| Módulo | Función |
|---|---|
| `src/configuracion.py` | Carga `config.yaml` + `config.local.yaml`, resuelve rutas, crea carpetas de salida |
| `src/contexto.py` | Configuración compartida en la sesión Streamlit |
| `src/catalogo_datos.py` | Catálogo de capas conocidas (clave → archivo, formato, procedencia) y adaptadores de lectura |
| `src/inventario.py` | Inventario de archivos geoespaciales → `resultados/catalogo/` |
| `src/vectores.py` · `src/rasteres.py` | Lectura/transformación de vectores y rásteres (simplificación y remuestreo solo para visualizar) |
| `src/mapas.py` | Construcción del mapa Folium/Leaflet, capas, leyendas, encuadre |
| `src/graficos.py` | Gráficos Plotly con estilo unificado (leyenda sobre el gráfico) |
| `src/estilos.py` | Sistema visual: temas claro/oscuro, tipografía (Manrope interfaz / Poppins títulos), tarjetas, pestañas, tablas, iconos SVG |
| `src/temporal.py` | Control temporal: fechas reales de observación, selección y navegación |
| `src/dsas.py` | Lectura de resultados DSAS y métricas del postproceso |
| `src/ivc.py` | Versiones del IVC de la tesis (2026, 2005, control), clases por variable, cambio 2005‑2026 |
| `src/predicciones.py` | Líneas proyectadas 2050/2100 e IVC futuro por escenario |
| `src/ruta90.py` | Priorización de tramos de la Ruta 90 |
| `src/metricas_modelos.py` | Tablas de la validación anidada v4 e importación de métricas externas |
| `src/informe_pdf.py` | Informe PDF tipo dashboard de un proyecto de la Calculadora (indicadores, mapas, gráficos, tablas, metodología y cita del aplicativo) |
| `src/exportaciones.py` | Exportación de capas y tablas (GeoJSON, GPKG, CSV) |
| `src/cachear.py` | Caché compatible con Streamlit y con scripts |

### Páginas (secciones de la interfaz) — `src/paginas/`

| Archivo | Sección |
|---|---|
| `visor.py` | 1 Visor geoespacial (mapa, capas por chips, control temporal, estadísticas) |
| `evolucion.py` | 2 Evolución histórica |
| `erosion.py` | 3 Línea de costa y erosión (DSAS) |
| `ivc.py` | 4 Vulnerabilidad costera (IVC) |
| `predicciones.py` | 5 Predicciones y escenarios (incl. Ruta 90) |
| `evaluacion.py` | 6 Evaluación del modelo |
| `calculadora.py` | 7 Calculadora IVC (asistente de 7 pasos, tarjetas de variables, control de vigencia de resultados) |
| `datos.py` | 8 Datos y metodología |
| `comunes.py` | Componentes compartidos: tarjetas KPI (se ocultan sin dato), paneles, notas plegadas ⓘ, tablas HTML (`tabla`), descargas, mapa |

### Motor de cálculo — `src/calculo/`

| Módulo | Qué calcula | Referencia metodológica |
|---|---|---|
| `transectos.py` | Línea base, transectos perpendiculares, intersecciones con cada línea de costa, P0 de referencia | DSAS v6.1 (Himmelstoss et al., 2021) |
| `tasas.py` | NSM, SCE, EPR, EPRunc, LRR, LR2, LSE, LCI95, WLR, WR2, WSE, WCI; tasas por ventana | DSAS v6.1 |
| `muestreo.py` | Distribución de variables a los transectos: estadístico en franja, pendiente, categoría dominante/% de área, distancia, más cercano, ancho de barra, tabla por id | `ivc_variables.py` de la tesis |
| `normalizacion.py` | Clases 1‑5 por umbrales (cerrado izq./der.), categorías, % de área, difusa 0‑1, quintiles, directa; clase del índice 0‑1 | M1/M2 de la tesis; Gornitz et al. (1991) |
| `ponderacion.py` | EWM (Shannon) con IC95 (bloques e iid), FAHP (TFN, Buckley 1985 / Chang 1996, CR de Saaty), pesos iguales/manuales, combinación FAHP‑EWM | Zou et al. (2006); Buckley (1985); Chang (1996); Saaty (1980) |
| `indice.py` | IVC lineal, TOPSIS (ideal absoluto y relativo), CVI de Gornitz, ρ de Spearman con bootstrap de bloques, κ ponderado, VIF, sensibilidad de pesos y por exclusión, estabilidad de clase, bloques contiguos | `ivc_multicriterio_v2.py` de la tesis; Hwang y Yoon (1981) |
| `proyeccion.py` | Ventanas, modelos de transición (persistencia, amortiguada, Ridge, RF) con validación en bloques y zona de exclusión, R²_OS, Monte Carlo, Bruun, IVC futuro | `Modelos/07_Proyecciones` de la tesis; Bruun (1962); Campbell y Thompson (2008) |
| `proyecto.py` | Proyecto serializable (`proyecto.json`), ejecución de cada paso y `exportar_todo` | — |
| `ejemplos.py` | Proyecto de ejemplo «Barra de Salamanca» con los 15 insumos de la tesis | — |
| `capas_proyecto.py` | Capas de los proyectos exportados (GeoPackages) para el visor y el mapa integrado; mapa HTML autónomo | — |

## tests/ — pruebas automáticas (51, `python -m pytest tests`)

| Archivo | Cubre |
|---|---|
| `test_calculadora.py` | Reproducción de la tesis (y capas de proyecto + informe PDF): tasas DSAS (< 0,001 m/año), transectos, 15 clases, pesos EWM e IVC (1e‑9), ρ 0,619/0,536, proyección amortiguada (R²_OS +10 %, 7/8), FAHP |
| `test_auditoria.py` | Regresión de los defectos D1–D9 de la auditoría con datos sintéticos |
| `test_modulos.py` · `test_temporal.py` · `test_geometrias.py` · `test_inventario.py` | Módulos de la tesis, control temporal, geometrías, catálogo |

## resultados/ — salidas generadas

| Carpeta | Contenido | ¿Se puede borrar? |
|---|---|---|
| `resultados/pruebas_calculadora/` | **Corrida de verificación de la Calculadora** (25‑10‑2026): `00_LEEME.md` (25 comprobaciones vs tesis), `verificacion_vs_tesis.csv`, `01_insumos/`, `02_transectos_tasas/` (GPKG + CSV + perfiles PNG + comparación con DSAS), `03_variables/`, `04_ponderacion/`, `05_indice_validacion/` (IVC por transecto, validación, κ, VIF, sensibilidad, gráficos), `06_proyeccion/` (tablas, líneas GPKG, escenarios, modelo, gráficos), `07_mapas/` (PNG: LRR, IVC 2026 clases/EWM/TOPSIS, IVC futuro por escenario), `08_capturas_interfaz/` (una captura por paso), `09_pruebas_automaticas/` (salida de pytest), `informe_dashboard_barra_salamanca.pdf` (informe generado con `src/informe_pdf.py`) | Sí; se regenera con `scripts/generar_pruebas_calculadora.py` |
| `resultados/calculadora/<proyecto>/` | Exportación de la Calculadora desde la interfaz (botón **Guardar todo**), `insumos/` subidos, `informe_<proyecto>.pdf` y mapa HTML; estas capas se cargan en el Visor (grupo «Calculadora») | Sí (son sus propios resultados) |
| `resultados/catalogo/` | `catalogo_datos.csv/json` (inventario de capas) | Sí; se regenera en «Datos y metodología» |
| `resultados/cache/` | Caché de GeoJSON/ráster para el mapa | Sí |
| `resultados/exportaciones/` · `resultados/reportes/` | Exportaciones puntuales | Sí |

## Datos de entrada (fuera del geovisor; solo lectura)

| Clave de `config.yaml › rutas` | Ruta en este equipo | Uso |
|---|---|---|
| `exportar_coastsat` | `D:/COASTSAS/CoastSat-master/exportar_coastsat` | líneas de costa (`dsas/lineas_anuales_dsas.shp`, 38 fechas), DSAS (`dsas_transectos.shp`, `dsas_tasas.shp`, `linea_base_dsas.shp`), IVC (`ivc/tabla_variables_ivc_transectos.csv`, `tabla_clases_1_5_ivc.csv`, pesos, geomorfología), rásteres |
| `resultados_tesis` | `D:/TRABAJO DE INVESTIGACION/Resultados tesis` | `Mapas_IVC/`, `Modelos/` (validación anidada v4, `07_Proyecciones`), `QGIS_IVC/datos/IVC_Barra_Salamanca.gpkg`, Ruta 90, figuras y atlas |
| `coastsat_data` | `D:/COASTSAS/CoastSat-master/data` | escenas Landsat (solo visualización) |

## Cambios del 25‑10‑2026 (resumen)

* Interfaz: tipografía Manrope/Poppins, botones y campos alineados, pestañas segmentadas, tablas HTML propias, notas plegadas, título genérico con chip de proyecto, indicadores sin dato ocultos, capas Transectos y Tasas activas al abrir.
* Calculadora: fila de insumos reorganizada, pestañas internas sin numeración, control de vigencia de resultados (D10), corrección de D1–D9 (ver auditoría), TOPSIS relativo, ρ por bloque, IC iid de EWM, sensibilidad por exclusión, exportaciones ampliadas.
* Organización: scripts en `scripts/`, documentación en `docs/`, corrida de verificación en `resultados/pruebas_calculadora/`.

## Añadido el 26‑10‑2026

* Grupo **Calculadora** en el Visor geoespacial: capas de cualquier proyecto exportado (`src/calculo/capas_proyecto.py`).
* Paso 7 de la Calculadora: mapa integrado, mapa HTML autónomo, informe PDF tipo dashboard (`src/informe_pdf.py`) y descarga del atlas IVC de la tesis.
* Guía de usuario y auditoría en PDF (`scripts/generar_guia_pdf.py`); capturas con fondo de mapa.
* Repositorio preparado para GitHub: `LICENSE`, `.gitignore`, `CITATION.cff`, README con capturas e instrucciones de publicación.
