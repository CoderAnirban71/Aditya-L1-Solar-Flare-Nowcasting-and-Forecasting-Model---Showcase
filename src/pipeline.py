"""
pipeline.py  —  full detection pipeline
ingest → trigger → filter → benchmark
"""

import sys
import time
from pathlib import Path
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from data_ingestion       import build_master
from statistical_trigger   import run_triggering
from morphological_filter  import run_morphological_filter
from benchmarking          import download_goes_flare_list, match_flares

MASTER_CSV  = ROOT / "outputs" / "master_data.csv"
TRIGGER_CSV = ROOT / "outputs" / "triggered_data.csv"
CATALOG_CSV = ROOT / "outputs" / "flare_catalog.csv"
LABELED_CSV = ROOT / "outputs" / "flare_catalog_labeled.csv"


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def run_pipeline():
    print("=" * 55)
    print("  Solar Flare Detection Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # Step 1: ingest
    print(f"[{_ts()}] ── Step 1 | Data Ingestion ──")
    t = time.time()
    master = build_master()
    print(f"    done ({time.time()-t:.1f}s)  shape={master.shape}")

    # Step 2: trigger
    print(f"[{_ts()}] ── Step 2 | Statistical Trigger (Poisson 5σ) ──")
    t = time.time()
    trigger = run_triggering(master)
    trigger.to_csv(TRIGGER_CSV, index=False)
    print(f"    done ({time.time()-t:.1f}s)  triggered={trigger['ANY_TRIG'].sum():,}")

    # Step 3: filter
    print(f"[{_ts()}] ── Step 3 | Morphological Filter ──")
    t = time.time()
    catalog = run_morphological_filter(trigger)
    catalog.to_csv(CATALOG_CSV, index=False)
    print(f"    done ({time.time()-t:.1f}s)  flares={len(catalog)}")

    # Step 4: benchmark
    print(f"[{_ts()}] ── Step 4 | Benchmarking (vs GOES) ──")
    t = time.time()
    goes_df = download_goes_flare_list()
    labeled = match_flares(catalog, goes_df)
    labeled.to_csv(LABELED_CSV, index=False)
    print(f"    done ({time.time()-t:.1f}s)  confirmed={labeled['confirmed'].sum()}")
    print(f"    classes={labeled['flare_class'].value_counts().to_dict()}")

    print(f"\n[{_ts()}] pipeline complete  ({time.time()-t0:.1f}s total)")
    print(f"  output → {LABELED_CSV}")
    return labeled


if __name__ == "__main__":
    run_pipeline()