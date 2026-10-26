"""COASTAL VULNERABILITY — BARRA DE SALAMANCA · aplicación Streamlit.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.catalogo_datos import CAPAS, estado_modulos  # noqa: E402
from src.contexto import cfg_app as _cfg  # noqa: E402
from src.estilos import LOGO_OLAS, OLAS_FONDO_HERO, OLAS_HERO, css, icono  # noqa: E402
from src.paginas import calculadora as pag_calculadora  # noqa: E402
from src.paginas import datos as pag_datos  # noqa: E402
from src.paginas import erosion as pag_erosion  # noqa: E402
from src.paginas import evaluacion as pag_evaluacion  # noqa: E402
from src.paginas import evolucion as pag_evolucion  # noqa: E402
from src.paginas import ivc as pag_ivc  # noqa: E402
from src.paginas import predicciones as pag_predicciones  # noqa: E402
from src.paginas import visor as pag_visor  # noqa: E402

st.set_page_config(page_title="Coastal Vulnerability — Barra de Salamanca", page_icon="🌊", layout="wide", initial_sidebar_state="collapsed")

SECCIONES = [
    (":material/map: Visor geoespacial", "visor", pag_visor),
    (":material/history: Evolución histórica", "evolucion", pag_evolucion),
    (":material/waves: Línea de costa y erosión", "erosion", pag_erosion),
    (":material/shield: Vulnerabilidad costera (IVC)", "ivc", pag_ivc),
    (":material/insights: Predicciones y escenarios", "predicciones", pag_predicciones),
    (":material/psychology: Evaluación del modelo", "evaluacion", pag_evaluacion),
    (":material/calculate: Calculadora IVC", "calculadora", pag_calculadora),
    (":material/database: Datos y metodología", "datos", pag_datos),
]


@st.cache_data(ttl=600, show_spinner=False)
def _contexto_cabecera(_cfg_id: str) -> dict:
    """Periodo real de observaciones y fecha de actualización verificada (mtime de los archivos fuente)."""
    cfg = _cfg()
    ctx = {"periodo": None, "actualizacion": None, "n_fechas": None}
    try:
        from src.temporal import cargar_lineas_fecha, observaciones

        obs = observaciones(cargar_lineas_fecha(cfg))
        if obs:
            ctx["periodo"] = (obs[0].fecha, obs[-1].fecha)
            ctx["n_fechas"] = len(obs)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("geovisor").warning("Cabecera: %s", e)
    mt = []
    for clave in ("lineas_anuales_dsas", "lineas_fecha", "dsas_tasas", "ivc_transectos", "proy_amortiguada", "metricas_anidadas"):
        p = CAPAS[clave].ruta(cfg)
        if p.exists():
            mt.append(p.stat().st_mtime)
    if mt:
        ctx["actualizacion"] = datetime.fromtimestamp(max(mt))
    return ctx


@st.cache_data(show_spinner=False)
def _fondo_b64(tema: str) -> str | None:
    """PNG transparente del mapa (malla de tierra + línea de costa real) generado desde los datos."""
    import base64

    ruta = RAIZ / "assets" / f"fondo_mapa_{tema}.png"
    if not ruta.exists():
        try:
            from scripts.generar_fondo import generar

            generar(_cfg())
        except Exception as e:  # noqa: BLE001
            logging.getLogger("geovisor").warning("No se pudo generar el fondo: %s", e)
            return None
    return base64.b64encode(ruta.read_bytes()).decode("ascii") if ruta.exists() else None


def cabecera(cfg: dict) -> None:
    app = cfg["aplicacion"]
    ctx = _contexto_cabecera("v1")
    mods = estado_modulos(cfg)
    periodo = f"{ctx['periodo'][0]:%Y} – {ctx['periodo'][1]:%Y}" if ctx["periodo"] else "—"
    actualizacion = f"{ctx['actualizacion']:%d-%m-%Y}" if ctx["actualizacion"] else "no verificada"
    stats = [
        (f"{ctx['n_fechas']}" if ctx["n_fechas"] else "—", "líneas anuales DSAS" if cfg["temporal"].get("capa_lineas", "lineas_anuales_dsas") == "lineas_anuales_dsas" else "fechas Landsat", "satelite"),
        (periodo, "periodo histórico", "calendario"),
        ("671", "transectos DSAS", "regla") if mods["DSAS"]["ok"] else ("—", "transectos DSAS", "regla"),
        ("2050 · 2100", "horizontes", "cristal") if mods["Predicciones"]["ok"] else ("—", "horizontes", "cristal"),
    ]
    stats_html = "".join(f'<div class="gv-stat" style="animation-delay:{i * 80}ms"><div class="n">{n}</div><div class="l">{icono(ic, "#fff")}{l}</div></div>' for i, (n, l, ic) in enumerate(stats))
    iconos_mod = {"Histórico": "lineas", "DSAS": "regla", "IVC": "escudo", "Predicciones": "cristal", "Evaluación": "cerebro"}
    mods_html = "".join(f'<span class="gv-mod" title="{v["detalle"]}"><span class="gv-dot {"gv-ok" if v["ok"] else "gv-no"}"></span>{icono(iconos_mod.get(k, "info"), "#1B2440", 13)}{k}</span>' for k, v in mods.items())
    chips = (f'<span class="gv-chip proy">{icono("pin", "#fff")}<span class="k">Proyecto</span><b>{app["area_estudio"]}</b></span>'
             f'<span class="gv-chip" title="Fecha de modificación más reciente de los archivos fuente">{icono("reloj", "#fff")}Datos actualizados <b>{actualizacion}</b></span>')
    st.markdown(
        f'<div class="gv-hero">{OLAS_FONDO_HERO}<div class="gv-hero-grid"><div class="gv-brand"><div class="logo">{LOGO_OLAS}</div>'
        f'<div><p class="gv-eyebrow">Geovisor científico · {app["institucion"].split(" · ")[0]}</p><p class="gv-title">COASTAL <span>VULNERABILITY</span> SYSTEM</p><p class="gv-sub">{app["subtitulo"]}</p></div></div>'
        f'<div class="gv-stats">{stats_html}</div></div><div class="gv-chips">{chips}<span style="flex:1"></span>{mods_html}</div></div>',
        unsafe_allow_html=True,
    )


def _bloquear_traduccion() -> None:
    """Evita que el traductor automático del navegador (Google Translate) reescriba el DOM de Streamlit.

    Al traducir, el navegador sustituye nodos de texto y React falla con
    «NotFoundError: Failed to execute 'removeChild' on 'Node'». El componente corre en el mismo origen
    (localhost), por lo que puede marcar la página padre como no traducible.
    """
    components.html(
        """<script>
        try {
          const d = window.parent.document;
          d.documentElement.setAttribute('translate', 'no');
          d.documentElement.classList.add('notranslate');
          d.documentElement.lang = 'es';
          if (!d.querySelector('meta[name="google"][content="notranslate"]')) {
            const m = d.createElement('meta'); m.name = 'google'; m.content = 'notranslate'; d.head.appendChild(m);
          }
        } catch (e) {}
        </script>""",
        height=0,
    )


def main() -> None:
    cfg = _cfg()
    st.session_state.setdefault("tema", "claro")
    _bloquear_traduccion()
    st.markdown(css(st.session_state["tema"], _fondo_b64(st.session_state["tema"])), unsafe_allow_html=True)
    cabecera(cfg)
    etiquetas = [s[0] for s in SECCIONES if cfg["modulos"].get(s[1], True)]
    c_nav, c_tema = st.columns([7.5, 1])
    with c_nav:
        seleccion = st.radio("Sección", etiquetas, horizontal=True, label_visibility="collapsed", key="seccion")
    with c_tema:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        oscuro = st.toggle("🌙 Modo oscuro", value=st.session_state["tema"] == "oscuro", key="tema_toggle")
        nuevo_tema = "oscuro" if oscuro else "claro"
        if nuevo_tema != st.session_state["tema"]:
            st.session_state["tema"] = nuevo_tema
            st.rerun()
    for titulo, clave, modulo in SECCIONES:
        if titulo == seleccion:
            try:
                modulo.render(cfg)
            except Exception as e:  # noqa: BLE001 — un módulo roto no debe tumbar la aplicación
                logging.getLogger("geovisor").exception("Error en la sección %s", clave)
                st.error(f"La sección «{titulo.split(' ', 1)[-1]}» no pudo mostrarse: {type(e).__name__}: {e}")
                st.caption("Revise logs/geovisor.log. Los demás módulos siguen disponibles.")
            break


if __name__ == "__main__":
    main()
