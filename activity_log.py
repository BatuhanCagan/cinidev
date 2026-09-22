import json
import os
import threading
from datetime import datetime

LOG_FILE = "activity.jsonl"
_lock = threading.Lock()


def log_event(action, project_name, details=""):
    """Append a timestamped project-management event to activity.jsonl."""
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "project": project_name,
        "details": details,
    }
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_events(limit=200):
    """Return up to `limit` events, newest first."""
    if not os.path.exists(LOG_FILE):
        return []
    with _lock:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    events = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    events.reverse()
    return events
