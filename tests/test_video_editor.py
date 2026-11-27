
from scripts.smart_cropper import piecewise_expr, plan_layout, simplify_keyframes
from scripts.templates_config import load_template
from scripts.video_cutter import TimelineMap, keep_intervals, trim_filter
from scripts.video_editor import plan_edit, zoom_expression


def _words(spans):
    return [{"start": s, "end": e, "word": f"w{i}", "prob": 1.0} for i, (s, e) in enumerate(spans)]


AUDIO = {"silences": [[3.0, 6.0], [8.2, 9.4]], "spikes": [{"t": 8.8, "z": 3.0, "db": -5}]}


def test_pause_removal_cuts_only_silent_gaps():
    words = _words([(0.2, 1.0), (1.1, 2.9), (6.1, 7.0), (7.1, 8.1), (9.5, 10.0)])
    cfg = {"enabled": True, "min_pause": 0.7, "pad": 0.15, "max_removed_ratio": 0.5}
    keeps = keep_intervals(0, 10, words, AUDIO, cfg)
    assert keeps[0][0] == 0 and keeps[-1][1] == 10
    assert keeps == [[0, 3.05], [5.95, 10]]                  # 3-6 s silence removed; 8.2-9.4 kept (spike)


def test_pause_removal_never_exceeds_ratio_and_can_be_disabled():
    words = _words([(0, 1), (5, 6), (10, 11)])
    audio = {"silences": [[1, 5], [6, 10]], "spikes": []}
    keeps = keep_intervals(0, 11, words, audio, {"enabled": True, "min_pause": 0.5, "pad": 0.1, "max_removed_ratio": 0.4})
    removed = 11 - sum(e - s for s, e in keeps)
    assert removed <= 0.4 * 11 + 1e-6
    assert keep_intervals(0, 11, words, audio, {"enabled": False}) == [[0, 11]]


def test_timeline_map_round_trip():
    tm = TimelineMap([[10, 13], [15, 20]])
    assert tm.duration == 8
    assert tm.to_output(11) == 1 and tm.to_output(15) == 3 and tm.to_output(14) is None
    assert tm.to_output_clamped(14) == 3
    assert abs(tm.to_source(4) - 16) < 1e-6
    mapped = tm.map_words(_words([(12.5, 13.5), (13.2, 14.0), (16, 17)]))
    assert [(w["start"], w["end"]) for w in mapped] == [(2.5, 3.0), (4.0, 5.0)]  # word inside a cut is dropped


def test_trim_filter_concat():
    graph, v, a = trim_filter([[10, 13], [15, 20]], 9.0, True)
    assert "concat=n=2:v=1:a=1" in graph and v == "[vcat]" and a == "[acat]"
    assert "trim=start=1.0000:end=4.0000" in graph
    graph, _, a = trim_filter([[10, 13]], 9.0, False)
    assert a == "" and "atrim" not in graph


def test_zoom_expression_is_bounded():
    expr = zoom_expression([{"t": 2.0, "strength": 0.2, "hold": 1.0}], 10, {"enabled": True, "style": "punch",
                                                                             "max_zoom": 1.15}, 30, [4.0])
    assert expr.startswith("clip(") and expr.endswith(",1,1.150)")
    assert zoom_expression([], 10, {"enabled": False, "style": "none"}, 30, []) is None


def test_plan_edit_uses_template(tmp_path):
    tpl = load_template("minimal-professional")
    ed = plan_edit({"start": 0, "end": 10}, tpl, AUDIO, None, 30)
    assert ed["zoom_expr"] is None and ed["output_duration"] == 10


def test_piecewise_expr_and_simplify():
    pts = [(0, 100), (1, 101), (2, 102), (3, 300)]
    simp = simplify_keyframes(pts, tol=3)
    assert simp[0] == (0, 100) and simp[-1] == (3, 300) and len(simp) <= 3
    expr = piecewise_expr(simp)
    assert expr.startswith("if(lt(t,") and "300.0" in expr
    assert piecewise_expr([(0, 5), (1, 5.2)]) == "5.0"


def _visual(faces, cam=None, cuts=()):
    times = [i * 0.5 for i in range(80)]
    return {"times": times, "motion": [0.05] * 80, "motion_cx": [0.6] * 80, "motion_cy": [0.5] * 80,
            "faces": faces, "scene_cuts": list(cuts), "facecam": cam, "face_fps": 1.0, "sample_fps": 2.0}


def test_face_track_centres_face_and_never_leaves_frame():
    faces = [{"t": float(t), "boxes": [[0.70, 0.2, 0.08, 0.14, 1.0]]} for t in range(40)]
    lay = plan_layout(1920, 1080, 1080, 1920, load_template("podcast-conversation")["layout"], _visual(faces), 0, 39,
                      TimelineMap([[0, 39]]))
    assert lay["mode"] == "face_track"
    cw = lay["crop"]["w"]
    assert cw == 608 and lay["crop"]["h"] == 1080
    xs = [x for _, x in lay["crop"]["x_keyframes"]]
    assert all(0 <= x <= 1920 - cw for x in xs)
    face_cx = (0.70 + 0.04) * 1920
    assert all(x <= face_cx <= x + cw for x in xs)          # face is inside the crop (not centre-cropped)
    assert abs(xs[0] - 960 + cw / 2) > 100                    # i.e. not a blind centre crop


def test_gaming_stack_layout_and_fallback():
    cam = {"rect": [0.02, 0.68, 0.16, 0.28], "face_center": [0.09, 0.78], "presence": 1.0, "confidence": 0.9}
    cfg = load_template("gaming-reaction")["layout"]
    lay = plan_layout(1920, 1080, 2160, 3840, cfg, _visual([], cam), 0, 30, TimelineMap([[0, 30]]))
    assert lay["mode"] == "gaming_stack"
    assert lay["gameplay"]["panel_h"] > lay["cam"]["panel_h"]                 # gameplay keeps the majority
    assert lay["cam"]["panel_h"] + lay["gameplay"]["panel_h"] == 3840
    assert 0.3 < lay["seam_y"] < 0.4
    gx = [x for _, x in lay["gameplay"]["x_keyframes"]]
    assert all(x >= 0.18 * 1920 - 1 for x in gx)                             # cam overlay kept out of gameplay
    lay2 = plan_layout(1920, 1080, 2160, 3840, cfg, _visual([]), 0, 30, TimelineMap([[0, 30]]))
    assert lay2["mode"] == "subject_track" and lay2["notes"]
