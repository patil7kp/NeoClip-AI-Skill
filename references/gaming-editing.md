# Gaming editing

## Layout: `gaming_stack`
```
┌───────────────┐  ← facecam panel (default 36% of height; allowed range 20–45%)
│   streamer    │     crop is taken INSIDE the detected webcam box, centred on the face
├───captions────┤  ← captions sit on the seam: they cover neither the face nor the action
│               │
│   gameplay    │  ← gameplay panel (≥ 55%, default 64%), full source height,
│               │     follows on-screen action, centre-weighted and smoothed
└───────────────┘
```
- **Gameplay stays big.** The cam can't go above 45% of the height (`layout.cam_ratio`), so an enlarged
  facecam never hides the game.
- **The cam overlay is kept out of the gameplay panel** when possible (`avoid_cam_in_gameplay`).
- **Action tracking** uses the motion centroid, pulled toward the centre (`center_weight` 0.7) and
  held static within a shot unless the action moves a lot. This avoids seasick pans. FPS games keep
  the crosshair area. You can tune it with `layout.gameplay_zoom` (> 1 zooms into the action).
- **No facecam detected** (no webcam, or the face isn't visible): the engine falls back to full-height
  gameplay tracking (`subject_track`) and reports it in the clip warnings. It never invents a cam panel.
- **Cam at the bottom**: `templates set gaming-reaction layout.cam_position=bottom`.

## Syncing the play and the reaction
- The selection window opens about 7 s before the reaction peak, so the cause (the in-game event) is included.
- Pause removal is light (gaps > 1.2 s), and gaps containing loud game audio are never cut.
- Zooms punch into the **gameplay panel** at reaction spikes, which highlights the action at the moment it happens.

## Agent checklist for gaming clips
- Does the clip show what caused the reaction? If not, move `start` earlier.
- Is the HUD element that matters (score, kill feed, health) visible in the gameplay crop? If it sits at
  the far edge, consider `layout.gameplay_zoom=1.0` with a different `center_weight`, or pick another moment.
- Mention the game in the title and hashtags when you know it. Don't claim things that didn't happen
  ("world record") unless the clip shows them.
- Gameplay footage belongs to the streamer, and game music can trigger Content ID. Check `risk.items`.
