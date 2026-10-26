"""Carga de la configuración (config.yaml + config.local.yaml) y resolución de rutas."""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

RAIZ_GEOVISOR = Path(__file__).resolve().parent.parent
ARCHIVO_CONFIG = RAIZ_GEOVISOR / "config.yaml"
ARCHIVO_CONFIG_LOCAL = RAIZ_GEOVISOR / "config.local.yaml"

_log = logging.getLogger("geovisor")


def _fusionar(base: dict, extra: dict) -> dict:
    """Fusión recursiva: los valores de ``extra`` se superponen a ``base``."""
    salida = copy.deepcopy(base)
    for clave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(salida.get(clave), dict):
            salida[clave] = _fusionar(salida[clave], valor)
        else:
            salida[clave] = valor
    return salida


ARCHIVO_CONFIG_PUBLICO = RAIZ_GEOVISOR / "config.publico.yaml"


def _config_local_disponible() -> Path | None:
    """config.local.yaml si sus rutas existen en esta máquina; si no (p. ej. en Streamlit Cloud), config.publico.yaml."""
    for candidato in (ARCHIVO_CONFIG_LOCAL, ARCHIVO_CONFIG_PUBLICO):
        if not candidato.exists():
            continue
        try:
            with open(candidato, encoding="utf-8") as f:
                rutas = (yaml.safe_load(f) or {}).get("rutas", {})
        except Exception:  # noqa: BLE001
            continue
        base = rutas.get("exportar_coastsat") or rutas.get("resultados_tesis")
        if not base:
            return candidato
        p = Path(str(base).replace("\\", "/"))
        if (p if p.is_absolute() else RAIZ_GEOVISOR / p).exists():
            return candidato
    return ARCHIVO_CONFIG_LOCAL if ARCHIVO_CONFIG_LOCAL.exists() else None


def cargar_config(ruta: str | os.PathLike | None = None) -> dict[str, Any]:
    """Lee config.yaml y, si existe, config.local.yaml (o la ruta de GEOVISOR_CONFIG)."""
    ruta = Path(ruta) if ruta else ARCHIVO_CONFIG
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    local = os.environ.get("GEOVISOR_CONFIG_LOCAL")
    local = Path(local) if local else _config_local_disponible()
    if local is not None and local.exists():
        with open(local, encoding="utf-8") as f:
            cfg = _fusionar(cfg, yaml.safe_load(f) or {})
        cfg.setdefault("_meta", {})["config_local"] = str(local)
    cfg.setdefault("_meta", {})["config"] = str(ruta)
    return cfg


def ruta(cfg: dict, clave: str) -> Path:
    """Devuelve una ruta de ``cfg['rutas']``; las relativas se resuelven desde la carpeta del geovisor."""
    valor = cfg["rutas"][clave]
    p = Path(str(valor).replace("\\", "/"))
    if not p.is_absolute():
        p = RAIZ_GEOVISOR / p
    return p


def rutas_salida(cfg: dict) -> dict[str, Path]:
    """Crea (si no existen) y devuelve las carpetas de salida del geovisor."""
    salidas = {}
    for clave in ("catalogo", "cache", "exportaciones", "reportes", "logs"):
        p = ruta(cfg, clave)
        p.mkdir(parents=True, exist_ok=True)
        salidas[clave] = p
    return salidas


def configurar_logs(cfg: dict) -> logging.Logger:
    carpeta = ruta(cfg, "logs")
    carpeta.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("geovisor")
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        fh = logging.FileHandler(carpeta / "geovisor.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(fh)
    logger.setLevel(logging.INFO)
    return logger


def ocultar_ruta(p: str | os.PathLike, cfg: dict | None = None) -> str:
    """Versión segura de una ruta para mostrar en la interfaz (sin exponer unidades ni usuarios)."""
    s = str(p).replace("\\", "/")
    if cfg:
        for clave, alias in (("coastsat_raiz", "[CoastSat]"), ("resultados_tesis", "[Resultados tesis]")):
            base = str(ruta(cfg, clave)).replace("\\", "/")
            if s.startswith(base):
                return alias + s[len(base):]
    base = str(RAIZ_GEOVISOR).replace("\\", "/")
    if s.startswith(base):
        return "[geovisor]" + s[len(base):]
    return Path(s).name
