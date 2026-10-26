"""Rásteres: lectura selectiva, remuestreo solo para visualización y superposición en el mapa.

Nunca se carga un ráster completo a resolución nativa: se lee con
``out_shape`` (decimación) hasta el lado máximo configurado y se reproyecta a
EPSG:4326 para Leaflet. Los PNG resultantes se guardan en ``resultados/cache``
con una firma (ruta, mtime, tamaño, parámetros) para no repetir el trabajo.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

from .cachear import firma_archivo
from .configuracion import ruta as ruta_cfg

_log = logging.getLogger("geovisor.rasteres")


@dataclass
class Superposicion:
    png_base64: str
    bounds: list            # [[lat_min, lon_min], [lat_max, lon_max]]
    ancho: int
    alto: int
    crs_origen: str
    nota: str = ""

    @property
    def url(self) -> str:
        return "data:image/png;base64," + self.png_base64


def info_raster(ruta: str | Path) -> dict:
    with rasterio.open(ruta) as src:
        return {
            "crs": str(src.crs), "epsg": src.crs.to_epsg() if src.crs else None, "bandas": src.count,
            "tipo": str(src.dtypes[0]), "ancho": src.width, "alto": src.height,
            "resolucion": [float(src.res[0]), float(src.res[1])], "nodata": src.nodata,
            "bounds": [float(b) for b in src.bounds],
        }


def _factor(src, max_px: int) -> int:
    lado = max(src.width, src.height)
    return max(1, int(np.ceil(lado / max_px)))


def _png_b64(rgba: np.ndarray) -> str:
    from PIL import Image

    im = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ruta_cache(cfg: dict, ruta: Path, params: dict) -> Path:
    carpeta = ruta_cfg(cfg, "cache")
    carpeta.mkdir(parents=True, exist_ok=True)
    firma = json.dumps([firma_archivo(ruta), params], sort_keys=True, default=str)
    h = hashlib.sha1(firma.encode()).hexdigest()[:16]
    return carpeta / f"{ruta.stem}_{h}.json"


def _leer_cache(p: Path) -> Superposicion | None:
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return Superposicion(**d)
        except Exception:  # noqa: BLE001
            return None
    return None


def _guardar_cache(p: Path, s: Superposicion) -> None:
    try:
        p.write_text(json.dumps(s.__dict__), encoding="utf-8")
    except OSError as e:
        _log.warning("No se pudo escribir la caché %s: %s", p, e)


def _reproyectar_a_4326(datos: np.ndarray, src, transform, nodata) -> tuple[np.ndarray, list]:
    """Reproyecta un arreglo (bandas, filas, cols) ya decimado al CRS 4326."""
    if src.crs and src.crs.to_epsg() == 4326:
        b = transform_bounds(src.crs, "EPSG:4326", *src.bounds) if src.crs else src.bounds
        return datos, [[b[1], b[0]], [b[3], b[2]]]
    alto, ancho = datos.shape[1], datos.shape[2]
    dst_transform, w, h = calculate_default_transform(src.crs, "EPSG:4326", ancho, alto, *src.bounds)
    salida = np.full((datos.shape[0], h, w), np.nan if np.issubdtype(datos.dtype, np.floating) else 0, dtype=datos.dtype)
    for i in range(datos.shape[0]):
        reproject(
            source=datos[i], destination=salida[i], src_transform=transform, src_crs=src.crs,
            dst_transform=dst_transform, dst_crs="EPSG:4326", src_nodata=nodata,
            dst_nodata=np.nan if np.issubdtype(datos.dtype, np.floating) else 0, resampling=Resampling.bilinear,
        )
    b = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    return salida, [[b[1], b[0]], [b[3], b[2]]]


def superponer_rgba(cfg: dict, ruta: str | Path, opacidad: float = 1.0) -> Superposicion:
    """Ráster RGB/RGBA uint8 (p. ej. mapas de calor del IVC o fondo) -> PNG."""
    ruta = Path(ruta)
    max_px = int(cfg["visualizacion"].get("raster_max_px", 1400))
    pc = _ruta_cache(cfg, ruta, {"tipo": "rgba", "max_px": max_px})
    s = _leer_cache(pc)
    if s:
        return s
    with rasterio.open(ruta) as src:
        f = _factor(src, max_px)
        shape = (src.count, src.height // f, src.width // f)
        datos = src.read(out_shape=shape, resampling=Resampling.average)
        transform = src.transform * src.transform.scale(src.width / shape[2], src.height / shape[1])
        datos, bounds = _reproyectar_a_4326(datos.astype(np.float32), src, transform, src.nodata)
        datos = np.nan_to_num(datos, nan=0).astype(np.uint8)
        if datos.shape[0] >= 4:
            rgba = np.moveaxis(datos[:4], 0, -1)
        elif datos.shape[0] == 3:
            alpha = np.where(datos.sum(axis=0) > 0, 255, 0).astype(np.uint8)
            rgba = np.dstack([np.moveaxis(datos, 0, -1), alpha])
        else:
            raise ValueError("Se esperaba un ráster RGB o RGBA")
        s = Superposicion(_png_b64(np.ascontiguousarray(rgba)), bounds, rgba.shape[1], rgba.shape[0], str(src.crs),
                          nota=f"remuestreado ×{f} solo para visualización")
    _guardar_cache(pc, s)
    return s


def superponer_valor(cfg: dict, ruta: str | Path, vmin: float | None = None, vmax: float | None = None,
                     paleta: str = "viridis", cortes: list | None = None, colores: list | None = None) -> tuple[Superposicion, dict]:
    """Ráster de una banda -> PNG con rampa continua (matplotlib) o por clases (cortes+colores)."""
    import matplotlib

    ruta = Path(ruta)
    max_px = int(cfg["visualizacion"].get("raster_max_px", 1400))
    params = {"tipo": "valor", "max_px": max_px, "vmin": vmin, "vmax": vmax, "paleta": paleta, "cortes": cortes, "colores": colores}
    pc = _ruta_cache(cfg, ruta, params)
    s = _leer_cache(pc)
    with rasterio.open(ruta) as src:
        f = _factor(src, max_px)
        shape = (1, src.height // f, src.width // f)
        datos = src.read(out_shape=shape, resampling=Resampling.average).astype(np.float32)
        nodata = src.nodata
        if nodata is not None:
            datos[datos == nodata] = np.nan
        transform = src.transform * src.transform.scale(src.width / shape[2], src.height / shape[1])
        datos, bounds = _reproyectar_a_4326(datos, src, transform, np.nan)
        v = datos[0]
        valid = np.isfinite(v)
        est = {"min": float(np.nanmin(v)) if valid.any() else None, "max": float(np.nanmax(v)) if valid.any() else None,
               "media": float(np.nanmean(v)) if valid.any() else None, "n_valid": int(valid.sum())}
        if s:
            return s, est
        if cortes and colores:
            idx = np.digitize(v, cortes)  # 0..len(cortes)
            lut = np.array([matplotlib.colors.to_rgb(c) for c in colores])
            rgb = (lut[np.clip(idx, 0, len(colores) - 1)] * 255).astype(np.uint8)
        else:
            lo = vmin if vmin is not None else est["min"]
            hi = vmax if vmax is not None else est["max"]
            norm = matplotlib.colors.Normalize(vmin=lo, vmax=hi)
            cmap = matplotlib.colormaps[paleta]
            rgb = (cmap(norm(np.nan_to_num(v, nan=lo if lo is not None else 0)))[..., :3] * 255).astype(np.uint8)
        alpha = np.where(valid, 255, 0).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
        s = Superposicion(_png_b64(np.ascontiguousarray(rgba)), bounds, rgba.shape[1], rgba.shape[0], str(src.crs),
                          nota=f"remuestreado ×{f} solo para visualización")
    _guardar_cache(pc, s)
    return s, est


def superponer_escena_landsat(cfg: dict, ruta: str | Path, bandas_rgb: tuple = (3, 2, 1), percentiles: tuple = (2, 98)) -> Superposicion:
    """Escena multiespectral de CoastSat (bandas B,G,R,NIR,SWIR1) -> composición RGB en color natural.

    El orden de bandas sigue la convención de CoastSat para Landsat (1=azul, 2=verde, 3=rojo, 4=NIR, 5=SWIR1).
    """
    ruta = Path(ruta)
    max_px = int(cfg["visualizacion"].get("raster_max_px", 1400))
    params = {"tipo": "landsat", "max_px": max_px, "bandas": bandas_rgb, "pct": percentiles}
    pc = _ruta_cache(cfg, ruta, params)
    s = _leer_cache(pc)
    if s:
        return s
    with rasterio.open(ruta) as src:
        if src.count < max(bandas_rgb):
            raise ValueError(f"La escena tiene {src.count} bandas; se esperaban al menos {max(bandas_rgb)}")
        f = _factor(src, max_px)
        shape = (len(bandas_rgb), src.height // f, src.width // f)
        datos = src.read(list(bandas_rgb), out_shape=shape, resampling=Resampling.average).astype(np.float32)
        datos[~np.isfinite(datos)] = np.nan
        transform = src.transform * src.transform.scale(src.width / shape[2], src.height / shape[1])
        datos, bounds = _reproyectar_a_4326(datos, src, transform, np.nan)
        valid = np.all(np.isfinite(datos), axis=0) & (np.nansum(datos, axis=0) > 0)
        rgb = np.zeros((datos.shape[1], datos.shape[2], 3), dtype=np.uint8)
        for i in range(3):
            b = datos[i]
            if valid.any():
                lo, hi = np.nanpercentile(b[valid], percentiles)
                hi = hi if hi > lo else lo + 1e-6
                rgb[..., i] = (np.clip((np.nan_to_num(b, nan=lo) - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
        alpha = np.where(valid, 255, 0).astype(np.uint8)
        s = Superposicion(_png_b64(np.ascontiguousarray(np.dstack([rgb, alpha]))), bounds, rgb.shape[1], rgb.shape[0], str(src.crs),
                          nota=f"color natural (bandas {bandas_rgb}), estiramiento P{percentiles[0]}–P{percentiles[1]}, remuestreado ×{f}")
    _guardar_cache(pc, s)
    return s


def estadisticas_en_poligonos(ruta: str | Path, geometrias, nodata_extra: float | None = None) -> list[dict]:
    """Estadísticas (media, min, max, n) de un ráster de una banda dentro de polígonos (CRS del ráster)."""
    from rasterio.mask import mask as rmask

    out = []
    with rasterio.open(ruta) as src:
        for geom in geometrias:
            try:
                arr, _ = rmask(src, [geom], crop=True, filled=True, nodata=src.nodata if src.nodata is not None else -9999)
            except ValueError:
                out.append({"media": None, "min": None, "max": None, "n": 0})
                continue
            v = arr[0].astype(np.float64)
            nd = src.nodata if src.nodata is not None else -9999
            v = v[(v != nd) & np.isfinite(v)]
            if nodata_extra is not None:
                v = v[v != nodata_extra]
            out.append({"media": float(v.mean()) if v.size else None, "min": float(v.min()) if v.size else None,
                        "max": float(v.max()) if v.size else None, "n": int(v.size)})
    return out
