"""Construcción del mapa interactivo (Folium/Leaflet)."""
from __future__ import annotations

from typing import Iterable

import branca.colormap as cm
import folium
from folium import plugins

from .rasteres import Superposicion


def vista_para_bounds(bounds: list, ancho_px: int = 800, alto_px: int = 640, zoom_max: int = 18) -> tuple[tuple[float, float], int]:
    """Centro y nivel de zoom (Web Mercator, teselas de 256 px) que encuadran ``bounds`` = [[lat_min, lon_min], [lat_max, lon_max]].

    streamlit-folium conserva el mapa ya dibujado y solo cambia la vista mediante los parámetros ``center``/``zoom``
    (los ``fit_bounds`` del HTML solo actúan en la primera carga), de ahí que haga falta este cálculo.
    """
    import math

    (lat0, lon0), (lat1, lon1) = bounds
    centro = ((lat0 + lat1) / 2, (lon0 + lon1) / 2)

    def _y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    dlon = max(abs(lon1 - lon0), 1e-6)
    dy = max(abs(_y(lat1) - _y(lat0)), 1e-9)
    z_lon = math.log2(360.0 * ancho_px / (256.0 * dlon))
    z_lat = math.log2(2 * math.pi * alto_px / (256.0 * dy))
    zoom = int(math.floor(min(z_lon, z_lat) - 0.1))
    return centro, max(1, min(zoom_max, zoom))


def crear_mapa(cfg: dict, bounds: list | None = None, mapa_base: str | None = None, altura: int = 640) -> folium.Map:
    mc = cfg["mapa"]
    base_defecto = mapa_base or mc.get("mapa_base_defecto")
    m = folium.Map(
        location=[mc["centro"][1], mc["centro"][0]], zoom_start=mc.get("zoom_inicial", 11),
        min_zoom=mc.get("zoom_min", 7), max_zoom=mc.get("zoom_max", 18), tiles=None, control_scale=mc.get("mostrar_escala", True),
        prefer_canvas=True,
    )
    bases = mc.get("mapas_base", [])
    # Primero las no seleccionadas, al final la seleccionada (Leaflet muestra la última añadida)
    orden = [b for b in bases if b["nombre"] != base_defecto] + [b for b in bases if b["nombre"] == base_defecto]
    for b in orden:
        folium.TileLayer(tiles=b["url"], attr=b["atribucion"], name=b["nombre"], overlay=False, control=True,
                         show=(b["nombre"] == base_defecto), max_zoom=mc.get("zoom_max", 18)).add_to(m)
    if mc.get("mostrar_coordenadas_cursor", True):
        plugins.MousePosition(position="bottomleft", separator=" | ", num_digits=5, prefix="Lon/Lat", lat_first=False).add_to(m)
    plugins.Fullscreen(position="topleft", title="Pantalla completa", title_cancel="Salir").add_to(m)
    plugins.MeasureControl(position="topleft", primary_length_unit="meters", secondary_length_unit="kilometers",
                           primary_area_unit="hectares", active_color="#ffd166", completed_color="#ffd166").add_to(m)
    if mc.get("mostrar_minimapa"):
        plugins.MiniMap(toggle_display=True).add_to(m)
    if bounds:
        # Centro y zoom explícitos en lugar de fit_bounds: dentro de una pestaña oculta de Streamlit el contenedor mide 0 px
        # y fit_bounds dejaría el mapa en el zoom máximo (escala de 50 m).
        centro, zoom = vista_para_bounds(bounds, 900, altura, mc.get("zoom_max", 18))
        m.location = [centro[0], centro[1]]
        m.options["zoom"] = int(zoom)
    m.get_root().html.add_child(folium.Element("<style>@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');.leaflet-container{background:#DCE6F2;font-family:Manrope,system-ui,sans-serif}"
                                               ".leaflet-bar a,.leaflet-control-layers,.leaflet-control-scale-line,.leaflet-control-mouseposition{border-radius:10px!important;font-family:Manrope,sans-serif}"
                                               ".leaflet-control-layers{border-radius:14px!important;box-shadow:0 8px 22px rgba(27,36,64,.18)!important;border:none!important}"
                                               ".leaflet-popup-content-wrapper{border-radius:14px;font-family:Manrope,sans-serif;box-shadow:0 10px 26px rgba(27,36,64,.2)}"
                                               ".leaflet-tooltip{border-radius:10px;font-family:Manrope,sans-serif;border:none;box-shadow:0 6px 16px rgba(27,36,64,.18)}</style>"))
    return m


def _formato_popup(campos: Iterable[str], alias: dict | None = None) -> tuple[list[str], list[str]]:
    campos = list(campos)
    alias = alias or {}
    return campos, [alias.get(c, c) + ":" for c in campos]


def agregar_geojson(m: folium.Map, geojson: dict, nombre: str, color: str = "#ffffff", grosor: float = 2.0, opacidad: float = 1.0,
                    relleno: str | None = None, opacidad_relleno: float = 0.2, campos_tooltip: Iterable[str] = (), campos_popup: Iterable[str] = (),
                    alias: dict | None = None, funcion_estilo=None, mostrar: bool = True, dash: str | None = None, z: int | None = None) -> folium.GeoJson:
    if not geojson or not geojson.get("features"):
        return None
    campos_t, alias_t = _formato_popup(campos_tooltip, alias)
    campos_p, alias_p = _formato_popup(campos_popup, alias)

    def estilo(feature):
        base = {"color": color, "weight": grosor, "opacity": opacidad, "fillColor": relleno or color, "fillOpacity": opacidad_relleno if relleno else 0.0}
        if dash:
            base["dashArray"] = dash
        if funcion_estilo:
            base.update(funcion_estilo(feature) or {})
        return base

    capa = folium.GeoJson(
        geojson, name=nombre, style_function=estilo, show=mostrar,
        highlight_function=lambda f: {"weight": grosor + 2, "opacity": 1.0},
        tooltip=folium.GeoJsonTooltip(fields=campos_t, aliases=alias_t, sticky=True, localize=True) if campos_t else None,
        popup=folium.GeoJsonPopup(fields=campos_p, aliases=alias_p, localize=True, max_width=360) if campos_p else None,
        zoom_on_click=False,
    )
    capa.add_to(m)
    return capa


def agregar_superposicion(m: folium.Map, s: Superposicion, nombre: str, opacidad: float = 1.0, mostrar: bool = True, zindex: int = 1) -> None:
    folium.raster_layers.ImageOverlay(image=s.url, bounds=s.bounds, name=nombre, opacity=opacidad, show=mostrar, interactive=False,
                                      cross_origin=False, zindex=zindex).add_to(m)


def rampa_cronologica(cfg: dict, vmin: float, vmax: float, titulo: str = "Año") -> cm.LinearColormap:
    c = cfg["visualizacion"]["colores"]
    colores = [c["linea_historica_inicio"], "#7570b3", "#e7298a", c["linea_historica_fin"]]
    rampa = cm.LinearColormap(colores, vmin=vmin, vmax=vmax, caption=titulo)
    return rampa


def rampa_divergente(vmin: float, vmax: float, titulo: str) -> cm.LinearColormap:
    lim = max(abs(vmin), abs(vmax)) or 1.0
    return cm.LinearColormap(["#b2182b", "#f4a582", "#f7f7f7", "#92c5de", "#2166ac"], vmin=-lim, vmax=lim, caption=titulo)


def rampa_clases_ivc(cfg: dict) -> cm.StepColormap:
    clases = cfg["ivc"]["clases"]
    cortes = cfg["ivc"]["cortes"]
    colores = [clases[k]["color"] for k in sorted(clases)]
    return cm.StepColormap(colores, index=[0.0, *cortes, 1.0], vmin=0.0, vmax=1.0, caption="IVC (0–1): " + " · ".join(f"{k} {clases[k]['nombre']}" for k in sorted(clases)))


def agregar_leyenda_html(m: folium.Map, html: str, posicion: str = "bottomright") -> None:
    """Acumula leyendas; se dibujan juntas en ``finalizar`` (una caja por posición, sin solapamientos)."""
    m._leyendas_gv = getattr(m, "_leyendas_gv", {})
    m._leyendas_gv.setdefault(posicion, []).append(html)


def _dibujar_leyendas(m: folium.Map) -> None:
    estilos = {"bottomright": "bottom:28px;right:12px", "topright": "top:60px;right:12px", "bottomleft": "bottom:28px;left:60px", "topleft": "top:12px;left:60px"}
    for posicion, partes in getattr(m, "_leyendas_gv", {}).items():
        cuerpo = '<hr style="border:0;border-top:1px solid #E6EBF5;margin:7px 0">'.join(partes)
        m.get_root().html.add_child(folium.Element(
            f'<div style="position:absolute;{estilos[posicion]};z-index:900;background:rgba(255,255,255,.94);color:#1B2440;padding:10px 12px;border-radius:14px;'
            f'font:11.5px Manrope,system-ui,sans-serif;box-shadow:0 8px 22px rgba(27,36,64,.18);backdrop-filter:blur(6px);max-width:250px;min-width:170px;max-height:46%;overflow:auto;line-height:1.35">{cuerpo}</div>'))


def leyenda_rampa(rampa: cm.LinearColormap, titulo: str, formato="{:.1f}") -> str:
    """Leyenda HTML (gradiente CSS) equivalente a una LinearColormap de branca. ``formato``: cadena o función."""
    if isinstance(formato, str):
        f_ = formato
        formato = type("F", (), {"format": staticmethod(lambda v: f_.format(v))})()
    colores = [c if isinstance(c, str) else "#%02x%02x%02x" % tuple(int(x * 255) for x in c[:3]) for c in rampa.colors]
    grad = ", ".join(colores)
    return (f"<b>{titulo}</b><div style='height:10px;border-radius:3px;margin:4px 0 2px;background:linear-gradient(to right,{grad})'></div>"
            f"<div style='display:flex;justify-content:space-between;opacity:.8'><span>{formato.format(rampa.vmin)}</span><span>{formato.format((rampa.vmin + rampa.vmax) / 2)}</span><span>{formato.format(rampa.vmax)}</span></div>")


def leyenda_clases(cfg: dict, titulo: str = "Clase de vulnerabilidad") -> str:
    clases = cfg["ivc"]["clases"]
    cortes = cfg["ivc"]["cortes"]
    limites = [0.0, *cortes, 1.0]
    filas = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0"><span style="width:14px;height:14px;background:{clases[k]["color"]};display:inline-block;border-radius:2px"></span>'
        f'{k} · {clases[k]["nombre"]} <span style="opacity:.7">({limites[i]:.1f}–{limites[i+1]:.1f})</span></div>'
        for i, k in enumerate(sorted(clases)))
    filas += f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0"><span style="width:14px;height:14px;background:{cfg["visualizacion"]["colores"]["sin_dato"]};display:inline-block;border-radius:2px"></span>Sin dato</div>'
    return f"<b>{titulo}</b><div style='opacity:.75;margin-bottom:4px'>intervalos iguales de 0,2 (escala 0–1)</div>{filas}"


def leyendas_html(m: folium.Map) -> str:
    """Leyendas acumuladas como tarjetas HTML para dibujarlas FUERA del mapa (cuando las capas se actualizan sin recrear el mapa)."""
    partes = []
    for posicion, lista in getattr(m, "_leyendas_gv", {}).items():
        for html in lista:
            partes.append(f'<div class="gv-leyenda">{html}</div>')
    return f'<div class="gv-leyendas">{"".join(partes)}</div>' if partes else ""


def finalizar(m: folium.Map, control_capas: bool = True) -> folium.Map:
    _dibujar_leyendas(m)
    if control_capas:
        folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m
