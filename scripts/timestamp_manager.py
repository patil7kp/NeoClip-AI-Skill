r"""Persistent timestamp history and duplicate prevention.

One JSON file per source video in <state_dir>/history/<video_id>.json (never in output folders).
Survives new sessions because it is plain files, not agent memory.

Clip lifecycle:  reserved -> rendering -> completed
                                       \-> failed      (never counted as used)
A clip only becomes "used" (blocks future selections) once marked completed, which the
pipeline does only after the file passed quality validation and was moved into place.
Stale "reserved/rendering" entries from a crashed run are recovered as "interrupted".

CLI: python scripts/timestamp_manager.py show <video_id|url|file>
     python scripts/timestamp_manager.py list
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import (SCHEMA_VERSION, HistoryError, atomic_write_json, file_lock, fmt_ts,
                            merge_intervals, now_iso, overlap, read_json, safe_id, state_dir,
                            subtract_intervals, today)

ACTIVE = {"reserved", "rendering"}
FINAL = {"completed", "failed", "interrupted", "skipped"}
DEFAULT_MAX_OVERLAP_SECONDS = 2.0     # tiny overlaps (shared lead-in breath) are tolerated
DEFAULT_MAX_OVERLAP_RATIO = 0.10


class HistoryStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else state_dir() / "history"
        self.root.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------- io
    def path(self, video_id: str) -> Path:
        return self.root / f"{safe_id(video_id)}.json"

    def load(self, video_id: str) -> dict | None:
        return read_json(self.path(video_id), None)

    def _save(self, rec: dict) -> None:
        rec["last_updated"] = now_iso()
        rec["used_segments"] = self._used(rec)
        if rec.get("duration"):
            rec["unused_segments"] = subtract_intervals([0.0, rec["duration"]], rec["used_segments"])
        atomic_write_json(self.path(rec["video_id"]), rec)

    def _mutate(self, video_id: str, fn):
        p = self.path(video_id)
        with file_lock(p):
            rec = read_json(p, None)
            if rec is None:
                raise HistoryError(f"No history for {video_id}. Call ensure() first.")
            result = fn(rec)
            self._save(rec)
            return result

    # ----------------------------------------------------------------- records
    def ensure(self, source: dict) -> dict:
        """Create or refresh the record for a source; returns the record."""
        p = self.path(source["video_id"])
        with file_lock(p):
            rec = read_json(p, None)
            if rec is None:
                rec = {
                    "schema_version": SCHEMA_VERSION,
                    "video_id": source["video_id"],
                    "source_kind": source.get("kind"),
                    "url": source.get("url"),
                    "title": source.get("title"),
                    "creator": source.get("creator"),
                    "channel_url": source.get("channel_url"),
                    "duration": source.get("duration"),
                    "local_paths": [],
                    "first_processed": now_iso(),
                    "templates_used": [],
                    "caption_preset": None,
                    "clips": [],
                }
            for key in ("url", "title", "creator", "channel_url", "duration"):
                if source.get(key):
                    rec[key] = source[key]
            lp = source.get("local_path")
            if lp and source.get("kind") == "local" and lp not in rec["local_paths"]:
                rec["local_paths"].append(lp)
            self._save(rec)
            return rec

    def find(self, query: str) -> dict | None:
        """Look up by video_id, YouTube URL/id, or a local path previously recorded."""
        from scripts.source_input import parse_youtube_id
        yid = parse_youtube_id(query)
        if yid:
            return self.load(f"yt-{yid}")
        direct = self.load(query)
        if direct:
            return direct
        for rec in self.all():
            if query in (rec.get("local_paths") or []) or rec.get("url") == query:
                return rec
        return None

    def all(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            rec = read_json(p, None)
            if rec and "video_id" in rec:
                out.append(rec)
        return out

    # ----------------------------------------------------------------- clip lifecycle
    def reserve(self, video_id: str, start: float, end: float, template: str, *,
                job_id: str, label: str = "", overlap_reason: str | None = None) -> str:
        clip_id = uuid.uuid4().hex[:12]

        def fn(rec):
            rec["clips"].append({
                "clip_id": clip_id, "job_id": job_id, "start": round(float(start), 3),
                "end": round(float(end), 3), "label": label, "template": template,
                "status": "reserved", "filename": None, "output_path": None,
                "processing_date": today(), "created_at": now_iso(), "updated_at": now_iso(),
                "overlap_reason": overlap_reason, "error": None, "attempts": 0,
            })
            if template not in rec["templates_used"]:
                rec["templates_used"].append(template)
            return clip_id
        return self._mutate(video_id, fn)

    def update_clip(self, video_id: str, clip_id: str, **fields) -> dict:
        def fn(rec):
            for c in rec["clips"]:
                if c["clip_id"] == clip_id:
                    c.update(fields)
                    c["updated_at"] = now_iso()
                    return dict(c)
            raise HistoryError(f"Clip {clip_id} not found for {video_id}.")
        return self._mutate(video_id, fn)

    def mark_rendering(self, video_id: str, clip_id: str, attempt: int) -> dict:
        return self.update_clip(video_id, clip_id, status="rendering", attempts=attempt)

    def mark_completed(self, video_id: str, clip_id: str, filename: str, output_path: str,
                       **extra) -> dict:
        if not Path(output_path).exists():
            raise HistoryError(f"Refusing to mark clip {clip_id} completed: {output_path} does not exist.")
        return self.update_clip(video_id, clip_id, status="completed", filename=filename,
                                output_path=str(output_path), error=None, completed_at=now_iso(), **extra)

    def mark_failed(self, video_id: str, clip_id: str, error: str) -> dict:
        return self.update_clip(video_id, clip_id, status="failed", error=error[:2000])

    def recover_interrupted(self, video_id: str) -> list[dict]:
        """Turn reserved/rendering clips left by a crashed run into 'interrupted' (not used)."""
        def fn(rec):
            changed = []
            for c in rec["clips"]:
                if c["status"] in ACTIVE:
                    c["status"] = "interrupted"
                    c["updated_at"] = now_iso()
                    changed.append(dict(c))
            return changed
        if not self.path(video_id).exists():
            return []
        return self._mutate(video_id, fn)

    def mark_window_done(self, video_id: str, start: float, end: float) -> None:
        """Hour-by-hour mode: remember that [start, end] has been processed, so the next run moves on."""
        def fn(rec):
            done = rec.setdefault("windows_done", [])
            w = [round(float(start), 3), round(float(end), 3)]
            if w not in done:
                done.append(w)
                done.sort()
        self._mutate(video_id, fn)

    def windows_done(self, video_id: str) -> list[list[float]]:
        return list((self.load(video_id) or {}).get("windows_done") or [])

    def set_caption_preset(self, video_id: str, preset: str) -> None:
        def fn(rec):
            rec["caption_preset"] = preset
        self._mutate(video_id, fn)

    # ----------------------------------------------------------------- queries
    @staticmethod
    def _used(rec: dict) -> list[list[float]]:
        return merge_intervals([c["start"], c["end"]] for c in rec.get("clips", [])
                               if c["status"] == "completed")

    def used_segments(self, video_id: str, include_active: bool = False) -> list[list[float]]:
        rec = self.load(video_id)
        if not rec:
            return []
        statuses = {"completed"} | (ACTIVE if include_active else set())
        return merge_intervals([c["start"], c["end"]] for c in rec["clips"] if c["status"] in statuses)

    def unused_segments(self, video_id: str, duration: float, min_len: float = 5.0) -> list[list[float]]:
        return [s for s in subtract_intervals([0.0, duration], self.used_segments(video_id, True))
                if s[1] - s[0] >= min_len]

    def completed_clips(self, video_id: str) -> list[dict]:
        rec = self.load(video_id) or {"clips": []}
        return [c for c in rec["clips"] if c["status"] == "completed"]


def overlap_conflict(start: float, end: float, used: Iterable[Iterable[float]],
                     max_seconds: float = DEFAULT_MAX_OVERLAP_SECONDS,
                     max_ratio: float = DEFAULT_MAX_OVERLAP_RATIO) -> float:
    """Return seconds of overlap if it exceeds the tolerance, else 0.0."""
    used = merge_intervals(used)
    ov = sum(overlap((start, end), u) for u in used)
    limit = min(max_seconds, (end - start) * max_ratio)
    return round(ov, 3) if ov > limit else 0.0


def summarize(rec: dict) -> dict:
    clips = rec.get("clips", [])
    by_status: dict[str, int] = {}
    for c in clips:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    used = rec.get("used_segments", [])
    dur = rec.get("duration") or 0
    return {
        "video_id": rec["video_id"], "title": rec.get("title"), "url": rec.get("url"),
        "duration": dur, "clip_counts": by_status,
        "used_seconds": round(sum(e - s for s, e in used), 1),
        "used_percent": round(100 * sum(e - s for s, e in used) / dur, 1) if dur else None,
        "completed": [{"label": c["label"], "filename": c["filename"], "date": c["processing_date"],
                       "range": f"{fmt_ts(c['start'])} - {fmt_ts(c['end'])}"}
                      for c in clips if c["status"] == "completed"],
        "templates_used": rec.get("templates_used", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    store = HistoryStore()
    if not args or args[0] == "list":
        print(json.dumps([summarize(r) for r in store.all()], indent=2))
        return 0
    if args[0] == "show" and len(args) > 1:
        q = args[1]
        rec = store.find(q)
        if rec is None and Path(q).expanduser().exists():
            from scripts.source_input import fingerprint
            rec = store.load(f"local-{fingerprint(Path(q).expanduser())}")
        print(json.dumps(summarize(rec) if rec else {"found": False, "query": q}, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
