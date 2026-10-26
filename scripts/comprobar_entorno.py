"""Comprueba el entorno Python antes de ejecutar el geovisor (no instala nada).

Uso:  python comprobar_entorno.py
Informa qué paquetes faltan y qué rutas de config.yaml existen.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

PAQUETES = {
    "streamlit": "streamlit", "streamlit_folium": "streamlit-folium", "folium": "folium", "branca": "branca", "plotly": "plotly",
    "yaml": "pyyaml", "geopandas": "geopandas", "shapely": "shapely", "pyproj": "pyproj", "rasterio": "rasterio",
    "pyogrio": "pyogrio", "pandas": "pandas", "numpy": "numpy", "matplotlib": "matplotlib", "PIL": "pillow", "openpyxl": "openpyxl", "pytest": "pytest",
}


def main() -> int:
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    faltan = []
    for modulo, pip in PAQUETES.items():
        try:
            m = importlib.import_module(modulo)
            print(f"  ok   {pip:18s} {getattr(m, '__version__', '')}")
        except Exception:  # noqa: BLE001
            print(f"  --   {pip:18s} FALTA")
            faltan.append(pip)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from src.configuracion import cargar_config, ruta

        cfg = cargar_config()
        print("\nRutas de config.yaml:")
        for k in ("coastsat_raiz", "coastsat_data", "exportar_coastsat", "resultados_tesis"):
            p = ruta(cfg, k)
            print(f"  {'ok' if p.exists() else '--'}   {k:18s} {p}")
        from src.catalogo_datos import estado_modulos

        print("\nMódulos:", ", ".join(f"{k}={'sí' if v['ok'] else 'no'}" for k, v in estado_modulos(cfg).items()))
    except Exception as e:  # noqa: BLE001
        print(f"\nNo se pudo leer la configuración: {e}")
    if faltan:
        print("\nInstale lo que falta (dentro del entorno coastsat):\n  pip install " + " ".join(faltan))
        return 1
    print("\nEntorno completo. Ejecute:  streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
