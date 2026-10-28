"""Keeps Windows from idle-sleeping until a marker appears in a log file (no settings are changed).

    python scripts/keep_awake_until.py data/alpha/results/llm_discovery.log ALLDONE
Uses SetThreadExecutionState (the API media players use); the request ends when this process exits.
"""
import ctypes
import sys
import time
from pathlib import Path

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
log, marker = Path(sys.argv[1]), sys.argv[2]
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
try:
    while not (log.exists() and marker in log.read_text(encoding="utf-8", errors="ignore")):
        time.sleep(60)
finally:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
