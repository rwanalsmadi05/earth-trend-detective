"""Disk cache. DataFrames -> Parquet, blobs -> files, plus meta.json with fetch dates.
Pattern: use cache if present; otherwise fetch live and store; if the live fetch of a
refresh fails, silently serve the stale cache."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .config import CACHE_DIR

META = CACHE_DIR / "meta.json"


def _meta() -> dict:
    return json.loads(META.read_text("utf-8")) if META.exists() else {}


_META_LOCK = threading.Lock()   # parallel fetches (monthly + daily + images) all stamp meta.json


def _stamp(key: str, extra: dict | None = None):
    with _META_LOCK:
        m = _meta()
        m[key] = {"fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"), **(extra or {})}
        META.write_text(json.dumps(m, indent=2), "utf-8")


def meta_for(key: str) -> dict:
    return _meta().get(key, {})


def load_df(key: str):
    p = CACHE_DIR / f"{key}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def cached_df(key: str, fetch, refresh: bool = False, extra: dict | None = None):
    """Return (df, status): 'cached' | 'fresh' | 'stale-cache'."""
    have = load_df(key)
    if have is not None and not refresh:
        return have, "cached"
    try:
        df = fetch()
        df.to_parquet(CACHE_DIR / f"{key}.parquet")
        _stamp(key, extra)
        return df, "fresh"
    except Exception:
        if have is not None:
            return have, "stale-cache"
        raise


def blob_path(key: str) -> Path:
    return CACHE_DIR / key


def save_blob(key: str, data: bytes, extra: dict | None = None):
    blob_path(key).write_bytes(data)
    _stamp(key, extra)
