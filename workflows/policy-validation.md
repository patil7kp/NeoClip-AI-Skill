# Workflow: policy validation

1. **Before processing:** confirm rights (the engine enforces this). For non-owned sources, tell the user up front
   about reused-content monetization rules and Content ID.
2. **Policy freshness:** if any result has `policy_review_due: true`, or the user asks about monetization or
   policy, fetch the official pages in `references/youtube-policies.md` and check them for changes. Mention
   anything that changed. Update `POLICY_LAST_VERIFIED` in `scripts/policy_checker.py` only if you maintain
   the skill.
3. **After rendering:** for each clip, read `risk.overall` and `risk.items`.
   - High: explain it plainly with timestamps, and recommend fixing it (trim, mute, bleep), skipping it, or a
     manual review before upload.
   - Medium: explain it and suggest a remedy.
   - Low: mention it briefly.
4. **Metadata:** make sure each title and description matches the clip. Remove clickbait or misleading claims.
5. **Wording:** "potential risk", "may be claimed", "could be age-restricted". Never "safe", "guaranteed",
   or "won't be claimed".
6. Full risk JSON per clip: `~/.neoclip-ai/work/<video>/jobs/<job>/<clip_id>.risk.json`.
