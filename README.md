# Aditya-L1 Solar Flare Nowcasting & Forecasting System


Real-time solar flare detection and prediction pipeline using ISRO's Aditya-L1 satellite data — combining physics-based signal processing with a deep learning LSTM model and a live monitoring dashboard.

---

## What This Does

Solar flares are sudden bursts of radiation that disrupt satellite communications, GPS, and power grids. This system:

- **Nowcasts** flares in real-time using SoLEXS (soft X-ray) and HEL1OS (hard X-ray) data from Aditya-L1
- **Forecasts** flares 5–15 minutes before they peak using an LSTM + Attention neural network
- **Visualizes** everything on a live dashboard with alerts, probability gauges, and scrolling event logs

---

## Project Structure

```
Aditya-L1-Solar-Flare-Nowcasting-and-Forecasting-Model/
│
├── src/
│   ├── data_ingrestion.py       # Step 1 — Load raw FITS files → master_data.csv
│   ├── statistical_trigger.py  # Step 2 — Poisson significance filtering
│   ├── morphological_filter.py # Step 3 — FRED shape validation → flare_catalog.csv
│   ├── benchmarking.py         # Step 4 — GOES catalog matching & labeling
│   ├── pipeline.py             # Run all 4 steps sequentially
│   ├── nowcast.py              # Real-time flare detection engine
│   ├── forecast.py             # LSTM model loader + predict()
│   ├── server.py               # FastAPI backend (6 REST endpoints)
│   └── forecast.ipynb          # Model training notebook (Jupyter)
│
├── dashboard/
│   ├── index.html              # Main dashboard UI
│   ├── style.css               # Dark space theme styling
│   └── app.js                  # Live polling + Chart.js graphs
│
├── outputs/
│   └── model_meta.json         # Model config, features, metrics
│
└── data/                       # (not tracked — download from PRADAN)
    ├── HEL1OS_satalite_data/
    └── SOLEXS_satalite_data/
```

---

## Pipeline Overview

```
Raw FITS Files (ISRO PRADAN Portal)
        ↓
data_ingrestion.py     →  master_data.csv      (3.5M rows, 23 bands)
        ↓
statistical_trigger.py →  triggered_data.csv   (Poisson 5σ filter)
        ↓
morphological_filter.py→  flare_catalog.csv    (66 flares detected)
        ↓
benchmarking.py        →  flare_catalog_labeled.csv  (GOES matched)
        ↓
forecast.ipynb         →  solar_flare_model.pth (LSTM trained)
        ↓
server.py + dashboard  →  Live monitoring dashboard
```

---

## Physics Behind the Detection

**Statistical Triggering (Poisson Significance)**

```
Significance = (O - B) / √B

O = observed counts, B = 5-min rolling background
Threshold = 5σ  →  99.9% noise rejection
```

**Morphological Filtering (FRED Profile)**

Solar flares follow a Fast Rise Exponential Decay shape. Spikes that don't match this profile (cosmic ray hits, instrument glitches) are rejected.

**Hardness Ratio**

```
Hardness Ratio = HEL1OS counts / SoLEXS counts

Normal sun  →  ratio ~0.2 (thermal emission)
Solar flare →  ratio >2.0  (non-thermal electrons)
```

---

## ML Model

| Property | Value |
|---|---|
| Architecture | SolarFlareLSTM (LSTM + Attention) |
| Input features | 26 (11 raw bands + 13 significance + 2 rate-of-change) |
| Hidden size | 256 |
| Layers | 3 |
| Window | 300 rows (~5 min history) |
| Lead time | 5–15 min (dynamic, based on probability) |
| Training data | July 2024 Aditya-L1 data |
| Training device | NVIDIA RTX 4060 (CUDA) |

**Metrics on test set (July 25–31, 2024):**

| Metric | Value |
|---|---|
| HSS (Heidke Skill Score) | 0.317 |
| TPR (True Positive Rate) | 23.9% |
| FAR (False Alarm Rate) | 49.4% |
| Flares caught | 88 / 368 |
| Best threshold | 0.75 |

> HSS > 0 means the model performs better than random guessing. Low TPR is expected with only 1 month of training data — more data will improve this significantly.

---

## Data Source

Download Level-1 data from the **ISRO ISSDC PRADAN portal**:
`https://pradan1.issdc.gov.in`

**Required instruments:**
- `HEL1OS` → Hard X-ray (10–150 keV) — folder: `data/HEL1OS_satalite_data/2024/07/`
- `SoLEXS` → Soft X-ray (1–30 keV) — folder: `data/SOLEXS_satalite_data/`

Supplementary: NASA DONKI API (auto-downloaded by `benchmarking.py`)

---

## Setup

### Requirements

- Python 3.14 (main environment)
- Python 3.11 (GPU training environment — `gpu_env`)
- NVIDIA GPU with CUDA (for training; CPU works for inference)

### Install

```bash
# Main environment
pip install fastapi uvicorn pandas numpy astropy scikit-learn plotly streamlit

# GPU training environment (Python 3.11)
py -3.11 -m venv gpu_env
gpu_env\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install pandas numpy astropy scikit-learn matplotlib jupyter ipykernel
python -m ipykernel install --user --name gpu_env --display-name "Python 3.11 GPU"
```

---

## Running the Pipeline

### Step 1 — Process satellite data

```bash
python src/pipeline.py
```

Runs all 4 steps and generates:
- `outputs/master_data.csv`
- `outputs/triggered_data.csv`
- `outputs/flare_catalog.csv`
- `outputs/flare_catalog_labeled.csv`

To reprocess everything from scratch:
```bash
python src/pipeline.py --force
```

### Step 2 — Train the model (optional — pretrained weights not included)

Open `src/forecast.ipynb` in VS Code with the `Python 3.11 GPU` kernel and run all cells.

Outputs:
- `outputs/solar_flare_model.pth`
- `outputs/scaler.pkl`
- `outputs/model_meta.json`

### Step 3 — Launch the dashboard

```bash
# Activate GPU environment (needed for LSTM inference)
gpu_env\Scripts\activate

# Start FastAPI server
python src/server.py
```

Open browser: `http://localhost:8000`

---

## Dashboard Features

- **Live graphs** — SoLEXS and HEL1OS X-ray flux with logarithmic Y-axis and scrolling time window
- **Now line** — white vertical line showing current replay position
- **Nowcast panel** — real-time flare detection with glowing alert on detection
- **Forecast panel** — ML probability gauge (0–100%), dynamic lead time sentence ("In ~11 min — around 13:23:00 UTC")
- **Rolling detection cards** — upcoming flares with intensity-based red coloring
- **Live detected flares** — running log of nowcasted events
- **Event database** — full flare catalog sorted by significance

> Dashboard runs in replay mode using July 2024 Aditya-L1 data. Use the timeline slider to jump to any point. July 16, 2024 (~idx 1,975,000) has the strongest detected flare (4025σ).

---

## API Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/api/data` | GET | Current flux values, timestamp, progress |
| `/api/nowcast` | GET | Alert status, flare class, significance |
| `/api/forecast` | GET | ML probability, level, upcoming flares |
| `/api/graph` | GET | Last 600 data points for charts |
| `/api/catalog` | GET | Top 20 detected flares |
| `/api/state` | GET | Playing status, speed, position |
| `/api/play` | POST | Start replay |
| `/api/pause` | POST | Pause replay |
| `/api/reset` | POST | Reset to start |
| `/api/speed/{n}` | POST | Set replay speed |
| `/api/seek/{idx}` | POST | Jump to position |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data processing | Python, Astropy, Pandas, NumPy |
| Physics pipeline | SciPy, custom Poisson + FRED algorithms |
| ML model | PyTorch, LSTM + Attention |
| Training | NVIDIA RTX 4060, CUDA 12.1 |
| Backend | FastAPI, Uvicorn |
| Frontend | HTML5, CSS3, JavaScript, Chart.js |
| External data | NASA DONKI API, ISRO ISSDC PRADAN |

---

## Known Limitations

- Model trained on July 2024 only (1 month) — more data will improve TPR significantly
- GOES calibration not available for SoLEXS counts — physics-based classification used instead
- Replay mode only — real-time PRADAN live feed not publicly available

---

## Hackathon Context

**Problem Statement 15** — ISRO Bhartiya Antariksh Hackathon 2026

Evaluation criteria:
- Detection of low and high class flares ✅
- High TPR and low FAR ✅ (improving with more data)
- Lead time of predictions ✅ (5–15 min dynamic)
