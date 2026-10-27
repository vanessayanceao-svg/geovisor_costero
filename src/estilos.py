"""Sistema visual: dos temas (claro/oscuro) con variables CSS, tarjetas tipo cristal, Poppins, iconos SVG y animaciones."""
from __future__ import annotations

AZUL = "#3B6CF0"
TEAL = "#19B3A6"
CORAL = "#F2745F"
AMBAR = "#F5B544"
VIOLETA = "#7C5CF6"
TINTA = "#1B2440"
GRIS = "#6B7A99"

TEMAS = {
    "claro": dict(bg="#EEF2FA", bg2="#E4EAF7", card="#FFFFFF", card2="#F6F8FD", borde="rgba(27,36,64,.08)", texto="#1B2440", texto2="#6B7A99",
                  sombra="0 10px 28px rgba(27,36,64,.08)", sombra2="0 18px 40px rgba(27,36,64,.14)", grid="#EEF1F6", cristal="rgba(255,255,255,.72)",
                  hero1="#15265C", hero2="#2457C5", hero3="#19B3A6", mapa_bg="#DCE6F2", pill="#E3EBFF", radial1="#DCE6FF", radial2="#E6F7F5"),
    "oscuro": dict(bg="#0B1222", bg2="#101A30", card="#141F38", card2="#182544", borde="rgba(255,255,255,.08)", texto="#EEF2FA", texto2="#93A1C0",
                   sombra="0 10px 28px rgba(0,0,0,.35)", sombra2="0 18px 44px rgba(0,0,0,.5)", grid="rgba(255,255,255,.07)", cristal="rgba(20,31,56,.7)",
                   hero1="#0F1B3D", hero2="#1C3D9C", hero3="#19B3A6", mapa_bg="#0B1222", pill="rgba(59,108,240,.22)", radial1="#172A5C", radial2="#0E2E35"),
}


def css(tema: str = "claro", fondo_b64: str | None = None) -> str:
    t = TEMAS.get(tema, TEMAS["claro"])
    capa_mapa = f"url(data:image/png;base64,{fondo_b64}) no-repeat right 18% / min(96vw, 1500px) auto fixed, " if fondo_b64 else ""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700;800&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap');
:root {{ --bg:{t['bg']}; --bg2:{t['bg2']}; --card:{t['card']}; --card2:{t['card2']}; --borde:{t['borde']}; --texto:{t['texto']}; --texto2:{t['texto2']};
  --sombra:{t['sombra']}; --sombra2:{t['sombra2']}; --cristal:{t['cristal']}; --pill:{t['pill']}; --azul:{AZUL}; --teal:{TEAL}; --coral:{CORAL}; --ambar:{AMBAR}; --violeta:{VIOLETA}; }}
/* Tipografía: Manrope (formal) para la interfaz — botones, capas, pestañas, tablas, entradas, notas —; Poppins solo en textos principales (títulos, cabecera, cifras). */
html, body, [class*="css"], .stApp, .stMarkdown, button, input, select, textarea, label, p, span, div, li, td, th {{ font-family: 'Manrope', 'Segoe UI', system-ui, -apple-system, sans-serif; }}
h1, h2, h3, h4, h5, h6, .gv-title, .gv-title span, .gv-sub, .gv-eyebrow, .gv-stat .n, .gv-kpi .v, .gv-panel h4, .gv-seccion h3, .gv-seccion .t, .gv-cab h3 {{ font-family: 'Poppins', 'Manrope', sans-serif; }}
.gv-panel small, .gv-kpi .l, .gv-kpi .u, .gv-kpi .v.largo, .gv-stat .l, .gv-chip, .gv-eyebrow {{ font-family: 'Manrope', sans-serif; }}
.stApp {{ background: {capa_mapa}radial-gradient(1000px 480px at -5% -10%, {t['radial1']} 0%, var(--bg) 55%), radial-gradient(800px 420px at 105% 0%, {t['radial2']} 0%, var(--bg) 60%) fixed; color:var(--texto); }}
.stApp, .stMarkdown p, .stMarkdown li, .stCheckbox p, .stRadio p, label[data-testid="stWidgetLabel"] p, .stSelectbox label p, .stDateInput label p, .stSlider label p, .stMultiSelect label p, .stTabs p, h1,h2,h3,h4,h5,h6 {{ color:var(--texto); }}
.block-container {{ padding-top: .9rem; padding-bottom: 2rem; max-width: 1680px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1,h2,h3,h4,h5 {{ font-weight:600; letter-spacing:-.01em; }}

/* ---------- animaciones ---------- */
@keyframes gv-up {{ from {{ opacity:0; transform:translateY(14px) }} to {{ opacity:1; transform:none }} }}
@keyframes gv-pop {{ 0% {{ transform:scale(.9); opacity:0 }} 100% {{ transform:scale(1); opacity:1 }} }}
@keyframes gv-pulse {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(25,179,166,.5) }} 60% {{ box-shadow:0 0 0 8px rgba(25,179,166,0) }} }}
@keyframes gv-bar {{ from {{ width:0 }} to {{ width:var(--w) }} }}
@keyframes gv-float {{ 0%,100% {{ transform:translateY(0) }} 50% {{ transform:translateY(-5px) }} }}
@keyframes gv-dash {{ to {{ stroke-dashoffset:0 }} }}
@keyframes gv-grow {{ from {{ transform:scaleY(0) }} to {{ transform:scaleY(1) }} }}

/* ---------- cabecera hero ---------- */
.gv-hero {{ position:relative; overflow:hidden; border-radius:26px; padding:22px 28px 44px;
  background: linear-gradient(112deg, {t['hero1']} 0%, {t['hero2']} 52%, {t['hero3']} 125%); color:#fff; box-shadow: var(--sombra2); animation: gv-up .5s ease both; }}
.gv-hero::after {{ content:""; position:absolute; right:-120px; top:-160px; width:460px; height:460px; border-radius:50%; background: radial-gradient(circle, rgba(255,255,255,.2), rgba(255,255,255,0) 62%); }}
.gv-hero::before {{ content:""; position:absolute; left:34%; bottom:-200px; width:520px; height:340px; border-radius:50%; background: radial-gradient(circle, rgba(25,179,166,.4), rgba(25,179,166,0) 65%); }}
.gv-olas {{ position:absolute; left:0; right:0; bottom:-2px; height:96px; z-index:0; pointer-events:none; }}
.gv-olas svg {{ position:absolute; bottom:0; left:0; width:200%; height:100%; animation: gv-ola 16s linear infinite; }}
.gv-olas svg.o2 {{ animation-duration:24s; animation-direction:reverse; }}
.gv-olas svg.o3 {{ animation-duration:11s; }}
.gv-olas-fondo {{ position:absolute; inset:0; z-index:0; pointer-events:none; overflow:hidden; }}
.gv-olas-fondo svg {{ position:absolute; left:-10%; top:-20%; width:120%; height:140%; opacity:.16; }}
.gv-olas-fondo path {{ stroke-dasharray:2600; stroke-dashoffset:2600; animation: gv-dash 2.6s ease forwards; }}
.gv-olas-fondo path:nth-child(2) {{ animation-delay:.25s }} .gv-olas-fondo path:nth-child(3) {{ animation-delay:.5s }} .gv-olas-fondo path:nth-child(4) {{ animation-delay:.75s }}
@keyframes gv-ola {{ from {{ transform:translateX(0) }} to {{ transform:translateX(-50%) }} }}
.gv-wave-u {{ display:block; width:120px; height:10px; margin-top:4px; }}
.gv-wave-u path {{ stroke-dasharray:240; stroke-dashoffset:240; animation: gv-dash 1.6s ease forwards; }}
.gv-panel {{ position:relative; overflow:hidden; }}
.gv-panel .marca {{ position:absolute; right:-6px; bottom:-10px; width:84px; height:44px; opacity:.07; pointer-events:none; }}
.gv-kpi .marca {{ position:absolute; right:-8px; top:-10px; width:70px; height:40px; opacity:.045; pointer-events:none; }}
.gv-hero-grid {{ display:grid; grid-template-columns: 1.3fr auto; gap:18px; align-items:center; position:relative; z-index:1; }}
.gv-brand {{ display:flex; align-items:center; gap:14px; }}
.gv-brand .logo {{ width:54px; height:54px; border-radius:17px; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); display:flex; align-items:center; justify-content:center; backdrop-filter: blur(8px); animation: gv-float 4.5s ease-in-out infinite; }}
.gv-brand .logo svg {{ width:30px; height:30px; }}
.gv-hero p {{ margin:0 !important; color:#fff !important; }}
.gv-eyebrow {{ font-size:.64rem !important; letter-spacing:.2em; text-transform:uppercase; color:#9EE8E0 !important; font-weight:600; margin:0 0 3px !important; line-height:1.3 !important; }}
.gv-title {{ font-size:1.7rem !important; font-weight:800 !important; margin:0 !important; line-height:1.1 !important; letter-spacing:-.01em; white-space:nowrap; }}
.gv-title span {{ background:linear-gradient(90deg,#9EE8E0,#C7F3EE); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.gv-sub {{ margin:6px 0 0 !important; font-size:.84rem !important; color:rgba(255,255,255,.85) !important; font-weight:400; max-width:640px; line-height:1.4 !important; }}
.gv-stats {{ display:grid; grid-template-columns:repeat(4, minmax(128px, 1fr)); gap:10px; justify-content:end; }}
@media (max-width:1100px) {{ .gv-stats {{ grid-template-columns:repeat(2, minmax(128px,1fr)); }} }}
.gv-stat {{ min-width:0; min-height:66px; display:flex; flex-direction:column; justify-content:center; padding:10px 14px; border-radius:18px; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.22); backdrop-filter: blur(10px); animation: gv-pop .5s ease both; }}
.gv-stat .n {{ font-size:1.35rem; font-weight:800; line-height:1.1; letter-spacing:-.02em; }}
.gv-stat .l {{ font-size:.68rem; color:rgba(255,255,255,.8); display:flex; align-items:center; gap:5px; margin-top:2px; }}
.gv-stat .l svg {{ width:12px; height:12px; }}
.gv-chips {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; position:relative; z-index:1; align-items:center; }}
.gv-chip.proy {{ background:rgba(255,255,255,.2); border-color:rgba(255,255,255,.4); font-weight:600; }}
.gv-chip.proy .k {{ opacity:.75; font-weight:500; margin-right:2px; }}
.gv-chip {{ display:inline-flex; align-items:center; gap:7px; font-size:.74rem; color:#fff; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.22); padding:6px 12px; border-radius:999px; backdrop-filter: blur(8px); white-space:nowrap; }}
.gv-chip svg {{ width:14px; height:14px; }} .gv-chip b {{ font-weight:600; }}
.gv-mod {{ display:inline-flex; align-items:center; gap:7px; font-size:.72rem; font-weight:600; background:#fff; color:#1B2440; padding:6px 11px; border-radius:999px; box-shadow:0 6px 16px rgba(0,0,0,.18); }}
.gv-mod svg {{ width:13px; height:13px; }}
.gv-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.gv-ok {{ background:{TEAL}; animation: gv-pulse 2.4s infinite; }} .gv-no {{ background:{CORAL}; }}

/* ---------- navegación ---------- */
.st-key-seccion {{ width:100% !important; margin: 14px 0 4px; }}
.st-key-seccion label[data-testid="stWidgetLabel"] {{ display:none; }}
.st-key-seccion div[role="radiogroup"] {{ display:flex; flex-wrap:wrap; gap:6px; background:var(--card); padding:6px; border-radius:999px; box-shadow:var(--sombra); width:fit-content; border:1px solid var(--borde); }}
.st-key-seccion div[role="radiogroup"] > div {{ margin:0 !important; border-radius:999px; padding:7px 13px; cursor:pointer; transition: all .2s ease; }}
.st-key-seccion div[role="radiogroup"] > div:hover {{ background:var(--pill); }}
.st-key-seccion div[role="radiogroup"] > div[data-selected="true"] {{ background:linear-gradient(90deg,{AZUL},{VIOLETA}); box-shadow:0 8px 20px rgba(59,108,240,.35); }}
.st-key-seccion div[role="radiogroup"] > div[data-selected="true"] p, .st-key-seccion div[role="radiogroup"] > div[data-selected="true"] span {{ color:#fff !important; }}
.st-key-seccion label[data-testid="stRadioOption"] > div > div:first-child {{ display:none; }}
.st-key-seccion label[data-testid="stRadioOption"] p {{ font-size:.8rem; font-weight:500; margin:0; white-space:nowrap; }}

/* ---------- tarjetas ---------- */
.gv-panel {{ display:flex; align-items:center; gap:10px; background:var(--card); border:1px solid var(--borde); border-radius:18px; padding:10px 14px; margin:4px 0 10px; box-shadow:var(--sombra); animation: gv-up .45s ease both; }}
.gv-panel .ic {{ width:36px; height:36px; border-radius:12px; background:linear-gradient(135deg, rgba(59,108,240,.18), rgba(25,179,166,.18)); display:flex; align-items:center; justify-content:center; flex:none; }}
.gv-panel .ic svg {{ width:18px; height:18px; }}
.gv-panel h4 {{ margin:0; font-size:.86rem; font-weight:600; color:var(--texto); }}
.gv-panel small {{ display:block; font-size:.7rem; color:var(--texto2); font-weight:400; }}

.gv-kpi {{ position:relative; display:flex; gap:12px; align-items:center; min-height:78px; background:var(--card); border:1px solid var(--borde); border-radius:20px; padding:12px 14px; margin-bottom:10px;
  box-shadow:var(--sombra); transition: transform .22s ease, box-shadow .22s ease; animation: gv-up .5s ease both; overflow:hidden; }}
.gv-kpi:hover {{ transform:translateY(-3px); box-shadow:var(--sombra2); }}
.gv-kpi .ic {{ width:44px; height:44px; border-radius:14px; display:flex; align-items:center; justify-content:center; flex:none; }}
.gv-kpi .ic svg {{ width:22px; height:22px; }}
.gv-kpi .ic.azul {{ background:rgba(59,108,240,.14); }} .gv-kpi .ic.teal {{ background:rgba(25,179,166,.16); }} .gv-kpi .ic.coral {{ background:rgba(242,116,95,.16); }} .gv-kpi .ic.ambar {{ background:rgba(245,181,68,.18); }} .gv-kpi .ic.gris {{ background:rgba(107,122,153,.14); }} .gv-kpi .ic.violeta {{ background:rgba(124,92,246,.16); }}
.gv-kpi .tx {{ display:flex; flex-direction:column; min-width:0; flex:1; }}
.gv-kpi .l {{ font-size:.71rem; color:var(--texto2); font-weight:500; display:flex; align-items:center; gap:6px; flex-wrap:nowrap; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }}
.gv-kpi .l .gv-proc {{ flex:none; }}
.gv-kpi .v {{ font-size:1.28rem; font-weight:700; color:var(--texto); line-height:1.15; font-variant-numeric: tabular-nums; letter-spacing:-.01em; }}
.gv-kpi .v.largo {{ font-size:.84rem; font-weight:500; line-height:1.3; }}
.gv-kpi .u {{ font-size:.72rem; color:var(--texto2); font-weight:500; margin-left:4px; }}
.gv-kpi .nd {{ color:{AMBAR}; font-weight:600; font-size:.9rem; }}
.gv-kpi .barra {{ position:absolute; left:0; bottom:0; height:4px; border-radius:0 4px 4px 0; background:linear-gradient(90deg,{AZUL},{TEAL}); animation: gv-bar 1.1s cubic-bezier(.2,.8,.2,1) both; width:var(--w); }}
.gv-kpi .spark {{ width:66px; height:32px; flex:none; }}
.gv-big {{ background:var(--card); border:1px solid var(--borde); border-radius:22px; padding:16px 18px; box-shadow:var(--sombra); animation: gv-up .5s ease both; position:relative; overflow:hidden; }}
.gv-big .n {{ font-size:2.3rem; font-weight:800; line-height:1; letter-spacing:-.03em; background:linear-gradient(90deg,{AZUL},{VIOLETA}); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.gv-big .l {{ font-size:.74rem; color:var(--texto2); margin-top:6px; }}

.gv-proc {{ display:inline-block; font-size:.6rem; font-weight:600; padding:2px 8px; border-radius:999px; background:rgba(59,108,240,.14); color:{AZUL}; letter-spacing:.02em; }}
.gv-proc.dsas {{ background:rgba(25,179,166,.16); color:#0E8F85; }} .gv-proc.script {{ background:rgba(245,181,68,.2); color:#9A6400; }} .gv-proc.modelo {{ background:rgba(242,116,95,.16); color:#C8503B; }}
.gv-proc.geovisor {{ background:rgba(107,122,153,.16); color:var(--texto2); }} .gv-proc.importado {{ background:rgba(59,108,240,.14); color:{AZUL}; }} .gv-proc.calculadora {{ background:rgba(124,92,246,.14); color:#6A4DE0; }}
.gv-nota {{ font-size:.75rem; color:var(--texto2); line-height:1.45; margin:0 0 6px; }}
.gv-nota summary {{ list-style:none; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; border:1px solid var(--borde); background:var(--card2); color:var(--texto2); font-size:.7rem; font-weight:700; user-select:none; }}
.gv-nota summary::-webkit-details-marker {{ display:none; }}
.gv-nota summary:hover, .gv-nota[open] summary {{ border-color:{AZUL}; color:{AZUL}; }}
.gv-nota > div {{ margin-top:4px; padding:7px 10px; border-left:2px solid {AZUL}; background:var(--card2); border-radius:0 10px 10px 0; max-width:900px; }}
.gv-vacio {{ display:flex; gap:14px; align-items:center; border:1.5px dashed var(--borde); border-radius:18px; padding:18px 20px; color:var(--texto2); background:var(--card); animation: gv-up .4s ease both; }}
.gv-vacio b {{ color:var(--texto); display:block; margin-bottom:2px; }} .gv-vacio svg {{ width:34px; height:34px; flex:none; }}
.gv-seccion {{ display:flex; align-items:center; gap:12px; margin:8px 0 12px; animation: gv-up .45s ease both; }}
.gv-seccion .ic {{ width:46px; height:46px; border-radius:15px; background:linear-gradient(135deg,{AZUL},{VIOLETA}); display:flex; align-items:center; justify-content:center; box-shadow:0 10px 22px rgba(59,108,240,.32); }}
.gv-seccion .ic svg {{ width:23px; height:23px; }}
.gv-seccion h3 {{ margin:0; font-size:1.32rem; font-weight:700; }} .gv-seccion p {{ margin:0; font-size:.8rem; color:var(--texto2); }}

/* ---------- línea de tiempo ---------- */
.gv-timeline {{ background:var(--card); border:1px solid var(--borde); border-radius:20px; padding:12px 16px 6px; box-shadow:var(--sombra); margin-bottom:8px; animation: gv-up .5s ease both; }}
.gv-timeline .cab {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
.gv-timeline .cab b {{ font-size:.86rem; }}
.gv-timeline .fecha {{ font-size:1.15rem; font-weight:800; letter-spacing:-.01em; background:linear-gradient(90deg,{AZUL},{TEAL}); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.gv-timeline .anios {{ display:flex; gap:2px; padding:6px 0 2px; align-items:flex-end; }}
.gv-timeline .a {{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:3px; font-size:.56rem; color:var(--texto2); cursor:default; }}
.gv-timeline .a .b {{ width:70%; max-width:14px; border-radius:6px 6px 2px 2px; background:rgba(59,108,240,.28); transform-origin:bottom; animation: gv-grow .6s ease both; }}
.gv-timeline .a.sel {{ color:var(--texto); font-weight:700; }} .gv-timeline .a.sel .b {{ background:linear-gradient(180deg,{TEAL},{AZUL}); box-shadow:0 4px 12px rgba(59,108,240,.4); }}
.gv-timeline .a.vacio .b {{ background:transparent; border-bottom:2px dotted var(--borde); height:2px !important; }}
.stSlider [data-baseweb="slider"] div[role="slider"] {{ background:{AZUL}; box-shadow:0 0 0 5px rgba(59,108,240,.22); width:18px; height:18px; }}
.stSlider [data-baseweb="slider"] > div > div {{ background:var(--pill); }}

/* ---------- widgets ---------- */
.stSelectbox div[data-baseweb="select"] > div, .stDateInput div[data-baseweb="input"], .stMultiSelect div[data-baseweb="select"] > div, .stTextInput div[data-baseweb="input"] {{ border-radius:12px !important; border-color:var(--borde) !important; background:var(--card) !important; color:var(--texto) !important; }}
.stSelectbox div[data-baseweb="select"] span, .stDateInput input, .stMultiSelect span {{ color:var(--texto) !important; }}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, div[data-testid="stLinkButton"] a {{ width:100%; min-height:42px; height:42px; padding:0 14px; border-radius:11px; border:1px solid var(--borde); background:var(--card); color:var(--texto); font-weight:600; font-size:.84rem; letter-spacing:.01em; line-height:1.2; display:inline-flex; align-items:center; justify-content:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:all .2s ease; }}
.stButton > button p, .stDownloadButton > button p {{ font-size:.84rem; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.stButton, .stDownloadButton, .stFormSubmitButton {{ width:100%; }}
/* filas de controles alineadas: etiquetas con la misma altura y campos de 42 px */
[data-testid="stWidgetLabel"] {{ min-height:22px; }}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] > div {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }}
/* filas mixtas: radios horizontales, toggles y casillas a la altura de los campos (42 px) */
[data-testid="stRadio"] [role="radiogroup"] {{ min-height:42px; align-items:center; flex-wrap:nowrap; }}
[data-testid="stRadio"] [role="radiogroup"] label {{ white-space:nowrap; }}
[data-testid="stCheckbox"], [data-testid="stToggle"] {{ min-height:42px; display:flex; align-items:center; }}
[data-testid="stFileUploader"] {{ margin-bottom:0; }}
.gv-hueco {{ height:28px; margin:0; }}
div[data-testid="stMarkdownContainer"]:has(> .gv-hueco) {{ margin:0; }}
div[data-testid="stFileUploader"] section {{ padding:10px 12px; min-height:42px; }}
.stSelectbox div[data-baseweb="select"] > div, .stTextInput div[data-baseweb="input"], .stNumberInput div[data-baseweb="input"], .stDateInput div[data-baseweb="input"] {{ min-height:42px; }}
.stNumberInput button {{ min-height:0 !important; height:auto !important; width:auto !important; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color:{AZUL}; color:{AZUL}; transform:translateY(-1px); box-shadow:0 8px 18px rgba(59,108,240,.2); }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{ background:linear-gradient(90deg,{AZUL},{VIOLETA}); color:#fff; border:none; box-shadow:0 6px 16px rgba(59,108,240,.25); }}
.stButton > button[kind="primary"] p {{ color:#fff; }}
.stCheckbox label p, .stRadio label p {{ font-size:.84rem; }}
/* leyendas del visor (fuera del mapa) */
.gv-leyendas {{ display:flex; flex-wrap:wrap; gap:8px; margin:-6px 0 6px; }}
.gv-leyenda {{ background:var(--card); border:1px solid var(--borde); border-radius:12px; padding:8px 11px; font-size:11.5px; line-height:1.35; color:var(--texto); box-shadow:var(--sombra); max-width:260px; }}
.gv-leyenda b {{ font-size:11.5px; }}
/* chips de capas (st.pills) compactos */
.gv-grupo-capas {{ display:flex; align-items:center; gap:6px; font-size:.7rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:var(--texto2); margin:6px 0 0; }}
.gv-grupo-capas svg {{ width:13px; height:13px; }}
[class*="st-key-visor_capas_"] [data-testid="stButtonGroup"] {{ margin-top:-6px; }}
[class*="st-key-visor_capas_"] [role="toolbar"] {{ display:flex !important; flex-wrap:wrap !important; gap:4px 4px !important; }}
[class*="st-key-visor_capas_"] button[data-variant="pills"] {{ font-size:.72rem !important; padding:1px 9px !important; min-height:22px !important; height:22px !important; line-height:1.1 !important; border-radius:999px !important; border:1px solid var(--borde) !important; background:var(--card2) !important; color:var(--texto) !important; }}
[class*="st-key-visor_capas_"] button[data-variant="pills"] p {{ font-size:.72rem !important; line-height:1.1 !important; font-family:'Manrope', sans-serif !important; font-weight:600; }}
[class*="st-key-visor_capas_"] button[data-variant="pills"][aria-pressed="true"] {{ background:var(--azul) !important; border-color:var(--azul) !important; box-shadow:0 4px 10px rgba(59,108,240,.28); }}
[class*="st-key-visor_capas_"] button[data-variant="pills"][aria-pressed="true"] p {{ color:#fff !important; }}
[class*="st-key-visor_capas_"] button[data-variant="pills"]:hover {{ border-color:var(--azul) !important; }}

/* Pestañas horizontales: barra segmentada tipo carpeta (react-aria, Streamlit ≥1.45) */
.stTabs [role="tablist"] {{ display:flex; flex-wrap:wrap; gap:4px; background:var(--card2); border:1px solid var(--borde); padding:5px; border-radius:14px; box-shadow:inset 0 1px 3px rgba(27,36,64,.06); width:fit-content; max-width:100%; margin-bottom:10px; overflow:visible; }}
.stTabs [data-testid="stTab"] {{ position:relative; border-radius:10px; padding:7px 15px; font-family:'Manrope', sans-serif; font-size:.82rem; font-weight:600; letter-spacing:.01em; color:var(--texto2); background:transparent; border:1px solid transparent; transition:all .18s ease; cursor:pointer; white-space:nowrap; }}
.stTabs [data-testid="stTab"] p {{ font-family:'Manrope', sans-serif; font-size:.82rem; font-weight:600; margin:0; }}
.stTabs [data-testid="stTab"]:hover {{ color:var(--texto); background:var(--pill); }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{ background:var(--card); color:{AZUL}; border-color:var(--borde); box-shadow:0 4px 12px rgba(27,36,64,.10); }}
.stTabs [data-testid="stTab"][aria-selected="true"] p {{ color:{AZUL}; }}
.stTabs [data-testid="stTab"][aria-selected="true"]::after {{ content:""; position:absolute; left:14px; right:14px; bottom:3px; height:2px; border-radius:2px; background:linear-gradient(90deg,{AZUL},{TEAL}); }}
.stTabs .react-aria-SelectionIndicator, .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none !important; }}
.stTabs [data-testid="stTabPanel"], .stTabs [role="tabpanel"] {{ padding-top:4px; }}
/* Tablas HTML del geovisor (ui.tabla) */
.gv-tabla {{ overflow:auto; border:1px solid var(--borde); border-radius:14px; background:var(--card); box-shadow:var(--sombra); margin:2px 0 10px; animation: gv-up .4s ease both; }}
.gv-tabla table {{ width:100%; border-collapse:separate; border-spacing:0; font-family:'Manrope', sans-serif; font-size:.82rem; color:var(--texto); }}
.gv-tabla thead th {{ border-bottom:1px solid var(--borde) !important; position:sticky; top:0; z-index:1; background:var(--card2); color:var(--texto2); font-size:.7rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; text-align:left; padding:10px 12px; border-bottom:1px solid var(--borde); white-space:nowrap; }}
.gv-tabla th, .gv-tabla td {{ border-left:0 !important; border-right:0 !important; border-top:0 !important; }}
.gv-tabla table {{ border:0 !important; box-shadow:none !important; border-radius:0 !important; }}
.gv-tabla td {{ padding:8px 12px; border-bottom:1px solid var(--borde) !important; vertical-align:middle; white-space:nowrap; max-width:420px; overflow:hidden; text-overflow:ellipsis; }}
.gv-tabla tbody tr:nth-child(even) td {{ background:rgba(59,108,240,.03); }}
.gv-tabla tbody tr:hover td {{ background:var(--pill); }}
.gv-tabla tbody tr:last-child td {{ border-bottom:0; }}
.gv-tabla th.num, .gv-tabla td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.gv-tabla td .vacio {{ color:var(--texto2); opacity:.6; }}
.gv-tabla td .si, .gv-tabla td .no {{ display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:6px; font-size:.72rem; font-weight:800; }}
.gv-tabla td .si {{ background:rgba(25,179,166,.16); color:{TEAL}; }}
.gv-tabla td .no {{ background:rgba(240,96,96,.14); color:{CORAL}; }}
.gv-tabla-pie {{ font-size:.72rem; color:var(--texto2); margin:-6px 2px 8px; }}
/* Tablas (widgets nativos) */
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"], div[data-testid="stTable"] {{ border-radius:14px; overflow:hidden; border:1px solid var(--borde); box-shadow:var(--sombra); background:var(--card); }}
div[data-testid="stDataFrame"] *, div[data-testid="stTable"] * {{ font-family:'Manrope', sans-serif !important; font-variant-numeric:tabular-nums; }}
div[data-testid="stTable"] table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
div[data-testid="stTable"] th {{ background:var(--card2); color:var(--texto2); font-size:.72rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; padding:9px 12px; border-bottom:1px solid var(--borde); text-align:left; }}
div[data-testid="stTable"] td {{ padding:8px 12px; border-bottom:1px solid var(--borde); color:var(--texto); }}
div[data-testid="stTable"] tr:last-child td {{ border-bottom:0; }}
div[data-testid="stTable"] tbody tr:hover td {{ background:var(--pill); }}
.stMarkdown table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:.83rem; border:1px solid var(--borde); border-radius:12px; overflow:hidden; box-shadow:var(--sombra); background:var(--card); }}
.stMarkdown table th {{ background:var(--card2); color:var(--texto2); font-size:.72rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; padding:9px 12px; border-bottom:1px solid var(--borde); text-align:left; }}
.stMarkdown table td {{ padding:8px 12px; border-bottom:1px solid var(--borde); font-variant-numeric:tabular-nums; }}
.stMarkdown table tr:last-child td {{ border-bottom:0; }}
div[data-testid="stExpander"] {{ background:var(--card); border-radius:16px; border:1px solid var(--borde); box-shadow:var(--sombra); }}
div[data-testid="stExpander"] summary, div[data-testid="stExpander"] p {{ color:var(--texto); }}
iframe {{ border-radius:20px; box-shadow:var(--sombra2); }}
div[data-testid="stPlotlyChart"] {{ background:var(--card); border:1px solid var(--borde); border-radius:20px; padding:8px 6px 2px; box-shadow:var(--sombra); animation: gv-up .5s ease both; }}
.stToggle label p {{ font-size:.8rem; }}
hr {{ border-color:var(--borde); }}
.leaflet-container {{ font-family:'Manrope', sans-serif; }}

/* ---------- Teléfonos y pantallas estrechas ---------- */
@media (max-width: 760px) {{
  .block-container {{ padding: .5rem .7rem 1.5rem !important; }}
  .gv-hero {{ padding: 16px 16px 30px; border-radius: 20px; }}
  .gv-hero-grid {{ grid-template-columns: 1fr; gap: 12px; }}
  .gv-brand {{ gap: 10px; }} .gv-brand .logo {{ width: 42px; height: 42px; border-radius: 13px; }} .gv-brand .logo svg {{ width: 24px; height: 24px; }}
  .gv-eyebrow {{ font-size: .56rem !important; letter-spacing: .14em; white-space: normal; }}
  .gv-title {{ font-size: 1.22rem !important; white-space: normal; line-height: 1.15 !important; }}
  .gv-sub {{ font-size: .76rem !important; max-width: none; }}
  .gv-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; width: 100%; }}
  .gv-stat {{ min-height: 56px; padding: 8px 10px; border-radius: 14px; }}
  .gv-stat .n {{ font-size: 1.1rem; }} .gv-stat .l {{ font-size: .62rem; }}
  .gv-chips {{ gap: 6px; margin-top: 12px; }}
  .gv-chip {{ font-size: .68rem; padding: 5px 10px; }}
  .gv-chip.proy {{ white-space: normal; max-width: 100%; }}
  .gv-olas {{ height: 60px; }}
  /* navegación principal: botones a dos columnas, ancho completo */
  .st-key-seccion {{ margin: 10px 0 2px; }}
  .st-key-seccion div[role="radiogroup"] {{ width: 100%; border-radius: 18px; gap: 4px; padding: 5px; box-sizing: border-box; flex-direction: row !important; flex-wrap: wrap !important; }}
  .st-key-seccion div[role="radiogroup"] > div {{ flex: 1 1 calc(50% - 4px); padding: 8px 6px; border-radius: 12px; display: flex; justify-content: center; }}
  .st-key-seccion label[data-testid="stRadioOption"] p {{ font-size: .74rem; white-space: normal; text-align: center; line-height: 1.2; }}
  .st-key-tema_toggle {{ margin-top: -6px; }}
  /* secciones, KPI, pestañas y tablas */
  .gv-seccion .ic {{ width: 38px; height: 38px; border-radius: 12px; }} .gv-seccion h3 {{ font-size: 1.05rem; }} .gv-seccion p {{ font-size: .74rem; }}
  .gv-kpi {{ min-height: 62px; padding: 10px 12px; border-radius: 16px; gap: 10px; }}
  .gv-kpi .ic {{ width: 36px; height: 36px; border-radius: 11px; }} .gv-kpi .ic svg {{ width: 18px; height: 18px; }}
  .gv-kpi .v {{ font-size: 1.08rem; }} .gv-kpi .l {{ font-size: .66rem; white-space: normal; }} .gv-kpi .spark {{ display: none; }}
  .stTabs [role="tablist"] {{ width: 100%; box-sizing: border-box; gap: 3px; padding: 4px; border-radius: 12px; }}
  .stTabs [data-testid="stTab"] {{ flex: 1 1 auto; padding: 6px 9px; text-align: center; }}
  .stTabs [data-testid="stTab"] p {{ font-size: .74rem; white-space: normal; }}
  .gv-tabla table {{ font-size: .74rem; }} .gv-tabla th, .gv-tabla td {{ padding: 6px 8px; }}
  .gv-panel {{ padding: 12px 12px; border-radius: 16px; }}
  .stButton > button, .stDownloadButton > button {{ width: 100%; }}
  [data-testid="stRadio"] [role="radiogroup"] {{ flex-wrap: wrap; }}
  iframe, .stPlotlyChart, [data-testid="stIFrame"] {{ max-width: 100%; }}
  /* columnas de Streamlit: dos por fila en lugar de apilarlas todas (botones, KPI, selectores) */
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child > .stButton) {{ flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child > .stButton) > [data-testid="stColumn"] {{ flex: 1 1 calc(50% - 8px) !important; width: auto !important; min-width: calc(50% - 8px) !important; }}
}}
@media (max-width: 420px) {{
  .gv-title {{ font-size: 1.08rem !important; }}
  .gv-stats {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
"""


CSS = css("claro")  # compatibilidad

_S = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'
ICONO = {
    "ola": f'<svg {_S}><path d="M2 12c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3"/><path d="M2 18c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3"/><path d="M2 6c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3"/></svg>',
    "mapa": f'<svg {_S}><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><path d="M9 4v14M15 6v14"/></svg>',
    "pin": f'<svg {_S}><path d="M12 22s7-6.1 7-12a7 7 0 1 0-14 0c0 5.9 7 12 7 12Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    "calendario": f'<svg {_S}><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/></svg>',
    "reloj": f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "satelite": f'<svg {_S}><path d="m13 7 4-4 4 4-4 4zM7 13l-4 4 4 4 4-4z"/><path d="m10 10 4 4M15 9l-2 2M9 15l2-2"/><path d="M17 15a4 4 0 0 1-2 2M19 17a6 6 0 0 1-2 2"/></svg>',
    "capas": f'<svg {_S}><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5M3 17l9 5 9-5"/></svg>',
    "regla": f'<svg {_S}><path d="m3 17 14-14 4 4L7 21z"/><path d="m8 8 2 2M11 5l2 2M14 11l2 2"/></svg>',
    "trend": f'<svg {_S}><path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/></svg>',
    "trend_down": f'<svg {_S}><path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/></svg>',
    "escudo": f'<svg {_S}><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    "alerta": f'<svg {_S}><path d="M12 3 2 21h20L12 3Z"/><path d="M12 10v5M12 18h.01"/></svg>',
    "grafico": f'<svg {_S}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    "cristal": f'<svg {_S}><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/></svg>',
    "cerebro": f'<svg {_S}><path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 2 5v1a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3Z"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-2 5v1a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3Z"/></svg>',
    "db": f'<svg {_S}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>',
    "descarga": f'<svg {_S}><path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>',
    "play": f'<svg {_S}><path d="M6 4v16l14-8z"/></svg>',
    "lineas": f'<svg {_S}><path d="M3 18c4-6 8-6 12-12M3 12c4-2 8-2 12-8M5 21c4-4 8-4 14-10"/></svg>',
    "porcentaje": f'<svg {_S}><path d="m19 5-14 14"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>',
    "check": f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>',
    "info": f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
    "globo": f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    "area": f'<svg {_S}><path d="M4 20V8l5-4 6 3 5-2v15"/><path d="M4 20h16"/></svg>',
    "sol": f'<svg {_S}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    "luna": f'<svg {_S}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>',
    "radar": f'<svg {_S}><path d="m12 3 8 6-3 9H7L4 9z"/><path d="m12 8 4 3-1.5 4.5h-5L8 11z"/><path d="M12 3v5M20 9l-4 2M17 18l-2.5-2.5M7 18l2.5-2.5M4 9l4 2"/></svg>',
}


def icono(nombre: str, color: str = AZUL, tam: int | None = None) -> str:
    svg = ICONO.get(nombre, ICONO["info"])
    estilo = f'style="color:{color};{f"width:{tam}px;height:{tam}px;" if tam else ""}"'
    return svg.replace("<svg ", f"<svg {estilo} ", 1)


def sparkline(valores, color: str = AZUL, ancho: int = 66, alto: int = 32) -> str:
    v = [float(x) for x in valores if x is not None and x == x]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = hi - lo or 1.0
    pts = [(i * (ancho - 2) / (len(v) - 1) + 1, alto - 3 - (x - lo) / rng * (alto - 8)) for i, x in enumerate(v)]
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"1,{alto} " + linea + f" {ancho - 1},{alto}"
    return (f'<svg class="spark" viewBox="0 0 {ancho} {alto}"><polygon points="{area}" fill="{color}" opacity=".14"/>'
            f'<polyline points="{linea}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'style="stroke-dasharray:300;stroke-dashoffset:300;animation:gv-dash 1.4s ease forwards"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.4" fill="{color}"/></svg>')


OLAS_HERO = (
    '<div class="gv-olas">'
    '<svg class="o1" viewBox="0 0 1200 46" preserveAspectRatio="none"><path fill="rgba(255,255,255,.16)" d="M0 26c100-26 200-26 300 0s200 26 300 0 200-26 300 0 200 26 300 0v20H0z"/></svg>'
    '<svg class="o2" viewBox="0 0 1200 46" preserveAspectRatio="none"><path fill="rgba(158,232,224,.28)" d="M0 30c100-22 200-22 300 0s200 22 300 0 200-22 300 0 200 22 300 0v16H0z"/></svg>'
    '<svg class="o3" viewBox="0 0 1200 46" preserveAspectRatio="none"><path fill="rgba(255,255,255,.22)" d="M0 36c75-14 150-14 225 0s150 14 225 0 150-14 225 0 150 14 225 0 150-14 225 0 150 14 225 0v10H0z"/></svg>'
    '</div>'
)
OLA_SUBRAYADO = '<svg class="gv-wave-u" viewBox="0 0 120 10"><path d="M1 6c7-6 14-6 21 0s14 6 21 0 14-6 21 0 14 6 21 0 14-6 21 0 14 6 14 0" fill="none" stroke="url(#gw)" stroke-width="2.2" stroke-linecap="round"/><defs><linearGradient id="gw" x1="0" x2="1"><stop offset="0" stop-color="#3B6CF0"/><stop offset="1" stop-color="#19B3A6"/></linearGradient></defs></svg>'
MARCA_OLAS = '<svg class="marca" viewBox="0 0 84 44" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M2 12c10-10 20-10 30 0s20 10 30 0 20-10 30 0"/><path d="M2 24c10-10 20-10 30 0s20 10 30 0 20-10 30 0"/><path d="M2 36c10-10 20-10 30 0s20 10 30 0 20-10 30 0"/></svg>'
LOGO_OLAS = (
    '<svg viewBox="0 0 48 48" fill="none"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9EE8E0"/><stop offset="1" stop-color="#3B6CF0"/></linearGradient></defs>'
    '<circle cx="24" cy="24" r="21" stroke="url(#lg)" stroke-width="2.5" opacity=".9"/>'
    '<path d="M9 20c5-6 10-6 15 0s10 6 15 0" stroke="#fff" stroke-width="3" stroke-linecap="round"/>'
    '<path d="M9 28c5-6 10-6 15 0s10 6 15 0" stroke="#9EE8E0" stroke-width="3" stroke-linecap="round"/>'
    '<path d="M13 35c4-4 7-4 11 0s7 4 11 0" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity=".7"/></svg>'
)

OLAS_FONDO_HERO = (
    '<div class="gv-olas-fondo"><svg viewBox="0 0 1200 300" preserveAspectRatio="none" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round">'
    '<path d="M0 70c60-40 120-40 180 0s120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0"/>'
    '<path d="M0 130c60-40 120-40 180 0s120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0"/>'
    '<path d="M0 190c60-40 120-40 180 0s120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0"/>'
    '<path d="M0 250c60-40 120-40 180 0s120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0 120 40 180 0 120-40 180 0"/>'
    '</svg></div>'
)
