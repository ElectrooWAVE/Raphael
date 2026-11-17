"""Plotly figures with a minimal light style."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

HIST, FCST, BAND = "#1F4E79", "#C2571A", "rgba(194,87,26,0.15)"


def _base(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title, template="plotly_white", paper_bgcolor="#FAF8F5", plot_bgcolor="#FAF8F5",
        font=dict(family="Inter, Arial, sans-serif", size=13, color="#1F2933"),
        margin=dict(l=10, r=10, t=50, b=10), height=420, hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0), xaxis_title=None, yaxis_title="Units sold",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E7E2DA")
    return fig


def history_figure(s: pd.DataFrame, title: str = "Historical daily sales") -> go.Figure:
    fig = _base(title)
    fig.add_scatter(x=s["date"], y=s["sales"], mode="lines", name="Historical sales",
                    line=dict(color=HIST, width=1.2))
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def combined_figure(s: pd.DataFrame, f: pd.DataFrame, history_days: int = 180) -> go.Figure:
    recent = s.tail(history_days)
    fig = _base("Historical sales and Chronos-2 forecast")
    fig.add_scatter(x=recent["date"], y=recent["sales"], mode="lines", name="Historical sales",
                    line=dict(color=HIST, width=1.5))
    fig.add_scatter(x=f["date"], y=f["q90"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=f["date"], y=f["q10"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=BAND, name="80% interval (10th-90th pct)", hoverinfo="skip")
    fig.add_scatter(x=f["date"], y=f["median"], mode="lines", name="Predicted demand (median)",
                    line=dict(color=FCST, width=2))
    return fig
