from scripts.clip_selector import (build_timeline, cue_hits, select_clips, snap_window, validate_plan_clips)
from scripts.common import overlap
from scripts.templates_config import load_template
from scripts.transcription import load_subtitles

from conftest import make_srt


def _audio(duration, spikes=(), silences=()):
    times = [i * 0.5 for i in range(int(duration * 2))]
    ez = [0.0] * len(times)
    for s in spikes:
        ez[int(s * 2)] = 4.0
    return {"has_audio": True, "window": 0.5, "times": times, "rms_db": [-30.0] * len(times),
            "energy_z": ez, "silences": [list(s) for s in silences],
            "spikes": [{"t": float(s), "z": 4.0, "db": -10.0} for s in spikes], "possible_music": []}


def test_cue_hits_detects_phrases(tmp_path):
    t = load_subtitles(make_srt(tmp_path / "a.srt", 30))
    cats = {h["category"] for h in cue_hits(t)}
    assert {"surprise", "excitement", "laughter", "story"} <= cats


def test_selection_prefers_signal_and_respects_template(tmp_path):
    t = load_subtitles(make_srt(tmp_path / "a.srt", 300))
    tpl = load_template("gaming-reaction")
    res = select_clips(300, None, _audio(300, spikes=[60, 150, 240]), t, tpl, [], count=3)
    sel = res["selected"]
    assert len(sel) == 3
    for c in sel:
        assert tpl["duration"]["min"] - 0.01 <= c["end"] - c["start"] <= tpl["duration"]["max"] + 0.5
        assert c["excerpt"] and c["reasons"] and c["range"]
    # no two selected clips overlap meaningfully
    for i, a in enumerate(sel):
        for b in sel[i + 1:]:
            assert overlap((a["start"], a["end"]), (b["start"], b["end"])) <= 0.1 * min(a["duration"], b["duration"])
    assert sorted(c["score"] for c in res["candidates"])[::-1] == [c["score"] for c in res["candidates"]]


def test_used_segments_are_excluded(tmp_path):
    t = load_subtitles(make_srt(tmp_path / "a.srt", 300))
    tpl = load_template("podcast-conversation")
    first = select_clips(300, None, _audio(300, spikes=[60, 150, 240]), t, tpl, [], count=2)["selected"]
    used = [[c["start"], c["end"]] for c in first]
    second = select_clips(300, None, _audio(300, spikes=[60, 150, 240]), t, tpl, used, count=2)["selected"]
    assert second
    for c in second:
        assert sum(overlap((c["start"], c["end"]), u) for u in used) <= 2.0


def test_windows_snap_to_sentences(tmp_path):
    t = load_subtitles(make_srt(tmp_path / "a.srt", 120))
    starts = {round(s["start"], 2) for s in t["segments"]}
    ends = {round(s["end"], 2) for s in t["segments"]}
    s, e = snap_window(20.0, 50.0, 30.0, 120, {"min": 15, "target": 30, "max": 60}, t, None)
    assert any(abs((s + 0.12) - x) < 0.05 for x in starts), (s, sorted(starts))
    assert any(abs((e - 0.25) - x) < 0.05 for x in ends), (e, sorted(ends))


def test_no_transcript_no_audio_still_returns_clips():
    tpl = load_template("minimal-professional")
    res = select_clips(200, None, None, None, tpl, [], count=3)
    assert len(res["selected"]) == 3


def test_validate_plan_clips_blocks_duplicates_and_bad_ranges():
    tpl = load_template("minimal-professional")
    used = [[100, 140]]
    clips = [{"start": 105, "end": 135}, {"start": 105, "end": 135, "overlap_reason": "different angle"},
             {"start": -5, "end": 10}, {"start": 10, "end": 300}, {"start": 200, "end": 230}]
    ok, warnings = validate_plan_clips(clips, 250, used, tpl)
    assert [(c["start"], c["end"]) for c in ok] == [(105.0, 135.0), (200.0, 230.0)]
    assert len(warnings) == 3


def test_timeline_normalization_handles_flat_video():
    tl = build_timeline(30, None, None, None)
    assert tl["n"] == 30 and all(len(v) == 30 for v in tl["features"].values())
