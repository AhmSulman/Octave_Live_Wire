from django.db import models
import json


class AudioUpload(models.Model):
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    bpm = models.FloatField(null=True, blank=True)
    key_detected = models.CharField(max_length=50, null=True, blank=True)
    is_minor = models.BooleanField(default=False)
    duration = models.FloatField(null=True, blank=True)
    waveform_data = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.file_name

    def get_waveform(self):
        try:
            return json.loads(self.waveform_data) if self.waveform_data else []
        except Exception:
            return []

    def set_waveform(self, samples):
        self.waveform_data = json.dumps(list(samples))
