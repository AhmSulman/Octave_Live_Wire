import ast
import builtins as _builtins
import json
import threading

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

# ---------------------------------------------------------------------------
# Music theory constants
# ---------------------------------------------------------------------------
BASE_MIDI = 60          # step 0 = C4

_NOTE_SEMITONES: dict = {
    "C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5,
    "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11,
    "C#": 1, "D#": 3, "F#": 6, "G#": 8, "A#": 10,
}

SCALE_INTERVALS: dict = {
    "chromatic":        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues":            [0, 3, 5, 6, 7, 10],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "whole_tone":       [0, 2, 4, 6, 8, 10],
}

# Named durations in beats
DURATION_CONSTANTS: dict = {
    "whole_note": 4.0,
    "half_note": 2.0,
    "quarter_note": 1.0,
    "eighth_note": 0.5,
    "sixteenth_note": 0.25,
    "thirty_second": 0.125,
    "dotted_whole": 6.0,
    "dotted_half": 3.0,
    "dotted_quarter": 1.5,
    "dotted_eighth": 0.75,
    "triplet_quarter": 2.0 / 3.0,
    "triplet_eighth": 1.0 / 3.0,
    "triplet_sixteenth": 1.0 / 6.0,
    # short aliases
    "W": 4.0, "H": 2.0, "Q": 1.0, "E": 0.5, "S": 0.25,
}

# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------
MAX_EVENTS = 1500
EXEC_TIMEOUT = 8.0

_SAFE_BUILTIN_NAMES = [
    "range", "len", "int", "float", "str", "bool", "list", "dict", "tuple",
    "set", "abs", "round", "min", "max", "enumerate", "zip", "sum", "sorted",
    "reversed", "isinstance", "type", "map", "filter", "any", "all",
    "chr", "ord", "hex", "bin", "oct", "format", "iter", "next",
    "pow", "divmod",
]

_BLOCKED_CALLS = frozenset([
    "exec", "eval", "compile", "open", "__import__",
    "input", "breakpoint", "exit", "quit",
])


def _check_ast(code: str):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "import is not allowed — use the built-in music functions"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BLOCKED_CALLS:
                return f"'{node.func.id}()' is not allowed"
    return None


# ---------------------------------------------------------------------------
# Music context
# ---------------------------------------------------------------------------
class _TooManyEvents(Exception):
    pass


class _MusicContext:
    """
    Captures music function calls and converts them to timed events.

    Time model
    ----------
    All times are in seconds internally.  User-facing functions accept *beats*
    and convert with the current BPM.

    Scale model
    -----------
    play_note(step) maps step → MIDI using the active scale + root.
    step 0 is always the root note at octave 4.
    Positive steps go up, negative go down.
    Alternatively pass a note-name string: play_note('A4').
    """

    def __init__(self, bpm=120.0, root="C", scale="chromatic", instrument="piano"):
        self.events: list = []
        self._time: float = 0.0
        self._bpm: float = float(bpm)
        self._root: str = root
        self._scale: str = scale if scale in SCALE_INTERVALS else "chromatic"
        self._instrument: str = instrument
        self._transpose: int = 0          # semitone offset applied to all notes
        self._humanize_t: float = 0.0     # max timing jitter in seconds
        self._humanize_v: int = 0         # max velocity jitter
        import random as _r
        self._rng = _r.Random()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _beats_to_sec(self, beats: float) -> float:
        return float(beats) * (60.0 / self._bpm)

    def _name_to_midi(self, name: str) -> int:
        """Parse a note name like 'E4', 'Bb3', 'C#5' into a MIDI number."""
        name = name.strip()
        if len(name) >= 2 and name[1] in ("#", "b"):
            letter, rest = name[:2], name[2:]
        else:
            letter, rest = name[0], name[1:]
        octave = int(rest) if rest else 4
        semitone = _NOTE_SEMITONES.get(letter, 0)
        return max(0, min(127, semitone + (octave + 1) * 12 + self._transpose))

    def _step_to_midi(self, step: int) -> int:
        intervals = SCALE_INTERVALS.get(self._scale, SCALE_INTERVALS["chromatic"])
        n = len(intervals)
        d = int(step)
        if d >= 0:
            octave_shift = d // n
            deg = d % n
        else:
            octave_shift = -((-d - 1) // n + 1)
            deg = d % n
        semitone = intervals[deg] + octave_shift * 12
        root_offset = _NOTE_SEMITONES.get(self._root, 0)
        return max(0, min(127, BASE_MIDI + root_offset + semitone + self._transpose))

    def _resolve(self, step_or_name):
        """Accept int step or str note name, return MIDI number."""
        if isinstance(step_or_name, str):
            return self._name_to_midi(step_or_name)
        return self._step_to_midi(int(step_or_name))

    def _push(self, ev: dict):
        if len(self.events) >= MAX_EVENTS:
            raise _TooManyEvents(
                f"Event limit ({MAX_EVENTS}) reached — reduce loop iterations."
            )
        # Apply humanization to note events
        if ev.get("type") == "note" and (self._humanize_t > 0 or self._humanize_v > 0):
            if self._humanize_t > 0:
                ev["time"] = max(0.0, ev["time"] + self._rng.uniform(-self._humanize_t, self._humanize_t))
            if self._humanize_v > 0:
                ev["velocity"] = max(0, min(127, ev["velocity"] + self._rng.randint(-self._humanize_v, self._humanize_v)))
        self.events.append(ev)

    # ------------------------------------------------------------------
    # Public API — Notes
    # ------------------------------------------------------------------
    def play_note(self, step_or_note, duration=0.5, velocity=90):
        """
        Play a single note.

        step_or_note : int scale degree  OR  str note name ('E4', 'Bb3', 'C#5').
          As int : 0=root, 1=2nd degree, 7=next-octave root, −1=below root.
                   In chromatic mode each step = 1 semitone from root.
          As str : absolute pitch regardless of scale/root setting.
        duration     : length in beats.  Use named constants: Q, H, W, eighth_note…
        velocity     : loudness 0–127.  90=forte, 64=mp, 127=fff.
        """
        midi = self._resolve(step_or_note)
        dur_s = self._beats_to_sec(float(duration))
        self._push({
            "type": "note",
            "note": midi,
            "time": round(self._time, 6),
            "duration": round(max(0.02, dur_s), 6),
            "velocity": max(0, min(127, int(velocity))),
            "instrument": self._instrument,
        })
        self._time += dur_s

    def play_chord(self, steps, duration=1, velocity=90):
        """
        Play multiple notes simultaneously.
        steps    : list of int steps OR str note names (may be mixed).
        duration : length in beats.
        velocity : loudness 0–127.
        """
        t = self._time
        dur_s = self._beats_to_sec(float(duration))
        for s in steps:
            self._push({
                "type": "note",
                "note": self._resolve(s),
                "time": round(t, 6),
                "duration": round(max(0.02, dur_s), 6),
                "velocity": max(0, min(127, int(velocity))),
                "instrument": self._instrument,
            })
        self._time = t + dur_s

    def strum(self, steps, duration=1, velocity=90, gap=0.04):
        """
        Play a chord with each note staggered by gap seconds — realistic strum.
        steps    : list of steps/note-names (low→high order sounds natural).
        duration : hold length in beats.
        gap      : seconds between each note strike (default 0.04 s ≈ 40 ms).
        """
        t = self._time
        dur_s = self._beats_to_sec(float(duration))
        for i, s in enumerate(steps):
            self._push({
                "type": "note",
                "note": self._resolve(s),
                "time": round(t + i * float(gap), 6),
                "duration": round(max(0.02, dur_s), 6),
                "velocity": max(0, min(127, int(velocity) - i * 3)),  # slight decay per string
                "instrument": self._instrument,
            })
        self._time = t + dur_s

    def arpeggio(self, steps, note_duration=0.25, style="up", repeats=1):
        """
        Play steps as an arpeggio pattern.
        steps         : list of steps/note-names.
        note_duration : beats per note.
        style         : 'up' | 'down' | 'updown' | 'downup' | 'random'
        repeats       : how many times to cycle.
        """
        seq = list(steps)
        if style == "down":
            seq = list(reversed(seq))
        elif style == "updown":
            seq = seq + list(reversed(seq[1:-1]))
        elif style == "downup":
            seq = list(reversed(seq)) + seq[1:-1]
        elif style == "random":
            seq = seq[:]
            self._rng.shuffle(seq)
        for _ in range(int(repeats)):
            for s in seq:
                self.play_note(s, note_duration)

    def echo(self, step_or_note, duration=0.5, velocity=90, times=3, decay=0.55, gap_beats=0.5):
        """
        Play a note followed by quieter echoes.
        times      : number of echoes (not counting the original).
        decay      : velocity multiplier per echo (0.5 = halves each time).
        gap_beats  : beats between each echo.
        """
        self.play_note(step_or_note, duration, velocity)
        t_save = self._time
        for i in range(1, int(times) + 1):
            echo_vel = int(velocity * (decay ** i))
            if echo_vel < 4:
                break
            echo_time = t_save + (i - 1) * self._beats_to_sec(float(gap_beats))
            self._push({
                "type": "note",
                "note": self._resolve(step_or_note),
                "time": round(echo_time, 6),
                "duration": round(max(0.02, self._beats_to_sec(float(duration))), 6),
                "velocity": max(0, min(127, echo_vel)),
                "instrument": self._instrument,
            })

    def trill(self, step_a, step_b, total_duration=1, note_duration=0.125):
        """
        Alternate rapidly between two notes (trill ornament).
        step_a / step_b : two pitches to alternate (int or str).
        total_duration  : beats for the whole trill.
        note_duration   : beats per individual note.
        """
        beats_done = 0.0
        toggle = False
        while beats_done < float(total_duration) - 0.001:
            nd = min(float(note_duration), float(total_duration) - beats_done)
            self.play_note(step_b if toggle else step_a, nd)
            beats_done += nd
            toggle = not toggle

    def play_drum(self, drum=0, velocity=90):
        """
        Trigger a drum sound at the current cursor.
        Does NOT advance time — combine with rest() to lay a rhythm.

        0=Kick  1=Snare  2=Hi-hat  3=Open hat  4=Clap  5=Tom
        """
        self._push({
            "type": "drum",
            "drum": max(0, min(5, int(drum))),
            "time": round(self._time, 6),
            "duration": 0.05,
            "velocity": max(0, min(127, int(velocity))),
        })

    def rest(self, duration=1):
        """
        Advance time by duration beats without playing anything.
        Supports named constants: rest(whole_note), rest(H), etc.
        """
        self._time += self._beats_to_sec(float(duration))

    def set_bpm(self, bpm):
        """Set tempo in BPM (20–400). Affects all subsequent beat→second conversions."""
        self._bpm = max(20.0, min(400.0, float(bpm)))

    def set_instrument(self, name):
        """
        Switch the active instrument.
        Options: 'piano'  'synth'  'pad'  'bass'  'pluck'
        """
        if str(name).lower() in {"piano", "synth", "pad", "bass", "pluck"}:
            self._instrument = str(name).lower()

    def transpose(self, semitones):
        """
        Shift all subsequent notes up or down by semitones.
        transpose(7)   → up a fifth
        transpose(-12) → down an octave
        transpose(0)   → reset
        """
        self._transpose = int(semitones)

    def humanize(self, timing=0.02, velocity=10):
        """
        Add subtle randomness to make music feel less robotic.
        timing   : max timing jitter in seconds (0.02 s ≈ 20 ms is subtle).
        velocity : max velocity variation ±N.
        Pass humanize(0, 0) to turn off.
        """
        self._humanize_t = max(0.0, float(timing))
        self._humanize_v = max(0, int(velocity))

    def set_scale(self, root=None, scale_type=None):
        """
        Change the active scale / root for note resolution.
        root       : 'C' 'Db' 'D' 'Eb' 'E' 'F' 'Gb' 'G' 'Ab' 'A' 'Bb' 'B'
        scale_type : 'chromatic' 'major' 'minor' 'pentatonic_major'
                     'pentatonic_minor' 'blues' 'dorian' 'phrygian'
                     'mixolydian' 'harmonic_minor' 'whole_tone'
        """
        if root is not None and root in _NOTE_SEMITONES:
            self._root = str(root)
        if scale_type is not None and scale_type in SCALE_INTERVALS:
            self._scale = str(scale_type)

    def rewind(self, beats=None):
        """
        Move the cursor backwards.
        rewind()     → jump to 0:00.
        rewind(2)    → go back 2 beats from current position.
        """
        if beats is None:
            self._time = 0.0
        else:
            self._time = max(0.0, self._time - self._beats_to_sec(float(beats)))

    def set_time(self, beats):
        """
        Jump the cursor to an absolute beat position.
        Useful for layering drums over a melody on the same track.
        """
        self._time = max(0.0, self._beats_to_sec(float(beats)))

    def get_bpm(self):
        """Return current BPM."""
        return self._bpm

    def current_beat(self):
        """Return current cursor position in beats."""
        return self._time / (60.0 / self._bpm)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def _execute(code: str, init_bpm=120.0, root="C", scale="chromatic", instrument="piano") -> dict:
    result = {"events": [], "output": [], "error": None, "bpm": init_bpm}

    err = _check_ast(code)
    if err:
        result["error"] = err
        return result

    ctx = _MusicContext(bpm=init_bpm, root=root, scale=scale, instrument=instrument)
    output_lines: list = []

    def _safe_print(*args, **kwargs):
        output_lines.append(" ".join(str(a) for a in args))

    # Note-name → step helper
    def _note_fn(name: str) -> int:
        name = name.strip()
        if len(name) >= 2 and name[1] in ("#", "b"):
            letter, rest = name[:2], name[2:]
        else:
            letter, rest = name[0], name[1:]
        octave = int(rest) if rest else 4
        semitone = _NOTE_SEMITONES.get(letter, 0)
        return semitone + (octave - 4) * 12  # relative to C4

    safe_globals = {
        "__builtins__": {
            k: getattr(_builtins, k)
            for k in _SAFE_BUILTIN_NAMES
            if hasattr(_builtins, k)
        },
        "print": _safe_print,
        # Music API — playback
        "play_note":      ctx.play_note,
        "play_chord":     ctx.play_chord,
        "play_drum":      ctx.play_drum,
        "strum":          ctx.strum,
        "arpeggio":       ctx.arpeggio,
        "echo":           ctx.echo,
        "trill":          ctx.trill,
        # Music API — time & cursor
        "rest":           ctx.rest,
        "rewind":         ctx.rewind,
        "set_time":       ctx.set_time,
        "current_beat":   ctx.current_beat,
        # Music API — global settings
        "set_bpm":        ctx.set_bpm,
        "get_bpm":        ctx.get_bpm,
        "set_instrument": ctx.set_instrument,
        "set_scale":      ctx.set_scale,
        "transpose":      ctx.transpose,
        "humanize":       ctx.humanize,
        # Note name helper
        "note":           _note_fn,
        # Duration constants
        **DURATION_CONSTANTS,
    }

    exc_holder: list = [None]

    def _target():
        try:
            exec(compile(code, "<pad>", "exec"), safe_globals)
        except _TooManyEvents as e:
            exc_holder[0] = str(e)
        except Exception as e:
            exc_holder[0] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(EXEC_TIMEOUT)

    if t.is_alive():
        result["error"] = f"Execution timed out ({EXEC_TIMEOUT}s). Reduce loop size."
    elif exc_holder[0]:
        result["error"] = exc_holder[0]
    else:
        result["events"] = ctx.events
        result["output"] = output_lines
        result["bpm"] = ctx._bpm

    return result


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
@ensure_csrf_cookie
@require_GET
def pad_view(request: HttpRequest) -> HttpResponse:
    return render(request, "pad/pad.html")


@require_POST
def run_code(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body)
        tracks = body.get("tracks", [])
        global_bpm = float(body.get("bpm", 120))
        global_root = str(body.get("root", "C"))
        global_scale = str(body.get("scale", "chromatic"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid request body"}, status=400)

    global_bpm = max(20.0, min(400.0, global_bpm))

    all_events: list = []
    all_output: list = []

    for idx, track in enumerate(tracks):
        if not track.get("armed", True):
            continue
        code = str(track.get("code", "")).strip()
        if not code:
            continue
        if len(code) > 50_000:
            return JsonResponse({"error": f"Track {idx + 1} code exceeds 50 KB"}, status=400)
        instrument = str(track.get("instrument", "piano"))

        data = _execute(code, global_bpm, global_root, global_scale, instrument)
        if data["error"]:
            return JsonResponse({"error": f"Track {idx + 1}: {data['error']}"})

        all_events.extend(data["events"])
        all_output.extend([f"[T{idx+1}] {line}" for line in data["output"]])
        global_bpm = data["bpm"]  # let last set_bpm() win

    all_events.sort(key=lambda e: e["time"])

    return JsonResponse({
        "events": all_events,
        "output": all_output,
        "bpm": global_bpm,
        "error": None,
    })
