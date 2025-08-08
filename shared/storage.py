from __future__ import annotations
import json
import os
import time
from typing import Dict, List

SUBJECTS = {"math", "english", "thinking"}


def ensure_question_dirs(base_dir: str = "questions") -> None:
    os.makedirs(base_dir, exist_ok=True)
    for sub in SUBJECTS:
        os.makedirs(os.path.join(base_dir, sub), exist_ok=True)


def save_items(ctx: Dict, items: List[Dict], base_dir: str = "questions") -> List[str]:
    """Save items to subject-specific JSON files; return written paths."""
    ensure_question_dirs(base_dir)
    written: List[str] = []
    # Group by subject
    by_subject: Dict[str, List[Dict]] = {}
    for it in items:
        subj = str(it.get("subject", "mixed"))
        by_subject.setdefault(subj, []).append(it)
    ts = int(time.time())
    job_id = ctx.get("job_id", "job")
    for subj, group in by_subject.items():
        subj_dir = subj if subj in SUBJECTS else "mixed"
        os.makedirs(os.path.join(base_dir, subj_dir), exist_ok=True)
        path = os.path.join(base_dir, subj_dir, f"{job_id}_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ctx": ctx, "items": group}, f, ensure_ascii=False, indent=2)
        written.append(path)
    return written 