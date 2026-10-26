"""Sección 7 — Datos y metodología: catálogo, procedencia, CRS, estado de módulos y regeneración del inventario."""
from __future__ import annotations

import platform
import sys

import pandas as pd
import streamlit as st

from .. import inventario
from ..catalogo_datos import CAPAS, estado_modulos
from ..configuracion import RAIZ_GEOVISOR, ocultar_ruta, ruta as ruta_cfg, rutas_salida
from . import comunes as ui


def render(cfg: dict) -> None:
    ui.seccion("Datos y metodología", "db", "catálogo de archivos, procedencia de cada capa, CRS y flujo metodológico")
    tabs = st.tabs(["Capas y procedencia", "Catálogo de archivos", "Metodología", "Entorno y configuración", "Publicación"])

    with tabs[0]:
        filas = []
        for c in CAPAS.values():
            p = c.ruta(cfg)
            ok = p.exists()
            filas.append({"estado": "✅" if ok else "—", "grupo": c.grupo, "capa": c.titulo, "formato": c.formato + (f" · {c.capa}" if c.capa else ""),
                          "procedencia": c.procedencia, "archivo": ocultar_ruta(p, cfg), "modificado": pd.Timestamp(p.stat().st_mtime, unit="s").strftime("%Y-%m-%d") if ok else "no disponible"})
        df = pd.DataFrame(filas).sort_values(["grupo", "capa"])
        ui.tabla(df, hide_index=True, use_container_width=True, height=520)
        mods = estado_modulos(cfg)
        st.markdown("**Estado de los módulos**: " + " · ".join(f"{'🟢' if v['ok'] else '🔴'} {k} ({v['detalle']})" for k, v in mods.items()))
        with st.expander("Descripción y campos de cada capa"):
            for c in CAPAS.values():
                if c.descripcion or c.campos:
                    st.markdown(f"**{c.titulo}** — {c.descripcion} {'Campos: `' + '`, `'.join(c.campos) + '`' if c.campos else ''} {('Unidades: ' + c.unidades) if c.unidades else ''}")

    with tabs[1]:
        carpeta = ruta_cfg(cfg, "catalogo")
        cat = inventario.cargar_catalogo(carpeta)
        c1, c2 = st.columns([3, 1])
        with c2:
            incluir_data = st.checkbox("Incluir escenas Landsat (data/)", value=True, help="Recorre data/<sitio>/<sensor>/ms sin abrir los GeoTIFF; puede tardar unos segundos con miles de escenas.")
            if st.button("Generar / actualizar catálogo", use_container_width=True, type="primary"):
                raices = {k: ruta_cfg(cfg, k) for k in ("exportar_coastsat", "resultados_tesis")}
                if incluir_data:
                    raices["coastsat_data"] = ruta_cfg(cfg, "coastsat_data")
                with st.spinner("Inspeccionando archivos (solo cabeceras)…"):
                    ent = inventario.inventariar(raices)
                    inventario.guardar_catalogo(ent, carpeta)
                st.cache_data.clear()
                st.success(f"Catálogo generado: {len(ent)} archivos.")
                st.rerun()
        with c1:
            if cat is None:
                ui.vacio("Catálogo no generado", "Pulse «Generar / actualizar catálogo». Se escribirá en resultados/catalogo (CSV y JSON).")
            else:
                res = inventario.resumen_catalogo(cat)
                ui.nota(f"Generado: {cat.attrs.get('generado')} · {res.get('n_total')} archivos · {res.get('tamano_total_gb')} GB · por categoría: {res.get('por_categoria')} · por EPSG: {res.get('por_epsg')}")
                if res.get("escenas_por_satelite"):
                    ui.nota(f"Escenas Landsat (ms): {res['escenas_por_satelite']} · {res.get('escenas_fecha_min')} → {res.get('escenas_fecha_max')} · sitios: {len(res.get('escenas_por_sitio', {}))}")
                filtro = st.multiselect("Categoría", sorted(cat["categoria"].unique()), default=[c for c in sorted(cat["categoria"].unique()) if c != "escena_landsat"], key="cat_filtro")
                d = cat[cat["categoria"].isin(filtro)].copy()
                d["archivo"] = d["ruta"].apply(lambda r: ocultar_ruta(r, cfg))
                cols = ["categoria", "archivo", "epsg", "tipo_geometria", "n_entidades", "capas", "atributos", "fechas_nombre", "anios_nombre", "tamano_bytes", "modificado", "error"]
                ui.tabla(d[[c for c in cols if c in d.columns]], hide_index=True, use_container_width=True, height=480)
                st.download_button("Descargar catálogo (CSV)", (carpeta / "catalogo_datos.csv").read_bytes() if (carpeta / "catalogo_datos.csv").exists() else b"", "catalogo_datos.csv", "text/csv")

    with tabs[2]:
        st.markdown(
            """
**Flujo de datos del geovisor** (ningún paso modifica los archivos originales):

1. **Extracción de líneas de costa** — CoastSat 2.x sobre Landsat 5/7/8/9 (1984‑2026), cuatro sectores (s01‑s04), EPSG:32618. Postproceso propio (`coastsat_postproceso.py`): unión de sectores, limpieza, corrección por marea con pendiente de playa y líneas anuales por mediana (`exportar_coastsat/postproceso`).
2. **Tasas de cambio** — DSAS v6.1.177 (USGS) sobre las 38 líneas anuales corregidas por marea; 671 transectos cada 100 m; EPR, LRR, WLR, NSM y SCE con IC95 (`exportar_coastsat/dsas`). El geovisor muestra estos valores sin recalcularlos y los distingue de las tasas del script (`tasas_transectos_*`).
3. **Variables del IVC** — 15 variables (geomorfológicas, geotécnicas, oceanográficas, ambientales, de infraestructura y socioeconómicas) muestreadas en franjas de 0‑500 m por transecto y clasificadas 1‑5 con umbrales publicados (`ivc/tabla_clases_1_5_ivc.csv`, `diccionario_variables_ivc.csv`).
4. **IVC** — ponderación objetiva por entropía (EWM) como esquema principal; FAHP pendiente del panel de expertos. IVC = Σ w·c en 1‑5 → (IVC−1)/4 en 0‑1 → clases por intervalos iguales de 0,2. Versiones alternativas (TOPSIS‑EWM, pesos iguales, CVI de Gornitz) y por fecha/modelo (`Mapas_IVC/ivc_versiones.py`, `QGIS_IVC`).
5. **Modelos IVC‑ML (v4)** — objetivo Δ = LRR 2005‑2026 − LRR 1984‑2005; bases Ridge, Random Forest, CNN‑LSTM, LSTM; apilamiento NNLS; validación anidada en 8 bloques espaciales con exclusión de 3 km; IC95 por bootstrap (`Modelos/06_Validacion_anidada`).
6. **Proyecciones** — persistencia amortiguada / Ridge con Monte Carlo (2000 réplicas) para 2050 y 2100; escenarios SSP2‑4.5 y SSP5‑8.5 (nivel del mar AR6 por celda, reducción del ancho de barra); regla de Bruun (`Modelos/07_Proyecciones`, `Multicriterio`).

**Sistemas de referencia**: métrico EPSG:32618 (WGS 84 / UTM 18N) para longitudes, áreas y simplificación; visualización EPSG:4326 (exigido por Leaflet). Las capas fuente de INVEMAR/DANE (EPSG:3857 y 4170) se reproyectan al vuelo a partir del CRS declarado en su archivo.

**Lo que el geovisor NO hace**: no calcula un IVC propio, no extrapola tasas al futuro, no interpola líneas entre fechas ni entre horizontes, no simula salidas de modelos. Donde falta un resultado muestra «No disponible».
            """
        )

    with tabs[3]:
        salidas = rutas_salida(cfg)
        info = {
            "Python": sys.version.split()[0], "Sistema": f"{platform.system()} {platform.release()}",
            "Carpeta del geovisor": ocultar_ruta(RAIZ_GEOVISOR, cfg), "Configuración": cfg.get("_meta", {}),
            "Salidas": {k: ocultar_ruta(v, cfg) for k, v in salidas.items()},
            "CRS": cfg["crs"], "Caché": cfg["cache"], "Clasificación IVC": {"método": cfg["ivc"]["metodo_clasificacion"], "cortes_0_1": cfg["ivc"]["cortes"], "cortes_1_5": cfg["ivc"]["cortes_1_5"]},
        }
        try:
            import folium, geopandas, plotly, rasterio, shapely, streamlit  # noqa: E401

            info["Paquetes"] = {"streamlit": streamlit.__version__, "geopandas": geopandas.__version__, "shapely": shapely.__version__, "rasterio": rasterio.__version__, "folium": folium.__version__, "plotly": plotly.__version__}
        except Exception as e:  # noqa: BLE001
            info["Paquetes"] = str(e)
        st.json(info)
        ui.nota("Las rutas privadas se muestran con alias ([CoastSat], [Resultados tesis]) para no exponerlas en una versión pública.")
        if st.button("Vaciar caché en memoria"):
            st.cache_data.clear()
            st.success("Caché vaciada.")

    with tabs[4]:
        st.markdown(open(RAIZ_GEOVISOR / "README.md", encoding="utf-8").read().split("## Publicación")[1] if (RAIZ_GEOVISOR / "README.md").exists() and "## Publicación" in open(RAIZ_GEOVISOR / "README.md", encoding="utf-8").read() else "Véase README.md.")
