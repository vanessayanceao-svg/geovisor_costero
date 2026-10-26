"""Fase 1 — inventario de archivos geoespaciales y generación del catálogo de datos.

El inventario recorre las carpetas configuradas, identifica los formatos
compatibles y registra, para cada archivo: ruta, tamaño, fecha de modificación,
tipo, CRS, extensión, geometría, capas y atributos. Nunca modifica los
archivos originales y no carga rásteres completos: solo lee sus cabeceras.

Las escenas Landsat de CoastSat (``data/<sitio>/<satélite>/ms/*.tif``) se
catalogan a partir del nombre del archivo y de su ``meta/*.txt`` (que incluye
el EPSG), sin abrir cada GeoTIFF, porque son miles de archivos.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

import pandas as pd

_log = logging.getLogger("geovisor.inventario")

EXT_VECTOR = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".kmz"}
EXT_RASTER = {".tif", ".tiff"}
EXT_TABLA = {".csv", ".xlsx"}
EXT_TODAS = EXT_VECTOR | EXT_RASTER | EXT_TABLA
TAMANO_MAX_INSPECCION = 150 * 1024 * 1024  # 150 MB: por encima solo se registra el tamaño

# Patrones de fecha en nombres de archivo (del más específico al más general)
_RE_FECHAS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"), "%Y-%m-%d-%H-%M-%S"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),
    (re.compile(r"(\d{4})_(\d{2})_(\d{2})"), "%Y_%m_%d"),
    (re.compile(r"(?<!\d)(\d{8})(?!\d)"), "%Y%m%d"),
]
_RE_ANIOS = re.compile(r"(?<!\d)((?:19[7-9]|20[0-9])\d)(?!\d)")
_RE_ESCENA = re.compile(r"^(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_(L\d|S2)_(\w+?)_(bs_[\w]+?)_(ms|mask|pan|swir)\.tif$")


@dataclass
class Entrada:
    ruta: str
    nombre: str
    carpeta_raiz: str
    categoria: str          # vector | raster | tabla | escena_landsat
    extension: str
    tamano_bytes: int
    modificado: str
    crs: str | None = None
    epsg: int | None = None
    bounds: list | None = None
    tipo_geometria: str | None = None
    n_entidades: int | None = None
    capas: list = field(default_factory=list)
    atributos: list = field(default_factory=list)
    fechas_nombre: list = field(default_factory=list)
    anios_nombre: list = field(default_factory=list)
    satelite: str | None = None
    sitio: str | None = None
    n_bandas: int | None = None
    resolucion: list | None = None
    tipo_dato: str | None = None
    nodata: float | None = None
    inspeccionado: bool = False
    error: str | None = None


def fechas_en_nombre(nombre: str) -> tuple[list[str], list[int]]:
    """Detecta fechas y años en un nombre de archivo (no se asume nada: solo se informa)."""
    fechas: list[str] = []
    texto = nombre
    for patron, formato in _RE_FECHAS:
        for m in patron.finditer(texto):
            try:
                f = datetime.strptime(m.group(0), formato)
                if 1970 <= f.year <= 2100:
                    fechas.append(f.isoformat())
            except ValueError:
                continue
        if fechas:
            break
    anios = sorted({int(a) for a in _RE_ANIOS.findall(nombre)})
    return sorted(set(fechas)), anios


def _inspeccionar_vector(p: Path, entrada: Entrada) -> None:
    import pyogrio

    capas = pyogrio.list_layers(str(p))
    entrada.capas = [str(c[0]) for c in capas]
    # Capa principal = primera capa con geometría (GPKG de DSAS tiene tablas internas)
    capa_principal = None
    for nombre, geom in capas:
        if geom is not None and not str(nombre).startswith(("idx_", "SE_", "views_", "virts_", "spatial", "geometry_columns", "rl2", "raster_", "vector_", "ISO_", "wms_")):
            capa_principal = nombre
            break
    if capa_principal is None:
        capa_principal = capas[0][0]
    info = pyogrio.read_info(str(p), layer=capa_principal)
    if info.get("crs") is None and len(capas) > 1:
        # GPKG con tablas internas (p. ej. proyecto DSAS): buscar la primera capa con CRS
        for nombre, _ in capas:
            try:
                alt = pyogrio.read_info(str(p), layer=nombre)
            except Exception:  # noqa: BLE001
                continue
            if alt.get("crs") is not None:
                info, capa_principal = alt, nombre
                break
    entrada.capas = [capa_principal] + [c for c in entrada.capas if c != capa_principal]
    if info.get("crs") is None:
        entrada.error = "CRS no legible con GDAL (contenedor SpatiaLite/DSAS); no se dibuja. Use las capas exportadas a Shapefile/GeoJSON."
    crs = info.get("crs")
    entrada.crs = str(crs) if crs else None
    entrada.epsg = _epsg_de_crs(crs)
    tb = info.get("total_bounds")
    entrada.bounds = [float(x) for x in tb] if tb is not None else None
    entrada.tipo_geometria = info.get("geometry_type")
    entrada.n_entidades = int(info.get("features", -1))
    entrada.atributos = [str(f) for f in info.get("fields", [])][:80]
    entrada.inspeccionado = True


def _epsg_de_crs(crs) -> int | None:
    if crs is None:
        return None
    try:
        from pyproj import CRS

        return CRS.from_user_input(crs).to_epsg()
    except Exception:  # noqa: BLE001
        m = re.search(r"EPSG:(\d+)", str(crs))
        return int(m.group(1)) if m else None


def _inspeccionar_raster(p: Path, entrada: Entrada) -> None:
    import rasterio

    with rasterio.open(p) as src:
        entrada.crs = str(src.crs) if src.crs else None
        entrada.epsg = src.crs.to_epsg() if src.crs else None
        entrada.bounds = [float(x) for x in src.bounds]
        entrada.n_bandas = src.count
        entrada.resolucion = [float(src.res[0]), float(src.res[1])]
        entrada.tipo_dato = str(src.dtypes[0])
        entrada.nodata = None if src.nodata is None else float(src.nodata)
        entrada.tipo_geometria = f"raster {src.width}x{src.height}"
    entrada.inspeccionado = True


def _inspeccionar_tabla(p: Path, entrada: Entrada) -> None:
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p, nrows=5, encoding_errors="replace")
        entrada.atributos = [str(c) for c in df.columns][:80]
        cols = [c.lower() for c in df.columns]
        if any(c in cols for c in ("lon", "lat", "x", "y", "longitud", "latitud", "lon_p0", "x_p0")):
            entrada.tipo_geometria = "tabla con coordenadas"
        else:
            entrada.tipo_geometria = "tabla"
    else:
        try:
            import openpyxl  # noqa: F401

            xl = pd.ExcelFile(p)
            entrada.capas = xl.sheet_names[:40]
            entrada.tipo_geometria = "libro Excel"
        except Exception as e:  # noqa: BLE001
            entrada.error = f"Excel no legible: {e}"
    entrada.inspeccionado = True


def _escena_landsat(p: Path, raiz: Path) -> Entrada | None:
    m = _RE_ESCENA.match(p.name)
    if not m:
        return None
    fecha, sat, tile, sitio, producto = m.groups()
    st = p.stat()
    e = Entrada(
        ruta=str(p), nombre=p.name, carpeta_raiz=str(raiz), categoria="escena_landsat",
        extension=".tif", tamano_bytes=st.st_size,
        modificado=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        satelite=sat, sitio=sitio, tipo_geometria=f"escena {producto}",
    )
    e.fechas_nombre, e.anios_nombre = fechas_en_nombre(p.name)
    # EPSG verificado en el meta/*.txt que CoastSat escribe junto a cada escena
    meta = p.parent.parent / "meta" / (p.name.replace(f"_{producto}.tif", ".txt"))
    if meta.exists():
        try:
            for linea in meta.read_text(encoding="utf-8", errors="replace").splitlines():
                if linea.lower().startswith("epsg"):
                    e.epsg = int(linea.split()[-1])
                    e.crs = f"EPSG:{e.epsg}"
                elif linea.lower().startswith("acc_georef"):
                    e.error = None
            e.inspeccionado = e.epsg is not None
        except Exception as ex:  # noqa: BLE001
            e.error = f"meta no legible: {ex}"
    return e


def inventariar(raices: dict[str, Path], excluir_dirs: tuple[str, ...] = ("__pycache__", ".git", "Claude outputs", "Word_fuentes", "Word_fuentes_v4", "Word_fuentes_resultados", "qa_render_font_review", "_qa_yance", "Referencias_zotero"),
                inspeccionar: bool = True) -> list[Entrada]:
    """Recorre las raíces y devuelve la lista de entradas del catálogo."""
    entradas: list[Entrada] = []
    for etiqueta, raiz in raices.items():
        raiz = Path(raiz)
        if not raiz.exists():
            _log.warning("Raíz no encontrada: %s (%s)", etiqueta, raiz)
            continue
        for carpeta, dirs, archivos in os.walk(raiz):
            dirs[:] = [d for d in dirs if d not in excluir_dirs]
            carpeta_p = Path(carpeta)
            es_coastsat_data = "data" in carpeta_p.parts and carpeta_p.parts[-1] in ("ms", "mask", "pan", "swir") and etiqueta == "coastsat_data"
            for nombre in archivos:
                p = carpeta_p / nombre
                ext = p.suffix.lower()
                if ext not in EXT_TODAS or nombre.startswith("~$"):
                    continue
                if es_coastsat_data or (etiqueta == "coastsat_data" and ext in EXT_RASTER):
                    e = _escena_landsat(p, raiz)
                    if e is not None:
                        entradas.append(e)
                        continue
                if etiqueta == "coastsat_data" and ext in EXT_TABLA:
                    continue  # tablas internas de CoastSat (no son capas)
                try:
                    st = p.stat()
                except OSError as ex:
                    _log.warning("No se pudo leer %s: %s", p, ex)
                    continue
                categoria = "vector" if ext in EXT_VECTOR else "raster" if ext in EXT_RASTER else "tabla"
                if ext == ".json" and not _parece_geojson(p):
                    continue
                e = Entrada(
                    ruta=str(p), nombre=nombre, carpeta_raiz=str(raiz), categoria=categoria, extension=ext,
                    tamano_bytes=st.st_size,
                    modificado=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                )
                e.fechas_nombre, e.anios_nombre = fechas_en_nombre(nombre)
                if inspeccionar:
                    if st.st_size > TAMANO_MAX_INSPECCION and categoria == "vector" and ext != ".gpkg":
                        e.error = "no inspeccionado: archivo mayor de 150 MB (se cataloga por tamaño)"
                    else:
                        try:
                            if categoria == "vector":
                                _inspeccionar_vector(p, e)
                            elif categoria == "raster":
                                _inspeccionar_raster(p, e)
                            else:
                                _inspeccionar_tabla(p, e)
                        except Exception as ex:  # noqa: BLE001
                            e.error = f"{type(ex).__name__}: {ex}"[:300]
                entradas.append(e)
    return entradas


def _parece_geojson(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            inicio = f.read(400).decode("utf-8", errors="ignore")
        return '"type"' in inicio and ("Feature" in inicio or "Geometry" in inicio)
    except OSError:
        return False


def guardar_catalogo(entradas: list[Entrada], carpeta: Path) -> tuple[Path, Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    registros = [asdict(e) for e in entradas]
    ruta_json = carpeta / "catalogo_datos.json"
    ruta_csv = carpeta / "catalogo_datos.csv"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump({"generado": datetime.now().isoformat(timespec="seconds"), "n": len(registros), "entradas": registros}, f, ensure_ascii=False, indent=1)
    df = pd.DataFrame(registros)
    for c in ("bounds", "capas", "atributos", "fechas_nombre", "anios_nombre", "resolucion"):
        if c in df.columns:
            df[c] = df[c].apply(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, tuple)) else v)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    return ruta_json, ruta_csv


def cargar_catalogo(carpeta: Path) -> pd.DataFrame | None:
    ruta_json = carpeta / "catalogo_datos.json"
    if not ruta_json.exists():
        return None
    with open(ruta_json, encoding="utf-8") as f:
        d = json.load(f)
    df = pd.DataFrame(d.get("entradas", []))
    df.attrs["generado"] = d.get("generado")
    return df


def resumen_catalogo(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    r = {"n_total": int(len(df))}
    r["por_categoria"] = df["categoria"].value_counts().to_dict()
    r["por_epsg"] = df["epsg"].dropna().astype(int).value_counts().to_dict() if "epsg" in df else {}
    esc = df[df["categoria"] == "escena_landsat"] if "categoria" in df else df.iloc[0:0]
    if not esc.empty:
        r["escenas_por_satelite"] = esc["satelite"].value_counts().to_dict()
        r["escenas_por_sitio"] = esc["sitio"].value_counts().to_dict()
        fechas = esc["fechas_nombre"].apply(lambda v: v[0] if isinstance(v, list) and v else None).dropna()
        if not fechas.empty:
            r["escenas_fecha_min"], r["escenas_fecha_max"] = str(min(fechas))[:10], str(max(fechas))[:10]
    r["tamano_total_gb"] = round(df["tamano_bytes"].sum() / 1024**3, 2)
    r["modificado_max"] = str(df["modificado"].max())
    return r


if __name__ == "__main__":  # uso: python -m src.inventario
    from .configuracion import cargar_config, ruta, rutas_salida

    logging.basicConfig(level=logging.INFO)
    cfg = cargar_config()
    raices = {k: ruta(cfg, k) for k in ("exportar_coastsat", "resultados_tesis", "coastsat_data")}
    ent = inventariar(raices)
    rj, rc = guardar_catalogo(ent, rutas_salida(cfg)["catalogo"])
    print(f"{len(ent)} entradas -> {rj}")
    print(json.dumps(resumen_catalogo(cargar_catalogo(rj.parent)), indent=1, ensure_ascii=False))
