"""Prepara una copia ligera de los datos para publicar el geovisor en internet.

Copia a ``datos_publicacion/`` únicamente las capas registradas en el catálogo
(src/catalogo_datos.py) cuyo tamaño no supere ``--max-mb`` (por defecto 60 MB),
conservando la estructura relativa, y escribe ``config.publico.yaml`` con las
rutas apuntando a esa copia. Nunca copia las escenas Landsat de ``data/``.

Uso (en el entorno coastsat):
    python preparar_publicacion.py            # copia y genera config.publico.yaml
    python preparar_publicacion.py --max-mb 25

Para ejecutar el geovisor con la copia:  set GEOVISOR_CONFIG_LOCAL=config.publico.yaml && streamlit run app.py
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raíz del geovisor

import yaml

from src.catalogo_datos import CAPAS
from src.configuracion import RAIZ_GEOVISOR, cargar_config, ruta

ANEXOS_SHP = (".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mb", type=float, default=60.0)
    ap.add_argument("--destino", default="datos_publicacion")
    args = ap.parse_args()
    cfg = cargar_config()
    destino = RAIZ_GEOVISOR / args.destino
    copiados, omitidos = [], []
    for capa in CAPAS.values():
        origen = capa.ruta(cfg)
        if not origen.exists():
            continue
        if origen.is_dir():  # carpeta de rásteres del IVC
            archivos = sorted(origen.glob("*.tif"))
        else:
            archivos = [origen]
            if origen.suffix.lower() == ".shp":
                archivos += [origen.with_suffix(e) for e in ANEXOS_SHP if origen.with_suffix(e).exists()]
        for a in archivos:
            mb = a.stat().st_size / 1024**2
            rel = a.relative_to(ruta(cfg, capa.raiz))
            if mb > args.max_mb:
                omitidos.append((str(rel), round(mb, 1)))
                continue
            d = destino / capa.raiz / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            if not d.exists() or d.stat().st_mtime < a.stat().st_mtime:
                shutil.copy2(a, d)
            copiados.append((str(rel), round(mb, 1)))
    rel = destino.relative_to(RAIZ_GEOVISOR).as_posix() if destino.is_relative_to(RAIZ_GEOVISOR) else str(destino)
    conf = {"rutas": {   # rutas relativas a la carpeta del geovisor: funcionan igual en el PC y en Streamlit Cloud
        "coastsat_raiz": f"{rel}/coastsat_raiz", "coastsat_data": f"{rel}/coastsat_data_vacio",
        "exportar_coastsat": f"{rel}/exportar_coastsat", "resultados_tesis": f"{rel}/resultados_tesis",
    }, "modulos": cfg["modulos"]}
    (destino / "coastsat_data_vacio").mkdir(parents=True, exist_ok=True)
    (RAIZ_GEOVISOR / "config.publico.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True, sort_keys=False), encoding="utf-8")
    total = sum(m for _, m in copiados)
    print(f"Copiados {len(copiados)} archivos ({total:.1f} MB) en {destino}")
    for r, m in omitidos:
        print(f"  omitido (> {args.max_mb} MB): {r} ({m} MB) -> publíquelo en almacenamiento externo (Zenodo/Drive) o reduzca su tamaño")
    print("Escrito config.publico.yaml. Las escenas Landsat de data/ no se copian.")


if __name__ == "__main__":
    main()
