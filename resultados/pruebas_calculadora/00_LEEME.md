# Corrida de verificación de la Calculadora IVC — Barra de Salamanca

Generado: 2026-10-25 23:21 · duración 51 s · `scripts/generar_pruebas_calculadora.py`

**Resultado: 25/25 comprobaciones superadas.** Cada paso del motor se ejecutó con los insumos reales de la tesis y se comparó
con los productos oficiales (DSAS v6.1.177, `tabla_clases_1_5_ivc.csv`, pesos EWM, `transectos_ivc`, proyección amortiguada v4).

| Paso | Comprobación | Valor | Umbral | Resultado |
|---|---|---|---|---|
| 01 insumos | número de fechas (líneas anuales DSAS) | 38 | = 38 | ✅ OK |
| 01 insumos | intervalo de fechas | 1984-11-28 → 2026-05-04 | 1984‑11‑28 → 2026‑05‑04 | ✅ OK |
| 02 transectos | transectos | 671 | = 671 | ✅ OK |
| 02 transectos | intersecciones línea‑transecto | 25068 | = 25 068 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en LRR | 8.80e-05 m/año | < 1e‑3 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en WLR | 8.80e-05 m/año | < 1e‑3 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en EPR | 7.81e-05 m/año | < 1e‑3 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en LCI95 | 5.22e-06 m/año | < 1e‑3 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en NSM | 3.23e-03 m | < 1e‑2 | ✅ OK |
| 02 tasas | máx. |geovisor − DSAS| en SCE | 7.10e-04 m | < 1e‑2 | ✅ OK |
| 03 variables | variables con clases idénticas a la tesis | 15/15 | 15/15 | ✅ OK |
| 03 variables | errores al distribuir | 0 | 0 | ✅ OK |
| 04 pesos | máx. |peso EWM geovisor − tesis| | 9.16e-14 | < 1e‑9 | ✅ OK |
| 04 pesos | suma de pesos EWM | 1.000000 | = 1 | ✅ OK |
| 05 índice | máx. |IVC EWM geovisor − tesis| | 1.79e-13 | < 1e‑9 | ✅ OK |
| 05 índice | máx. |IVC TOPSIS geovisor − tesis| | 1.52e-13 | < 1e‑9 | ✅ OK |
| 05 validación | ρ Spearman IVC EWM vs −LRR | 0.619 | 0,619 ± 0,005 (tesis) | ✅ OK |
| 05 validación | ρ Spearman IVC estructural (sin tasa) vs −LRR | 0.536 | 0,536 ± 0,005 (tesis) | ✅ OK |
| 05 índice | % transectos clase alta + muy alta (2026) | 10.28 % | 10,28 % (tesis) | ✅ OK |
| 06 proyección | R²_OS del modelo de transición (amortiguada) frente a persistencia | 0.100 | 0,08–0,12 (tesis +10,0 %) | ✅ OK |
| 06 proyección | bloques (de 8) en que mejora a la persistencia | 7 | ≥ 6 (tesis 7/8) | ✅ OK |
| 06 proyección | correlación desplazamiento 2100 geovisor vs tesis | 1.00000 | > 0,999 | ✅ OK |
| 06 proyección | % clase alta+muy alta SSP2‑4.5 2050 | 12.97 % | 12,97 % ± 0,5 (tesis) | ✅ OK |
| 07 exportación | productos exportados | 30 | ≥ 23 | ✅ OK |
| 09 pruebas | pytest | 50 passed, 6 warnings in 11.62s | todas superadas | ✅ OK |

## Contenido de las carpetas

| Carpeta | Contenido |
|---|---|
| `01_insumos/` | `proyecto.json` (proyecto completo tal como lo guarda la app), `proyecto_inicial.json`, `lineas_por_fecha.csv` |
| `02_transectos_tasas/` | `transectos_tasas.gpkg` (671 transectos con NSM, SCE, EPR, EPRunc, LRR, LR2, LSE, LCI95, WLR, WR2, WSE, WCI), `linea_base.gpkg`, `intersecciones.csv` (25 068), `tasas.csv`, `comparacion_tasas_vs_dsas.csv`, perfiles e histograma PNG |
| `03_variables/` | `variables_valores.csv` (valor bruto por transecto), `variables_clases.csv` (clase 1‑5), `comparacion_clases_vs_tesis.csv`, `resumen_pct_por_clase.csv`, `clases_por_variable.png` |
| `04_ponderacion/` | `pesos_ewm.csv` (entropía, divergencia, peso, IC95), `pesos_fahp.csv`, `pesos_todos.csv` (EWM, FAHP, iguales, combinados), `pesos_ewm_ic95.png` |
| `05_indice_validacion/` | `indice_transectos.csv/.gpkg` (IVC por esquema, TOPSIS, Gornitz, clases, bloque, estabilidad), `validacion.csv` (ρ con IC95 por bloques), `concordancia.csv` (κ), `redundancia_vif.csv`, `sensibilidad_pesos.csv`, gráficos PNG |
| `06_proyeccion/` | `proyeccion_transectos.csv` (tasas por ventana, desplazamientos 2050/2100 con p05–p95), `proyeccion_resumen.csv`, `lineas_proyectadas.gpkg`, `escenario_*.csv` (IVC futuro SSP2‑4.5/SSP5‑8.5 2050/2100), `proyeccion_modelo.json`, gráficos PNG |
| `07_mapas/` | Mapas estáticos PNG: tasa LRR, IVC 2026 (clases, EWM, TOPSIS) e IVC futuro por escenario |
| `08_capturas_interfaz/` | Capturas de cada paso de la Calculadora en la aplicación (`scripts/capturas_calculadora.py`) |
| `09_pruebas_automaticas/` | Salida completa de `pytest` (`tests/`) |

Todos los CRS de las capas exportadas son EPSG:32618 (WGS 84 / UTM 18N). Signo de las tasas: negativo = retroceso (hacia tierra).