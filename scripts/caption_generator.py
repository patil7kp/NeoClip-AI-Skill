"""Standardized caption system (ASS subtitles burned in with libass).

One style system for every category. A project (source video) keeps the same preset for all
its Shorts: the preset chosen first is stored in the timestamp history and reused.

Pipeline: transcript words -> clean_words (punctuation/obvious ASR fixes, fillers dropped from
captions only) -> TimelineMap (sync after pause removal) -> chunk_words (short readable groups)
-> layout-aware position (YouTube UI safe zone, avoids faces/gameplay) -> ASS file.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.common import atomic_write_text

# YouTube Shorts overlays: channel/title/description at the bottom, action buttons on the right.
SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT = 0.10, 0.78, 0.06, 0.86

PRESETS: dict[str, dict] = {
    "bold_pop": {"fonts": ["Montserrat ExtraBold", "Montserrat Black", "Inter ExtraBold", "Arial Black",
                           "DejaVu Sans"], "bold": True, "size": 0.052, "primary": "FFFFFF",
                 "highlight": "FFD400", "outline": "000000", "outline_w": 0.10, "shadow": 0.04,
                 "uppercase": True, "max_words": 3, "max_chars": 18, "highlight_mode": "word", "pop": True,
                 "box": False},
    "clean_pro": {"fonts": ["Inter SemiBold", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans"], "bold": True,
                  "size": 0.042, "primary": "FFFFFF", "highlight": "7FD3FF", "outline": "000000",
                  "outline_w": 0.07, "shadow": 0.03, "uppercase": False, "max_words": 5, "max_chars": 26,
                  "highlight_mode": "keywords", "pop": False, "box": False},
    "story": {"fonts": ["Inter Bold", "Inter", "Arial", "DejaVu Sans"], "bold": True, "size": 0.044,
              "primary": "FFFFFF", "highlight": "FFB84D", "outline": "000000", "outline_w": 0.08, "shadow": 0.03,
              "uppercase": False, "max_words": 4, "max_chars": 24, "highlight_mode": "word", "pop": True,
              "box": False},
    "minimal": {"fonts": ["Inter Medium", "Inter", "Helvetica", "Arial", "DejaVu Sans"], "bold": False,
                "size": 0.038, "primary": "FFFFFF", "highlight": "FFFFFF", "outline": "000000",
                "outline_w": 0.0, "shadow": 0.0, "uppercase": False, "max_words": 6, "max_chars": 30,
                "highlight_mode": "none", "pop": False, "box": True},
}
FILLERS = {"um", "uh", "erm", "uhm", "hmm", "mm", "ah"}
EMPHASIS = re.compile(r"^(no|never|always|insane|crazy|huge|best|worst|win|won|lost|dead|money|free|"
                      r"secret|why|how|what|wow|yes|clutch|epic|love|hate|first|last|only|\d[\d,.%$k]*)$", re.I)


# --------------------------------------------------------------------------- fonts
_FONT_CACHE: dict[str, str] = {}


def resolve_font(candidates: list[str]) -> str:
    key = "|".join(candidates)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    chosen = candidates[-1]
    if shutil.which("fc-list"):
        try:
            names = subprocess.run(["fc-list", ":", "family", "style"], capture_output=True, text=True,
                                   timeout=10).stdout.lower()
            for c in candidates:
                fam = c.split(" ")[0].lower()
                if fam in names:
                    chosen = c
                    break
        except (subprocess.SubprocessError, OSError):
            pass
    else:
        chosen = candidates[0]  # macOS/Windows: libass asks the OS and falls back gracefully
    _FONT_CACHE[key] = chosen
    return chosen


# --------------------------------------------------------------------------- text cleanup
def clean_words(words: list[dict], corrections: dict[str, str] | None = None,
                drop_fillers: bool = True) -> list[dict]:
    corrections = {k.lower(): v for k, v in (corrections or {}).items()}
    out: list[dict] = []
    sentence_start = True
    for w in words:
        tok = w["word"].strip()
        if not tok:
            continue
        if re.fullmatch(r"[^\w]+", tok) and out:         # stray punctuation token -> attach
            out[-1]["word"] += tok
            out[-1]["end"] = max(out[-1]["end"], w["end"])
            continue
        bare = re.sub(r"[^\w']", "", tok).lower()
        if drop_fillers and bare in FILLERS:
            continue
        if bare in corrections:
            tok = re.sub(re.escape(bare), corrections[bare], tok, flags=re.I)
        if out and bare and re.sub(r"[^\w']", "", out[-1]["word"]).lower() == bare and \
                w["start"] - out[-1]["end"] < 0.4 and len(bare) > 1:
            out[-1]["end"] = w["end"]                       # "the the" -> "the"
            continue
        tok = re.sub(r"^i(?=$|'|[.,!?])", "I", tok)
        tok = re.sub(r"\s+([,.!?])", r"\1", tok)
        if sentence_start and tok[:1].islower():
            tok = tok[0].upper() + tok[1:]
        sentence_start = bool(re.search(r"[.!?]['\")]*$", tok))
        out.append({**w, "word": tok})
    return out


def chunk_words(words: list[dict], max_words: int, max_chars: int, max_gap: float = 0.6,
                max_dur: float = 2.6) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur:
            chars = sum(len(x["word"]) + 1 for x in cur) + len(w["word"])
            gap = w["start"] - cur[-1]["end"]
            if (len(cur) >= max_words or chars > max_chars or gap > max_gap
                    or w["end"] - cur[0]["start"] > max_dur or re.search(r"[.!?,;:]$", cur[-1]["word"])):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


# --------------------------------------------------------------------------- placement
def choose_position(layout: dict, preset_size: float) -> float:
    """Return the caption block centre y (0..1) that stays in the safe zone and off faces."""
    if layout.get("mode") == "gaming_stack" and layout.get("seam_y"):
        # sit on the seam between facecam and gameplay: covers neither the face nor the action
        y = layout["seam_y"]
        return max(SAFE_TOP + preset_size, min(SAFE_BOTTOM - preset_size, y))
    faces = layout.get("faces_out") or []
    band = preset_size * 1.4
    best, best_hits = 0.70, None
    for y in (0.70, 0.64, 0.74, 0.58, 0.28):
        hits = sum(1 for top, _, bot in faces if not (bot < y - band or top > y + band))
        if best_hits is None or hits < best_hits:
            best, best_hits = y, hits
        if hits == 0:
            break
    return best


def hook_position(layout: dict, caption_y: float, size: float) -> float:
    """Hook text goes where it hides neither a face nor the captions (gaming: top of the gameplay panel)."""
    if layout.get("mode") == "gaming_stack" and layout.get("seam_y"):
        seam = layout["seam_y"]
        return seam + 0.10 if layout.get("cam_position", "top") == "top" else max(SAFE_TOP + 0.04, seam - 0.10)
    faces = layout.get("faces_out") or []
    for y in (SAFE_TOP + 0.04, 0.22, 0.50):
        if abs(y - caption_y) < size * 3:
            continue
        if not any(top - 0.04 <= y <= bot + 0.04 for top, _, bot in faces):
            return y
    return SAFE_TOP + 0.04


# --------------------------------------------------------------------------- ASS
def _ass_color(hex_rgb: str, alpha: str = "00") -> str:
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    cs = int(round((s - int(s)) * 100))
    if cs == 100:
        s, cs = int(s) + 1, 0
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _wrap(tokens: list[str], max_line: int) -> list[str]:
    """Insert one \\N in the middle of long chunks so lines stay short on phones."""
    text_len = sum(len(t) + 1 for t in tokens)
    if text_len <= max_line or len(tokens) < 2:
        return tokens
    acc, split = 0, 1
    for i, t in enumerate(tokens):
        acc += len(t) + 1
        if acc >= text_len / 2:
            split = max(1, i + 1 if i + 1 < len(tokens) else i)
            break
    return tokens[:split - 1] + [tokens[split - 1] + "\\N"] + tokens[split:]


def build_ass(words: list[dict], out_w: int, out_h: int, duration: float, preset_name: str,
              layout: dict, overrides: dict | None = None, hook: dict | None = None) -> tuple[str, dict]:
    p = {**PRESETS.get(preset_name, PRESETS["clean_pro"]), **(overrides or {})}
    font = resolve_font(p["fonts"])
    size = int(out_h * p["size"])
    outline = max(0.0, size * p["outline_w"])
    shadow = size * p["shadow"]
    y = choose_position(layout, p["size"])
    x = int(out_w * (SAFE_LEFT + SAFE_RIGHT) / 2)
    ypx = int(out_h * y)
    border_style = 3 if p.get("box") else 1
    back = _ass_color("000000", "60") if p.get("box") else _ass_color("000000", "80")
    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {out_w}", f"PlayResY: {out_h}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{size},{_ass_color(p['primary'])},{_ass_color(p['highlight'])},"
        f"{_ass_color(p['outline'])},{back},{-1 if p['bold'] else 0},0,0,0,100,100,0,0,{border_style},"
        f"{outline:.1f},{shadow:.1f},5,{int(out_w * SAFE_LEFT)},{int(out_w * (1 - SAFE_RIGHT))},0,1",
        f"Style: Hook,{font},{int(size * 0.9)},{_ass_color('FFFFFF')},{_ass_color('FFFFFF')},"
        f"{_ass_color('000000')},{_ass_color('000000', '30')},-1,0,0,0,100,100,0,0,3,{size * 0.18:.1f},0,5,"
        f"{int(out_w * SAFE_LEFT)},{int(out_w * (1 - SAFE_RIGHT))},0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    chunks = chunk_words(words, p["max_words"], p["max_chars"])
    hl = _ass_color(p["highlight"])
    base = _ass_color(p["primary"])
    pos = f"\\an5\\pos({x},{ypx})"
    for ci, ch in enumerate(chunks):
        c_start = ch[0]["start"]
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else duration
        c_end = min(nxt, ch[-1]["end"] + 0.25, duration)
        if c_end - c_start < 0.08:
            continue
        toks = [w["word"].upper() if p["uppercase"] else w["word"] for w in ch]
        toks = [_esc(t) for t in toks]
        toks = _wrap(toks, max(10, p["max_chars"] * 2 // 3))
        emph = [bool(EMPHASIS.match(re.sub(r"[^\w$%]", "", w["word"]))) for w in ch]
        if p["highlight_mode"] == "word":
            for wi, w in enumerate(ch):
                s = c_start if wi == 0 else w["start"]
                e = ch[wi + 1]["start"] if wi + 1 < len(ch) else c_end
                if e - s < 0.02:
                    continue
                parts = []
                for ti, t in enumerate(toks):
                    col = hl if ti == wi else base
                    parts.append(f"{{\\c{col}}}{t}")
                anim = "\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)" if (p["pop"] and wi == 0) else ""
                events.append((s, e, f"{{{pos}{anim}}}" + " ".join(parts)))
        else:
            parts = []
            for t, is_emph in zip(toks, emph):
                col = hl if (p["highlight_mode"] == "keywords" and is_emph) else base
                parts.append(f"{{\\c{col}}}{t}")
            anim = "\\fscx90\\fscy90\\t(0,100,\\fscx100\\fscy100)" if p["pop"] else "\\fad(60,60)"
            events.append((c_start, c_end, f"{{{pos}{anim}}}" + " ".join(parts)))
    lines = header + [f"Dialogue: 1,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{t}" for s, e, t in events]
    hook_info = None
    if hook and hook.get("text"):
        hy = int(out_h * hook_position(layout, y, p["size"]))
        txt = _esc(hook["text"])[:60]
        hd = min(float(hook.get("duration", 2.5)), duration)
        lines.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(hd)},Hook,,0,0,0,,"
                     f"{{\\an5\\pos({x},{hy})\\fad(120,200)}}{txt}")
        hook_info = {"text": txt, "y": hy / out_h, "duration": hd}
    info = {"preset": preset_name, "font": font, "font_size": size, "position_y": round(y, 4),
            "position_x": round(x / out_w, 4), "events": len(events), "chunks": len(chunks),
            "first": events[0][0] if events else None, "last": events[-1][1] if events else None,
            "hook": hook_info, "safe_zone": [SAFE_LEFT, SAFE_TOP, SAFE_RIGHT, SAFE_BOTTOM]}
    return "\n".join(lines) + "\n", info


def write_captions(path: Path, words: list[dict], out_w: int, out_h: int, duration: float, preset: str,
                   layout: dict, overrides: dict | None = None, hook: dict | None = None) -> dict:
    text, info = build_ass(words, out_w, out_h, duration, preset, layout, overrides, hook)
    atomic_write_text(path, text)
    info["path"] = str(path)
    return info


def ass_filter(path: Path, fontsdir: str | None = None) -> str:
    """Escape a path for use inside an FFmpeg filtergraph."""
    p = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    f = f"ass='{p}'"
    if fontsdir:
        fd = str(fontsdir).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        f += f":fontsdir='{fd}'"
    return f
