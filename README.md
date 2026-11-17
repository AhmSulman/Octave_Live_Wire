# Octave Live Wire

**A browser-based music toolkit: audio analysis, instruments, a backing-track studio, and a live Python music-coding pad.**

🔗 **Live:** [octave-live-wire.vercel.app](https://octave-live-wire.vercel.app)

![Django](https://img.shields.io/badge/Django_5.2-092E20?style=flat-square&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![librosa](https://img.shields.io/badge/librosa-audio_DSP-4B8BBE?style=flat-square)
![Vercel](https://img.shields.io/badge/Vercel-serverless-000?style=flat-square&logo=vercel&logoColor=white)

---

## What's inside

| Tool | Route | What it does |
|---|---|---|
| **Media Player & Analyser** | `/media-player/` | Upload a track and get its tempo, key and waveform, computed server-side with librosa |
| **Piano Learner** | `/piano/` | Playable keyboard built from real sampled piano notes |
| **Guitar Fretboard** | `/guitar/` | Scale and note visualiser across the neck, with audio playback |
| **Backing Track Studio** | `/backing-track/` | Drum sequencer plus chord-progression builder, with an auto-compose API |
| **Pad** | `/pad/` | TunePad-style Python music-coding environment: Monaco editor, multi-track, piano roll |

## Architecture

```
octave_live_wire/         Django project config (settings, urls, wsgi)
backing_track_creator/    Four music tools + JSON API
  audio_analyser.py       librosa-based tempo / key / waveform analysis
  views.py                Page views and API endpoints
pad/                      Python music-coding environment (run_code endpoint)
```

**API endpoints:** `api/analyze/` · `api/fretboard/` · `api/compose/` · `api/contact/` · `pad/run/`

The whole app runs as **one Python serverless function on Vercel**. Every request routes through `wsgi.py`. The Lambda size limit is raised to 250 MB to fit the scientific audio stack (librosa, NumPy, SciPy, matplotlib). Static assets are served with WhiteNoise.

## Run locally

```bash
git clone https://github.com/AhmSulman/Octave_Live_Wire.git
cd Octave_Live_Wire
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set SECRET_KEY, DEBUG=True for local dev
python manage.py migrate
python manage.py runserver
```

Tests: `python manage.py test backing_track_creator`

## Deploy

`build_files.sh` installs dependencies and runs `collectstatic` during the Vercel build. `vercel.json` handles routing. Set the variables from `.env.example` in the Vercel dashboard.

---

Built by [Ahmed Salman (Maan)](https://github.com/AhmSulman)
