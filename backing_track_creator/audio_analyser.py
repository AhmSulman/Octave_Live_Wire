import base64
import io

import librosa
import librosa.display
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


class AudioAnalyser:

    pitch_classes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    major_profile = np.array(
        [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    )
    minor_profile = np.array(
        [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    )

    key_profiles = {}

    @classmethod
    def get_key_profiles(cls):
        if not cls.key_profiles:
            for i, pitch in enumerate(cls.pitch_classes):
                cls.key_profiles[f"{pitch} Major"] = np.roll(cls.major_profile, i)
                cls.key_profiles[f"{pitch} Minor"] = np.roll(cls.minor_profile, i)
        return cls.key_profiles

    @staticmethod
    def detect_key(chroma_vector):
        similarities = {
            key: np.dot(chroma_vector, profile)
            for key, profile in AudioAnalyser.get_key_profiles().items()
        }
        detected_key = max(similarities, key=lambda k: similarities[k])
        is_minor = "Minor" in detected_key
        return detected_key, is_minor

    @classmethod
    def analyze_file(cls, filepath):
        try:
            y, sr = librosa.load(filepath)

            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(np.asarray(tempo).item())

            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            chroma_avg = np.mean(chroma, axis=1)
            chroma_norm = chroma_avg / (np.linalg.norm(chroma_avg) + 1e-8)

            key_name, is_minor = cls.detect_key(chroma_norm)

            step = max(1, len(y) // 1000)
            samples = y[::step]
            max_abs = float(np.max(np.abs(samples))) if len(samples) else 1.0
            if max_abs == 0:
                max_abs = 1.0

            waveform_data = (128 + (samples / max_abs * 127)).astype(int).tolist()

            result = {
                "bpm": round(bpm, 2),
                "key": key_name,
                "is_minor": is_minor,
                "duration": float(librosa.get_duration(y=y, sr=sr)),
                "sample_rate": int(sr),
                "waveform_data": waveform_data[:1000],
            }

            plt.figure(figsize=(10, 4))
            librosa.display.waveshow(samples, sr=sr)
            plt.title(f"Waveform - BPM: {bpm:.0f}, Key: {key_name}")
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode("utf-8")
            buf.close()
            plt.close()

            result["waveform_image"] = f"data:image/png;base64,{img_base64}"

            return result
        except Exception as e:
            raise Exception(f"Analysis failed: {str(e)}")
