"""Small, credential-free UI event log; never format exception messages."""
import json
import os
from pathlib import Path
import re
import sys
import threading
from datetime import datetime, timezone

_lock = threading.Lock()


def record(event, **fields):
    safe = {"timestamp": datetime.now(timezone.utc).isoformat()}
    for key, value in {"event": event, **fields}.items():
        if re.fullmatch(r"[a-z_]{1,32}", key) and (type(value) in (bool, int)
                or isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value)):
            safe[key] = value
    try:
        path = Path(os.environ["LOCALAPPDATA"]) / "SmartTray/ui-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            if path.exists() and path.stat().st_size > 1_000_000:
                path.replace(path.with_suffix(".previous.jsonl"))
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(safe) + "\n")
    except OSError:
        pass  # Diagnostics must never make a callback fail.


def install_exception_hook():
    def hook(kind, value, tb):
        line = 0
        while tb:
            line = tb.tb_lineno
            tb = tb.tb_next
        record("callback_error", error_type=kind.__name__, line=line)
    sys.excepthook = hook
