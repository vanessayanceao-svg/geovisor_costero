"""Capas de los proyectos calculados con la Calculadora IVC, para verlas en el mapa (visor o mapa integrado del proyecto).

Un proyecto exportado (``resultados/calculadora/<proyecto>/``) contiene GeoPackages en la EPSG métrica del proyecto:
``transectos_tasas.gpkg``, ``indice_transectos.gpkg``, ``lineas_proyectadas.gpkg``, ``linea_base.gpkg`` y ``escenario_*.gpkg``.
Aquí se localizan, se leen (con caché) y se añaden al mapa con la misma simbología del geovisor (tasas en rampa
divergente, IVC por clase, líneas proyectadas por tipo). El mapa integrado también puede exportarse como HTML autónomo.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from .. import mapas, vectores
from ..cachear import cachear_datos
from ..configuracion import rutas_salida

ARCHIVOS = {
    "calc_tasas": ("transectos_tasas.gpkg", "Transectos y tasas"),
    "calc_ivc": ("indice_transectos.gpkg", "IVC del proyecto"),
    "calc_lineas": ("lineas_proyectadas.gpkg", "Líneas proyectadas"),
    "calc_escenario": ("escenario_*.gpkg", "IVC futuro (escenario)"),
    "calc_base": ("linea_base.gpkg", "Línea base"),
}
TASAS = ["LRR", "WLR", "EPR", "NSM", "SCE"]


def carpeta_proyectos(cfg: dict) -> Path:
    return Path(rutas_salida(cfg).get("reportes", "resultados/reportes")).parent / "calculadora"


def proyectos(cfg: dict) -> dict[str, Path]:
    """Proyectos exportados (nombre → carpeta) que tienen al menos un GeoPackage."""
    base = carpeta_proyectos(cfg)
    if not base.exists():
        return {}
    out = {}
    for d in sorted(base.iterdir()):
        if d.is_dir() and any(d.glob("*.gpkg")):
            out[d.name] = d
    return out


def capas_de(carpeta: Path) -> dict[str, list[Path]]:
    """Capas presentes en la carpeta del proyecto: clave → archivos."""
    out = {}
    for k, (patron, _) in ARCHIVOS.items():
        f = sorted(carpeta.glob(patron))
        if f:
            out[k] = f
    return out


def escenarios_de(carpeta: Path) -> list[str]:
    return [p.stem.replace("escenario_", "") for p in sorted(carpeta.glob("escenario_*.gpkg"))]


def metadatos(carpeta: Path) -> dict:
    p = carpeta / "proyecto.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


@cachear_datos(ttl=600)
def _leer(ruta: str, mtime: float) -> gpd.GeoDataFrame:  # mtime solo invalida la caché
    return gpd.read_file(ruta)


def leer(ruta: Path) -> gpd.GeoDataFrame:
    return _leer(str(ruta), ruta.stat().st_mtime)


def agregar_capas(fg, m, cfg: dict, carpeta: Path, activas: dict, campo_tasa: str = "LRR", esquema: str = "ewm", escenario: str | None = None,
                  prefijo: str = "") -> dict:
    """Añade al mapa las capas activas del proyecto. ``fg(nombre)`` devuelve el FeatureGroup/mapa donde dibujar.

    Devuelve estadísticas (n transectos, tasa media, IVC medio, % alta) y deja las leyendas registradas en ``m``.
    """
    col = cfg["visualizacion"]["colores"]
    clases = cfg["ivc"]["clases"]
    stats: dict = {}
    disp = capas_de(carpeta)
    if activas.get("calc_base") and "calc_base" in disp:
        g = leer(disp["calc_base"][0])
        mapas.agregar_geojson(fg(f"{prefijo}Línea base"), vectores.a_geojson(g, cfg, []), f"{prefijo}Línea base", color="#ffffff", grosor=1.5, dash="6 4", opacidad=0.8)
    if activas.get("calc_tasas") and "calc_tasas" in disp:
        g = leer(disp["calc_tasas"][0])
        campo = campo_tasa if campo_tasa in g.columns else "LRR"
        cols = [c for c in ["id_ivc", "dist_costa_km", "n_lineas", "LRR", "LCI95", "EPR", "NSM", "SCE", "WLR"] if c in g.columns]
        gj = vectores.a_geojson(g, cfg, cols)
        vals = [f["properties"].get(campo) for f in gj["features"] if f["properties"].get(campo) is not None]
        if vals:
            rampa = mapas.rampa_divergente(min(vals), max(vals), f"{campo} del proyecto (m/año)" if campo not in ("NSM", "SCE") else f"{campo} del proyecto (m)")
            mapas.agregar_geojson(fg(f"{prefijo}Tasas ({campo})"), gj, f"{prefijo}Tasas ({campo})", grosor=3, opacidad=0.9, campos_tooltip=["id_ivc", campo],
                                  campos_popup=cols, alias={"id_ivc": "Transecto", "dist_costa_km": "Km", "n_lineas": "N.º líneas", "LRR": "LRR (m/año)", "LCI95": "IC95", "EPR": "EPR (m/año)", "NSM": "NSM (m)", "SCE": "SCE (m)", "WLR": "WLR (m/año)"},
                                  funcion_estilo=lambda f, r=rampa, c=campo: {"color": r(f["properties"][c]) if f["properties"].get(c) is not None else col["sin_dato"]})
            mapas.agregar_leyenda_html(m, mapas.leyenda_rampa(rampa, rampa.caption, "{:.1f}"), "bottomleft")
            stats["n_transectos"] = len(gj["features"]); stats["tasa_media"] = sum(vals) / len(vals); stats["campo_tasa"] = campo
    if activas.get("calc_ivc") and "calc_ivc" in disp:
        g = leer(disp["calc_ivc"][0])
        ci, cc = f"ivc_{esquema}", f"clase_{esquema}"
        if ci not in g.columns:
            ci = next((c for c in g.columns if c.startswith("ivc_")), None); cc = ci.replace("ivc_", "clase_") if ci else None
        if ci and cc in g.columns:
            cols = ["id_ivc", "dist_costa_km", ci, cc]
            gj = vectores.a_geojson(g, cfg, cols)
            mapas.agregar_geojson(fg(f"{prefijo}IVC ({esquema})"), gj, f"{prefijo}IVC ({esquema})", grosor=4, opacidad=0.95, campos_tooltip=["id_ivc", ci, cc],
                                  campos_popup=cols, alias={"id_ivc": "Transecto", "dist_costa_km": "Km", ci: "IVC (0‑1)", cc: "Clase"},
                                  funcion_estilo=lambda f, c=cc: {"color": clases.get(int(f["properties"][c]), {"color": col["sin_dato"]})["color"] if f["properties"].get(c) is not None else col["sin_dato"]})
            mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, f"IVC del proyecto ({esquema})"), "bottomright")
            v = g[ci].dropna()
            if len(v):
                stats["ivc_medio"] = float(v.mean()); stats["pct_alta"] = float(100 * (g[cc] >= 4).mean())
    if activas.get("calc_lineas") and "calc_lineas" in disp:
        g = leer(disp["calc_lineas"][0])
        gj = vectores.a_geojson(g, cfg, [c for c in ("tipo", "anio", "linea") if c in g.columns])
        estilos = {"observada": (col["linea_seleccionada"], None, 2.0), "central": (col["prediccion_central"], None, 3.0),
                   "p05": (col["prediccion_banda"], "4 6", 1.5), "p95": (col["prediccion_banda"], "4 6", 1.5), "persistencia": (col["prediccion_persistencia"], "10 6", 2.0)}
        mapas.agregar_geojson(fg(f"{prefijo}Líneas proyectadas"), gj, f"{prefijo}Líneas proyectadas", grosor=2, campos_tooltip=[c for c in ("tipo", "anio") if c in g.columns],
                              funcion_estilo=lambda f, e=estilos: {"color": e.get(f["properties"].get("tipo"), ("#ffffff", None, 2.0))[0], "dashArray": e.get(f["properties"].get("tipo"), ("#fff", None, 2))[1], "weight": e.get(f["properties"].get("tipo"), ("#fff", None, 2.0))[2]})
    if activas.get("calc_escenario") and "calc_escenario" in disp:
        esc = escenario or escenarios_de(carpeta)[0]
        ruta = carpeta / f"escenario_{esc}.gpkg"
        if ruta.exists():
            g = leer(ruta)
            cc = f"clase_{esc}"; ci = f"ivc_{esc}"
            if cc in g.columns:
                cols = [c for c in ("id_ivc", ci, cc, f"retroceso_m_{esc}") if c in g.columns]
                gj = vectores.a_geojson(g, cfg, cols)
                mapas.agregar_geojson(fg(f"{prefijo}IVC futuro {esc}"), gj, f"{prefijo}IVC futuro {esc}", grosor=4, opacidad=0.95, campos_tooltip=["id_ivc", cc],
                                      campos_popup=cols, alias={"id_ivc": "Transecto", ci: "IVC", cc: "Clase", f"retroceso_m_{esc}": "Retroceso (m)"},
                                      funcion_estilo=lambda f, c=cc: {"color": clases.get(int(f["properties"][c]), {"color": col["sin_dato"]})["color"] if f["properties"].get(c) is not None else col["sin_dato"]})
                mapas.agregar_leyenda_html(m, mapas.leyenda_clases(cfg, f"IVC futuro {esc}"), "bottomright")
                stats["pct_alta_escenario"] = float(100 * (g[cc] >= 4).mean()); stats["escenario"] = esc
    return stats


def bounds_proyecto(carpeta: Path, cfg: dict) -> list | None:
    """[[lat_min, lon_min], [lat_max, lon_max]] de la primera capa disponible, en WGS 84."""
    for k in ("calc_tasas", "calc_ivc", "calc_lineas", "calc_base"):
        f = capas_de(carpeta).get(k)
        if f:
            g = leer(f[0]).to_crs(cfg["crs"]["visualizacion"])
            b = g.total_bounds
            return [[float(b[1]), float(b[0])], [float(b[3]), float(b[2])]]
    return None


def mapa_integrado(cfg: dict, carpeta: Path, mapa_base: str | None = None, campo_tasa: str = "LRR", esquema: str = "ewm", escenario: str | None = None,
                   altura: int = 640, capas: dict | None = None):
    """Mapa Folium con todas las capas del proyecto (para mostrar en la app o exportar como HTML)."""
    import folium

    bounds = bounds_proyecto(carpeta, cfg)
    m = mapas.crear_mapa(cfg, bounds, mapa_base, altura)
    grupos = []

    def fg(nombre):
        g = folium.FeatureGroup(name=nombre, show=True)
        grupos.append(g)
        return g

    activas = capas or {k: True for k in ARCHIVOS}
    stats = agregar_capas(fg, m, cfg, carpeta, activas, campo_tasa, esquema, escenario)
    for g in grupos:
        g.add_to(m)
    return m, grupos, stats


def html_autonomo(cfg: dict, carpeta: Path, **kw) -> str:
    """HTML completo del mapa integrado (Leaflet desde CDN), con las leyendas, para abrir en cualquier navegador."""
    m, _, _ = mapa_integrado(cfg, carpeta, **kw)
    mapas.finalizar(m, control_capas=True)
    html = m.get_root().render()
    leyendas = mapas.leyendas_html(m)
    estilo = ("<style>.gv-leyendas{position:absolute;right:12px;bottom:28px;z-index:1000;display:flex;flex-direction:column;gap:8px;font:12px Manrope,system-ui,sans-serif}"
              ".gv-leyenda{background:#fff;border:1px solid #dde3ee;border-radius:10px;padding:8px 11px;box-shadow:0 6px 16px rgba(27,36,64,.15);max-width:260px}</style>")
    return html.replace("</body>", f"{estilo}{leyendas}</body>") if leyendas else html
