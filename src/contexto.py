"""Configuración compartida en la sesión de Streamlit (una sola instancia cacheada)."""
from __future__ import annotations

import streamlit as st

from .configuracion import cargar_config, configurar_logs, rutas_salida


@st.cache_resource(show_spinner=False)
def cfg_app() -> dict:
    cfg = cargar_config()
    rutas_salida(cfg)
    configurar_logs(cfg)
    return cfg
