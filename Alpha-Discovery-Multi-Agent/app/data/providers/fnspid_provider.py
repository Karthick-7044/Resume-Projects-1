"""FNSPID news provider: filter-on-the-fly extraction + normalisation to the unified news schema.

Source: Hugging Face dataset Zihan1004/FNSPID (CC BY-NC-4.0, non-commercial research use; cite
Dong, Fan & Peng, arXiv:2402.06698). The two news CSVs are 5.7 GB and 23.2 GB, so they are never
stored: rows are streamed over HTTP range requests and only rows for the configured universe inside
the study window are kept.

Layout discovered by inspection (see NEWS_PIPELINE.md)
- All_external.csv        : 11 columns, \\r\\n rows, real timestamps (mostly Benzinga headlines), NOT sorted by
                            ticker, contains non-English text and rows with no ticker -> full stream-filter.
- nasdaq_exteral_data.csv : 12 columns (leading float row index). First ~75% is sorted by ticker (block
                            search by binary search over byte offsets); the tail is a different, unsorted
                            section with an empty row index -> full stream-filter.
Rows are split on a strict row-start pattern and parsed one by one, so one malformed quote can never
swallow neighbouring rows. Everything is resumable (progress.json) and idempotent.
"""
import csv
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

import pandas as pd
import requests

from app.config.settings import DATA_DIR, RAW_NEWS_DIR

logger = logging.getLogger(__name__)

HF_URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/{name}.csv"
FILE_SIZES = {"All_external": 5_731_397_037, "nasdaq_exteral_data": 23_232_979_597}
FNSPID_RAW_DIR = DATA_DIR / "raw" / "news_fnspid"
PARTS_DIR = FNSPID_RAW_DIR / "parts"
PROGRESS_PATH = FNSPID_RAW_DIR / "progress.json"

ROW_RX = re.compile(rb"(?m)^(?:\d+\.0,|,)?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC,")
SEGMENT_BYTES = 24 * 1024 * 1024
SUMMARY_MAX_CHARS = 600
# FNSPID tags pre-2022 Facebook as FB and Alphabet's other share class as GOOG; kept aside, not used.
ALIAS_CANDIDATES = {"FB": "META", "GOOG": "GOOGL"}


def parse_row(raw: bytes) -> Optional[Dict]:
    """Parses one row (already split on the row-start pattern) into a dict, or None if malformed."""
    try:
        f = next(csv.reader(io.StringIO(raw.decode("utf-8", "replace"))))
    except (csv.Error, StopIteration):
        return None
    if not f:
        return None
    off = 0 if re.match(r"\d{4}-\d{2}-\d{2} ", f[0]) else 1       # nasdaq rows carry a leading row index
    if len(f) < off + 5:
        return None
    return {
        "date_raw": f[off][:19], "title": f[off + 1].strip(), "symbol": f[off + 2].strip().upper(),
        "url": f[off + 3].strip(), "publisher": f[off + 4].strip(),
        "summary": (f[off + 9].strip()[:SUMMARY_MAX_CHARS] if len(f) > off + 9 else ""),
        "row_format": "A" if off == 0 else ("B" if re.match(r"\d+\.0$", f[0]) else "C"),
    }


class FnspidExtractor:
    def __init__(self, tickers: Iterable[str], raw_dir: Path = FNSPID_RAW_DIR,
                 start: str = "2013-01-01", end: str = "2023-12-31"):
        self.tickers = {t.upper() for t in tickers}
        self.wanted = self.tickers | set(ALIAS_CANDIDATES)
        self.raw_dir = Path(raw_dir)
        self.parts_dir = self.raw_dir / "parts"
        self.parts_dir.mkdir(parents=True, exist_ok=True)
        self.progress_path = self.raw_dir / "progress.json"
        self.start, self.end = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
        self.session = requests.Session()
        self.progress: Dict = json.loads(self.progress_path.read_text()) if self.progress_path.exists() else {}
        self._part_no = len(list(self.parts_dir.glob("*.parquet")))

    # ------------------------------------------------------------------ plumbing
    def _save_progress(self):
        self.progress_path.write_text(json.dumps(self.progress, indent=1))

    def _get(self, name: str, a: int, b: int) -> bytes:
        """Bytes [a, b] inclusive via a Range request, with retries."""
        last = None
        for attempt in range(1, 7):
            try:
                r = self.session.get(HF_URL.format(name=name), headers={"Range": f"bytes={a}-{b}"}, timeout=120)
                if r.status_code == 206:
                    return r.content
                if r.status_code == 200 and a == 0:
                    return r.content[: b + 1]
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last = str(e)
            time.sleep(min(60, 3 * attempt * attempt))
        raise RuntimeError(f"Range request failed for {name} [{a}-{b}]: {last}")

    def _flush(self, rows: List[Dict], tag: str):
        if not rows:
            return
        self._part_no += 1
        pd.DataFrame(rows).to_parquet(self.parts_dir / f"{self._part_no:05d}_{tag}.parquet", index=False)

    def _keep(self, row: Dict) -> bool:
        if row["symbol"] not in self.wanted or not row["title"]:
            return False
        ts = pd.to_datetime(row["date_raw"], errors="coerce")
        return pd.notna(ts) and self.start <= ts < self.end

    # ------------------------------------------------------------------ streaming
    def stream_filter(self, name: str, start: int, end: int, tag: str, section: str,
                      progress_key: Optional[str] = None, flush_rows: int = 3000) -> int:
        """Streams [start, end) of a file, keeps wanted rows. Resumes from progress[progress_key]."""
        pos = start
        if progress_key and progress_key in self.progress:
            pos = max(pos, self.progress[progress_key].get("offset", start))
            if self.progress[progress_key].get("done"):
                return 0
        carry, kept, buf_rows, t0, scanned = b"", 0, [], time.time(), 0
        fetch_pos = pos
        while fetch_pos < end or carry:
            final = fetch_pos >= end
            if not final:
                seg_end = min(fetch_pos + SEGMENT_BYTES, end)
                data = self._get(name, fetch_pos, seg_end - 1)
                fetch_pos = seg_end
                buf = carry + data
                starts = [m.start() for m in ROW_RX.finditer(buf)]
                if not starts:
                    carry = buf
                    continue
                cut = starts[-1]
            else:
                buf, cut = carry, len(carry)
                starts = [m.start() for m in ROW_RX.finditer(buf)]
            bounds = [s for s in starts if s < cut] + [cut]
            for a, b in zip(bounds, bounds[1:]):
                row = parse_row(buf[a:b])
                scanned += 1
                if row and self._keep(row):
                    row["source_file"], row["section"] = name, section
                    buf_rows.append(row)
                    kept += 1
            carry = buf[cut:] if not final else b""
            if len(buf_rows) >= flush_rows or final:
                self._flush(buf_rows, tag)
                buf_rows = []
            if progress_key:
                self.progress[progress_key] = {"offset": fetch_pos - len(carry), "done": final}
                self._save_progress()
            mb = (fetch_pos - start) / 1e6
            if int(mb) % 240 < SEGMENT_BYTES / 1e6:
                logger.info(f"[{tag}] {mb:,.0f}/{(end - start) / 1e6:,.0f} MB, scanned {scanned:,}, kept {kept:,}, "
                            f"{mb / max(time.time() - t0, 1):.1f} MB/s")
            if final:
                break
        if progress_key:
            self.progress[progress_key] = {"offset": end, "done": True}
            self._save_progress()
        return kept

    # ------------------------------------------------------------------ sorted-block search (nasdaq file)
    def _probe(self, name: str, off: int, n: int = 400_000) -> Optional[Tuple[int, Dict]]:
        """First complete row starting at/after off -> (absolute offset, parsed row)."""
        buf = self._get(name, off, min(off + n, FILE_SIZES[name] - 1))
        ms = [m.start() for m in ROW_RX.finditer(buf)]
        for a, b in zip(ms, ms[1:]):
            row = parse_row(buf[a:b])
            if row:
                return off + a, row
        return None

    def find_tail_start(self, name: str = "nasdaq_exteral_data") -> int:
        """Smallest offset from which rows use the unsorted 'C' format (empty row index)."""
        if "tail_start" in self.progress:
            return self.progress["tail_start"]
        lo, hi = 0, FILE_SIZES[name]
        while hi - lo > 262_144:
            mid = (lo + hi) // 2
            p = self._probe(name, mid)
            if p is None:
                p = self._probe(name, mid, 1_500_000)
            if p is None or p[1]["row_format"] == "C":
                hi = mid
            else:
                lo = mid
        buf = self._get(name, lo, min(hi + 2_000_000, FILE_SIZES[name] - 1))
        ms = [m.start() for m in ROW_RX.finditer(buf)]
        tail = hi
        for a, b in zip(ms, ms[1:]):
            row = parse_row(buf[a:b])
            if row and row["row_format"] == "C":
                tail = lo + a
                break
        self.progress["tail_start"] = tail
        self._save_progress()
        return tail

    def lower_bound(self, name: str, symbol: str, limit: int, strict: bool = False) -> int:
        """Byte offset of the first row (in the sorted region [0, limit)) whose symbol >= symbol (or > if strict)."""
        pred = (lambda s: s > symbol) if strict else (lambda s: s >= symbol)
        lo, hi = 0, limit
        while hi - lo > 262_144:
            mid = (lo + hi) // 2
            p = self._probe(name, mid)
            if p is None:
                p = self._probe(name, mid, 1_500_000)
            if p is None or pred(p[1]["symbol"]):
                hi = mid
            else:
                lo = mid
        buf = self._get(name, lo, min(hi + 2_000_000, FILE_SIZES[name] - 1))
        ms = [m.start() for m in ROW_RX.finditer(buf)]
        for a, b in zip(ms, ms[1:]):
            row = parse_row(buf[a:b])
            if row and pred(row["symbol"]):
                return lo + a
        return hi

    # ------------------------------------------------------------------ orchestration
    def run_all_external(self) -> int:
        return self.stream_filter("All_external", 0, FILE_SIZES["All_external"], "all_external", "all_external",
                                  "job_all_external")

    def run_nasdaq(self, blocks_only: bool = False, tail_only: bool = False, reverse: bool = False) -> Dict[str, int]:
        name = "nasdaq_exteral_data"
        tail = self.find_tail_start(name)
        logger.info(f"nasdaq sorted region = [0, {tail:,}); unsorted tail = [{tail:,}, {FILE_SIZES[name]:,})")
        out = {}
        for sym in ([] if tail_only else sorted(self.wanted, reverse=reverse)):
            key = f"job_nasdaq_block_{sym}"
            if self.progress.get(key, {}).get("done"):
                continue
            a = self.lower_bound(name, sym, tail)
            b = self.lower_bound(name, sym, tail, strict=True)
            logger.info(f"nasdaq block {sym}: bytes [{a:,}, {b:,}) = {(b - a) / 1e6:.0f} MB")
            out[sym] = self.stream_filter(name, a, b, f"nasdaq_{sym}", "nasdaq_sorted", key) if b > a else 0
            self.progress[key] = {"offset": b, "done": True}
            self._save_progress()
        if blocks_only:
            return out
        out["TAIL"] = self.stream_filter(name, tail, FILE_SIZES[name], "nasdaq_tail", "nasdaq_tail", "job_nasdaq_tail")
        return out

    def load_parts(self) -> pd.DataFrame:
        files = sorted(self.parts_dir.glob("*.parquet"))
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()
