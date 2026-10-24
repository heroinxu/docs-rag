"""Question log: one JSON line per question asked, for the top-questions report.

Stores only the question text and how it was answered. No IPs, user IDs or names.

Environment:
    DOCS_RAG_LOG   log file path (default logs/questions.jsonl); "off" disables logging
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

PATH = os.environ.get("DOCS_RAG_LOG", str(Path(__file__).parent / "logs" / "questions.jsonl"))
_lock = threading.Lock()


def log_question(question, res, source):
    if PATH == "off":
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "question": question[:500],
        "answered": not res.get("refused", False) and bool(res.get("citations")),
        "citations": len(res.get("citations", [])),
        "unverified": res.get("unsupported", 0),
        "pages": sorted({c["url"] for c in res.get("citations", [])}),
    }
    try:
        Path(PATH).parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:  # logging must never break answering
        print(f"question log write failed: {e}")


def read_log(path=PATH):
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a half-written last line
    return entries
