"""Fama-French 5-factor + momentum attribution of the walk-forward long-short returns.

    python -m app.alpha.ff_attribution [--tag ""]

Downloads the free daily factor files from Kenneth French's data library once (cached in data/raw/ff), regresses each
daily out-of-sample return series on Mkt-RF, SMB, HML, RMW, CMA and Mom, and reports the annualised intercept (alpha)
with Newey-West (HAC, 5 lags) t-statistics. The long-short portfolios are self-financing (dollar-neutral), so their
returns are already excess returns; long-only active returns (portfolio minus benchmark) are also self-financing.
"""
import argparse
import io
import json
import logging
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm

from app.config.settings import ALPHA_RESULTS_DIR, RAW_DATA_DIR

logger = logging.getLogger("FFAttribution")
FF_DIR = RAW_DATA_DIR / "ff"
FF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FF_FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}
FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
HAC_LAGS = 5


def _download(name: str) -> bytes:
    FF_DIR.mkdir(parents=True, exist_ok=True)
    p = FF_DIR / name
    if not p.exists():
        r = requests.get(FF_BASE + name, timeout=60)
        r.raise_for_status()
        p.write_bytes(r.content)
    return p.read_bytes()


def parse_french_csv(text: str) -> pd.DataFrame:
    """Parses a Ken French daily CSV (header row, YYYYMMDD rows in percent, copyright footer) into decimal returns."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() and ln.split(",")[0].strip() == "" and "," in ln)
    header = [c.strip() for c in lines[start].split(",")]
    rows = []
    for ln in lines[start + 1:]:
        parts = [c.strip() for c in ln.split(",")]
        if len(parts) != len(header) or not (parts[0].isdigit() and len(parts[0]) == 8):
            if rows:
                break
            continue
        rows.append(parts)
    df = pd.DataFrame(rows, columns=["date"] + header[1:])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df.set_index("date").astype(float) / 100.0


def load_factors() -> pd.DataFrame:
    out = []
    for name in FF_FILES.values():
        with zipfile.ZipFile(io.BytesIO(_download(name))) as z:
            out.append(parse_french_csv(z.read(z.namelist()[0]).decode("latin-1")))
    f = out[0].join(out[1], how="inner")
    f.columns = [c.strip() for c in f.columns]
    return f.rename(columns={"Mom   ": "Mom", "MOM": "Mom"})


def align_forward_returns(y: pd.Series, factor_dates: pd.DatetimeIndex) -> pd.Series:
    """Our series is indexed by the signal date t and holds the return from close t to close t+1, whereas French dates a
    return by the day it is realised; move each value to the next factor date so both describe the same day."""
    pos = factor_dates.searchsorted(y.index, side="right")
    ok = pos < len(factor_dates)
    return pd.Series(y.values[ok], index=factor_dates[pos[ok]])


def regress(y: pd.Series, factors: pd.DataFrame) -> dict:
    y = align_forward_returns(y, factors.index)
    d = pd.concat([y.rename("y"), factors[FACTORS]], axis=1, join="inner").dropna()
    d = d[d["y"] != 0.0]   # days in cash (exactly zero return) carry no information about factor exposure
    if len(d) < 60:
        return {"n": int(len(d))}
    X = sm.add_constant(d[FACTORS])
    m = sm.OLS(d["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    raw = d["y"]
    return {"n": int(len(d)), "start": str(d.index.min().date()), "end": str(d.index.max().date()),
            "mean_ann": float(raw.mean() * 252), "alpha_ann": float(m.params["const"] * 252),
            "alpha_t": float(m.tvalues["const"]), "alpha_p": float(m.pvalues["const"]), "r2": float(m.rsquared),
            "betas": {k: float(m.params[k]) for k in FACTORS}, "beta_t": {k: float(m.tvalues[k]) for k in FACTORS}}


def run(tag: str = "", extra: list = None) -> dict:
    fac = load_factors()
    series = {}
    p = ALPHA_RESULTS_DIR / f"walkforward_daily{tag}.parquet"
    if p.exists():
        d = pd.read_parquet(p)
        series.update({c: d[c] for c in d.columns if c.endswith("_net") or c.endswith("_gross")})
    for ex in extra or []:
        q = ALPHA_RESULTS_DIR / ex
        if q.exists():
            d = pd.read_parquet(q)
            series.update({f"{ex.split('.')[0]}:{c}": d[c] for c in d.columns})
    res = {"factors": FACTORS, "hac_lags": HAC_LAGS, "factor_sample": [str(fac.index.min().date()), str(fac.index.max().date())],
           "series": {k: regress(v.dropna(), fac) for k, v in series.items()}}
    (ALPHA_RESULTS_DIR / f"ff_attribution{tag}.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    ap.add_argument("--extra", nargs="*", default=[])
    a = ap.parse_args()
    r = run(a.tag, a.extra)
    for k, v in r["series"].items():
        if "alpha_ann" in v:
            print(f"{k:45s} alpha {v['alpha_ann']:+.4f}/yr  t={v['alpha_t']:+.2f}  p={v['alpha_p']:.3f}  R2={v['r2']:.2f}  "
                  f"MKT {v['betas']['Mkt-RF']:+.2f} MOM {v['betas']['Mom']:+.2f}")
