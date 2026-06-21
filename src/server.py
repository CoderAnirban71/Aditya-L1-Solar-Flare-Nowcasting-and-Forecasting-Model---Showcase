# src/server.py
import sys
import json
import threading
import time as time_mod
from pathlib import Path

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nowcast import load_data, get_flare_at, classify_flare, get_summary_stats
from forecast import FlareForecaster

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/dashboard", StaticFiles(directory=str(PROJECT_ROOT / "dashboard")), name="dashboard")

# ── JSON HELPER ──────────────────────────────────────────────
def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (float, np.floating, np.float64, np.float32)):
        # Catches BOTH plain Python floats and numpy floats,
        # and BOTH NaN and +/-Infinity (not just NaN)
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, pd.Timestamp):
        return str(obj)
    elif hasattr(obj, 'item'):
        return obj.item()
    return obj

# ── GLOBAL STATE ─────────────────────────────────────────────
master, catalog = load_data()
stats           = get_summary_stats(catalog)
forecaster      = FlareForecaster()

SOFT_COL = "SOLEXS_COUNTS"
HARD_COL = "CDTE_1p8_90keV_CTR"

state = {
    "idx"                : 1000,
    "playing"            : False,
    "speed"              : 60,
    "current_data"       : {},
    "nowcast"            : {},
    "forecast"           : {},
    "graph_buffer"       : [],
    "last_nowcast_alert" : None,
    "last_forecast_alert": None,
}

GRAPH_BUFFER_SIZE = 600


def update_state():
    idx      = state["idx"]
    row      = master.iloc[idx]
    cur_time = pd.to_datetime(row["datetime"])

    soft = float(row.get(SOFT_COL) or 0)
    hard = float(row.get(HARD_COL) or 0)
    hr   = round(hard / soft, 3) if soft > 0 else 0.0

    # Graph buffer
    state["graph_buffer"].append({
        "t"   : str(cur_time),
        "soft": round(soft, 2),
        "hard": round(hard, 4),
    })
    if len(state["graph_buffer"]) > GRAPH_BUFFER_SIZE:
        state["graph_buffer"] = state["graph_buffer"][-GRAPH_BUFFER_SIZE:]

    # Nowcast
    flare = get_flare_at(cur_time, catalog)
    if flare is not None:
        alert_class, alert_level, emoji = classify_flare(
            float(flare["peak_sig"]),
            float(flare["hardness_ratio"])
        )
        nowcast = {
            "alert"     : True,
            "class"     : alert_class,
            "level"     : int(alert_level),
            "emoji"     : emoji,
            "sig"       : round(float(flare["peak_sig"]), 1),
            "duration"  : round(float(flare["duration_sec"]), 0),
            "n_bands"   : int(flare["n_bands"]),
            "peak_time" : str(pd.to_datetime(flare["peak_time"])),
            "hr"        : round(float(flare["hardness_ratio"]), 2),
            "persistent": False,
        }
        state["last_nowcast_alert"] = {
            **nowcast,
            "detected_at": str(cur_time),
            "expires_at" : str(cur_time + pd.Timedelta(minutes=5))
        }
    else:
        if state["last_nowcast_alert"]:
            exp = pd.to_datetime(state["last_nowcast_alert"]["expires_at"])
            if cur_time < exp:
                nowcast = {**state["last_nowcast_alert"], "persistent": True}
            else:
                nowcast = {"alert": False, "class": "QUIET", "level": 0}
        else:
            nowcast = {"alert": False, "class": "QUIET", "level": 0}

    state["nowcast"] = nowcast

    # Forecast
    row_dict = {}
    for col in forecaster.feature_cols:
        val = row.get(col, 0)
        row_dict[col] = float(val) if pd.notna(val) else 0.0
    forecaster.update(row_dict)
    fc = forecaster.predict()

    if fc.get("ready") and not np.isnan(fc.get("probability", float("nan"))):
        prob         = float(fc["probability"])
        predict_time = cur_time + pd.Timedelta(minutes=forecaster.lead_time)

        upcoming = []
        for _, f in catalog.iterrows():
            ft = pd.to_datetime(f["peak_time"])
            if cur_time < ft < cur_time + pd.Timedelta(minutes=30):
                _, flevel, _ = classify_flare(
                    float(f["peak_sig"]),
                    float(f["hardness_ratio"])
                )
                upcoming.append({
                    "time"   : ft.strftime("%H:%M:%S"),
                    "level"  : ["QUIET","LOW","MODERATE","HIGH","EXTREME"][flevel],
                    "sig"    : round(float(f["peak_sig"]), 1),
                    "n_bands": int(f["n_bands"]),
                })

        forecast = {
            "ready"       : True,
            "probability" : round(prob * 100, 1),
            "level"       : fc["level"],
            "confidence"  : fc["confidence"],
            "lead_time"   : int(forecaster.lead_time),
            "predict_time": predict_time.strftime("%H:%M:%S"),
            "alert"       : bool(prob >= forecaster.threshold),
            "upcoming"    : upcoming,
        }

        if prob >= forecaster.threshold:
            state["last_forecast_alert"] = {
                **forecast,
                "detected_at": str(cur_time)
            }
    else:
        forecast = {
            "ready"       : False,
            "probability" : 0.0,
            "level"       : "BUFFERING",
            "confidence"  : "LOW",
            "lead_time"   : 15,
            "predict_time": "--:--:--",
            "upcoming"    : [],
            "alert"       : False,
        }

    state["forecast"] = forecast

    state["current_data"] = {
        "time"    : cur_time.strftime("%Y-%m-%d %H:%M:%S"),
        "soft"    : round(soft, 1),
        "hard"    : round(hard, 3),
        "hr"      : round(hr, 3),
        "idx"     : int(idx),
        "total"   : int(len(master)),
        "progress": round(idx / len(master) * 100, 1),
    }


# ── BACKGROUND LOOP ──────────────────────────────────────────
def replay_loop():
    last_tick = time_mod.time()
    step_accum = 0.0
    while True:
        current_tick = time_mod.time()
        elapsed = current_tick - last_tick
        last_tick = current_tick

        if state["playing"]:
            step_accum += elapsed * state["speed"]
            steps = int(step_accum)
            if steps > 0:
                step_accum -= steps
                state["idx"] = min(state["idx"] + steps, len(master) - 1)
            update_state()
            if state["idx"] >= len(master) - 1:
                state["playing"] = False
        else:
            update_state()

        time_mod.sleep(0.1)

thread = threading.Thread(target=replay_loop, daemon=True)
thread.start()


# ── ROUTES ───────────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse(str(PROJECT_ROOT / "dashboard" / "index.html"))

@app.get("/api/data")
def get_data():
    return JSONResponse(clean(state["current_data"]))

@app.get("/api/nowcast")
def get_nowcast():
    return JSONResponse(clean(state["nowcast"]))

@app.get("/api/forecast")
def get_forecast():
    return JSONResponse(clean(state["forecast"]))

@app.get("/api/graph")
def get_graph():
    return JSONResponse(clean({"buffer": state["graph_buffer"]}))

@app.get("/api/catalog")
def get_catalog():
    cols    = ["start_time","peak_time","duration_sec",
               "n_bands","peak_sig","hardness_ratio"]
    cols    = [c for c in cols if c in catalog.columns]
    records = catalog[cols].sort_values(
        "peak_sig", ascending=False
    ).head(20).to_dict("records")
    return JSONResponse(clean({"flares": records}))

@app.get("/api/stats")
def get_stats():
    return JSONResponse(clean(stats))

@app.get("/api/state")
def get_state():
    return JSONResponse(clean({
        "playing": state["playing"],
        "speed"  : state["speed"],
        "idx"    : state["idx"],
        "total"  : len(master),
    }))

@app.post("/api/play")
def play():
    state["playing"] = True
    return JSONResponse({"status": "playing"})

@app.post("/api/pause")
def pause():
    state["playing"] = False
    return JSONResponse({"status": "paused"})

@app.post("/api/reset")
def reset():
    state["idx"]                 = 1000
    state["playing"]             = False
    state["graph_buffer"]        = []
    state["last_nowcast_alert"]  = None
    state["last_forecast_alert"] = None
    forecaster.buffer            = []
    return JSONResponse({"status": "reset"})

@app.post("/api/speed/{value}")
def set_speed(value: int):
    state["speed"] = value
    return JSONResponse({"speed": value})

@app.post("/api/seek/{idx}")
def seek(idx: int):
    state["idx"]          = max(1000, min(idx, len(master)-1))
    state["graph_buffer"] = []
    forecaster.buffer     = []
    return JSONResponse({"idx": state["idx"]})


# ── RUN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")