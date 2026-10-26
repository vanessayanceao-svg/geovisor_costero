"""Caché compatible con Streamlit que también funciona fuera de él (pruebas, scripts).

``cachear_datos`` envuelve ``st.cache_data`` cuando Streamlit está disponible y
en ejecución; de lo contrario usa ``functools.lru_cache``. Las funciones
decoradas deben recibir argumentos *hashables* (rutas como str, no Path).
"""
from __future__ import annotations

import functools
import os


def _en_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:  # noqa: BLE001
        return False


def cachear_datos(ttl: int | None = 3600, max_entries: int | None = 64, show_spinner: bool = False):
    def decorador(fn):
        if _en_streamlit():
            import streamlit as st

            return st.cache_data(ttl=ttl, max_entries=max_entries, show_spinner=show_spinner)(fn)
        return functools.lru_cache(maxsize=max_entries or 64)(fn)

    return decorador


def cachear_recurso(fn):
    if _en_streamlit():
        import streamlit as st

        return st.cache_resource(show_spinner=False)(fn)
    return functools.lru_cache(maxsize=16)(fn)


def firma_archivo(ruta: str | os.PathLike) -> tuple[str, float, int]:
    """(ruta, mtime, tamaño): invalida la caché cuando el archivo cambia."""
    st_ = os.stat(ruta)
    return (str(ruta), st_.st_mtime, st_.st_size)
