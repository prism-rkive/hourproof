"""Energi Data Service client (Energinet, keyless). Month-by-month, cached on disk, patient on HTTP 429."""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable

import pandas as pd
import requests

from .config import CACHE

API = "https://api.energidataservice.dk/dataset/"
PAUSE_S = 2.0
_session = requests.Session()


class EDSError(RuntimeError):
    pass


class EDSBlocked(EDSError):
    """HTTP 403: Energinet blocks the IP. Fatal on purpose: retrying makes a block worse."""


BLOCKED_HELP = ("HTTP 403 from Energi Data Service: this IP address is blocked (usually after too many requests). "
                "Do NOT retry in a loop, that makes it worse. Already downloaded months stay cached in "
                f"{CACHE}. Ask Energinet to lift the block: https://www.energidataservice.dk/support-service")


def _get(dataset: str, params: dict, use_cache: bool = True) -> list[dict]:
    key = hashlib.sha256((dataset + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:20]
    f = CACHE / f"{dataset}_{params.get('start', 'latest')[:7]}_{key}.json"
    if use_cache and f.exists():
        return json.loads(f.read_text())
    wait = 10
    for attempt in range(10):
        time.sleep(PAUSE_S)
        try:
            r = _session.get(API + dataset, params=params, timeout=300)
        except requests.RequestException as e:
            print(f"   network error ({e.__class__.__name__}); retry in {wait}s")
            time.sleep(wait)
            wait = min(wait * 2, 180)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("Retry-After")
            w = int(ra) + 1 if ra and ra.isdigit() else wait
            print(f"   HTTP {r.status_code} on {dataset} {params.get('start', '')[:7]}: waiting {w}s ({attempt + 1}/10)")
            time.sleep(w)
            wait = min(wait * 2, 180)
            continue
        if r.status_code == 403:
            raise EDSBlocked(f"{dataset} {params.get('start', '')[:7]}: {BLOCKED_HELP}")
        r.raise_for_status()
        recs = r.json().get("records", [])
        if use_cache:
            f.write_text(json.dumps(recs))
        return recs
    raise EDSError(f"{dataset}: still rate-limited after 10 attempts; rerun later (finished months are cached)")


def fetch(dataset: str, start: pd.Timestamp, end: pd.Timestamp, filt: dict | None = None,
          columns: Iterable[str] | None = None, timecol: str = "HourUTC", use_cache: bool = True) -> pd.DataFrame:
    """All records in [start, end), requested one calendar month at a time."""
    frames = []
    edges = sorted({start, *pd.date_range(start, end, freq="MS"), end})
    for a, b in zip(edges[:-1], edges[1:]):
        params = {"start": a.strftime("%Y-%m-%dT%H:%M"), "end": b.strftime("%Y-%m-%dT%H:%M"), "limit": 0}
        if filt:
            params["filter"] = json.dumps(filt)
        if columns:
            params["columns"] = ",".join(columns)
        frames.append(pd.DataFrame(_get(dataset, params, use_cache)))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        raise EDSError(f"{dataset}: no records for {start}..{end}")
    df[timecol] = pd.to_datetime(df[timecol])
    lo, hi = df[timecol].min(), df[timecol].max()
    if lo < start - pd.Timedelta(days=2) or hi > end + pd.Timedelta(days=2):
        raise EDSError(f"{dataset}: API returned {lo}..{hi}, outside {start}..{end}: parameters ignored?")
    print(f"   {dataset}: {len(df):,} rows {lo:%Y-%m-%d %H:%M} .. {hi:%Y-%m-%d %H:%M}")
    return df


def latest(dataset: str, start: pd.Timestamp, end: pd.Timestamp, filt: dict | None = None) -> pd.DataFrame:
    """Uncached fetch for live data."""
    params = {"start": start.strftime("%Y-%m-%dT%H:%M"), "end": end.strftime("%Y-%m-%dT%H:%M"), "limit": 0}
    if filt:
        params["filter"] = json.dumps(filt)
    df = pd.DataFrame(_get(dataset, params, use_cache=False))
    if not df.empty and "HourUTC" in df:
        df["HourUTC"] = pd.to_datetime(df["HourUTC"])
    return df
