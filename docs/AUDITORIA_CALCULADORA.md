# Auditoría numérica del motor de cálculo del geovisor (`src/calculo/`)

> **Estado (25‑10‑2026, tras la auditoría): todos los defectos D1–D10 están corregidos** y cubiertos por pruebas de regresión (`tests/test_auditoria.py`, 10 pruebas) además de las 6 pruebas de reproducción de la tesis; la suite completa (50 pruebas) pasa. La sección final «Correcciones aplicadas» detalla cada cambio y su justificación. El informe que sigue es el de la auditoría independiente, realizada sobre el código *antes* de las correcciones, y se conserva íntegro como evidencia.


**Fecha:** 2026‑10‑25 · **Código auditado:** `src/calculo/{transectos,tasas,muestreo,normalizacion,ponderacion,indice,proyeccion,proyecto,ejemplos}.py` y `src/paginas/calculadora.py` (sin modificar) · **Verdad de referencia:** DSAS v6.1 (`exportar_coastsat/dsas/dsas_tasas.shp`, `dsas_intersecciones.shp`), tablas de la tesis (`exportar_coastsat/ivc/*.csv`, `Resultados tesis/Mapas_IVC/*`, `Resultados tesis/Modelos/07_Proyecciones/resultados_amortiguada/*`).

**Método.** Se ejecutó el flujo completo (`ejemplos.ejemplo_salamanca` → `paso_transectos` → `paso_variables` → `paso_pesos` → `paso_indice` → `paso_proyeccion` → `exportar_todo`) y se contrastó cada módulo con (i) implementaciones independientes de las fórmulas (scipy/sklearn/numpy), (ii) las salidas de la tesis y (iii) datos sintéticos de respuesta conocida y casos límite. Scripts y salidas en `docs/auditoria_scripts/` (`run_e2e.py`, `check_dsas.py`, `check_units.py`, `check_muestreo.py`, `check_proy.py`, `check_edges.py`, con sus `salida_*.txt`). La suite `tests/test_calculadora.py` pasa (6/6, 10,8 s).

**Veredicto global.** El núcleo numérico es correcto y reproduce la tesis con precisión de máquina: tasas DSAS (error máximo 8,8·10⁻⁵ m/año), clases 1‑5, pesos EWM (9·10⁻¹⁴), IVC‑EWM, TOPSIS (1,5·10⁻¹³), ρ de Spearman (0,6188 vs 0,6188 de la tesis), R²_OS (+10,0 %, 7/8 bloques) y los desplazamientos centrales 2050/2100 (corr 1,000). Se encontraron **3 defectos de impacto real en casos de uso del geovisor** (TOPSIS con cualquier NaN, tasa media `tasaL` para horizontes cercanos, invalidación de resultados en la UI), **6 defectos menores** y varias advertencias metodológicas. Ninguno afecta a los números que la tesis ya publicó con el caso Salamanca (sin NaN, horizontes 2050/2100).

---

## (a) Tabla de comprobaciones

| # | Módulo | Comprobación | Resultado | Evidencia numérica |
|---|---|---|---|---|
| 1.1 | tasas | NSM, SCE vs `dsas_tasas.shp` (671 transectos) | **OK** | máx \|Δ\| NSM 0,0032 m; SCE 0,0007 m (DSAS redondea la distancia de intersección a 6 cifras; Δ coordenadas 0,0046 m) |
| 1.2 | tasas | EPR, EPRUNC = √(u₁²+u₂²)/años | **OK** | máx \|Δ\| EPR 7,8·10⁻⁵ m/a; EPRUNC 0,0 |
| 1.3 | tasas | LRR (MCO sobre año decimal), LR2, LSE, LCI95 = t₀,₉₇₅(n−2)·se(b) | **OK** | máx \|Δ\| LRR 8,8·10⁻⁵; LR2 3,1·10⁻⁵; LSE 1,9·10⁻⁴; LCI95 5·10⁻⁶. Contra `scipy.stats.linregress` independiente: 7·10⁻¹⁵ |
| 1.4 | tasas | WLR (pesos 1/unc²), WR2, WSE, WCI | **OK** | máx \|Δ\| WLR 8,8·10⁻⁵; WR2 3,1·10⁻⁵; WSE 1,7·10⁻⁵; WCI 5·10⁻⁶. Contra MCP matricial independiente: 7,7·10⁻¹⁰. WSE de DSAS = √(Σw·r²/(n−2)) sin normalizar pesos → reproducido (WSE 3,567 vs LSE 39,23 con unc = 11) |
| 1.5 | tasas | Signo: NSM<0 = erosión (hacia tierra) | **OK** | 85,69 % de transectos con NSM<0 = informe DSAS (85,69 %); distancia crece hacia el mar (−u) |
| 1.6 | tasas | n_lineas vs ShrCount; umbral 10 | **OK** | Δ máx 0; mínimo 17 líneas; ningún LRR nulo |
| 1.7 | tasas | unc = 0 en una línea | **ADVERTENCIA** (D5) | WLR/WR2/WSE/WCI se omiten para todo el transecto (peso ∞) en lugar de usar la incertidumbre por defecto |
| 1.8 | tasas | Fechas duplicadas / 1 sola línea | OK | `intersecciones` deja una fila por (id_t, fecha); 1 línea → EPR/LRR NaN sin error |
| 2.1 | transectos | Intersecciones vs `dsas_intersecciones.shp` | **OK** | 25 068 = 25 068 pares (id, fecha) emparejados, 0 huérfanos; máx \|Δ dist\| 0,0044 m; Δ año decimal 0,0 (también en 5 932 fechas de años bisiestos: DSAS = año + día/365) |
| 2.2 | transectos | Criterio «cercana» (DSAS) vs «lejana» | OK | 0 de 25 068 pares con cortes múltiples en Salamanca (ambos criterios idénticos); lógica revisada: `dist < prev` para cercana |
| 2.3 | transectos | Signo respecto de la base (u hacia tierra, dist = −v·u) | **OK** | coherente con 1.5 y con `lineas_proyectadas` (x₀ − u·d) |
| 2.4 | transectos | Transectos sin corte | OK | se omiten en `inter`; `p0_de_referencia` marca `sin_linea_ref=1`, tasas NaN |
| 2.5 | transectos | Generación de transectos desde la línea base DSAS | OK (test) | azimut mediano < 0,1°, p95 < 1° (test existente) |
| 2.6 | transectos | `generar_linea_base` docstring vs código | ADVERTENCIA | docstring (l. 72‑74) promete estimar el lado por centroide; el código (l. 79) usa «derecha» por defecto |
| 2.7 | transectos | Año decimal 31‑dic de año bisiesto | ADVERTENCIA | 366/365 = 1,0027 → mayor que el 1‑ene siguiente (no monótono). Fiel a DSAS; irrelevante con líneas anuales |
| 3.1 | muestreo | `raster_estadistico` mediana/media/pct_bajo/min/max en DEM sintético z = y (5 m) | **OK** (aprox.) | 97,5 vs 100 exacto (malla de puntos cada 10 m; artefacto de alineación con los bordes de celda); pct_bajo 25,0 % = esperado; NoData (−9999) filtrado (mín 2,5); zonal exacta `rasterio.mask`: 100,0 |
| 3.2 | muestreo | pct_nodata y franja sin dato | OK | franja 100 % NoData → pct_nodata 100 %, estadístico NaN |
| 3.3 | muestreo | `raster_pendiente` (DEM 45° y 0,573°) | **OK** | 45,00° y 0,573° exactos |
| 3.4 | muestreo | Ráster en EPSG:4326 reproyectado a 32618 | OK | mediana 98,27 (≈100); resolución deducida 5,08 m (grados·111 000) |
| 3.5 | muestreo | `vector_categorico` % de área y dominante | **OK** | 75/25 y 50/50 exactos; `vector_numerico` media por área 15,0 y 20,0 exactos |
| 3.6 | muestreo | Polígonos solapados | **ERROR menor** (D6) | suma de % = 200 %; `sin_dato` recortado a 0 en silencio (l. 167) |
| 3.7 | muestreo | `excluir` sensible a mayúsculas | ADVERTENCIA | `excluir=("a",)` no excluye la categoría «A» (el mapa de clases sí normaliza a minúsculas) |
| 3.8 | muestreo | `distancia_a`, filtro pandas, `mas_cercano` | OK | 50 m / 300 m con filtro; valores 1,1,1,2,2,2 esperados |
| 3.9 | muestreo | `tabla_por_id` ids duplicados / columnas mixtas | ADVERTENCIA (D7) | «cannot reindex on an axis with duplicate labels» (mensaje crudo); 3 números + 1 texto → numérica con NaN (heurística 50 %) |
| 3.10 | muestreo | `ancho_barra` (agua de 30 m ignorada; agua ≥ 60 m detectada) | OK (±paso) | 310 y 410 m frente a 300/400 exactos (discretización de 10 m); P0 en el mar → ancho medido desde P0 (310), no desde la orilla (260) |
| 4.1 | normalizacion | `por_umbrales` cerrado derecha/izquierda | **OK** | x = 1,0 → clase (−∞,1] con «derecha», [1,2) con «izquierda»; NaN → NaN |
| 4.2 | normalizacion | Clases de las 15 variables vs `tabla_clases_1_5_ivc.csv` | **OK** (test) | `np.allclose` 1e‑6 en todas |
| 4.3 | normalizacion | `clase_de_indice_01` bordes | OK | 0,2 → 2; 0,8 → 5; 1,0 → 5; −0,1 → 1; 1,2 → 5; cortes 1‑5 equivalentes [1,8; 2,6; 3,4; 4,2] = config |
| 4.4 | normalizacion | Clases IVC vs tesis `clase_ewm_total` | **OK** | 0 transectos distintos |
| 4.5 | normalizacion | quintiles / difusa / categorías / directa | OK | quintiles 1‑5 e inverso 5‑1; < 5 válidos → NaN; difusa constante → 0,5; «directa» fuera de 1‑5 → ValueError; «directa» todo NaN pasa sin aviso |
| 5.1 | ponderacion | EWM (Shannon) independiente y vs tesis `peso_total` | **OK** | Δ 0,0 (independiente) y 9,2·10⁻¹⁴ (tesis) |
| 5.2 | ponderacion | Columna constante ≠ 0 | OK | peso 0 (−3·10⁻¹⁵) |
| 5.3 | ponderacion | Columna toda 0 / todas constantes | **ADVERTENCIA** (D8) | columna de ceros recibe peso 0,93; todas constantes → 0/0 → [0,5, 0,5] (NaN enmascarado por `np.where`) |
| 5.4 | ponderacion | IC95 bootstrap de bloques | OK | 0 pesos fuera de su IC; `c_vivienda` IC_inf ≈ 0 (en ≥ 2,5 % de réplicas la variable es constante) |
| 6.1 | ponderacion | Fuzzificación recíprocos | **OK** | 1/3 → (1/4, 1/3, 1/2); 1/5 → (1/6, 1/5, 1/4); 9 → (8, 9, 9) |
| 6.2 | ponderacion | Buckley: media geométrica y división difusa (l/Σu, m/Σm, u/Σl), centroide | **OK** | Δ 0,0 vs cálculo independiente; δ = 0 reproduce la media geométrica nítida (1,4·10⁻¹⁷) |
| 6.3 | ponderacion | Chang: S_i, V(S_i ≥ S_k), mín | **OK** | Δ 0,0; matriz extrema → [1, 0, 0] (propiedad conocida de Chang) |
| 6.4 | ponderacion | CR de Saaty, RI | **OK** | [1,3,5;1/3,1,3;1/5,1/3,1]: λmáx 3,0385, CI 0,0193, CR 0,0332; RI = valores de Saaty (1980) n ≤ 15 |
| 6.5 | ponderacion | Validación de la matriz | ADVERTENCIA (D9) | acepta a_ij negativos (−2/−0,5) y a_ij = 12 (> 9); NaN → mensaje «debe ser recíproca» |
| 7.1 | indice | IVC = (Σw·c − 1)/4 | **OK** | Δ 0,0; rango 0,153‑0,750; vs tesis `ivc_ewm_total` < 1e‑9 (test) |
| 7.2 | indice | TOPSIS (norma vectorial, ideal fijo 5/1) | **OK** sin NaN | Δ 0,0 independiente; vs tesis 1,5·10⁻¹³ |
| 7.3 | indice | TOPSIS con un NaN | **ERROR** (D1) | un NaN en `c_oleaje` (fila 0) cambia el TOPSIS de 670/671 transectos (máx 0,70): la norma de la columna pasa de 113,7 a 1 |
| 7.4 | indice | Gornitz √(Πc/n) | OK | Δ 5·10⁻¹² |
| 8.1 | indice | ρ de Spearman (índice, −tasa) | **OK** | 0,61883 = scipy; tesis 0,61882 (`ivc_ewm_total`) y 0,5356 (estructural) |
| 8.2 | indice | κ ponderado cuadrático | **OK** | 0,353996 vs sklearn 0,353996 |
| 8.3 | indice | VIF | **OK** | Δ 0,0 vs regresión auxiliar; VIF constante → 1,0 (indefinido) |
| 8.4 | indice | Bloques contiguos | OK | 8 bloques de 79‑86 transectos; km constante → todo bloque 0 |
| 8.5 | indice | Sensibilidad y estabilidad con cortes del proyecto | **ERROR menor** (D3) | con cortes [0,1; 0,3; 0,5; 0,7] la sensibilidad y la estabilidad son idénticas a las de [0,2…0,8] |
| 8.6 | indice | Estabilidad con fila NaN | ERROR menor (D4) | 0,0 % en vez de NaN |
| 9.1 | proyeccion | Ventanas históricas y cobertura | OK | (1984,91‑2005,34), (2005,34‑2026,34); 0 intersecciones fuera; `tasa_ventana` cerrada ≡ `rasgos_ventana` semiabierta (Δ 2,5·10⁻¹⁴) |
| 9.2 | proyeccion | Bloques igual n y zona de exclusión 3 km | **OK** | 0 fugas: distancia mínima entrenamiento‑prueba 3,061 km en todos los bloques |
| 9.3 | proyeccion | R²_OS = 1 − SSE_mod/SSE_pers (fuera de bloque) | **OK** | 0,09994 = independiente; tesis +10,0 % (IC +1,0…+24,3; 7/8) vs geovisor +10,0 % (IC +1,0…+23,6; 7/8); β = (−0,3750, −0,9933) vs tesis (−0,3750, −0,9939) |
| 9.4 | proyeccion | OOF excluye realmente al bloque | OK | bloque 3 recalculado a mano: Δ 0,0 |
| 9.5 | proyeccion | Recursión: desplaz = Σ tasa·dur; tasaL = media [T−L, T] | **OK** (T ≥ ref+L) | Δ 0,0 para 2050 y 2100; tendencia centrada: media regional −4,1624 en todas las ventanas |
| 9.6 | proyeccion | `tasaL` con T − L < año de referencia | **ERROR** (D2) | horizonte 2030: tasaL = −0,73 frente a tasa W3 = −4,16 (= −4,16·3,66/21): el tramo observado [T−L, 2026] no se integra |
| 9.7 | proyeccion | Desplazamiento central vs tesis | **OK** | corr 1,0000 en 2050/2100; mediana \|Δ\| 1,3 m (β y n_mc) |
| 9.8 | proyeccion | Bandas MC vs tesis | ADVERTENCIA | anchura p95‑p05 2100: 946 m vs 1 016 m; σ_regional 1,0 (valor fijo por defecto) vs 1,308 de la tesis |
| 9.9 | proyeccion | Bruun R = E·ΔS·L*/(h*+B) | **OK** | cálculo manual (H12 4,3; T 9,5; d50 0,2 mm; SLR 0,81 m; 95 a) → w 0,0232 m/s, A 0,0971, h* 8,37 m, L* 801 m, ΔS neto 0,356 m, R 22,83 m = geovisor 22,83; SLR < ritmo histórico → 0 |
| 9.10 | proyeccion | IVC futuro: reclasificación por rol | **OK** | tasa = por_umbrales(tasaL); ancho = por_umbrales(ancho − ret); nivel_mar por escenario cambia en 560 transectos; % alta+muy alta 12,97/14,61/41,73/44,26 vs tesis sin Bruun 12,97/14,61/42,03/44,56 |
| 10.1 | proyecto | `exportar_todo` | ADVERTENCIA (M1) | 23 archivos, CRS 32618 correcto; faltan ρ entre variables, R²_OS por bloque, rasgos, tablas de % por categoría, consistencia FAHP, franjas, escenarios como GPKG, semilla/ventanas en `proyeccion_modelo.json` |
| 10.2 | proyecto | Serialización JSON | ADVERTENCIA | NaN de Python se escribe como `NaN` (JSON no estándar); numpy → OK |
| 10.3 | calculadora | Invalidación de pasos | **ERROR** (D10) | los cambios de parámetros (cortes, n_bloques, matriz FAHP, modelo, horizontes…) no invalidan los resultados; sólo lo hacen los cambios de archivo y los botones |
| 11.1 | varios | Fila toda NaN | OK | IVC, clase, Gornitz y su clase → NaN |
| 11.2 | varios | Columna de texto en clases | OK | ValueError explícito |
| 11.3 | varios | Una sola ventana histórica | OK | ValueError con L = 45 (serie de 41,4 años) |
| 11.4 | varios | L = 10 (4 ventanas) | ADVERTENCIA | σ_regional estimado 1,267 (bien), pero el modelo de transición sólo usa el último par de ventanas |

---

## (b) Defectos confirmados

### D1 · TOPSIS: un solo NaN anula la normalización vectorial de toda la columna — **impacto alto** (usuario con datos incompletos)
- **Dónde:** `src/calculo/indice.py:28‑30`
  ```python
  if nrm is None:
      nrm = np.sqrt((X ** 2).sum(0))
  nrm = np.where(nrm > 0, nrm, 1)
  ```
- **Qué pasa:** con cualquier NaN en una columna, `sum` devuelve NaN, `NaN > 0` es False y la norma se sustituye por 1. La columna deja de estar normalizada (valores 1‑5 frente a ~0,01‑0,04 en las demás) y domina la distancia a los ideales. Verificado: un NaN en `c_oleaje` cambia el TOPSIS de 670 de 671 transectos (máx 0,70); el IVC lineal no cambia.
- **Referencia:** Hwang y Yoon (1981): r_ij = x_ij / √Σ_i x_ij² sobre las alternativas válidas.
- **Corrección:**
  ```python
  if nrm is None:
      nrm = np.sqrt(np.nansum(X ** 2, 0))
  nrm = np.where(np.isfinite(nrm) & (nrm > 0), nrm, 1)
  ```
  (las filas con NaN siguen dando NaN, como el IVC lineal). Añadir un test con un NaN.

### D2 · `tasa_L` ignora el tramo observado cuando T − L < año de referencia — **impacto alto para horizontes cercanos (2030, 2040)**
- **Dónde:** `src/calculo/proyeccion.py:284‑288`
  ```python
  def tasa_L(R, T):
      tot = 0.0
      for i, (a, z) in enumerate(ventanas, start=1):
          tot = tot + R[i] * max(0, min(T, z) - max(a, T - L))
      return tot / L
  ```
- **Qué pasa:** la «tasa de los L años anteriores a T» (la que reclasifica `c_cambio_costa` en el IVC futuro) sólo integra ventanas futuras y divide por L. Para T = 2030 (ref 2026,34, L = 21) integra 3,66 años y divide por 21: tasaL = −0,73 m/a frente a −4,16 m/a (factor 3,66/21 exacto). La clase de tasa futura se vuelve «3» (estable) en casi toda la barra → el IVC 2030/2040 subestima la vulnerabilidad. `config.yaml` prevé horizontes 2030 y 2040 y la UI permite cualquier horizonte.
- **Corrección:** incluir la tasa observada actual (R[0] = r₀, común a central y MC) en el tramo [T − L, año_ref]:
  ```python
  def tasa_L(R, T):
      tot = R[0] * max(0.0, anio_ref - (T - L))          # tramo observado
      for i, (a, z) in enumerate(ventanas, start=1):
          tot = tot + R[i] * max(0, min(T, z) - max(a, T - L))
      return tot / L
  ```
  (Si se prefiere, usar la tasa LRR observada de los últimos (T−L…ref) años en lugar de r₀; r₀ es la LRR de la ventana completa.)

### D3 · Sensibilidad y estabilidad de clase usan cortes fijos (0,2…0,8) en vez de los del proyecto — **impacto medio**
- **Dónde:** `src/calculo/indice.py:112‑124` (`sensibilidad_pesos`: `clase_de_indice_01(base)`/`(v)` sin cortes) y `:127‑143` (`estabilidad_clase_bootstrap`, l. 134 y 142); llamadas en `src/calculo/proyecto.py:344‑345` sin pasar `cortes`.
- **Qué pasa:** con `p["indice"]["cortes"] = [0.1,0.3,0.5,0.7]` las tablas «% cambia de clase» y «estabilidad de la clase» son idénticas a las de los cortes por defecto, mientras `clase_ewm` sí usa los nuevos: métricas inconsistentes con el mapa mostrado.
- **Corrección:** añadir el parámetro `cortes=(0.2,0.4,0.6,0.8)` a ambas funciones, usarlo en las llamadas a `clase_de_indice_01`, y en `proyecto.py:344‑345` pasar `cortes`.

### D4 · Estabilidad de clase: 0 % para transectos con NaN — **impacto bajo**
- **Dónde:** `src/calculo/indice.py:138‑143` (`igual = np.zeros(len(X))`; `NaN == NaN` es False).
- **Corrección:** tras el bucle, `out = 100 * igual / n_boot; out[~ok] = np.nan; return out`.

### D5 · Incertidumbre 0 en una línea → se omite WLR en todo el transecto — **impacto bajo‑medio**
- **Dónde:** `src/calculo/transectos.py:179` (`.fillna(unc_defecto)` sólo cubre nulos) y `src/calculo/tasas.py:61‑62` (`w = 1/np.where(unc > 0, unc, nan)**2`; `if np.isfinite(w).all()` → se saltan WLR/WR2/WSE/WCI).
- **Por qué:** un peso 1/0² no es válido; DSAS aplica la incertidumbre por defecto a las líneas sin valor (y, según la guía de usuario, también a las de valor 0 — conviene confirmarlo en la guía v5/v6). Omitir todo el estimador ponderado por una sola línea es peor que sustituirla.
- **Corrección (transectos.py:179):**
  ```python
  u = pd.to_numeric(L[campo_unc], errors="coerce") if campo_unc and campo_unc in L else pd.Series(np.nan, index=L.index)
  L["_unc"] = u.where(u > 0).fillna(unc_defecto)
  ```

### D6 · `vector_categorico`: polígonos solapados inflan los porcentajes (> 100 %) y el solape se oculta — **impacto medio con capas de usuario**
- **Dónde:** `src/calculo/muestreo.py:162‑167` (`overlay` sin disolver; `tab["sin_dato"] = (100 - tab.sum(axis=1)).clip(lower=0)`).
- **Evidencia:** capa sintética con un polígono «C» superpuesto → suma de % = 200 %, `sin_dato` = 0.
- **Corrección:** disolver por categoría antes del cruce y exponer el solape en lugar de recortarlo:
  ```python
  g = g.dissolve(by=campo, as_index=False)          # elimina solapes dentro de una misma categoría
  ...
  tab["solape_pct"] = (tab.sum(axis=1) - 100).clip(lower=0)   # solape entre categorías distintas
  tab["sin_dato"] = (100 - tab.drop(columns="solape_pct").sum(axis=1)).clip(lower=0)
  ```
  y avisar en la UI si `solape_pct > 1`.

### D7 · `tabla_por_id` con ids duplicados: error críptico — **impacto bajo**
- **Dónde:** `src/calculo/muestreo.py:221` (`d.set_index(campo_id)[campo_valor]` → `reindex` falla con «cannot reindex on an axis with duplicate labels»).
- **Corrección:** `if d[campo_id].duplicated().any(): raise ValueError(f"La columna '{campo_id}' tiene ids repetidos")`.

### D8 · `pesos_ewm` sin guardas para columnas de suma 0 o todas constantes — **impacto bajo** (no alcanzable desde las normalizaciones actuales; sí desde el uso directo de la función)
- **Dónde:** `src/calculo/ponderacion.py:25‑31`.
- **Evidencia:** `[x, 0, 1]` → pesos [0,069, 0,931, 0] (la constante 0 recibe el máximo peso porque 0/0 → NaN → e = 0 → d = 1); todas constantes → [0,5, 0,5] en vez de error/NaN.
- **Corrección:**
  ```python
  s = X.sum(0)
  p = np.divide(X, s, out=np.zeros_like(X), where=s > 0)
  e = ...; d = 1 - e; d[s <= 0] = 0.0
  if d.sum() <= 0: raise ValueError("Todas las variables son constantes: la entropía no define pesos")
  ```

### D9 · `matriz_saaty_valida` no comprueba rango ni signo — **impacto bajo**
- **Dónde:** `src/calculo/ponderacion.py:64‑72`. Acepta a_ij = −2 / −0,5 (producto 1) y a_ij = 12; con NaN devuelve «La matriz debe ser recíproca».
- **Corrección:** añadir `if not np.isfinite(A).all(): raise ValueError("La matriz tiene celdas vacías")` y `if (A <= 0).any() or (A > 9).any() or (A < 1/9).any(): raise ValueError("Juicios fuera de la escala de Saaty (1/9 … 9)")`.

### D10 · UI: los cambios de parámetros no invalidan los resultados posteriores — **impacto medio (trazabilidad)**
- **Dónde:** `src/paginas/calculadora.py` — `_invalidar` (l. 59‑63) sólo se llama al cambiar archivos (l. 103, 278, 313, 326, 345), al editar variables (l. 637) y al pulsar los botones (l. 380, 665, 781, 835, 953). Los widgets de cortes (l. 819‑823), tasa de validación (l. 827), n_bloques (l. 829), matriz FAHP/δ/método (l. 743‑771), pesos manuales (l. 773‑777), ventana/horizontes/modelo/n_mc/buffer/escenarios/Bruun (l. 910‑950) modifican `p` sin tocar `res`.
- **Qué pasa:** tras cambiar, p. ej., los cortes, `res["indice"]` sigue mostrando y exportando el índice calculado con los cortes anteriores, y `exportar_todo` escribe un `proyecto.json` que no corresponde a los CSV/GPKG exportados.
- **Corrección:** guardar en cada `res[paso]` una «firma» (hash JSON de la sección de `p` que le afecta) al calcular y, en cada render, si la firma actual difiere, llamar a `_invalidar(res, paso)` o marcar el paso como «desactualizado» y bloquear la exportación hasta recalcular.

---

## (c) Advertencias y limitaciones (no son errores)

1. **σ_regional por defecto = 1,0 m/año** (`proyeccion.py:237`, `proyecto.py:366‑368` sólo estima con ≥ 3 ventanas). La tesis usó 1,308 (desviación de ΔL medio entre 4 ventanas de la validación temporal); con L = 21 sólo hay 2 ventanas y el valor 1,0 no está justificado por los datos → bandas 2100 un 7 % más estrechas (946 vs 1 016 m). Conviene exponerlo en la UI con el valor de la tesis como defecto documentado.
2. **Monte Carlo con desplazamiento circular fijo por realización** (`proyeccion.py:241, 266`): el mismo campo de residuos se suma en cada ventana → error perfectamente persistente (acumulación lineal). Reproduce fielmente la tesis (`proyeccion_modelos.py:211‑215`, decisión explícita y conservadora), pero el `configuracion_proyeccion.json` de la tesis lo describe como «aleatorio por paso»; documentar la elección en el geovisor.
3. **Con más de 2 ventanas el modelo de transición sólo usa el último par** (`proyecto.py:364`, `H[-2] → H[-1]`); con L = 10 se desaprovechan 3 transiciones (n podría pasar de 671 a ~2 000).
4. **Rasgos en pasos ≥ 2 de la recursión** (`proyeccion.py:254‑258`): tasa_10 = tasa, aceleración = 0, variabilidad fija — aproximación heredada de la tesis; sólo afecta a ridge/rf.
5. **`rol="H12"` asignado a Hs p95** (`ejemplos.py:40`; plantilla de la UI `calculadora.py:493`). Si se activa Bruun, h* de Hallermeier se calcularía con Hs p95 (~3,0 m) en vez de H12 (4,3 m) → h* y L* subestimados. En el ejemplo Bruun está desactivado.
6. **Validación circular**: `ivc_ewm` incluye la tasa; se marca «circular: sí» y se ofrece `ivc_ewm_estructural` (ρ 0,536). El valor p de `spearmanr` asume independencia espacial; sólo el IC por bloques es defendible.
7. **Estadísticos zonales por malla de puntos (10 m)**, no por ponderación exacta de área (`muestreo.py:45‑51, 111‑123`): sesgo ≈ ±media celda y submuestreo de rásteres < 10 m (en el DEM de 5 m la mediana dio 97,5 vs 100). El paso de 10 m no se expone en `distribuir_variable`. Igual que la tesis.
8. **`pct_bajo` excluye NoData del denominador**: correcto para DeltaDTM (mar = NoData) pero sobreestima el % si el ráster tiene huecos en tierra. En la proyección el umbral es el SLR absoluto respecto del datum del DEM (`proyecto.py:415‑416`), válido sólo si el datum ≈ nivel medio del mar del periodo base.
9. **`ancho_barra`** mide desde P0 aunque P0 esté en el agua (310 m en vez de 260 m en el caso sintético) y con resolución del paso (±10 m); la censura «minimo» no se propaga a la clase ni al IVC futuro (`ivc_futuro` resta el retroceso también a anchos censurados; la tesis lo evitaba «si el transecto no estaba en la clase 5 censurada»).
10. **Semánticas distintas de `filtro`**: lista de categorías a excluir en `vector_categorico` (`proyecto.py:177`) y expresión pandas en `distancia_a` (l. 184); la UI lo distingue (l. 582‑585) pero el JSON no.
11. **`tasa_validacion: 'ventana'`** documentado en `proyecto.py:12` no está implementado (l. 316 sólo acepta columnas de `t`); la UI ofrece LRR/EPR/WLR.
12. **Año decimal = año + día/365** (DSAS): no monótono en el 31‑dic de años bisiestos; irrelevante con líneas anuales.
13. **`difusa_01` constante → 0,5** y **`directa` con todo NaN** no avisan; `VIF` de una constante devuelve 1,0.
14. **Diferencias residuales con la tesis** en escenarios 2100 (41,73 vs 42,03 % alta+muy alta sin Bruun; 2 transectos): SLR por defecto 330/350/810/1030 mm frente a 325/350/794/1009 mm de la tesis y tratamiento de la censura del ancho.
15. **`proyeccion_modelo.json`** no guarda semilla, ventanas, n_mc, σ_regional ni R²_OS por bloque (sí está en memoria), lo que dificulta reproducir la corrida.

---

## (d) Qué falta frente a un flujo CVI completo (y frente a la propia tesis)

| Componente | Estado | Comentario |
|---|---|---|
| Sensibilidad por exclusión de variables (leave‑one‑out / jackknife) | **Falta** | sólo perturbación de pesos ±10/20 %; la tesis añadió Sobol (SALib) |
| Índices de Sobol | Falta | en la tesis (`sensibilidad_sobol.csv`) |
| TOPSIS con ideal relativo | Función existe (`absoluto=False`) pero `paso_indice` no lo calcula | la tesis reporta ambos |
| Bootstrap iid de los pesos EWM (además del de bloques) | Falta | la tesis reporta ambos IC |
| Validación por bloque (ρ por bloque) | Falta | `validacion_por_bloque.csv` en la tesis |
| Escenarios con IC de la tasa (LRR ± LCI95) | Falta | la tesis da p05/p95 del % alta+muy alta por MC y por LCI95 |
| Retrospectiva por ventanas (IVC 2005 reconstruido, diferencias con IC) | Parcial | `tasa_ventana` existe, pero no hay reclasificación retrospectiva del IVC |
| Priorización de infraestructura (año en que la costa alcanza la Ruta 90, con IC) | Falta | producto clave de la tesis para la toma de decisiones |
| Intervalo conformal / modelos ML apilados (RF, Ridge, CNN‑LSTM, stacking) | Falta | el geovisor sólo cubre persistencia/amortiguada/ridge/rf como Δ de tasa |
| Exportación de figuras (mapas, barras de pesos, dispersión Δ obs‑pred) | Falta | `exportar_todo` sólo escribe tablas/GPKG |
| Exportación de la matriz ρ, R²_OS por bloque, rasgos, % por categoría, franjas, escenarios como GPKG, metadatos de la corrida | Falta | ver 10.1 |
| Pruebas unitarias de casos límite (NaN en TOPSIS, cortes no estándar, horizontes cercanos, polígonos solapados) | Faltan | los 6 tests actuales sólo cubren la reproducción de la tesis |
| Pesos FAHP reales (panel de expertos) | Pendiente en la tesis | el motor está listo y verificado (Buckley/Chang/CR) |

---

### Resumen ejecutivo
El motor reproduce DSAS v6.1 y los resultados de la tesis con error numérico de máquina, y las fórmulas de EWM, FAHP (Buckley/Chang, fuzzificación de recíprocos, CR), Spearman con bootstrap de bloques, κ, VIF, R²_OS con exclusión espacial y la regla de Bruun están implementadas correctamente. Los defectos que conviene corregir antes de usar la calculadora con datos distintos de los de la tesis son **D1 (TOPSIS con NaN)**, **D2 (tasaL para horizontes a menos de L años)** y **D10 (invalidación de resultados en la UI)**; D3‑D9 son robustez y mensajes. Los scripts de verificación permiten reutilizarse como pruebas de regresión.


---

## Correcciones aplicadas (25‑10‑2026)

| Defecto | Archivo | Cambio | Justificación | Prueba |
|---|---|---|---|---|
| D1 TOPSIS con NaN | `src/calculo/indice.py` (`topsis`) | norma vectorial con `np.nansum` sobre las filas válidas; norma no finita → 1 | Hwang y Yoon (1981): r_ij = x_ij/√Σx_ij² sobre las alternativas válidas; un NaN no debe desnormalizar la columna | `test_d1_topsis_con_nan_no_altera_el_resto` |
| D2 tasaL con T − L < año_ref | `src/calculo/proyeccion.py` (`tasa_L`) | el tramo observado [T−L, año_ref] se integra con la tasa actual R[0] | la variable «tasa de los L años previos» debe cubrir L años; antes dividía un tramo corto por L (factor 3,66/21 en 2030) | `test_d2_tasa_L_incluye_el_tramo_observado` |
| D3 cortes fijos en sensibilidad/estabilidad | `indice.py` (`sensibilidad_pesos`, `estabilidad_clase_bootstrap`), `proyecto.py` (`paso_indice`) | parámetro `cortes` propagado desde `p["indice"]["cortes"]` | coherencia entre el mapa de clases y las métricas de sensibilidad | `test_d3_…` |
| D4 estabilidad 0 % con NaN | `indice.py` | `NaN` para transectos sin dato | 0 % sería un dato falso | `test_d4_…` |
| D5 incertidumbre 0 | `transectos.py` (`intersecciones`) | `u.where(u > 0).fillna(unc_defecto)` | 1/0² no es un peso válido; DSAS aplica el valor por defecto a líneas sin incertidumbre | `test_d5_…` |
| D6 polígonos solapados | `muestreo.py` (`vector_categorico`) | `dissolve` por categoría; columna `solape_pct`; `excluir` sin distinción de mayúsculas | evita porcentajes > 100 % y expone el solape entre categorías | `test_d6_…` |
| D7 ids repetidos | `muestreo.py` (`tabla_por_id`) | `ValueError` explícito con los ids repetidos | mensaje útil en lugar del error interno de pandas | `test_d7_…` |
| D8 EWM con columnas constantes | `ponderacion.py` (`pesos_ewm`) | división segura; constante ⇒ peso 0; todas constantes ⇒ `ValueError` | por definición una variable sin dispersión no aporta información (d_j = 0) | `test_d8_…` |
| D9 validación de la matriz de Saaty | `ponderacion.py` (`matriz_saaty_valida`) | rechaza vacíos, negativos y juicios fuera de 1/9…9 | escala fundamental de Saaty (1980) | `test_d9_…` |
| D10 parámetros cambiados sin recalcular | `src/paginas/calculadora.py` | huella MD5 de las secciones del proyecto que determinan cada paso (`_firma`, `_sellar`, `_comprobar_vigencia`); si cambia, el paso y los posteriores se descartan y se avisa | trazabilidad: lo exportado corresponde siempre a `proyecto.json` | verificación manual en la interfaz |

**Advertencias atendidas**

* (c)1 σ_regional: el ejemplo de la tesis fija `sigma_regional = 1,308 m/año` (valor de la validación temporal de la tesis); en proyectos nuevos se estima de las ventanas (≥ 3) y, si no es posible, se usa 1,0 y la interfaz lo indica.
* (c)5 rol H12: se retiró el rol `H12` de la variable «Oleaje Hs p95» (ejemplo y plantilla); Bruun usa el parámetro explícito `H12_m`.
* (c)14 escenarios SLR: los valores por defecto pasan a 325/350/794/1009 mm (medianas AR6 usadas en la tesis).
* (c)15 metadatos: `proyeccion_modelo.json` incluye ahora los parámetros de la proyección (semilla, ventana, horizontes, n_mc, σ usado) y las ventanas históricas; se exportan además `proyeccion_r2os_por_bloque.csv`, `validacion_por_bloque.csv`, `redundancia_spearman.csv` y los escenarios como GeoPackage.
* (d) añadidos: TOPSIS con ideal relativo (`ivc_topsis_rel_ewm`), ρ por bloque espacial (`validacion_bloques`), IC95 iid de los pesos EWM (`IC95_iid_*`) junto al de bloques, sensibilidad por exclusión de cada variable (fila «excluida» en `sensibilidad_pesos`), 10 pruebas de casos límite.

**Pendiente (fuera del alcance de la calculadora genérica, disponible en los módulos de la tesis del geovisor):** índices de Sobol, modelos apilados (RF/Ridge/CNN‑LSTM/stacking) e intervalos conformales, priorización de la Ruta 90 con IC, exportación de figuras desde la aplicación (los PNG se generan con `scripts/generar_pruebas_calculadora.py`).
