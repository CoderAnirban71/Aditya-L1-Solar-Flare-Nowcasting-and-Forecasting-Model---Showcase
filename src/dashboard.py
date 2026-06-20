# src/dashboard.py
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nowcast import load_data, get_flare_at, classify_flare, get_summary_stats

try:
    from forecast import FlareForecaster
    FORECAST_AVAILABLE = True
except Exception as e:
    FORECAST_AVAILABLE = False

# ── PAGE CONFIG ──────────────────────────────────────────────
st.set_page_config(
    page_title = "Solar Flare Monitor — Aditya-L1",
    page_icon  = "☀️",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  [data-testid="collapsedControl"] { display: none; }
  .block-container { padding: 0.5rem 1.5rem 1rem; }

  .top-header {
    background: linear-gradient(90deg, #0a0e1a 0%, #0f1628 100%);
    border-bottom: 2px solid #F97316;
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    border-radius: 8px;
  }
  .header-title {
    color: #F97316;
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .header-sub {
    color: #64748b;
    font-size: 0.75rem;
    margin-top: 2px;
  }
  .header-badge {
    background: rgba(249,115,22,0.15);
    border: 1px solid #F97316;
    color: #F97316;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .metric-row {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
  }
  .metric-box {
    background: #0f1628;
    border: 1px solid #1e2d4a;
    border-radius: 8px;
    padding: 8px 14px;
    flex: 1;
    text-align: center;
  }
  .metric-label {
    color: #64748b;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .metric-value {
    color: #e2e8f0;
    font-size: 1rem;
    font-weight: 600;
    margin-top: 2px;
  }

  .panel {
    background: #0f1628;
    border: 1px solid #1e2d4a;
    border-radius: 10px;
    padding: 14px;
    height: 100%;
  }
  .panel-title {
    color: #94a3b8;
    font-size: 0.75rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 10px;
    border-bottom: 1px solid #1e2d4a;
    padding-bottom: 6px;
  }

  .alert-box {
    border-radius: 8px;
    padding: 14px;
    text-align: center;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    margin-bottom: 10px;
  }
  .alert-quiet    { background:#051a0f; border:2px solid #1db954; color:#1db954; }
  .alert-low      { background:#0f1a05; border:2px solid #7cbb00; color:#7cbb00; }
  .alert-moderate { background:#1a1500; border:2px solid #f0a500; color:#f0a500; }
  .alert-high     { background:#1a0800; border:2px solid #ff6b00; color:#ff6b00; }
  .alert-extreme  { background:#1a0000; border:2px solid #ff0000; color:#ff0000;
                    animation: pulse 1s infinite; }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(255,0,0,0.4); }
    50%      { box-shadow: 0 0 0 8px rgba(255,0,0,0); }
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 5px 0;
    border-bottom: 1px solid #1e2d4a;
    font-size: 0.82rem;
  }
  .info-label { color: #64748b; }
  .info-value { color: #e2e8f0; font-weight: 500; }

  .controls-bar {
    background: #0f1628;
    border: 1px solid #1e2d4a;
    border-radius: 8px;
    padding: 8px 16px;
    margin-bottom: 10px;
  }

  .perf-box {
    background: #0a0e1a;
    border: 1px solid #1e2d4a;
    border-radius: 6px;
    padding: 8px;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
  }
</style>
""", unsafe_allow_html=True)

# ── LOAD DATA ────────────────────────────────────────────────
@st.cache_data
def load_all():
    master, catalog = load_data()
    stats = get_summary_stats(catalog)
    return master, catalog, stats

master, catalog, stats = load_all()

@st.cache_resource
def load_forecaster():
    if FORECAST_AVAILABLE:
        try:
            return FlareForecaster()
        except Exception:
            return None
    return None

forecaster = load_forecaster()

# ── SESSION STATE ────────────────────────────────────────────
if "idx"     not in st.session_state: st.session_state.idx     = 1000
if "playing" not in st.session_state: st.session_state.playing = False
if "speed"   not in st.session_state: st.session_state.speed   = 60
if "show_ctrl" not in st.session_state: st.session_state.show_ctrl = False

SOFT_COL = "SOLEXS_COUNTS"
HARD_COL = "CDTE_1p8_90keV_CTR"

# ── HEADER ───────────────────────────────────────────────────
st.markdown("""
<div class="top-header">
  <div>
    <div class="header-title">☀️ SOLAR FLARE MONITORING & FORECASTING — ISRO ADITYA-L1</div>
    <div class="header-sub">SoLEXS (Soft X-ray) + HEL1OS (Hard X-ray) · July 2024 Replay Mode</div>
  </div>
  <div class="header-badge">🇮🇳 BHARTIYA ANTARIKSH HACKATHON</div>
</div>
""", unsafe_allow_html=True)

# ── CONTROLS BAR ─────────────────────────────────────────────
ctrl_toggle = st.button(
    "⚙️ Controls" if not st.session_state.show_ctrl else "✕ Hide Controls"
)
if ctrl_toggle:
    st.session_state.show_ctrl = not st.session_state.show_ctrl

if st.session_state.show_ctrl:
    with st.container():
        st.markdown('<div class="controls-bar">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1,1,2,3])
        with c1:
            if st.button("▶ Play" if not st.session_state.playing else "⏸ Pause"):
                st.session_state.playing = not st.session_state.playing
        with c2:
            if st.button("⏮ Reset"):
                st.session_state.idx     = 1000
                st.session_state.playing = False
        with c3:
            speed = st.select_slider(
                "Speed",
                options=[10, 30, 60, 120, 300, 600],
                value=st.session_state.speed,
                label_visibility="collapsed"
            )
            st.session_state.speed = speed
        with c4:
            idx = st.slider(
                "Timeline",
                min_value=1000,
                max_value=len(master)-1,
                value=st.session_state.idx,
                step=60,
                label_visibility="collapsed"
            )
            if idx != st.session_state.idx:
                st.session_state.idx = idx
        st.markdown('</div>', unsafe_allow_html=True)

# ── CURRENT DATA ─────────────────────────────────────────────
idx          = st.session_state.idx
window_size  = 600
window       = master.iloc[max(0, idx-window_size):idx]
current      = master.iloc[idx]
current_time = pd.to_datetime(current["datetime"])

soft_val = float(current.get(SOFT_COL) or 0)
hard_val = float(current.get(HARD_COL) or 0)
hr_val   = (hard_val / soft_val) if soft_val > 0 else 0.0

# Nowcast
flare = get_flare_at(current_time, catalog)
if flare is not None:
    alert_class, alert_level, emoji = classify_flare(
        float(flare["peak_sig"]),
        float(flare["hardness_ratio"])
    )
else:
    alert_class, alert_level, emoji = "QUIET", 0, "⚪"

# Forecast
if forecaster:
    row_dict = {}
    for col in forecaster.feature_cols:
        val = current.get(col, 0)
        row_dict[col] = float(val) if pd.notna(val) else 0.0
    forecaster.update(row_dict)
    forecast_result = forecaster.predict()
else:
    forecast_result = None

# ── TOP METRICS ──────────────────────────────────────────────
m1,m2,m3,m4,m5,m6 = st.columns(6)
with m1: st.metric("UTC Time",       current_time.strftime("%Y-%m-%d %H:%M"))
with m2: st.metric("SoLEXS",         f"{soft_val:.1f} cts/s")
with m3: st.metric("HEL1OS",         f"{hard_val:.3f} cts/s")
with m4: st.metric("Hardness Ratio", f"{hr_val:.2f}")
with m5: st.metric("Total Flares",   stats["total_flares"])
with m6: st.metric("Max Sig",        f"{stats['max_sig']:.0f}σ")

# ── MAIN LAYOUT: graphs (left) + panels (right) ──────────────
graph_col, panel_col = st.columns([2.5, 1])

with graph_col:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        subplot_titles=("SoLEXS — Soft X-ray Flux", "HEL1OS — Hard X-ray Flux"),
        vertical_spacing=0.10,
        row_heights=[0.5, 0.5]
    )

    times = window["datetime"]

    fig.add_trace(go.Scatter(
        x=times, y=window[SOFT_COL],
        mode="lines", name="SoLEXS",
        line=dict(color="#60A5FA", width=0.8),
        fill="tozeroy", fillcolor="rgba(96,165,250,0.06)"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=times, y=window[HARD_COL],
        mode="lines", name="HEL1OS",
        line=dict(color="#F97316", width=0.8),
        fill="tozeroy", fillcolor="rgba(249,115,22,0.06)"
    ), row=2, col=1)

    # Mark flares
    for _, f in catalog.iterrows():
        ft = pd.to_datetime(f["peak_time"])
        if times.min() <= ft <= times.max():
            sig    = float(f["peak_sig"])
            color  = "#ff0000" if sig >= 100 else "#ff6b00" if sig >= 50 else "#f0a500"
            label  = "X" if sig >= 100 else "M" if sig >= 50 else "C"
            for row in [1, 2]:
                fig.add_vline(
                    x=ft, line_dash="dot",
                    line_color=color, line_width=1.5,
                    row=row, col=1
                )
            fig.add_annotation(
                x=ft, y=1.05, yref="paper",
                text=f"⚡{label}",
                showarrow=False,
                font=dict(color=color, size=11)
            )

    # Current time line
    fig.add_vline(
        x=current_time,
        line_color="#ffffff",
        line_width=1.5,
        line_dash="solid"
    )

    fig.update_layout(
        height         = 380,
        paper_bgcolor  = "#0a0e1a",
        plot_bgcolor   = "#0f1628",
        font           = dict(color="#94a3b8", size=11),
        showlegend     = False,
        margin         = dict(l=50, r=10, t=30, b=10),
    )
    fig.update_yaxes(gridcolor="#1e2d4a", type="log", row=1)
    fig.update_yaxes(gridcolor="#1e2d4a", type="log", row=2)
    fig.update_xaxes(gridcolor="#1e2d4a", showticklabels=True, row=2)

    st.plotly_chart(fig, use_container_width=True)

with panel_col:
    # NOWCAST PANEL
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">⚡ LIVE ANALYSIS & ALERTS</div>', unsafe_allow_html=True)

    alert_css_map = {
        "QUIET"   : "alert-quiet",
        "LOW"     : "alert-low",
        "MODERATE": "alert-moderate",
        "HIGH"    : "alert-high",
        "EXTREME" : "alert-extreme",
    }
    css = alert_css_map.get(alert_class, "alert-quiet")
    alert_text = "🚨 FLARE ACTIVE" if alert_level >= 3 else f"{emoji} {alert_class}"
    st.markdown(
        f'<div class="alert-box {css}">{alert_text}</div>',
        unsafe_allow_html=True
    )

    st.markdown("**NOWCAST (Real-time)**")
    if flare is not None:
        st.markdown(f"""
        <div class="info-row"><span class="info-label">Alert Class</span>
        <span class="info-value" style="color:#F97316">{alert_class}</span></div>
        <div class="info-row"><span class="info-label">Significance</span>
        <span class="info-value">{float(flare['peak_sig']):.1f}σ</span></div>
        <div class="info-row"><span class="info-label">Duration</span>
        <span class="info-value">{float(flare['duration_sec']):.0f}s</span></div>
        <div class="info-row"><span class="info-label">Bands</span>
        <span class="info-value">{int(flare['n_bands'])}</span></div>
        <div class="info-row"><span class="info-label">Detection Time</span>
        <span class="info-value">{current_time.strftime('%H:%M UTC')}</span></div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-row"><span class="info-label">Status</span>
        <span class="info-value" style="color:#1db954">Quiet Sun</span></div>
        """, unsafe_allow_html=True)

    st.divider()

    # FORECAST PANEL
    st.markdown("**FORECAST (ML · 15 min ahead)**")
    if forecast_result and forecast_result.get("ready"):
        prob  = forecast_result["probability"]
        level = forecast_result["level"]
        conf  = forecast_result["confidence"]

        if np.isnan(prob):
            prob = 0.0

        fc_css = alert_css_map.get(level, "alert-quiet")
        st.markdown(
            f'<div class="alert-box {fc_css}" style="font-size:0.9rem">'
            f'P(flare) = {prob*100:.1f}%<br>'
            f'Class: {level}'
            f'</div>',
            unsafe_allow_html=True
        )

        prob_safe = max(0.0, min(1.0, float(prob)))
        st.progress(prob_safe)

        st.markdown(f"""
        <div class="info-row"><span class="info-label">Probability</span>
        <span class="info-value">{prob*100:.1f}%</span></div>
        <div class="info-row"><span class="info-label">Confidence</span>
        <span class="info-value">{conf}</span></div>
        <div class="info-row"><span class="info-label">Lead Time</span>
        <span class="info-value">~15 min</span></div>
        """, unsafe_allow_html=True)
    else:
        buf = len(forecaster.buffer) if forecaster else 0
        st.info(f"Buffering... {buf}/300")

    st.markdown('</div>', unsafe_allow_html=True)

# ── BOTTOM: METRICS + EVENT LOG ──────────────────────────────
st.divider()
bot_l, bot_r = st.columns([1, 2.5])

with bot_l:
    st.markdown(f"""
    <div class="perf-box">
      <span style="color:#64748b">HSS Score</span>
      <span style="color:#F97316;font-weight:600">0.317</span>
    </div>
    <div class="perf-box">
      <span style="color:#64748b">True Positive Rate</span>
      <span style="color:#60A5FA;font-weight:600">23.9%</span>
    </div>
    <div class="perf-box">
      <span style="color:#64748b">False Alarm Rate</span>
      <span style="color:#94a3b8;font-weight:600">49.4%</span>
    </div>
    <div class="perf-box">
      <span style="color:#64748b">Avg Lead Time</span>
      <span style="color:#4ADE80;font-weight:600">~15 min</span>
    </div>
    <div class="perf-box">
      <span style="color:#64748b">Flares Caught</span>
      <span style="color:#e2e8f0;font-weight:600">88 / 368</span>
    </div>
    """, unsafe_allow_html=True)

with bot_r:
    st.markdown("**📋 Automated Event Log (Flare Database)**")
    display_cols = ["start_time","peak_time","duration_sec",
                    "n_bands","peak_sig","hardness_ratio"]
    display_cols = [c for c in display_cols if c in catalog.columns]
    st.dataframe(
        catalog[display_cols].sort_values("peak_sig", ascending=False),
        use_container_width=True,
        height=180,
    )

# ── AUTO PLAY ────────────────────────────────────────────────
if st.session_state.playing:
    time.sleep(0.05)
    st.session_state.idx = min(
        st.session_state.idx + st.session_state.speed,
        len(master) - 1
    )
    st.rerun()