import json

import pytest

from scripts.common import HistoryError
from scripts.timestamp_manager import HistoryStore, overlap_conflict, summarize

SRC = {"video_id": "yt-dQw4w9WgXcQ", "kind": "youtube", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "title": "Test", "creator": "Creator", "channel_url": "https://www.youtube.com/@c", "duration": 600.0}


def _complete(store, tmp_path, s, e, name="01_x.mp4"):
    cid = store.reserve(SRC["video_id"], s, e, "gaming-reaction", job_id="j1", label="x")
    f = tmp_path / name
    f.write_bytes(b"x" * 2000)
    store.mark_completed(SRC["video_id"], cid, name, str(f))
    return cid


def test_history_persists_across_instances(tmp_path):
    a = HistoryStore()
    a.ensure(SRC)
    _complete(a, tmp_path, 100, 140)
    b = HistoryStore()                      # "new session"
    assert b.used_segments(SRC["video_id"]) == [[100.0, 140.0]]
    assert b.find("https://youtu.be/dQw4w9WgXcQ")["video_id"] == SRC["video_id"]
    rec = b.load(SRC["video_id"])
    assert rec["unused_segments"] == [[0.0, 100.0], [140.0, 600.0]]
    assert rec["clips"][0]["filename"] == "01_x.mp4" and rec["clips"][0]["template"] == "gaming-reaction"


def test_failed_and_interrupted_clips_are_not_used(tmp_path):
    s = HistoryStore()
    s.ensure(SRC)
    bad = s.reserve(SRC["video_id"], 10, 40, "t", job_id="j")
    s.mark_failed(SRC["video_id"], bad, "boom")
    s.reserve(SRC["video_id"], 50, 80, "t", job_id="j")        # crash mid-render: stays reserved
    assert s.used_segments(SRC["video_id"]) == []
    assert s.used_segments(SRC["video_id"], include_active=True) == [[50.0, 80.0]]
    recovered = s.recover_interrupted(SRC["video_id"])
    assert len(recovered) == 1
    assert s.used_segments(SRC["video_id"], include_active=True) == []
    statuses = [c["status"] for c in s.load(SRC["video_id"])["clips"]]
    assert statuses == ["failed", "interrupted"]


def test_cannot_mark_completed_without_file(tmp_path):
    s = HistoryStore()
    s.ensure(SRC)
    cid = s.reserve(SRC["video_id"], 1, 20, "t", job_id="j")
    with pytest.raises(HistoryError):
        s.mark_completed(SRC["video_id"], cid, "nope.mp4", str(tmp_path / "nope.mp4"))


def test_overlap_tolerance():
    used = [[100, 140]]
    assert overlap_conflict(140, 180, used) == 0.0          # touching
    assert overlap_conflict(139, 180, used) == 0.0          # 1 s shared breath is fine
    assert overlap_conflict(120, 160, used) == 20.0         # real duplicate
    assert overlap_conflict(0, 30, used) == 0.0


def test_corrupt_history_is_preserved_not_discarded(isolated_state):
    s = HistoryStore()
    s.ensure(SRC)
    p = s.path(SRC["video_id"])
    p.write_text("{not json")
    with pytest.raises(HistoryError):
        s.load(SRC["video_id"])
    assert list(p.parent.glob("*.corrupt-*"))


def test_history_lives_outside_output(isolated_state, tmp_path):
    s = HistoryStore()
    s.ensure(SRC)
    assert str(s.path(SRC["video_id"])).startswith(str(isolated_state))
    summary = summarize(s.load(SRC["video_id"]))
    assert summary["used_percent"] == 0.0
    json.dumps(summary)
