# Workflow: rendering

1. Resolution: the default is 2160×3840. Suggest `--resolution 1080x1920` for speed when the source is ≤ 1080p,
   and explain that 4K output from a 1080p source is upscaled, not native 4K.
2. Run `render --plan plan.json` (or `run`). Each clip renders to a temp file, gets validated, and is moved into
   the date folder only if it passes.
3. Read each clip's `validation.attempts`. If a fallback profile was used, mention it (for example "rendered without
   zoom effects after the first attempt failed validation").
4. Failures: `status: failed` with `error` and `hint`. Common causes are missing libass (`doctor`), disk space,
   or a corrupt source section. Fix it, then run `resume`.
5. Interrupted (closed terminal, crash): `resume` re-runs only the unfinished clips. Completed ones are skipped.
