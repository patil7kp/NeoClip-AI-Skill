import pytest

from scripts.common import InputError, UnsupportedFormatError
from scripts.source_input import check_rights, local_source, parse_youtube_id, resolve_source
from scripts.video_analyzer import analyze_visual, detect_facecam, guess_content_type, probe
from scripts.audio_analyzer import analyze_audio


@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1", "dQw4w9WgXcQ"),
    ("youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=short", None),
    ("https://vimeo.com/123456", None),
    ("https://evil.com/watch?v=dQw4w9WgXcQ", None),
    ("not a url", None),
])
def test_parse_youtube_id(url, vid):
    assert parse_youtube_id(url) == vid


def test_rights_are_required():
    from scripts.common import RightsError
    with pytest.raises(RightsError):
        check_rights(None)
    with pytest.raises(RightsError):
        check_rights("i-gave-credit")
    assert check_rights("OWN") == "own"


def test_probe_local(media):
    meta = probe(media["talk"])
    assert meta["width"] == 320 and meta["height"] == 180
    assert meta["has_audio"] and abs(meta["duration"] - 120) < 0.5
    assert 29 < meta["fps"] < 31


def test_local_source_identity_is_content_based(media, tmp_path):
    a = local_source(str(media["talk"]))
    copy = tmp_path / "renamed copy.mp4"
    copy.write_bytes(media["talk"].read_bytes())
    b = local_source(str(copy))
    assert a["video_id"] == b["video_id"] and a["video_id"].startswith("local-")


def test_unsupported_and_missing_inputs(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("hi")
    with pytest.raises(UnsupportedFormatError):
        local_source(str(bad))
    with pytest.raises(InputError):
        local_source(str(tmp_path / "missing.mp4"))
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"\x00" * 2048)
    with pytest.raises(UnsupportedFormatError):
        local_source(str(corrupt))
    with pytest.raises(InputError):
        resolve_source("https://vimeo.com/1", "own")


def test_visual_analysis_shapes(media):
    meta = probe(media["talk"])
    v = analyze_visual(media["talk"], meta, sample_fps=1.0, face_fps=0.5, end=20)
    assert len(v["times"]) == len(v["motion"]) == len(v["motion_cx"]) >= 19
    assert all(0 <= x <= 1 for x in v["motion_cx"])
    assert v["content_hint"] in {"gaming", "podcast", "talking", "general"}


def test_audio_analysis_finds_silences_and_spikes(media):
    meta = probe(media["talk"])
    a = analyze_audio(media["talk"], meta)
    assert a["has_audio"]
    assert any(s <= 10.6 and e >= 11.3 for s, e in a["silences"]), a["silences"][:5]
    assert any(8.5 <= sp["t"] <= 10.5 for sp in a["spikes"]), a["spikes"][:5]


def test_audio_analysis_without_audio(media):
    meta = probe(media["silent"])
    a = analyze_audio(media["silent"], meta)
    assert a["has_audio"] is False and a["spikes"] == []


def _faces(center, n=20, size=0.06, jitter=0.0):
    out = []
    for i in range(n):
        dx = jitter * (i / n)
        out.append({"t": float(i), "boxes": [[center[0] - size / 2 + dx, center[1] - size / 2, size, size, 1.0]]})
    return out


def test_facecam_detected_for_static_corner_face():
    cam = detect_facecam(_faces((0.1, 0.8)), 20)
    assert cam and cam["rect"][0] < 0.1 and cam["rect"][1] > 0.5
    assert guess_content_type(_faces((0.1, 0.8)), 20, cam, [0.05] * 20) == "gaming"


def test_moving_or_central_face_is_not_a_facecam():
    assert detect_facecam(_faces((0.5, 0.45), size=0.15), 20) is None          # big, central
    assert detect_facecam(_faces((0.1, 0.8), jitter=0.15), 20) is None        # moving
    assert detect_facecam(_faces((0.1, 0.8), n=4), 20) is None                 # rarely present
