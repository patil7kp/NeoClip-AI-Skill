import re

from scripts.caption_generator import (SAFE_BOTTOM, SAFE_TOP, build_ass, choose_position, chunk_words,
                                       clean_words)


def _w(text, start=0.0, step=0.4):
    return [{"start": start + i * step, "end": start + i * step + step * 0.9, "word": t, "prob": 1.0}
            for i, t in enumerate(text.split())]


def test_clean_words_fixes_obvious_errors():
    out = clean_words(_w("um so i think the the answer is , yes"), {"answr": "answer"})
    text = " ".join(w["word"] for w in out)
    assert text == "So I think the answer is, yes"


def test_corrections_map():
    out = clean_words(_w("we played valorent today."), {"valorent": "Valorant"})
    assert "Valorant" in " ".join(w["word"] for w in out)


def test_chunking_limits_words_and_breaks_on_punctuation():
    words = clean_words(_w("this is a long sentence. and here comes another one that keeps going on"))
    chunks = chunk_words(words, max_words=3, max_chars=18)
    assert all(len(c) <= 3 for c in chunks)
    assert chunks[1][-1]["word"].endswith(".")  or any(c[-1]["word"].endswith(".") for c in chunks)
    assert all(sum(len(w["word"]) + 1 for w in c) - 1 <= 18 or len(c) == 1 for c in chunks)


def test_ass_has_synced_events_and_consistent_style():
    words = clean_words(_w("no way that was insane let's go", start=1.0))
    ass, info = build_ass(words, 1080, 1920, 6.0, "bold_pop", {"mode": "face_track", "faces_out": []})
    events = [ln for ln in ass.splitlines() if ln.startswith("Dialogue")]
    assert info["events"] == len(events) > 0
    assert "Style: Cap," in ass and "PlayResY: 1920" in ass
    assert "NO" in ass and "LET'S" in ass                     # uppercase preset
    first = events[0].split(",")[1]
    assert first == "0:00:01.00"
    assert SAFE_TOP <= info["position_y"] <= SAFE_BOTTOM


def test_position_avoids_faces_and_uses_gaming_seam():
    y = choose_position({"mode": "face_track", "faces_out": [(0.62, 0.70, 0.78)]}, 0.045)
    assert not 0.6 <= y <= 0.8
    assert choose_position({"mode": "gaming_stack", "seam_y": 0.36}, 0.05) == 0.36


def test_hook_overlay_and_minimal_preset_box():
    ass, info = build_ass(_w("hello there"), 1080, 1920, 3.0, "minimal", {"mode": "face_track"},
                          hook={"text": "He did NOT expect that", "duration": 2.0})
    assert info["hook"]["text"] == "He did NOT expect that"
    assert re.search(r"Style: Cap,[^\n]*,3,", ass)              # BorderStyle 3 = boxed captions


def test_hook_never_covers_facecam_in_gaming_layout():
    from scripts.caption_generator import hook_position
    lay = {"mode": "gaming_stack", "seam_y": 0.36, "cam_position": "top"}
    assert hook_position(lay, 0.36, 0.05) > 0.36            # in the gameplay panel, below the seam captions
    face_lay = {"mode": "face_track", "faces_out": [(0.08, 0.15, 0.24)]}
    y = hook_position(face_lay, 0.70, 0.045)
    assert not 0.04 <= y <= 0.28


def test_template_caption_style_setting(isolated_state):
    import pytest
    from scripts.common import InputError
    from scripts.templates_config import customize_template
    t = customize_template("gaming-reaction", ["captions.uppercase=false"])
    assert t["captions"]["overrides"]["uppercase"] is False
    with pytest.raises(InputError):
        customize_template("gaming-reaction", ["captions.not_a_style=1"])
