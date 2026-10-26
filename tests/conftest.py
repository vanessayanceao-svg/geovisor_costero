"""Fixtures comunes. Las pruebas con datos reales se omiten si los archivos no están disponibles."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.configuracion import cargar_config, rutas_salida  # noqa: E402
from src.catalogo_datos import CAPAS  # noqa: E402


@pytest.fixture(scope="session")
def cfg() -> dict:
    c = cargar_config()
    rutas_salida(c)
    return c


def requiere(cfg: dict, clave: str) -> None:
    if not CAPAS[clave].disponible(cfg):
        pytest.skip(f"Datos no disponibles: {CAPAS[clave].titulo}")
