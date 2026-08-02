import os
import re
import gzip
import warnings
import numpy as np
import pandas as pd
from astropy.io import fits
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent
HEL1OS_BASE  = PROJECT_ROOT / "data" / "HEL1OS_satalite_data" / "2024" / "07"
SOLEXS_BASE  = PROJECT_ROOT / "data" / "SOLEXS_satalite_data"
OUTPUT_PATH  = PROJECT_ROOT / "outputs" / "master_data.csv"

CDTE_BANDS = {
    1: "CDTE_5_20keV",
    2: "CDTE_20_30keV",
    3: "CDTE_30_40keV",
    4: "CDTE_40_60keV",
    5: "CDTE_1p8_90keV",
}

CZT_BANDS = {
    1: "CZT_20_40keV",
    2: "CZT_40_60keV",
    3: "CZT_60_80keV",
    4: "CZT_80_150keV",
    5: "CZT_18_160keV",
}

SOLEXS_MJDREFI = 51544.0


def get_latest_version_folders(base_path):
    pattern = re.compile(r'(HLS_\d{8}_\d{6}_\d+sec_lev1)_(V\d{3})$')
    obs_map = {}

    for day in sorted(os.listdir(base_path)):
        day_path = os.path.join(base_path, day)
        if not os.path.isdir(day_path):
            continue
        for obs in os.listdir(day_path):
            obs_path = os.path.join(day_path, obs)
            if not os.path.isdir(obs_path):
                continue
            m = pattern.match(obs)
            if m:
                key = f"{day}/{m.group(1)}"
                obs_map.setdefault(key, {})[m.group(2)] = obs_path
            else:
                obs_map[f"{day}/{obs}"] = {"V000": obs_path}

    latest = []
    skipped = 0
    for key, versions in obs_map.items():
        best = sorted(versions.keys())[-1]
        latest.append(versions[best])
        skipped += len(versions) - 1

    print(f"  Observations: {len(latest)} kept, {skipped} duplicate versions skipped")
    return sorted(latest)


def _read_fits_bands(filepath, band_map):
    result = {}
    if not os.path.exists(filepath):
        return result
    try:
        with fits.open(filepath) as hdul:
            for idx, label in band_map.items():
                if idx >= len(hdul) or hdul[idx].data is None:
                    continue
                d = hdul[idx].data
                df = pd.DataFrame({
                    "MJD":      d["MJD"].astype(np.float64),
                    "CTR":      d["CTR"].astype(np.float64),
                    "STAT_ERR": d["STAT_ERR"].astype(np.float64),
                })
                df = df[df["CTR"] >= 0].dropna(subset=["MJD", "CTR"])
                result[label] = df.sort_values("MJD").reset_index(drop=True)
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
    return result


def _merge_detectors(df1, df2, label):
    if df1 is None and df2 is None:
        return None
    if df1 is None or len(df1) == 0:
        return df2.rename(columns={"CTR": label + "_CTR", "STAT_ERR": label + "_ERR"})
    if df2 is None or len(df2) == 0:
        return df1.rename(columns={"CTR": label + "_CTR", "STAT_ERR": label + "_ERR"})

    a = df1.sort_values("MJD")
    b = df2.sort_values("MJD")
    merged = pd.merge_asof(
        a, b, on="MJD",
        suffixes=("_d1", "_d2"),
        tolerance=1.5 / 86400,
        direction="nearest"
    )

    w1 = np.where(merged["STAT_ERR_d1"] > 0, 1.0 / merged["STAT_ERR_d1"] ** 2, 0)
    w2 = np.where(merged["STAT_ERR_d2"] > 0, 1.0 / merged["STAT_ERR_d2"] ** 2, 0)
    wt = w1 + w2
    wt_safe = np.where(wt > 0, wt, 1)

    return pd.DataFrame({
        "MJD":          merged["MJD"],
        label + "_CTR": (w1 * merged["CTR_d1"].fillna(0) + w2 * merged["CTR_d2"].fillna(0)) / wt_safe,
        label + "_ERR": np.where(wt > 0, 1.0 / np.sqrt(wt_safe), 0),
    }).dropna().reset_index(drop=True)


def load_hel1os():
    print("Loading HEL1OS...")
    folders = get_latest_version_folders(str(HEL1OS_BASE))
    acc = {l: [] for l in list(CDTE_BANDS.values()) + list(CZT_BANDS.values())}

    for i, folder in enumerate(folders):
        c1 = _read_fits_bands(os.path.join(folder, "cdte", "lightcurve_cdte1.fits"), CDTE_BANDS)
        c2 = _read_fits_bands(os.path.join(folder, "cdte", "lightcurve_cdte2.fits"), CDTE_BANDS)
        z1 = _read_fits_bands(os.path.join(folder, "czt",  "lightcurve_czt1.fits"),  CZT_BANDS)
        z2 = _read_fits_bands(os.path.join(folder, "czt",  "lightcurve_czt2.fits"),  CZT_BANDS)

        for label in CDTE_BANDS.values():
            r = _merge_detectors(c1.get(label), c2.get(label), label)
            if r is not None:
                acc[label].append(r)

        for label in CZT_BANDS.values():
            r = _merge_detectors(z1.get(label), z2.get(label), label)
            if r is not None:
                acc[label].append(r)

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(folders)} observations processed...")

    final = {}
    for label, dfs in acc.items():
        if dfs:
            combined = (pd.concat(dfs)
                        .sort_values("MJD")
                        .drop_duplicates("MJD")
                        .reset_index(drop=True))
            final[label] = combined
            print(f"  {label}: {len(combined):,} rows")
        else:
            print(f"  {label}: no data")
    return final


def load_solexs():
    print("Loading SoLEXS...")
    files = sorted([
        os.path.join(r, f)
        for r, _, fs in os.walk(str(SOLEXS_BASE))
        for f in fs if f.endswith(".lc.gz") and "sdd2" in f.lower()
    ])
    print(f"  Found {len(files)} SDD2 files")

    dfs = []
    for fp in files:
        try:
            with gzip.open(fp, "rb") as f:
                with fits.open(f) as hdul:
                    hdu     = hdul[1]
                    d       = hdu.data
                    if d is None or len(d) == 0:
                        continue
                    mjdrefi = float(hdu.header.get("MJDREFI", SOLEXS_MJDREFI))
                    mjdreff = float(hdu.header.get("MJDREFF", 0.0))
                    mjd     = (mjdrefi + mjdreff) + d["TIME"].astype(np.float64) / 86400.0
                    counts  = d["COUNTS"].astype(np.float64)
                    df      = pd.DataFrame({"MJD": mjd, "SOLEXS_COUNTS": counts})
                    df      = df[df["SOLEXS_COUNTS"] >= 0].dropna().sort_values("MJD").reset_index(drop=True)
                    dfs.append(df)
        except Exception as e:
            print(f"  Error: {fp}: {e}")

    if not dfs:
        print("  No SoLEXS data loaded")
        return None

    combined = (pd.concat(dfs)
                .sort_values("MJD")
                .drop_duplicates("MJD")
                .reset_index(drop=True))
    print(f"  SOLEXS_COUNTS: {len(combined):,} rows")
    return combined


def build_master():
    hel1os_data = load_hel1os()
    solexs_df   = load_solexs()

    print("\nMerging all bands on MJD...")

    backbone = "CDTE_1p8_90keV" if "CDTE_1p8_90keV" in hel1os_data else list(hel1os_data.keys())[0]
    master   = hel1os_data[backbone][["MJD"]].copy()

    for label, df in hel1os_data.items():
        master = pd.merge_asof(
            master.sort_values("MJD"),
            df.sort_values("MJD"),
            on="MJD", tolerance=2.0 / 86400, direction="nearest"
        )

    if solexs_df is not None:
        master = pd.merge_asof(
            master.sort_values("MJD"),
            solexs_df.sort_values("MJD"),
            on="MJD", tolerance=2.0 / 86400, direction="nearest"
        )

    master["datetime"] = pd.to_datetime(master["MJD"] - 40587.0, unit="D", origin="unix")
    master = master.sort_values("MJD").reset_index(drop=True)

    print(f"\nmaster_data shape : {master.shape[0]:,} rows x {master.shape[1]} cols")
    print(f"MJD range         : {master['MJD'].min():.4f} → {master['MJD'].max():.4f}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved             : {OUTPUT_PATH}")
    return master


if __name__ == "__main__":
    build_master()