# Instrument Audition App + Numpy-Derived Harmonics — Design

Status: **approved, not yet implemented**
Date: 2026-08-09

## Why this doc exists

This directory (`Octave_live_wire`) has been moved on disk more than once, which
breaks continuity between Claude Code sessions. This spec is written so that
**opening this doc alone reconstructs full context** — what the project is,
what's broken, what's already decided, and what to do next — without needing
prior conversation history.

## Project context

Octave Live Wire is a Django project (`octave_live_wire/`) with several apps:

- `backing_track_creator/` — genre-based backing-track studio (drum sequencer +
  auto-generated chord progression + piano/guitar instrument pages):
  `backing_track.html`, `guitar_fretboard.html`, `piano_learner.html`,
  `media_player.html`, `home.html`.
- `pad/` — separate pad/synth tool (`pad.html`).
- Real recorded piano samples live at repo-root `Piano/Piano.pp.<note>.wav`
  (mapped as a static prefix `"Piano"` in `settings.py` → `STATICFILES_DIRS`),
  used by `guitar_fretboard.html` for sample playback with pitch-shift fallback
  to nearby octaves.
- `numpy`, `scipy`, `soundfile`, `librosa` are already in `requirements.txt`
  (used elsewhere for audio analysis / waveform generation), so no new backend
  dependency is needed for this work.
- Every template so far is fully self-contained (inline `<script>` blocks, no
  shared static JS files, no build step). This spec intentionally deviates
  from that convention once (see "Shared engine" below) because the
  alternative is copy-pasting the same synthesis formula into four files.

Prior standing preference (from user, established on the Bassist Bot project):
**avoid hardcoded data/sequences — build small parameter-driven generative
systems instead.** This spec follows that preference throughout.

## The larger initiative (3 sub-projects)

This spec covers **sub-project 1 only**. It exists inside a 3-part cleanup the
user requested in one sitting; the other two are queued, not designed yet:

1. **[This doc] Numpy-derived instrument harmonics + shared synth engine +
   one-by-one audition app.**
2. **Backing track generative chord progressions + multi-bar loop fix.**
   Diagnosed root cause (not yet fixed): `backing_track.html`'s sequencer
   hardcodes `totalSteps = 16` (exactly one bar). The chord-advance logic
   computes `barInProgression = Math.floor(step / stepsPerBar)`, but `step`
   resets to 0 every 16 steps (`advanceNote()`), so `barInProgression` is
   always 0 — the progression can never advance past chord #1. This is why
   playback "becomes more like playing 4 sec on loop" and why the bar counter
   doesn't reflect the real progression length: it's one bug, not two.
   Required fixes, per explicit user instructions:
   - Replace the hardcoded `CHORD_PROGRESSIONS` dict in
     `backing_track_creator/views.py` (fixed genre→tonality→key chord lists)
     with a generative progression algorithm (diatonic chord-building from
     scale degrees + genre-informed patterns) — "avoid hardcoding anything."
   - Make the sequencer loop span the full progression length instead of a
     fixed 1 bar, and derive `chordIdx` from a counter that keeps
     incrementing across the loop (e.g. `barCount`), not from `step` which
     wraps every bar.
   - User must be able to **manually edit/arrange the chords per bar**
     themselves after auto-generation, not just accept whatever the
     generator produces ("I should be able to adjust chords myself").
3. **Global resize/scroll CSS fix.** Window resizing is broken and no tab in
   the app can scroll. Not yet investigated — likely a shared layout/overflow
   issue rather than per-page, since the user says it affects "all tabs."

Do sub-projects 2 and 3 in that order after this one, each getting its own
brainstorm → spec → plan cycle. Don't conflate them with this spec's scope.

## Sub-project 1 scope

**In scope:**
- Measure real piano harmonic decay from `Piano/Piano.pp.*.wav` via numpy FFT
  (not a textbook physics formula — the user explicitly wants it derived from
  the real recordings already in the repo).
- Replace every hand-picked harmonic-amplitude table in the codebase with one
  shared, formula-driven synth engine parameterized by the numpy fit.
- Build a minimal "instrument lab" page: pick a synthesis method from a
  dropdown, play notes on a simple on-screen keyboard, hear **only** the
  selected method — no mixing, no side-by-side comparison (explicit user
  correction: "DUMMY APP SHOULD ONLY LET ME HEAR INSTRUMENTS CREATED WITH
  DIFFERENT METHODS ONE BY ONE").
- Delete `guitar_fretboard.html`'s crude 2-oscillator `playOscillatorFallback`
  in favor of the new shared engine as the no-sample fallback.

**Out of scope (explicitly deferred):** backing track chord progression/loop
bug, manual chord editing UI, resize/scroll CSS — all sub-project 2/3.

## Architecture

### 1. Analysis script (offline, run once by hand) — `scripts/analyze_piano_harmonics.py`

- Loads a handful of real notes spanning the piano's range (e.g. A1, A3, A5,
  A7 — bass/mid/treble) from `Piano/`.
- FFTs each with numpy, finds the fundamental, measures each partial's peak
  magnitude relative to the fundamental for harmonics 1–6 (or as many as
  clear the noise floor).
- Fits a power-law decay `amp(n) ≈ n^-p` via numpy least-squares in log
  space (`np.polyfit(log(n), log(amp), 1)`).
- Because real piano decay differs by register (bass rings with more
  overtones than treble), also fits `p` as a linear function of
  `log(fundamental_freq)`, so the final model is register-aware — this is
  still just 2–3 fitted constants, not a per-note table.
- Prints the fit plus an R² sanity check. The resulting constants are copied
  by hand into the JS engine below (this script is a dev-time tool, not part
  of the request/response cycle — the piano's physical harmonic decay doesn't
  change, so there's no need to re-run it at runtime).

### 2. Shared engine (new) — `static/js/instrument_engine.js`

- Core function `harmonicAmplitude(n, fundamentalFreq)` implementing the
  numpy-fit formula. This *is* the generative system replacing every
  hardcoded table in the project.
- A small preset layer on top: **Piano** (the directly-measured curve),
  **Bright**, **Soft** (parameter variations of the same measured curve —
  more/fewer harmonics, exponent scaling). Honesty constraint: only "Piano"
  is actually measured from real recordings; Bright/Soft must be documented
  in-code as derived variations, not implied to be separately-measured
  instruments, since no real organ/electric-piano recordings exist in this
  repo to analyze.
- First shared static JS file in the project — a deliberate, small deviation
  from the self-contained-template convention, justified because the
  alternative is duplicating the same formula across 4 templates.

### 3. Wiring (edits to existing files)

- `piano_learner.html` — `playNote()` calls the engine instead of using its
  hardcoded `harmonics = [{ratio:1,amp:1}, ...]` array.
- `backing_track.html` — `playPianoNote()`'s 3 hardcoded oscillator tables
  (acoustic/organ/electric, currently literal arrays of oscillator
  type/amp/ratio) become the 3 engine presets.
- `guitar_fretboard.html` — `playOscillatorFallback` function deleted;
  the no-sample-available fallback path calls the shared engine instead.

### 4. Audition app (new)

- New route + view + `backing_track_creator/templates/backing_track_creator/instrument_lab.html`.
- One dropdown with three choices:
  - **Old hardcoded baseline** — a frozen snapshot of the original hand-picked
    harmonic table, kept only for A/B comparison; not used anywhere in
    production anymore once the wiring above lands.
  - **Numpy-derived engine** — with a sub-choice for the Piano/Bright/Soft
    presets.
  - **Real WAV sample** — straight playback of `Piano/Piano.pp.*.wav`.
- One simple on-screen keyboard. Clicking a note plays it through **only**
  the currently selected method.

## Testing

- Analysis script prints the fit quality (R²) so the derived constants can be
  sanity-checked before being copied into the engine.
- Manual verification: use the audition lab itself to A/B the three methods
  by ear across low/mid/high notes.
- No new automated Django tests planned beyond a basic smoke test that the
  `instrument_lab` view returns 200.

## Open items carried into the implementation plan

- Exact URL path and app placement for `instrument_lab` (likely
  `backing_track_creator`, alongside the other instrument pages).
- Exact preset parameter values for Bright/Soft once the base Piano fit is in
  hand (depends on the actual numpy output).
