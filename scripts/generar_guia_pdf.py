"""Convierte docs/GUIA_USUARIO.md (y opcionalmente otros .md de docs/) en PDF con Chromium (Playwright).

    python scripts/generar_guia_pdf.py                 # docs/GUIA_USUARIO.pdf
    python scripts/generar_guia_pdf.py docs/INVENTARIO.md docs/AUDITORIA_CALCULADORA.md

Requiere ``pip install markdown playwright`` y ``playwright install chromium`` (solo la primera vez). Las imágenes se
incrustan en base64 para que el PDF sea autónomo.
"""
from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parent.parent
CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: 'Aptos Narrow', 'Segoe UI', 'Manrope', system-ui, sans-serif; color: #1B2440; font-size: 10.5pt; line-height: 1.45; }
h1, h2, h3 { font-family: 'Aptos SemiBold', 'Aptos', 'Poppins', 'Segoe UI', sans-serif; font-weight: 600; }
h1 { font-size: 22pt; color: #1E3A8A; border-bottom: 3px solid #19B3A6; padding-bottom: 6px; margin: 0 0 12px; }
h2 { font-size: 15pt; color: #1E3A8A; margin: 22px 0 8px; page-break-after: avoid; }
h3 { font-size: 12pt; color: #3B6CF0; margin: 16px 0 6px; page-break-after: avoid; }
p, li { text-align: justify; }
code { font-family: Consolas, 'JetBrains Mono', monospace; font-size: 9pt; background: #F3F5FA; padding: 1px 4px; border-radius: 4px; }
pre { background: #F3F5FA; border: 1px solid #E1E6F2; border-radius: 8px; padding: 8px 10px; font-size: 9pt; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 8px 0 12px; page-break-inside: auto; }
th { background: #F3F5FA; color: #55596A; text-transform: uppercase; font-size: 7.6pt; letter-spacing: .05em; text-align: left; padding: 5px 7px; border-bottom: 1px solid #DDE3EE; }
td { padding: 5px 7px; border-bottom: 1px solid #E8ECF4; vertical-align: top; }
tr { page-break-inside: avoid; }
img { max-width: 100%; border: 1px solid #DDE3EE; border-radius: 8px; margin: 6px 0 10px; page-break-inside: avoid; }
hr { border: 0; border-top: 1px solid #DDE3EE; margin: 18px 0; }
blockquote { border-left: 3px solid #19B3A6; margin: 8px 0; padding: 4px 12px; color: #55596A; background: #F8FAFD; }
.pie { position: fixed; bottom: 0; font-size: 8pt; color: #55596A; }
"""


def md_a_html(ruta_md: Path) -> str:
    texto = ruta_md.read_text(encoding="utf-8")
    html = markdown.markdown(texto, extensions=["tables", "fenced_code", "toc"])

    def incrustar(m):
        src = m.group(1)
        f = (ruta_md.parent / src).resolve()
        if f.exists():
            tipo = mimetypes.guess_type(str(f))[0] or "image/png"
            return f'src="data:{tipo};base64,{base64.b64encode(f.read_bytes()).decode()}"'
        return m.group(0)

    html = re.sub(r'src="([^"]+)"', incrustar, html)
    return f"<!doctype html><html lang='es'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html}</body></html>"


def a_pdf(ruta_md: Path, salida: Path) -> Path:
    from playwright.sync_api import sync_playwright

    html = md_a_html(ruta_md)
    with sync_playwright() as p:
        kw = {}
        if Path("/opt/pw-browsers/chromium").exists():
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        b = p.chromium.launch(**kw)
        pg = b.new_page()
        pg.set_content(html, wait_until="load")
        pg.pdf(path=str(salida), format="A4", print_background=True, margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
               display_header_footer=True, header_template="<div></div>",
               footer_template="<div style='font-size:7pt;color:#55596A;width:100%;text-align:center;font-family:sans-serif'>Coastal Vulnerability System · "
                               + ruta_md.stem.replace("_", " ") + " · página <span class='pageNumber'></span> de <span class='totalPages'></span></div>")
        b.close()
    return salida


if __name__ == "__main__":
    archivos = [Path(a) for a in sys.argv[1:]] or [RAIZ / "docs" / "GUIA_USUARIO.md"]
    for a in archivos:
        out = a.with_suffix(".pdf")
        a_pdf(a, out)
        print(f"{out} ({out.stat().st_size / 1e6:.1f} MB)")
