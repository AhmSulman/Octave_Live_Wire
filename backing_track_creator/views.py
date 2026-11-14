from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import AudioUpload

# ---------------------------------------------------------------------------
# Guitar tunings (no DB needed)
# ---------------------------------------------------------------------------
GUITAR_TUNINGS = {
    "standard": {"display": "Standard (E A D G B e)", "strings": ["E2", "A2", "D3", "G3", "B3", "E4"], "difficulty": "Beginner"},
    "drop_d":   {"display": "Drop D (D A D G B e)",   "strings": ["D2", "A2", "D3", "G3", "B3", "E4"], "difficulty": "Beginner"},
    "drop_c":   {"display": "Drop C (C G C F A d)",   "strings": ["C2", "G2", "C3", "F3", "A3", "D4"], "difficulty": "Intermediate"},
    "dadgad":   {"display": "DADGAD",                  "strings": ["D2", "A2", "D3", "G3", "A3", "D4"], "difficulty": "Intermediate"},
    "open_g":   {"display": "Open G (D G D G B d)",   "strings": ["D2", "G2", "D3", "G3", "B3", "D4"], "difficulty": "Intermediate"},
    "open_e":   {"display": "Open E (E B E Ab B e)",  "strings": ["E2", "B2", "E3", "Ab3", "B3", "E4"], "difficulty": "Advanced"},
}

NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}


def _note_to_midi(note_str: str) -> int:
    note_str = note_str.strip()
    for sharp, flat in SHARP_TO_FLAT.items():
        note_str = note_str.replace(sharp, flat)

    if len(note_str) >= 3 and note_str[1] == "b":
        name = note_str[:2]
        octave = int(note_str[2:])
    else:
        name = note_str[0]
        octave = int(note_str[1:])

    return (octave + 1) * 12 + NOTE_NAMES.index(name)


def _midi_to_note(midi: int) -> str:
    return NOTE_NAMES[midi % 12] + str(midi // 12 - 1)


def _media_root() -> Path:
    mr = getattr(settings, "MEDIA_ROOT", None)
    return Path(mr) if mr else Path.cwd() / "media"


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------
@ensure_csrf_cookie
@require_GET
def home_view(request: HttpRequest) -> HttpResponse:
    return render(request, "backing_track_creator/home.html")


@ensure_csrf_cookie
@require_GET
def media_player_view(request: HttpRequest) -> HttpResponse:
    recent = AudioUpload.objects.order_by("-uploaded_at")[:10]
    return render(request, "backing_track_creator/media_player.html", {"recent_files": recent})


@ensure_csrf_cookie
@require_GET
def piano_learner_view(request: HttpRequest) -> HttpResponse:
    return render(request, "backing_track_creator/piano_learner.html")


@ensure_csrf_cookie
@require_GET
def guitar_fretboard_view(request: HttpRequest) -> HttpResponse:
    tuning_key = request.GET.get("tuning", "standard")
    if tuning_key not in GUITAR_TUNINGS:
        tuning_key = "standard"
    current = {"name": tuning_key, **GUITAR_TUNINGS[tuning_key]}
    tunings = [{"name": k, **v} for k, v in GUITAR_TUNINGS.items()]
    return render(request, "backing_track_creator/guitar_fretboard.html", {
        "tunings": tunings,
        "current_tuning": current,
    })


@ensure_csrf_cookie
@require_GET
def backing_track_view(request: HttpRequest) -> HttpResponse:
    return render(request, "backing_track_creator/backing_track.html")


# Public profiles shown on the contact page (and linked from the portfolio).
PUBLIC_LINKS = [
    {"name": "Portfolio", "handle": "ahmed-salman.vercel.app", "url": "https://ahmed-salman.vercel.app/", "icon": "🌐"},
    {"name": "GitHub", "handle": "@AhmSulman", "url": "https://github.com/AhmSulman", "icon": "💻"},
    {"name": "LinkedIn", "handle": "ahmed-salman-maan", "url": "https://www.linkedin.com/in/ahmed-salman-maan", "icon": "💼"},
    {"name": "YouTube", "handle": "@Ahm3dSulman", "url": "https://www.youtube.com/@Ahm3dSulman", "icon": "▶️"},
]


@ensure_csrf_cookie
@require_GET
def contact_view(request: HttpRequest) -> HttpResponse:
    return render(request, "backing_track_creator/contact.html", {"links": PUBLIC_LINKS})


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
_CONTACT_LIMITS = {"name": 100, "email": 254, "subject": 150, "message": 5000}


@require_http_methods(["POST"])
def send_contact(request: HttpRequest) -> JsonResponse:
    """Deliver a contact-form message to settings.CONTACT_EMAIL over SMTP."""
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    # Honeypot: real visitors never see or fill the "website" field.
    if str(data.get("website", "")).strip():
        return JsonResponse({"success": True})

    fields = {k: str(data.get(k, "")).strip() for k in _CONTACT_LIMITS}
    errors = {}
    if not fields["name"]:
        errors["name"] = "Please enter your name."
    if not fields["message"] or len(fields["message"]) < 10:
        errors["message"] = "Please write a message (at least 10 characters)."
    try:
        validate_email(fields["email"])
    except ValidationError:
        errors["email"] = "Please enter a valid email address."
    for k, limit in _CONTACT_LIMITS.items():
        if len(fields[k]) > limit:
            errors[k] = f"Too long (max {limit} characters)."
    # Header-injection guard for anything that ends up in a mail header.
    for k in ("name", "email", "subject"):
        if "\n" in fields[k] or "\r" in fields[k]:
            errors[k] = "Invalid characters."
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    recipient = getattr(settings, "CONTACT_EMAIL", "")
    backend = getattr(settings, "EMAIL_BACKEND", "")
    smtp_ready = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
    if not recipient or (not smtp_ready and "smtp" in backend.lower()):
        return JsonResponse({
            "success": False,
            "error": "The contact form isn't set up yet. Please reach me through one of the links on this page.",
        }, status=503)

    subject = fields["subject"] or "New message"
    body = (
        f"From: {fields['name']} <{fields['email']}>\n"
        "Sent via the Octave Live Wire contact page\n"
        f"{'-' * 48}\n\n{fields['message']}\n"
    )
    msg = EmailMessage(
        subject=f"[Octave Live Wire] {subject}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        reply_to=[f"{fields['name']} <{fields['email']}>"],
    )
    try:
        msg.send(fail_silently=False)
    except Exception:
        return JsonResponse({
            "success": False,
            "error": "Sorry, the message couldn't be sent right now. Please try again or use one of the links on this page.",
        }, status=502)
    return JsonResponse({"success": True})
@require_GET
def get_fretboard_data(request: HttpRequest) -> JsonResponse:
    tuning_key = request.GET.get("tuning", "standard")
    if tuning_key not in GUITAR_TUNINGS:
        tuning_key = "standard"

    tuning = GUITAR_TUNINGS[tuning_key]
    try:
        frets = int(request.GET.get("frets", 17))
    except (TypeError, ValueError):
        frets = 17
    frets = max(1, min(frets, 36))  # clamp: no crash, no unbounded response
    strings_data = []

    for open_note in reversed(tuning["strings"]):
        base_midi = _note_to_midi(open_note)
        frets_out = [
            {"fret": i, "note": _midi_to_note(base_midi + i)}
            for i in range(frets + 1)
        ]
        strings_data.append({"open_note": open_note, "frets": frets_out})

    return JsonResponse({
        "success": True,
        "tuning": tuning["display"],
        "tuning_name": tuning_key,
        "frets": frets,
        "strings": strings_data,
    })


MAX_AUDIO_BYTES = 30 * 1024 * 1024  # 30 MB
ALLOWED_AUDIO_EXTS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".aif"})


@require_http_methods(["POST"])
def analyze_audio(request: HttpRequest) -> JsonResponse:
    up = request.FILES.get("file")
    if not up:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    # Reject oversized or non-audio uploads before writing to disk / decoding.
    if up.size and up.size > MAX_AUDIO_BYTES:
        return JsonResponse(
            {"success": False, "error": "File too large (max 30 MB)."}, status=413
        )
    safe_name = Path(up.name).name
    if Path(safe_name).suffix.lower() not in ALLOWED_AUDIO_EXTS:
        return JsonResponse(
            {"success": False, "error": "Unsupported file type. Upload an audio file."},
            status=415,
        )

    upload_dir = _media_root() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{safe_name}"

    written = 0
    with dest.open("wb") as f:
        for chunk in up.chunks():
            written += len(chunk)
            if written > MAX_AUDIO_BYTES:  # guard streamed/chunked uploads too
                f.close()
                dest.unlink(missing_ok=True)
                return JsonResponse(
                    {"success": False, "error": "File too large (max 30 MB)."},
                    status=413,
                )
            f.write(chunk)

    try:
        from .audio_analyser import AudioAnalyser
        result = AudioAnalyser.analyze_file(str(dest))

        audio_obj = AudioUpload.objects.create(
            file_name=safe_name,
            file_path=str(dest),
            file_size=dest.stat().st_size,
            bpm=result["bpm"],
            key_detected=result["key"],
            is_minor=result["is_minor"],
            duration=result.get("duration"),
        )
        audio_obj.set_waveform(result["waveform_data"])
        audio_obj.save()

        return JsonResponse({
            "success": True,
            "bpm": result["bpm"],
            "key": result["key"],
            "is_minor": result["is_minor"],
            "best_major": result.get("best_major", ""),
            "best_minor": result.get("best_minor", ""),
            "relative_key": result.get("relative_key", ""),
            "confidence": result.get("confidence", 0),
            "top_keys": result.get("top_keys", {}),
            "duration": result.get("duration"),
            "waveform": result["waveform_data"],
            "waveform_image": result.get("waveform_image", ""),
        })
    except Exception:
        # Don't leak internal/library error details to the client.
        return JsonResponse(
            {"success": False, "error": "Could not analyze this file. Please try another audio file."},
            status=500,
        )
    finally:
        # The upload is only needed during analysis; don't leave it on disk.
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass


CHORD_PROGRESSIONS = {
    "rock": {
        "major": {
            "C": ["C", "Am", "F", "G"],
            "D": ["D", "Bm", "G", "A"],
            "E": ["E", "C#m", "A", "B"],
            "G": ["G", "Em", "C", "D"],
            "A": ["A", "F#m", "D", "E"],
        },
        "minor": {
            "A": ["Am", "F", "C", "G"],
            "E": ["Em", "C", "G", "D"],
            "D": ["Dm", "Bb", "F", "C"],
            "B": ["Bm", "G", "D", "A"],
        },
    },
    "jazz": {
        "major": {
            "C": ["Cmaj7", "Am7", "Dm7", "G7"],
            "F": ["Fmaj7", "Dm7", "Gm7", "C7"],
            "G": ["Gmaj7", "Em7", "Am7", "D7"],
        },
        "minor": {
            "A": ["Am7", "D7", "Gmaj7", "Cmaj7"],
            "D": ["Dm7", "G7", "Cmaj7", "Fmaj7"],
        },
    },
    "blues": {
        "major": {
            "A": ["A7", "D7", "A7", "E7"],
            "E": ["E7", "A7", "E7", "B7"],
            "G": ["G7", "C7", "G7", "D7"],
        },
        "minor": {
            "A": ["Am7", "Dm7", "Am7", "Em7"],
        },
    },
    "pop": {
        "major": {
            "C": ["C", "G", "Am", "F"],
            "G": ["G", "D", "Em", "C"],
            "D": ["D", "A", "Bm", "G"],
        },
        "minor": {
            "A": ["Am", "C", "G", "F"],
            "E": ["Em", "G", "D", "A"],
        },
    },
    "indie": {
        "major": {
            "C": ["C", "F", "Am", "G"],
            "G": ["G", "C", "Em", "D"],
        },
        "minor": {
            "A": ["Am", "Em", "F", "G"],
            "D": ["Dm", "Am", "Bb", "C"],
        },
    },
}


@require_http_methods(["POST"])
def auto_compose(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            payload = {}
        genre = str(payload.get("genre", "rock")).lower()
        key = str(payload.get("key", "A"))
        tonality = str(payload.get("tonality", "minor"))

        genre_data = CHORD_PROGRESSIONS.get(genre, CHORD_PROGRESSIONS["rock"])
        tonality_data = genre_data.get(tonality, genre_data.get("major", {}))

        if key in tonality_data:
            chords = tonality_data[key]
        else:
            chords = list(tonality_data.values())[0] if tonality_data else ["Am", "F", "C", "G"]

        scale_notes_map = {
            "major": ["C", "D", "E", "F", "G", "A", "B"],
            "minor": ["A", "B", "C", "D", "E", "F", "G"],
        }
        scale = scale_notes_map.get(tonality, scale_notes_map["minor"])

        melody = []
        octave = 4
        for _ in range(16):
            note = random.choice(scale)
            melody.append(f"{note}{octave}")

        return JsonResponse({
            "success": True,
            "chords": chords,
            "melody": melody,
            "genre": genre,
            "key": key,
            "tonality": tonality,
        })
    except Exception:
        return JsonResponse({"success": False, "error": "Could not compose. Please try again."}, status=400)
