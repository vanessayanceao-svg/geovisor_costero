"""Gráficos interactivos (Plotly) con estilo unificado. Todos reciben datos reales ya cargados."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .estilos import AMBAR, AZUL, CORAL, GRIS, TEAL, TINTA, VIOLETA

PLANTILLA = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Manrope, system-ui, sans-serif", size=12, color=TINTA),
    margin=dict(l=44, r=18, t=64, b=44), hoverlabel=dict(bgcolor="#1B2440", font=dict(color="#fff", family="Manrope", size=12), bordercolor="#1B2440"),
    legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1.0, xanchor="right", font=dict(size=11), bgcolor="rgba(0,0,0,0)"), transition=dict(duration=600, easing="cubic-in-out"),
    colorway=[AZUL, TEAL, CORAL, AMBAR, "#8E6BF5", "#2CB8E8"],
)
COLOR_ACENTO = AZUL
COLOR_SEL = CORAL


def _estilo(fig: go.Figure, titulo: str | None = None, altura: int = 320) -> go.Figure:
    fig.update_layout(**PLANTILLA, height=altura, hovermode="closest")
    if titulo:
        fig.update_layout(title=dict(text=titulo, x=0.01, y=0.985, yanchor="top", font=dict(size=14, family="Poppins", color=TINTA, weight=600)))
    fig.update_xaxes(gridcolor="#EEF1F6", zerolinecolor="#D9DFEA", linecolor="#E6EBF5", tickfont=dict(color=GRIS), title_font=dict(color=GRIS))
    fig.update_yaxes(gridcolor="#EEF1F6", zerolinecolor="#D9DFEA", linecolor="#E6EBF5", tickfont=dict(color=GRIS), title_font=dict(color=GRIS))
    return fig


def aplicar_tema(fig: go.Figure, tema: str) -> go.Figure:
    """Ajusta colores de texto/rejilla al tema activo (claro/oscuro)."""
    if tema == "oscuro":
        fig.update_layout(font=dict(color="#EEF2FA"), title_font=dict(color="#EEF2FA"), legend=dict(font=dict(color="#C9D3EA")))
        fig.update_xaxes(gridcolor="rgba(255,255,255,.07)", zerolinecolor="rgba(255,255,255,.2)", linecolor="rgba(255,255,255,.1)", tickfont=dict(color="#93A1C0"), title_font=dict(color="#93A1C0"))
        fig.update_yaxes(gridcolor="rgba(255,255,255,.07)", zerolinecolor="rgba(255,255,255,.2)", linecolor="rgba(255,255,255,.1)", tickfont=dict(color="#93A1C0"), title_font=dict(color="#93A1C0"))
        if fig.layout.polar:
            fig.update_polars(bgcolor="rgba(0,0,0,0)", radialaxis=dict(gridcolor="rgba(255,255,255,.12)", tickfont=dict(color="#93A1C0")), angularaxis=dict(gridcolor="rgba(255,255,255,.12)", tickfont=dict(color="#C9D3EA")))
        for a in fig.layout.annotations:
            a.font.color = "#EEF2FA"
    return fig


def radar(categorias: list[str], series: dict[str, list[float]], titulo: str, rango=(0, 5), altura: int = 380) -> go.Figure:
    """Gráfico de radar (estilo «Structure» de las referencias) con una o varias series."""
    fig = go.Figure()
    paleta = [AZUL, TEAL, CORAL, VIOLETA]
    for i, (nombre, vals) in enumerate(series.items()):
        c = paleta[i % len(paleta)]
        fig.add_trace(go.Scatterpolar(r=list(vals) + [vals[0]], theta=categorias + [categorias[0]], fill="toself", name=nombre,
                                      line=dict(color=c, width=2), fillcolor=c.replace(")", ",0.18)").replace("rgb", "rgba") if c.startswith("rgb") else c + "2E",
                                      marker=dict(size=6, color=c, line=dict(color="#fff", width=1)), hovertemplate="%{theta}: %{r:.2f}<extra>" + nombre + "</extra>"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, range=list(rango), gridcolor="#E6EBF5", tickfont=dict(size=9, color=GRIS)),
                                 angularaxis=dict(gridcolor="#E6EBF5", tickfont=dict(size=10))), showlegend=len(series) > 1)
    return _estilo(fig, titulo, altura)


def donut(etiquetas, valores, colores, titulo: str, centro: str = "", altura: int = 300) -> go.Figure:
    """Gráfico de anillo con texto central (estilo tarjeta de las referencias)."""
    fig = go.Figure(go.Pie(labels=etiquetas, values=valores, hole=0.66, marker=dict(colors=colores, line=dict(color="#fff", width=3)),
                           textinfo="none", hovertemplate="%{label}: %{value:.1f} (%{percent})<extra></extra>", sort=False, direction="clockwise", rotation=90))
    fig.update_layout(annotations=[dict(text=centro, x=0.5, y=0.5, showarrow=False, font=dict(size=20, family="Poppins", color=TINTA, weight=700))], showlegend=True)
    fig = _estilo(fig, titulo, altura)
    fig.update_layout(legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=11)))
    return fig


def longitud_por_fecha(df: pd.DataFrame, fecha_sel=None) -> go.Figure:
    fig = px.scatter(df, x="fecha", y="largo_m", color="satelite", hover_data={"cobertura_pct": ":.1f", "n_lados": True},
                     labels={"largo_m": "Longitud de línea (m)", "fecha": "Fecha de observación", "satelite": "Sensor"},
                     color_discrete_sequence=["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3"])
    fig.update_traces(marker=dict(size=7, opacity=0.85, line=dict(width=1, color="#fff")))
    if fecha_sel is not None:
        fig.add_vline(x=pd.Timestamp(fecha_sel).timestamp() * 1000, line_color=COLOR_SEL, line_width=2, line_dash="dot")
    fig = _estilo(fig, "Longitud total de la línea de costa por fecha (campo 'largo_m' importado)", 380)
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.07), rangeselector=dict(buttons=[
        dict(count=10, label="10 a", step="year", stepmode="backward"), dict(count=20, label="20 a", step="year", stepmode="backward"), dict(step="all", label="Todo")],
        bgcolor="#EEF2FA", activecolor="#E3EBFF", font=dict(size=10)))
    return fig


def observaciones_por_anio(cobertura: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=cobertura["anio"], y=cobertura["n_fechas"], name="Fechas con línea", marker_color=COLOR_ACENTO)
    if "completas_oeste" in cobertura:
        fig.add_bar(x=cobertura["anio"], y=cobertura["completas_oeste"], name="Completas (oeste)", marker_color="#66c2a5", opacity=0.8)
    fig.update_layout(barmode="overlay", xaxis_title="Año", yaxis_title="N.º de fechas", bargap=0.25)
    fig.update_traces(marker=dict(cornerradius=6))
    return _estilo(fig, "Observaciones por año (postproceso/cobertura_por_anio.csv)", 300)


def tasa_por_transecto(g: pd.DataFrame, campo: str, unidad: str, x: str = "dist_costa_km", ci: str | None = None, seleccion=None) -> go.Figure:
    d = g.sort_values(x) if x in g.columns else g.reset_index()
    xx = d[x] if x in d.columns else d.index
    fig = go.Figure()
    if ci and ci in d.columns:
        fig.add_scatter(x=pd.concat([xx, xx[::-1]]), y=pd.concat([d[campo] + d[ci], (d[campo] - d[ci])[::-1]]), fill="toself",
                        fillcolor="rgba(59,108,240,.14)", line=dict(width=0), name="IC95", hoverinfo="skip")
    colores = [CORAL if v < 0 else AZUL for v in d[campo].fillna(0)]
    fig.add_scatter(x=xx, y=d[campo], mode="markers+lines", marker=dict(color=colores, size=5), line=dict(color="rgba(27,36,64,.25)", width=1),
                    name=campo, customdata=d[["TransOrder"]] if "TransOrder" in d else None,
                    hovertemplate=("Transecto %{customdata[0]}<br>" if "TransOrder" in d else "") + "km %{x:.1f}<br>" + campo + " = %{y:.2f} " + unidad + "<extra></extra>")
    fig.add_hline(y=0, line_color="rgba(27,36,64,.4)", line_width=1)
    if seleccion is not None:
        fig.add_vline(x=seleccion, line_color=COLOR_SEL, line_width=2)
    fig.update_layout(xaxis_title="Distancia desde Bocas de Ceniza (km)" if x == "dist_costa_km" else x, yaxis_title=f"{campo} ({unidad})")
    return _estilo(fig, f"{campo} a lo largo de la costa (rojo = retroceso, azul = avance)", 340)


def histograma(serie: pd.Series, titulo: str, unidad: str, nbins: int = 40, cortes: list | None = None, color: str = COLOR_ACENTO) -> go.Figure:
    fig = go.Figure(go.Histogram(x=serie.dropna(), nbinsx=nbins, marker_color=color, opacity=0.9, marker=dict(cornerradius=4)))
    for c in cortes or []:
        fig.add_vline(x=c, line_dash="dot", line_color="rgba(27,36,64,.45)")
    fig.update_layout(xaxis_title=f"{titulo} ({unidad})", yaxis_title="Frecuencia", bargap=0.05)
    return _estilo(fig, f"Distribución de {titulo}", 280)


def alcance_ruta90(d, colores: dict, titulo: str = "Año en que la costa proyectada alcanza la Ruta 90 (SSP5‑8.5)", altura: int = 420) -> go.Figure:
    """Barras por tramo de 1 km (base 2026, tope = año de alcance; sin alcance = 2110 con marcador) coloreadas por prioridad,
    con el intervalo erosión rápida/lenta como barra de error. Reproduce el panel (b) de la Figura 37."""
    import numpy as np

    fig = go.Figure()
    tope = 2110
    d = d.sort_values("km_inicio")
    for pr, color in colores.items():
        s = d[d["prioridad"] == pr]
        if s.empty:
            continue
        a = s["anio_alcance"].replace(np.inf, tope).clip(upper=tope)
        rap = s.get("anio_alcance_erosion_rapida", a).replace(np.inf, tope).clip(upper=tope)
        len_ = s.get("anio_alcance_erosion_lenta", a).replace(np.inf, tope).clip(upper=tope)
        fig.add_bar(x=s["km_inicio"] + 0.5, y=a - 2026, base=2026, name=pr, marker_color=color, width=0.85,
                    error_y=dict(type="data", symmetric=False, array=(len_ - a).clip(lower=0), arrayminus=(a - rap).clip(lower=0), color="#2b2f3a", thickness=1),
                    customdata=np.c_[s["tramo"], s["dist_min_ruta90_m"], s["anio_alcance"].map(lambda v: "> 2110 (sin alcance)" if not np.isfinite(v) else f"{v:.1f}"), s.get("km_via_inicio", a), s.get("km_via_fin", a)],
                    hovertemplate="<b>%{customdata[0]}</b> de la costa<br>Vía a %{customdata[1]:.0f} m · km vía %{customdata[3]}–%{customdata[4]}<br>Alcance: %{customdata[2]}<extra></extra>")
    for y, txt, dash in ((2050, "2050", "dash"), (2100, "2100", "dot")):
        fig.add_hline(y=y, line_dash=dash, line_color="#55596a", line_width=1, annotation_text=txt, annotation_position="top left")
    fig.update_layout(barmode="overlay", xaxis_title="Distancia a lo largo de la costa desde Bocas de Ceniza (km)", yaxis_title="Año en que la costa alcanza la vía",
                      yaxis=dict(range=[2024, 2114], tickvals=[2026, 2050, 2075, 2100, 2110], ticktext=["2026", "2050", "2075", "2100", "> 2110"]), legend_title_text="Prioridad")
    return _estilo(fig, titulo, altura)


def barras_clases(pct: dict, cfg: dict, titulo: str = "Transectos por clase") -> go.Figure:
    clases = cfg["ivc"]["clases"]
    ks = sorted(clases)
    fig = go.Figure(go.Bar(x=[f"{k} · {clases[k]['nombre']}" for k in ks], y=[pct.get(k, 0) for k in ks],
                           marker_color=[clases[k]["color"] for k in ks], text=[f"{pct.get(k, 0):.1f} %" for k in ks], textposition="outside", marker=dict(cornerradius=8)))
    fig.update_layout(yaxis_title="% de transectos", yaxis_range=[0, max(60, max(pct.values(), default=0) * 1.2)])
    return _estilo(fig, titulo, 300)


def ivc_por_km(g: pd.DataFrame, col: str, cfg: dict, col_inf: str | None = None, col_sup: str | None = None, titulo: str = "IVC a lo largo de la costa") -> go.Figure:
    d = g.sort_values("dist_costa_km")
    fig = go.Figure()
    if col_inf and col_sup and col_inf in d and col_sup in d:
        fig.add_scatter(x=pd.concat([d["dist_costa_km"], d["dist_costa_km"][::-1]]), y=pd.concat([d[col_sup], d[col_inf][::-1]]), fill="toself",
                        fillcolor="rgba(27,36,64,.10)", line=dict(width=0), name="Intervalo (inf–sup)", hoverinfo="skip")
    clases = cfg["ivc"]["clases"]
    cortes = cfg["ivc"]["cortes"]
    limites = [0.0, *cortes, 1.0]
    for i, k in enumerate(sorted(clases)):
        fig.add_hrect(y0=limites[i], y1=limites[i + 1], fillcolor=clases[k]["color"], opacity=0.10, line_width=0)
    fig.add_scatter(x=d["dist_costa_km"], y=d[col], mode="lines", line=dict(color=TINTA, width=1.8, shape="spline", smoothing=0.6), name=col,
                    hovertemplate="km %{x:.1f}<br>IVC = %{y:.3f}<extra></extra>")
    fig.update_layout(xaxis_title="Distancia desde Bocas de Ceniza (km)", yaxis_title="IVC (0–1)", yaxis_range=[0, 1])
    return _estilo(fig, titulo, 320)


def comparacion_versiones(g: pd.DataFrame, cols: dict[str, str]) -> go.Figure:
    d = g.sort_values("dist_costa_km")
    fig = go.Figure()
    for etiqueta, col in cols.items():
        if col in d:
            fig.add_scatter(x=d["dist_costa_km"], y=d[col], mode="lines", name=etiqueta, line=dict(width=1.5))
    fig.update_layout(xaxis_title="Distancia desde Bocas de Ceniza (km)", yaxis_title="IVC (0–1)", yaxis_range=[0, 1])
    return _estilo(fig, "Comparación de versiones del IVC por transecto", 320)


def metricas_modelos(df: pd.DataFrame, metrica: str, etiqueta: str, inf: str | None = None, sup: str | None = None) -> go.Figure:
    d = df.sort_values(metrica, ascending=False)
    err = None
    if inf and sup and inf in d and sup in d:
        err = dict(type="data", symmetric=False, array=(d[sup] - d[metrica]).clip(lower=0), arrayminus=(d[metrica] - d[inf]).clip(lower=0), color="rgba(27,36,64,.45)")
    fig = go.Figure(go.Bar(x=d["nombre"], y=d[metrica], error_y=err, marker_color=[AMBAR if "persistencia" in str(m) else (TEAL if v > 0 else CORAL) for m, v in zip(d["modelo"], d[metrica].fillna(0))],
                           marker=dict(cornerradius=6), hovertemplate="%{x}<br>" + etiqueta + " = %{y:.3f}<extra></extra>"))
    fig.add_hline(y=0, line_color="rgba(27,36,64,.4)")
    fig.update_layout(yaxis_title=etiqueta, xaxis_tickangle=-30)
    return _estilo(fig, f"{etiqueta} por modelo (validación anidada, fuera de bloque)", 380)


def observado_vs_predicho(df: pd.DataFrame, col_obs: str, col_pred: str, nombre: str) -> go.Figure:
    d = df[[col_obs, col_pred]].dropna()
    fig = px.scatter(d, x=col_obs, y=col_pred, opacity=0.6, labels={col_obs: "Δ observado (m/año)", col_pred: "Δ predicho (m/año)"}, color_discrete_sequence=[COLOR_ACENTO])
    lim = [float(min(d.min())), float(max(d.max()))] if not d.empty else [-1, 1]
    fig.add_scatter(x=lim, y=lim, mode="lines", line=dict(color="rgba(27,36,64,.5)", dash="dot"), name="1:1")
    return _estilo(fig, f"Observado frente a predicho — {nombre}", 340)


def lineas_proyectadas_resumen(df: pd.DataFrame, x: str, y: str, color: str | None, titulo: str) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, barmode="group", color_discrete_sequence=["#66c2a5", "#fc8d62", "#8da0cb"])
    return _estilo(fig, titulo, 320)


def escenarios_barras(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    d = df.copy()
    fig.add_bar(x=d["clave"], y=d["pct_alta_muy_alta"], name="% transectos clase alta + muy alta", marker_color=CORAL, marker=dict(cornerradius=8),
                error_y=dict(type="data", symmetric=False, array=(d["pct_alta_mc_p95"] - d["pct_alta_muy_alta"]).fillna(0),
                             arrayminus=(d["pct_alta_muy_alta"] - d["pct_alta_mc_p05"]).fillna(0), color="rgba(27,36,64,.45)") if "pct_alta_mc_p95" in d else None)
    fig.update_layout(yaxis_title="% de transectos", xaxis_title="Escenario")
    return _estilo(fig, "Transectos en clase alta o muy alta por escenario (barras de error = p05–p95 Monte Carlo)", 320)


def evolucion_animada(df_anual: pd.DataFrame, titulo: str = "Evolución anual", unidad: str = "") -> go.Figure:
    """Animación (botón ▶) de una serie anual real: cada fotograma añade un año (sin interpolar)."""
    d = df_anual.dropna(subset=["anio", "valor"]).sort_values("anio")
    anios = [int(a) for a in d["anio"].unique()]
    if not anios:
        return _estilo(go.Figure(), titulo, 300)

    def traza(hasta):
        dd = d[d["anio"] <= hasta]
        return go.Scatter(x=dd["anio"], y=dd["valor"], mode="lines+markers", line=dict(color=AZUL, width=2.5, shape="spline", smoothing=0.5), marker=dict(size=7, color=TEAL, line=dict(width=1.5, color="#fff")),
                          fill="tozeroy", fillcolor="rgba(59,108,240,.08)", hovertemplate="%{x}: %{y:,.0f} " + unidad + "<extra></extra>")

    fig = go.Figure(data=[traza(anios[-1])], frames=[go.Frame(name=str(a), data=[traza(a)]) for a in anios])
    fig.update_layout(
        xaxis=dict(range=[anios[0] - 1, anios[-1] + 1], title="Año"), yaxis=dict(range=[float(d["valor"].min()) * 0.9, float(d["valor"].max()) * 1.08], title=unidad),
        updatemenus=[dict(type="buttons", direction="left", showactive=False, x=1.0, xanchor="right", y=1.22, bgcolor="#EEF2FA", bordercolor="#DCE3F1", font=dict(size=11), buttons=[
            dict(label="▶ Reproducir", method="animate", args=[None, dict(frame=dict(duration=160, redraw=True), fromcurrent=True, transition=dict(duration=100))]),
            dict(label="⏸ Pausa", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])],
        sliders=[dict(active=len(anios) - 1, pad=dict(t=28), currentvalue=dict(prefix="Hasta el año ", font=dict(size=12)), bgcolor="#EEF2FA", bordercolor="#DCE3F1", tickcolor="#DCE3F1",
                      steps=[dict(method="animate", label=str(a), args=[[str(a)], dict(mode="immediate", frame=dict(duration=0, redraw=True))]) for a in anios])],
    )
    return _estilo(fig, titulo, 400)
