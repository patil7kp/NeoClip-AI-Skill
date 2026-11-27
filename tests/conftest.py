"""Shared fixtures: an isolated state dir per test and small synthetic videos (generated with FFmpeg).

No network, no Whisper download: transcripts come from generated .srt files.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")

LINES = [
    "Hello everyone and welcome back to the show.",
    "So basically this is the story of what happened.",
    "No way! That was insane, let's go!",
    "I can't believe he did that, haha.",
    "Honestly I love this part of the game.",
    "Wait, what? Are you serious?",
    "And then we won the whole thing.",
    "Here's why most people get this wrong.",
]


def _ts(x: float) -> str:
    h, m, s = int(x // 3600), int(x % 3600 // 60), x % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def make_srt(path: Path, duration: float, gap_every: int = 4) -> Path:
    out, i, t = [], 1, 1.0
    while t + 2.2 < duration - 0.5:
        line = LINES[(i - 1) % len(LINES)]
        out.append(f"{i}\n{_ts(t)} --> {_ts(t + 2.2)}\n{line}\n")
        t += 2.2 + (1.8 if i % gap_every == 0 else 0.3)
        i += 1
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def make_video(path: Path, duration: float = 60, size: str = "320x180", audio: bool = True,
               letterbox: bool = False) -> Path:
    vf = "testsrc2=s={}:r=30:d={}".format(size, duration)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf]
    if audio:
        # speech-like tone with true silences every 10 s and a loud "reaction" every 15 s
        cmd += ["-f", "lavfi", "-i", f"anoisesrc=d={duration}:c=pink:a=0.3:r=48000",
                "-filter_complex",
                "[1:a]volume='if(lt(mod(t,10),1.5),0.0,if(between(mod(t,15),9,10),1.0,0.15))':eval=frame[a]",
                "-map", "0:v", "-map", "[a]", "-c:a", "aac"]
    if letterbox:
        cmd += ["-vf", "pad=iw:ih*2:0:ih/2:black"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-t", str(duration), str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("YT_SHORTS_STATE_DIR", str(state))
    monkeypatch.setenv("YT_SHORTS_QUIET", "1")
    monkeypatch.delenv("YT_SHORTS_AI_COMMAND", raising=False)
    return state


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    d = tmp_path_factory.mktemp("media")
    talk = make_video(d / "talk.mp4", 120)
    srt = make_srt(d / "talk.srt", 120)
    silent = make_video(d / "silent.mp4", 8, audio=False)
    return {"dir": d, "talk": talk, "srt": srt, "silent": silent}


@pytest.fixture
def small_cfg(tmp_path):
    return {"resolution": "180x320", "output_root": str(tmp_path / "YouTube_Shorts"), "preset": "ultrafast",
            "crf": 28, "audio_bitrate": "96k"}
