import numpy as np
import pandas as pd
import requests
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PATH   = PROJECT_ROOT / "outputs" / "flare_catalog.csv"
OUTPUT_PATH  = PROJECT_ROOT / "outputs" / "flare_catalog_labeled.csv"
GOES_CACHE   = PROJECT_ROOT / "outputs" / "goes_flare_list.csv"

MATCH_WINDOW_SEC = 300


def download_goes_flare_list():
    if GOES_CACHE.exists():
        print(f"GOES list already cached: {GOES_CACHE}")
        return pd.read_csv(GOES_CACHE)

    print("Downloading flare list from NASA DONKI...")
    url = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/FLR?startDate=2024-07-01&endDate=2024-07-31"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        records = []
        for event in data:
            try:
                peak_time = pd.to_datetime(event["peakTime"])
                magnitude = event.get("classType", "")
                if not magnitude:
                    continue
                records.append({
                    "goes_peak"     : peak_time,
                    "goes_class"    : magnitude[0],
                    "goes_magnitude": magnitude,
                })
            except Exception:
                continue

        goes_df = pd.DataFrame(records)
        goes_df.to_csv(GOES_CACHE, index=False)
        print(f"  GOES flares in July 2024: {len(goes_df)}")
        return goes_df

    except Exception as e:
        print(f"  Download failed: {e}")
        return pd.DataFrame()


def match_flares(our_catalog, goes_df):
    print(f"Matching flares (window = {MATCH_WINDOW_SEC}s)...")

    our_catalog["peak_dt"]        = pd.to_datetime(our_catalog["peak_time"])
    our_catalog["flare_class"]    = "UNCONFIRMED"
    our_catalog["goes_magnitude"] = ""
    our_catalog["goes_peak"]      = pd.NaT
    our_catalog["confirmed"]      = False

    if goes_df.empty:
        print("  No GOES data to match against")
        return our_catalog

    goes_df["goes_peak"]       = pd.to_datetime(goes_df["goes_peak"]).dt.tz_localize(None)
    our_catalog["peak_dt"]     = pd.to_datetime(our_catalog["peak_dt"]).dt.tz_localize(None)

    for idx, row in our_catalog.iterrows():
        our_peak = row["peak_dt"]
        for _, grow in goes_df.iterrows():
            diff = abs((our_peak - grow["goes_peak"]).total_seconds())
            if diff <= MATCH_WINDOW_SEC:
                our_catalog.at[idx, "flare_class"]    = grow["goes_class"]
                our_catalog.at[idx, "goes_magnitude"] = str(grow["goes_magnitude"])
                our_catalog.at[idx, "goes_peak"]      = grow["goes_peak"]
                our_catalog.at[idx, "confirmed"]      = True
                break

    confirmed   = our_catalog["confirmed"].sum()
    unconfirmed = len(our_catalog) - confirmed
    print(f"  Confirmed by GOES : {confirmed}")
    print(f"  Unconfirmed       : {unconfirmed}")
    return our_catalog


if __name__ == "__main__":
    print(f"Reading: {INPUT_PATH}")
    catalog = pd.read_csv(INPUT_PATH)
    print(f"  Loaded {len(catalog)} flares")

    goes_df = download_goes_flare_list()
    labeled = match_flares(catalog, goes_df)

    labeled.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved: {OUTPUT_PATH} ({len(labeled)} flares)")

    print("\nClass distribution:")
    print(labeled["flare_class"].value_counts().to_string())