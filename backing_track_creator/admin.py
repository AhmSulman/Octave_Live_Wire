from django.contrib import admin

from .models import AudioUpload


@admin.register(AudioUpload)
class AudioUploadAdmin(admin.ModelAdmin):
    list_display = ("file_name", "bpm", "key_detected", "is_minor", "duration", "file_size", "uploaded_at")
    list_filter = ("is_minor", "key_detected")
    search_fields = ("file_name",)
    ordering = ("-uploaded_at",)

    # These fields are set programmatically — never let admin edit them.
    readonly_fields = ("file_name", "file_path", "file_size", "uploaded_at", "waveform_data")

    # Prevent creating new records through admin (uploads go through the API).
    def has_add_permission(self, _request):
        return False

    # Prevent bulk deletion through the action menu.
    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
