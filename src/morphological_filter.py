import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PATH   = PROJECT_ROOT / "outputs" / "triggered_data.csv"
OUTPUT_PATH  = PROJECT_ROOT / "outputs" / "flare_catalog.csv"

# Minimum duration for a real flare
MIN_DURATION_SEC  = 10

# Minimum bands that must trigger together
MIN_BANDS_TRIGGERED = 2

# Rise must be faster than decay (flare shape check)
# rise_time * this factor < decay_time
RISE_DECAY_RATIO = 0.5

HARD_TRIG_COLS = [
    "CDTE_5_20keV_TRIG",
    "CDTE_20_30keV_TRIG",
    "CDTE_30_40keV_TRIG",
    "CDTE_40_60keV_TRIG",
    "CDTE_1p8_90keV_TRIG",
    "CZT_20_40keV_TRIG",
    "CZT_40_60keV_TRIG",
    "CZT_60_80keV_TRIG",
    "CZT_80_150keV_TRIG",
    "CZT_18_160keV_TRIG",
]

SIG_COLS = [
    "CDTE_5_20keV_SIG",
    "CDTE_20_30keV_SIG",
    "CDTE_30_40keV_SIG",
    "CDTE_40_60keV_SIG",
    "CDTE_1p8_90keV_SIG",
    "CZT_20_40keV_SIG",
    "CZT_40_60keV_SIG",
    "CZT_60_80keV_SIG",
    "CZT_80_150keV_SIG",
    "CZT_18_160keV_SIG",
    "SOLEXS_SIG",
]


def group_events(df):
    """
    Group consecutive ANY_TRIG=True rows into discrete events.
    Returns list of DataFrames, one per event.
    """
    trig  = df["ANY_TRIG"].astype(int)
    group = (trig != trig.shift()).cumsum()
    group = group[trig == 1]

    events = []
    for _, idx in group.groupby(group):
        events.append(df.loc[idx.index])
    return events


def check_duration(event_df):
    """
    Event must last at least MIN_DURATION_SEC seconds.
    """
    duration = (event_df["MJD"].max() - event_df["MJD"].min()) * 86400
    return duration >= MIN_DURATION_SEC, duration


def check_multi_band(event_df):
    """
    At least MIN_BANDS_TRIGGERED bands must trigger together.
    Single-band spikes are likely noise or particle hits.
    """
    available = [c for c in HARD_TRIG_COLS if c in event_df.columns]
    if not available:
        return False, 0
    bands_triggered = event_df[available].any(axis=0).sum()
    return bands_triggered >= MIN_BANDS_TRIGGERED, int(bands_triggered)


def check_rise_decay(event_df):
    """
    Solar flares have fast rise, slow decay.
    rise_time < decay_time is expected.
    Uses CDTE_1p8_90keV_SIG as primary band.
    """
    sig_col = "CDTE_1p8_90keV_SIG" if "CDTE_1p8_90keV_SIG" in event_df.columns else None
    if sig_col is None:
        return True, np.nan, np.nan

    sig    = event_df[sig_col].fillna(0).values
    times  = event_df["MJD"].values * 86400

    peak_idx  = np.argmax(sig)
    peak_time = times[peak_idx]

    rise_time  = peak_time - times[0]
    decay_time = times[-1] - peak_time

    if decay_time <= 0:
        return False, rise_time, decay_time

    ratio = rise_time / decay_time
    return ratio <= RISE_DECAY_RATIO, rise_time, decay_time


def extract_peak_info(event_df):
    """
    Find peak significance, peak time, and which band peaked.
    """
    available_sig = [c for c in SIG_COLS if c in event_df.columns]

    if not available_sig:
        peak_idx  = event_df.index[0]
        peak_sig  = np.nan
        peak_band = "unknown"
    else:
        max_sigs  = event_df[available_sig].max(axis=1)
        peak_idx  = max_sigs.idxmax()
        peak_sig  = max_sigs[peak_idx]
        peak_band = event_df[available_sig].loc[peak_idx].idxmax()

    return (
        event_df.loc[peak_idx, "MJD"],
        peak_sig,
        peak_band,
        event_df.loc[peak_idx, "HARDNESS_RATIO"] if "HARDNESS_RATIO" in event_df.columns else np.nan,
        event_df.loc[peak_idx, "SOLEXS_COUNTS"]  if "SOLEXS_COUNTS"  in event_df.columns else np.nan,
        event_df.loc[peak_idx, "CDTE_1p8_90keV_CTR"] if "CDTE_1p8_90keV_CTR" in event_df.columns else np.nan,
    )


def run_morphological_filter(df):
    """
    Filter triggered events using 3 shape checks:
      1. Duration >= 10 seconds
      2. Multi-band confirmation (>= 2 bands)
      3. Fast rise / slow decay shape
    """
    print("Running morphological filter...")

    events      = group_events(df)
    print(f"  Candidate events  : {len(events)}")

    records     = []
    rejected    = {"duration": 0, "multi_band": 0, "rise_decay": 0}

    for event_df in events:

        # Check 1: Duration
        ok_dur, duration = check_duration(event_df)
        if not ok_dur:
            rejected["duration"] += 1
            continue

        # Check 2: Multi-band
        ok_mb, n_bands = check_multi_band(event_df)
        if not ok_mb:
            rejected["multi_band"] += 1
            continue

        # Check 3: Rise/decay shape
        ok_rd, rise, decay = check_rise_decay(event_df)
        if not ok_rd:
            rejected["rise_decay"] += 1
            continue

        # Passed all checks — extract info
        peak_mjd, peak_sig, peak_band, hardness, solexs_peak, hel_peak = extract_peak_info(event_df)

        records.append({
            "start_mjd"    : event_df["MJD"].iloc[0],
            "peak_mjd"     : peak_mjd,
            "end_mjd"      : event_df["MJD"].iloc[-1],
            "start_time"   : event_df["datetime"].iloc[0]  if "datetime" in event_df.columns else np.nan,
            "peak_time"    : event_df.loc[event_df["MJD"].idxmax() if peak_mjd is None else event_df["MJD"].sub(peak_mjd).abs().idxmin(), "datetime"] if "datetime" in event_df.columns else np.nan,
            "duration_sec" : duration,
            "n_bands"      : n_bands,
            "rise_sec"     : rise,
            "decay_sec"    : decay,
            "peak_sig"     : peak_sig,
            "peak_band"    : peak_band,
            "hardness_ratio" : hardness,
            "solexs_peak"  : solexs_peak,
            "hel_peak"     : hel_peak,
        })

    catalog = pd.DataFrame(records).reset_index(drop=True)

    print(f"  Rejected (duration)   : {rejected['duration']}")
    print(f"  Rejected (multi-band) : {rejected['multi_band']}")
    print(f"  Rejected (rise/decay) : {rejected['rise_decay']}")
    print(f"  Accepted flares       : {len(catalog)}")

    return catalog


if __name__ == "__main__":
    print(f"Reading: {INPUT_PATH}")
    df = pd.read_csv(INPUT_PATH)
    print(f"  Loaded {len(df):,} rows")

    catalog = run_morphological_filter(df)

    catalog.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved: {OUTPUT_PATH} ({len(catalog)} flares)")
    print(catalog.to_string(index=False) if len(catalog) <= 20 else catalog.head(20).to_string(index=False))