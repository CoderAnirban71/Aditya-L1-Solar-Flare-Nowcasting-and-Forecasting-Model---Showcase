import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PATH   = PROJECT_ROOT / "outputs" / "master_data.csv"
OUTPUT_PATH  = PROJECT_ROOT / "outputs" / "triggered_data.csv"

HARD_BANDS = [
    "CDTE_5_20keV_CTR",
    "CDTE_20_30keV_CTR",
    "CDTE_30_40keV_CTR",
    "CDTE_40_60keV_CTR",
    "CDTE_1p8_90keV_CTR",
    "CZT_20_40keV_CTR",
    "CZT_40_60keV_CTR",
    "CZT_60_80keV_CTR",
    "CZT_80_150keV_CTR",
    "CZT_18_160keV_CTR",
]
SOFT_BAND = "SOLEXS_COUNTS"

# Background window — 5 minutes of data
# master_data is ~1 sec cadence so 300 rows = 5 min
BACKGROUND_WINDOW = 300
SIGMA_THRESHOLD   = 5.0


def compute_background(series):
    """
    Rolling 5-minute median background.
    Median is used instead of mean to avoid
    flare contamination in background estimate.
    """
    return series.rolling(
        window=BACKGROUND_WINDOW,
        min_periods=10,
        center=False
    ).median()


def poisson_significance(observed, background):
    """
    Statistical significance of excess counts.
    Formula: (O - B) / sqrt(B)
    Returns NaN where background is zero or negative.
    """
    B = np.where(background > 0, background, np.nan)
    return (observed - B) / np.sqrt(B)


def compute_hardness_ratio(df):
    """
    Hardness Ratio = Hard X-ray / Soft X-ray
    Rises sharply during non-thermal flare phase.
    Helps distinguish real flares from noise.
    """
    hard = df["CDTE_1p8_90keV_CTR"] if "CDTE_1p8_90keV_CTR" in df.columns else None
    soft = df[SOFT_BAND] if SOFT_BAND in df.columns else None

    if hard is not None and soft is not None:
        denom = soft.replace(0, np.nan)
        return hard / denom
    return pd.Series(np.nan, index=df.index)


def run_triggering(df):
    """
    For each band:
      1. Compute rolling background (5-min median)
      2. Compute Poisson significance
      3. Flag rows exceeding SIGMA_THRESHOLD

    A row is triggered if ANY band exceeds threshold.
    Also computes hardness ratio as extra physics feature.
    """
    print(f"Running statistical triggering (threshold = {SIGMA_THRESHOLD} sigma)...")

    trigger_cols = []

    # Hard X-ray bands
    for band in HARD_BANDS:
        if band not in df.columns:
            continue

        sig_col  = band.replace("_CTR", "_SIG")
        trig_col = band.replace("_CTR", "_TRIG")

        background    = compute_background(df[band])
        df[sig_col]   = poisson_significance(df[band].values, background.values)
        df[trig_col]  = df[sig_col] > SIGMA_THRESHOLD
        trigger_cols.append(trig_col)

    # Soft X-ray band (SoLEXS)
    if SOFT_BAND in df.columns:
        background          = compute_background(df[SOFT_BAND])
        df["SOLEXS_SIG"]    = poisson_significance(df[SOFT_BAND].values, background.values)
        df["SOLEXS_TRIG"]   = df["SOLEXS_SIG"] > SIGMA_THRESHOLD
        trigger_cols.append("SOLEXS_TRIG")

    # Hardness ratio
    df["HARDNESS_RATIO"] = compute_hardness_ratio(df)

    # Any-band trigger
    if trigger_cols:
        df["ANY_TRIG"] = df[trigger_cols].any(axis=1)
    else:
        df["ANY_TRIG"] = False

    triggered = df["ANY_TRIG"].sum()
    total     = len(df)
    print(f"  Total rows      : {total:,}")
    print(f"  Triggered rows  : {triggered:,} ({100*triggered/total:.2f}%)")
    print(f"  Non-triggered   : {total - triggered:,}")

    return df


if __name__ == "__main__":
    print(f"Reading: {INPUT_PATH}")
    df = pd.read_csv(INPUT_PATH)
    print(f"  Loaded {len(df):,} rows")

    df = run_triggering(df)

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved: {OUTPUT_PATH}")