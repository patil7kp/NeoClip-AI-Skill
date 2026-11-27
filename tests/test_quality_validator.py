import subprocess


from scripts.quality_validator import validate

from conftest import needs_ffmpeg


def _render(path, size="180x320", d=4, audio=True, extra_vf=None, black=False):
    src = f"color=c=black:s={size}:d={d}:r=30" if black else f"testsrc2=s={size}:d={d}:r=30"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=d={d}:sample_rate=48000", "-c:a", "aac"]
    if extra_vf:
        cmd += ["-vf", extra_vf]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-t", str(d), str(path)]
    subprocess.run(cmd, check=True)
    return path


@needs_ffmpeg
def test_good_file_passes(tmp_path):
    f = _render(tmp_path / "ok.mp4")
    r = validate(f, width=180, height=320, expected_duration=4, expect_audio=True)
    assert r["passed"], r


@needs_ffmpeg
def test_wrong_resolution_and_missing_audio_fail(tmp_path):
    f = _render(tmp_path / "wide.mp4", size="320x180", audio=False)
    r = validate(f, width=180, height=320, expected_duration=4, expect_audio=True)
    assert not r["passed"]
    assert {"resolution", "aspect_9_16", "audio_present"} <= set(r["failed"])


@needs_ffmpeg
def test_black_frames_and_letterbox_fail(tmp_path):
    f = _render(tmp_path / "black.mp4", black=True)
    r = validate(f, width=180, height=320, expected_duration=4, expect_audio=True)
    assert "no_black_frames" in r["failed"]
    g = _render(tmp_path / "bars.mp4", extra_vf="scale=180:100,pad=180:320:0:110:black")
    r2 = validate(g, width=180, height=320, expected_duration=4, expect_audio=True)
    assert "no_empty_bars" in r2["failed"]


@needs_ffmpeg
def test_duration_and_caption_checks(tmp_path):
    f = _render(tmp_path / "ok.mp4")
    caps = {"events": 3, "safe_zone": [0.06, 0.1, 0.86, 0.78], "position_y": 0.7, "position_x": 0.46, "last": 3.5}
    r = validate(f, width=180, height=320, expected_duration=10, expect_audio=True, captions=caps)
    assert "duration" in r["failed"] and "captions_in_safe_zone" not in r["failed"]
    caps_bad = dict(caps, position_y=0.95, events=0)
    r = validate(f, width=180, height=320, expected_duration=4, expect_audio=True, captions=caps_bad)
    assert "captions_present" in r["failed"]


def test_missing_file(tmp_path):
    r = validate(tmp_path / "nope.mp4", width=180, height=320, expected_duration=4, expect_audio=True)
    assert r["failed"] == ["file_exists"]
