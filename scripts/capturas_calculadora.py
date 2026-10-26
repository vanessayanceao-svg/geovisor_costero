"""Capturas de pantalla de la Calculadora IVC paso a paso (Playwright + Chromium).

Requiere el geovisor en marcha en http://localhost:8501 (``streamlit run app.py``). Carga el ejemplo de la tesis y
ejecuta cada paso desde la interfaz, guardando una captura por paso en ``resultados/pruebas_calculadora/08_capturas_interfaz/``.

    python scripts/capturas_calculadora.py [URL]
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "resultados" / "pruebas_calculadora" / "08_capturas_interfaz"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"


async def esperar(pg, extra=2500):
    await pg.wait_for_timeout(1200)
    try:
        await pg.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=600000)
    except Exception as e:
        print("espera:", e)
    await pg.wait_for_timeout(extra)


async def captura(pg, nombre, completa=False):
    await pg.evaluate("window.scrollTo(0,0)")
    await pg.wait_for_timeout(600)
    await pg.screenshot(path=str(OUT / nombre), full_page=completa)
    print("captura", nombre)


async def pestana(pg, texto):
    await pg.locator('[data-testid="stTab"]', has_text=texto).first.click()
    await esperar(pg, 1500)


async def boton(pg, texto):
    await pg.get_by_role("button", name=texto).first.click()
    await esperar(pg, 2500)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        kw = {}
        if Path("/opt/pw-browsers/chromium").exists():
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        b = await p.chromium.launch(**kw)
        ctx = await b.new_context(viewport={"width": 1600, "height": 2200})
        rutas = os.environ.get("GV_RUTAS_LOCALES")  # opcional: módulo con una corrutina route(r) que sirve CDN/teselas en local
        if rutas:
            import importlib.util, re
            spec = importlib.util.spec_from_file_location("rutas_locales", rutas); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            await ctx.route(re.compile(r"^https?://(?!localhost)"), mod.route)
        pg = await ctx.new_page()
        await pg.goto(URL, wait_until="networkidle", timeout=120000)
        await esperar(pg)
        await pg.get_by_text("Calculadora IVC", exact=False).first.click(); await esperar(pg)
        await captura(pg, "00_calculadora_vacia.png")
        await boton(pg, "Cargar ejemplo (tesis)")
        await captura(pg, "01_insumos.png", True)
        await pestana(pg, "Transectos y tasas"); await boton(pg, "Calcular transectos y tasas")
        await captura(pg, "02_transectos_tasas.png", True)
        await pestana(pg, "Variables"); await boton(pg, "Distribuir y clasificar todas")
        await captura(pg, "03_variables.png", True)
        await pestana(pg, "Ponderación"); await boton(pg, "Calcular pesos")
        await captura(pg, "04_ponderacion.png", True)
        await pestana(pg, "Índice y validación"); await boton(pg, "Calcular índice")
        await captura(pg, "05_indice_validacion.png", True)
        await pestana(pg, "Proyección"); await boton(pg, "Proyectar")
        await captura(pg, "06_proyeccion.png", True)
        await pestana(pg, "Exportar"); await boton(pg, "Guardar todo")
        await captura(pg, "07_exportar.png", True)
        try:
            await boton(pg, "Generar informe PDF")
            await captura(pg, "08_entregables_informe.png", True)
        except Exception as e:  # noqa: BLE001
            print("informe:", e)
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
