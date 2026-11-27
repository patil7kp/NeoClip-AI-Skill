# Third-party components

NeoClip-AI-Skill (© 2026 Kiran Patil) uses the components below. **None of them are owned by the NeoClip-AI-Skill author.**
Each remains under its own license and copyright. NeoClip-AI-Skill does not bundle or redistribute them: they are
installed separately by the user (pip, a system package manager, or an explicit download command).
Check each project's current license before redistributing anything.

| Component | Used for | License (as published by the project) | Project |
|---|---|---|---|
| FFmpeg / ffprobe | decoding, editing, rendering, validation | LGPL-2.1+ (GPL-2.0+ for builds with GPL parts such as x264) | https://ffmpeg.org |
| x264 (libx264, via FFmpeg) | H.264 encoding | GPL-2.0+ | https://www.videolan.org/developers/x264.html |
| x265 (libx265, via FFmpeg, optional) | HEVC encoding | GPL-2.0+ | https://www.x265.org |
| libass (via FFmpeg) | caption rendering | ISC | https://github.com/libass/libass |
| OpenCV (opencv-python-headless) | frame analysis, face detection | Apache-2.0 (OpenCV 4.5+) | https://opencv.org |
| OpenCV Haar cascades | face detection (OpenCV < 5) | Intel License Agreement / BSD-style, shipped with OpenCV | https://github.com/opencv/opencv |
| YuNet face model (optional, `setup-models`) | face detection | MIT | https://github.com/opencv/opencv_zoo |
| NumPy | numerical analysis | BSD-3-Clause | https://numpy.org |
| faster-whisper | speech-to-text | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 (faster-whisper dependency) | model inference | MIT | https://github.com/OpenNMT/CTranslate2 |
| OpenAI Whisper models / openai-whisper (optional) | speech-to-text weights and code | MIT | https://github.com/openai/whisper |
| yt-dlp (optional) | YouTube metadata and download | Unlicense | https://github.com/yt-dlp/yt-dlp |
| pytest (development) | tests | MIT | https://pytest.org |
| jsonschema (development) | schema tests | MIT | https://github.com/python-jsonschema/jsonschema |
| Fonts (system: Montserrat, Inter, DejaVu, Arial…) | caption text | per font (e.g. SIL OFL for Montserrat and Inter) | user's system |

Other notes:
- Music used through `music_library.json` belongs to its rights holders under the license the user records.
- YouTube, Shorts and Content ID are trademarks or services of Google LLC. NeoClip-AI-Skill is not affiliated with
  or endorsed by Google or YouTube.
- AI agents that drive the skill (Claude, ChatGPT, Gemini, Cursor and others) are products of their respective
  owners.
