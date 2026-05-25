# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Octave Live Wire is a Django 5.2 web app — a music tools suite with five browser-based instruments/tools deployed on Vercel as a Python serverless function.

## Commands

### Local Development

```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Run the development server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Create migrations after model changes
python manage.py makemigrations

# Collect static files (required before deploying)
python manage.py collectstatic --noinput
```

> **Windows note**: Use the `Bash` tool (not PowerShell) to run `collectstatic` — PowerShell exits with code 1 silently on this project. Example: `.venv/Scripts/python.exe manage.py collectstatic --noinput 2>&1 | tail -10`

### Running Tests

```bash
python manage.py test backing_track_creator
python manage.py test backing_track_creator.tests.SomeTestClass  # single test class
```

### Vercel Deployment

The `build_files.sh` script runs during Vercel build: it installs requirements then runs `collectstatic`. Deployment is configured via `vercel.json` — all requests route through `octave_live_wire/wsgi.py`. The Lambda size limit is set to 250 MB due to heavy audio libraries (librosa, numpy, scipy, matplotlib).

## Architecture

### Django App Structure

There are two Django apps: `backing_track_creator` (four music tools) and `pad` (Python music coding environment). The project config package is `octave_live_wire/`.

```text
octave_live_wire/          # Django project config (settings, urls, wsgi, asgi)
backing_track_creator/     # App containing the four classic music tools
  views.py                 # All page views + API endpoints
  models.py                # AudioUpload model
  audio_analyser.py        # AudioAnalyser class (librosa-based)
  urls.py                  # URL patterns (app_name = "backing_track_creator")
  templates/backing_track_creator/
    home.html              # Landing page (5-tool grid)
    media_player.html      # Audio upload & analysis tool
    piano_learner.html     # Piano keyboard interface
    guitar_fretboard.html  # Fretboard visualizer (WAV audio + Phrygian scale)
    backing_track.html     # Drum sequencer + chord progression studio
pad/                       # Python music coding environment (TunePad-inspired)
  views.py                 # pad_view + run_code API endpoint
  urls.py                  # app_name = "pad"; "" → pad_view, "run/" → run_code
  templates/pad/
    pad.html               # Full Pad UI: Monaco editor, multi-track, piano roll
DrumsSample/               # Drum sample audio files served as static assets
Piano/                     # Piano sample WAV files (Piano.pp.<Note><Octave>.wav)
staticfiles/               # Output of collectstatic — do not edit directly
```

### URL Map

| URL | View | App | Template |
| --- | ---- | --- | -------- |
| `/` | `home_view` | backing_track_creator | `home.html` |
| `/media-player/` | `media_player_view` | backing_track_creator | `media_player.html` |
| `/piano/` | `piano_learner_view` | backing_track_creator | `piano_learner.html` |
| `/guitar/` | `guitar_fretboard_view` | backing_track_creator | `guitar_fretboard.html` |
| `/backing-track/` | `backing_track_view` | backing_track_creator | `backing_track.html` |
| `/api/analyze/` | `analyze_audio` (POST) | backing_track_creator | — |
| `/api/fretboard/` | `get_fretboard_data` (GET) | backing_track_creator | — |
| `/api/compose/` | `auto_compose` (POST) | backing_track_creator | — |
| `/pad/` | `pad_view` | pad | `pad.html` |
| `/pad/run/` | `run_code` (POST) | pad | — |

### Audio Analysis Pipeline (`/api/analyze/`)

1. File is uploaded and saved to `MEDIA_ROOT/uploads/` with a timestamp-prefixed filename.
2. `AudioAnalyser.analyze_file()` loads the file with librosa, extracts BPM (beat tracking), key (chroma + Krumhansl-Schmuckler profiles), duration, and a 1000-sample waveform array.
3. A waveform PNG is rendered with matplotlib and returned as a base64 data URI.
4. An `AudioUpload` record is created in the database storing metadata and waveform JSON.

### Key Detection Logic

`AudioAnalyser` uses Krumhansl-Schmuckler key profiles. Chromagram mean is computed over the entire file, normalized, then dot-producted against all 24 major/minor rotated profiles. The highest-scoring key wins. Note names are stored in flat notation (C#→Db, etc.) throughout `views.py`.

### Guitar Fretboard Data (`/api/fretboard/`)

All six tunings are defined as a static dict in `views.py` (`GUITAR_TUNINGS`). Notes are computed on the fly using MIDI arithmetic: `_note_to_midi()` and `_midi_to_note()` convert between note strings and integer MIDI values. The view returns a JSON array of strings, each with fret-by-fret note labels.

Supported scales: chromatic, major, minor, pentatonic major, pentatonic minor, blues, dorian, **phrygian**, mixolydian, harmonic minor, whole tone.

**Audio playback**: The fretboard uses a two-stage WAV sampler (no oscillator). On page load, Piano WAV `ArrayBuffer`s are fetched without an AudioContext. On first user click, they are decoded into `AudioBuffer`s and cached. Notes play via `AudioBufferSourceNode` with pitch-shifting (`playbackRate = 2^(semitones/12)`) for any missing octave. Falls back to an oscillator only if all WAV attempts fail.

### Backing Track / Auto Compose (`/api/compose/`)

`CHORD_PROGRESSIONS` in `views.py` is a static nested dict keyed by genre → tonality → root key. The `auto_compose` endpoint picks a matching progression and generates a random 16-note melody from the scale. No audio synthesis happens server-side — the browser handles playback using the `Piano/` and `DrumsSample/` WAV files via the Web Audio API.

### Pad — Python Music Coding Environment (`/pad/`)

Pad is a TunePad-inspired browser IDE where users write Python to compose music. It is **not** a direct clone — the core concept (Python → music) is shared, but Pad adds substantial original functionality.

#### How it works

The browser POSTs `{ bpm, root, scale, tracks: [{code, armed, instrument}] }` to `/pad/run/`. Django executes each armed track's Python in a sandboxed `_MusicContext`, merges the resulting events sorted by time, and returns them as JSON. Tone.js in the browser schedules and plays the events.

#### Execution sandbox (`pad/views.py`)

- AST scan blocks `import`, `exec`, `eval`, `compile`, `open`, `__import__`
- Restricted `__builtins__` (math, random, range, etc. allowed)
- 8-second thread timeout per execution; 1500-event cap per run
- Each track gets its own `_MusicContext` with an independent time cursor

#### `_MusicContext` API (callable from user Python)

##### Playback

| Function | Description |
| -------- | ----------- |
| `play_note(step_or_note, duration=0.5, velocity=90)` | Play a note; advances time. Accepts int scale-degree OR string like `'G4'`, `'Bb3'` |
| `play_chord(steps, duration=1, velocity=90)` | Play multiple notes simultaneously; advances time |
| `play_drum(drum=0, velocity=90)` | Trigger a drum sound; does NOT advance time |
| `rest(duration=1)` | Silence; advances time |

##### Creative functions

| Function | Description |
| -------- | ----------- |
| `strum(steps, duration=1, velocity=90, gap=0.04)` | Staggered chord (like a guitar strum) |
| `arpeggio(steps, note_duration=0.25, style='up', repeats=1)` | Arpeggiate steps up/down/random/pingpong |
| `echo(step_or_note, duration, velocity, times=3, decay=0.55, gap_beats=0.5)` | Decaying repeat echoes |
| `trill(step_a, step_b, total_duration=1, note_duration=0.125)` | Rapid alternation between two notes |

##### Control

| Function | Description |
| -------- | ----------- |
| `set_bpm(bpm)` | Change tempo mid-track |
| `set_instrument(name)` | Switch instrument: `piano`, `synth`, `pad`, `bass`, `pluck` |
| `set_scale(root=None, scale_type=None)` | Override global scale from code |
| `transpose(semitones)` | Shift all subsequent notes by semitones |
| `humanize(timing=0.02, velocity=10)` | Add random timing/velocity jitter |
| `rewind(beats=None)` | Jump back N beats (or to start if None) |
| `set_time(beats)` | Jump to absolute beat position |
| `get_bpm()` / `current_beat()` | Read current state |

#### Named duration constants

Available as globals in user code:

| Constant | Alias | Beats |
| -------- | ----- | ----- |
| `whole_note` | `W` | 4.0 |
| `half_note` | `H` | 2.0 |
| `quarter_note` | `Q` | 1.0 |
| `eighth_note` | `E` | 0.5 |
| `sixteenth_note` | `S` | 0.25 |
| `thirty_second` | — | 0.125 |
| `dotted_whole` | — | 6.0 |
| `dotted_half` | — | 3.0 |
| `dotted_quarter` | — | 1.5 |
| `dotted_eighth` | — | 0.75 |
| `triplet_quarter` | — | 0.667 |
| `triplet_eighth` | — | 0.333 |
| `triplet_sixteenth` | — | 0.167 |

#### Scales (available in UI and `set_scale()`)

chromatic, major, minor, pentatonic_major, pentatonic_minor, blues, dorian, phrygian, mixolydian, harmonic_minor, whole_tone

#### Frontend (`pad/templates/pad/pad.html`)

- Three-column CSS Grid layout: `270px` docs panel | `1fr` editor+piano roll | `260px` console
- **Monaco Editor** (CDN, `monaco-editor@0.44.0`) with Python syntax and custom autocomplete for all music functions
- **Tone.js 14** for audio: `Tone.Sampler` (piano WAVs), `Tone.PolySynth` (synth/pad/bass), `Tone.PluckSynth`, `Tone.MembraneSynth`, `Tone.NoiseSynth`, `Tone.MetalSynth`; global Reverb + Chorus chain
- **Piano roll canvas**: notes as colored rectangles (Y = MIDI pitch, X = time), drum markers at bottom row, animated playhead via `requestAnimationFrame`
- Up to 4 tracks; each independently arm-able, with its own Monaco instance and instrument selector
- Docs panel: collapsible accordion — Functions, Duration constants, Note reference, Time model, 10 code examples with "Use" buttons

### Static Audio Assets

- `Piano/` — individual piano WAV samples named `Piano.pp.<Note><Octave>.wav` (e.g., `Piano.pp.C4.wav`). Used by guitar fretboard (direct Web Audio API), piano learner, backing track studio, and Pad (via Tone.Sampler).
- `DrumsSample/` — Focusrite drum pack organized into subdirectories: `HEAVY/`, `INDIE/`, `ROCK/`, `SAMPLES/` and under `Samples/`: `Bass Loops`, `Drum Loops`, `Loops`, `Music Loops`, `One Shots`, `Percussion Loops`, `Waveforms`.
- `STATICFILES_DIRS` includes `("Piano", BASE_DIR / "Piano")` so Piano WAVs are served at `/static/Piano/Piano.pp.{Note}{Octave}.wav`.

### Vercel / Production Considerations

- **Filesystem is ephemeral**: `MEDIA_ROOT` is `/tmp/media` on Vercel. Uploaded audio files and the SQLite DB (`/tmp/db.sqlite3`) do not persist across Lambda invocations. For durable storage, migrate to S3/Cloudinary (media) and a hosted Postgres (DB).
- **Static files**: Served by WhiteNoise (`CompressedManifestStaticFilesStorage`). Hashed filenames are written to `staticfiles/staticfiles.json` at build time — always run `collectstatic` before deploying.
- **SSL**: Vercel terminates TLS at the edge. `SECURE_SSL_REDIRECT` must stay off to avoid redirect loops; `SECURE_PROXY_SSL_HEADER` is set for `X-Forwarded-Proto`.
- **CSRF**: All page views use `@ensure_csrf_cookie`. New Vercel deployment URLs must be added to `CSRF_TRUSTED_ORIGINS` or the `CSRF_TRUSTED_ORIGINS` env var.

### Frontend Patterns

All templates are self-contained single-file pages (inline CSS + JS, no build step, no external JS framework). They use Google Fonts (Orbitron + Space Grotesk) and vanilla Canvas API for animations. CSRF tokens are passed via the cookie set by `@ensure_csrf_cookie`; fetch calls to POST endpoints read `document.cookie` for the token. Exception: `pad.html` uses Monaco Editor from CDN and Tone.js from CDN — both loaded via `<script>` tags.
