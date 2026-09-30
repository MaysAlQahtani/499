"""charts.py - Plotly figures: radar chart, pitch view, progress trend, position map."""
import plotly.express as px
import plotly.graph_objects as go

from db import SKILLS

ROLE_COLORS = {"GK": "#f9a825", "DF": "#1e88e5", "MF": "#43a047", "FW": "#e53935"}


def radar(items):
    """items: list of (label, player_dict)."""
    fig = go.Figure()
    for label, p in items:
        vals = [p[s] for s in SKILLS]
        fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=SKILLS + SKILLS[:1], fill="toself", name=label, opacity=0.6))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=380, margin=dict(l=40, r=40, t=30, b=30),
                      legend=dict(orientation="h", y=-0.1))
    return fig


def pitch(assignments):
    fig = go.Figure()
    line = dict(color="white", width=2)
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=line, fillcolor="#2e7d32", layer="below")
    fig.add_shape(type="line", x0=0, y0=50, x1=100, y1=50, line=line)
    fig.add_shape(type="circle", x0=41, y0=41, x1=59, y1=59, line=line)
    fig.add_shape(type="rect", x0=22, y0=0, x1=78, y1=16, line=line)
    fig.add_shape(type="rect", x0=22, y0=84, x1=78, y1=100, line=line)
    for a in assignments:
        p = a["player"]
        fig.add_trace(go.Scatter(
            x=[a["x"]], y=[a["y"]], mode="markers+text", text=[p["PlayerName"]], textposition="bottom center",
            textfont=dict(color="white", size=11), showlegend=False,
            marker=dict(size=26, color=ROLE_COLORS[a["role"]], line=dict(color="white", width=2)),
            hovertext=f"{a['slot']} - {p['PlayerName']}<br>Overall {p['OverallScore']} | Role fit {a['fit']:.0f}",
            hoverinfo="text"))
    fig.update_xaxes(visible=False, range=[-2, 102])
    fig.update_yaxes(visible=False, range=[-4, 104])
    fig.update_layout(height=640, margin=dict(l=0, r=0, t=0, b=0), plot_bgcolor="#2e7d32")
    return fig


def trend(history, name):
    xs = [h["LastUpdate"] for h in history]
    fig = go.Figure(go.Scatter(x=xs, y=[h["CurrentScore"] for h in history], mode="lines+markers", name="Overall"))
    fig.update_layout(title=f"{name} - overall score over time", yaxis=dict(range=[0, 100], title="Overall score"),
                      xaxis_title="Update date", height=380, margin=dict(l=40, r=20, t=50, b=40))
    return fig


def position_map(df):
    fig = px.scatter(df, x="x", y="y", color="Suggested role", text="Player", color_discrete_map=ROLE_COLORS,
                     hover_data=["Current position"])
    fig.update_traces(textposition="top center", marker=dict(size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10))
    return fig
