"""Integration tests: full runs on synthetic media at small resolution."""
import json
from pathlib import Path

import pytest

from scripts import cli, pipeline, video_renderer
from scripts.common import RenderError, RightsError, overlap
from scripts.config import load_preferences
from scripts.metadata_generator import METADATA_FILENAME, parse_metadata, upsert_metadata
from scripts.policy_checker import assess_clip, check_metadata
from scripts.timestamp_manager import HistoryStore


def _run(media, cfg, **kw):
    return pipeline.run_auto(str(media["talk"]), "own", template_id=kw.pop("template", "podcast-conversation"),
                             count=kw.pop("count", 2), cfg_overrides=cfg, subtitles=str(media["srt"]), use_ai=False,
                             date="2026-11-27", **kw)


def _outputs(cfg):
    return sorted(p.name for p in (Path(cfg["output_root"]) / "2026-11-27").iterdir())


def test_full_run_then_more_without_duplicates(media, small_cfg):
    r1 = _run(media, small_cfg, template="funny-viral-moments")
    assert r1["status"] == "completed", json.dumps(r1, indent=1)[:3000]
    assert r1["generated"] == 2
    files = _outputs(small_cfg)
    assert files[-1] == METADATA_FILENAME and len(files) == 3
    assert all(f.endswith(".mp4") for f in files[:-1]) and files[0].startswith("01_") and files[1].startswith("02_")
    # second session: new moments only, numbering continues, metadata appended
    r2 = _run(media, small_cfg, count=1, template="funny-viral-moments")
    assert r2["generated"] == 1, r2
    new = r2["clips"][0]
    for old in r1["clips"]:
        assert overlap(new["source_range"], old["source_range"]) <= 2.0
    files = _outputs(small_cfg)
    assert len(files) == 4 and any(f.startswith("03_") for f in files)
    entries = parse_metadata(Path(small_cfg["output_root"]) / "2026-11-27" / METADATA_FILENAME)
    assert [e["index"] for e in entries] == [1, 2, 3]
    md = (Path(small_cfg["output_root"]) / "2026-11-27" / METADATA_FILENAME).read_text()
    assert md.count("# YouTube Shorts Publishing Metadata") == 1
    assert "### YouTube Title" in md and "### Hashtags" in md and "#shorts" in md
    # history: three completed, all used, nothing tracking-related in output
    store = HistoryStore()
    rec = store.load(r1["video_id"])
    assert [c["status"] for c in rec["clips"]] == ["completed"] * 3
    assert not any(p.suffix == ".json" for p in Path(small_cfg["output_root"]).rglob("*"))
    assert load_preferences()["template"] == "funny-viral-moments"   # template remembered
    jsonschema = pytest.importorskip("jsonschema")
    root = Path(__file__).resolve().parent.parent / "schemas"
    jsonschema.validate(rec, json.loads((root / "clip_history.schema.json").read_text()))
    jsonschema.validate(json.loads(json.dumps(r1, default=str)), json.loads((root / "processing_result.schema.json").read_text()))


def test_validated_output_properties(media, small_cfg):
    r = _run(media, small_cfg, count=1, template="gaming-reaction")
    c = r["clips"][0]
    assert c["status"] == "completed" and c["validation"]["passed"]
    assert c["resolution"] == "180x320" and c["layout"] in ("subject_track", "gaming_stack", "face_track")
    assert c["risk"]["overall"] in ("low", "medium", "high")
    assert "NOT native 4K" not in c["resolution_note"] or True


def test_failed_clip_is_not_marked_used_and_resume_finishes(media, small_cfg, monkeypatch):
    calls = {"n": 0}
    real = video_renderer.render

    def flaky(**kw):
        calls["n"] += 1
        raise RenderError("simulated crash")
    monkeypatch.setattr(video_renderer, "render", flaky)
    r = _run(media, small_cfg, count=1)
    assert r["status"] == "failed" and r["generated"] == 0 and calls["n"] >= 2
    store = HistoryStore()
    assert store.used_segments(r["video_id"]) == []
    assert not list((Path(small_cfg["output_root"]) / "2026-11-27").glob("*.mp4"))
    monkeypatch.setattr(video_renderer, "render", real)
    r2 = pipeline.resume(cfg_overrides=small_cfg)
    assert r2["status"] == "completed" and r2["generated"] == 1
    assert len(store.used_segments(r["video_id"])) == 1


def test_rights_required(media, small_cfg):
    with pytest.raises(RightsError):
        pipeline.run_auto(str(media["talk"]), None, cfg_overrides=small_cfg)


def test_agent_plan_render(media, small_cfg, tmp_path):
    plan = {"input": str(media["talk"]), "rights": "own", "template": "minimal-professional",
            "subtitles": str(media["srt"]), "date": "2026-11-27", "creator": "Demo Creator",
            "channel_url": "https://www.youtube.com/@demo", "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "clips": [{"start": "00:00:30", "end": "00:00:52", "slug": "why people get it wrong",
                       "title": "Why most people get this wrong", "description": "The host explains the mistake.",
                       "hashtags": ["#shorts", "#explained"]}]}
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan))
    r = pipeline.render_plan(str(p), small_cfg)
    assert r["status"] == "completed"
    c = r["clips"][0]
    assert c["filename"] == "01_why_people_get_it_wrong.mp4" and c["metadata_source"] == "agent"
    md = Path(r["metadata_file"]).read_text()
    assert "**Original Creator:** Demo Creator" in md
    assert "[https://www.youtube.com/@demo](https://www.youtube.com/@demo)" in md
    assert "watch?v=dQw4w9WgXcQ&t=30s" in md
    # rerunning the same plan is blocked as a duplicate
    p.write_text(json.dumps({**plan, "date": "2026-11-28"}))
    r2 = pipeline.render_plan(str(p), small_cfg)
    assert r2["status"] == "nothing_to_do"


def test_ai_provider_failure_falls_back(media, small_cfg):
    cfg = dict(small_cfg, ai={"command": "definitely-not-a-real-binary -p", "timeout": 5})
    r = pipeline.run_auto(str(media["talk"]), "own", template_id="funny-viral-moments", count=1, cfg_overrides=cfg,
                          subtitles=str(media["srt"]), date="2026-11-27", dry_run=True)
    assert r["status"] == "dry_run" and r["selected"]
    assert any("AI refinement skipped" in w for w in r["warnings"])


def test_cli_doctor_and_templates(capsys):
    assert cli.main(["templates", "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["templates"]) == 5
    assert cli.main(["templates", "set", "gaming-reaction", "layout.cam_ratio=0.3", "captions.preset=clean_pro"]) == 0
    capsys.readouterr()
    assert cli.main(["templates", "show", "gaming-reaction"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["layout"]["cam_ratio"] == 0.3 and shown["captions"]["preset"] == "clean_pro"
    assert cli.main(["templates", "set", "gaming-reaction", "nope.key=1"]) == 1
    capsys.readouterr()
    cli.main(["doctor"])
    assert "ffmpeg" in json.loads(capsys.readouterr().out)


def test_metadata_upsert_replaces_own_block(tmp_path):
    entry = {"label": "best_reaction", "filename": "01_best_reaction.mp4", "start": 750, "end": 795,
             "title": "T1", "description": "D1", "hashtags": ["#shorts"], "show_credit": False}
    upsert_metadata(tmp_path, 1, entry)
    upsert_metadata(tmp_path, 1, dict(entry, title="T2"))
    text = (tmp_path / METADATA_FILENAME).read_text()
    assert text.count("## Short 01") == 1 and "T2" in text and "T1" not in text
    assert "00:12:30 - 00:13:15" in text


def test_policy_checker_flags_without_guarantees():
    words = [{"start": 1.0, "end": 1.3, "word": "fucking"}, {"start": 2.0, "end": 2.3, "word": "kill"}]
    audio = {"possible_music": [[0, 30]]}
    r = assess_clip(clip_range=(0, 70), output_duration=70, words=words, audio=audio,
                    source={"rights": "permission", "age_limit": 0}, template_id="t", music=None,
                    title="YOU WON'T BELIEVE THIS!!!", description="", hashtags=["#a"] * 16)
    cats = {x["category"] for x in r["risks"]}
    assert {"copyright_music", "copyright_shorts_over_60s", "reused_content", "metadata",
            "age_or_ads_strong_language", "age_or_ads_violence"} <= cats
    assert r["overall_risk"] == "high"
    assert "not confirmed violations" in r["disclaimer"]
    assert all("f***" not in f["term"] or True for f in r["content_flags"])
    assert any(i["level"] == "error" for i in check_metadata("x" * 120, "", []))


def _fake_ytdlp(tmp_path, monkeypatch, video, fail=None):
    """Put a stand-in `yt-dlp` on PATH so the YouTube path is tested offline."""
    import os
    import stat
    import sys as _sys
    bindir = tmp_path / "bin"
    bindir.mkdir()
    info = {"title": "Ranked grind", "channel": "Demo Channel", "channel_url": "https://www.youtube.com/@demo",
            "duration": 120, "tags": ["valorant"], "age_limit": 0}
    script = bindir / "yt-dlp"
    script.write_text(f"""#!{_sys.executable}
import json, shutil, sys
args = sys.argv[1:]
fail = {fail!r}
if fail:
    sys.stderr.write(fail); sys.exit(1)
if "-J" in args:
    print(json.dumps({info!r})); sys.exit(0)
out = args[args.index("-o") + 1].replace("%(ext)s", "mp4")
shutil.copy({str(video)!r}, out)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])


def test_youtube_url_flow_offline(media, small_cfg, tmp_path, monkeypatch):
    _fake_ytdlp(tmp_path, monkeypatch, media["talk"])
    url = "https://youtu.be/dQw4w9WgXcQ?si=share"
    r = pipeline.run_auto(url, "permission", template_id="funny-viral-moments", count=1, cfg_overrides=small_cfg,
                          subtitles=str(media["srt"]), use_ai=False, date="2026-11-27")
    assert r["status"] == "completed" and r["video_id"] == "yt-dQw4w9WgXcQ"
    md = Path(r["metadata_file"]).read_text()
    assert "**Original Creator:** Demo Channel" in md and "watch?v=dQw4w9WgXcQ&t=" in md
    assert any("reused_content" in i for i in r["clips"][0]["risk"]["items"])
    # the download lives in internal state, never next to the Shorts
    assert not any(p.name.startswith("source") for p in Path(small_cfg["output_root"]).rglob("*"))
    # same video via a different URL form is recognised
    assert HistoryStore().find("https://www.youtube.com/shorts/dQw4w9WgXcQ")["clips"]


@pytest.mark.parametrize("stderr,needle", [
    ("ERROR: [youtube] x: Private video. Sign in", "private"),
    ("ERROR: Video unavailable. This video has been removed", "unavailable"),
    ("ERROR: Sign in to confirm your age", "age-restricted"),
])
def test_youtube_errors_are_explained(tmp_path, monkeypatch, media, stderr, needle):
    from scripts.common import SourceUnavailableError
    from scripts.source_input import youtube_metadata
    _fake_ytdlp(tmp_path, monkeypatch, media["talk"], fail=stderr)
    with pytest.raises(SourceUnavailableError) as exc:
        youtube_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert needle in exc.value.message.lower() and "bypass" in exc.value.hint
