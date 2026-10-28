"""Probe: how far back does Finnhub company-news really go on the configured key?

    python scripts/probe_news_sources.py [TICKER]

Requests (a) one month in early 2024, (b) one month in mid 2025, (c) the last 7 days, prints counts,
earliest/latest timestamps and a few titles, then a verdict. Exit code 0 = 2024 data available,
1 = not available, 2 = key rejected / probe inconclusive. The key is read from FINNHUB_API_KEY only.
"""
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
URL = "https://finnhub.io/api/v1/company-news"


def fetch(symbol: str, a: date, b: date, key: str):
    r = requests.get(URL, params={"symbol": symbol, "from": a.isoformat(), "to": b.isoformat()},
                     headers={"X-Finnhub-Token": key}, timeout=30)
    return r.status_code, (r.json() if r.status_code == 200 else r.text[:120])


def main() -> int:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        print("FINNHUB_API_KEY is not set (environment or .env)")
        return 2
    today = date.today()
    windows = [("(a) early 2024", date(2024, 3, 1), date(2024, 3, 31)),
               ("(b) mid 2025", date(2025, 6, 1), date(2025, 6, 30)),
               ("(c) last 7 days", today - timedelta(days=7), today)]
    results = {}
    for label, a, b in windows:
        status, body = fetch(symbol, a, b, key)
        time.sleep(1.1)
        if status != 200:
            print(f"{label}: HTTP {status} {body}")
            results[label] = None
            continue
        ts = [datetime.fromtimestamp(x["datetime"], tz=timezone.utc) for x in body if x.get("datetime")]
        print(f"{label} {a}..{b}: {len(body)} articles; "
              f"earliest {min(ts) if ts else None}; latest {max(ts) if ts else None}")
        for x in body[:3]:
            print("    -", (x.get("headline") or "")[:90], "|", x.get("source"))
        results[label] = len(body)
    print("\nVERDICT")
    if all(v is None for v in results.values()):
        print("INCONCLUSIVE: every request was rejected (check FINNHUB_API_KEY).")
        return 2
    print("  2024 data :", "YES" if results["(a) early 2024"] else "NO (empty)")
    print("  2025 data :", "YES" if results["(b) mid 2025"] else "NO (empty)")
    print("  last 7 days:", "YES" if results["(c) last 7 days"] else "NO (empty)")
    return 0 if results["(a) early 2024"] else 1


if __name__ == "__main__":
    sys.exit(main())
