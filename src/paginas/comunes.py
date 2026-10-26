"""Componentes compartidos por las páginas (KPIs con icono, paneles, estados vacíos, descargas, mapa)."""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .. import exportaciones
from ..estilos import AMBAR, AZUL, CORAL, GRIS, MARCA_OLAS, OLA_SUBRAYADO, TEAL, icono, sparkline

_COLOR_IC = {"azul": AZUL, "teal": TEAL, "coral": CORAL, "ambar": AMBAR, "gris": GRIS}


def tema() -> str:
    return st.session_state.get("tema", "claro")


def cifra(valor: str, etiqueta: str) -> None:
    st.markdown(f'<div class="gv-big"><div class="n">{valor}</div><div class="l">{etiqueta}</div></div>', unsafe_allow_html=True)


def panel(titulo: str, ic: str = "capas", sub: str = "") -> None:
    st.markdown(f'<div class="gv-panel"><div class="ic">{icono(ic)}</div><div><h4>{titulo}</h4>{f"<small>{sub}</small>" if sub else ""}</div>{MARCA_OLAS}</div>', unsafe_allow_html=True)


def seccion(titulo: str, ic: str, sub: str = "") -> None:
    st.markdown(f'<div class="gv-seccion"><div class="ic">{icono(ic, "#fff")}</div><div><h3>{titulo}</h3><p>{sub}</p>{OLA_SUBRAYADO}</div></div>', unsafe_allow_html=True)


def kpi(etiqueta: str, valor, unidad: str = "", ayuda: str = "", decimales: int = 1, procedencia: str | None = None,
        ic: str = "grafico", tono: str = "azul", serie=None, progreso: float | None = None, mostrar_vacio: bool = False) -> bool:
    """Tarjeta KPI: icono, valor, unidad, procedencia; opcional sparkline (serie) o barra de progreso (0‑1).

    Sin dato la tarjeta se omite (se devuelve False) para no mostrar «No disponible»; con ``mostrar_vacio=True`` se dibuja
    igualmente con esa leyenda. Nunca se muestran ceros en lugar del dato ausente.
    """
    sin_dato = valor is None or (isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor))) or valor == ""
    if sin_dato and not mostrar_vacio:
        return False
    if sin_dato:
        v, u, clase_v, tono = '<span class="nd">No disponible</span>', "", "", "gris"
    else:
        clase_v = ""
        if isinstance(valor, int) and not isinstance(valor, bool):
            v = f"{valor:,}".replace(",", " ")
        elif isinstance(valor, float):
            v = f"{valor:,.{decimales}f}".replace(",", " ")
        else:
            v = str(valor)
            if len(v) > 22:
                clase_v = " largo"
        u = f'<span class="u">{unidad}</span>' if unidad else ""
    proc = f'<span class="gv-proc {procedencia.lower()}">{procedencia}</span>' if procedencia else ""
    extra = ""
    if serie is not None and not sin_dato:
        extra = sparkline(serie, _COLOR_IC.get(tono, AZUL))
    barra = f'<div class="barra" style="--w:{max(0.0, min(1.0, progreso)) * 100:.0f}%"></div>' if progreso is not None and not sin_dato else ""
    st.markdown(
        f'<div class="gv-kpi" title="{ayuda}"><div class="ic {tono}">{icono(ic, _COLOR_IC.get(tono, AZUL))}</div>'
        f'<div class="tx"><span class="l">{etiqueta}{proc}</span><span class="v{clase_v}">{v}{u}</span></div>{extra}{barra}{MARCA_OLAS}</div>',
        unsafe_allow_html=True,
    )
    return not sin_dato


def vacio(titulo: str, detalle: str = "", ic: str = "info") -> None:
    st.markdown(f'<div class="gv-vacio">{icono(ic, AMBAR)}<div><b>{titulo}</b>{detalle}</div></div>', unsafe_allow_html=True)


def hueco_etiqueta() -> None:
    """Espacio equivalente a la etiqueta de un campo, para alinear botones/toggles con campos etiquetados de la misma fila."""
    st.markdown('<div class="gv-hueco"></div>', unsafe_allow_html=True)


def nota(texto: str, abierta: bool = False) -> None:
    """Nota explicativa plegada: se muestra solo un pequeño «ⓘ» y el texto aparece al pulsarlo (o pasar el cursor)."""
    if not texto:
        return
    titulo = texto.replace('"', "&quot;")
    abierto = " open" if abierta else ""
    st.markdown(f'<details class="gv-nota"{abierto}><summary title="{titulo}">ⓘ</summary><div>{texto}</div></details>', unsafe_allow_html=True)


def mostrar_mapa(m, altura: int = 640, clave: str = "mapa", vista: tuple | None = None, capas: list | None = None, control_capas: bool = True) -> dict:
    """Dibuja el mapa sin devolver eventos (evita re‑ejecuciones al desplazarse).

    * ``vista`` = ((lat, lon), zoom) mueve la vista en esta ejecución (sector, «Encuadrar», «Restablecer»).
    * ``capas`` = lista de ``folium.FeatureGroup`` con las capas dinámicas. streamlit-folium conserva el mapa base ya
      dibujado (misma ``clave``) y solo sustituye esas capas, de modo que al cambiar de fecha o activar capas no hay
      recarga del mapa (sin parpadeo) y el encuadre del usuario se mantiene.
    """
    import folium

    kw = {}
    if vista:
        (lat, lon), zoom = vista
        kw = {"center": (float(lat), float(lon)), "zoom": int(zoom)}
    if capas is not None:
        kw["feature_group_to_add"] = capas or None
        if control_capas:
            kw["layer_control"] = folium.LayerControl(position="topright", collapsed=True)
    return st_folium(m, height=altura, use_container_width=True, returned_objects=[], key=clave, **kw)

def descargas(g: gpd.GeoDataFrame | pd.DataFrame | None, nombre: str, cfg: dict, clave: str, formatos: tuple = ("geojson", "gpkg", "csv")) -> None:
    """Botones de descarga. Las geometrías se exportan sin simplificar y con sus atributos originales."""
    if g is None or len(g) == 0:
        nota("Nada que exportar.")
        return
    es_geo = isinstance(g, gpd.GeoDataFrame) and "geometry" in g.columns
    cols = st.columns(len(formatos))
    i = 0
    if es_geo and "geojson" in formatos:
        with cols[i]:
            if st.button("⬇ GeoJSON", key=f"{clave}_bgj", help="EPSG:4326 (RFC 7946)", use_container_width=True):
                datos, archivo, crs = exportaciones.exportar_geojson(g, nombre, cfg)
                st.download_button(f"Descargar {archivo}", datos, archivo, "application/geo+json", key=f"{clave}_dgj", use_container_width=True)
                nota(f"CRS exportado: {crs}. Copia guardada en resultados/exportaciones.")
        i += 1
    if es_geo and "gpkg" in formatos:
        with cols[i]:
            if st.button("⬇ GeoPackage", key=f"{clave}_bgp", help="Conserva el CRS original", use_container_width=True):
                datos, archivo, crs = exportaciones.exportar_gpkg(g, nombre, cfg)
                st.download_button(f"Descargar {archivo}", datos, archivo, "application/geopackage+sqlite3", key=f"{clave}_dgp", use_container_width=True)
                nota(f"CRS exportado: {crs}.")
        i += 1
    if "csv" in formatos:
        with cols[min(i, len(cols) - 1)]:
            if st.button("⬇ CSV", key=f"{clave}_bcs", use_container_width=True):
                datos, archivo, crs = exportaciones.exportar_csv(g, nombre, cfg, con_wkt=es_geo)
                st.download_button(f"Descargar {archivo}", datos, archivo, "text/csv", key=f"{clave}_dcs", use_container_width=True)
                nota(f"Atributos{' + WKT en ' + crs if crs else ''}.")


def _celda(v, dec: int | None):
    """Formato de una celda para la tabla HTML: booleanos como insignia, vacíos como «—», números con separador de miles."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "") or str(v) == "NaT":
        return '<span class="vacio">—</span>'
    if isinstance(v, (bool, np.bool_)):
        return '<span class="si">✓</span>' if v else '<span class="no">✕</span>'
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}".replace(",", " ")
    if isinstance(v, (float, np.floating)):
        if dec is not None:
            t = f"{float(v):,.{dec}f}"
        else:
            t = f"{float(v):,.4f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{float(v):,.0f}"
        return t.replace(",", " ")
    t = str(v)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return t


def tabla(df, hide_index: bool = True, height: int | None = None, use_container_width: bool = True, decimales: int | None = None,
          max_filas: int = 1500, **_kw) -> None:
    """Tabla HTML con el estilo del geovisor (Manrope, cabecera gris, filas alternas, modo oscuro) en lugar de st.dataframe.

    Acepta los mismos argumentos de ``st.dataframe`` (hide_index, height, use_container_width) para sustituirlo sin cambios.
    ``height`` fija la altura máxima con desplazamiento interno; sin él la tabla crece hasta ~520 px.
    """
    d = df
    if hasattr(d, "to_frame") and not hasattr(d, "columns"):
        d = d.to_frame()
    d = pd.DataFrame(d)
    if "geometry" in d.columns:
        d = d.drop(columns="geometry")
    n_total = len(d)
    d = d.head(max_filas)
    if not hide_index and not isinstance(d.index, pd.RangeIndex):
        d = d.reset_index()
    num_cols = [pd.api.types.is_numeric_dtype(d[c]) and not pd.api.types.is_bool_dtype(d[c]) for c in d.columns]
    cls = [' class="num"' if n else "" for n in num_cols]
    cabecera = "".join(f"<th{cls[j]}>{_celda(c, None)}</th>" for j, c in enumerate(d.columns))
    filas = []
    for fila in d.itertuples(index=False, name=None):
        filas.append("<tr>" + "".join(f"<td{cls[j]}>{_celda(v, decimales)}</td>" for j, v in enumerate(fila)) + "</tr>")
    alto = f"max-height:{int(height)}px;" if height else "max-height:520px;"
    pie = f'<div class="gv-tabla-pie">{min(n_total, max_filas):,} de {n_total:,} filas</div>'.replace(",", " ") if n_total > max_filas else ""
    st.markdown(f'<div class="gv-tabla" style="{alto}"><table><thead><tr>{cabecera}</tr></thead><tbody>{"".join(filas)}</tbody></table></div>{pie}', unsafe_allow_html=True)


def tabla_atributos(g: gpd.GeoDataFrame | pd.DataFrame, max_filas: int = 500) -> None:
    d = pd.DataFrame(g.drop(columns="geometry")) if "geometry" in getattr(g, "columns", []) else pd.DataFrame(g)
    tabla(d.head(max_filas), height=min(400, 44 + 34 * min(len(d), 12)))
    if len(d) > max_filas:
        nota(f"Se muestran {max_filas} de {len(d)} filas.")


def procedencia_html(texto: str, tipo: str = "") -> str:
    return f'<span class="gv-proc {tipo}">{texto}</span>'


CONFIG_PLOTLY = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"], "responsive": True}


def grafico_en(contenedor, fig, clave: str | None = None) -> None:
    with contenedor:
        grafico(fig, clave)


def grafico(fig, clave: str | None = None) -> None:
    from .. import graficos as _g

    _g.aplicar_tema(fig, tema())
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY, key=clave)
