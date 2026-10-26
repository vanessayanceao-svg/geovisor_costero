"""Informe PDF de un proyecto de la Calculadora IVC (o de la corrida de verificación de la tesis), con el lenguaje visual del geovisor.

Lee los productos exportados (CSV y GeoPackage) de una carpeta de proyecto —búsqueda recursiva, de modo que sirve tanto
para ``resultados/calculadora/<proyecto>/`` como para ``resultados/pruebas_calculadora/``— y compone con matplotlib un
PDF A4 apaisado: portada con degradado azul→verde azulado, tarjetas «de cristal» biseladas, cifras grandes, y capítulos
con panel lateral degradado y mapas sobre un fondo cartográfico real:

* ``arcgis``: imagen satelital Esri World Imagery (vía *contextily*; requiere internet),
* ``delta``: sombreado del DEM DeltaDTM (o del DEM del proyecto) con tinte hipsométrico y mar en azul,
* ``fondo``: mosaico tierra/agua de la tesis (``fondo_rgb.tif``),
* ``auto`` (por defecto): el primero disponible de los anteriores; ``ninguno``: sin fondo.

Solo necesita matplotlib, pandas, geopandas y rasterio (contextily es opcional).
"""
from __future__ import annotations

import datetime as dt
import re
import logging
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.colors import LightSource, ListedColormap, LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch, PathPatch, Polygon  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.transforms import Affine2D  # noqa: E402

LOG = logging.getLogger("geovisor")
NAVY = "#1B2A6B"
NAVY2 = "#243A8C"
NAVY3 = "#2F4BB0"
TINTA = "#1B2440"
GRIS = "#5B6178"
GRIS2 = "#9AA1B8"
LINEA = "#DDE3EE"
AZUL = "#3B6CF0"
TEAL = "#5FD8C9"
TEAL2 = "#19B3A6"
CORAL = "#F2745F"
AMBAR = "#F5B544"
FONDO = "#F3F5FA"
BLANCO = "white"
VERSION_APP = "26‑10‑2026"
A4 = (11.69, 8.27)   # apaisado
_NUM = {"n": 0, "total": 0}

# ---------------------------------------------------------------------------
# Tipografía: Aptos Narrow para el texto y Aptos SemiBold (o Poppins) para títulos, con alternativas si no están instaladas
# ---------------------------------------------------------------------------
def _registrar_fuentes() -> tuple[str, str]:
    """Busca las fuentes en el sistema (incluidas las «fuentes en la nube» de Microsoft 365 en Windows) y devuelve
    (familia_texto, familia_titulos). Orden de preferencia: Aptos Narrow → Manrope → DejaVu Sans para el texto;
    Aptos SemiBold → Poppins → DejaVu Sans para los títulos."""
    import os
    from matplotlib import font_manager as fm

    carpetas = [Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "FontCache" / "4" / "CloudFonts",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
                Path("C:/Windows/Fonts"), Path("C:/Program Files/Microsoft Office/root/vfs/Fonts/private"),
                Path(__file__).resolve().parent.parent / "assets" / "fuentes"]
    for c in carpetas:
        if c.is_dir():
            for f in list(c.rglob("*.ttf")) + list(c.rglob("*.otf")):
                if any(k in f.name.lower() for k in ("aptos", "poppins", "manrope")):
                    try:
                        fm.fontManager.addfont(str(f))
                    except Exception:
                        pass
    disponibles = {f.name for f in fm.fontManager.ttflist}

    def primera(*nombres):
        for n in nombres:
            if n in disponibles:
                return n
        return "DejaVu Sans"

    texto = primera("Aptos Narrow", "Aptos", "Manrope", "Segoe UI")
    titulos = primera("Aptos SemiBold", "Aptos Semibold", "Poppins", "Aptos", "Segoe UI")
    return texto, titulos


FUENTE_TEXTO, FUENTE_TITULO = _registrar_fuentes()
matplotlib.rcParams["font.family"] = FUENTE_TEXTO
matplotlib.rcParams["pdf.fonttype"] = 42      # fuentes incrustadas como TrueType (texto seleccionable)
TIT = {"fontweight": "bold", "fontfamily": FUENTE_TITULO}   # títulos, cifras grandes y etiquetas en mayúsculas


# ---------------------------------------------------------------------------
# Utilidades de datos
# ---------------------------------------------------------------------------
def _buscar(carpeta: Path, nombre: str) -> Path | None:
    c = list(carpeta.rglob(nombre))
    return c[0] if c else None


def _csv(carpeta: Path, nombre: str) -> pd.DataFrame | None:
    r = _buscar(carpeta, nombre)
    return pd.read_csv(r, encoding="utf-8-sig") if r else None


def _gpkg(carpeta: Path, nombre: str):
    r = _buscar(carpeta, nombre)
    if not r:
        return None
    import geopandas as gpd

    return gpd.read_file(r)


def _fmt(v, dec=2, suf=""):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        return f"{float(v):,.{dec}f}{suf}".replace(",", " ")
    except Exception:  # noqa: BLE001
        return str(v)


def _wrap(ax, x, y, texto, ancho=95, fs=8, color=TINTA, dy=0.0165, **kw):
    """Escribe un párrafo ajustado a ``ancho`` caracteres; devuelve la y siguiente."""
    for linea in textwrap.wrap(texto, ancho):
        ax.text(x, y, linea, fontsize=fs, color=color, transform=ax.transAxes, va="top", **kw)
        y -= dy
    return y - dy * 0.5


# ---------------------------------------------------------------------------
# Fondos cartográficos
# ---------------------------------------------------------------------------
def _ruta_dem_proyecto(meta: dict) -> Path | None:
    for v in meta.get("variables", []):
        f = str(v.get("fuente") or "")
        if str(v.get("metodo", "")).startswith("raster") and f.lower().endswith((".tif", ".tiff")) and Path(f).exists():
            return Path(f)
    return None


class Fondo:
    """Decide y dibuja el fondo del mapa. ``modo``: auto | arcgis | delta | fondo | ninguno."""

    def __init__(self, cfg: dict, modo: str = "auto", meta: dict | None = None):
        self.cfg = cfg; self.modo = modo; self.meta = meta or {}
        self.dem = None; self.rgb = None; self.ctx = None
        self.usado = "ninguno"
        from .catalogo_datos import CAPAS

        if modo in ("auto", "arcgis"):
            try:
                import contextily as ctx

                self.ctx = ctx
            except Exception:  # noqa: BLE001
                self.ctx = None
        if modo in ("auto", "delta"):
            r = _ruta_dem_proyecto(self.meta)
            if r is None and CAPAS["dem"].disponible(cfg):
                r = CAPAS["dem"].ruta(cfg)
            self.dem = r
        if modo in ("auto", "fondo") and CAPAS["fondo_rgb"].disponible(cfg):
            self.rgb = CAPAS["fondo_rgb"].ruta(cfg)

    def crs(self) -> str:
        """Las capas se dibujan en el CRS del fondo: 3857 para teselas web, 4326 para rásteres locales."""
        if self.ctx is not None and self.modo in ("auto", "arcgis") and self.usado in ("ninguno", "arcgis"):
            return "EPSG:3857"
        return "EPSG:4326"

    def dibujar(self, ax, bounds4326, crs_usado: str) -> str:
        """Pinta el fondo bajo [xmin, ymin, xmax, ymax] (EPSG:4326). Devuelve el modo usado."""
        if self.modo == "ninguno":
            return "ninguno"
        if crs_usado == "EPSG:3857" and self.ctx is not None and self.modo in ("auto", "arcgis"):
            try:
                self.ctx.add_basemap(ax, source=self.ctx.providers.Esri.WorldImagery, attribution=False, crs="EPSG:3857")
                self.usado = "arcgis"
                return "arcgis"
            except Exception as e:  # noqa: BLE001
                LOG.info("Sin teselas Esri para el informe (%s); se intenta con el DEM", e)
                self.ctx = None
                return "ninguno"
        if crs_usado != "EPSG:4326":
            return "ninguno"
        if self.dem is not None and self.modo in ("auto", "delta"):
            try:
                self._dem(ax, bounds4326); self.usado = "delta"; return "delta"
            except Exception as e:  # noqa: BLE001
                LOG.info("Fondo DEM no disponible: %s", e)
        if self.rgb is not None and self.modo in ("auto", "fondo"):
            try:
                self._rgb(ax, bounds4326); self.usado = "fondo"; return "fondo"
            except Exception as e:  # noqa: BLE001
                LOG.info("Fondo tierra/agua no disponible: %s", e)
        return "ninguno"

    def _ventana(self, ruta, bounds, margen=0.02):
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window, bounds as wbounds, from_bounds

        with rasterio.open(ruta) as r:
            b = transform_bounds("EPSG:4326", r.crs, bounds[0] - margen, bounds[1] - margen, bounds[2] + margen, bounds[3] + margen)
            w = from_bounds(*b, transform=r.transform).round_offsets().round_lengths()
            w = w.intersection(Window(0, 0, r.width, r.height))
            esc = max(1, int(max(w.width, w.height) // 1600))
            out_shape = (r.count, max(1, int(w.height // esc)), max(1, int(w.width // esc)))
            a = r.read(window=w, out_shape=out_shape, resampling=Resampling.bilinear)
            bb = wbounds(w, r.transform)
            if str(r.crs).upper() != "EPSG:4326":
                bb = transform_bounds(r.crs, "EPSG:4326", *bb)
            return a, [bb[0], bb[2], bb[1], bb[3]], r.nodata

    def _dem(self, ax, bounds):
        a, ext, nodata = self._ventana(self.dem, bounds)
        z = a[0].astype(float)
        if nodata is not None:
            z[z == nodata] = np.nan
        agua = ~np.isfinite(z) | (z <= 0.05)
        zz = np.where(np.isfinite(z), z, 0)
        ls = LightSource(azdeg=315, altdeg=45)
        cmap = LinearSegmentedColormap.from_list("tierra", ["#EDE6CC", "#DDD6AC", "#C3D6A6", "#93C08A", "#619D65", "#417B4C"])
        vmax = float(np.nanpercentile(zz[~agua], 98)) if (~agua).any() else 10.0
        rgb = ls.shade(zz, cmap=cmap, vmin=0, vmax=max(vmax, 2.0), vert_exag=25, blend_mode="soft")
        rgb[agua] = np.array([0.66, 0.79, 0.92, 1.0])
        ax.imshow(rgb, extent=ext, origin="upper", interpolation="bilinear", zorder=0)

    def _rgb(self, ax, bounds):
        a, ext, _ = self._ventana(self.rgb, bounds)
        ax.imshow(np.transpose(a[:3], (1, 2, 0)), extent=ext, origin="upper", interpolation="bilinear", zorder=0)


def _mapa(ax, fondo: Fondo, capas: list, bounds_g, margen=0.08) -> str:
    """Dibuja ``capas`` = [(GeoDataFrame, kwargs de .plot)] sobre el fondo; ``bounds_g`` fija el encuadre. Devuelve el fondo usado."""
    crs = fondo.crs()
    g0 = bounds_g.to_crs(crs)
    xmin, ymin, xmax, ymax = g0.total_bounds
    dx, dy = (xmax - xmin) * margen, (ymax - ymin) * margen
    dx = max(dx, (ymax - ymin) * 0.05); dy = max(dy, (xmax - xmin) * 0.05)
    for g, kw in capas:
        g.to_crs(crs).plot(ax=ax, zorder=3, **kw)
    for a in ax.figure.axes:          # la barra de color que crea geopandas debe quedar sobre las tarjetas
        if a is not ax and a.get_zorder() == 0:
            a.set_zorder(2)
    ax.set_xlim(xmin - dx, xmax + dx); ax.set_ylim(ymin - dy, ymax + dy)
    # encuadre que llena la caja del mapa: se amplía el rango corto (más contexto de fondo) en vez de dejar bandas vacías
    k = 1 / np.cos(np.radians((ymin + ymax) / 2)) if crs == "EPSG:4326" else 1.0
    fig = ax.figure; bb = ax.get_position(original=True)
    w_in, h_in = bb.width * fig.get_figwidth(), bb.height * fig.get_figheight()
    x0, x1, y0, y1 = xmin - dx, xmax + dx, ymin - dy, ymax + dy
    rel = (y1 - y0) * k / (x1 - x0)           # alto/ancho de los datos
    obj = h_in / w_in                           # alto/ancho de la caja
    if rel < obj:                               # datos más anchos: ampliar y (como máximo 1,8× para no alejar la costa)
        cy = (y0 + y1) / 2; h = min((x1 - x0) * obj / k, (y1 - y0) * 1.8)
        y0, y1 = cy - h / 2, cy + h / 2
    else:                                       # datos más altos: ampliar x
        cx = (x0 + x1) / 2; w = (y1 - y0) * k / obj
        x0, x1 = cx - w / 2, cx + w / 2
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    if crs == "EPSG:4326":
        b4326 = [x0, y0, x1, y1]
    else:
        from pyproj import Transformer

        tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        lon0, lat0 = tr.transform(x0, y0); lon1, lat1 = tr.transform(x1, y1)
        b4326 = [lon0, lat0, lon1, lat1]
    usado = fondo.dibujar(ax, b4326, crs)
    if usado == "ninguno" and crs == "EPSG:3857":   # sin teselas: repintar en 4326 con el DEM o el mosaico
        ax.cla()
        return _mapa(ax, fondo, capas, bounds_g, margen)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect(k)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_edgecolor(LINEA); s.set_linewidth(0.6)
    ax.set_facecolor("#DCE6F2")
    return usado


def _escala(ax):
    """Barra de escala (km) en la esquina inferior izquierda, válida en grados o en metros."""
    xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
    ancho = xmax - xmin
    m_por_u = 111_320 * np.cos(np.radians((ymin + ymax) / 2)) if abs(xmax) < 400 else 1.0
    km_total = ancho * m_por_u / 1000
    km = next((k for k in (1, 2, 5, 10, 20, 50) if k >= km_total / 5), 50)
    L = km * 1000 / m_por_u
    x0 = xmin + ancho * 0.03; y0 = ymin + (ymax - ymin) * 0.06
    ax.plot([x0, x0 + L], [y0, y0], color="white", lw=4, solid_capstyle="butt", zorder=10)
    ax.plot([x0, x0 + L], [y0, y0], color=TINTA, lw=1.4, solid_capstyle="butt", zorder=11)
    ax.text(x0 + L / 2, y0 + (ymax - ymin) * 0.03, f"{km} km", fontsize=5.6, ha="center", color=TINTA, zorder=11,
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.85))


def _leyenda_clases(ax, cfg, titulo="Clase de vulnerabilidad", loc="lower right"):
    from matplotlib.lines import Line2D

    clases = cfg["ivc"]["clases"]
    h = [Line2D([0], [0], color=clases[k]["color"], lw=4, label=f"{k} · {clases[k]['nombre']}") for k in sorted(clases)]
    lg = ax.legend(handles=h, title=titulo, loc=loc, fontsize=5.6, title_fontsize=6, frameon=True, framealpha=0.92, edgecolor=LINEA)
    lg.get_frame().set_linewidth(0.5)


def _clase_cmap(cfg):
    clases = cfg["ivc"]["clases"]; ks = sorted(clases)
    return ListedColormap([clases[k]["color"] for k in ks]), min(ks) - 0.5, max(ks) + 0.5


# ---------------------------------------------------------------------------
# Elementos de página (lenguaje visual del geovisor: degradados, cristal, biseles)
# ---------------------------------------------------------------------------
VIOLETA = "#7C5CF6"
AZUL_OSC = "#1E3A8A"
VERDE = "#2E9E6B"
GRIS_F = "#EEF2FA"


def _hex(c):
    if not str(c).startswith("#"):
        from matplotlib.colors import to_hex
        c = to_hex(c)
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])


# ---------------------------------------------------------------------------
# Iconos del geovisor (los mismos SVG de src/estilos.py) dibujados como trazos vectoriales
# ---------------------------------------------------------------------------
def _svg_a_path(svg: str) -> MPath:
    """Convierte los elementos path/circle/ellipse/rect de un icono SVG (viewBox 0‑24) en un Path de matplotlib."""
    from svgpath2mpl import parse_path

    partes = []
    for m in re.finditer(r"<(path|circle|ellipse|rect)\b([^>]*)/?>", svg):
        tag, at = m.group(1), dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(2)))
        f = lambda k, d=0.0: float(at.get(k, d))  # noqa: E731
        if tag == "path":
            partes.append(parse_path(at["d"]))
        elif tag == "circle":
            partes.append(MPath.circle((f("cx"), f("cy")), f("r")))
        elif tag == "ellipse":
            partes.append(Affine2D().scale(f("rx"), f("ry")).translate(f("cx"), f("cy")).transform_path(MPath.unit_circle()))
        elif tag == "rect":
            x, y, w, h = f("x"), f("y"), f("width"), f("height")
            partes.append(MPath([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], [1, 2, 2, 2, 79]))
    return MPath.make_compound_path(*partes) if partes else MPath([(0, 0)])


_CACHE_ICONOS: dict = {}


def _icono(ax, nombre, x, y, tam=0.02, color=AZUL, lw=1.2, alpha=1.0, zorder=5):
    """Dibuja el icono `nombre` del geovisor con su esquina inferior izquierda en (x, y) de ejes y lado `tam` (en ancho de página)."""
    try:
        from .estilos import ICONO
    except Exception:  # noqa: BLE001
        from src.estilos import ICONO  # type: ignore
    svg = ICONO.get(nombre, ICONO["info"])
    if nombre not in _CACHE_ICONOS:
        _CACHE_ICONOS[nombre] = _svg_a_path(svg)
    path = _CACHE_ICONOS[nombre]
    sx = tam / 24; sy = sx * A4[0] / A4[1]
    tr = Affine2D().scale(sx, -sy).translate(x, y + 24 * sy) + ax.transAxes
    ax.add_patch(PathPatch(path, transform=tr, facecolor="none", edgecolor=color, lw=lw, alpha=alpha, capstyle="round", joinstyle="round", zorder=zorder))


def _ic_de(etiqueta: str) -> str:
    """Icono según el texto de la cifra o del título (misma lógica de iconos que el geovisor)."""
    e = etiqueta.lower()
    reglas = [("dinámica", "lineas"), ("vulnerabilidad", "escudo"), ("índice", "escudo"), ("transecto", "capas"), ("longitud", "regla"), ("km", "regla"), ("mapa", "mapa"), ("clase alta", "alerta"), ("alta +", "alerta"), ("alta+", "alerta"),
              ("retroceso", "trend_down"), ("moderada", "escudo"), ("baja", "check"), ("ivc", "escudo"), ("ρ", "grafico"), ("validación", "check"), ("escenario", "cristal"),
              ("ssp", "cristal"), ("proyec", "cristal"), ("líneas", "lineas"), ("perfil", "trend"), ("distribución", "grafico"), ("pesos", "grafico"), ("por clase", "grafico"),
              ("resumen", "info"), ("contenido", "capas"), ("metodolog", "regla"), ("referencias", "db"), ("medio", "trend_down"), ("mediano", "trend_down")]
    for k, v in reglas:
        if k in e:
            return v
    return "grafico"


# ---------------------------------------------------------------------------
# Lenguaje visual claro (como la referencia de folleto): fondo blanco, halos suaves azules, píldoras con degradado y bisel,
# tarjetas blancas con sombra tenue, numeración grande y tipografía ligera/negrita. Paleta: azules del geovisor.
# ---------------------------------------------------------------------------
AZUL_CLARO = "#8CC3EC"
AZUL_SUAVE = "#DCE9FF"
AZUL_MEDIO = "#5B8DEF"


def _degradado(fig, rect, colores, angulo=20, radio=0.02, alpha=1.0, zorder=-1):
    """Rectángulo con degradado lineal (varios colores) y esquinas redondeadas, en coordenadas de figura."""
    ax = fig.add_axes(rect, zorder=zorder); ax.set_axis_off()
    n = 400
    t = np.linspace(0, 1, n)
    cols = np.array([_hex(c) for c in colores])
    pos = np.linspace(0, 1, len(cols))
    ramp = np.stack([np.interp(t, pos, cols[:, i]) for i in range(3)], axis=1)
    a = np.radians(angulo)
    X, Y = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, int(n * rect[3] / rect[2]) if rect[2] else n))
    u = (X * np.cos(a) + (1 - Y) * np.sin(a)); u = (u - u.min()) / (u.max() - u.min() + 1e-9)
    img = ramp[(u * (n - 1)).astype(int)]
    im = ax.imshow(img, extent=(0, 1, 0, 1), aspect="auto", interpolation="bilinear", alpha=alpha, zorder=0)
    clip = FancyBboxPatch((0, 0), 1, 1, boxstyle=f"round,pad=0,rounding_size={radio}", transform=ax.transAxes, facecolor="none", edgecolor="none")
    ax.add_patch(clip); im.set_clip_path(clip)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return ax


def _halos(fig, halos, zorder=-1):
    """Halos de luz suaves (degradado radial difuminado) sobre el fondo blanco: [(cx, cy, rx, ry, color, alpha), …]."""
    ax = fig.add_axes([0, 0, 1, 1], zorder=zorder); ax.set_axis_off()
    nx, ny = 420, 300
    X, Y = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny))
    img = np.ones((ny, nx, 4)); img[..., 3] = 0
    acum = np.zeros((ny, nx, 3)); peso = np.zeros((ny, nx))
    for cx, cy, rx, ry, color, alpha in halos:
        g = np.exp(-(((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2) * 1.6) * alpha
        acum += g[..., None] * _hex(color); peso += g
    m = peso > 1e-4
    img[..., :3][m] = acum[m] / peso[m][:, None]
    img[..., 3] = np.clip(peso, 0, 1)
    ax.imshow(img, extent=(0, 1, 0, 1), aspect="auto", interpolation="bicubic", origin="lower", zorder=0)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return ax


def _pildora(ax, x, y, w, h, c_ini=AZUL_SUAVE, c_fin="white", alpha=1.0, radio=None, borde=LINEA, sombra=True, zorder=1.5):
    """Píldora (rectángulo de esquinas totalmente redondeadas) con degradado horizontal y bisel superior claro."""
    radio = radio if radio is not None else h / 2
    if sombra:
        ax.add_patch(FancyBboxPatch((x + 0.002, y - 0.005), w, h, boxstyle=f"round,pad=0,rounding_size={radio}", facecolor=AZUL_OSC, edgecolor="none", alpha=0.06,
                                    transform=ax.transAxes, zorder=zorder))
    base = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radio}", facecolor="white", edgecolor=borde, lw=0.6, alpha=alpha, transform=ax.transAxes, zorder=zorder)
    ax.add_patch(base)
    n = 28; a, b = _hex(c_ini), _hex(c_fin)
    for i in range(n):
        col = a + (b - a) * i / (n - 1)
        r = plt.Rectangle((x + w * i / n, y), w / n + 0.002, h, facecolor=col, edgecolor="none", alpha=alpha, transform=ax.transAxes, zorder=zorder)
        ax.add_patch(r); r.set_clip_path(base)
    brillo = FancyBboxPatch((x + 0.004, y + h * 0.56), w - 0.008, h * 0.36, boxstyle=f"round,pad=0,rounding_size={min(radio, h * 0.18)}", facecolor="white", edgecolor="none",
                            alpha=0.55, transform=ax.transAxes, zorder=zorder)
    ax.add_patch(brillo); brillo.set_clip_path(base)
    return base


def _ficha_icono(ax, ic, x, y, lado=0.026, color=AZUL, fuerte=False):
    """Pequeña ficha redondeada con degradado azul y el icono del geovisor dentro."""
    h = lado * A4[0] / A4[1]
    _pildora(ax, x, y, lado, h, (AZUL if fuerte else AZUL_SUAVE), (AZUL_MEDIO if fuerte else "#F3F7FF"), radio=0.008, borde="none", sombra=False, zorder=1.6)
    _icono(ax, ic, x + lado * 0.2, y + h * 0.17, lado * 0.6, "white" if fuerte else color, lw=1.25, zorder=1.7)


def _cristal(ax, x, y, w, h, titulo="", icono_color=AZUL, alpha=0.96, oscuro=False, radio=0.018, ic=None):
    """Tarjeta blanca con sombra tenue, borde fino y bisel superior; título en negrita con ficha de icono."""
    titulo = (titulo or "").replace("‑", "-")
    ax.add_patch(FancyBboxPatch((x + 0.003, y - 0.007), w, h, boxstyle=f"round,pad=0,rounding_size={radio}", facecolor=AZUL_OSC, edgecolor="none", alpha=0.07, transform=ax.transAxes))
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radio}", facecolor="white", edgecolor=LINEA, lw=0.7, alpha=alpha, transform=ax.transAxes))
    if titulo:
        _ficha_icono(ax, ic or _ic_de(titulo), x + 0.014, y + h - 0.044, 0.024, icono_color)
        ax.text(x + 0.047, y + h - 0.027, titulo, fontsize=7.2, color=TINTA, **TIT, va="center", transform=ax.transAxes)
        ax.add_patch(plt.Rectangle((x + 0.014, y + h - 0.053), w - 0.028, 0.0007, facecolor=LINEA, edgecolor="none", transform=ax.transAxes))
    return (x + 0.014, y + 0.014, w - 0.028, h - (0.068 if titulo else 0.028))


def _kpi(ax, x, y, w, h, etiqueta, valor, unidad="", color=AZUL, oscuro=False, ic=None):
    """Cifra en píldora con degradado azul claro → blanco, icono del geovisor a la izquierda, etiqueta pequeña y valor grande."""
    valor = str(valor).replace("‑", "-")
    _pildora(ax, x, y, w, h, AZUL_SUAVE, "white", radio=min(h / 2, 0.03))
    lado = min(0.028, h * 0.5 * A4[1] / A4[0])
    _ficha_icono(ax, ic or _ic_de(etiqueta), x + 0.012, y + (h - lado * A4[0] / A4[1]) / 2, lado, color, fuerte=True)
    ax.text(x + 0.052, y + h * 0.70, etiqueta, fontsize=6.2, color=GRIS, va="center", transform=ax.transAxes, zorder=3)
    ax.text(x + 0.052, y + h * 0.35, valor, fontsize=12.5, color=TINTA, **TIT, va="center", transform=ax.transAxes, zorder=3)
    if unidad:
        ax.text(x + w - 0.016, y + h * 0.35, unidad, fontsize=6.2, color=GRIS2, va="center", ha="right", transform=ax.transAxes, zorder=3)


def _chip(ax, x, y, texto, color=AZUL, oscuro=False, w=None):
    w = w or (0.016 + 0.0062 * len(texto))
    _pildora(ax, x, y - 0.013, w, 0.026, AZUL_SUAVE, "white", sombra=False)
    ax.text(x + w / 2, y, texto, fontsize=6.2, color=TINTA, va="center", ha="center", transform=ax.transAxes, zorder=3)
    return x + w + 0.008


def _nueva(halos=None):
    fig = plt.figure(figsize=A4, dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1], zorder=1); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.patch.set_alpha(0)
    _halos(fig, halos if halos is not None else [(0.93, 0.95, 0.30, 0.42, AZUL_CLARO, 0.55), (0.05, 0.05, 0.28, 0.40, AZUL_SUAVE, 0.9)])
    return fig, ax


def _pie(ax, pie: str, oscuro=False):
    _NUM["n"] += 1
    ax.text(0.04, 0.028, pie, fontsize=6.2, color=GRIS2, va="center")
    ax.text(0.96, 0.028, f"{_NUM['n']:02d}" + (f" / {_NUM['total']:02d}" if _NUM["total"] else ""), fontsize=6.2, color=GRIS2, va="center", ha="right")


def _marca(ax, x, y, claro=False):
    _ficha_icono(ax, "ola", x, y - 0.014, 0.022, AZUL, fuerte=True)
    ax.text(x + 0.030, y + 0.006, "Coastal Vulnerability System", fontsize=6.6, color=TINTA, **TIT, va="center")
    ax.text(x + 0.030, y - 0.009, "Geovisor científico · Universidad del Magdalena", fontsize=5.4, color=GRIS, va="center")


def _cabecera(fig, ax, titulo, sub, numero=None):
    """Cabecera clara: número de capítulo grande en azul ligero, título en negrita, subtítulo gris y línea de degradado."""
    x = 0.04
    if numero:
        ax.text(x, 0.915, numero, fontsize=30, color=AZUL_MEDIO, fontfamily=FUENTE_TITULO, fontweight="light", va="center")
        x = 0.115
    partes = titulo.split(" ", 1)
    ax.text(x, 0.93, partes[0], fontsize=15, color=TINTA, fontfamily=FUENTE_TITULO, fontweight="light", va="center")
    if len(partes) > 1:
        ax.text(x, 0.900, partes[1], fontsize=15, color=TINTA, **TIT, va="center")
    ax.text(x, 0.872, sub, fontsize=7.0, color=GRIS, va="center")
    _marca(ax, 0.775, 0.915)
    _degradado(fig, [0.04, 0.852, 0.92, 0.004], [AZUL, AZUL_CLARO, "#FFFFFF"], angulo=0, radio=0.0, zorder=1.4)


def _titulo_bloque(ax, x, y, texto, color=TINTA):
    _pildora(ax, x, y - 0.010, 0.018, 0.020, AZUL, AZUL_MEDIO, radio=0.006, borde="none", sombra=False)
    ax.text(x + 0.026, y, texto.upper(), fontsize=6.6, color=color, **TIT, va="center")


def _tabla(ax, df: pd.DataFrame, fs=6.2, col_w=None, cab="#EAF1FF"):
    ax.set_axis_off()
    if df is None or df.empty:
        ax.text(0, 0.5, "No disponible", fontsize=7, color=GRIS); return
    df = df.copy().astype(object).where(df.notna(), "—")
    t = ax.table(cellText=df.values, colLabels=list(df.columns), loc="upper left", cellLoc="left", colLoc="left", colWidths=col_w)
    t.auto_set_font_size(False); t.set_fontsize(fs); t.scale(1, 1.28)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#E6EAF2"); cell.set_linewidth(0.4)
        if r == 0:
            cell.set_facecolor(cab); cell.set_text_props(color=TINTA, **TIT)
        elif r % 2 == 0:
            cell.set_facecolor("#F8FAFE")
        else:
            cell.set_facecolor("white")


def _etapas(ax, x, y, w, h, etapas, oscuro=False):
    """Fila de etapas numeradas 01 … 04 en píldoras con degradado (como el índice de la referencia)."""
    n = len(etapas); sep = 0.012; pw = (w - sep * (n - 1)) / n
    for i, (ic, rot, sub) in enumerate(etapas):
        xi = x + i * (pw + sep)
        _pildora(ax, xi, y, pw, h, AZUL_SUAVE, "white", radio=0.022)
        ax.text(xi + 0.016, y + h * 0.5, f"{i + 1:02d}", fontsize=16, color=AZUL_MEDIO, fontfamily=FUENTE_TITULO, fontweight="light", va="center", zorder=3)
        _ficha_icono(ax, ic, xi + 0.060, y + h * 0.5 - 0.013 * A4[0] / A4[1], 0.020, AZUL)
        ax.text(xi + 0.088, y + h * 0.64, rot, fontsize=7.4, color=TINTA, **TIT, va="center", zorder=3)
        ax.text(xi + 0.088, y + h * 0.32, sub, fontsize=5.6, color=GRIS, va="center", zorder=3)


def _eje(fig, rect):
    ax = fig.add_axes(rect, zorder=2); ax.set_facecolor("none")
    ax.tick_params(labelsize=5.8, colors=GRIS, length=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_edgecolor(LINEA)
    ax.grid(alpha=0.18, lw=0.5)
    return ax


def _panel_lateral(fig, ax, numero, titulo, texto, cifras):
    """Columna izquierda clara: número de capítulo grande, título, párrafo y cifras en píldoras."""
    _cristal(ax, 0.03, 0.06, 0.27, 0.91)
    ax.text(0.055, 0.905, numero, fontsize=34, color=AZUL_MEDIO, fontfamily=FUENTE_TITULO, fontweight="light", va="center")
    y = 0.835
    lineas = titulo.split("\n")
    for i, l in enumerate(lineas):
        ax.text(0.055, y, l, fontsize=10.5, color=TINTA, fontfamily=FUENTE_TITULO, fontweight="light" if i < len(lineas) - 1 else "bold", va="center"); y -= 0.03
    y = _wrap(ax, 0.055, y - 0.008, texto, 46, 6.2, GRIS, 0.0145)
    y -= 0.006
    for v_, e_, c_ in cifras[:6]:
        h = 0.080
        if y - h < 0.075:
            break
        _kpi(ax, 0.045, y - h, 0.24, h, e_, v_, "", c_); y -= h + 0.010


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
def generar_informe(cfg: dict, carpeta: str | Path, salida: str | Path, nombre_proyecto: str | None = None, autor: str | None = None,
                    esquema: str = "ewm", campo_tasa: str = "LRR", fondo: str = "auto") -> Path:
    carpeta = Path(carpeta); salida = Path(salida)
    app = cfg.get("aplicacion", {})
    nombre_proyecto = nombre_proyecto or carpeta.name
    autor = autor or app.get("autora", "")
    hoy = dt.date.today(); fecha = hoy.strftime("%d‑%m‑%Y"); anio = hoy.year
    cita = (f"{autor} ({anio}). Coastal Vulnerability System — geovisor y calculadora del Índice de Vulnerabilidad Costera "
            f"[software, versión {VERSION_APP}]. {app.get('institucion', '')}. Proyecto «{nombre_proyecto}», informe generado el {fecha}.")
    pie = f"Coastal Vulnerability System · Informe de vulnerabilidad costera · {nombre_proyecto} · {fecha}"

    tasas = _gpkg(carpeta, "transectos_tasas.gpkg")
    indice = _gpkg(carpeta, "indice_transectos.gpkg")
    lineas = _gpkg(carpeta, "lineas_proyectadas.gpkg")
    base = _gpkg(carpeta, "linea_base.gpkg")
    val = _csv(carpeta, "validacion.csv")
    pesos = _csv(carpeta, "pesos_ewm.csv")
    pesos_todos = _csv(carpeta, "pesos_todos.csv")
    resumen = _csv(carpeta, "proyeccion_resumen.csv")
    escs = sorted(carpeta.rglob("escenario_*.gpkg"))
    meta = {}
    pj = _buscar(carpeta, "proyecto.json")
    if pj:
        import json
        try:
            meta = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
    ci, cc = f"ivc_{esquema}", f"clase_{esquema}"
    if indice is not None and ci not in indice.columns:
        ci = next((c for c in indice.columns if c.startswith("ivc_")), None); cc = ci.replace("ivc_", "clase_") if ci else None
    if tasas is not None and campo_tasa not in tasas.columns:
        campo_tasa = "LRR" if "LRR" in tasas.columns else None
    ref_geo = tasas if tasas is not None else (indice if indice is not None else lineas)
    F = Fondo(cfg, fondo, meta)
    cm_cl, vmin_cl, vmax_cl = _clase_cmap(cfg)
    etiqueta_fondo = {"arcgis": "Fondo: Esri World Imagery (ArcGIS)", "delta": "Fondo: DEM DeltaDTM con sombreado", "fondo": "Fondo: mosaico tierra/agua (IDEAM · DeltaDTM · Sentinel‑2)", "ninguno": ""}
    capa_base = [(base, dict(color="white", linewidth=0.6, alpha=0.85))] if (base is not None and len(base)) else []

    v_t = tasas[campo_tasa].dropna() if (tasas is not None and campo_tasa) else pd.Series(dtype=float)
    v_i = indice[ci].dropna() if (indice is not None and ci) else pd.Series(dtype=float)
    pct_alta = float(100 * (indice[cc] >= 4).mean()) if (indice is not None and cc in indice.columns) else np.nan
    rho = rho_inf = rho_sup = rho_e = np.nan
    if val is not None and len(val):
        f = val[val["indice"] == ci]
        if len(f):
            rho, rho_inf, rho_sup = float(f["rho"].iloc[0]), float(f["IC95_inf"].iloc[0]), float(f["IC95_sup"].iloc[0])
        fe = val[val["indice"] == "ivc_ewm_estructural"]
        if len(fe):
            rho_e = float(fe["rho"].iloc[0])
    km_costa = float(tasas["dist_costa_km"].max()) if (tasas is not None and "dist_costa_km" in tasas) else np.nan

    paginas = ["portada", "indice_resumen"]
    if len(v_t):
        paginas.append("tasas")
    if len(v_i):
        paginas.append("ivc")
    if pesos is not None or val is not None:
        paginas.append("pesos")
    if lineas is not None or resumen is not None:
        paginas.append("proyeccion")
    if escs and indice is not None:
        paginas.append("escenarios")
    paginas += ["metodologia", "contraportada"]
    _NUM["n"] = 0; _NUM["total"] = len(paginas)
    salida.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(salida) as pdf:
        # ================================================================ portada (clara, como la referencia de folleto)
        fig, ax = _nueva([(0.88, 0.78, 0.34, 0.50, AZUL_CLARO, 0.75), (0.70, 0.95, 0.25, 0.30, AZUL, 0.35), (0.02, 0.02, 0.30, 0.38, AZUL_SUAVE, 0.9)])
        _marca(ax, 0.05, 0.93)
        ax.text(0.95, 0.936, app.get("subtitulo", ""), fontsize=6.0, color=GRIS, va="center", ha="right")
        # título: primera línea ligera, segunda en negrita (estilo de la referencia)
        ax.text(0.05, 0.775, "Informe de", fontsize=30, color=TINTA, fontfamily=FUENTE_TITULO, fontweight="light", va="center")
        ax.text(0.05, 0.705, "Vulnerabilidad Costera", fontsize=30, color=TINTA, **TIT, va="center")
        ax.text(0.05, 0.650, f"{nombre_proyecto} · {anio}", fontsize=9.5, color=AZUL, **TIT, va="center")
        x = _chip(ax, 0.05, 0.600, f"Generado el {fecha}")
        x = _chip(ax, x, 0.600, f"versión {VERSION_APP}")
        _chip(ax, x, 0.600, f"esquema {esquema} · tasa {campo_tasa or 'LRR'}")
        _wrap(ax, 0.05, 0.560, "Transectos y tasas de cambio de la línea de costa, Índice de Vulnerabilidad Costera (IVC), validación espacial y proyección de escenarios, "
              "generados con la Calculadora IVC del geovisor.", 78, 6.8, GRIS, 0.0155)
        # mapa en tarjeta (derecha) + cifras en píldoras (izquierda abajo)
        if ref_geo is not None:
            _cristal(ax, 0.50, 0.14, 0.46, 0.44)
            axm = fig.add_axes([0.512, 0.175, 0.436, 0.38], zorder=2)
            capas = list(capa_base)
            if indice is not None and cc in indice.columns:
                capas.append((indice, dict(column=cc, cmap=cm_cl, vmin=vmin_cl, vmax=vmax_cl, linewidth=1.6))); sub = f"IVC por clase ({esquema})"
            elif len(v_t):
                lim = float(np.nanpercentile(np.abs(v_t), 98)) or 1
                capas.append((tasas, dict(column=campo_tasa, cmap="RdBu", vmin=-lim, vmax=lim, linewidth=1.6))); sub = f"{campo_tasa} (m/año)"
            else:
                capas.append((ref_geo, dict(color=TEAL, linewidth=1.2))); sub = "Transectos"
            usado = _mapa(axm, F, capas, ref_geo, 0.06); _escala(axm)
            ax.text(0.512, 0.155, f"{sub} · {etiqueta_fondo.get(usado, '')}", fontsize=5.6, color=GRIS2, va="center")
        fichas = []
        if len(v_t):
            fichas += [("transectos", f"{len(tasas)}", "", AZUL), (f"{campo_tasa} medio", _fmt(v_t.mean()), "m/año", CORAL), ("costa en retroceso", _fmt(100 * (v_t < 0).mean(), 1), "%", AMBAR)]
        if len(v_i):
            fichas += [(f"IVC medio ({esquema})", _fmt(v_i.mean(), 3), "0‑1", TEAL), ("clase alta + muy alta", _fmt(pct_alta, 1), "%", CORAL)]
        if np.isfinite(rho):
            fichas.append(("ρ con la tasa observada", _fmt(rho, 3), "", VERDE))
        for i, (e_, v_, u_, c_) in enumerate(fichas[:6]):
            col_, row_ = i % 2, i // 2
            _kpi(ax, 0.05 + col_ * 0.215, 0.405 - row_ * 0.092, 0.205, 0.080, e_, v_, u_, c_)
        # etapas del flujo (01 … 04) al pie
        _etapas(ax, 0.05, 0.055, 0.90, 0.070,
                [("lineas", "Líneas de costa", f"{Path(meta.get('lineas', {}).get('ruta', '')).name or 'multitemporales'} · EPSG {meta.get('epsg', '—')}"),
                 ("regla", "Tasas DSAS", f"{len(tasas) if tasas is not None else '—'} transectos · {campo_tasa or 'LRR'}"),
                 ("escudo", "Índice IVC", f"esquema {esquema} · clases 1‑5"),
                 ("cristal", "Proyección y escenarios", f"{len(escs)} escenarios SSP · 2050 · 2100")])
        _NUM["n"] += 1
        pdf.savefig(fig); plt.close(fig)

        # ================================================================ contenido + resumen ejecutivo
        fig, ax = _nueva()
        _cabecera(fig, ax, "Contenido y resumen ejecutivo", "qué incluye este informe y las cifras que lo resumen")
        nombres = {"tasas": "Dinámica de la línea de costa", "ivc": "Índice de Vulnerabilidad Costera", "pesos": "Ponderación y validación",
                   "proyeccion": "Proyección 2050 · 2100", "escenarios": "Escenarios SSP del IVC futuro", "metodologia": "Metodología y referencias"}
        _cristal(ax, 0.03, 0.09, 0.30, 0.74, "Contenido", AZUL)
        y = 0.74; n = 2
        for k in paginas[2:-1]:
            n += 1
            ax.text(0.05, y + 0.001, f"{n:02d}", fontsize=15, color=AZUL_MEDIO, fontfamily=FUENTE_TITULO, fontweight="light", va="center")
            _ficha_icono(ax, _ic_de(nombres.get(k, k)), 0.098, y - 0.014, 0.020, AZUL)
            ax.text(0.126, y + 0.001, nombres.get(k, k), fontsize=7.6, color=TINTA, va="center")
            ax.add_patch(plt.Rectangle((0.05, y - 0.03), 0.26, 0.0007, facecolor=LINEA, edgecolor="none"))
            y -= 0.075
        _cristal(ax, 0.35, 0.44, 0.62, 0.39, "Resumen ejecutivo", TEAL2)
        yy = 0.77
        res_txt = []
        if len(v_t):
            res_txt.append(f"Se analizaron {len(tasas)} transectos a lo largo de {_fmt(km_costa, 1)} km de costa. La tasa {campo_tasa} media es {_fmt(v_t.mean())} m/año "
                           f"(mediana {_fmt(v_t.median())}); el {_fmt(100 * (v_t < 0).mean(), 1)} % del litoral está en retroceso.")
        if len(v_i):
            res_txt.append(f"El IVC medio ({esquema}) es {_fmt(v_i.mean(), 3)} en la escala 0‑1 y el {_fmt(pct_alta, 1)} % de los transectos queda en clase alta o muy alta.")
        if np.isfinite(rho):
            res_txt.append(f"El índice se validó frente a la tasa observada: ρ de Spearman = {_fmt(rho, 3)} (IC95 {_fmt(rho_inf, 3)}–{_fmt(rho_sup, 3)}, bootstrap de bloques espaciales)"
                           + (f"; el índice estructural, sin la tasa, alcanza ρ = {_fmt(rho_e, 3)}." if np.isfinite(rho_e) else "."))
        if resumen is not None and len(resumen):
            r = resumen.set_index("clave"); esc_k = [k for k in r.index if k != "actual"]
            if esc_k:
                res_txt.append("Escenarios: " + "; ".join(f"{r.loc[k, 'escenario']} → {_fmt(r.loc[k, 'pct_alta_muy_alta'], 1)} % alta+muy alta" for k in esc_k) + ".")
        for t in res_txt:
            yy = _wrap(ax, 0.37, yy, t, 112, 7.2, TINTA, 0.0165)
        fichas = []
        if len(v_t):
            fichas += [("transectos analizados", f"{len(tasas)}", "", AZUL), (f"{campo_tasa} medio", _fmt(v_t.mean()), "m/año", CORAL), ("de la costa en retroceso", _fmt(100 * (v_t < 0).mean(), 0), "%", AMBAR)]
        if len(v_i):
            fichas += [(f"IVC medio ({esquema})", _fmt(v_i.mean(), 3), "0‑1", TEAL2), ("clase alta + muy alta", _fmt(pct_alta, 1), "%", CORAL)]
        if np.isfinite(rho):
            fichas.append(("ρ con la tasa observada", _fmt(rho, 2), "", VERDE))
        _titulo_bloque(ax, 0.35, 0.405, "Cifras clave")
        for i, (e_, v_, u_, c_) in enumerate(fichas[:6]):
            _kpi(ax, 0.35 + (i % 3) * 0.212, 0.245 - (i // 3) * 0.145, 0.20, 0.125, e_, v_, u_, c_)
        _pie(ax, pie)
        pdf.savefig(fig); plt.close(fig)

        # ================================================================ capítulo tasas
        if "tasas" in paginas:
            fig, ax = _nueva()
            _panel_lateral(fig, ax, "03", "Dinámica de\nla línea de costa",
                           "Tasas por transecto con las definiciones de DSAS v6.1: NSM, SCE, EPR, LRR (regresión lineal con IC95) y WLR. Valor negativo = retroceso hacia tierra.",
                           [(f"{len(tasas)}", "transectos", AZUL), (f"{_fmt(km_costa, 1)} km", "longitud de costa", TEAL), (f"{_fmt(v_t.mean())} m/año", f"{campo_tasa} medio", CORAL),
                            (f"{_fmt(v_t.median())} m/año", f"{campo_tasa} mediano", CORAL), (f"{_fmt(100 * (v_t < 0).mean(), 1)} %", "de la costa en retroceso", AMBAR),
                            (f"{_fmt(v_t.min())} m/año", "retroceso máximo", "#FF8A80")])
            r = _cristal(ax, 0.32, 0.50, 0.65, 0.47, f"Mapa de {campo_tasa} (m/año; negativo = retroceso)", CORAL)
            axm = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2)
            lim = float(np.nanpercentile(np.abs(v_t), 98)) or 1.0
            capas = list(capa_base) + [(tasas, dict(column=campo_tasa, cmap="RdBu", vmin=-lim, vmax=lim, linewidth=1.7, legend=True,
                                                     legend_kwds={"shrink": 0.6, "label": f"{campo_tasa} (m/año)", "pad": 0.01}))]
            usado = _mapa(axm, F, capas, tasas); _escala(axm)
            ax.text(0.34, 0.508, etiqueta_fondo.get(usado, ""), fontsize=5.6, color=GRIS2, va="center")
            r = _cristal(ax, 0.32, 0.07, 0.25, 0.40, f"Distribución de {campo_tasa}", AZUL)
            axh = _eje(fig, [r[0] + 0.03, r[1] + 0.045, r[2] - 0.04, r[3] - 0.06])
            axh.hist(v_t, bins=36, color=AZUL, alpha=0.9); axh.axvline(0, color=CORAL, lw=0.9, ls="--"); axh.set_xlabel("m/año", fontsize=5.8, color=GRIS)
            r = _cristal(ax, 0.59, 0.07, 0.38, 0.40, "Perfil a lo largo de la costa (rojo = retroceso; banda = IC95)", TEAL2)
            axp = _eje(fig, [r[0] + 0.03, r[1] + 0.045, r[2] - 0.04, r[3] - 0.06])
            if "dist_costa_km" in tasas:
                d = tasas.sort_values("dist_costa_km")
                axp.fill_between(d["dist_costa_km"], 0, d[campo_tasa], where=d[campo_tasa] < 0, color=CORAL, alpha=0.65, step="mid")
                axp.fill_between(d["dist_costa_km"], 0, d[campo_tasa], where=d[campo_tasa] >= 0, color=TEAL2, alpha=0.65, step="mid")
                if "LCI95" in d and campo_tasa == "LRR":
                    axp.fill_between(d["dist_costa_km"], d["LRR"] - d["LCI95"], d["LRR"] + d["LCI95"], color=AZUL, alpha=0.12, step="mid")
                axp.set_xlabel("Distancia a lo largo de la costa (km)", fontsize=5.8, color=GRIS); axp.set_ylabel("m/año", fontsize=5.8, color=GRIS)
            _pie(ax, pie)
            pdf.savefig(fig); plt.close(fig)

        # ================================================================ capítulo IVC
        if "ivc" in paginas:
            fig, ax = _nueva()
            cl = indice[cc].dropna(); pct = {k: float(100 * (cl == k).mean()) for k in range(1, 6)}
            cif = [(f"{_fmt(v_i.mean(), 3)}", "IVC medio (0‑1)", TEAL), (f"{_fmt(v_i.median(), 3)}", "IVC mediano", TEAL), (f"{_fmt(pct[4] + pct[5], 1)} %", "clase alta + muy alta", CORAL),
                   (f"{_fmt(pct[3], 1)} %", "clase moderada", AMBAR), (f"{_fmt(pct[1] + pct[2], 1)} %", "clase baja + muy baja", VERDE)]
            if np.isfinite(rho):
                cif.append((f"{_fmt(rho, 2)}", f"ρ con la tasa (IC95 {_fmt(rho_inf, 2)}–{_fmt(rho_sup, 2)})", AZUL))
            _panel_lateral(fig, ax, "04", "Índice de\nvulnerabilidad\ncostera",
                           f"IVC = (Σ wᵢ·cᵢ − 1)/4 con las clases 1‑5 de cada variable y los pesos del esquema «{esquema}». Clases por intervalos de 0,2: 1 muy baja … 5 muy alta.", cif)
            r = _cristal(ax, 0.32, 0.50, 0.65, 0.47, "Mapa del IVC por clase", CORAL)
            axm = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2)
            capas = list(capa_base) + [(indice, dict(column=cc, cmap=cm_cl, vmin=vmin_cl, vmax=vmax_cl, linewidth=1.8))]
            usado = _mapa(axm, F, capas, indice); _escala(axm); _leyenda_clases(axm, cfg)
            ax.text(0.34, 0.508, etiqueta_fondo.get(usado, ""), fontsize=5.6, color=GRIS2, va="center")
            r = _cristal(ax, 0.32, 0.07, 0.25, 0.40, "Transectos por clase", AMBAR)
            axb = _eje(fig, [r[0] + 0.03, r[1] + 0.045, r[2] - 0.04, r[3] - 0.06])
            clases = cfg["ivc"]["clases"]
            axb.bar([f"{k}" for k in range(1, 6)], [pct[k] for k in range(1, 6)], color=[clases[k]["color"] for k in range(1, 6)], width=0.65)
            for k in range(1, 6):
                axb.text(k - 1, pct[k] + 1, f"{pct[k]:.1f} %", ha="center", fontsize=5.6, color=TINTA)
            axb.set_ylim(0, max(pct.values()) * 1.3 + 1); axb.set_ylabel("% transectos", fontsize=5.8, color=GRIS)
            r = _cristal(ax, 0.59, 0.07, 0.38, 0.40, "Perfil del IVC a lo largo de la costa (punteado = cortes de clase)", TEAL2)
            axp = _eje(fig, [r[0] + 0.03, r[1] + 0.045, r[2] - 0.04, r[3] - 0.06])
            if "dist_costa_km" in indice:
                d = indice.sort_values("dist_costa_km")
                axp.plot(d["dist_costa_km"], d[ci], color=AZUL, lw=1.0)
                axp.fill_between(d["dist_costa_km"], 0, d[ci], color=AZUL, alpha=0.12)
                for c0 in (0.2, 0.4, 0.6, 0.8):
                    axp.axhline(c0, color=GRIS2, lw=0.5, ls="--")
                axp.set_ylim(0, 1); axp.set_xlabel("Distancia a lo largo de la costa (km)", fontsize=5.8, color=GRIS); axp.set_ylabel("IVC (0‑1)", fontsize=5.8, color=GRIS)
            _pie(ax, pie)
            pdf.savefig(fig); plt.close(fig)

        # ================================================================ pesos y validación
        if "pesos" in paginas:
            fig, ax = _nueva()
            _cabecera(fig, ax, "Ponderación y validación", "pesos por entropía (EWM), FAHP y validación espacial del índice", "05")
            if pesos is not None and len(pesos):
                r = _cristal(ax, 0.03, 0.44, 0.62, 0.39, "Pesos EWM con IC95 por bootstrap de bloques · punteado = pesos iguales", AZUL)
                axw = _eje(fig, [r[0] + 0.03, r[1] + 0.07, r[2] - 0.04, r[3] - 0.08])
                nom = pesos["variable"] if "variable" in pesos else pd.Series([f"v{i}" for i in range(len(pesos))])
                err = [pesos["peso"] - pesos["IC95_inf"], pesos["IC95_sup"] - pesos["peso"]] if "IC95_inf" in pesos else None
                axw.bar(range(len(pesos)), pesos["peso"], color=AZUL, yerr=err, capsize=2, error_kw={"lw": 0.6, "ecolor": GRIS})
                axw.axhline(1 / len(pesos), color=CORAL, ls=":", lw=0.9)
                axw.set_xticks(range(len(pesos))); axw.set_xticklabels(nom, rotation=40, ha="right", fontsize=5.2)
                if pesos_todos is not None and len(pesos_todos):
                    r = _cristal(ax, 0.67, 0.44, 0.30, 0.39, "Pesos por esquema", AMBAR)
                    axt = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2); _tabla(axt, pesos_todos.round(3), 5.2)
            if val is not None and len(val):
                r = _cristal(ax, 0.03, 0.07, 0.94, 0.34, "Validación frente a la tasa observada — ρ de Spearman índice vs −tasa, IC95 por bloques espaciales («circular» = incluye la tasa)", TEAL2)
                v2 = val.copy()
                for c in ("rho", "IC95_inf", "IC95_sup"):
                    if c in v2:
                        v2[c] = v2[c].round(3)
                if "p" in v2:
                    v2["p"] = v2["p"].map(lambda x_: f"{x_:.1e}" if pd.notna(x_) else "—")
                axv = fig.add_axes([r[0], r[1] + 0.05, r[2], r[3] - 0.05], zorder=2); _tabla(axv, v2, 6.0)
                _wrap(ax, r[0], r[1] + 0.045, "El IC95 se obtiene por bootstrap de bloques espaciales contiguos (respeta la autocorrelación a lo largo de la costa); el índice estructural excluye la tasa y evita la circularidad.",
                      190, 6.2, GRIS, 0.013)
            _pie(ax, pie)
            pdf.savefig(fig); plt.close(fig)

        # ================================================================ proyección
        if "proyeccion" in paginas:
            fig, ax = _nueva()
            pr = meta.get("proyeccion", {})
            cif = []
            if resumen is not None and len(resumen):
                rr = resumen.set_index("clave")
                for k in [k for k in rr.index if k != "actual"][:4]:
                    cif.append((f"{_fmt(rr.loc[k, 'pct_alta_muy_alta'], 1)} %", f"alta + muy alta · {rr.loc[k, 'escenario']}", CORAL))
                if "retroceso_mediana_m" in rr:
                    for k in [k for k in rr.index if k != "actual" and str(k).endswith("2100")][:1]:
                        cif.append((f"{_fmt(rr.loc[k, 'retroceso_mediana_m'], 0)} m", "retroceso mediano a 2100", AMBAR))
            _panel_lateral(fig, ax, "06", "Proyección\n2050 · 2100",
                           f"Transición «{pr.get('modelo', 'amortiguada')}» de la tasa por ventanas de {pr.get('ventana_anios', 21)} años, validada en bloques con zona de exclusión; Monte Carlo ({pr.get('n_mc', 1000)} réplicas), banda p05–p95.", cif)
            r = _cristal(ax, 0.32, 0.50, 0.65, 0.47, "Líneas proyectadas (central, banda p05–p95 y persistencia)", CORAL)
            axm = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2)
            if lineas is not None and len(lineas):
                colores = {"observada": "#FFD166", "central": CORAL, "p05": "#FFB38A", "p95": "#FFB38A", "persistencia": "#B388FF"}
                capas = []
                for (tipo, _an), g in lineas.groupby(["tipo", "anio"]):
                    capas.append((g, dict(color=colores.get(tipo, GRIS), linewidth=1.5 if tipo in ("observada", "central") else 0.7, linestyle="--" if tipo in ("p05", "p95", "persistencia") else "-")))
                usado = _mapa(axm, F, capas, lineas); _escala(axm)
                from matplotlib.lines import Line2D

                h = [Line2D([0], [0], color=colores["observada"], lw=2, label="observada"), Line2D([0], [0], color=colores["central"], lw=2, label="central 2050/2100"),
                     Line2D([0], [0], color=colores["p05"], lw=1, ls="--", label="p05–p95"), Line2D([0], [0], color=colores["persistencia"], lw=1, ls="--", label="persistencia")]
                lg = axm.legend(handles=h, loc="lower left", fontsize=5.4, frameon=True, framealpha=0.92, edgecolor=LINEA); lg.get_frame().set_linewidth(0.5)
                ax.text(0.34, 0.508, etiqueta_fondo.get(usado, ""), fontsize=5.6, color=GRIS2, va="center")
            if resumen is not None and len(resumen):
                r = _cristal(ax, 0.32, 0.07, 0.28, 0.40, "% alta + muy alta por escenario (punteado = actual)", AMBAR)
                axb = _eje(fig, [r[0] + 0.03, r[1] + 0.06, r[2] - 0.04, r[3] - 0.08])
                rr = resumen[resumen["clave"] != "actual"] if "clave" in resumen else resumen
                axb.bar(rr["escenario"], rr["pct_alta_muy_alta"], color=[AZUL, AZUL_OSC, CORAL, "#C8503B"][: len(rr)], width=0.6)
                if "pct_alta_mc_p05" in rr:
                    axb.errorbar(rr["escenario"], rr["pct_alta_muy_alta"], yerr=[rr["pct_alta_muy_alta"] - rr["pct_alta_mc_p05"], rr["pct_alta_mc_p95"] - rr["pct_alta_muy_alta"]], fmt="none", ecolor=GRIS, capsize=3, lw=0.7)
                act = resumen[resumen["clave"] == "actual"] if "clave" in resumen else pd.DataFrame()
                if len(act):
                    axb.axhline(float(act["pct_alta_muy_alta"].iloc[0]), color=GRIS, ls=":", lw=0.8)
                plt.setp(axb.get_xticklabels(), rotation=15, ha="right"); axb.set_ylabel("%", fontsize=5.8, color=GRIS)
                r = _cristal(ax, 0.62, 0.07, 0.35, 0.40, "Resumen por escenario", TEAL2)
                cols = [c for c in ("escenario", "pct_clase_2", "pct_clase_3", "pct_clase_4", "pct_alta_muy_alta", "ivc_medio", "retroceso_mediana_m") if c in resumen]
                axt = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2)
                _tabla(axt, resumen[cols].round(2).rename(columns={"pct_clase_2": "% c2", "pct_clase_3": "% c3", "pct_clase_4": "% c4", "pct_alta_muy_alta": "% alta+", "ivc_medio": "IVC", "retroceso_mediana_m": "retr. (m)"}), 5.6)
            _pie(ax, pie)
            pdf.savefig(fig); plt.close(fig)

        # ================================================================ escenarios (4 mapas)
        if "escenarios" in paginas:
            import geopandas as gpd

            fig, ax = _nueva()
            _cabecera(fig, ax, "Escenarios SSP", "IVC futuro por clase: nivel del mar AR6, retroceso proyectado y pesos fijos", "07")
            usado = "ninguno"
            for i, e in enumerate(escs[:4]):
                g = gpd.read_file(e); k = e.stem.replace("escenario_", "")
                ccol = f"clase_{k}" if f"clase_{k}" in g.columns else next((c for c in g.columns if c.startswith("clase")), None)
                if not ccol:
                    continue
                x0 = 0.03 + (i % 2) * 0.475; y0 = 0.455 - (i // 2) * 0.375
                nombre = k.replace("ssp245_", "SSP2-4.5 · ").replace("ssp585_", "SSP5-8.5 · ").replace("ssp245", "SSP2-4.5").replace("ssp585", "SSP5-8.5")
                r = _cristal(ax, x0, y0, 0.465, 0.37, f"{nombre} — {100 * (g[ccol] >= 4).mean():.1f} % alta + muy alta", [AZUL, TEAL2, AMBAR, CORAL][i % 4])
                axm = fig.add_axes([r[0], r[1], r[2], r[3]], zorder=2)
                capas = list(capa_base) + [(g, dict(column=ccol, cmap=cm_cl, vmin=vmin_cl, vmax=vmax_cl, linewidth=1.5))]
                usado = _mapa(axm, F, capas, g); _escala(axm)
                if i == 0:
                    _leyenda_clases(axm, cfg)
            ax.text(0.03, 0.062, etiqueta_fondo.get(usado, "") + "  ·  En cada escenario se reclasifican la tasa, el ancho de la barra, la distancia a la infraestructura y el % bajo el nivel del mar; las demás variables y los pesos se mantienen fijos.",
                    fontsize=5.8, color=GRIS, va="center")
            _pie(ax, pie)
            pdf.savefig(fig); plt.close(fig)

        # ================================================================ metodología
        fig, ax = _nueva()
        _cabecera(fig, ax, "Metodología y referencias", "parámetros del proyecto tal como quedaron en proyecto.json", "08")
        tr = meta.get("transectos", {}); ln = meta.get("lineas", {}); pr = meta.get("proyeccion", {}); ind = meta.get("indice", {}); po = meta.get("ponderacion", {})
        bloques = [
            ("Insumos", f"Líneas de costa: {Path(ln.get('ruta', '')).name or '—'} (campo de fecha «{ln.get('campo_fecha', '—')}», incertidumbre «{ln.get('campo_unc') or 'por defecto ' + str(ln.get('unc_defecto', ''))}»). EPSG métrica {meta.get('epsg', '—')}."),
            ("Transectos y tasas", f"Origen {tr.get('modo', '—')}; espaciado {tr.get('espaciado_m', '—')} m, longitud {tr.get('longitud_m', '—')} m, suavizado {tr.get('suavizado_m', '—')} m, mínimo {tr.get('umbral_lineas', '—')} líneas, intersección «{tr.get('criterio', 'cercana')}». "
                                   "Tasas DSAS v6.1: NSM, SCE, EPR (± EPRunc), LRR (R², LSE, LCI95 con t de Student), WLR (pesos 1/σ²)."),
            ("Variables", (", ".join(f"{v.get('nombre', v.get('codigo'))} [{v.get('normalizacion', 'umbrales')}]" for v in meta.get("variables", [])) or "—") + "."),
            ("Ponderación", f"Esquema principal «{po.get('esquema_principal', 'ewm')}». EWM: entropía de Shannon (d_j = 1 − e_j; w_j = d_j/Σd) con IC95 por bootstrap de bloques e iid. FAHP: números triangulares (δ = {po.get('fahp', {}).get('delta', 1)}), método {po.get('fahp', {}).get('metodo', 'buckley')}, CR de Saaty ≤ 0,10."),
            ("Índice y validación", f"IVC = (Σ w·c − 1)/4 en 0‑1; clases por cortes {ind.get('cortes', [0.2, 0.4, 0.6, 0.8])}; TOPSIS (ideal absoluto y relativo) y CVI de Gornitz. ρ de Spearman frente a −{ind.get('tasa_validacion', 'LRR')} con IC95 por bootstrap de {ind.get('n_bloques', 8)} bloques; índice estructural; κ ponderado, VIF, sensibilidad y estabilidad de clase."),
            ("Proyección", f"Ventanas de {pr.get('ventana_anios', 21)} años; modelo «{pr.get('modelo', 'amortiguada')}» validado en {pr.get('n_bloques', 8)} bloques con exclusión de {pr.get('buffer_km', 3)} km; Monte Carlo ({pr.get('n_mc', 1000)} réplicas) con residuos fuera de bloque y σ regional; horizontes {pr.get('horizontes', [2050, 2100])}; escenarios "
                           + (", ".join(f"{e.get('nombre')} {e.get('anio')} ({e.get('slr_mm')} mm)" for e in pr.get("escenarios", [])) or "—") + "."),
        ]
        _cristal(ax, 0.03, 0.07, 0.56, 0.76, "Metodología implementada", AZUL)
        y = 0.765
        for tit, txt in bloques:
            _titulo_bloque(ax, 0.05, y, tit); y -= 0.022
            y = _wrap(ax, 0.05, y, txt, 110, 6.2, TINTA, 0.0135)
        refs = ["Bruun, P. (1962). Sea-level rise as a cause of shore erosion. Journal of the Waterways and Harbors Division, 88(1), 117–130.",
                "Buckley, J. J. (1985). Fuzzy hierarchical analysis. Fuzzy Sets and Systems, 17(3), 233–247. https://doi.org/10.1016/0165-0114(85)90090-9",
                "Chang, D.-Y. (1996). Applications of the extent analysis method on fuzzy AHP. European Journal of Operational Research, 95(3), 649–655. https://doi.org/10.1016/0377-2217(95)00300-2",
                "Gornitz, V. (1991). Global coastal hazards from future sea level rise. Palaeogeography, Palaeoclimatology, Palaeoecology, 89(4), 379–398. https://doi.org/10.1016/0031-0182(91)90173-O",
                "Himmelstoss, E. A., Henderson, R. E., Kratzmann, M. G., & Farris, A. S. (2021). Digital Shoreline Analysis System (DSAS) version 5.1 user guide (Open-File Report 2021‑1091). U.S. Geological Survey. https://doi.org/10.3133/ofr20211091",
                "Hwang, C.-L., & Yoon, K. (1981). Multiple attribute decision making: Methods and applications. Springer. https://doi.org/10.1007/978-3-642-48318-9",
                "Saaty, T. L. (1980). The analytic hierarchy process. McGraw-Hill.",
                "Shannon, C. E. (1948). A mathematical theory of communication. Bell System Technical Journal, 27(3), 379–423. https://doi.org/10.1002/j.1538-7305.1948.tb01338.x"]
        _cristal(ax, 0.61, 0.07, 0.36, 0.76, "Referencias (APA 7.ª)", TEAL2)
        y = 0.765
        for r_ in refs:
            y = _wrap(ax, 0.63, y, r_, 68, 5.6, GRIS, 0.0122)
        _pie(ax, pie)
        pdf.savefig(fig); plt.close(fig)

        # ================================================================ contraportada
        fig, ax = _nueva([(0.10, 0.90, 0.32, 0.45, AZUL_CLARO, 0.7), (0.95, 0.05, 0.30, 0.40, AZUL_SUAVE, 0.9)])
        _cristal(ax, 0.20, 0.25, 0.60, 0.50)
        _marca(ax, 0.235, 0.685)
        ax.text(0.235, 0.630, f"Proyecto «{nombre_proyecto}» · Informe de vulnerabilidad costera {anio}", fontsize=7, color=GRIS, va="center")
        _titulo_bloque(ax, 0.235, 0.585, "Cómo citar")
        y = _wrap(ax, 0.235, 0.560, cita, 100, 6.8, TINTA, 0.0155)
        _wrap(ax, 0.235, y - 0.01, "Los resultados reproducen las definiciones de DSAS v6.1 y los métodos de la tesis; el motor de cálculo fue auditado y verificado frente a los productos oficiales "
              "(docs/AUDITORIA_CALCULADORA.md del repositorio). Este informe es un producto automático de apoyo a la decisión y no sustituye el juicio experto.", 100, 6.2, GRIS, 0.0135)
        ax.text(0.04, 0.04, f"{app.get('institucion', '')}  ·  {autor}", fontsize=6.4, color=GRIS2, va="center")
        ax.text(0.96, 0.04, f"{fecha} · versión {VERSION_APP}", fontsize=6.4, color=GRIS2, va="center", ha="right")
        _NUM["n"] += 1
        pdf.savefig(fig); plt.close(fig)
    return salida
