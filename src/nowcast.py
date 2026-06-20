import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT  = Path(__file__).parent.parent
MASTER_PATH   = PROJECT_ROOT / "outputs" / "master_data.csv"
CATALOG_PATH  = PROJECT_ROOT / "outputs" / "flare_catalog.csv"

# Alert only for strong flares
ALERT_SIG_THRESHOLD = 50.0


# Ye line add karo load_data() mein debugging ke liye
def load_data():
    master  = pd.read_csv(MASTER_PATH)
    master["datetime"] = pd.to_datetime(master["datetime"])
    catalog = pd.read_csv(CATALOG_PATH)
    catalog["start_time"] = pd.to_datetime(catalog["start_time"])
    catalog["peak_time"]  = pd.to_datetime(catalog["peak_time"])
    catalog["end_time"]   = pd.to_datetime(
        (catalog["end_mjd"] - 40587.0) * 86400, unit="s", origin="unix"
    )
    return master, catalog

def get_flare_at(timestamp, catalog, buffer_sec=300):
    """
    Check if timestamp is near any detected flare.
    Uses ±5 min buffer around peak time for dashboard visibility.
    """
    match = catalog[
        (pd.to_datetime(catalog["peak_time"]) - pd.Timedelta(seconds=buffer_sec) <= timestamp) &
        (pd.to_datetime(catalog["peak_time"]) + pd.Timedelta(seconds=buffer_sec) >= timestamp)
    ]
    if len(match) > 0:
        # Return closest flare to current timestamp
        match = match.copy()
        match["diff"] = abs(
            pd.to_datetime(match["peak_time"]) - timestamp
        ).dt.total_seconds()
        return match.loc[match["diff"].idxmin()]
    return None


def classify_flare(peak_sig, hardness_ratio):
    """
    Physics-based classification.
    Significance + hardness ratio combined.
    No GOES calibration needed.
    """
    if peak_sig >= 100 and hardness_ratio >= 3.0:
        return "EXTREME", 4, "🔴"
    elif peak_sig >= 50 and hardness_ratio >= 2.0:
        return "HIGH", 3, "🟠"
    elif peak_sig >= 20 and hardness_ratio >= 1.0:
        return "MODERATE", 2, "🟡"
    elif peak_sig >= 5:
        return "LOW", 1, "🟢"
    else:
        return "QUIET", 0, "⚪"


def replay_stream(master, catalog, speed=1):
    """
    Generator — yields one data packet per row.
    Dashboard calls next() to get latest data point.

    Each packet contains:
      - Current flux values
      - Alert status
      - Flare info if active
    """
    soft_col = "SOLEXS_COUNTS"
    hard_col = "CDTE_1p8_90keV_CTR"

    for _, row in master.iterrows():
        timestamp = row["datetime"]

        soft = row.get(soft_col, np.nan)
        hard = row.get(hard_col, np.nan)

        # Hardness ratio
        hr = (hard / soft) if (
            not np.isnan(soft) and
            not np.isnan(hard) and
            soft > 0
        ) else 0.0

        # Check flare catalog
        flare = get_flare_at(timestamp, catalog)

        if flare is not None:
            alert_class, alert_level, emoji = classify_flare(
                flare["peak_sig"],
                flare["hardness_ratio"]
            )
            is_alert = alert_level >= 3
        else:
            alert_class  = "QUIET"
            alert_level  = 0
            emoji        = "⚪"
            is_alert     = False

        packet = {
            "datetime"      : timestamp,
            "soft_counts"   : soft,
            "hard_counts"   : hard,
            "hardness_ratio": round(hr, 3),
            "alert_class"   : alert_class,
            "alert_level"   : alert_level,
            "emoji"         : emoji,
            "is_alert"      : is_alert,
            "flare_peak_sig": flare["peak_sig"]      if flare is not None else None,
            "flare_duration": flare["duration_sec"]  if flare is not None else None,
            "flare_n_bands" : flare["n_bands"]       if flare is not None else None,
        }

        yield packet


def get_summary_stats(catalog):
    """
    Summary stats for dashboard sidebar.
    """
    return {
        "total_flares"   : len(catalog),
        "extreme_flares" : len(catalog[catalog["peak_sig"] >= 100]),
        "high_flares"    : len(catalog[
            (catalog["peak_sig"] >= 50) &
            (catalog["peak_sig"] < 100)
        ]),
        "moderate_flares": len(catalog[
            (catalog["peak_sig"] >= 20) &
            (catalog["peak_sig"] < 50)
        ]),
        "low_flares"     : len(catalog[catalog["peak_sig"] < 20]),
        "max_sig"        : round(catalog["peak_sig"].max(), 1),
        "avg_duration"   : round(catalog["duration_sec"].mean(), 1),
    }


if __name__ == "__main__":
    master, catalog = load_data()
    stats = get_summary_stats(catalog)

    print("Nowcast Engine Ready")
    print(f"  Master data rows : {len(master):,}")
    print(f"  Detected flares  : {stats['total_flares']}")
    print(f"  Extreme          : {stats['extreme_flares']}")
    print(f"  High             : {stats['high_flares']}")
    print(f"  Moderate         : {stats['moderate_flares']}")
    print(f"  Low              : {stats['low_flares']}")
    print(f"  Max significance : {stats['max_sig']}")
    print(f"  Avg duration     : {stats['avg_duration']} sec")

    # Test first 5 packets
    print("\nFirst 5 data packets:")
    stream = replay_stream(master, catalog)
    for i, packet in enumerate(stream):
        if i >= 5:
            break
        print(f"  {packet['datetime']} | "
              f"{packet['emoji']} {packet['alert_class']} | "
              f"Soft: {packet['soft_counts']:.1f} | "
              f"Hard: {packet['hard_counts']:.3f}")